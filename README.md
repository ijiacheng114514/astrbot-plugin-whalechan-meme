# 鲸鱼娘表情包生成（astrbot_plugin_whalechan_meme）

AstrBot 插件：把一句自然语言变成一张**固定主角**的 Q 版表情包。
主角是原创的「鲸鱼娘」Q 版形象——无论画面要求穿什么、做什么，形象锁保证她始终是她。

![示例](docs/img/sample.png)

> 示例：`/生图 明日方舟的斯卡蒂抱着鲸鱼玩偶发呆 # 摸鱼中`
> 插件自动考据斯卡蒂的服装要素 → 搜参考图 → 多模态核对 → 带身份卡生图 → 图上写字。

## 特性

- **两条连接分开管（v0.9）**：语言模型（考据/核对）**默认跟随 AstrBot 当前聊天模型**，零配置；
  也可以在面板改成自己的 URL + API Key。生图模型**必须在面板填 URL + API Key**
  （老版本靠 `provider_source_id` 读 AstrBot 凭据的方式仍作兜底）。
- **形象锁（反漂移）**：角色身份卡作为必选参考图；参考图硬闸门（短边 <400px / 过扁 / 超大一律剔除，
  因为生图接口会对小图**整单**报 400）；调用阶梯 `身份卡+素材 → 仅身份卡`，
  且默认**禁止**静默降级纯文生图（`allow_text_fallback=false`）——宁可不出图，不可画错人。
  如果生图接口不是百炼 / DashScope 系（不支持图生图），插件会**明确报「形象锁无法生效」**，
  而不是假装锁住了主角。
- **考据层**：低温 + JSON 模式的 LLM 先把描述考据成规范名（中/英/日）、视觉特征、多组搜图关键词；
  用户原话作为「最高优先级子句」回拼进最终提示词，永不截断。
- **搜图 + 核对层**：百度（Cookie 预热）→ 360 thumb → 必应兜底；搜到的图先经多模态模型逐张核对
  「是不是目标对象」，剔除跑题素材。核对模型不支持图片输入时自动跳过并告警。
- **控制台面板**：附着在 AstrBot 控制台（同地址端口）的七页签面板——
  概览 / **模型连接** / 运行日志 / 图库 / 设置 / 角色参考图 / 考据自测。
  面板改动写进 `plugin_data/<插件名>/site.json`（**不在插件目录里，升级不丢**），密钥只回显打码值。
- **token 记账**：每次运行的考据、核对、生图 token 与耗时写入 JSONL 日志，面板可查、可核算额度。
- **QQ 回复极简**：只发两条消息——接单回执 + 「图片 & 提示词解析」合并一条。

## 流水线

```
/生图 描述 # 图上文字
   │
   ├─ ⓪ 连接解析：LLM（跟随 AstrBot 或自定义）+ 生图（面板配置，缺则立刻失败不烧额度）
   ├─ ① 考据（LLM, 低温+JSON）→ 规范名/视觉特征/关键词/是否需素材
   ├─ ② 搜图（多图源, Cookie 预热）→ 候选下载 → 尺寸硬闸门
   ├─ ③ 核对（多模态模型, 256px 缩图）→ 剔除跑题素材
   ├─ ④ 提示词组装（角色 DNA + 考据特征 + 用户原话回拼 + 风格前缀）
   ├─ ⑤ 生图调用阶梯：身份卡+素材 → 仅身份卡 →（默认禁止）纯文生图
   │     非百炼系接口不支持图生图时：显式拦截并报「形象锁无法生效」
   └─ ⑥ 落盘 + JSONL 记账 → QQ 回「图片 + 解析」一条
```

## 安装

1. AstrBot ≥ 4.24（实测 v4.28.0）。把本仓库克隆/复制为
   `<AstrBot 数据目录>/plugins/astrbot_plugin_whalechan_meme/`
   （目录名必须等于插件名）。
2. 依赖：容器/主机内 Python 需有 `Pillow`（参考图校验与身份卡裁切用）。
3. 重启 AstrBot，控制台「插件页面」里即出现本面板。**首次打开会自动跳到「模型连接」页**。
4. 语言模型：默认「跟随 AstrBot 聊天模型」，**不用填任何东西**。
   想固定用别的模型/别家接口，就选「自定义 URL + Key」。
5. 生图模型：在「模型连接」页填**生图接口地址 + API Key + 模型名**，点「保存连接」，
   再点「测试两条连接」确认（生图只查 `/models`，**不消耗生图额度**）。
   - 阿里云百炼 token-plan：`https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
   - 普通百炼账号：`https://dashscope.aliyuncs.com/compatible-mode/v1`
   - 只有百炼 / DashScope 系支持图生图形象锁；别的 OpenAI 兼容生图接口只能纯文生图。
6. 角色素材：把三视图设定稿放 `plugin_data/astrbot_plugin_whalechan_meme/character_ref.jpg`，
   正面身份卡 `character_front.jpg` 可用面板「角色参考图」页在线裁切生成。

