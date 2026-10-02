# WhaleChan Meme Plugin Tests

该目录包含了 WhaleChan Meme 插件的所有独立单元测试，旨在建立一个长期可维护的测试体系。

## 如何运行测试

测试完全独立于真实的 API 环境。你可以在任何包含依赖的 Python 环境中直接运行，无需连接互联网或填写真实的 API 密钥。

```bash
# 安装测试依赖
pip install pytest pytest-mock pytest-asyncio

# 运行所有测试
python -m pytest tests/

# 运行特定的测试文件
python -m pytest tests/test_pipeline.py
```

## 测试覆盖范围

我们的测试完全通过 `pytest-mock` 对外部调用和环境进行打桩(Mock)，实现了以下范围的覆盖：

1. **插件初始化 (`test_plugin_init.py`)**：确保 `WhaleChanMemePlugin` 在初始化时可以正确构建文件目录、解析优先级配置，并注入下层 Client 与 Pipeline。
2. **配置读取 (`test_config.py`)**：覆盖了 `SiteConfig` 独立读取与回写的逻辑，涵盖空文件、错误文件读取等边界情况。
3. **LLM与API异常处理 (`test_client.py`)**：覆盖了 `BailianClient` 中 HTTP 层 500 错误和网络连通异常带来的失败处理场景。
4. **图片生成流程 (`test_pipeline.py`)**：测试了 Pipeline 从 `enhance`（调用大模型进行关键词和考据分析）到 `run`（发起图片生成，并写入结果）的整套逻辑。
5. **临时文件清理 (`test_cleanup.py`)**：测试了正常运行结束、运行过程抛出异常以及“搜图测试”功能中对于残余临时文件的强制清理。

## 新增测试方法

1. **命名规范**：新的测试文件必须以 `test_` 开头。
2. **复用 Fixture**：在编写新测试时，如果有对配置、路径或是客户端的共同需求，请直接通过函数的参数引用定义在 `conftest.py` 中的 fixture（如 `mock_paths`, `mock_client`, `pipeline`）。
3. **保持独立性**：严格禁止在测试中调用真实的接口服务，所有涉及 `client.chat`, `client.generate` 和 `http_json` 的网络调用必须被 `patch` 拦截。