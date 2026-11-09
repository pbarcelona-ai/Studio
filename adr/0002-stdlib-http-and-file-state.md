# ADR 0002 – Standard-library HTTP server and file-based state
Status: accepted

**Context.** One person, one computer, non-developer install ("double-click the app"). Jobs run for hours and survive in files.

**Decision.** Keep `http.server.ThreadingHTTPServer` and plain CSV/JSON files. No database, no web framework, no build step for the page.

**Consequences.** Zero extra dependencies and easy backup/debug. Costs: one global job at a time (`jobs.JOB`), hand-written transport (kept small and tested), no migrations engine (use `schemas.upgrade`). Revisit if the Studio becomes multi-user or remote – then use a framework with real auth.
