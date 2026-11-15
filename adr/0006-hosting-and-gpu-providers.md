# ADR 0006 – Hosting the Studio for other people, and GPU providers
Status: proposed (design for ROADMAP Phase 5; the pieces marked "built" exist, the rest does not).
Update 2026-11-10: accounts and storage are skipped by decision. The provider list is now on the Models tab (`studio_app/providers.json`): This computer, Free external, and Paid external marked unproven; no paid adapter is built.

**Context.** ADR 0003 makes the Studio safe on one person's computer by binding to 127.0.0.1 and trusting every request that carries the session token. That
design cannot be exposed to other people as it is: the token is full control (it can start programs, read every project file and spend the owner's Kaggle quota),
there is one set of projects, one job at a time, and the producer must install Kaggle, a Hugging Face token and Claude Code.

**What is built (local, single owner, still ADR 0003).**
- *Private preview links* (`scripts/shares.py`, `/watch/<book>/<token>`): a 192-bit token opens one finished film and its captions to anyone, with expiry, revocation,
  a view count and `noindex`. Nothing else is reachable through it, and the Studio's own routes still need the session token. A link is served only for Host
  names the owner allows (`STUDIO_WATCH_HOSTS`, e.g. a tunnel's name), so the Studio is not open to DNS rebinding through it. Tested in `tests/test_shares.py`.
- *Job queue* (`studio_app/jobs.py`): a job started while another runs can wait (up to 10), shares the log, and drops if the running job is stopped. Jobs still run one
  at a time; "several at once" needs per-user process isolation first (below), because the page, `JOB` and the `_need_idle()` guards assume one job per Studio.
- *Adult-content models* are off by default (hidden and refused until `STUDIO_ADULT_MODELS=1` or the Models tab switch) so a default or hosted catalogue does not offer them.
- The page's main flow is four tabs (Book and Script, Cast and Look, Storyboard and Shoot, Cut and Premiere); Models, Single Prompts, Library and Compare sit under Advanced.

**Decision for hosting (not built).** One Studio process per account, behind a small gateway, rather than making one process multi-tenant.
1. *Gateway* (new, stdlib or a small framework): sign-up and login (scrypt password hashes, constant-time compare, login throttling, `HttpOnly; Secure; SameSite=Strict`
   session cookie, CSRF token on writes), and for each logged-in account it finds or starts a Studio child with `STUDIO_HOME=/data/<account id>` and its own port, then
   reverse-proxies `/` to it while injecting that child's session token. The child never listens on a public interface.
2. *Data root*: `STUDIO_HOME` replaces `ROOT` for `projects/`, `books/`, the setup `.env` and the flag files. Today `config.ROOT`, `layout.ROOT` and `bookkit.ROOT` are the
   repository; they must become "code root" and "data root". The tests already redirect all of them through `fake_root`, which is the list of what to change.
3. *Isolation*: each child runs as an unprivileged user (or in a container) with its data directory only, a disk quota, a CPU/memory limit, no access to other accounts'
   tokens, and `uv`/`ffmpeg` only through the existing argv-list subprocess pattern (no shell).
4. *Watch links* move to the gateway: the public host serves only `/watch/...` (proxied to the owning child), so a viewer never reaches a Studio.
5. *Storage*: films and clips on the account's volume; an object store (S3-compatible) later, behind the same `projects/` paths.
6. *Rights and licences* (Phase 6) are checked in the child, since it knows the models used.

**Decision for GPU providers (not built).** A provider is a small adapter with `submit(model, rows, csv) -> run id`, `status(run id)`, `fetch(run id) -> files`, matching what
`run_kaggle_model.sh`, `run_colab_model.sh`, `run_hf_space.py` and `run_local_model.py` already do per service. Candidates: an HTTP prediction API (submit JSON, poll, download
the output URL; the model-to-input mapping lives in a `providers.json` the owner edits, not in code), and a rented GPU box reached over SSH that runs `run_local_model.py`.
Billing is the provider's; the budget preview (`budget.py`) gets a `gpu_usd_per_hour` per provider. The producer-facing setup shrinks to "paste a provider key" in the
account's own settings. Until a provider is chosen and tried against its real service, any adapter would be unverified code, so none is written.

**Consequences.**
- Everything above the gateway stays as it is: the Studio remains a single-user program that happens to run in a box. That keeps ADR 0003 true for the part that matters.
- Per-account processes cost memory; idle children are stopped after a timeout and restarted at the next login.
- Several jobs at once are then per account (several children share one GPU provider, not one machine's disk), which is the case the queue was built for.

**Open questions.** Who pays for the language-model calls (the owner's Claude/Codex login does not exist in a hosted account: use an API key per account or a pooled one)?
Which GPU provider first? Is a self-service sign-up wanted, or invitation only (much simpler to run safely)?
