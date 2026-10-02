import pytest
import os

from plugin.core.client import BailianClient
from plugin.core.pipeline import Pipeline
from plugin.core.journal import Journal
from plugin.core.siteconf import SiteConfig

@pytest.fixture
def mock_paths(tmp_path):
    """Provide standard mocked paths for testing."""
    tmp_tmp = tmp_path / "tmp"
    tmp_outputs = tmp_path / "outputs"
    tmp_state = tmp_path / "state"

    tmp_tmp.mkdir(exist_ok=True)
    tmp_outputs.mkdir(exist_ok=True)
    tmp_state.mkdir(exist_ok=True)

    return {
        "state": str(tmp_state),
        "tmp": str(tmp_tmp),
        "outputs": str(tmp_outputs),
        "logs": str(tmp_path / "logs"),
        "ref_default": str(tmp_state / "character_front.jpg"),
        "sheet": str(tmp_state / "character_ref.jpg"),
    }

@pytest.fixture
def mock_conf():
    """Returns a mock configuration getter function."""
    config_data = {
        "keep_assets": False,
        "enhance_model": "test_model",
        "model": "test_gen_model",
        "enhance_enabled": True,
        "allow_text_fallback": True,
        "use_reference": False
    }
    return lambda key, default=None: config_data.get(key, default)

@pytest.fixture
def mock_client(mocker):
    """Returns a mocked BailianClient."""
    client = mocker.MagicMock(spec=BailianClient)
    client.resolve_llm = mocker.MagicMock(return_value={"ok": True, "label": "llm", "model": "test_model"})
    client.resolve_gen = mocker.MagicMock(return_value={"ok": True, "label": "gen", "model": "test_gen_model", "dialect": "openai"})
    usage = mocker.MagicMock()
    usage.in_tok = 10
    usage.out_tok = 10
    usage.as_dict = lambda: {"in": 10, "out": 10}
    client.chat = mocker.MagicMock(return_value=("{}", usage, {"status": "ok", "ms": 10}))
    client.generate = mocker.MagicMock(return_value=(b"fake_image_data", [{"status": "ok"}]))
    return client

@pytest.fixture
def pipeline(mocker, mock_conf, mock_client, mock_paths):
    """Returns a Pipeline configured with mocks."""
    journal_mock = mocker.MagicMock(spec=Journal)
    journal_mock.new_id.return_value = "123"

    p = Pipeline(mock_conf, mock_client, journal_mock, mock_paths, log=lambda lvl, msg: None)
    return p
