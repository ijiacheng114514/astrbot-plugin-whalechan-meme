# BUG-001 修复报告 (临时文件清理)

## 1. 发现的问题回顾
根据在回归测试阶段的反馈（报告参见 `reports/runtime-compatibility-report.md` 中的 BUG-001）：
临时目录 `tmpdir` 在部分流程（`/试搜图` 流程 `cmd_search_test`，以及 `Pipeline.run` 正常或异常报错中止时）结束后没有被可靠清理。
如果发生大批量请求，可能导致僵尸临时文件占用硬盘空间。

## 2. 修改文件
*   `plugin/main.py`
*   `plugin/core/pipeline.py`

## 3. 修改原因
部分提前 `return` 或报错抛出异常的路径跳过了原本写在方法结尾的清理流程，或在如 `cmd_search_test` 里完全遗漏了清理步骤。需要一种可靠的结构来保证任何返回或崩溃情况下的资源释放。

## 4. 修改方式
*   对于 `plugin/main.py` 的 `cmd_search_test` 方法：
    使用 `try...finally` 块包裹请求逻辑，最后强制执行 `shutil.rmtree(tmpdir, ignore_errors=True)`。
*   对于 `plugin/core/pipeline.py` 的 `run` 方法：
    将原流程逻辑抽离到了一个私有帮助方法 `_run_impl` 中，并在 `run` 方法中使用 `try...finally` 进行封装包装，当由于 `keep_assets` 为 `False` 时进行确保调用了原先的 `shutil.rmtree`，成功保证无论网络错误还是正常退出都能按预期执行。

## 5. 测试结果
针对两处修改逻辑，引入了测试脚本 `tests/test_cleanup.py`，增加了三个通过 `patch` 对 `shutil.rmtree` 监控的 Mock 测试。
*   `test_pipeline_run_cleanup_success`: 验证在 `run` 正常走完后清理是否执行。
*   `test_pipeline_run_cleanup_exception`: 验证在中间模拟出意外异常终止时，临时目录清理能否执行。
*   `test_cmd_search_test_cleanup`: 验证使用异步协程的 `cmd_search_test` 调用完成后，临时目录清理是否执行。

测试均已 **PASS**，BUG 成功修复，并且不改变原来的搜图及业务图片生成逻辑（功能无影响）。
