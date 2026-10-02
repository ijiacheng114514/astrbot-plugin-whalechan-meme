import pytest
import os
import json
from plugin.core.siteconf import SiteConfig

def test_site_config_load_and_get(tmp_path):
    conf_file = tmp_path / "site.json"
    conf_data = {"test_key": "test_value", "int_key": 42}
    conf_file.write_text(json.dumps(conf_data))

    site_conf = SiteConfig(str(conf_file))

    assert site_conf.get("test_key") == "test_value"
    assert site_conf.get("int_key") == 42
    assert site_conf.get("missing_key", "default_value") == "default_value"

def test_site_config_save_and_update(tmp_path):
    conf_file = tmp_path / "site.json"

    # Initialize missing file
    site_conf = SiteConfig(str(conf_file))
    assert site_conf.get("key") is None

    # Update value
    site_conf.update({"key": "new_value"})
    assert site_conf.get("key") == "new_value"

    # Verify file content
    saved_data = json.loads(conf_file.read_text())
    assert saved_data["key"] == "new_value"

def test_site_config_invalid_json(tmp_path):
    conf_file = tmp_path / "site.json"
    conf_file.write_text("{invalid json")

    # Should not crash, should return empty dict internally
    site_conf = SiteConfig(str(conf_file))
    assert site_conf.get("any_key", "default") == "default"

def test_site_config_permission_error(tmp_path):
    conf_file = tmp_path / "site.json"
    conf_file.write_text('{"key": "value"}')

    # Simulate a read error
    with pytest.MonkeyPatch.context() as m:
        def mock_open(*args, **kwargs):
            raise PermissionError("Access denied")
        m.setattr("builtins.open", mock_open)

        site_conf = SiteConfig(str(conf_file))
        assert site_conf.get("key") is None
