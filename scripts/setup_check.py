"""First-run setup for Pistachio's Studio: what this computer still needs, and a safe place to keep each person's own keys.

The Studio page shows `check()` in its Setup window and calls `save()` when someone pastes a key. Keys are only ever written to files on THIS
computer, with owner-only permissions, and are never sent back to the page (the page only learns "found" or "missing").

  Kaggle login   -> ~/.kaggle/kaggle.json (username + key) or ~/.kaggle/access_token (an API token); both are what the Kaggle program reads itself
  Hugging Face   -> ~/.pistachios_studio/settings.json, loaded into the environment when the Studio starts (a HF_TOKEN already in the environment wins)

Every function takes `home` and `environ` so the tests can run against a throw-away folder instead of the real one.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SETTINGS_DIR = ".pistachios_studio"
SAVED_KEYS = ("HF_TOKEN",)                      # keys kept in settings.json and loaded into the environment
USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,59}$")
SECRET_RE = re.compile(r"^[A-Za-z0-9_.\-]{10,200}$")
_loaded = set()                                  # environment variables this module set from settings.json (so "remove" only unsets those)


def _home(home):
    return Path(home) if home else Path.home()


def settings_path(home=None):
    return _home(home) / SETTINGS_DIR / "settings.json"


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_private(path, text):
    """Write a file that only the owner can read, without ever leaving it world-readable, even for a moment."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def load_saved_env(home=None, environ=None):
    """Put the saved keys into the environment (the Studio calls this once at start-up). Returns the names that were set."""
    env = os.environ if environ is None else environ
    data = _read_json(settings_path(home))
    done = []
    for k in SAVED_KEYS:
        v = str(data.get(k) or "").strip()
        if v and not env.get(k):
            env[k] = v
            _loaded.add(k)
            done.append(k)
    return done


def kaggle_state(home=None, environ=None):
    """Where a Kaggle login is found: {"found": bool, "how": text, "username": text or ""}. Never returns the key itself."""
    env = os.environ if environ is None else environ
    kdir = _home(home) / ".kaggle"
    cred = _read_json(kdir / "kaggle.json")
    oauth = _read_json(kdir / "credentials.json")
    user = str(cred.get("username") or oauth.get("username") or env.get("KAGGLE_USERNAME") or "").strip()
    if env.get("KAGGLE_API_TOKEN"):
        return {"found": True, "how": "KAGGLE_API_TOKEN in the environment", "username": user}
    if env.get("KAGGLE_USERNAME") and env.get("KAGGLE_KEY"):
        return {"found": True, "how": "KAGGLE_USERNAME and KAGGLE_KEY in the environment", "username": user}
    if cred.get("username") and cred.get("key"):
        return {"found": True, "how": "~/.kaggle/kaggle.json", "username": user}
    if (kdir / "access_token").is_file() and (kdir / "access_token").stat().st_size > 0:
        return {"found": True, "how": "~/.kaggle/access_token", "username": user}
    if oauth.get("refresh_token") or oauth.get("access_token"):
        return {"found": True, "how": "~/.kaggle/credentials.json (kaggle auth login)", "username": user}
    return {"found": False, "how": "", "username": user}


def _has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def check(path=None, home=None, environ=None, local_llm_ready=False, local_gpu="", gpu_seen=""):
    """The list shown in the Setup window. Each item: id, title, level (required / recommended / optional), ok, detail, fix.
    local_gpu: this computer's NVIDIA GPU (for example "NVIDIA RTX 4090 (24 GB)"), or "" if it has none. With one, models can run here
    (scripts/run_local_model.py), so a Kaggle account becomes optional instead of required. gpu_seen: why the GPU that was found cannot be used."""
    env = os.environ if environ is None else environ
    which = lambda t: shutil.which(t, path=path)
    items = []

    def add(id_, title, level, ok, detail, fix=""):
        items.append({"id": id_, "title": title, "level": level, "ok": bool(ok), "detail": detail, "fix": "" if ok else fix})

    v = sys.version_info
    add("python", "Python 3.9 or newer", "required", v >= (3, 9), f"Python {v.major}.{v.minor}.{v.micro}",
        "Install a current Python from python.org (or: brew install python), then run install.sh again.")
    add("local_gpu", "A GPU in this computer (NVIDIA, Linux or Windows WSL 2)", "optional" if not local_gpu else "recommended", bool(local_gpu),
        local_gpu or gpu_seen or "none found: the models run on Kaggle, Colab or Hugging Face instead",
        "Only needed to run the models here instead of on a website: an NVIDIA GPU with its driver (nvidia-smi), on Linux or WSL 2.")
    if local_gpu:
        add("git", "git (some models fetch their own program)", "recommended", bool(which("git")), "found" if which("git") else "not found",
            "Install git with your package manager (for example: sudo apt install git)")
        add("nvcc", "CUDA compiler nvcc (only for the FlashVSR upscaler)", "optional", bool(which("nvcc")), "found" if which("nvcc") else "not found",
            "Install the CUDA toolkit that matches your driver (for example: sudo apt install nvidia-cuda-toolkit)")
    web = "optional" if local_gpu else "required"         # with a GPU here, the websites are a choice, not a need
    add("kaggle_cli", "Kaggle command-line program", web, bool(which("kaggle")), "found" if which("kaggle") else "not found",
        "Run ./install.sh (it installs it), or: pip install kaggle")
    ks = kaggle_state(home, env)
    add("kaggle_login", "Kaggle login", web, ks["found"],
        (f"found in {ks['how']}" + (f" (account: {ks['username']})" if ks["username"] else "")) if ks["found"] else "no Kaggle key on this computer",
        "Paste your Kaggle API token below (kaggle.com > Settings > API > Create New Token), or run: kaggle auth login")
    add("uv", "uv (runs the PDF reader and the film joiner)", "recommended", bool(which("uv")), "found" if which("uv") else "not found",
        "Run ./install.sh (it installs it), or: pip install uv")
    add("pillow", "Pillow (small preview pictures)", "recommended", _has_module("PIL"), "found" if _has_module("PIL") else "not found",
        "Run ./install.sh, or: pip install pillow")
    have_3d = all(_has_module(m) for m in ("numpy", "cv2", "transformers", "torch"))
    add("depth3d", "3D depth view (numpy, opencv, transformers, torch)", "optional", have_3d, "found" if have_3d else "not installed; the 3D button stays unavailable",
        "Optional and large (about 2 GB): ./install.sh --3d")
    writers = [n for n, ok in (("Claude Code", bool(which("claude"))), ("Codex", bool(which("codex"))), ("Hugging Face", bool(env.get("HF_TOKEN", "").strip())),
                               ("a local model server", bool(local_llm_ready))) if ok]
    add("writer", "An AI prompt writer", "recommended", bool(writers), ("available: " + ", ".join(writers)) if writers else "none found",
        "Install Claude Code or Codex, or paste a Hugging Face token below. Without one you can still type your own prompts.")
    hf = bool(env.get("HF_TOKEN", "").strip())
    add("hf_token", "Hugging Face token", "optional", hf, "found" if hf else "not set (only needed for the Hugging Face prompt writer)",
        "Paste a token below (huggingface.co > Settings > Access Tokens). Inference Providers needs prepaid credit.")
    return items


