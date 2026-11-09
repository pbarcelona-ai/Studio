"""bookkit's chat calls against a small real HTTP server standing in for Hugging Face and a local model server."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import bookkit as bk


@pytest.fixture()
def chat_server():
    state = {"status": 200, "body": {"choices": [{"message": {"content": "<think>hmm</think> Hello there "}}]}, "seen": []}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            state["seen"].append({"auth": self.headers.get("Authorization"), "body": json.loads(self.rfile.read(n))})
            payload = json.dumps(state["body"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_port}/v1/chat/completions"
    yield state
    srv.shutdown()
    srv.server_close()


MSG = [{"role": "user", "content": "hi"}]


class TestHuggingFace:
    def test_sends_the_token_and_strips_reasoning(self, chat_server, monkeypatch):
        monkeypatch.setattr(bk, "HF_ROUTER_URL", chat_server["url"])
        monkeypatch.setenv("HF_TOKEN", " hf_abc ")
        assert bk.hf_chat(MSG, model="m/x", max_tokens=5, temperature=0.1) == "Hello there"
        sent = chat_server["seen"][0]
        assert sent["auth"] == "Bearer hf_abc" and sent["body"]["model"] == "m/x" and sent["body"]["max_tokens"] == 5 and sent["body"]["messages"] == MSG

    def test_default_model_and_missing_token(self, chat_server, monkeypatch):
        monkeypatch.setattr(bk, "HF_ROUTER_URL", chat_server["url"])
        monkeypatch.setenv("HF_TOKEN", "t")
        bk.hf_chat(MSG)
        assert chat_server["seen"][0]["body"]["model"] == bk.HF_DEFAULT_MODEL
        monkeypatch.delenv("HF_TOKEN")
        with pytest.raises(RuntimeError, match="HF_TOKEN is not set"):
            bk.hf_chat(MSG)

    @pytest.mark.parametrize("status,hint", [(401, "token was refused"), (402, "no Inference Providers credit"), (403, "lacks the"), (404, "not served"), (429, "rate limit"), (500, "")])
    def test_http_errors_get_a_plain_hint(self, chat_server, monkeypatch, status, hint):
        monkeypatch.setattr(bk, "HF_ROUTER_URL", chat_server["url"])
        monkeypatch.setenv("HF_TOKEN", "t")
        chat_server.update(status=status, body={"error": "nope"})
        with pytest.raises(RuntimeError, match=f"Hugging Face answered {status}") as e:
            bk.hf_chat(MSG)
        assert (hint in str(e.value)) and "nope" in str(e.value)

    def test_unexpected_answers(self, chat_server, monkeypatch):
        monkeypatch.setattr(bk, "HF_ROUTER_URL", chat_server["url"])
        monkeypatch.setenv("HF_TOKEN", "t")
        chat_server["body"] = {"choices": []}
        with pytest.raises(RuntimeError, match="unexpected answer from Hugging Face"):
            bk.hf_chat(MSG)
        chat_server["body"] = {"choices": [{"message": {"content": None}}]}
        assert bk.hf_chat(MSG) == ""


class TestLocal:
    def test_needs_a_model_and_sends_no_token(self, chat_server, monkeypatch):
        monkeypatch.setattr(bk, "LOCAL_LLM_URL", chat_server["url"])
        with pytest.raises(RuntimeError, match="choose a local model name"):
            bk.local_chat(MSG)
        assert bk.local_chat(MSG, model=" llama3 ") == "Hello there"
        assert chat_server["seen"][0]["auth"] is None and chat_server["seen"][0]["body"]["model"] == "llama3"

    def test_a_server_that_is_not_there(self, monkeypatch):
        monkeypatch.setattr(bk, "LOCAL_LLM_URL", "http://127.0.0.1:9/v1/chat/completions")
        with pytest.raises(RuntimeError, match="could not reach the local model server"):
            bk.local_chat(MSG, model="x", timeout=2)

    def test_http_errors_have_no_hf_hint(self, chat_server, monkeypatch):
        monkeypatch.setattr(bk, "LOCAL_LLM_URL", chat_server["url"])
        chat_server.update(status=401, body={"error": "x"})
        with pytest.raises(RuntimeError) as e:
            bk.local_chat(MSG, model="x")
        assert "the local model server answered 401" in str(e.value) and "HF_TOKEN" not in str(e.value)
