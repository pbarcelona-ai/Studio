"""The access token and the session file (.studio_session.json: token + port, readable by this user only)."""
import json
import os
import secrets

from .config import ROOT
from .log import get_logger

log = get_logger("session")
SESSION_FILE = ROOT / ".studio_session.json"


class Session:
    """The random token every request must carry, and the port a running Studio used last time."""

    def __init__(self) -> None:
        self.token, self.port = self.load()

    @staticmethod
    def new_token() -> str:
        return secrets.token_urlsafe(24)

    @staticmethod
    def load() -> tuple[str, int | None]:
        """The saved token and port, or a fresh token and no port."""
        try:
            data = json.loads(SESSION_FILE.read_text())
            token, port = data["token"], data["port"]
            if isinstance(token, str) and len(token) >= 16 and isinstance(port, int):
                return token, port
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning("ignoring unreadable session file: %s", e)
        return Session.new_token(), None

    def reset(self) -> None:
        """Forget the saved session: a new token and no preferred port."""
        self.token, self.port = self.new_token(), None

    def save(self, port: int) -> None:
        """Write token+port with mode 0600 (the token lets whoever holds it run the Studio's jobs)."""
        try:
            fd = os.open(SESSION_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps({"token": self.token, "port": port}))
            os.chmod(SESSION_FILE, 0o600)         # the mode in os.open is ignored when the file already exists
        except OSError as e:
            log.warning("could not save the session file: %s", e)

    @staticmethod
    def remove() -> None:
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except OSError as e:
            log.warning("could not remove the session file: %s", e)

    def matches(self, candidate: str) -> bool:
        return secrets.compare_digest((candidate or "").encode(), self.token.encode())


SESSION = Session()