> 密钥与面板改动都存在 `plugin_data/astrbot_plugin_whalechan_meme/site.json`（权限 0600），
> 本仓库不含任何密钥，接口回显一律打码。
> 从 v0.8 升级：老的 `provider_source_id` 仍然生效（生图会用它兜底），不填新地址也能继续跑。

## 命令

| 命令 | 作用 |
|---|---|
| `/生图 <描述> [# 图上文字]` | 全流程出图（考据+搜图核对+身份卡）。`#` 后是要画在图上的字，可省 |
| `/快图 <描述> [# 图上文字]` | 跳过考据与搜图，直接带身份卡出图（省钱、快，但道具可能不准） |
| `/考据 <描述>` | 只看考据层怎么理解（排查"认错人"最直接，不出图不花生图额度） |
| `/试搜图 <词1｜词2>` | 单独测试搜图链路 |
| `/生图连接` | 打印两条连接的解析结果（密钥打码）与图生图是否可用 |
| `/生图额度` | 今日张数 / token 用量 / 预算 |

例：`/生图 明日方舟的斯卡蒂抱着鲸鱼玩偶发呆 # 摸鱼中`

## 配置要点

模型地址与 API Key 在控制台**「模型连接」**页，其余在**「设置」**页；两页都是保存即生效，
写进 `plugin_data/astrbot_plugin_whalechan_meme/site.json`。

| 键 | 默认 | 说明 |
|---|---|---|
| `llm_source` | astrbot | `astrbot`=跟随 AstrBot 聊天模型（零配置）；`custom`=用自己填的 URL+Key |
| `llm_base_url` / `llm_api_key` | 空 | 仅 `llm_source=custom` 时用 |
| `llm_model` | 空 | 留空=完全跟随；填了只覆盖模型名 |
| `gen_base_url` / `gen_api_key` | 空 | **生图连接**；留空则回落老的 `provider_source_id` |
| `model` / `size` | wan2.7-image / 1024*1024 | 生图模型名必须是你的生图接口上真实存在的 |
| `enhance_model` | 空 | 考据模型；**留空=跟随 LLM 连接** |
| `verify_model` | 空 | 素材核对模型；留空=跟随 LLM 连接，不支持图片输入时自动跳过 |
| `enhance_temperature` | 0.15 | 低温防擅自发挥 |
| `max_refs` / `search_refs` | 3 / 2 | 参考图张数上限——**token 的真正阀门** |
| `search_min_px` | 400 | 搜图候选短边下限（低于此值接口会整单 400） |
| `allow_text_fallback` | false | 是否允许无形象锁纯文生图（默认禁止） |
| `reply_detail` / `ack_text` | full / 收到，开始执行 | QQ 回复形态 |
| `character_dna` | （内置） | 角色设定文本，提示词里标注"禁止改动" |

## token 账（实测单次全流程 ≈24.5k）

下表是本站（百炼 token-plan）的实测值；模型名取决于你在面板里接的是什么。

| 环节 | 模型（示例） | 实测 |
|---|---|---|
| 考据优化 | deepseek-v4-pro | in 1.2k / out 0.6k |
| 素材核对 | qwen3.8-flash | in 0.7k / out 0.3k |
| 生图 | wan2.7-image | in ≈20k（每张参考图固定 ≈6.7~9.4k） |

省额度的三个阀门：`max_refs`（每张参考图 ≈9k 输入）、`search_refs`、`/快图`（跳过考据与搜图）。
面板「概览」页有当日张数、token、预算余量。

## 开发

- `tools/selftest.py`：容器内端到端自测（不依赖 AstrBot 运行时），分 10 个阶段可单独跑，
  含参考图硬闸门反例测试。`--stages conf,conn --test-conn` 只花几十 token 就能验两条连接
  （生图侧只 GET `/models`，不出图）。
- `tools/make_preview.py`：本地生成面板预览（stub 桥 + 假数据），浏览器目检 UI；
  stub 故意注入在 app.js 之后以复现真控制台的脚本时序，并内置一个迷你后端
  （保存连接 → 状态卡/概览/自测结果会跟着变），能真跑「配置→生效」这条链。
  `WM_PREVIEW_FRESH=1` 生成全新安装场景（生图未配置，面板自动跳到「模型连接」页）。
- `tools/deploy.py`：备份→替换→重启→轮询验收→失败自动回滚 的部署脚本；
  版本号从 `plugin/main.py` 的 `PLUGIN_VERSION` 读，不在脚本里写死；
  站点私有值放 `tools/deploy_home.env`（见 `deploy_home.env.example`，不入库）。
- 架构与坑位详见 [docs/DESIGN.md](docs/DESIGN.md)，部署详见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 许可证

MIT（含 `assets/` 与 `docs/img/` 内的美术素材）。
