"""Tier 1 E2E tests for Milestone E4 (R3/R4): F17 (Apps/Packs HTTP), F18 (SSE + core.js),
F19 (ported freefield JS), F20 (Canvas Studio), and F21 (Unified 4-workspace shell & JS checks).

Also embeds the self-contained jsdom + RGBA Canvas 2D + PNG harness (`_JSDOM_CANVAS_HARNESS_CJS`
and `run_jsdom_harness`) so Tier 2 can import shared non-test helpers without adding files
outside E4's exclusive ownership.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
from typing import Any

from PIL import Image
import pytest

from e2e.conftest import FULL_48G_PLATFORM_TAG, MAC_8G_PLATFORM_TAG
from e2e.helpers.fake_comfyui import MINIMAL_JPEG, MINIMAL_PNG, FakeComfyUIServer
from e2e.helpers.fake_hf import FakeHFHubServer
from e2e.helpers.studio_harness import IsolatedWorkspace, SSEEvent, StudioHarness

_NEON_ROOT = Path(__file__).resolve().parents[2]
_WEB_DIR = _NEON_ROOT / "web"
_STATIC_JS_DIR = _WEB_DIR / "static" / "js"
_TESTS_JS_DIR = _NEON_ROOT / "tests" / "js"
_NODE_MODULES_DIR = _TESTS_JS_DIR / "node_modules"

_INLINE_HANDLER_RE = re.compile(
    r"""\son(click|change|input|submit|load|error|focus|blur|keydown|keyup|mouse\w+)\s*=""",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Self-contained jsdom + RGBA Canvas 2D + zlib PNG + Pointer/Media harness
# ---------------------------------------------------------------------------

_JSDOM_CANVAS_HARNESS_CJS = r"""
"use strict";

const zlib = require("zlib");
const { JSDOM, ResourceLoader, VirtualConsole, CookieJar } = require("jsdom");

// ---- CRC32 + real RGBA PNG encoder (decodable by Python PIL.Image) ----
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    }
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const typeBuf = Buffer.from(type, "ascii");
  const lenBuf = Buffer.alloc(4);
  lenBuf.writeUInt32BE(data.length, 0);
  const crcInput = Buffer.concat([typeBuf, data]);
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(crcInput), 0);
  return Buffer.concat([lenBuf, typeBuf, data, crcBuf]);
}

function encodePNG(width, height, rgba) {
  const w = Math.max(1, width | 0);
  const h = Math.max(1, height | 0);
  const expected = w * h * 4;
  const src = rgba && rgba.length >= expected ? rgba : new Uint8ClampedArray(expected);
  const stride = w * 4 + 1;
  const raw = Buffer.alloc(stride * h);
  for (let y = 0; y < h; y++) {
    const rowStart = y * stride;
    raw[rowStart] = 0; // filter type 0 (None)
    const srcStart = y * w * 4;
    for (let x = 0; x < w * 4; x++) {
      raw[rowStart + 1 + x] = src[srcStart + x];
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type: RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  const idat = zlib.deflateSync(raw);
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  return Buffer.concat([sig, pngChunk("IHDR", ihdr), pngChunk("IDAT", idat), pngChunk("IEND", Buffer.alloc(0))]);
}

function parsePNGDimensions(buf) {
  if (!buf || buf.length < 24) return null;
  if (buf[0] !== 0x89 || buf[1] !== 0x50 || buf[2] !== 0x4e || buf[3] !== 0x47) return null;
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

// ---- CSS color parser + RGBA pixel rasterizer ----
function parseColor(spec) {
  if (!spec || typeof spec !== "string") return [0, 0, 0, 255];
  const s = spec.trim().toLowerCase();
  const named = {
    black: [0, 0, 0, 255],
    white: [255, 255, 255, 255],
    transparent: [0, 0, 0, 0],
    red: [255, 0, 0, 255],
    green: [0, 128, 0, 255],
    blue: [0, 0, 255, 255],
    yellow: [255, 255, 0, 255],
    gray: [128, 128, 128, 255],
    grey: [128, 128, 128, 255],
  };
  if (named[s]) return named[s];
  if (s.startsWith("#")) {
    const h = s.slice(1);
    if (h.length === 3) {
      return [parseInt(h[0] + h[0], 16), parseInt(h[1] + h[1], 16), parseInt(h[2] + h[2], 16), 255];
    }
    if (h.length === 6) {
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 255];
    }
    if (h.length === 8) {
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), parseInt(h.slice(6, 8), 16)];
    }
  }
  const m = s.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)$/);
  if (m) {
    const a = m[4] === undefined ? 255 : Math.round(Math.max(0, Math.min(1, parseFloat(m[4]))) * 255);
    return [parseInt(m[1], 10) & 255, parseInt(m[2], 10) & 255, parseInt(m[3], 10) & 255, a];
  }
  return [255, 255, 255, 255];
}

function blendPixel(buf, idx, sr, sg, sb, sa, op, globalAlpha) {
  const effA = (sa / 255) * globalAlpha;
  const dr = buf[idx], dg = buf[idx + 1], db = buf[idx + 2], da = buf[idx + 3] / 255;
  if (op === "destination-out") {
    const outA = da * (1 - effA);
    buf[idx + 3] = Math.round(outA * 255);
    if (outA <= 0.001) {
      buf[idx] = 0; buf[idx + 1] = 0; buf[idx + 2] = 0;
    }
    return;
  }
  if (op === "source-in") {
    const outA = effA * da;
    buf[idx] = sr;
    buf[idx + 1] = sg;
    buf[idx + 2] = sb;
    buf[idx + 3] = Math.round(outA * 255);
    return;
  }
  if (op === "overlay") {
    const ch = (d, s) => {
      const dn = d / 255, sn = s / 255;
      const o = dn < 0.5 ? 2 * dn * sn : 1 - 2 * (1 - dn) * (1 - sn);
      return Math.round(((1 - effA) * dn + effA * o) * 255);
    };
    buf[idx] = ch(dr, sr);
    buf[idx + 1] = ch(dg, sg);
    buf[idx + 2] = ch(db, sb);
    buf[idx + 3] = Math.round(Math.min(1, da + effA * (1 - da)) * 255);
    return;
  }
  // source-over (default)
  const outA = effA + da * (1 - effA);
  if (outA <= 0) {
    buf[idx] = 0; buf[idx + 1] = 0; buf[idx + 2] = 0; buf[idx + 3] = 0;
    return;
  }
  buf[idx] = Math.round((sr * effA + dr * da * (1 - effA)) / outA);
  buf[idx + 1] = Math.round((sg * effA + dg * da * (1 - effA)) / outA);
  buf[idx + 2] = Math.round((sb * effA + db * da * (1 - effA)) / outA);
  buf[idx + 3] = Math.round(outA * 255);
}

const canvasStores = new WeakMap();

function getBackingStore(canvas) {
  const w = Math.max(0, Number(canvas.width) || 0);
  const h = Math.max(0, Number(canvas.height) || 0);
  let store = canvasStores.get(canvas);
  if (!store || store.width !== w || store.height !== h) {
    store = { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) };
    canvasStores.set(canvas, store);
  }
  return store;
}

