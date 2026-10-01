# 部署与回滚

## 目标形态

插件目录 = `<AstrBot 数据目录>/plugins/astrbot_plugin_whalechan_meme/`。
容器部署时该目录通常是宿主机某路径 bind-mount 进容器的 `/AstrBot/data/plugins/...`。

## 手工部署（任何环境）

1. 备份现目录：`tar -czf whalechan.bak-$(date +%s).tar.gz -C <plugins> astrbot_plugin_whalechan_meme`
2. 用本仓库 `plugin/` 的内容**整体替换**插件目录（先删干净，避免残留旧文件被加载）。
3. 重启 AstrBot（`docker compose restart astrbot` 或等价操作）。
4. 验收（见下）。

## 脚本部署（本机 → 宿主机 → LXC → 容器）

`tools/deploy.py` 把上面四步串成一条命令，并带**失败自动回滚**：

```bash
python tools/deploy.py             # 真部署
python tools/deploy.py --dry-run   # 只打包 + 打印将执行的命令
python tools/deploy.py --rollback  # 用最近一次备份回滚
```

站点私有值从环境变量或 `tools/deploy_home.env` 读（KEY=VALUE，**不入库**），
模板见 `tools/deploy_home.env.example`：

| 变量 | 含义 |
|---|---|
| `WM_PVESSH` | 操作员自有的 ssh 包装脚本路径（不随本仓库分发） |
| `WM_LXC_ID` | LXC 容器编号 |
| `WM_LXC_PLUGINS` | 宿主机侧插件目录（bind-mount 进容器的那份） |
| `WM_LXC_BACKUPS` | 备份 tar.gz 存放目录 |
| `WM_COMPOSE` | botstack 的 compose 文件 |
| `WM_DASH_URL` | dashboard 地址（默认 `http://127.0.0.1:6185`） |

## 验收判据

`docker logs astrbot` 中：

- 出现 `v<PLUGIN_VERSION> 初始化完成` 与 `控制台面板路由已注册` 两行
  （版本号由脚本从 `plugin/main.py` 的 `PLUGIN_VERSION` 读，**不在脚本里写死**）；
- 无 `missing dependencies`、无 `Traceback`；
- dashboard 健康检查返回 200。

⚠️ 两个高频坑：

1. **验收必须轮询等启动完成**（约 30~60s）。固定 sleep 会在日志尚未写出时误判并触发回滚。
2. **dashboard 端口可能只发布在某个具体 IP 上、没有 loopback**：
   在容器/LXC 内 `curl 127.0.0.1:<port>` 会返回 000 而造成误判；
   健康检查地址要用实际发布地址（`WM_DASH_URL`）。
3. 未登录时 `/api/v1/...` 与面板内容路由一律 401（鉴权中间件先行），
   **401 不能当作路由存在的验收判据**。

## 升级不丢配置

面板改过的配置（含生图 URL / API Key）落在
`plugin_data/astrbot_plugin_whalechan_meme/site.json`（权限 0600），**不在插件目录里**。
所以"整目录替换"式部署不会抹掉用户配置；回滚也只回滚插件代码，不动站点配置。
从 v0.8 升级：没填 `gen_base_url`/`gen_api_key` 时生图自动回落老的 `provider_source_id`，
**升级后不用重新配任何东西**。

## 容器内自测（不经过 QQ）

```bash
# 只验两条连接（几十 token，不出图）
docker exec astrbot python3 /AstrBot/data/wm-selftest/selftest.py \
    --plugin /AstrBot/data/wm-selftest/plugin --stages conf,conn --test-conn

# 全流程（真实出图，精度优先档约 18~25k token/次）
docker exec astrbot python3 /AstrBot/data/wm-selftest/selftest.py \
    --plugin /AstrBot/data/wm-selftest/plugin --state /tmp/wm-selftest \
    --stages conf,conn,imaging,journal,enhance,guard,search,full
```

分阶段跑：配置 / 连接解析 / 硬闸门（含 300×120 反例）/ journal / 模型列表 / 考据 /
守卫 / 搜图 / 生图 / 全流程。`--site <path>` 可叠加面板保存的站点配置（只读，绝不写回）。
全流程会真实消耗 token，按需只跑前置阶段；`--test-conn` 的生图侧只 GET `/models`，不烧出图额度。
