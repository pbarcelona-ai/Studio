"""setup_check: finding logins, saving keys privately, the Setup list and the Kaggle login test (all against throw-away folders)."""
import json
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest

import setup_check as sc


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


@pytest.fixture
def env():
    return {}


def mode(p):
    return stat.S_IMODE(Path(p).stat().st_mode)


class TestKaggleState:
    def test_nothing(self, home, env):
        assert sc.kaggle_state(home, env) == {"found": False, "how": "", "username": ""}

    @pytest.mark.parametrize("environ,how", [({"KAGGLE_API_TOKEN": "t"}, "KAGGLE_API_TOKEN"), ({"KAGGLE_USERNAME": "u", "KAGGLE_KEY": "k"}, "KAGGLE_USERNAME and KAGGLE_KEY")])
    def test_environment(self, home, environ, how):
        s = sc.kaggle_state(home, environ)
        assert s["found"] and how in s["how"]

    def test_files(self, home, env):
        (home / ".kaggle").mkdir(parents=True)
        (home / ".kaggle" / "kaggle.json").write_text(json.dumps({"username": "pat", "key": "k" * 20}))
        s = sc.kaggle_state(home, env)
        assert s == {"found": True, "how": "~/.kaggle/kaggle.json", "username": "pat"}

    def test_token_file_must_not_be_empty(self, home, env):
        (home / ".kaggle").mkdir(parents=True)
        (home / ".kaggle" / "access_token").write_text("")
        assert not sc.kaggle_state(home, env)["found"]
        (home / ".kaggle" / "access_token").write_text("tok")
        assert sc.kaggle_state(home, env)["found"]

    def test_oauth_credentials(self, home, env):
        (home / ".kaggle").mkdir(parents=True)
        (home / ".kaggle" / "credentials.json").write_text(json.dumps({"refresh_token": "r", "username": "pat"}))
        assert sc.kaggle_state(home, env)["found"]

    def test_the_key_is_never_returned(self, home, env):
        (home / ".kaggle").mkdir(parents=True)
        (home / ".kaggle" / "kaggle.json").write_text(json.dumps({"username": "pat", "key": "SECRETSECRET"}))
        assert "SECRETSECRET" not in json.dumps(sc.kaggle_state(home, env))


class TestSave:
    def test_token_is_stored_privately(self, home, env):
        assert sc.save({"kaggle_token": "a" * 30}, home, env) == ["kaggle_token"]
        p = home / ".kaggle" / "access_token"
        assert p.read_text() == "a" * 30 and mode(p) == 0o600 and mode(p.parent) == 0o700

    def test_username_and_key(self, home, env):
        assert sc.save({"kaggle_username": "pat", "kaggle_key": "k" * 20}, home, env) == ["kaggle_login"]
        assert json.loads((home / ".kaggle" / "kaggle.json").read_text()) == {"username": "pat", "key": "k" * 20}
        assert mode(home / ".kaggle" / "kaggle.json") == 0o600

    @pytest.mark.parametrize("body,msg", [({"kaggle_token": "bad token!"}, "API token"), ({"kaggle_token": "short"}, "API token"),
                                          ({"kaggle_username": "pat"}, "both"), ({"kaggle_key": "k" * 20}, "both"),
                                          ({"kaggle_username": "../x", "kaggle_key": "k" * 20}, "username"), ({"kaggle_username": "pat", "kaggle_key": "has space in it"}, "Kaggle key"),
                                          ({"hf_token": "x y"}, "Hugging Face token")])
    def test_refused_and_nothing_written(self, home, env, body, msg):
        with pytest.raises(ValueError, match=msg):
            sc.save(body, home, env)
        assert not home.exists() or not list(home.rglob("*"))

    def test_hf_token_is_saved_and_put_in_the_environment(self, home, env):
        assert sc.save({"hf_token": "hf_" + "a" * 20}, home, env) == ["hf_token"]
        assert env["HF_TOKEN"] == "hf_" + "a" * 20 and mode(sc.settings_path(home)) == 0o600

    def test_clear_removes_only_what_the_studio_set(self, home, env):
        sc.save({"hf_token": "hf_" + "a" * 20}, home, env)
        assert sc.save({"clear": ["hf_token"]}, home, env) == ["hf_token_removed"]
        assert "HF_TOKEN" not in env and "HF_TOKEN" not in json.loads(sc.settings_path(home).read_text())

    def test_clear_keeps_a_token_from_the_users_own_environment(self, home):
        mine = {"HF_TOKEN": "from-the-shell-env"}
        sc._loaded.discard("HF_TOKEN")
        sc.save({"clear": ["hf_token"]}, home, mine)
        assert mine["HF_TOKEN"] == "from-the-shell-env"