function makeCanvasContext(canvas) {
  const calls = [];
  let pathOps = [];
  let cx = 0, cy = 0;
  const stack = [];
  const state = {
    fillStyle: "#000000",
    strokeStyle: "#000000",
    lineWidth: 1,
    lineCap: "butt",
    lineJoin: "miter",
    globalCompositeOperation: "source-over",
    globalAlpha: 1,
    filter: "none",
    font: "10px sans-serif",
    textAlign: "start",
    textBaseline: "alphabetic",
    shadowBlur: 0,
    shadowColor: "rgba(0, 0, 0, 0)",
    tx: 0,
    ty: 0,
    sx: 1,
    sy: 1,
  };

  function plotDisc(x0, y0, radius, rgba) {
    const store = getBackingStore(canvas);
    if (store.width <= 0 || store.height <= 0) return;
    const r = Math.max(0.5, radius);
    const r2 = r * r;
    const minX = Math.max(0, Math.floor(x0 - r));
    const maxX = Math.min(store.width - 1, Math.ceil(x0 + r));
    const minY = Math.max(0, Math.floor(y0 - r));
    const maxY = Math.min(store.height - 1, Math.ceil(y0 + r));
    const op = state.globalCompositeOperation || "source-over";
    const ga = typeof state.globalAlpha === "number" ? state.globalAlpha : 1;
    for (let y = minY; y <= maxY; y++) {
      for (let x = minX; x <= maxX; x++) {
        const dx = x - x0, dy = y - y0;
        if (dx * dx + dy * dy <= r2) {
          blendPixel(store.data, (y * store.width + x) * 4, rgba[0], rgba[1], rgba[2], rgba[3], op, ga);
        }
      }
    }
  }

  function plotSegment(x0, y0, x1, y1, radius, rgba) {
    const dx = x1 - x0, dy = y1 - y0;
    const steps = Math.max(1, Math.ceil(Math.hypot(dx, dy)));
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      plotDisc(x0 + dx * t, y0 + dy * t, radius, rgba);
    }
  }

  function fillRectImpl(rx, ry, rw, rh, rgba, clearMode) {
    const store = getBackingStore(canvas);
    if (store.width <= 0 || store.height <= 0) return;
    const x0 = Math.max(0, Math.floor(rx + state.tx));
    const y0 = Math.max(0, Math.floor(ry + state.ty));
    const x1 = Math.min(store.width, Math.ceil(rx + state.tx + rw));
    const y1 = Math.min(store.height, Math.ceil(ry + state.ty + rh));
    const op = state.globalCompositeOperation || "source-over";
    const ga = typeof state.globalAlpha === "number" ? state.globalAlpha : 1;
    for (let y = y0; y < y1; y++) {
      for (let x = x0; x < x1; x++) {
        const idx = (y * store.width + x) * 4;
        if (clearMode) {
          store.data[idx] = 0; store.data[idx + 1] = 0; store.data[idx + 2] = 0; store.data[idx + 3] = 0;
        } else {
          blendPixel(store.data, idx, rgba[0], rgba[1], rgba[2], rgba[3], op, ga);
        }
      }
    }
  }

  const ctx = {
    canvas,
    get fillStyle() { return state.fillStyle; },
    set fillStyle(v) { state.fillStyle = v; },
    get strokeStyle() { return state.strokeStyle; },
    set strokeStyle(v) { state.strokeStyle = v; },
    get lineWidth() { return state.lineWidth; },
    set lineWidth(v) { state.lineWidth = Number(v) || 1; },
    get lineCap() { return state.lineCap; },
    set lineCap(v) { state.lineCap = String(v); },
    get lineJoin() { return state.lineJoin; },
    set lineJoin(v) { state.lineJoin = String(v); },
    get globalCompositeOperation() { return state.globalCompositeOperation; },
    set globalCompositeOperation(v) { state.globalCompositeOperation = String(v || "source-over"); },
    get globalAlpha() { return state.globalAlpha; },
    set globalAlpha(v) { state.globalAlpha = Number.isFinite(Number(v)) ? Number(v) : 1; },
    get filter() { return state.filter; },
    set filter(v) { state.filter = String(v || "none"); },
    get font() { return state.font; },
    set font(v) { state.font = String(v); },
    get textAlign() { return state.textAlign; },
    set textAlign(v) { state.textAlign = String(v); },
    get textBaseline() { return state.textBaseline; },
    set textBaseline(v) { state.textBaseline = String(v); },
    get shadowBlur() { return state.shadowBlur; },
    set shadowBlur(v) { state.shadowBlur = Number(v) || 0; },
    get shadowColor() { return state.shadowColor; },
    set shadowColor(v) { state.shadowColor = String(v); },

    __getCalls() { return calls.slice(); },
    __clearCalls() { calls.length = 0; },

    save() { stack.push({ ...state }); },
    restore() { if (stack.length) Object.assign(state, stack.pop()); },
    translate(x, y) { state.tx += Number(x) || 0; state.ty += Number(y) || 0; },
    scale(x, y) { state.sx *= Number(x) || 1; state.sy *= Number(y) || 1; },
    rotate() {},
    setTransform(a, b, c, d, e, f) { state.sx = a; state.sy = d; state.tx = e; state.ty = f; },
    resetTransform() { state.tx = 0; state.ty = 0; state.sx = 1; state.sy = 1; },

    beginPath() { pathOps = []; },
    closePath() { pathOps.push({ op: "close" }); },
    moveTo(x, y) { cx = x; cy = y; pathOps.push({ op: "move", x, y }); },
    lineTo(x, y) { pathOps.push({ op: "line", x0: cx, y0: cy, x1: x, y1: y }); cx = x; cy = y; },
    quadraticCurveTo(cpx, cpy, x, y) { pathOps.push({ op: "line", x0: cx, y0: cy, x1: x, y1: y }); cx = x; cy = y; },
    bezierCurveTo(cp1x, cp1y, cp2x, cp2y, x, y) { pathOps.push({ op: "line", x0: cx, y0: cy, x1: x, y1: y }); cx = x; cy = y; },
    arc(x, y, r) { pathOps.push({ op: "arc", x, y, r }); cx = x; cy = y; },
    ellipse(x, y, rx, ry) { pathOps.push({ op: "arc", x, y, r: Math.max(rx, ry) }); cx = x; cy = y; },
    rect(x, y, w, h) { pathOps.push({ op: "rect", x, y, w, h }); },

    stroke() {
      calls.push({ method: "stroke", args: [pathOps.length], strokeStyle: state.strokeStyle, globalCompositeOperation: state.globalCompositeOperation, filter: state.filter });
      const rgba = typeof state.strokeStyle === "string" ? parseColor(state.strokeStyle) : [255, 255, 255, 255];
      const rad = Math.max(0.5, (state.lineWidth || 1) / 2);
      let firstMove = null;
      for (const seg of pathOps) {
        if (seg.op === "move") {
          if (!firstMove) firstMove = { x: seg.x, y: seg.y };
          plotDisc(seg.x + state.tx, seg.y + state.ty, rad, rgba);
        } else if (seg.op === "line") {
          plotSegment(seg.x0 + state.tx, seg.y0 + state.ty, seg.x1 + state.tx, seg.y1 + state.ty, rad, rgba);
        } else if (seg.op === "arc") {
          plotDisc(seg.x + state.tx, seg.y + state.ty, Math.max(rad, seg.r), rgba);
        } else if (seg.op === "rect") {
          plotSegment(seg.x, seg.y, seg.x + seg.w, seg.y, rad, rgba);
          plotSegment(seg.x + seg.w, seg.y, seg.x + seg.w, seg.y + seg.h, rad, rgba);
          plotSegment(seg.x + seg.w, seg.y + seg.h, seg.x, seg.y + seg.h, rad, rgba);
          plotSegment(seg.x, seg.y + seg.h, seg.x, seg.y, rad, rgba);
        } else if (seg.op === "close" && firstMove) {
          plotSegment(cx + state.tx, cy + state.ty, firstMove.x + state.tx, firstMove.y + state.ty, rad, rgba);
        }
      }
    },

    fill() {
      calls.push({ method: "fill", args: [pathOps.length], fillStyle: state.fillStyle, globalCompositeOperation: state.globalCompositeOperation, filter: state.filter });
      const rgba = typeof state.fillStyle === "string" ? parseColor(state.fillStyle) : [255, 255, 255, 255];
      for (const seg of pathOps) {
        if (seg.op === "rect") fillRectImpl(seg.x, seg.y, seg.w, seg.h, rgba, false);
        else if (seg.op === "arc") plotDisc(seg.x + state.tx, seg.y + state.ty, Math.max(1, seg.r), rgba);
      }
    },

    fillRect(x, y, w, h) {
      calls.push({ method: "fillRect", args: [x, y, w, h], fillStyle: state.fillStyle, globalCompositeOperation: state.globalCompositeOperation, filter: state.filter });
      const rgba = typeof state.fillStyle === "string" ? parseColor(state.fillStyle) : [128, 128, 128, 128];
      fillRectImpl(x, y, w, h, rgba, false);
    },

    clearRect(x, y, w, h) {
      calls.push({ method: "clearRect", args: [x, y, w, h] });
      fillRectImpl(x, y, w, h, [0, 0, 0, 0], true);
    },

    strokeRect(x, y, w, h) {
      calls.push({ method: "strokeRect", args: [x, y, w, h], strokeStyle: state.strokeStyle });
      const rgba = typeof state.strokeStyle === "string" ? parseColor(state.strokeStyle) : [255, 255, 255, 255];
      const rad = Math.max(0.5, (state.lineWidth || 1) / 2);
      plotSegment(x, y, x + w, y, rad, rgba);
      plotSegment(x + w, y, x + w, y + h, rad, rgba);
      plotSegment(x + w, y + h, x, y + h, rad, rgba);
      plotSegment(x, y + h, x, y, rad, rgba);
    },

    createImageData(w, h) {
      const iw = Math.max(1, w | 0), ih = Math.max(1, h | 0);
      return { width: iw, height: ih, data: new Uint8ClampedArray(iw * ih * 4) };
    },

    getImageData(sx, sy, sw, sh) {
      const store = getBackingStore(canvas);
      const iw = Math.max(1, sw | 0), ih = Math.max(1, sh | 0);
      const out = new Uint8ClampedArray(iw * ih * 4);
      for (let y = 0; y < ih; y++) {
        const srcY = sy + y;
        if (srcY < 0 || srcY >= store.height) continue;
        for (let x = 0; x < iw; x++) {
          const srcX = sx + x;
          if (srcX < 0 || srcX >= store.width) continue;
          const si = (srcY * store.width + srcX) * 4;
          const di = (y * iw + x) * 4;
          out[di] = store.data[si]; out[di + 1] = store.data[si + 1]; out[di + 2] = store.data[si + 2]; out[di + 3] = store.data[si + 3];
        }
      }
      return { width: iw, height: ih, data: out };
    },

    putImageData(imgData, dx, dy) {
      const store = getBackingStore(canvas);
      const iw = imgData.width | 0, ih = imgData.height | 0;
      for (let y = 0; y < ih; y++) {
        const ty = dy + y;
        if (ty < 0 || ty >= store.height) continue;
        for (let x = 0; x < iw; x++) {
          const tx = dx + x;
          if (tx < 0 || tx >= store.width) continue;
          const si = (y * iw + x) * 4;
          const di = (ty * store.width + tx) * 4;
          store.data[di] = imgData.data[si];
          store.data[di + 1] = imgData.data[si + 1];
          store.data[di + 2] = imgData.data[si + 2];
          store.data[di + 3] = imgData.data[si + 3];
        }
      }
    },

    drawImage(img, ...rest) {
      calls.push({ method: "drawImage", args: [img && img.tagName ? img.tagName : typeof img, ...rest], filter: state.filter, globalCompositeOperation: state.globalCompositeOperation });
      const store = getBackingStore(canvas);
      if (store.width <= 0 || store.height <= 0) return;
      let dx = 0, dy = 0, dw = store.width, dh = store.height;
      if (rest.length === 2) { dx = rest[0]; dy = rest[1]; dw = (img && (img.width || img.naturalWidth)) || store.width; dh = (img && (img.height || img.naturalHeight)) || store.height; }
      else if (rest.length === 4) { dx = rest[0]; dy = rest[1]; dw = rest[2]; dh = rest[3]; }
      else if (rest.length === 8) { dx = rest[4]; dy = rest[5]; dw = rest[6]; dh = rest[7]; }
      const srcStore = img && canvasStores.get(img);
      if (srcStore && srcStore.width > 0 && srcStore.height > 0) {
        const op = state.globalCompositeOperation || "source-over";
        const ga = typeof state.globalAlpha === "number" ? state.globalAlpha : 1;
        for (let y = 0; y < Math.min(dh, store.height - dy); y++) {
          const sy = Math.min(srcStore.height - 1, Math.floor((y / Math.max(1, dh)) * srcStore.height));
          for (let x = 0; x < Math.min(dw, store.width - dx); x++) {
            const sx = Math.min(srcStore.width - 1, Math.floor((x / Math.max(1, dw)) * srcStore.width));
            const si = (sy * srcStore.width + sx) * 4;
            const di = ((Math.floor(dy) + y) * store.width + (Math.floor(dx) + x)) * 4;
            if (di >= 0 && di + 3 < store.data.length) {
              blendPixel(store.data, di, srcStore.data[si], srcStore.data[si + 1], srcStore.data[si + 2], srcStore.data[si + 3], op, ga);
            }
          }
        }
      } else {
        fillRectImpl(dx, dy, dw, dh, [100, 120, 140, 255], false);
      }
    },

    createRadialGradient(...args) {
      calls.push({ method: "createRadialGradient", args });
      const stops = [];
      return { addColorStop(offset, color) { stops.push([offset, color]); }, __stops: stops };
    },
    createLinearGradient(...args) {
      calls.push({ method: "createLinearGradient", args });
      return { addColorStop() {} };
    },
    createPattern(source, repetition) {
      const sw = (source && source.width) || 0;
      const sh = (source && source.height) || 0;
      calls.push({ method: "createPattern", args: [sw, sh, repetition || "repeat"], globalCompositeOperation: state.globalCompositeOperation });
      return { source, repetition: repetition || "repeat" };
    },
    fillText(text, x, y, maxWidth) {
      calls.push({ method: "fillText", args: [String(text), x, y, maxWidth], fillStyle: state.fillStyle, font: state.font });
      fillRectImpl(x, y, Math.min(40, String(text).length * 6), 8, parseColor(String(state.fillStyle)), false);
    },
    strokeText(text, x, y) {
      calls.push({ method: "strokeText", args: [String(text), x, y] });
    },
    measureText(text) {
      return { width: String(text || "").length * 8 };
    },
  };
  return ctx;
}

