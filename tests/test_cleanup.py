import pytest
import os
import shutil
from unittest.mock import MagicMock, patch

from plugin.core.pipeline import Pipeline
from plugin.main import WhaleChanMemePlugin

@pytest.fixture
def pipeline(tmp_path):
    config_mock = MagicMock(return_value=False) # keep_assets = False
    client_mock = MagicMock()
    # Mock LLM and Gen resolution to pass checks
    client_mock.resolve_llm = MagicMock(return_value={"ok": True, "label": "llm", "model": "m"})
    client_mock.resolve_gen = MagicMock(return_value={"ok": True, "label": "gen", "model": "m", "dialect": "openai"})

    journal_mock = MagicMock()

    tmp_tmp = tmp_path / "tmp"
    tmp_outputs = tmp_path / "outputs"
    tmp_state = tmp_path / "state"

    tmp_tmp.mkdir(exist_ok=True)
    tmp_outputs.mkdir(exist_ok=True)
    tmp_state.mkdir(exist_ok=True)

    paths = {
        "state": str(tmp_state),
        "tmp": str(tmp_tmp),
        "outputs": str(tmp_outputs),
        "logs": str(tmp_path / "logs"),
        "ref_default": str(tmp_state / "character_front.jpg"),
        "sheet": str(tmp_state / "character_ref.jpg"),
    }

    p = Pipeline(config_mock, client_mock, journal_mock, paths, log=lambda lvl, msg: None)
    return p

@patch('plugin.core.pipeline.shutil.rmtree')
def test_pipeline_run_cleanup_success(mock_rmtree, pipeline):
    pipeline.enhance = MagicMock(return_value=({"prompt": "test prompt", "needs_asset": False}, {"id": 1}))
    pipeline._build_prompt = MagicMock(return_value="assembled prompt")
    pipeline.client.generate = MagicMock(return_value=(b"fake image data", [{"status": "success"}]))

    pipeline.run("scene", "caption", True)

    # Assert rmtree was called with the tmpdir created
    assert mock_rmtree.called

@patch('plugin.core.pipeline.shutil.rmtree')
def test_pipeline_run_cleanup_exception(mock_rmtree, pipeline):
    # Simulate an unexpected exception in _run_impl
    pipeline._run_impl = MagicMock(side_effect=Exception("Unexpected Error"))

    with pytest.raises(Exception):
        pipeline.run("scene", "caption", True)

    # Assert rmtree was still called despite exception
    assert mock_rmtree.called

@pytest.mark.asyncio
@patch('shutil.rmtree')
async def test_cmd_search_test_cleanup(mock_rmtree):
    context = MagicMock()
    plugin = WhaleChanMemePlugin(context, config={})
    plugin._c = MagicMock(return_value=True)

    event = MagicMock()
    event.get_message_str.return_value = "试搜图 明日方舟"

    plugin.pipeline = MagicMock()
    plugin.pipeline.search_refs.return_value = (["img1.jpg"], {"candidates": 1})

    plugin.client = MagicMock()
    plugin.client.resolve_llm = MagicMock(return_value={"ok": True})

    # Iterate generator
    async for _ in plugin.cmd_search_test(event):
        pass

    assert mock_rmtree.called
