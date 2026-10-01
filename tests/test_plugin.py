import asyncio
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from astrbot.api.event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain

class MockEvent(AstrMessageEvent):
    def __init__(self, message_str: str):
        self.message_str = message_str
        self.sent_messages = []
        self._message_obj = MagicMock()
        self._message_obj.message_id = "mock_msg_123"

    @property
    def message_obj(self):
        return self._message_obj

    def get_sender_id(self):
        return "mock_user"

    def get_session_id(self):
        return "mock_session"

    def get_message_id(self):
        return "mock_msg_123"

    async def send(self, message):
        self.sent_messages.append(message)

    def plain_result(self, msg):
        return MessageChain([MagicMock(text=msg)])

    def chain_result(self, chain):
        return MessageChain(chain)


@pytest.fixture
def astrbot_mock_env():
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir)

@pytest.fixture
def plugin_instance(astrbot_mock_env):
    import plugin.main

    class MockContext:
        def register_commands(self, plugin):
            pass

    with patch("plugin.core.siteconf.get_astrbot_data_path", create=True, return_value=astrbot_mock_env), \
         patch("plugin.main.get_astrbot_data_path", create=True, return_value=astrbot_mock_env), \
         patch("astrbot.core.utils.astrbot_path.get_astrbot_data_path", return_value=astrbot_mock_env):

        pi = plugin.main.WhaleChanMemePlugin(context=MockContext())
        yield pi

@pytest.mark.asyncio
async def test_plugin_initialization(plugin_instance):
    assert plugin_instance is not None
    assert plugin_instance.site is not None
    assert plugin_instance.pipeline is not None

@pytest.mark.asyncio
async def test_configuration_loading(plugin_instance):
    # Test valid configuration update
    plugin_instance.site.update({
        "gen_base_url": "http://mock.gen/v1",
        "gen_api_key": "mock_gen_key",
        "model": "mock_model",
        "size": "1024*1024",
        "llm_source": "custom",
        "llm_base_url": "http://mock.llm/v1",
        "llm_api_key": "mock_llm_key",
        "cooldown": 0
    })

    assert plugin_instance.site.get("gen_base_url") == "http://mock.gen/v1"
    assert plugin_instance.site.get("model") == "mock_model"

@pytest.mark.asyncio
async def test_image_generation_workflow(plugin_instance):
    plugin_instance.site.update({
        "cooldown": 0
    })

    event = MockEvent("/快图 测试文字")
    with patch.object(plugin_instance.pipeline, "run") as mock_run:
        mock_run.return_value = {
            "img": b"mock_image_bytes",
            "rec": {"id": "123", "error": ""},
            "caption": "测试文字"
        }

        res_list = []
        gen = plugin_instance.cmd_fast_draw(event)
        async for res in gen:
            res_list.append(res)

        assert len(res_list) > 0
        assert mock_run.called

@pytest.mark.asyncio
async def test_failure_handling(plugin_instance):
    plugin_instance.site.update({"cooldown": 0})
    event = MockEvent("/快图 测试文字")

    # Simulate a pipeline failure
    with patch.object(plugin_instance.pipeline, "run") as mock_run:
        mock_run.return_value = {
            "img": None,
            "rec": {"id": "123", "error": "mock_error"},
            "caption": "测试文字"
        }

        res_list = []
        gen = plugin_instance.cmd_fast_draw(event)
        async for res in gen:
            res_list.append(res)

        assert len(res_list) > 0

@pytest.mark.asyncio
async def test_api_timeout_handling(plugin_instance):
    # Testing how the HTTP client handles a timeout
    client = plugin_instance.client
    with patch("urllib.request.urlopen") as mock_urlopen:
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("timeout")

        res, usage, meta = client.chat(
            "test_model",
            [{"role": "user", "content": "hello"}],
            key="test", base="http://test.api"
        )

        assert res is None
        assert "urllib" in meta["error"] or "timeout" in meta["error"]

@pytest.mark.asyncio
async def test_malformed_json_response(plugin_instance):
    client = plugin_instance.client
    with patch.object(client, "http_json") as mock_http:
        mock_http.return_value = (200, "invalid json")

        res, usage, meta = client.chat(
            "test_model",
            [{"role": "user", "content": "hello"}],
            key="test", base="http://test.api"
        )

        assert res is None
        assert "json" in meta["error"].lower()
