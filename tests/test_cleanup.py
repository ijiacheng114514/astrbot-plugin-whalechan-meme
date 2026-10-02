import pytest
import os
import shutil

from plugin.main import WhaleChanMemePlugin

def test_pipeline_run_cleanup_success(pipeline, mocker):
    mock_rmtree = mocker.patch("plugin.core.pipeline.shutil.rmtree")

    pipeline.enhance = mocker.MagicMock(return_value=({"prompt": "test prompt", "needs_asset": False}, {"status": "ok"}))
    pipeline.client.generate = mocker.MagicMock(return_value=(b"fake image data", [{"status": "success"}]))

    # Conf keep_assets is false by default in our fixture
    pipeline.run("scene", "caption", True)

    # Assert rmtree was called with the tmpdir created
    assert mock_rmtree.called

def test_pipeline_run_cleanup_exception(pipeline, mocker):
    mock_rmtree = mocker.patch("plugin.core.pipeline.shutil.rmtree")

    # Simulate an unexpected exception in _run_impl
    pipeline._run_impl = mocker.MagicMock(side_effect=Exception("Unexpected Error"))

    with pytest.raises(Exception):
        pipeline.run("scene", "caption", True)

    # Assert rmtree was still called despite exception
    assert mock_rmtree.called

@pytest.mark.asyncio
async def test_cmd_search_test_cleanup(mocker, tmp_path):
    mock_rmtree = mocker.patch("plugin.main.shutil.rmtree")

    context = mocker.MagicMock()

    test_data_dir = tmp_path / "data"
    test_data_dir.mkdir()

    from unittest.mock import patch
    with patch("plugin.main.STATE_DIR", str(test_data_dir / "plugin_data")), \
         patch("plugin.main.SITE_CONF_PATH", str(test_data_dir / "plugin_data" / "site.json")), \
         patch("plugin.main.CONFIG_PATH", str(tmp_path / "cmd_config.json")):

        plugin = WhaleChanMemePlugin(context, config={})
        plugin._c = mocker.MagicMock(return_value=True)

        event = mocker.MagicMock()
        event.get_message_str.return_value = "试搜图 明日方舟"

        plugin.pipeline = mocker.MagicMock()
        plugin.pipeline.search_refs.return_value = (["img1.jpg"], {"candidates": 1})

        plugin.client = mocker.MagicMock()
        plugin.client.resolve_llm = mocker.MagicMock(return_value={"ok": True})

        # Iterate generator
        async for _ in plugin.cmd_search_test(event):
            pass

        assert mock_rmtree.called
