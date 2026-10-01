# 鲸鱼娘表情包生成（astrbot_plugin_whalechan_meme）

AstrBot 插件：把一句自然语言变成一张**固定主角**的 Q 版表情包。
主角是原创的「鲸鱼娘」Q 版形象——无论画面要求穿什么、做什么，形象锁保证她始终是她。

![示例](docs/img/sample.png)

> 示例：`/生图 明日方舟的斯卡蒂抱着鲸鱼玩偶发呆｜摸鱼中`
> 插件自动考据斯卡蒂的服装要素 → 搜参考图 → 多模态核对 → 带身份卡生图 → 图上写字。

## 特性

- **形象锁（反漂移）**：角色身份卡作为必选参考图；参考图硬闸门（短边 <400px / 过扁 / 超大一律剔除，
  因为生图接口会对小图**整单**报 400）；调用阶梯 `身份卡+素材 → 仅身份卡`，
  且默认**禁止**静默降级纯文生图（`allow_text_fallback=false`）——宁可不出图，不可画错人。
- **考据层**：低温 + JSON 模式的 LLM 先把描述考据成规范名（中/英/日）、视觉特征、多组搜图关键词；
  用户原话作为「最高优先级子句」回拼进最终提示词，永不截断。
- **搜图 + 核对层**：百度（Cookie 预热）→ 360 thumb → 必应兜底；搜到的图先经多模态模型逐张核对
  「是不是目标对象」，剔除跑题素材。
- **控制台面板**：附着在 AstrBot 控制台（同地址端口）的六页签面板——
  概览 / 运行日志 / 图库 / 设置 / 角色参考图 / 考据自测；设置保存即生效并写回 schema。
- **token 记账**：每次运行的考据、核对、生图 token 与耗时写入 JSONL 日志，面板可查、可核算额度。
- **QQ 回复极简**：只发两条消息——接单回执 + 「图片 & 提示词解析」合并一条。

## 流水线

```
/生图 描述｜图上文字
   │
   ├─ ① 考据（LLM, 低温+JSON）→ 规范名/视觉特征/关键词/是否需素材
   ├─ ② 搜图（多图源, Cookie 预热）→ 候选下载 → 尺寸硬闸门
   ├─ ③ 核对（多模态模型, 256px 缩图）→ 剔除跑题素材
   ├─ ④ 提示词组装（角色 DNA + 考据特征 + 用户原话回拼 + 风格前缀）
   ├─ ⑤ 生图调用阶梯：身份卡+素材 → 仅身份卡 →（默认禁止）纯文生图
   └─ ⑥ 落盘 + JSONL 记账 → QQ 回「图片 + 解析」一条
```

## 安装

1. AstrBot ≥ 4.24（实测 v4.28.0）。把本仓库克隆/复制为
   `<AstrBot 数据目录>/plugins/astrbot_plugin_whalechan_meme/`
   （目录名必须等于插件名）。
2. 依赖：容器/主机内 Python 需有 `Pillow`（参考图校验与身份卡裁切用）。
3. 凭据：插件从 AstrBot 的 `cmd_config.json` 里读 `provider_sources`（百炼 token-plan 网关），
   不在本仓库存任何密钥。
4. 角色素材：把三视图设定稿放 `plugin_data/astrbot_plugin_whalechan_meme/character_ref.jpg`，
   正面身份卡 `character_front.jpg` 可用面板「角色参考图」页在线裁切生成。
5. 重启 AstrBot，控制台「插件页面」里即出现本面板。

## 命令

| 命令 | 作用 |
|---|---|
| `/生图 <描述>｜<图上文字>` | 出图；`｜` 后为要画在图上的字（可选） |
| `/考据 <描述>` | 只看考据层怎么理解（排查"认错人"最直接，不出图不花钱生图） |
| `/试搜图 <词1｜词2>` | 单独测试搜图链路 |

## 配置要点（控制台「设置」页可改）

| 键 | 默认 | 说明 |
|---|---|---|
| `model` | wan2.7-image | 生图模型 |
| `enhance_model` / `enhance_temperature` | deepseek-v4-pro / 0.15 | 考据模型与温度（低温防擅自发挥） |
| `verify_model` | qwen3.8-max | 素材核对模型 |
| `max_refs` / `search_refs` | 3 / 2 | 参考图张数上限——**token 的真正阀门** |
| `search_min_px` | 400 | 搜图候选短边下限（低于此值接口会整单 400） |
| `allow_text_fallback` | false | 是否允许无形象锁纯文生图（默认禁止） |
| `reply_detail` / `ack_text` | full / 收到，开始执行 | QQ 回复形态 |
| `character_dna` | （内置） | 角色设定文本，提示词里标注"禁止改动" |

## token 账（实测单次全流程 ≈24.5k）

| 环节 | 模型 | 实测 |
|---|---|---|
| 考据优化 | deepseek-v4-pro | in 1.2k / out 0.6k |
| 素材核对 | qwen3.8-max | in 0.7k / out 0.8k |
| 生图 | wan2.7-image | in ≈20k（每张参考图固定 ≈6.7~9.4k） |

## 开发

- `tools/selftest.py`：容器内端到端自测（不依赖 AstrBot 运行时），含硬闸门反例测试。
- `tools/make_preview.py`：本地生成面板预览（stub 桥 + 假数据），浏览器目检 UI；
  stub 故意注入在 app.js 之后以复现真控制台的脚本时序。
- `tools/deploy.py`：备份→替换→重启→轮询验收→失败自动回滚 的部署脚本；
  站点私有值放 `tools/deploy_home.env`（见 `deploy_home.env.example`，不入库）。
- 架构与坑位详见 [docs/DESIGN.md](docs/DESIGN.md)，部署详见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 许可证

MIT（含 `assets/` 与 `docs/img/` 内的美术素材）。
