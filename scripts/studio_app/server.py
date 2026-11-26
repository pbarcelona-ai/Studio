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


class StudioServer(ThreadingHTTPServer):
    request_queue_size = 128          # the page fetches a dozen files at once; the default backlog of 5 resets connections
    daemon_threads = True             # allow immediate clean exit on Ctrl+C even if browser tabs keep sockets open


def make_server(preferred_ports, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    """The first port in `preferred_ports` that is free (0 = any free port). Bound to localhost only."""
    for port in preferred_ports:
        try:
            return StudioServer((host, port), Handler)
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

    # Single-click auto-start for the local ComfyUI image engine (non-blocking background boot)
    from local_runners.comfyui_lifecycle import ensure_comfyui_started, stop_managed_comfyui
    comfy_state = ensure_comfyui_started(wait_ready_s=0.0)
    if comfy_state.get("status") == "started":
        print(f"Local ComfyUI starting in background ({comfy_state.get('url')})...", flush=True)
        log.info("autostarted ComfyUI pid=%s url=%s log=%s", comfy_state.get("pid"), comfy_state.get("url"), comfy_state.get("log_path"))
    elif comfy_state.get("status") == "already_running":
        log.info("local ComfyUI already running at %s", comfy_state.get("url"))

    import studio_index

    def after_jobs():                            # after the last job of a queue: Kaggle clean-up, and the search index sees the new pictures
        start_auto_cleanup()
        studio_index.rebuild_in_background()
    JOB.on_finish = after_jobs
    start_auto_cleanup()
    studio_index.rebuild_in_background()         # derived from the folders; a missing or old index is simply rebuilt
    from .resume import on_startup
    on_startup()                                 # a job from the last session that is still running: follow it
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        SESSION.remove()
        srv.server_close()
        if JOB.running:                          # the job keeps going on its own; the next Studio follows it (jobs.py, resume.py)
            print("\nstopped. A job is still running on its own: start the Studio again to follow it, or stop it there.", flush=True)
        else:
            print("\nstopped", flush=True)
    finally:
        if not JOB.running:
            stop_managed_comfyui()


if __name__ == "__main__":
    main()
