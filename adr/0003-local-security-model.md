# ADR 0003 – Local security model
Status: accepted

**Context.** The server can start programs and read project files, so any web page the person visits must not be able to drive it.

**Decision.** Bind to 127.0.0.1; require a matching Host and (when present) Origin (defeats DNS rebinding and cross-site requests); require a random 24-byte token in a header, an `HttpOnly; SameSite=Strict` cookie, or `?t=` for media elements only; write the session file with mode 0600; cap request bodies; send CSP (`script-src 'self'`), `nosniff`, `no-referrer`; escape quotes in `escapeHtml`; resolve every file name against its project folder.

**Consequences.** No inline scripts or handlers in the page (test enforced). Google Fonts is the only external origin allowed. A same-user process that can read the session file can still use the Studio – accepted for a single-user machine.
