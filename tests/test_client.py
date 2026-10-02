import pytest
import json

from plugin.core.client import BailianClient

@pytest.fixture
def client(tmp_path):
    conf_path = tmp_path / "cmd_config.json"
    conf_path.write_text(json.dumps({}))
    return BailianClient(str(conf_path), "test_source", log=lambda lvl, msg: None)

def test_client_chat_success(client, mocker):
    mock_http = mocker.patch("plugin.core.client.BailianClient.http_json")
    mock_http.return_value = (200, {
        "choices": [{"message": {"content": "success_reply"}}],
        "usage": {"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5}
    })
    txt, usage, meta = client.chat("test_model", [{"role": "user", "content": "hello"}], key="testkey", base="http://testbase")
    assert txt == "success_reply"
    assert meta["status"] == "ok"
    assert usage.in_tok == 5

def test_client_chat_http_error(client, mocker):
    mock_http = mocker.patch("plugin.core.client.BailianClient.http_json")
    # Simulate 500 error
    mock_http.return_value = (500, "Internal Server Error")
    txt, usage, meta = client.chat("test_model", [{"role": "user", "content": "hello"}], key="testkey", base="http://testbase")

    assert txt is None
    assert meta["status"] == "http500"
    assert "Internal Server Error" in meta["error"]

def test_client_resolve_llm_without_config(client):
    def mock_conf(key, default=None):
        return default

    # Empty config without astrbot fallback (already set to empty cmd_config in fixture)
    res = client.resolve_llm(mock_conf)
    assert res["ok"] is False
    assert "不可用" in res["why"]

def test_client_generate_network_exception(client, mocker):
    mock_http = mocker.patch("plugin.core.client.BailianClient.http_json")
    # Generate relies on HTTP returning failure body or network error handled by http_json
    mock_http.return_value = (-1, "Connection refused")

    # Test direct _gen_openai method failure mode which generate calls inside
    raw, usage, meta = client._gen_openai("testkey", "http://testbase", "test_model", "prompt", "1024*1024")
    assert raw is None
    assert meta["status"] == "http-1"
