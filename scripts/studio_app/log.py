"""Logging for the Studio: one logger, written to studio.log next to the program and to the terminal."""
import logging
import logging.handlers

from .config import ROOT

LOG_FILE = ROOT / "studio.log"
_configured = False


def get_logger(name: str = "studio") -> logging.Logger:
    """The Studio logger (or a child of it). Safe to call many times; set up once."""
    global _configured
    root = logging.getLogger("studio")
    if not _configured:
        _configured = True
        root.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        try:
            fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:                           # a read-only folder must not stop the Studio
            pass
        sh = logging.StreamHandler()
        sh.setLevel(logging.WARNING)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    return root if name == "studio" else root.getChild(name)
