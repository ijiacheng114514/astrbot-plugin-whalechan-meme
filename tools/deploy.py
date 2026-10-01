# -*- coding: utf-8 -*-
"""v0.8.x 部署脚本（在本机跑，通过操作员自有的 ssh 包装脚本串起 宿主机 → LXC → astrbot 容器）。

站点私有值（ssh 包装脚本路径、LXC 编号、容器数据目录、compose 文件、dashboard 地址）
一律从环境变量读，或放在同目录 `deploy_home.env`（KEY=VALUE，**不入库**）。
仓库里的默认值只是占位示例。

流程：
  1. 打包 plugin/（排除 baseline / __pycache__）
  2. 上传到宿主机暂存目录
  3. LXC 内备份现插件目录 -> <backups>/<ts>.tar.gz
  4. 替换插件目录
  5. docker compose restart astrbot
  6. 验收：日志里出现 v0.8 加载、面板路由注册、无 missing dependencies；dashboard 健康
  7. 验收失败自动回滚（还原旧目录 + 再重启）

用法：
  python tools/deploy.py            # 真部署
  python tools/deploy.py --dry-run  # 只打包和打印将执行的命令
  python tools/deploy.py --rollback # 用最近一次备份回滚
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_SRC = os.path.join(ROOT, "plugin")
PYTHON = sys.executable


def _load_env_file():
    """站点私有值放 tools/deploy_home.env（KEY=VALUE，已在 .gitignore 里，不入库）。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deploy_home.env")
    if not os.path.isfile(p):
        return
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env_file()

# 站点相关全部走环境变量（公开仓库不带任何内网信息）。
# 真部署前必须提供：WM_PVESSH / WM_LXC_ID / WM_LXC_PLUGINS / WM_LXC_BACKUPS / WM_COMPOSE；
# 建议写在同目录 deploy_home.env（不入库）。WM_DASH_URL 默认本机回环。
PVESSH = os.environ.get("WM_PVESSH", "")
LXC_ID = os.environ.get("WM_LXC_ID", "")
LXC_PLUGINS = os.environ.get("WM_LXC_PLUGINS", "")
LXC_BACKUPS = os.environ.get("WM_LXC_BACKUPS", "")
COMPOSE = os.environ.get("WM_COMPOSE", "")
DASH_URL = os.environ.get("WM_DASH_URL", "http://127.0.0.1:6185")
LXC_PLUGIN = (LXC_PLUGINS.rstrip("/") + "/astrbot_plugin_whalechan_meme") if LXC_PLUGINS else ""

REQUIRED_ENV = ("WM_PVESSH", "WM_LXC_ID", "WM_LXC_PLUGINS", "WM_LXC_BACKUPS", "WM_COMPOSE")


def _require_env():
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            "缺少站点配置环境变量: " + ", ".join(missing) +
            "\n请在 tools/deploy_home.env（KEY=VALUE，不入库）或环境变量中提供后重试。")

EXCLUDE = ("baseline-v070", "__pycache__", ".pyc")


