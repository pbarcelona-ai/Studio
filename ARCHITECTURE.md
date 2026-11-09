# Architecture

Pistachio's Studio is a **local, single-user** tool. A small Python HTTP server (`scripts/studio.py` → `scripts/studio_app/`) serves one web
page (`web/`) and runs the project's own scripts as background jobs. All state is plain files on disk.

```
browser ──HTTP (127.0.0.1)──► handler.py ──► api.py (route table) ──► routes_get.py / routes_post.py
                                   │                                         │
                          static files, media,                    domain modules (planner, generation, takes,
                          uploads, auth, headers                  scenes, llm, gallery, cleanup, kaggle_*, ...)
                                                                              │
                                                    jobs.py ──subprocess (argv list, no shell)──► scripts/*.py, run_*.sh
                                                                              │
                                              Kaggle / Colab / Hugging Face Space / this computer's GPU
```

## Layers (a module may import only from the layers above it)

| Layer | Modules | Responsibility |
|---|---|---|
| Foundation | `config`, `common`, `log`, `session`, `schemas` (scripts/) | paths, constants, `PlanError`, logging, token, data contracts |
| Domain | `projects`, `steps`, `gpus`, `generation`, `planner`, `takes`, `direction`, `scenes`, `single_prompts`, `llm`, `gallery`, `media`, `cleanup`, `kaggle_runs`, `kaggle_cleanup`, `overview` | what the Studio *does*; takes plain dicts, returns plain dicts, raises `PlanError` for mistakes the person can fix |
| Execution | `jobs` | runs a list of validated steps one after another; keeps the output; stop/kill |
| API | `api`, `routes_get`, `routes_post` | `@route("GET", "/api/x")` functions: `Request -> dict` |
| Transport | `handler`, `server` | Host/Origin check, token (header, cookie or `?t=` for media tags), CSP and other headers, body limits, media streaming, uploads |

Rules that keep this workable:
* Domain modules never import `handler`, `api` or the routes. `jobs` never imports `kaggle_cleanup`: the server sets `JOB.on_finish`.
* A mistake the person can fix → `raise PlanError("what to change")` (HTTP 400). A bug → let it propagate; `api.dispatch` logs it with a traceback and answers 500 without internals.
* Anything that starts a program builds an **argv list** (`steps.py`); `jobs.py` runs it without a shell. `shell_form()` is for display only.
* Anything read from the request that names a file goes through `common.resolve_project_file`, `handler.safe_project_file` or a `SLUG_RE` check.

## Data on disk
* `projects/books|characters|prompts/<name>/…` – see `scripts/layout.py`. Shot CSVs (`schemas.VIDEO_COLS` / `IMAGE_COLS`), `<book>.json` (continuity book, `schemas.validate_continuity`), `global_params.json` (`schema_version`), clips, audio, films.
* `scripts/studio_app/catalog.json` – model and GPU tables (edit data, not code); `scripts/check_catalog.py` verifies the Hugging Face ids exist (weekly CI).
* `.studio_session.json` – token + port, mode 0600, git-ignored. `studio.log` – rotating log, git-ignored.

## Security model (see ADR 0003)
Listens on 127.0.0.1 only. Every request needs the Host/Origin of this server and the session token. The page's own link (`/?t=…`) sets an
`HttpOnly; SameSite=Strict` cookie and redirects, so the token leaves the address bar. JSON bodies ≤ 8 MB, uploads ≤ 300 MB. CSP forbids inline
scripts and event handlers (`tests/test_web.py` enforces it). Notebook templates that run on Kaggle/Colab contain static shell lines; they are never built from request data (ADR 0004).

## The web page
`web/index.html` (markup), `web/static/css/*.css`, `web/static/js/*.js` (classic scripts sharing globals, loaded in order with `defer`). The token reaches the JS through `<meta name="studio-token">`.

## Quality gates (CI: `.github/workflows/ci.yml`)
`ruff check .` · `mypy` · `pytest --cov=scripts`. Locally: `uv venv .venv-dev && uv pip install --python .venv-dev/bin/python -e '.[dev]'`.
Tests cover auth and file-serving security, the planner, the job runner, media readers, schemas and catalog.
