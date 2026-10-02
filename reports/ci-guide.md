# GitHub Actions CI 指南

本项目现已集成 GitHub Actions 以自动化代码测试和代码规范检查，保障项目质量与稳定性。

## CI 触发条件

自动化的 CI 测试会在以下情况被触发：
- 代码推送到任意分支 (`push`)。
- 提交 Pull Request (`pull_request`) 时。

## CI 检查流程

CI 在 `ubuntu-latest` 环境上运行，并采用 `matrix` 策略支持多个 Python 环境同时进行测试：
- Python 3.10
- Python 3.11
- Python 3.12

在每个 Python 版本环境下，CI 将按顺序执行以下步骤：
1. **安装依赖**：安装 AstrBot 及插件的运行必需依赖 (`Pillow`, `requests`, `pydantic`)。
2. **安装测试依赖**：安装必要的测试和代码检查工具 (`pytest`, `pytest-mock`, `pytest-asyncio`, `flake8`, `mypy`)。
3. **执行 `pytest`**：运行所有单元测试，确保代码逻辑的正确性（独立运行、不依赖真实 API 环境）。
4. **执行 `flake8`**：检查 Python 源码 (`plugin/` 和 `tests/` 目录) 是否符合 PEP 8 风格规范。
5. **执行 `mypy`**：进行静态类型检查，确保所有的类型注解能够推导和验证通过。

## 阻止合并机制

- 若在执行的任意一个环境或检查步骤中发生失败，整个 CI 流水线状态将被标记为失败 (Failed)。
- 默认情况下，如果 CI 测试未全部通过，将阻止对应 Pull Request 的合并。这是为了确保问题代码不会混入主分支 `main`。
- 你可以点击 GitHub 页面 PR 区域中的“Details”按钮，查看完整的构建日志，通过日志输出定位失败的具体原因（如测试未通过、类型错误或是规范不符），并在本地进行修复和提交，CI 会随着每次新提交重新运行。

## 本地重现测试

建议在提交代码或 Pull Request 之前，开发者能在本地环境进行相应的检查。你可以在开发环境根目录下运行以下命令，与 CI 的操作保持一致：
```bash
# 安装测试依赖
pip install pytest pytest-mock pytest-asyncio flake8 mypy

# 执行 pytest
python -m pytest tests/

# 执行 flake8 检查
flake8 plugin tests

# 执行 mypy 类型检查
mypy plugin tests
```
在这些步骤都能顺利通过后，再行推送至代码库。