class TestLoadSavedEnv:
    def test_loads_but_never_overrides(self, home):
        sc.save({"hf_token": "hf_" + "b" * 20}, home, {})
        fresh = {}
        assert sc.load_saved_env(home, fresh) == ["HF_TOKEN"] and fresh["HF_TOKEN"] == "hf_" + "b" * 20
        own = {"HF_TOKEN": "mine"}
        assert sc.load_saved_env(home, own) == [] and own["HF_TOKEN"] == "mine"

    def test_missing_or_corrupt_settings(self, home):
        assert sc.load_saved_env(home, {}) == []
        sc.settings_path(home).parent.mkdir(parents=True)
        sc.settings_path(home).write_text("{broken")
        assert sc.load_saved_env(home, {}) == []


class TestCheck:
    def items(self, home, env, **kw):
        return {i["id"]: i for i in sc.check(path="", home=home, environ=env, **kw)}

    def test_python_item_matches_the_real_requirement(self, home, env):
        i = self.items(home, env)["python"]
        assert i["title"] == "Python 3.11 or newer" and i["ok"] and i["level"] == "required" and i["fix"] == ""

    def test_without_a_gpu_kaggle_is_required(self, home, env):
        items = self.items(home, env)
        assert items["kaggle_cli"]["level"] == "required" and items["kaggle_login"]["level"] == "required" and "git" not in items
        assert not items["kaggle_login"]["ok"] and items["kaggle_login"]["fix"]
        assert sc.summary(list(items.values()))["missing_required"] == ["kaggle_cli", "kaggle_login"]

    def test_with_a_gpu_kaggle_is_optional(self, home, env):
        items = self.items(home, env, local_gpu="NVIDIA RTX 4090 (24 GB)")
        assert items["kaggle_login"]["level"] == "optional" and "git" in items and items["local_gpu"]["level"] == "recommended"
        assert sc.summary(list(items.values())) == {"ready": True, "missing_required": []}

    def test_writer_lists_what_is_available(self, home):
        assert self.items(home, {})["writer"]["ok"] is False
        w = self.items(home, {"HF_TOKEN": "hf_x"}, local_llm_ready=True)["writer"]
        assert w["ok"] and "Hugging Face" in w["detail"] and "local model server" in w["detail"]

    def test_gpu_seen_reason_is_shown(self, home, env):
        assert "too small" in self.items(home, env, gpu_seen="too small")["local_gpu"]["detail"]

    def test_login_detail_names_the_account_but_not_the_key(self, home):
        e = {"KAGGLE_USERNAME": "pat", "KAGGLE_KEY": "SECRETSECRET"}
        text = json.dumps(sc.check(path="", home=home, environ=e))
        assert "pat" in text and "SECRETSECRET" not in text


class TestKaggleLoginTest:
    @pytest.fixture(autouse=True)
    def exe(self, monkeypatch):
        monkeypatch.setattr(sc.shutil, "which", lambda n, path=None: "/bin/kaggle")

    def logged_in(self, home):
        sc.save({"kaggle_token": "a" * 30}, home, {})

    def test_not_installed(self, home, monkeypatch):
        monkeypatch.setattr(sc.shutil, "which", lambda n, path=None: None)
        assert "not installed" in sc.test_kaggle(home=home, environ={})["message"]

    def test_no_key_yet(self, home):
        assert "No Kaggle key" in sc.test_kaggle(home=home, environ={})["message"]

    def test_ok(self, home, monkeypatch):
        self.logged_in(home)
        monkeypatch.setattr(sc.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="secret listing", stderr=""))
        out = sc.test_kaggle(home=home, environ={})
        assert out == {"ok": True, "message": "Kaggle accepted the login."}

    def test_rejected(self, home, monkeypatch):
        self.logged_in(home)
        monkeypatch.setattr(sc.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="401 Unauthorized"))
        assert "did not accept" in sc.test_kaggle(home=home, environ={})["message"]

    def test_other_error_shows_the_last_useful_line(self, home, monkeypatch):
        self.logged_in(home)
        err = "Traceback (most recent call last):\n  File x\nConnectionError: no route to host"
        monkeypatch.setattr(sc.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=err))
        assert "no route to host" in sc.test_kaggle(home=home, environ={})["message"]

    def test_timeout(self, home, monkeypatch):
        self.logged_in(home)

        def slow(*a, **k):
            raise subprocess.TimeoutExpired("kaggle", 1)
        monkeypatch.setattr(sc.subprocess, "run", slow)
        assert "did not answer in time" in sc.test_kaggle(home=home, environ={})["message"]