def sh(cmd: str, check=True, quiet=False):
    """在本机跑 pvessh.py exec（远端命令）。"""
    if not quiet:
        print("$ " + cmd[:200])
    r = subprocess.run([PYTHON, PVESSH, "exec", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (("\n[STDERR]\n" + r.stderr) if r.stderr.strip() else "")
    if not quiet:
        print(out.strip()[:4000])
    if check and "[RC=0]" not in out:
        raise SystemExit(f"远端命令失败 (rc!=0):\n{out}")
    return out


def lxc(cmd: str, check=True, quiet=False):
    return sh(f"pct exec {LXC_ID} -- sh -lc {quote(cmd)}", check=check, quiet=quiet)


def quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def build_tar(dst: str) -> int:
    n = 0
    with tarfile.open(dst, "w:gz") as tf:
        for base, dirs, files in os.walk(PLUGIN_SRC):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in sorted(files):
                if any(x in f for x in EXCLUDE):
                    continue
                full = os.path.join(base, f)
                rel = os.path.relpath(full, os.path.dirname(PLUGIN_SRC))
                tf.add(full, arcname=rel)
                n += 1
    return n


def deploy(dry=False):
    ts = time.strftime("%Y%m%d-%H%M%S")
    tmp = tempfile.mkdtemp(prefix="wm-deploy-")
    tar = os.path.join(tmp, "wm-v08.tar.gz")
    n = build_tar(tar)
    print(f"打包 {n} 个文件 -> {tar} ({os.path.getsize(tar)} bytes)")
    if dry:
        print("[dry-run] 以下命令不会执行：")
        for c in (f"upload {tar} /root/wm/wm-v08.tar.gz",
                  f"pct push 200 /root/wm/wm-v08.tar.gz /root/wm-v08.tar.gz",
                  f"备份 {LXC_PLUGIN} -> {LXC_BACKUPS}/astrbot_plugin_whalechan_meme.bak-{ts}.tar.gz",
                  f"替换 {LXC_PLUGIN}",
                  f"docker compose -f {COMPOSE} restart astrbot",
                  "验收日志"):
            print("  -", c)
        return

    _require_env()

    # 1 上传
    subprocess.run([PYTHON, PVESSH, "upload", tar, "/root/wm/wm-v08.tar.gz"], check=True)
    sh("pct push 200 /root/wm/wm-v08.tar.gz /root/wm-v08.tar.gz")

    # 2 备份 + 替换
    lxc(f"mkdir -p {LXC_BACKUPS}")
    lxc(f"tar --no-same-owner -czf {LXC_BACKUPS}/astrbot_plugin_whalechan_meme.bak-{ts}.tar.gz "
        f"-C {LXC_PLUGINS} astrbot_plugin_whalechan_meme")
    lxc(f"ls -l {LXC_BACKUPS}/astrbot_plugin_whalechan_meme.bak-{ts}.tar.gz")
    lxc(f"rm -rf {LXC_PLUGIN} && mkdir -p {LXC_PLUGIN} && "
        f"tar --no-same-owner --no-same-permissions -xzf /root/wm-v08.tar.gz -C {LXC_PLUGIN} --strip-components=1 && "
        f"find {LXC_PLUGIN} -type f | sort")

    # 3 重启
    sh(f"pct exec 200 -- docker compose -f {COMPOSE} restart astrbot")
    print("等待 astrbot 起来…")

    # 4 验收（轮询到启动完成或超时）
    ok, out = verify()
    if not ok:
        print("!! 验收失败，开始回滚")
        rollback(ts)
        raise SystemExit("部署失败，已回滚")
    print("\n部署成功：v0.8.0 已加载，面板路由已注册。")
    print(f"备份位置：{LXC_BACKUPS}/astrbot_plugin_whalechan_meme.bak-{ts}.tar.gz")


def _boot_state():
    """返回 (health_code, 插件相关日志行)。"""
    raw = lxc(f"curl -s -o /dev/null -w '%{{http_code}}' {DASH_URL}/ || true",
              quiet=True)
    m = re.search(r"\b(\d{3})\b", raw or "")
    health = m.group(1) if m else "000"
    out = lxc("docker logs --since 6m astrbot 2>&1", quiet=True)
    wl = [l for l in out.splitlines() if "whalechan" in l.lower()]
    return health, wl


def verify(timeout: int = 150) -> tuple[bool, list]:
    """轮询等待启动完成：面板端口可访问 且 插件日志已给出结论（加载成功或报错）。"""
    deadline = time.time() + timeout
    health, wl = "", []
    while True:
        health, wl = _boot_state()
        loaded = any("v0.8.0 初始化完成" in l for l in wl)
        route = any("控制台面板路由已注册" in l for l in wl)
        failed = any(("Traceback" in l) or ("missing dependencies" in l) for l in wl)
        if (loaded and route and health.isdigit() and health != "000") or failed:
            break
        if time.time() > deadline:
            print(f"  等待超时（{timeout}s），最后 health={health}")
            break
        time.sleep(5)
    checks = {
        "版本横幅 v4.28.0": True,  # 下面单独用全量日志校验
        "插件 v0.8.0 初始化": any("v0.8.0 初始化完成" in l for l in wl),
        "面板路由已注册": any("控制台面板路由已注册" in l for l in wl),
        "无 missing dependencies": not any("missing dependencies" in l for l in wl),
        "无 Traceback": not any("Traceback" in l for l in wl),
        "面板端口 6185 可达": health.isdigit() and health != "000",
    }
    full = lxc("docker logs --since 6m astrbot 2>&1", quiet=True).splitlines()
    checks["版本横幅 v4.28.0"] = any("4.28.0" in l for l in full)
    for k, v in checks.items():
        print(f"  [{'OK' if v else 'FAIL'}] {k}")
    print("  插件相关日志：")
    for l in wl[-8:]:
        print("    " + l.strip()[:160])
    print("  6185 HTTP:", health)
    return all(checks.values()), wl


def rollback(ts: str):
    bak = f"{LXC_BACKUPS}/astrbot_plugin_whalechan_meme.bak-{ts}.tar.gz"
    lxc(f"rm -rf {LXC_PLUGIN} && mkdir -p {LXC_PLUGIN} && "
        f"tar --no-same-owner --no-same-permissions -xzf {bak} -C {LXC_PLUGIN} --strip-components=1")
    sh(f"pct exec 200 -- docker compose -f {COMPOSE} restart astrbot")
    time.sleep(10)
    out = lxc("docker logs --tail 60 astrbot 2>&1 | tail -60", quiet=True)
    print("回滚后日志尾部：")
    print(out[-1500:])


def rollback_latest():
    out = lxc(f"ls -t {LXC_BACKUPS}/astrbot_plugin_whalechan_meme.bak-*.tar.gz 2>/dev/null | head -1",
              quiet=True)
    bak = [l for l in out.splitlines() if l.strip().endswith(".tar.gz")]
    if not bak:
        raise SystemExit("没找到备份")
    path = bak[0].strip()
    print("回滚到", path)
    lxc(f"rm -rf {LXC_PLUGIN} && mkdir -p {LXC_PLUGIN} && "
        f"tar --no-same-owner --no-same-permissions -xzf {path} -C {LXC_PLUGIN} --strip-components=1")
    sh(f"pct exec 200 -- docker compose -f {COMPOSE} restart astrbot")
    time.sleep(10)
    print(lxc("docker logs --tail 40 astrbot 2>&1 | tail -40", quiet=True)[-1200:])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()
    if a.rollback:
        rollback_latest()
    else:
        deploy(dry=a.dry_run)
