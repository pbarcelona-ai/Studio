"""Loopback fake Hugging Face Hub HTTP server for E2E tests."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, unquote, urlparse

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


@dataclass
class _FileEntry:
    repo: str
    filename: str
    revision: str
    content: bytes
    sha256: str
    commit: str
    status: int | None
    gated: bool
    required_token: str | None
    allowed_tokens: set[str] | None
    redirect_to_cdn: bool


def _parse_range(header_val: str, total_len: int) -> tuple[int, int] | None:
    m = _RANGE_RE.match(header_val.strip())
    if not m or total_len <= 0:
        return None
    start_s, end_s = m.group(1), m.group(2)
    if not start_s and not end_s:
        return None
    if not start_s:
        suffix = int(end_s)
        if suffix <= 0:
            return None
        start = max(0, total_len - suffix)
        end = total_len - 1
        return start, end
    start = int(start_s)
    end = int(end_s) if end_s else total_len - 1
    if start >= total_len or end < start:
        return None
    end = min(end, total_len - 1)
    return start, end


class _HFHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128

    def __init__(self, server_address: tuple[str, int], fake: FakeHFHubServer) -> None:
        self.fake = fake
        super().__init__(server_address, _HFHandler)


class _HFHandler(BaseHTTPRequestHandler):
    server: _HFHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_response(
        self,
        status: int,
        headers: dict[str, str],
        body: bytes = b"",
    ) -> None:
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _send_json(self, status: int, obj: Any, extra_headers: dict[str, str] | None = None) -> None:
        payload = json.dumps(obj).encode("utf-8")
        hdrs = {
            "Content-Type": "application/json",
            "Content-Length": str(len(payload)),
        }
        if extra_headers:
            hdrs.update(extra_headers)
        self._send_response(status, hdrs, payload)

    def _handle_read(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        hdrs_raw = dict(self.headers)
        auth = self.headers.get("Authorization", "")
        fake = self.server.fake
        fake.record_request(method, path, hdrs_raw, auth)

        if path == "/api/whoami-v2":
            status, json_body = fake.handle_whoami(auth)
            self._send_json(status, json_body)
            return

        if path.startswith("/api/models/"):
            status, json_body, extra = fake.handle_model_info(path, auth)
            self._send_json(status, json_body, extra)
            return

        if path.startswith("/cdn/"):
            status, resp_hdrs, raw_body = fake.handle_cdn(path, hdrs_raw)
            self._send_response(status, resp_hdrs, raw_body)
            return

        if "/resolve/" in path:
            status, resp_hdrs, raw_body = fake.handle_resolve(path, hdrs_raw, auth)
            self._send_response(status, resp_hdrs, raw_body)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"not found: {path}"})

    def do_HEAD(self) -> None:
        self._handle_read("HEAD")

    def do_GET(self) -> None:
        self._handle_read("GET")


class FakeHFHubServer:
    """Thread-safe loopback Hugging Face Hub server for E2E tests."""

    def __init__(
        self,
        *,
        valid_tokens: dict[str, str] | set[str] | None = None,
        reject_invalid_tokens_on_public: bool = False,
    ) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, str] = {}
        self._files: dict[tuple[str, str, str], _FileEntry] = {}
        self._default_reject_invalid_tokens_on_public = bool(reject_invalid_tokens_on_public)
        self._reject_invalid_tokens_on_public = bool(reject_invalid_tokens_on_public)
        self.requests_log: list[dict[str, Any]] = []
        if valid_tokens is not None:
            self.set_valid_tokens(valid_tokens)
        else:
            self._tokens["hf_test_valid"] = "test-user"

        self._httpd = _HFHTTPServer(("127.0.0.1", 0), self)
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> int:
        return int(self._httpd.server_port)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> FakeHFHubServer:
        if self._thread is None:
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._thread.start()
        return self

    def close(self) -> None:
        if self._thread is not None:
            self._httpd.shutdown()
            self._thread.join(timeout=2.0)
            self._thread = None
        self._httpd.server_close()

    def __enter__(self) -> FakeHFHubServer:
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def reset(self) -> None:
        """Clear registered files/logs and restore default tokens and constructor auth policy."""
        with self._lock:
            self._files.clear()
            self.requests_log.clear()
            self._tokens = {"hf_test_valid": "test-user"}
            self._reject_invalid_tokens_on_public = self._default_reject_invalid_tokens_on_public

    def set_valid_tokens(self, tokens: dict[str, str] | set[str]) -> None:
        with self._lock:
            if isinstance(tokens, dict):
                self._tokens = dict(tokens)
            else:
                self._tokens = {t: f"user-{idx}" for idx, t in enumerate(sorted(tokens), 1)}

    def set_reject_invalid_tokens_on_public(self, enabled: bool) -> None:
        with self._lock:
            self._reject_invalid_tokens_on_public = bool(enabled)

    def register_file(
        self,
        repo: str,
        filename: str,
        content: bytes = b"fake-model-weights",
        *,
        status: int | None = None,
        gated: bool = False,
        required_token: str | None = None,
        allowed_tokens: set[str] | None = None,
        redirect_to_cdn: bool = True,
        revision: str = "main",
        commit: str | None = None,
    ) -> str:
        digest = hashlib.sha256(content).hexdigest()
        commit_sha = commit or hashlib.sha1(f"{repo}@{revision}".encode()).hexdigest()
        entry = _FileEntry(
            repo=repo.strip("/"),
            filename=filename.lstrip("/"),
            revision=revision.strip("/"),
            content=content,
            sha256=digest,
            commit=commit_sha,
            status=status,
            gated=gated,
            required_token=required_token,
            allowed_tokens=set(allowed_tokens) if allowed_tokens is not None else None,
            redirect_to_cdn=redirect_to_cdn,
        )
        with self._lock:
            self._files[(entry.repo, entry.revision, entry.filename)] = entry
        return digest

    def sha256_of(self, repo: str, filename: str, revision: str = "main") -> str:
        key = (repo.strip("/"), revision.strip("/"), filename.lstrip("/"))
        with self._lock:
            entry = self._files.get(key)
            if entry is None:
                raise KeyError(f"file not registered: {repo}@{revision}/{filename}")
            return entry.sha256

    def record_request(self, method: str, path: str, headers: dict[str, str], authorization: str) -> None:
        lower_headers = {k.lower(): v for k, v in headers.items()}
        with self._lock:
            self.requests_log.append({
                "method": method,
                "path": path,
                "headers": headers,
                "headers_lower": lower_headers,
                "authorization": authorization,
            })

    @staticmethod
    def _extract_bearer(auth: str) -> str:
        parts = auth.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return ""

    def handle_whoami(self, auth: str) -> tuple[int, dict[str, Any]]:
        token = self._extract_bearer(auth)
        with self._lock:
            username = self._tokens.get(token)
        if not username:
            return HTTPStatus.UNAUTHORIZED, {"error": "Invalid credentials in Authorization header"}
        return HTTPStatus.OK, {"name": username, "type": "user"}

    def handle_model_info(self, path: str, auth: str) -> tuple[int, dict[str, Any], dict[str, str]]:
        rest = path.removeprefix("/api/models/").strip("/")
        revision = "main"
        if "/revision/" in rest:
            repo_part, rev_part = rest.split("/revision/", 1)
            repo = unquote(repo_part).strip("/")
            revision = unquote(rev_part).strip("/") or "main"
        else:
            repo = unquote(rest).strip("/")

        token = self._extract_bearer(auth)
        with self._lock:
            entries = [e for (r, rev, _), e in self._files.items() if r == repo and rev == revision]
            valid_user = bool(token and token in self._tokens)
            reject_public = self._reject_invalid_tokens_on_public

        if not entries:
            return HTTPStatus.NOT_FOUND, {"error": "Repository not found"}, {"X-Error-Code": "RepositoryNotFound"}

        gated = any(e.gated for e in entries)
        if gated and not valid_user:
            return HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"}, {"X-Error-Code": "Unauthorized"}

        for entry in entries:
            denied = self._token_allowed(entry, token, valid_user, reject_invalid_on_public=reject_public)
            if denied is not None:
                status_code, err_code = denied
                msg = "Access to gated repo restricted" if status_code == HTTPStatus.FORBIDDEN else err_code
                return status_code, {"error": msg}, {"X-Error-Code": err_code}

        siblings = [{"rfilename": e.filename, "size": len(e.content)} for e in entries]
        return (
            HTTPStatus.OK,
            {
                "id": repo,
                "sha": entries[0].commit,
                "gated": "manual" if gated else False,
                "siblings": siblings,
            },
            {},
        )

    @staticmethod
    def _token_allowed(
        entry: _FileEntry,
        token: str,
        valid_user: bool,
        *,
        reject_invalid_on_public: bool = False,
    ) -> tuple[int, str] | None:
        if entry.status is not None and entry.status >= 400:
            code = "GatedRepo" if entry.status == 403 else ("EntryNotFound" if entry.status == 404 else "Unauthorized")
            return entry.status, code

        if entry.gated:
            if not token or not valid_user:
                return HTTPStatus.UNAUTHORIZED, "Unauthorized"
            if entry.required_token is not None:
                if token != entry.required_token:
                    return HTTPStatus.FORBIDDEN, "GatedRepo"
                return None
            if entry.allowed_tokens is not None:
                if token not in entry.allowed_tokens:
                    return HTTPStatus.FORBIDDEN, "GatedRepo"
                return None
            return HTTPStatus.FORBIDDEN, "GatedRepo"

        if reject_invalid_on_public and token and not valid_user:
            return HTTPStatus.UNAUTHORIZED, "Unauthorized"
        if entry.required_token is not None and token != entry.required_token:
            return HTTPStatus.UNAUTHORIZED, "Unauthorized"
        if entry.allowed_tokens is not None and token not in entry.allowed_tokens:
            return HTTPStatus.UNAUTHORIZED, "Unauthorized"
        return None

    def handle_resolve(
        self,
        path: str,
        headers: dict[str, str],
        auth: str,
    ) -> tuple[int, dict[str, str], bytes]:
        # Format: /<repo>/resolve/<rev>/<filepath...> (supports single-segment repos and slash revisions)
        repo_part, rest = path.lstrip("/").split("/resolve/", 1)
        repo = unquote(repo_part).strip("/")
        token = self._extract_bearer(auth)
        rest_decoded = unquote(rest)

        with self._lock:
            valid_user = bool(token and token in self._tokens)
            reject_public = self._reject_invalid_tokens_on_public
            entry: _FileEntry | None = None
            for (r, rev, fname), candidate in self._files.items():
                if r == repo and rest_decoded == f"{rev}/{fname}":
                    entry = candidate
                    break
            if entry is None and "/" in rest:
                rev_part, file_part = rest.split("/", 1)
                revision = unquote(rev_part).strip("/") or "main"
                filename = unquote(file_part).lstrip("/")
                entry = self._files.get((repo, revision, filename))

        if entry is None:
            msg = json.dumps({"error": "Entry not found"}).encode("utf-8")
            return (
                HTTPStatus.NOT_FOUND,
                {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(msg)),
                    "X-Error-Code": "EntryNotFound",
                },
                msg,
            )

        denied = self._token_allowed(entry, token, valid_user, reject_invalid_on_public=reject_public)
        if denied is not None:
            status_code, err_code = denied
            msg = json.dumps({"error": err_code}).encode("utf-8")
            return (
                status_code,
                {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(msg)),
                    "X-Error-Code": err_code,
                },
                msg,
            )

        if (entry.status is not None and 300 <= entry.status < 400) or entry.redirect_to_cdn:
            redirect_status = entry.status if (entry.status is not None and 300 <= entry.status < 400) else HTTPStatus.FOUND
            quoted_repo = quote(entry.repo, safe="/")
            quoted_rev = quote(entry.revision, safe="/")
            quoted_file = quote(entry.filename, safe="/")
            location = f"{self.base_url}/cdn/{quoted_repo}/{quoted_rev}/{quoted_file}"
            hdrs = {
                "Location": location,
                "X-Repo-Commit": entry.commit,
                "X-Linked-Etag": f'"{entry.sha256}"',
                "X-Linked-Size": str(len(entry.content)),
                "ETag": f'"{entry.sha256}"',
                "Content-Length": "0",
            }
            return redirect_status, hdrs, b""

        return self._serve_entry_bytes(entry, headers, include_hf_meta=True)

    def handle_cdn(self, path: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        rest = unquote(path.removeprefix("/cdn/").lstrip("/"))
        entry: _FileEntry | None = None
        with self._lock:
            for (repo, revision, filename), candidate in self._files.items():
                if rest == f"{repo}/{revision}/{filename}":
                    entry = candidate
                    break
        if entry is None:
            return HTTPStatus.NOT_FOUND, {"Content-Length": "0"}, b""
        return self._serve_entry_bytes(entry, headers, include_hf_meta=False)

    @staticmethod
    def _serve_entry_bytes(
        entry: _FileEntry,
        headers: dict[str, str],
        *,
        include_hf_meta: bool,
    ) -> tuple[int, dict[str, str], bytes]:
        total = len(entry.content)
        lower_hdrs = {k.lower(): v for k, v in headers.items()}
        range_hdr = lower_hdrs.get("range")
        status = HTTPStatus.OK
        slice_bytes = entry.content
        resp_hdrs: dict[str, str] = {
            "Content-Type": "application/octet-stream",
            "ETag": f'"{entry.sha256}"',
            "Accept-Ranges": "bytes",
        }
        if include_hf_meta:
            resp_hdrs["X-Repo-Commit"] = entry.commit
            resp_hdrs["X-Linked-Etag"] = f'"{entry.sha256}"'
            resp_hdrs["X-Linked-Size"] = str(total)

        if range_hdr:
            parsed_range = _parse_range(range_hdr, total)
            if parsed_range is None:
                resp_hdrs["Content-Range"] = f"bytes */{total}"
                resp_hdrs["Content-Length"] = "0"
                return HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, resp_hdrs, b""
            start, end = parsed_range
            slice_bytes = entry.content[start : end + 1]
            status = HTTPStatus.PARTIAL_CONTENT
            resp_hdrs["Content-Range"] = f"bytes {start}-{end}/{total}"

        resp_hdrs["Content-Length"] = str(len(slice_bytes))
        return status, resp_hdrs, slice_bytes
