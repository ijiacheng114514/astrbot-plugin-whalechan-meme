# 测试工程化报告：WhaleChan Meme Plugin

## 1. 添加了哪些测试

为了建立长期可维护的 `pytest` 测试体系，我们在项目中重构和建立了标准的 `tests/` 目录结构，并新增了 17 个测试用例，全部分布在以下模块中：

*   **`tests/conftest.py`**：引入了统一的测试 Fixtures（包含路径 Mock，配置 Mock，Client 和 Pipeline Mock）。
*   **`tests/test_plugin_init.py`**：测试 `WhaleChanMemePlugin` 的加载初始化逻辑。
*   **`tests/test_config.py`**：测试配置模块 `SiteConfig`。
*   **`tests/test_client.py`**：测试网络请求与 LLM / Image 生图客户端的处理逻辑。
*   **`tests/test_pipeline.py`**：测试大模型工作流和生图流程逻辑。
*   **`tests/test_cleanup.py`**：重构并新增测试清理临时文件的任务逻辑。

## 2. 覆盖什么功能

该测试体系现已完全实现了不依赖真实 API 的外部服务打桩（Mock），覆盖了以下核心逻辑：

1.  **插件初始化**：测试了配置优先级判断以及数据依赖文件路径的正确创建。
2.  **配置读取**：测试了自定义站点配置覆盖，以及配置无效或加载失败情况的兜底机制。
3.  **LLM调用失败处理**：通过 Mock `http_json` 网络服务，测试了当服务端报 500、连接被拒绝以及无配置凭据情况下的容错及状态机捕获处理。
4.  **图片生成流程**：独立测试了 `Pipeline.enhance` 的考据推理正常、错误返回状态。同时验证了在 `Pipeline.run` 发生模拟生成错误或成功时，业务状态能否正确流转与数据记录能否落盘。
5.  **网络异常处理**：涵盖模型和图像下载过程中抛出连接和超时错误的测试。
6.  **临时文件清理**：确保插件能够在正常流转结束或是中途由于代码和网络异常报错中断后，依旧触发并确保 `shutil.rmtree` 针对临时文件的安全清理。

## 3. 如何使用

### 安装环境依赖

确保安装最新的 `pytest` 套件及异步运行依赖：
```bash
pip install pytest pytest-mock pytest-asyncio
```

### 运行测试

所有测试设计为独立可运行。为了防止环境根目录加载失败，建议带上路径参数运行全部：
```bash
python -m pytest tests/
```

或者针对某个特定的逻辑层单独排查：
```bash
python -m pytest tests/test_cleanup.py
```