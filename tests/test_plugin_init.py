import pytest

from plugin.main import WhaleChanMemePlugin


@pytest.fixture
def mock_context(mocker):
    return mocker.MagicMock()


def test_plugin_initialization(tmp_path, mock_context, mocker):
    # Prepare dummy paths using mock
    test_data_dir = tmp_path / "data"
    test_data_dir.mkdir()

    from unittest.mock import patch
    with patch("plugin.main.STATE_DIR", str(test_data_dir / "plugin_data")), \
            patch("plugin.main.SITE_CONF_PATH", str(test_data_dir / "plugin_data" / "site.json")), \
            patch("plugin.main.CONFIG_PATH", str(tmp_path / "cmd_config.json")):

        # Initialize plugin
        plugin = WhaleChanMemePlugin(mock_context, config={"test_conf": "val"})

        # Trigger path creation in plugin initialization via a method if it's not created by init directly
        plugin._save_state()  # Forces state dir creation
        # Run method to ensure paths created (tmp/outputs are usually created on run)

        # Check internal structures
        assert plugin.version is not None
        assert plugin.conf["test_conf"] == "val"

        # Ensure we check that the paths dictionary is pointing to the right place
        assert str(test_data_dir) in plugin.paths["state"]
        assert "tmp" in plugin.paths["tmp"]

        # Check client and pipeline are initialized
        assert plugin.client is not None
        assert plugin.pipeline is not None


def test_plugin_config_priority(tmp_path, mock_context, mocker):
    test_data_dir = tmp_path / "data"
    test_data_dir.mkdir()

    from unittest.mock import patch
    with patch("plugin.main.STATE_DIR", str(test_data_dir / "plugin_data")), \
            patch("plugin.main.SITE_CONF_PATH", str(test_data_dir / "plugin_data" / "site.json")), \
            patch("plugin.main.CONFIG_PATH", str(tmp_path / "cmd_config.json")):

        plugin = WhaleChanMemePlugin(mock_context, config={"test_key": "conf_value"})

        # Fallback to conf
        assert plugin._c("test_key") == "conf_value"

        # Override with SiteConfig (mock site file generation)
        plugin.site.update({"test_key": "site_value"})

        # SiteConfig should take priority over plugin.conf
        assert plugin._c("test_key") == "site_value"

        # Default value should be returned if not present
        assert plugin._c("non_existent", "default") == "default"
