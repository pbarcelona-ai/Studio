# ADR 0001 – Split the server into a package with a route table
Status: accepted

**Context.** `studio.py` had grown to 3,650 lines: HTTP routing (a 600-line if-chain), planning, GPU rules, Kaggle, LLM calls, thumbnails and clean-up in one file, untestable in parts.

**Decision.** `scripts/studio_app/` package, layered as in ARCHITECTURE.md. Routes are functions registered with `@route`; `api.dispatch` maps `PlanError`→400, `HttpError`→its code, unexpected errors→logged 500. `scripts/studio.py` remains the command and re-exports the names `regress_kaggle.py` imports.

**Consequences.** Behaviour is unchanged (verified by comparing 39 endpoint responses before and after). Each module can be tested alone. Cycles are forbidden; the one existing cycle (jobs ↔ kaggle_cleanup) became a callback.
