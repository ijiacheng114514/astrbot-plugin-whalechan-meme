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

- 出现 `v0.8.x 初始化完成` 与 `控制台面板路由已注册` 两行；
- 无 `missing dependencies`、无 `Traceback`；
- dashboard 健康检查返回 200。

⚠️ 两个高频坑：

1. **验收必须轮询等启动完成**（约 30~60s）。固定 sleep 会在日志尚未写出时误判并触发回滚。
2. **dashboard 端口可能只发布在某个具体 IP 上、没有 loopback**：
   在容器/LXC 内 `curl 127.0.0.1:<port>` 会返回 000 而造成误判；
   健康检查地址要用实际发布地址（`WM_DASH_URL`）。
3. 未登录时 `/api/v1/...` 与面板内容路由一律 401（鉴权中间件先行），
   **401 不能当作路由存在的验收判据**。

## 容器内自测（不经过 QQ）

```bash
docker exec astrbot python3 /AstrBot/data/wm-selftest/selftest.py
```

分阶段跑：配置 / 硬闸门（含 300×120 反例）/ journal / 模型列表 / 考据 / 守卫 / 搜图 / 生图 / 全流程。
全流程会真实消耗 token（精度优先档约 24.5k/次），按需只跑前置阶段。
