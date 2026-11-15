"""Kaggle limits a notebook's title (and so its slug, which must equal the title with dashes for spaces) to 50 characters, and a dataset's too.
A long book name made "<book>-<model>-keyframes-1-40" longer than that, and Kaggle answered "400 Bad Request" when the notebook was pushed.

  fit(name, tail)   <name><tail> in at most 50 characters: a name that is too long is cut and given a short number from its full text, so two
                    long names that start alike stay different (the same name always gives the same result)
  cksum5(text)      that short number: the first 5 digits of the POSIX `cksum` of the text. Computed here, so Windows (no cksum) gives the
                    same names as the old shell version, and runs started on a Mac are still recognised.
"""
from __future__ import annotations

MAX = 50


def _table() -> list[int]:
    out = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ 0x04C11DB7) if c & 0x80000000 else (c << 1)
        out.append(c & 0xFFFFFFFF)
    return out


_T = _table()


def cksum(data: bytes) -> int:
    """The POSIX cksum CRC (as the `cksum` command prints it): CRC-32/CKSUM over the bytes and then their length."""
    c = 0
    for b in data:
        c = ((c << 8) & 0xFFFFFFFF) ^ _T[(c >> 24) ^ b]
    n = len(data)
    while n:
        c = ((c << 8) & 0xFFFFFFFF) ^ _T[(c >> 24) ^ (n & 0xFF)]
        n >>= 8
    return (~c) & 0xFFFFFFFF


def cksum5(text: str) -> str:
    return str(cksum(text.encode("utf-8")))[:5]


def fit(name: str, tail: str) -> str:
    room = MAX - len(tail)
    if len(name) <= room:
        return name + tail
    cut = name[: room - 6].rstrip("-")
    return f"{cut}-{cksum5(name)}{tail}"