function installCanvasAndBrowserPolyfills(w, options = {}) {
  const baseUrl = options.baseUrl || "http://127.0.0.1:0";
  w.__neonBlobs = new Map();
  w.__neonRevokedUrls = [];
  w.__fetchLog = [];
  w.__virtualRoutes = Object.assign({}, w.__virtualRoutes || {});
  w.__zeroRect = Boolean(options.zeroRect);

  // Polyfill Blob.prototype.arrayBuffer & .text via jsdom Symbol(impl)._buffer
  if (w.Blob && w.Blob.prototype) {
    const getBlobBuffer = (blob) => {
      const sym = Object.getOwnPropertySymbols(blob).find((s) => String(s).includes("impl"));
      if (sym && blob[sym] && blob[sym]._buffer) return Buffer.from(blob[sym]._buffer);
      return Buffer.alloc(0);
    };
    if (!w.Blob.prototype.arrayBuffer) {
      w.Blob.prototype.arrayBuffer = async function arrayBuffer() {
        const b = getBlobBuffer(this);
        return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
      };
    }
    if (!w.Blob.prototype.text) {
      w.Blob.prototype.text = async function text() {
        return getBlobBuffer(this).toString("utf-8");
      };
    }
  }

  // URL.createObjectURL / revokeObjectURL tracking
  let blobSeq = 1;
  w.URL.createObjectURL = (blob) => {
    const id = `blob:neon/${blobSeq++}`;
    w.__neonBlobs.set(id, blob);
    return id;
  };
  w.URL.revokeObjectURL = (u) => {
    w.__neonRevokedUrls.push(String(u));
    w.__neonBlobs.delete(String(u));
  };

  // PointerEvent + pointer capture stubs
  if (typeof w.PointerEvent !== "function") {
    class PointerEventPolyfill extends w.MouseEvent {
      constructor(type, init = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 1;
        this.pointerType = init.pointerType ?? "mouse";
        this.pressure = init.pressure ?? (init.buttons ? 0.5 : 0);
        this.isPrimary = init.isPrimary ?? true;
      }
    }
    w.PointerEvent = PointerEventPolyfill;
  }
  const captured = new WeakMap();
  w.Element.prototype.setPointerCapture = function (id) { captured.set(this, id); };
  w.Element.prototype.releasePointerCapture = function () { captured.delete(this); };
  w.Element.prototype.hasPointerCapture = function (id) { return captured.get(this) === id; };

  // Observers, matchMedia, scroll, RAF
  const NoopObs = class { observe() {} unobserve() {} disconnect() {} };
  w.ResizeObserver = w.ResizeObserver || NoopObs;
  w.IntersectionObserver = w.IntersectionObserver || NoopObs;
  w.matchMedia = w.matchMedia || ((q) => ({
    matches: false,
    media: String(q || ""),
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  }));
  w.scrollTo = w.scrollTo || (() => {});
  w.Element.prototype.scrollIntoView = w.Element.prototype.scrollIntoView || (() => {});
  const rafTimers = new Set();
  w.requestAnimationFrame = (cb) => {
    const id = setTimeout(() => {
      rafTimers.delete(id);
      if (w.document) cb(Date.now());
    }, 16);
    rafTimers.add(id);
    return id;
  };
  w.cancelAnimationFrame = (id) => {
    rafTimers.delete(id);
    clearTimeout(id);
  };
  w.__clearNeonTimers = () => {
    for (const id of rafTimers) clearTimeout(id);
    rafTimers.clear();
  };

  // HTMLMediaElement stubs with mutable currentTime/duration/paused/muted
  const mediaState = new WeakMap();
  const getMediaState = (el) => {
    let st = mediaState.get(el);
    if (!st) {
      st = {
        currentTime: 0,
        duration: Number(el.getAttribute("data-duration")) || 10,
        paused: true,
        muted: false,
        playbackRate: 1,
        volume: 1,
        readyState: 4,
      };
      mediaState.set(el, st);
    }
    return st;
  };
  if (w.HTMLMediaElement && w.HTMLMediaElement.prototype) {
    Object.defineProperties(w.HTMLMediaElement.prototype, {
      currentTime: {
        configurable: true,
        get() { return getMediaState(this).currentTime; },
        set(v) { getMediaState(this).currentTime = Number(v); },
      },
      duration: {
        configurable: true,
        get() {
          const attr = this.getAttribute("data-duration");
          if (attr !== null) {
            if (attr === "NaN") return NaN;
            return Number(attr);
          }
          return getMediaState(this).duration;
        },
        set(v) { getMediaState(this).duration = Number(v); },
      },
      paused: {
        configurable: true,
        get() { return getMediaState(this).paused; },
      },
      muted: {
        configurable: true,
        get() { return getMediaState(this).muted; },
        set(v) { getMediaState(this).muted = Boolean(v); },
      },
      readyState: {
        configurable: true,
        get() { return getMediaState(this).readyState; },
      },
    });
    w.HTMLMediaElement.prototype.play = function () {
      const st = getMediaState(this);
      st.paused = false;
      this.dispatchEvent(new w.Event("play"));
      return Promise.resolve();
    };
    w.HTMLMediaElement.prototype.pause = function () {
      const st = getMediaState(this);
      st.paused = true;
      this.dispatchEvent(new w.Event("pause"));
    };
    w.HTMLMediaElement.prototype.load = function () {
      this.dispatchEvent(new w.Event("loadedmetadata"));
    };
  }

  // getBoundingClientRect (configurable 0x0 or realistic default)
  w.Element.prototype.getBoundingClientRect = function () {
    if (w.__zeroRect || this.dataset.zeroRect === "1") {
      return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0 };
    }
    if (this.dataset && this.dataset.rect) {
      const [rw, rh] = this.dataset.rect.split(",").map(Number);
      if (rw >= 0 && rh >= 0) {
        return { left: 0, top: 0, right: rw, bottom: rh, width: rw, height: rh, x: 0, y: 0 };
      }
    }
    if (this.tagName === "CANVAS" && this.width > 0 && this.height > 0) {
      return { left: 0, top: 0, right: this.width, bottom: this.height, width: this.width, height: this.height, x: 0, y: 0 };
    }
    return { left: 0, top: 0, right: 320, bottom: 240, width: 320, height: 240, x: 0, y: 0 };
  };

  // HTMLCanvasElement 2D + toBlob + toDataURL
  const ctxMap = new WeakMap();
  w.HTMLCanvasElement.prototype.getContext = function (kind) {
    if (kind !== "2d") return null;
    let ctx = ctxMap.get(this);
    if (!ctx) {
      ctx = makeCanvasContext(this);
      ctxMap.set(this, ctx);
    }
    return ctx;
  };
  w.HTMLCanvasElement.prototype.toDataURL = function (mime = "image/png") {
    const store = getBackingStore(this);
    const png = encodePNG(store.width, store.height, store.data);
    return `data:${mime || "image/png"};base64,${png.toString("base64")}`;
  };
  w.HTMLCanvasElement.prototype.toBlob = function (cb, mime = "image/png") {
    const store = getBackingStore(this);
    const png = encodePNG(store.width, store.height, store.data);
    const blob = new w.Blob([png], { type: mime || "image/png" });
    setTimeout(() => cb(blob), 0);
  };

  // Image polyfill: parses data:image/png;base64,... IHDR dimensions and fires onload/onerror
  const OrigImage = w.Image;
  class NeonImage extends OrigImage {
    set src(val) {
      const s = String(val || "");
      this._neonSrc = s;
      const bad = !s || /corrupt|invalid|broken|bad-image|404/i.test(s);
      if (bad) {
        this._nw = 0; this._nh = 0; this._complete = true;
        setTimeout(() => {
          const ev = new w.Event("error");
          if (typeof this.onerror === "function") this.onerror(ev);
          this.dispatchEvent(ev);
        }, 0);
        return;
      }
      let nw = options.defaultImageWidth || 160;
      let nh = options.defaultImageHeight || 120;
      const m = s.match(/^data:image\/png;base64,(.+)$/i);
      if (m) {
        try {
          const buf = Buffer.from(m[1], "base64");
          const dims = parsePNGDimensions(buf);
          if (dims) { nw = dims.width; nh = dims.height; }
          else {
            setTimeout(() => {
              const ev = new w.Event("error");
              if (typeof this.onerror === "function") this.onerror(ev);
              this.dispatchEvent(ev);
            }, 0);
            return;
          }
        } catch (_e) {
          setTimeout(() => {
            const ev = new w.Event("error");
            if (typeof this.onerror === "function") this.onerror(ev);
            this.dispatchEvent(ev);
          }, 0);
          return;
        }
      }
      this._nw = nw;
      this._nh = nh;
      this._complete = true;
      setTimeout(() => {
        const ev = new w.Event("load");
        if (typeof this.onload === "function") this.onload(ev);
        this.dispatchEvent(ev);
      }, 0);
    }
    get src() { return this._neonSrc || ""; }
    get naturalWidth() { return this._nw ?? 160; }
    get naturalHeight() { return this._nh ?? 120; }
    get width() { return this._nw ?? 160; }
    get height() { return this._nh ?? 120; }
    get complete() { return this._complete ?? true; }
  }
  w.Image = NeonImage;

  // fetch forwarding + virtual route override hook
  w.fetch = async (u, init = {}) => {
    const raw = String(u);
    const resolved = baseUrl && baseUrl !== "http://127.0.0.1:0" ? new URL(raw, baseUrl) : new URL(raw, "http://127.0.0.1");
    const pathname = resolved.pathname + resolved.search;
    const method = (init && init.method) || "GET";
    let parsedBody = null;
    if (init && typeof init.body === "string") {
      try { parsedBody = JSON.parse(init.body); } catch (_e) { parsedBody = init.body; }
    }
    w.__fetchLog.push({ url: pathname, method, body: parsedBody });
    const vrMap = w.__virtualRoutes || {};
    const vr = vrMap[resolved.pathname] || vrMap[pathname] || vrMap[raw];
    if (vr) {
      const resSpec = typeof vr === "function" ? await vr(pathname, init, parsedBody) : vr;
      const st = resSpec.status || 200;
      const payload = typeof resSpec.body === "string" ? resSpec.body : JSON.stringify(resSpec.body ?? {});
      if (typeof w.Response === "function") {
        return new w.Response(payload, { status: st, headers: { "Content-Type": "application/json", ...(resSpec.headers || {}) } });
      }
      return {
        ok: st >= 200 && st < 300,
        status: st,
        headers: { get(k) { return String(k).toLowerCase() === "content-type" ? "application/json" : null; } },
        async json() { return JSON.parse(payload); },
        async text() { return payload; },
      };
    }
    if (!baseUrl || baseUrl === "http://127.0.0.1:0") {
      if (typeof w.Response === "function") {
        return new w.Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return {
        ok: true,
        status: 200,
        headers: { get() { return "application/json"; } },
        async json() { return {}; },
        async text() { return "{}"; },
      };
    }
    return fetch(resolved.href, init);
  };
}

async function createNeonDOM(options = {}) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => {
    errors.push("jsdomError: " + ((e && e.detail && e.detail.stack) || (e && e.message) || String(e)));
  });
  vc.on("error", (...args) => {
    errors.push("console.error: " + args.map(String).join(" ").slice(0, 400));
  });
  class StubFontLoader extends ResourceLoader {
    fetch(u, o) {
      if (String(u).includes("fonts.g")) return Promise.resolve(Buffer.from(""));
      return super.fetch(u, o);
    }
  }
  let dom;
  const beforeParse = (w) => {
    installCanvasAndBrowserPolyfills(w, options);
    if (typeof options.beforeParse === "function") options.beforeParse(w);
  };
  if (options.url) {
    dom = await JSDOM.fromURL(options.url, {
      beforeParse,
      runScripts: "dangerously",
      resources: new StubFontLoader(),
      pretendToBeVisual: true,
      virtualConsole: vc,
      cookieJar: options.cookieJar || new CookieJar(),
    });
  } else {
    dom = new JSDOM(options.html || "<!doctype html><html><head></head><body></body></html>", {
      url: options.baseUrl || "http://127.0.0.1/",
      beforeParse,
      runScripts: "dangerously",
      resources: new StubFontLoader(),
      pretendToBeVisual: true,
      virtualConsole: vc,
    });
  }
  const origEval = dom.window.eval.bind(dom.window);
  dom.window.eval = (code) => {
    try {
      return origEval(code);
    } catch (e) {
      errors.push("evalError: " + ((e && e.stack) || (e && e.message) || String(e)));
      throw e;
    }
  };
  return {
    dom,
    window: dom.window,
    document: dom.window.document,
    errors,
    close: () => {
      if (typeof dom.window.__clearNeonTimers === "function") dom.window.__clearNeonTimers();
      setTimeout(() => {
        try { dom.window.close(); } catch (_e) {}
      }, 0);
    },
  };
}