def summary(items):
    req = [i for i in items if i["level"] == "required" and not i["ok"]]
    return {"ready": not req, "missing_required": [i["id"] for i in req]}


def save(body, home=None, environ=None):
    """Store what the person pasted. Fields (all optional): kaggle_username + kaggle_key, kaggle_token, hf_token, clear (list of "hf_token", "kaggle").
    Raises ValueError with a plain-English message when something does not look right. Returns the names that were saved."""
    env = os.environ if environ is None else environ
    kdir = _home(home) / ".kaggle"
    saved = []
    token = str(body.get("kaggle_token") or "").strip()
    user = str(body.get("kaggle_username") or "").strip()
    key = str(body.get("kaggle_key") or "").strip()
    hf = str(body.get("hf_token") or "").strip()
    if token:
        if not SECRET_RE.match(token):
            raise ValueError("that does not look like a Kaggle API token (it should be one unbroken piece of text, 10 to 200 characters)")
        _write_private(kdir / "access_token", token)
        saved.append("kaggle_token")
    if user or key:
        if not (user and key):
            raise ValueError("enter both the Kaggle username and the key, or use the API token box instead")
        if not USER_RE.match(user):
            raise ValueError("that Kaggle username has characters Kaggle does not allow (use the part after kaggle.com/)")
        if not SECRET_RE.match(key):
            raise ValueError("that does not look like a Kaggle key (one unbroken piece of text, 10 to 200 characters)")
        _write_private(kdir / "kaggle.json", json.dumps({"username": user, "key": key}))
        saved.append("kaggle_login")
    if hf:
        if not SECRET_RE.match(hf):
            raise ValueError("that does not look like a Hugging Face token (it usually starts with hf_ and has no spaces)")
        data = _read_json(settings_path(home))
        data["HF_TOKEN"] = hf
        _write_private(settings_path(home), json.dumps(data))
        env["HF_TOKEN"] = hf
        _loaded.add("HF_TOKEN")
        saved.append("hf_token")
    for what in body.get("clear") or []:
        if what == "hf_token":
            data = _read_json(settings_path(home))
            data.pop("HF_TOKEN", None)
            _write_private(settings_path(home), json.dumps(data))
            if "HF_TOKEN" in _loaded:
                env.pop("HF_TOKEN", None)
                _loaded.discard("HF_TOKEN")
            saved.append("hf_token_removed")
    return saved


def test_kaggle(path=None, home=None, environ=None, timeout=45):
    """Ask Kaggle one cheap question to prove the login works. Returns {"ok": bool, "message": text}; never returns what Kaggle answered."""
    exe = shutil.which("kaggle", path=path)
    if not exe:
        return {"ok": False, "message": "The Kaggle program is not installed (run ./install.sh)."}
    env = dict(os.environ if environ is None else environ)
    if not kaggle_state(home, env)["found"]:
        return {"ok": False, "message": "No Kaggle key is saved on this computer yet. Paste your API token above and press Save first."}
    if home:
        env["HOME"] = str(home)
    if path:
        env["PATH"] = path
    try:
        r = subprocess.run([exe, "kernels", "list", "--mine", "--page-size", "1"], capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Kaggle did not answer in time. Check your internet connection and try again."}
    if r.returncode == 0:
        return {"ok": True, "message": "Kaggle accepted the login."}
    err = (r.stderr or r.stdout or "").strip().splitlines()
    low = " ".join(err).lower()
    if "401" in low or "unauthor" in low or "credential" in low or "could not find" in low or "authenticat" in low:
        return {"ok": False, "message": "Kaggle did not accept the login. Check the username and key (or create a new token) and try again."}
    lines = [l.strip() for l in err if l.strip() and not l.strip().startswith(("File ", "Traceback", "<"))]
    return {"ok": False, "message": "Kaggle answered with an error: " + (lines[-1][:200] if lines else "no details") + ". Check your internet connection and your token."}
