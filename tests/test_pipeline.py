import os


def test_pipeline_enhance_success(pipeline, mocker):
    # Already configured with mock_client in conftest which returns a chat success
    # However we need the mock to return a JSON to simulate LLM structure
    mock_chat = mocker.patch.object(pipeline.client, "chat")
    usage = mocker.MagicMock()
    usage.in_tok = 10
    usage.out_tok = 10
    usage.as_dict = lambda: {"in": 10, "out": 10}
    mock_chat.return_value = (
        '{"prompt": "final prompt", "needs_asset": false}',
        usage,
        {"status": "ok", "ms": 10}
    )

    plan, rec = pipeline.enhance("test scene", "", {"ok": True, "model": "test"})
    assert plan is not None
    assert plan["prompt"] == "final prompt"
    assert rec["status"] == "ok"


def test_pipeline_enhance_bad_json(pipeline, mocker):
    mock_chat = mocker.patch.object(pipeline.client, "chat")
    usage = mocker.MagicMock()
    usage.in_tok = 10
    usage.out_tok = 10
    usage.as_dict = lambda: {"in": 10, "out": 10}
    mock_chat.return_value = (
        'bad response',
        usage,
        {"status": "ok", "ms": 10}
    )

    plan, rec = pipeline.enhance("test scene", "", {"ok": True, "model": "test"})
    assert plan is None
    assert rec["status"] == "bad_json"


def test_pipeline_run_success(pipeline, mocker):
    # Mock enhance to return a valid plan
    pipeline.enhance = mocker.MagicMock(return_value=({"prompt": "generated prompt"}, {
                                        "status": "ok", "in": 10, "out": 10, "ms": 10}))

    # Run pipeline
    res = pipeline.run("test scene", "test caption", enhanced=True)

    # Assert successful run based on mocked image data from mock_client in conftest
    assert res["img"] == b"fake_image_data"
    assert res["rec"]["status"] == "ok"

    # Assert outputs are written
    out_dir = pipeline.p["outputs"]
    written_files = os.listdir(out_dir)
    assert len(written_files) == 1
    assert written_files[0].endswith(".png")


def test_pipeline_run_gen_fail(pipeline, mocker):
    # Mock enhance to return a valid plan
    pipeline.enhance = mocker.MagicMock(return_value=({"prompt": "generated prompt"}, {
                                        "status": "ok", "in": 10, "out": 10, "ms": 10}))

    # Change client to fail generation
    pipeline.client.generate = mocker.MagicMock(return_value=(
        None, [{"status": "no_valid_ref", "error": "test error"}]))

    # Run pipeline
    res = pipeline.run("test scene", "test caption", enhanced=True)

    # Assert failed run
    assert res["img"] is None
    assert res["rec"]["status"] == "failed"
    assert "test error" in res["rec"]["error"]
