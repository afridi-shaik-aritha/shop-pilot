import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.config import Settings
from app.llm import LLMError, OpenAICompatibleClient, to_openai_tools


@dataclass(frozen=True)
class _StubTool:
    name: str
    description: str
    schema: dict


class _Handler(BaseHTTPRequestHandler):
    response_body: object = {}
    status: int = 200
    seen: dict = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        type(self).seen = {
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
            "body": json.loads(raw.decode("utf-8")),
        }
        data = json.dumps(type(self).response_body).encode("utf-8")
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture()
def api():
    _Handler.seen = {}
    _Handler.response_body = {}
    _Handler.status = 200
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join()


def _client(api, **kw):
    base = f"http://127.0.0.1:{api.server_port}/v1"
    return OpenAICompatibleClient(base, "sk-test", "m", **kw)


def _chat_msg(content="", calls=()):
    return {"choices": [{"message": {"content": content, "tool_calls": list(calls)}}]}


def _fn_call(name, arguments):
    return {"id": "1", "type": "function", "function": {"name": name, "arguments": arguments}}


def test_to_openai_tools_shape():
    tools = {
        "get_cart": _StubTool(
            "get_cart",
            "Read the cart.",
            {"name": "get_cart", "type": "object", "properties": {}, "required": []},
        )
    }
    assert to_openai_tools(tools) == [
        {
            "type": "function",
            "function": {
                "name": "get_cart",
                "description": "Read the cart.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
    ]


def test_chat_with_tool_call(api):
    _Handler.response_body = _chat_msg("", [_fn_call("get_cart", "{}")])
    msg = _client(api).complete([{"role": "user", "content": "hi"}], {"x": _StubTool("x", "Use x.", {"name": "x", "type": "object", "properties": {}, "required": []})})
    assert msg.tool_calls[0].name == "get_cart"
    assert msg.tool_calls[0].arguments == {}
    assert _Handler.seen["path"] == "/v1/chat/completions"
    assert _Handler.seen["auth"] == "Bearer sk-test"
    assert _Handler.seen["content_type"] == "application/json"
    assert _Handler.seen["body"]["model"] == "m"
    assert _Handler.seen["body"]["tool_choice"] == "auto"


def test_plain_answer_sends_no_tools(api):
    _Handler.response_body = _chat_msg("hello", [])
    msg = _client(api).complete([{"role": "user", "content": "hi"}], {})
    assert msg.content == "hello"
    assert msg.tool_calls == []
    assert _Handler.seen["body"]["tools"] == []
    assert _Handler.seen["body"]["tool_choice"] == "none"


def test_http_error_raises(api):
    _Handler.response_body = {"error": "boom"}
    _Handler.status = 500
    with pytest.raises(LLMError):
        _client(api).complete([], [])


def test_garbage_body_raises(api):
    _Handler.response_body = "oops"
    with pytest.raises(LLMError):
        _client(api).complete([], [])


def test_missing_choices_raises(api):
    _Handler.response_body = {}
    with pytest.raises(LLMError):
        _client(api).complete([], [])


def test_bad_tool_arguments_raise(api):
    _Handler.response_body = _chat_msg("", [_fn_call("get_cart", "not json")])
    with pytest.raises(LLMError):
        _client(api).complete([], [])


def test_from_settings_providers():
    nim = Settings(llm_provider="nim", llm_base_url="http://n:8000/v1",
                   llm_api_key="k", llm_model="meta/x")
    assert OpenAICompatibleClient.from_settings(nim)._url == "http://n:8000/v1/chat/completions"
    oro = Settings(llm_provider="openrouter", llm_base_url="https://openrouter.ai/api/v1/",
                   llm_api_key="k", llm_model="y")
    assert OpenAICompatibleClient.from_settings(oro)._url == "https://openrouter.ai/api/v1/chat/completions"
    with pytest.raises(ValueError):
        OpenAICompatibleClient.from_settings(Settings(llm_provider="other"))
    with pytest.raises(ValueError):
        OpenAICompatibleClient("", "k", "m")
