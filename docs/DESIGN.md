# 设计说明（v0.8.x）

## 模块划分

```
plugin/
├── main.py            AstrBot 入口：命令注册、QQ 回复形态、面板路由注册、executor 包装同步流水线
├── metadata.yaml      插件元数据（name 决定面板路由前缀，勿改）
├── _conf_schema.json  配置 schema（面板「设置」写回这里的 default）
├── core/
│   ├── prompts.py     所有提示词与角色 DNA；PLUGIN_NAME / LOG_TAG 常量
│   ├── client.py      百炼 token-plan 客户端：chat / 多模态核对 / 生图调用阶梯 / Usage 记账
│   ├── imaging.py     参考图硬闸门 check_ref / 规范化 / 身份卡裁切 / base64
│   ├── search.py      多图源搜图 + Cookie 预热 + 候选下载
│   ├── pipeline.py    考据→搜图→核对→组装→生图→落盘→记账 的总编排
│   ├── journal.py     JSONL 运行日志与 token 统计（线程安全 + 轮转）
│   └── page_api.py    控制台面板后端路由（全部阻塞操作走 asyncio.to_thread）
└── pages/console/     面板前端（原生 JS，无构建；index.html / app.js / styles.css）
```

## 形象锁：为什么这样修"主角漂移"

v0.7 的漂移**不是提示词问题**：百炼生图接口对短边 <~300px 的参考图返回
400 InvalidParameter "Error validating image"，且是**整单**失败；
v0.7 在该错误后静默回退纯文生图 ⇒ 形象锁丢失 ⇒ 模型自己编主角。

v0.8 的三层防御：

1. **入参硬闸门** `imaging.check_ref`：短边 <400 / 长边 >4096 / 长宽比 >2.2 / >8MB /
   非 JPEG·PNG 一律剔除并记录原因（比实测下限 300 留余量）。
2. **调用阶梯** `client.generate`：`身份卡+素材 → 仅身份卡`；
   `allow_text_fallback=false` 且无合格参考图时返回 `blocked/no_valid_ref`，
   **绝不静默出图**。
3. **提示词纪律**：考据低温 0.15 + JSON 模式；用户原话作为「最高优先级子句」回拼且永不截断；
   角色 DNA 标注"本次与以后每次生图都必须严格遵守，禁止改动"。

## token 经济学

- 每张参考图的输入 token 近似**固定** 6.7k~9.4k（与图内容无关，与分辨率档有关）。
- 因此 `max_refs`（生图最多喂几张）与 `search_refs`（搜图保留几张）是额度阀门；
  核对层用 256px 缩图（384px 实测慢 5 倍且判断质量无增益）。
- 每次运行的 in/out/images/ms 全量记入 JSONL，面板「运行日志/概览」直接核算。

## 面板后端契约

- 路由前缀 = `/{metadata.name}/page`，即
  `/api/v1/plugins/extensions/astrbot_plugin_whalechan_meme/page/*`。
  **前缀写错就全 404**（dashboard 按 `/` + plugin_path 精确匹配注册的 route）。
- 响应信封 `{"status":"ok"|"error","message":...,"data":...}`，原样透传不被包装。
- 上传走 `bridge.upload("page/ref/upload", file)`；阻塞操作（PIL/网络/JSONL）一律
  `asyncio.to_thread`，避免卡 dashboard 事件循环。

## 面板前端：桥时序坑（必读）

dashboard 把 `bridge-sdk.js` 注入到 `</body>` 前一刻，**晚于页面自己的 app.js** 执行。
因此 app.js 同步读 `window.AstrBotPluginPage` 必为 `undefined`，
会误显示"必须嵌在控制台打开"的红横幅且数据全空（2026-10-01 首开踩过）。
正确做法：`waitBridge()` 轮询（25ms 间隔、10s 超时）等桥出现后再 boot；
本地预览的 stub 也注入在 app.js 之后以复现该时序。

## 日志与记账

- `<plugin_data>/logs/runs.jsonl`：每运行一条，含考据/搜图/核对/生图阶梯/成品路径/解析文案。
- 单文件 >2MB 轮转为 `.1`；面板读取时合并排序。
- `journal.stats()` 提供"今日"口径的 gens/ok/fail/tokens/images/avg_ms。
