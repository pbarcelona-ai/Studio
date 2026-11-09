"""Start-up: choose a port, make the HTTP server, print the link, run until Ctrl-C."""
import argparse
import webbrowser
from http.server import ThreadingHTTPServer

import setup_check

from .handler import Handler
from .jobs import JOB
from .kaggle_cleanup import start_auto_cleanup
from .log import get_logger
from .session import SESSION

log = get_logger("server")


def make_server(preferred_ports, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """The first port in `preferred_ports` that is free (0 = any free port). Bound to localhost only."""
    for port in preferred_ports:
        try:
            return ThreadingHTTPServer((host, port), Handler)
        except OSError:
            continue
    raise SystemExit("no free port found")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--new-session", action="store_true", help="Force new session (don't reuse existing)")
    a = ap.parse_args(argv)
    setup_check.load_saved_env()                 # keys saved from the Setup window (a variable already in the environment wins)

    if a.new_session:
        SESSION.remove()
        SESSION.reset()

    ports = ([SESSION.port] if SESSION.port else []) + list(range(a.port, a.port + 20))
    srv = make_server(ports)
    SESSION.save(srv.server_port)

    url = f"http://127.0.0.1:{srv.server_port}/?t={SESSION.token}"
    print(f"Pistachio's Studio running. Open: {url}\nCtrl-C to stop.", flush=True)
    log.info("listening on 127.0.0.1:%s", srv.server_port)
    JOB.on_finish = start_auto_cleanup
    start_auto_cleanup()
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        JOB.stop()
        SESSION.remove()
        print("\nstopped")


if __name__ == "__main__":
    main()