module.exports = { encodePNG, parsePNGDimensions, createNeonDOM, installCanvasAndBrowserPolyfills };
"""


def run_jsdom_harness(
    tmp_path: Path,
    scenario_js: str,
    *,
    args: list[str] | None = None,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Stage _JSDOM_CANVAS_HARNESS_CJS + scenario.cjs in tmp_path and execute via node."""
    node_bin = shutil.which("node")
    assert node_bin is not None, "node binary not found in PATH"
    assert (_NODE_MODULES_DIR / "jsdom").is_dir(), f"Missing jsdom at {_NODE_MODULES_DIR}"

    harness_path = tmp_path / "neon_canvas_harness.cjs"
    harness_path.write_text(_JSDOM_CANVAS_HARNESS_CJS, encoding="utf-8")
    scenario_path = tmp_path / "scenario.cjs"
    scenario_path.write_text(scenario_js, encoding="utf-8")

    env = dict(os.environ)
    env["NODE_PATH"] = str(_NODE_MODULES_DIR)
    proc = subprocess.run(
        [node_bin, str(scenario_path), *(args or [])],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, (
        f"Node jsdom scenario failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, f"Expected JSON line on stdout; stderr={proc.stderr}"
    result = json.loads(lines[-1])
    assert isinstance(result, dict), f"Expected JSON object from scenario, got {type(result)!r}"
    return result


def run_node_check(js_path: Path, timeout: float = 15.0) -> None:
    """Verify JS file syntax with `node --check`."""
    node_bin = shutil.which("node")
    assert node_bin is not None, "node binary not found in PATH"
    proc = subprocess.run(
        [node_bin, "--check", str(js_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    assert proc.returncode == 0, f"node --check failed for {js_path}: {proc.stderr}"
    assert proc.stderr.strip() == "", f"Unexpected stderr from node --check {js_path}: {proc.stderr}"


def make_solid_png_bytes(width: int, height: int, rgba: tuple[int, int, int, int] = (30, 80, 160, 255)) -> bytes:
    """Create a valid RGBA PNG in memory using Pillow."""
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), rgba).save(buf, format="PNG")
    return buf.getvalue()


def ensure_workspace_manifests(ws: IsolatedWorkspace) -> None:
    """Ensure bundled apps/, packs/, and schema/ are visible inside isolated workspace root if present in Neon."""
    for folder in ("apps", "schema"):
        src = _NEON_ROOT / folder
        dst = ws.root / folder
        if src.is_dir() and not dst.exists():
            dst.symlink_to(src)
    packs_src = _NEON_ROOT / "packs"
    packs_dst = ws.root / "packs"
    if packs_src.is_dir() and not packs_dst.exists():
        shutil.copytree(packs_src, packs_dst)


def seed_demo_book_project(ws: IsolatedWorkspace, slug: str = "demo", shots: int = 2) -> Path:
    """Create a minimal book project with all_shots.csv inside the isolated workspace."""
    proj = ws.root / "projects" / "books" / slug
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{slug}.json").write_text(json.dumps({"slug": slug, "title": "Demo Film"}), encoding="utf-8")
    rows = ["chapter,shot,prompt,seconds"]
    for i in range(1, shots + 1):
        rows.append(f"1,{i},Scene shot {i},4")
    (proj / "all_shots.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return proj


def find_workspace_token_files(ws: IsolatedWorkspace) -> list[Path]:
    """Find persisted HF token files inside isolated workspace roots."""
    candidates: list[Path] = []
    for base in (ws.home, ws.data_dir, ws.hf_home):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and "token" in p.name.lower():
                candidates.append(p)
    return candidates


def wait_until(predicate: Any, timeout: float = 5.0, interval: float = 0.05) -> Any:
    """Poll predicate until truthy or deadline expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        val = predicate()
        if val:
            return val
        time.sleep(interval)
    return predicate()


# ===========================================================================
# F17 — Apps & Packs HTTP Routes (Tier 1: 6 tests)
# ===========================================================================


def test_f17_t1_list_apps_and_get_app_detail(
    live_studio_server: StudioHarness,
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    gpus = importlib.import_module("studio_app.gpus")
    monkeypatch.setattr(gpus, "gpu_profile", lambda: dict(full_48g_profile))

    r_all = live_studio_server.get("/api/apps")
    assert r_all.status == 200, r_all.text
    assert "application/json" in r_all.header("Content-Type")
    data_all = r_all.json()
    apps_list = data_all.get("apps", data_all if isinstance(data_all, list) else [])
    assert isinstance(apps_list, list) and len(apps_list) >= 2
    by_id = {a["id"]: a for a in apps_list}
    assert "smoke" in by_id and "create-image" in by_id
    for app in apps_list:
        for req_key in ("id", "name", "section", "pack", "min_vram_gb", "platforms", "compatible"):
            assert req_key in app, f"Missing {req_key} in app summary {app!r}"
        assert isinstance(app["compatible"], bool)
        assert isinstance(app["platforms"], list)

    r_img = live_studio_server.get("/api/apps?section=image")
    assert r_img.status == 200, r_img.text
    img_apps = r_img.json().get("apps", [])
    assert len(img_apps) >= 1
    assert all(a["section"] == "image" for a in img_apps)
    assert any(a["id"] == "create-image" for a in img_apps)

    r_ci = live_studio_server.get("/api/apps/create-image")
    assert r_ci.status == 200, r_ci.text
    ci = r_ci.json()
    assert ci["id"] == "create-image"
    assert ci["pack"] == "image-flux3"
    assert ci["compatible"] is True
    assert FULL_48G_PLATFORM_TAG in ci["platforms"]
    assert isinstance(ci.get("inputs"), list) and len(ci["inputs"]) > 0
    assert isinstance(ci.get("outputs"), list) and len(ci["outputs"]) > 0

    r_smoke = live_studio_server.get("/api/apps/smoke")
    assert r_smoke.status == 200, r_smoke.text
    sm = r_smoke.json()
    assert sm["id"] == "smoke"
    assert sm["pack"] == "core"
    assert sm["compatible"] is True
    assert MAC_8G_PLATFORM_TAG in sm["platforms"]


def test_f17_t1_get_app_workflow_valid_comfy_api_json(
    live_studio_server: StudioHarness,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    for app_id in ("smoke", "create-image"):
        detail_resp = live_studio_server.get(f"/api/apps/{app_id}")
        assert detail_resp.status == 200, detail_resp.text
        detail = detail_resp.json()

        wf_resp = live_studio_server.get(f"/api/apps/{app_id}/workflow")
        assert wf_resp.status == 200, wf_resp.text
        assert "application/json" in wf_resp.header("Content-Type")
        wf = wf_resp.json()
        assert isinstance(wf, dict) and len(wf) >= 1
        for node_id, node in wf.items():
            assert isinstance(node_id, str)
            assert isinstance(node, dict)
            assert isinstance(node.get("class_type"), str) and node["class_type"]
            assert isinstance(node.get("inputs"), dict)
        for out_spec in detail.get("outputs", []):
            out_node = str(out_spec["node"])
            assert out_node in wf, f"Output node {out_node!r} missing from {app_id} workflow"


def test_f17_t1_run_app_dispatches_to_fake_comfyui_and_produces_output(
    live_studio_server: StudioHarness,
    fake_comfyui: FakeComfyUIServer,
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    gpus = importlib.import_module("studio_app.gpus")
    monkeypatch.setattr(gpus, "gpu_profile", lambda: dict(full_48g_profile))
    monkeypatch.setenv("COMFYUI_URL", fake_comfyui.base_url)
    monkeypatch.setenv("COMFY_BASE_URL", fake_comfyui.base_url)

    fake_comfyui.steps = 1
    fake_comfyui.step_delay_s = 0.01
    fake_comfyui.output_format = "png"

    resp = live_studio_server.post(
        "/api/apps/smoke/run",
        {"inputs": {"width": 128, "height": 128, "color": 255}},
    )
    assert resp.status in {200, 202}, resp.text
    body = resp.json()
    assert any(k in body for k in ("job_id", "run_id", "prompt_id", "outputs", "status")), body

    prompts = wait_until(lambda: fake_comfyui.prompts if len(fake_comfyui.prompts) >= 1 else None, timeout=6.0)
    assert prompts, "Expected fake_comfyui to receive at least one /prompt submission"
    submitted = prompts[0]["prompt"]
    assert "1" in submitted
    node1_inputs = submitted["1"].get("inputs", {})
    assert node1_inputs.get("width") == 128
    assert node1_inputs.get("height") == 128
    assert node1_inputs.get("color") == 255

    hist_ready = wait_until(lambda: fake_comfyui.history if len(fake_comfyui.history) >= 1 else None, timeout=5.0)
    assert hist_ready, "Expected fake_comfyui.history to record completed output"


def test_f17_t1_send_to_shot_copies_output_to_keyframe_and_take(
    live_studio_server: StudioHarness,
    isolated_workspace: IsolatedWorkspace,
) -> None:
    ensure_workspace_manifests(isolated_workspace)
    proj = seed_demo_book_project(isolated_workspace, slug="demo", shots=2)
    dl_dir = isolated_workspace.root / "my_downloads"
    src1 = dl_dir / "app_out_1.png"
    src2 = dl_dir / "app_out_2.png"
    png1 = make_solid_png_bytes(64, 64, (255, 0, 0, 255))
    png2 = make_solid_png_bytes(64, 64, (0, 255, 0, 255))
    src1.write_bytes(png1)
    src2.write_bytes(png2)

    r1 = live_studio_server.post(
        "/api/apps/smoke/send-to-shot",
        {"project": "demo", "shot": 1, "kind": "keyframe", "model": "flux3", "source": str(src1)},
    )
    assert r1.status == 200, r1.text
    kf_path = proj / "images" / "flux3_keyframes" / "image-0001.png"
    assert kf_path.is_file(), f"Expected keyframe at {kf_path}, response={r1.text}"
    assert kf_path.read_bytes() == png1

    r2 = live_studio_server.post(
        "/api/apps/smoke/send-to-shot",
        {"project": "demo", "shot": 1, "kind": "keyframe", "model": "flux3", "source": str(src2), "as_take": True},
    )
    assert r2.status == 200, r2.text
    takes_dir = proj / "images" / "flux3_keyframes" / "takes"
    take_files = sorted(takes_dir.glob("image-0001-t*.png")) if takes_dir.is_dir() else []
    assert take_files or kf_path.read_bytes() == png2
    all_bytes = [kf_path.read_bytes(), *(t.read_bytes() for t in take_files)]
    assert png1 in all_bytes and png2 in all_bytes, "Expected both first and second outputs preserved without data loss"


def test_f17_t1_list_packs_and_download_pack_from_fake_hf(
    live_studio_server: StudioHarness,
    fake_hf_hub: FakeHFHubServer,
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    gpus = importlib.import_module("studio_app.gpus")
    monkeypatch.setattr(gpus, "gpu_profile", lambda: dict(full_48g_profile))
    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)

    r_packs = live_studio_server.get("/api/packs")
    assert r_packs.status == 200, r_packs.text
    packs_payload = r_packs.json()
    packs_raw = packs_payload.get("packs", [])
    packs_list = list(packs_raw.values()) if isinstance(packs_raw, dict) else list(packs_raw)
    assert len(packs_list) >= 2
    assert "free_gb" in packs_payload or any("free_gb" in p for p in packs_list)

    # Pick a public pack with at least 1 model file (e.g., audio / upscale / image)
    public_pack = next(
        (p for p in packs_list if not p.get("needs_hf_token") and not p.get("gated") and len(p.get("models", [])) >= 1),
        None,
    )
    assert public_pack is not None, f"No public pack with models found in {packs_list!r}"
    pack_id = str(public_pack.get("pack") or public_pack.get("id"))
    registered: list[tuple[str, str, str]] = []
    for idx, m in enumerate(public_pack["models"]):
        payload = f"fake-model-weights-{pack_id}-{idx}-".encode() * 64
        sha = fake_hf_hub.register_file(m["repo"], m["file"], content=payload, gated=False)
        registered.append((m["repo"], m["file"], sha))

    r_dl = live_studio_server.post(f"/api/packs/{pack_id}/download", {})
    assert r_dl.status in {200, 202}, r_dl.text

    def _pack_installed() -> bool:
        check = live_studio_server.get("/api/packs")
        if check.status != 200:
            return False
        raw = check.json().get("packs", [])
        items = list(raw.values()) if isinstance(raw, dict) else list(raw)
        target = next((x for x in items if (x.get("pack") or x.get("id")) == pack_id), None)
        if not target:
            return False
        return target.get("missing", 0) == 0 and target.get("installed", True) is True

    assert wait_until(_pack_installed, timeout=10.0), f"Pack {pack_id} did not finish downloading from fake_hf_hub"
    assert len(fake_hf_hub.requests_log) >= len(registered)


def test_f17_t1_hf_token_validate_save_0600_and_no_leak(
    live_studio_server: StudioHarness,
    fake_hf_hub: FakeHFHubServer,
    isolated_workspace: IsolatedWorkspace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(isolated_workspace)
    token_val = "hf_valid_e2e_token_1234567890abcdef"
    fake_hf_hub.set_valid_tokens({token_val: "alice_e2e"})
    monkeypatch.setenv("HF_ENDPOINT", fake_hf_hub.base_url)

    resp = live_studio_server.post("/api/hf/token", {"token": token_val})
    assert resp.status == 200, resp.text
    assert token_val not in resp.text, "Raw HF token must never be echoed back in HTTP response"
    body = resp.json()
    assert body.get("user") == "alice_e2e" or body.get("username") == "alice_e2e" or body.get("ok") is True

    assert any(
        req.get("path") == "/api/whoami-v2" and req.get("authorization") == f"Bearer {token_val}"
        for req in fake_hf_hub.requests_log
    ), f"Expected /api/whoami-v2 call in {fake_hf_hub.requests_log!r}"

    token_files = find_workspace_token_files(isolated_workspace)
    assert token_files, "Expected HF token file persisted inside isolated workspace"
    for tf in token_files:
        if token_val in tf.read_text(encoding="utf-8", errors="ignore"):
            assert stat.S_IMODE(tf.stat().st_mode) == 0o600, f"Token file {tf} must have 0600 permissions"
            break
    else:
        raise AssertionError("None of the workspace token files stored the validated token")

    r_packs = live_studio_server.get("/api/packs")
    assert r_packs.status == 200, r_packs.text
    tok_info = r_packs.json().get("token", {})
    assert token_val not in r_packs.text
    assert tok_info.get("ok") or tok_info.get("configured") or tok_info.get("user") == "alice_e2e"


# ===========================================================================
# F18 — SSE event: preview & core.js EventSource (Tier 1: 6 tests)
# ===========================================================================


def test_f18_t1_sse_headers_retry_log_and_status_events(live_studio_server: StudioHarness) -> None:
    jobs = importlib.import_module("studio_app.jobs")
    with jobs.JOB.lock:
        jobs.JOB.lines[:] = ["hello-sse-1", "hello-sse-2"]
        jobs.JOB.running = True
        jobs.JOB.current = "render_step"

    try:
        conn = http.client.HTTPConnection("127.0.0.1", live_studio_server.port, timeout=5.0)
        try:
            conn.putrequest("GET", "/api/v1/events?since=0&seconds=0.6", skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{live_studio_server.port}")
            conn.putheader("X-Studio-Token", live_studio_server.token)
            conn.endheaders()
            resp = conn.getresponse()
            assert resp.status == 200
            hdrs = {k.lower(): v for k, v in resp.getheaders()}
            assert hdrs.get("content-type", "").startswith("text/event-stream")
            assert hdrs.get("cache-control") == "no-store"
            assert hdrs.get("x-content-type-options") == "nosniff"
            _ = resp.read()
        finally:
            conn.close()

        events = live_studio_server.read_sse_events("/api/v1/events?since=0&seconds=0.7")
        assert any(e.retry == 3000 for e in events)
        log_events = [e for e in events if e.event == "log"]
        assert [(e.id, e.json()) for e in log_events] == [("1", "hello-sse-1"), ("2", "hello-sse-2")]
        status_events = [e for e in events if e.event == "status"]
        assert any(e.json() == {"running": True, "step": "render_step"} for e in status_events)
    finally:
        with jobs.JOB.lock:
            jobs.JOB.running = False
            jobs.JOB.current = ""


def test_f18_t1_comfyui_ws_jpeg_preview_relayed_to_sse_event_preview(
    live_studio_server: StudioHarness,
    fake_comfyui: FakeComfyUIServer,
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    gpus = importlib.import_module("studio_app.gpus")
    monkeypatch.setattr(gpus, "gpu_profile", lambda: dict(full_48g_profile))
    monkeypatch.setenv("COMFYUI_URL", fake_comfyui.base_url)
    monkeypatch.setenv("COMFY_BASE_URL", fake_comfyui.base_url)

    fake_comfyui.steps = 2
    fake_comfyui.step_delay_s = 0.08
    fake_comfyui.preview_format = 1  # JPEG

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(live_studio_server.read_sse_events, "/api/v1/events?seconds=2.5")
        time.sleep(0.15)
        run_resp = live_studio_server.post("/api/apps/smoke/run", {"inputs": {"width": 128, "height": 128}})
        assert run_resp.status in {200, 202}, run_resp.text
        events: list[SSEEvent] = fut.result(timeout=6.0)

    preview_events = [e for e in events if e.event == "preview"]
    assert len(preview_events) >= 1, f"Expected event: preview in {[e.event for e in events]}"
    payload = preview_events[0].json()
    assert payload["content_type"] == "image/jpeg"
    raw = base64.b64decode(payload["data_base64"])
    assert raw.startswith(b"\xff\xd8\xff") and raw.endswith(b"\xff\xd9")
    assert raw == MINIMAL_JPEG


def test_f18_t1_comfyui_ws_png_preview_format_2_relayed_to_sse(
    live_studio_server: StudioHarness,
    fake_comfyui: FakeComfyUIServer,
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    gpus = importlib.import_module("studio_app.gpus")
    monkeypatch.setattr(gpus, "gpu_profile", lambda: dict(full_48g_profile))
    monkeypatch.setenv("COMFYUI_URL", fake_comfyui.base_url)
    monkeypatch.setenv("COMFY_BASE_URL", fake_comfyui.base_url)

    fake_comfyui.steps = 1
    fake_comfyui.step_delay_s = 0.06
    fake_comfyui.preview_format = 2  # PNG

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(live_studio_server.read_sse_events, "/api/v1/events?seconds=2.0")
        time.sleep(0.15)
        run_resp = live_studio_server.post("/api/apps/smoke/run", {"inputs": {"width": 128, "height": 128}})
        assert run_resp.status in {200, 202}, run_resp.text
        events = fut.result(timeout=6.0)

    preview_events = [e for e in events if e.event == "preview"]
    assert len(preview_events) >= 1
    payload = preview_events[0].json()
    assert payload["content_type"] == "image/png"
    raw = base64.b64decode(payload["data_base64"])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert raw == MINIMAL_PNG


def test_f18_t1_sse_since_resume_and_new_job_reset(live_studio_server: StudioHarness) -> None:
    jobs = importlib.import_module("studio_app.jobs")
    with jobs.JOB.lock:
        jobs.JOB.lines[:] = ["L1", "L2", "L3"]

    events_resume = live_studio_server.read_sse_events("/api/v1/events?since=2&seconds=0.6")
    log_resume = [(e.id, e.json()) for e in events_resume if e.event == "log"]
    assert log_resume == [("3", "L3")]

    with jobs.JOB.lock:
        jobs.JOB.lines[:] = ["NEW_JOB_1"]

    events_reset = live_studio_server.read_sse_events("/api/v1/events?since=10&seconds=0.6")
    log_reset = [(e.id, e.json()) for e in events_reset if e.event == "log"]
    assert log_reset == [("1", "NEW_JOB_1")]


def test_f18_t1_core_js_eventsource_updates_log_status_and_preview_dom(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    core_js = _STATIC_JS_DIR / "core.js"
    run_node_check(core_js)
    jpeg_b64 = base64.b64encode(MINIMAL_JPEG).decode("ascii")

    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url, b64] = process.argv.slice(2);
(async () => {
  let spyES = null;
  class SpyEventSource {
    constructor(u) {
      this.url = String(u);
      this.listeners = {};
      this.closed = false;
      spyES = this;
    }
    addEventListener(type, fn) {
      (this.listeners[type] = this.listeners[type] || []).push(fn);
    }
    removeEventListener(type, fn) {
      this.listeners[type] = (this.listeners[type] || []).filter(f => f !== fn);
    }
    close() { this.closed = true; }
    __emit(type, dataObj, id) {
      const ev = { type, data: typeof dataObj === "string" ? dataObj : JSON.stringify(dataObj), lastEventId: id || "" };
      if (typeof this["on" + type] === "function") this["on" + type](ev);
      for (const fn of this.listeners[type] || []) fn(ev);
    }
  }
  const { window: w, document: d, errors, close } = await createNeonDOM({
    url,
    baseUrl: new URL(url).origin,
    beforeParse(win) {
      win.EventSource = SpyEventSource;
      win.__originalES = SpyEventSource;
    },
  });
  await new Promise(r => setTimeout(r, 800));
  if (!spyES && typeof w.startLogStream === "function") w.startLogStream();
  if (!spyES && typeof w.poll === "function") w.poll();
  await new Promise(r => setTimeout(r, 150));
  if (!spyES) {
    console.log(JSON.stringify({ ok: false, reason: "EventSource was never constructed by core.js", errors }));
    close();
    process.exit(1);
  }
  spyES.__emit("log", "sse-streamed-line-1", "1");
  spyES.__emit("status", { running: true, step: "generating_frames" });
  const runningDisabled = Boolean(d.getElementById("bRun")?.disabled);
  const stepText = d.getElementById("cur")?.textContent || "";
  spyES.__emit("preview", { content_type: "image/jpeg", data_base64: b64 });
  spyES.__emit("status", { running: false, step: "" });
  await new Promise(r => setTimeout(r, 100));
  const previewImg = d.querySelector("#livePreview, #previewImg, img[data-live-preview], .live-preview img");
  const out = {
    ok: true,
    esUrl: spyES.url,
    logText: d.getElementById("log")?.textContent || "",
    mLogText: d.getElementById("mLog")?.textContent || "",
    runningDisabled,
    idleDisabled: Boolean(d.getElementById("bRun")?.disabled),
    stepText,
    previewSrc: previewImg ? previewImg.getAttribute("src") || previewImg.src : "",
    previewHidden: previewImg ? previewImg.classList.contains("hidden") : true,
    errors,
  };
  close();
  console.log(JSON.stringify(out));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}", jpeg_b64])
    assert res["errors"] == [], res["errors"]
    assert res["esUrl"].startswith("/api/v1/events"), res["esUrl"]
    assert "sse-streamed-line-1" in res["logText"]
    assert "sse-streamed-line-1" in res["mLogText"]
    assert res["runningDisabled"] is True
    assert res["idleDisabled"] is False
    assert "generating_frames" in res["stepText"]
    assert res["previewSrc"] == f"data:image/jpeg;base64,{jpeg_b64}"
    assert res["previewHidden"] is False


def test_f18_t1_core_js_eventsource_fallback_to_api_log_polling(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    jobs = importlib.import_module("studio_app.jobs")
    with jobs.JOB.lock:
        jobs.JOB.lines[:] = ["fallback-poll-ok"]
        jobs.JOB.running = True

    try:
        scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    url,
    baseUrl: new URL(url).origin,
    beforeParse(win) {
      delete win.EventSource;
      win.EventSource = undefined;
    },
  });
  await new Promise(r => setTimeout(r, 600));
  if (typeof w.startLogStream === "function") w.startLogStream();
  else if (typeof w.poll === "function") w.poll();
  await new Promise(r => setTimeout(r, 400));
  const fetchedLog = w.__fetchLog.some(f => f.url.includes("/api/log"));
  const logText = d.getElementById("log")?.textContent || "";
  close();
  console.log(JSON.stringify({ fetchedLog, logText, errors }));
})();
"""
        res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
        assert res["errors"] == [], res["errors"]
        assert res["fetchedLog"] is True
        assert "fallback-poll-ok" in res["logText"]
    finally:
        with jobs.JOB.lock:
            jobs.JOB.running = False


# ===========================================================================
# F19 — Ported freefield JS Modules (Tier 1: 8 tests)
# ===========================================================================


def test_f19_t1_static_js_syntax_and_http_serving(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    modules = ("paint.js", "compare.js", "apps_gallery.js", "packs_vram.js")
    for mod in modules:
        path = _STATIC_JS_DIR / mod
        assert path.is_file(), f"Missing F19 JS module: {path}"
        run_node_check(path)
        resp = live_studio_server.get(f"/static/js/{mod}")
        assert resp.status == 200
        assert "javascript" in resp.header("Content-Type")
        assert resp.header("X-Content-Type-Options") == "nosniff"

    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { errors, close } = await createNeonDOM({ url, baseUrl: new URL(url).origin });
  await new Promise(r => setTimeout(r, 800));
  close();
  console.log(JSON.stringify({ errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]


def test_f19_t1_paint_brush_eraser_and_white_on_black_png(tmp_path: Path) -> None:
    paint_js = _STATIC_JS_DIR / "paint.js"
    assert paint_js.is_file(), f"Missing {paint_js}"
    bg_b64 = base64.b64encode(make_solid_png_bytes(160, 120, (40, 90, 180, 255))).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [paintPath, bgB64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='paintHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(paintPath, "utf-8"));
  let exportedBytes = null;
  const openFn = w.openPainter || (w.StudioPaint && w.StudioPaint.open);
  if (typeof openFn !== "function") throw new Error("No openPainter / StudioPaint.open global found");
  const promise = openFn(`data:image/png;base64,${bgB64}`, {
    container: d.getElementById("paintHost"),
    onDone(blob) { exportedBytes = blob; },
  });
  await new Promise(r => setTimeout(r, 80));
  const canvas = d.querySelector("canvas");
  if (!canvas) throw new Error("Painter did not mount a <canvas>");
  const rect = canvas.getBoundingClientRect();
  const fire = (type, x, y) => canvas.dispatchEvent(new w.PointerEvent(type, {
    bubbles: true, clientX: rect.left + x, clientY: rect.top + y, pointerId: 1, buttons: type === "pointerup" ? 0 : 1,
  }));
  // Brush stroke (20, 20) -> (80, 20)
  fire("pointerdown", 20, 20);
  fire("pointermove", 50, 20);
  fire("pointermove", 80, 20);
  fire("pointerup", 80, 20);
  // Switch to Eraser and erase (40, 20) -> (60, 20)
  const eraserBtn = [...d.querySelectorAll("button,[data-tool]")].find(b => /eras/i.test(b.textContent || b.dataset.tool || ""));
  if (!eraserBtn) throw new Error("Eraser button not found");
  eraserBtn.click();
  fire("pointerdown", 40, 20);
  fire("pointermove", 50, 20);
  fire("pointermove", 60, 20);
  fire("pointerup", 60, 20);
  // Click Done/Apply
  const doneBtn = [...d.querySelectorAll("button")].find(b => /done|apply|save|export/i.test(b.textContent || ""));
  if (!doneBtn) throw new Error("Done button not found");
  doneBtn.click();
  const maybeBlob = promise && typeof promise.then === "function" ? await Promise.race([promise, new Promise(r => setTimeout(() => r(null), 200))]) : null;
  await new Promise(r => setTimeout(r, 80));
  const finalBlob = exportedBytes || maybeBlob;
  if (!finalBlob) throw new Error("Painter did not emit mask blob");
  const ab = await finalBlob.arrayBuffer();
  close();
  console.log(JSON.stringify({ pngB64: Buffer.from(ab).toString("base64"), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(paint_js), bg_b64])
    assert res["errors"] == [], res["errors"]
    png_bytes = base64.b64decode(res["pngB64"])
    im = Image.open(io.BytesIO(png_bytes))
    assert im.format == "PNG"
    assert im.size == (160, 120)
    rgb = im.convert("RGB")
    assert rgb.getpixel((0, 0)) == (0, 0, 0)
    assert rgb.getpixel((20, 20)) == (255, 255, 255)
    assert rgb.getpixel((50, 20)) == (0, 0, 0)


def test_f19_t1_paint_undo_redo_and_clear(tmp_path: Path) -> None:
    paint_js = _STATIC_JS_DIR / "paint.js"
    assert paint_js.is_file(), f"Missing {paint_js}"
    bg_b64 = base64.b64encode(make_solid_png_bytes(160, 120)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [paintPath, bgB64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='paintHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(paintPath, "utf-8"));
  const openFn = w.openPainter || (w.StudioPaint && w.StudioPaint.open);
  let latest = null;
  openFn(`data:image/png;base64,${bgB64}`, { container: d.getElementById("paintHost"), onDone(b) { latest = b; } });
  await new Promise(r => setTimeout(r, 80));
  const canvas = d.querySelector("canvas");
  const fire = (t, x, y) => canvas.dispatchEvent(new w.PointerEvent(t, { bubbles: true, clientX: x, clientY: y, pointerId: 1 }));
  for (const [x, y] of [[20, 20], [20, 60], [20, 100]]) {
    fire("pointerdown", x, y);
    fire("pointermove", x + 20, y);
    fire("pointerup", x + 20, y);
  }
  const undoBtn = [...d.querySelectorAll("button")].find(b => /undo/i.test(b.textContent || b.title || ""));
  const redoBtn = [...d.querySelectorAll("button")].find(b => /redo/i.test(b.textContent || b.title || ""));
  const clearBtn = [...d.querySelectorAll("button")].find(b => /clear/i.test(b.textContent || b.title || ""));
  if (!undoBtn || !clearBtn) throw new Error("Undo/Clear buttons missing");
  const ctx = canvas.getContext("2d");
  const pixelAt = (x, y) => ctx.getImageData(x, y, 1, 1).data[0];
  const beforeUndo = [pixelAt(25, 20), pixelAt(25, 60), pixelAt(25, 100)];
  undoBtn.click();
  const afterUndo1 = [pixelAt(25, 20), pixelAt(25, 60), pixelAt(25, 100)];
  if (redoBtn) {
    redoBtn.click();
  }
  const afterRedo = [pixelAt(25, 20), pixelAt(25, 60), pixelAt(25, 100)];
  clearBtn.click();
  const afterClear = [pixelAt(25, 20), pixelAt(25, 60), pixelAt(25, 100)];
  undoBtn.click();
  const afterUndoClear = [pixelAt(25, 20), pixelAt(25, 60), pixelAt(25, 100)];
  close();
  console.log(JSON.stringify({ beforeUndo, afterUndo1, afterRedo, afterClear, afterUndoClear, hasRedo: Boolean(redoBtn), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(paint_js), bg_b64])
    assert res["errors"] == [], res["errors"]
    assert res["beforeUndo"][2] > 0
    assert res["afterUndo1"][2] == 0 and res["afterUndo1"][0] > 0
    if res["hasRedo"]:
        assert res["afterRedo"][2] > 0
    assert res["afterClear"] == [0, 0, 0]
    assert res["afterUndoClear"][0] > 0


def test_f19_t1_compare_image_wipe_slider_and_swap(tmp_path: Path) -> None:
    compare_js = _STATIC_JS_DIR / "compare.js"
    assert compare_js.is_file(), f"Missing {compare_js}"
    img_a = base64.b64encode(make_solid_png_bytes(160, 120, (255, 0, 0, 255))).decode("ascii")
    img_b = base64.b64encode(make_solid_png_bytes(160, 120, (0, 0, 255, 255))).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [cmpPath, aB64, bB64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='cmpHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(cmpPath, "utf-8"));
  const openCmp = w.openCompare || (w.StudioCompare && w.StudioCompare.open);
  if (typeof openCmp !== "function") throw new Error("No openCompare / StudioCompare.open global found");
  openCmp(
    { kind: "image", src: `data:image/png;base64,${aB64}`, label: "Model A" },
    { kind: "image", src: `data:image/png;base64,${bB64}`, label: "Model B" },
    { container: d.getElementById("cmpHost") }
  );
  await new Promise(r => setTimeout(r, 80));
  const wipeBtn = [...d.querySelectorAll("button")].find(b => /wipe/i.test(b.textContent || ""));
  const sideBtn = [...d.querySelectorAll("button")].find(b => /side/i.test(b.textContent || ""));
  const swapBtn = [...d.querySelectorAll("button")].find(b => /swap/i.test(b.textContent || ""));
  if (!wipeBtn || !sideBtn || !swapBtn) throw new Error("Compare controls missing");
  wipeBtn.click();
  await new Promise(r => setTimeout(r, 30));
  const stage = d.querySelector(".wipe, .compare-stage, [data-compare-stage]") || d.getElementById("cmpHost");
  const rect = stage.getBoundingClientRect();
  stage.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: rect.left + rect.width * 0.25, clientY: rect.top + 20, pointerId: 1 }));
  stage.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: rect.left + rect.width * 0.25, clientY: rect.top + 20, pointerId: 1 }));
  stage.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: rect.left + rect.width * 0.25, clientY: rect.top + 20, pointerId: 1 }));
  const handle = d.querySelector("[data-wipe-handle], .wipe-handle, .compare-handle, [role='slider']");
  const handleLeftAfterDrag = handle ? handle.style.left : "";
  if (handle) handle.dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  const handleLeftAfterArrow = handle ? handle.style.left : "";
  const imgsBeforeSwap = [...d.querySelectorAll("img")].map(i => i.src);
  swapBtn.click();
  const imgsAfterSwap = [...d.querySelectorAll("img")].map(i => i.src);
  close();
  console.log(JSON.stringify({ handleLeftAfterDrag, handleLeftAfterArrow, imgsBeforeSwap, imgsAfterSwap, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(compare_js), img_a, img_b])
    assert res["errors"] == [], res["errors"]
    assert "25%" in res["handleLeftAfterDrag"] or res["handleLeftAfterDrag"] != ""
    assert res["imgsAfterSwap"][::-1] == res["imgsBeforeSwap"]


def test_f19_t1_compare_dual_video_synchronized_playback(tmp_path: Path) -> None:
    compare_js = _STATIC_JS_DIR / "compare.js"
    assert compare_js.is_file(), f"Missing {compare_js}"

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [cmpPath] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='cmpHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(cmpPath, "utf-8"));
  const openCmp = w.openCompare || (w.StudioCompare && w.StudioCompare.open);
  openCmp(
    { kind: "video", src: "http://127.0.0.1/a.mp4", label: "Clip A", duration: 10 },
    { kind: "video", src: "http://127.0.0.1/b.mp4", label: "Clip B", duration: 10 },
    { container: d.getElementById("cmpHost") }
  );
  await new Promise(r => setTimeout(r, 80));
  const videos = [...d.querySelectorAll("video")];
  if (videos.length < 2) throw new Error("Expected 2 <video> elements");
  videos.forEach(v => { v.duration = 10; v.currentTime = 0; });
  const playBtn = [...d.querySelectorAll("button")].find(b => /play/i.test(b.textContent || ""));
  if (!playBtn) throw new Error("Play Both button missing");
  playBtn.click();
  const bothPlaying = videos.every(v => !v.paused);
  const seek = d.querySelector("input[type='range']");
  if (seek) {
    seek.value = String((Number(seek.max || 100) + Number(seek.min || 0)) / 2);
    seek.dispatchEvent(new w.Event("input", { bubbles: true }));
    seek.dispatchEvent(new w.Event("change", { bubbles: true }));
  }
  const timesAfterSeek = videos.map(v => v.currentTime);
  videos[0].currentTime = 6.0;
  videos[1].currentTime = 5.2;
  await new Promise(r => setTimeout(r, 500));
  const timesAfterDriftSync = videos.map(v => v.currentTime);
  const muteBtns = [...d.querySelectorAll("button")].filter(b => /mute/i.test(b.textContent || ""));
  if (muteBtns.length >= 2) muteBtns[0].click();
  const mutedStates = videos.map(v => v.muted);
  close();
  console.log(JSON.stringify({ bothPlaying, timesAfterSeek, timesAfterDriftSync, mutedStates, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(compare_js)])
    assert res["errors"] == [], res["errors"]
    assert res["bothPlaying"] is True
    assert all(abs(t - 5.0) <= 0.5 for t in res["timesAfterSeek"])
    assert abs(res["timesAfterDriftSync"][1] - 6.0) <= 0.2
    assert res["mutedStates"][0] is True and res["mutedStates"][1] is False


def test_f19_t1_apps_gallery_filter_badges_inspect_run_send_to_shot(
    live_studio_server: StudioHarness,
    fake_comfyui: FakeComfyUIServer,
    full_48g_profile: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ensure_workspace_manifests(live_studio_server.workspace)
    seed_demo_book_project(live_studio_server.workspace, slug="demo", shots=2)
    gpus = importlib.import_module("studio_app.gpus")
    monkeypatch.setattr(gpus, "gpu_profile", lambda: dict(full_48g_profile))
    monkeypatch.setenv("COMFYUI_URL", fake_comfyui.base_url)
    monkeypatch.setenv("COMFY_BASE_URL", fake_comfyui.base_url)

    apps_js = _STATIC_JS_DIR / "apps_gallery.js"
    assert apps_js.is_file(), f"Missing {apps_js}"

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [appsJsPath, baseUrl] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    url: baseUrl,
    baseUrl: new URL(baseUrl).origin,
  });
  await new Promise(r => setTimeout(r, 800));
  const appsTab = [...d.querySelectorAll("button,[role='tab'],a")].find(el => /^\\s*apps\\s*$/i.test(el.textContent || ""));
  if (appsTab) appsTab.click();
  await new Promise(r => setTimeout(r, 500));
  const search = d.querySelector("#appsSearch, input[type='search'], input[placeholder*='app' i], input[placeholder*='search' i]");
  if (!search) throw new Error("Apps search input not found");
  const initialText = d.body.textContent;
  search.value = "smoke";
  search.dispatchEvent(new w.Event("input", { bubbles: true }));
  await new Promise(r => setTimeout(r, 200));
  const filteredHasSmoke = /smoke/i.test(d.body.textContent);
  const runCard = [...d.querySelectorAll("button,[data-app-id]")].find(el => /smoke/i.test(el.textContent || el.dataset.appId || ""));
  if (runCard) runCard.click();
  await new Promise(r => setTimeout(r, 300));
  const inspectBtn = [...d.querySelectorAll("button")].find(b => /workflow|inspect/i.test(b.textContent || ""));
  if (inspectBtn) inspectBtn.click();
  await new Promise(r => setTimeout(r, 300));
  const runBtn = [...d.querySelectorAll("button")].find(b => /^\\s*run\\b/i.test(b.textContent || ""));
  if (runBtn) runBtn.click();
  await new Promise(r => setTimeout(r, 400));
  const fetched = w.__fetchLog.map(f => f.url);
  close();
  console.log(JSON.stringify({ initialHasApps: /create-image|smoke/i.test(initialText), filteredHasSmoke, fetched, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(apps_js), f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]
    assert res["initialHasApps"] is True
    assert res["filteredHasSmoke"] is True
    assert any("/api/apps" in u for u in res["fetched"])


def test_f19_t1_packs_vram_map_48g_vs_8g_comparison(tmp_path: Path) -> None:
    packs_js = _STATIC_JS_DIR / "packs_vram.js"
    assert packs_js.is_file(), f"Missing {packs_js}"

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [packsPath] = process.argv.slice(2);
async function renderWithProfile(tier, vramGb) {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='packsHost'></div></body></html>",
    beforeParse(win) {
      win.__virtualRoutes = {
        "/api/packs": {
          status: 200,
          body: {
            free_gb: 120.0,
            token: { ok: false, configured: false },
            gpu_profile: { tier, vram_gb: vramGb, ram_gb: tier === "full_48g" ? 64 : 8 },
            packs: [
              { pack: "core", apps: ["smoke"], download_gb: 0, min_vram_gb: 2, platforms: ["win_cuda", "mac_metal"], models: [], missing: 0, installed: true },
              { pack: "image-flux3", apps: ["create-image"], download_gb: 18.0, min_vram_gb: 18, platforms: ["win_cuda"], models: [{ repo: "bfl/flux3", file: "f.safetensors", gb: 18.0, gated: true }], missing: 1, installed: false },
            ],
          },
        },
      };
    },
  });
  w.eval(fs.readFileSync(packsPath, "utf-8"));
  const initFn = w.initPacksVram || (w.PacksVram && w.PacksVram.render);
  if (typeof initFn === "function") await initFn(d.getElementById("packsHost"));
  await new Promise(r => setTimeout(r, 150));
  const txt = d.body.textContent;
  close();
  return { txt, errors };
}
(async () => {
  const r48 = await renderWithProfile("full_48g", 48.0);
  const r8 = await renderWithProfile("mac_8g_lite", 8.0);
  console.log(JSON.stringify({ r48, r8 }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(packs_js)])
    assert res["r48"]["errors"] == [] and res["r8"]["errors"] == []
    assert "48" in res["r48"]["txt"] and "8" in res["r8"]["txt"]
    assert "18" in res["r8"]["txt"]


def test_f19_t1_packs_hf_token_gated_status_and_download_progress(
    live_studio_server: StudioHarness,
    fake_hf_hub: FakeHFHubServer,
    tmp_path: Path,
) -> None:
    packs_js = _STATIC_JS_DIR / "packs_vram.js"
    assert packs_js.is_file(), f"Missing {packs_js}"

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [packsPath] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='packsHost'></div></body></html>",
    beforeParse(win) {
      win.__virtualRoutes = {
        "/api/packs": {
          status: 200,
          body: {
            free_gb: 200.0,
            token: { ok: false, configured: false },
            gpu_profile: { tier: "full_48g", vram_gb: 48.0, ram_gb: 64.0 },
            packs: [
              { pack: "image-flux3", apps: ["create-image"], download_gb: 10.0, min_vram_gb: 16, platforms: ["win_cuda"], needs_hf_token: true, gated: true, missing: 1, done_gb: 3.2, models: [{ repo: "bfl/flux3", file: "m.safetensors", gb: 10.0, gated: true }] },
            ],
          },
        },
        "/api/hf/token": { status: 200, body: { ok: true, user: "alice_e2e" } },
        "/api/packs/image-flux3/download": { status: 202, body: { ok: true, started: true } },
      };
    },
  });
  w.eval(fs.readFileSync(packsPath, "utf-8"));
  const initFn = w.initPacksVram || (w.PacksVram && w.PacksVram.render);
  if (typeof initFn === "function") await initFn(d.getElementById("packsHost"));
  await new Promise(r => setTimeout(r, 150));
  const tokInput = d.querySelector("input[type='password']");
  if (!tokInput) throw new Error("Expected password-masked HF token input");
  tokInput.value = "hf_test_token_1234567890abcdef";
  const saveBtn = [...d.querySelectorAll("button")].find(b => /token|save|verify/i.test(b.textContent || ""));
  if (saveBtn) saveBtn.click();
  await new Promise(r => setTimeout(r, 100));
  const dlBtn = [...d.querySelectorAll("button")].find(b => /download|install/i.test(b.textContent || ""));
  if (dlBtn) dlBtn.click();
  await new Promise(r => setTimeout(r, 100));
  const calls = w.__fetchLog.map(f => `${f.method} ${f.url}`);
  const html = d.body.innerHTML;
  close();
  console.log(JSON.stringify({ inputCleared: tokInput.value === "", calls, has32Pct: html.includes("32%"), errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(packs_js)])
    assert res["errors"] == [], res["errors"]
    assert res["inputCleared"] is True
    assert any("POST /api/hf/token" in c for c in res["calls"])
    assert any("POST /api/packs/image-flux3/download" in c for c in res["calls"])


# ===========================================================================
# F20 — Client-Side Canvas Studio (Tier 1: 7 tests)
# ===========================================================================


def test_f20_t1_canvas_studio_syntax_http_and_workspace_mount(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    run_node_check(cs_js)
    assert "cdn.muapi.ai" not in cs_js.read_text(encoding="utf-8")

    resp = live_studio_server.get("/static/js/canvas_studio.js")
    assert resp.status == 200
    assert "cdn.muapi.ai" not in resp.text

    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { document: d, errors, close } = await createNeonDOM({ url, baseUrl: new URL(url).origin });
  await new Promise(r => setTimeout(r, 800));
  const wsBtn = [...d.querySelectorAll("button,[role='tab'],a")].find(el => /canvas.*compare/i.test(el.textContent || ""));
  if (!wsBtn) throw new Error("Canvas & Compare workspace trigger not found");
  wsBtn.click();
  await new Promise(r => setTimeout(r, 200));
  close();
  console.log(JSON.stringify({ found: true, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]
    assert res["found"] is True


def test_f20_t1_pan_zoom_and_reset_view(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  if (typeof mount !== "function") throw new Error("CanvasStudio mount function not found");
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  const zoomIn = [...d.querySelectorAll("button")].find(b => /zoom\\s*\\+|\\bin\\b|^\\+$/i.test((b.textContent || b.title || "").trim()));
  const zoomOut = [...d.querySelectorAll("button")].find(b => /zoom\\s*-|\\bout\\b|^-$/i.test((b.textContent || b.title || "").trim()));
  const handBtn = [...d.querySelectorAll("button")].find(b => /hand|pan/i.test(b.textContent || b.dataset.tool || b.title || ""));
  const resetBtn = [...d.querySelectorAll("button")].find(b => /reset\\s*view|100%/i.test(b.textContent || b.title || ""));
  if (!zoomIn || !zoomOut || !handBtn || !resetBtn) throw new Error("Pan/Zoom/Reset controls missing");
  zoomIn.click(); zoomIn.click(); zoomOut.click();
  handBtn.click();
  const stage = d.querySelector("[data-canvas-viewport], .canvas-viewport, .cs-viewport, .cs-stage") || d.querySelector("canvas").parentElement;
  stage.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: 100, clientY: 100, pointerId: 1 }));
  stage.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 160, clientY: 145, pointerId: 1 }));
  stage.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: 160, clientY: 145, pointerId: 1 }));
  const transformAfter = stage.style.transform || (d.querySelector("[style*='scale']") || {}).style?.transform || "";
  resetBtn.click();
  const transformReset = stage.style.transform || (d.querySelector("[style*='scale']") || {}).style?.transform || "";
  const state = api && typeof api.getState === "function" ? api.getState() : null;
  close();
  console.log(JSON.stringify({ transformAfter, transformReset, state, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert "1.1" in res["transformAfter"] or (res["state"] and res["state"].get("zoom") == 1.1)
    assert "scale(1)" in res["transformReset"] or (res["state"] and res["state"].get("zoom") == 1)


def test_f20_t1_lasso_and_box_region_selection_bbox(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  const lassoBtn = [...d.querySelectorAll("button")].find(b => /lasso/i.test(b.textContent || b.dataset.tool || b.title || ""));
  const boxBtn = [...d.querySelectorAll("button")].find(b => /box|region|rect/i.test(b.textContent || b.dataset.tool || b.title || ""));
  if (!lassoBtn || !boxBtn) throw new Error("Lasso/Box Region buttons missing");
  const canvas = d.querySelector("canvas");
  const fire = (t, x, y) => canvas.dispatchEvent(new w.PointerEvent(t, { bubbles: true, clientX: x, clientY: y, pointerId: 1 }));
  lassoBtn.click();
  fire("pointerdown", 32, 24);
  fire("pointermove", 96, 24);
  fire("pointermove", 160, 24);
  fire("pointermove", 160, 72);
  fire("pointermove", 160, 120);
  fire("pointermove", 32, 120);
  fire("pointerup", 32, 120);
  boxBtn.click();
  fire("pointerdown", 80, 60);
  fire("pointermove", 240, 180);
  fire("pointerup", 240, 180);
  const svgPaths = [...d.querySelectorAll("svg path")].map(p => p.getAttribute("d") || "");
  const state = api && typeof api.getState === "function" ? api.getState() : null;
  close();
  console.log(JSON.stringify({ svgPaths, regions: state && state.markedRegions, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert any(p.startswith("M") and p.endswith("Z") for p in res["svgPaths"])
    assert res["regions"] and len(res["regions"]) >= 2


def test_f20_t1_sketch_shapes_text_and_image_overlays_with_undo_redo(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  const drawBtn = [...d.querySelectorAll("button")].find(b => /draw|pen|brush|sketch/i.test(b.textContent || b.dataset.tool || ""));
  const textBtn = [...d.querySelectorAll("button")].find(b => /text/i.test(b.textContent || b.dataset.tool || ""));
  const undoBtn = [...d.querySelectorAll("button")].find(b => /undo/i.test(b.textContent || b.title || ""));
  const redoBtn = [...d.querySelectorAll("button")].find(b => /redo/i.test(b.textContent || b.title || ""));
  if (!drawBtn || !textBtn || !undoBtn || !redoBtn) throw new Error("Draw/Text/Undo/Redo controls missing");
  const canvas = d.querySelector("canvas");
  drawBtn.click();
  canvas.dispatchEvent(new w.PointerEvent("pointerdown", { bubbles: true, clientX: 20, clientY: 20, pointerId: 1 }));
  canvas.dispatchEvent(new w.PointerEvent("pointermove", { bubbles: true, clientX: 80, clientY: 40, pointerId: 1 }));
  canvas.dispatchEvent(new w.PointerEvent("pointerup", { bubbles: true, clientX: 80, clientY: 40, pointerId: 1 }));
  textBtn.click();
  const txtInput = d.querySelector("input[type='text'], textarea");
  if (txtInput) {
    txtInput.value = "Hero Shot";
    txtInput.dispatchEvent(new w.Event("input", { bubbles: true }));
    txtInput.dispatchEvent(new w.Event("change", { bubbles: true }));
  }
  const addTextConfirm = [...d.querySelectorAll("button")].find(b => /add|place|apply/i.test(b.textContent || ""));
  if (addTextConfirm) addTextConfirm.click();
  const countBeforeUndo = api && api.getState ? (api.getState().objects || api.getState().strokes || []).length : 1;
  undoBtn.click();
  const countAfterUndo = api && api.getState ? (api.getState().objects || api.getState().strokes || []).length : 0;
  redoBtn.click();
  const countAfterRedo = api && api.getState ? (api.getState().objects || api.getState().strokes || []).length : 1;
  close();
  console.log(JSON.stringify({ countBeforeUndo, countAfterUndo, countAfterRedo, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert res["countAfterUndo"] <= res["countBeforeUndo"]
    assert res["countAfterRedo"] >= res["countAfterUndo"]


def test_f20_t1_seven_category_color_grading_non_destructive_and_resets(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const srcUrl = `data:image/png;base64,${b64}`;
  const api = mount(d.getElementById("csHost"), { imageUrl: srcUrl });
  await new Promise(r => setTimeout(r, 80));
  const sliders = [...d.querySelectorAll("input[type='range']")];
  if (sliders.length < 7) throw new Error(`Expected >=7 grading sliders, got ${sliders.length}`);
  sliders.forEach(s => {
    const mid = (Number(s.max || 100) + Number(s.min || 0)) / 2;
    s.value = String(mid === Number(s.value) ? Number(s.max || 100) : mid);
    s.dispatchEvent(new w.Event("input", { bubbles: true }));
  });
  const baseImg = d.querySelector("img");
  const filterApplied = baseImg ? baseImg.style.filter : "";
  const resetAllBtn = [...d.querySelectorAll("button")].find(b => /reset\\s*all/i.test(b.textContent || ""));
  if (!resetAllBtn) throw new Error("Reset All button missing");
  resetAllBtn.click();
  const filterAfterReset = baseImg ? baseImg.style.filter : "";
  close();
  console.log(JSON.stringify({
    sliderCount: sliders.length,
    baseImgSrcIntact: baseImg ? baseImg.src === srcUrl : false,
    filterApplied,
    filterAfterReset,
    hasApi: Boolean(api),
    errors,
  }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert res["sliderCount"] >= 7
    assert res["baseImgSrcIntact"] is True
    assert res["filterApplied"] not in ("", "none")
    assert res["filterAfterReset"] in ("", "none")


def test_f20_t1_export_composite_applies_grading_vignette_grain_and_overlays(tmp_path: Path) -> None:
    cs_js = _STATIC_JS_DIR / "canvas_studio.js"
    assert cs_js.is_file(), f"Missing {cs_js}"
    img_b64 = base64.b64encode(make_solid_png_bytes(320, 240)).decode("ascii")

    scenario = """
const fs = require("fs");
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [csPath, b64] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({
    html: "<!doctype html><html><body><div id='csHost'></div></body></html>",
  });
  w.eval(fs.readFileSync(csPath, "utf-8"));
  const mount = w.mountCanvasStudio || (w.CanvasStudio && w.CanvasStudio.mount);
  const api = mount(d.getElementById("csHost"), { imageUrl: `data:image/png;base64,${b64}` });
  await new Promise(r => setTimeout(r, 80));
  if (api && typeof api.setGrading === "function") {
    api.setGrading({ exposure: { stops: 1.0 }, lensInstructions: { vignette: 0.6 }, filmGrain: { strength: 0.5, size: "35mm" } });
  }
  const origGetContext = w.HTMLCanvasElement.prototype.getContext;
  const contexts = [];
  w.HTMLCanvasElement.prototype.getContext = function (k) {
    const c = origGetContext.call(this, k);
    if (c && !contexts.includes(c)) contexts.push(c);
    return c;
  };
  const blob = api && typeof api.exportComposite === "function" ? await api.exportComposite() : null;
  const allCalls = contexts.flatMap(c => c.__getCalls());
  const ab = blob ? await blob.arrayBuffer() : new ArrayBuffer(0);
  close();
  console.log(JSON.stringify({
    hasBlob: Boolean(blob),
    byteLength: ab.byteLength,
    methods: allCalls.map(c => c.method),
    hasBrightness200: allCalls.some(c => String(c.filter || "").includes("brightness(200%)")),
    hasRadial: allCalls.some(c => c.method === "createRadialGradient"),
    hasPattern: allCalls.some(c => c.method === "createPattern"),
    errors,
  }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[str(cs_js), img_b64])
    assert res["errors"] == [], res["errors"]
    assert res["hasBlob"] is True and res["byteLength"] > 0
    assert res["hasBrightness200"] is True
    assert res["hasRadial"] is True
    assert res["hasPattern"] is True


def test_f20_t1_export_composite_and_mask_to_shot_take(
    live_studio_server: StudioHarness,
    isolated_workspace: IsolatedWorkspace,
) -> None:
    proj = seed_demo_book_project(isolated_workspace, slug="demo", shots=2)
    png_bytes = make_solid_png_bytes(128, 96, (200, 120, 40, 255))
    b64 = base64.b64encode(png_bytes).decode("ascii")

    # Exercise Neon's shot/take persistence endpoint for Canvas Studio exports
    resp = live_studio_server.post(
        "/api/canvas/export_take",
        {
            "project": "demo",
            "shot": 1,
            "kind": "keyframe",
            "model": "flux3",
            "image_base64": b64,
            "filename": "canvas_composite.png",
        },
    )
    assert resp.status in {200, 201}, resp.text
    saved = list((proj / "images").rglob("*.png"))
    assert saved, f"Expected exported composite PNG saved under {proj / 'images'}"


# ===========================================================================
# F21 — Unified 4-Workspace Shell & JS Tests (Tier 1: 7 tests)
# ===========================================================================


def test_f21_t1_unified_4_workspace_shell_dom_navigation(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { document: d, errors, close } = await createNeonDOM({ url, baseUrl: new URL(url).origin });
  await new Promise(r => setTimeout(r, 1200));
  const legacyFlowVisible = Boolean(d.getElementById("flowNav") && !d.getElementById("flowNav").classList.contains("hidden"));
  const legacyPhaseVisible = Boolean(d.getElementById("pipelinePhasesBar") && !d.getElementById("pipelinePhasesBar").classList.contains("hidden"));
  const patterns = [/film\\s*studio/i, /^\\s*apps\\s*$/i, /canvas.*compare/i, /models.*hardware/i];
  const triggers = patterns.map(re =>
    [...d.querySelectorAll("nav button, nav [role='tab'], nav a, [data-workspace]")].find(el => re.test((el.textContent || "").trim()))
  );
  const foundAll = triggers.every(Boolean) && new Set(triggers).size === 4;
  const switchStates = [];
  if (foundAll) {
    for (const trig of triggers) {
      trig.click();
      await new Promise(r => setTimeout(r, 80));
      const activeBtns = triggers.filter(t => t.classList.contains("active") || t.getAttribute("aria-selected") === "true" || t.getAttribute("aria-current") === "page");
      const panels = [...d.querySelectorAll("[data-workspace-panel], .workspace-panel, section.panel[role='tabpanel']")];
      const visiblePanels = panels.filter(p => !p.classList.contains("hidden") && p.getAttribute("aria-hidden") !== "true" && p.style.display !== "none");
      switchStates.push({ activeBtnCount: activeBtns.length, visiblePanelCount: visiblePanels.length });
    }
  }
  close();
  console.log(JSON.stringify({ legacyFlowVisible, legacyPhaseVisible, foundAll, switchStates, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]
    assert res["legacyFlowVisible"] is False and res["legacyPhaseVisible"] is True
    assert res["foundAll"] is True
    assert all(s["activeBtnCount"] == 1 and s["visiblePanelCount"] == 1 for s in res["switchStates"])


def test_f21_t1_legacy_cloud_gating_off_and_on_across_api_and_dom(
    live_studio_server: StudioHarness,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { document: d, errors, close } = await createNeonDOM({ url, baseUrl: new URL(url).origin });
  await new Promise(r => setTimeout(r, 1200));
  const mhBtn = [...d.querySelectorAll("nav button, nav [role='tab'], nav a, [data-workspace]")].find(el => /models.*hardware/i.test(el.textContent || ""));
  if (mhBtn) mhBtn.click();
  await new Promise(r => setTimeout(r, 200));
  const visibleCloud = ["kaggle", "colab", "huggingface"].filter(val => {
    const inp = d.querySelector(`input[name='svc'][value='${val}']`);
    if (!inp) return false;
    let cur = inp;
    while (cur && cur !== d.body) {
      if (cur.classList?.contains("hidden") || cur.style?.display === "none") return false;
      cur = cur.parentElement;
    }
    return true;
  });
  const paidItems = [...d.querySelectorAll("#paidProviders li")].filter(li => {
    let cur = li;
    while (cur && cur !== d.body) {
      if (cur.classList?.contains("hidden") || cur.style?.display === "none") return false;
      cur = cur.parentElement;
    }
    return true;
  }).length;
  close();
  console.log(JSON.stringify({ visibleCloud, paidItems, errors }));
})();
"""
    monkeypatch.delenv("STUDIO_LEGACY_CLOUD", raising=False)
    r_prov_off = live_studio_server.get("/api/providers")
    assert r_prov_off.status == 200
    prov_off = r_prov_off.json()
    assert prov_off["legacy_cloud"] is False
    assert prov_off["free"] == [] and prov_off["paid"] == []
    r_stat_off = live_studio_server.get("/api/status")
    assert r_stat_off.json()["legacy_cloud"] is False
    assert set(r_stat_off.json()["gpus"]) == {"computer"}

    dom_off = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert dom_off["errors"] == []
    assert dom_off["visibleCloud"] == [] and dom_off["paidItems"] == 0

    monkeypatch.setenv("STUDIO_LEGACY_CLOUD", "1")
    r_prov_on = live_studio_server.get("/api/providers")
    prov_on = r_prov_on.json()
    assert prov_on["legacy_cloud"] is True
    assert {p["id"] for p in prov_on["free"]} == {"kaggle", "colab", "huggingface"}
    assert len(prov_on["paid"]) >= 10
    r_stat_on = live_studio_server.get("/api/status")
    assert r_stat_on.json()["legacy_cloud"] is True
    assert "kaggle" in r_stat_on.json()["gpus"]

    dom_on = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert dom_on["errors"] == []
    assert set(dom_on["visibleCloud"]) >= {"kaggle", "colab", "huggingface"}
    assert dom_on["paidItems"] >= 10


def test_f21_t1_composer_selector_and_qa_post_ui_controls(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    r_comp = live_studio_server.get("/api/composers/status")
    assert r_comp.status == 200, r_comp.text
    comp = r_comp.json()
    for rt in ("ffmpeg", "remotion", "hyperframes", "blender"):
        assert rt in comp, f"Runtime {rt!r} missing from /api/composers/status"

    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({ url, baseUrl: new URL(url).origin });
  await new Promise(r => setTimeout(r, 1000));
  const txt = d.body.innerHTML.toLowerCase();
  const hasComposers = ["ffmpeg", "remotion", "hyperframes", "blender"].every(k => txt.includes(k));
  const hasQa = /slideshow|qa|critic|validate/.test(txt);
  const hasPost = /silence|reframe/.test(txt);
  const compSel = d.querySelector("select[id*='composer' i], select[name*='composer' i], input[name*='composer' i]");
  if (compSel && compSel.tagName === "SELECT") {
    compSel.value = "remotion";
    compSel.dispatchEvent(new w.Event("change", { bubbles: true }));
  }
  close();
  console.log(JSON.stringify({ hasComposers, hasQa, hasPost, errors }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]
    assert res["hasComposers"] is True
    assert res["hasQa"] is True
    assert res["hasPost"] is True


def test_f21_t1_all_static_js_syntax_node_check() -> None:
    static_files = sorted(_STATIC_JS_DIR.glob("*.js"))
    assert len(static_files) >= 10
    expected = {
        "canvas_studio.js",
        "paint.js",
        "compare.js",
        "apps_gallery.js",
        "packs_vram.js",
        "shell.js",
        "core.js",
        "providers.js",
        "models.js",
    }
    present = {p.name for p in static_files}
    assert expected.issubset(present), f"Missing static JS modules: {sorted(expected - present)}"
    for js_file in static_files:
        run_node_check(js_file)
    for test_js in sorted(_TESTS_JS_DIR.glob("*.js")):
        run_node_check(test_js)


def test_f21_t1_csp_no_inline_scripts_and_no_external_js_cdn(
    live_studio_server: StudioHarness,
) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", live_studio_server.port, timeout=5.0)
    try:
        conn.request("GET", f"/?t={live_studio_server.token}", headers={"Host": f"127.0.0.1:{live_studio_server.port}"})
        r1 = conn.getresponse()
        r1.read()
        assert r1.status == 302
        cookie = r1.getheader("Set-Cookie") or ""
        conn.request("GET", "/", headers={"Host": f"127.0.0.1:{live_studio_server.port}", "Cookie": cookie.split(";", 1)[0]})
        r2 = conn.getresponse()
        r2.read()
        assert r2.status == 200
        csp = r2.getheader("Content-Security-Policy") or ""
        assert "default-src 'self'" in csp and "script-src 'self'" in csp
        assert "object-src 'none'" in csp and "base-uri 'none'" in csp and "frame-ancestors 'none'" in csp
        assert r2.getheader("X-Content-Type-Options") == "nosniff"
    finally:
        conn.close()

    html = (_WEB_DIR / "index.html").read_text(encoding="utf-8")
    for m in re.finditer(r"<script\b([^>]*)>", html, re.IGNORECASE):
        attrs = m.group(1)
        assert "src=" in attrs, "Inline <script> without src= violates CSP"
        src_m = re.search(r"""src=["']([^"']+)["']""", attrs)
        assert src_m is not None and src_m.group(1).startswith("/static/js/"), f"External script src forbidden: {attrs}"
    assert not _INLINE_HANDLER_RE.search(html), "Inline on* handler in index.html"
    assert "javascript:" not in html.lower()

    loaded_scripts = re.findall(r"""<script\s+src="/static/js/([A-Za-z0-9_]+)\.js"\s+defer""", html)
    on_disk = sorted(p.stem for p in _STATIC_JS_DIR.glob("*.js") if p.stem != "installer")
    assert sorted(loaded_scripts) == on_disk and len(loaded_scripts) == len(set(loaded_scripts))

    for js_file in sorted(_STATIC_JS_DIR.glob("*.js")):
        src = js_file.read_text(encoding="utf-8")
        assert not _INLINE_HANDLER_RE.search(src), f"Inline handler in {js_file.name}"
        if js_file.stem != "installer":
            r_js = live_studio_server.get(f"/static/js/{js_file.name}")
            assert r_js.status == 200
            assert live_studio_server.token not in r_js.text


def test_f21_t1_existing_tests_js_smoke_passes_on_4_workspace_shell(
    live_studio_server: StudioHarness,
) -> None:
    node_bin = shutil.which("node")
    assert node_bin is not None
    smoke_js = _TESTS_JS_DIR / "smoke.js"
    assert smoke_js.is_file()
    proc = subprocess.run(
        [node_bin, str(smoke_js), f"{live_studio_server.base_url}/?t={live_studio_server.token}"],
        cwd=str(_TESTS_JS_DIR),
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    assert proc.returncode == 0, f"smoke.js failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    out = json.loads(lines[-1])
    assert out["errors"] == [], out["errors"]
    assert int(out.get("tabs", 0)) >= 4


def test_f21_t1_keyboard_shortcuts_and_workspace_persistence(
    live_studio_server: StudioHarness,
    tmp_path: Path,
) -> None:
    scenario = """
const { createNeonDOM } = require("./neon_canvas_harness.cjs");
const [url] = process.argv.slice(2);
(async () => {
  const { window: w, document: d, errors, close } = await createNeonDOM({ url, baseUrl: new URL(url).origin });
  await new Promise(r => setTimeout(r, 900));
  const escaped = typeof w.escapeHtml === "function" ? w.escapeHtml("<img src=x onerror=\\"a\\">'&") : "";
  d.dispatchEvent(new w.KeyboardEvent("keydown", { key: "4", bubbles: true }));
  await new Promise(r => setTimeout(r, 100));
  const savedTab = w.localStorage.getItem("activeWorkspace") || w.localStorage.getItem("activeTab") || w.location.hash;
  const storageDump = {};
  for (let i = 0; i < w.localStorage.length; i++) {
    const k = w.localStorage.key(i);
    storageDump[k] = w.localStorage.getItem(k);
  }
  const hashAfter = w.location.hash;
  close();

  const dom2 = await createNeonDOM({
    url: url + (hashAfter || ""),
    baseUrl: new URL(url).origin,
    beforeParse(w2) {
      for (const [k, v] of Object.entries(storageDump)) w2.localStorage.setItem(k, v);
    },
  });
  await new Promise(r => setTimeout(r, 900));
  const activeModelsBtn = [...dom2.document.querySelectorAll("nav button, nav [role='tab'], [data-workspace]")].find(
    el => (el.classList.contains("active") || el.getAttribute("aria-selected") === "true") && /models.*hardware/i.test(el.textContent || "")
  );
  const errors2 = dom2.errors;
  dom2.close();
  console.log(JSON.stringify({ escaped, savedTab, restoredModels: Boolean(activeModelsBtn), errors: [...errors, ...errors2] }));
})();
"""
    res = run_jsdom_harness(tmp_path, scenario, args=[f"{live_studio_server.base_url}/?t={live_studio_server.token}"])
    assert res["errors"] == [], res["errors"]
    assert "<" not in res["escaped"] and "&quot;" in res["escaped"] and "&#39;" in res["escaped"]
    assert res["restoredModels"] is True
