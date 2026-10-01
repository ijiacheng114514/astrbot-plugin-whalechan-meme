# -*- coding: utf-8 -*-
"""站点配置（面板写入的那一份）。v0.9.0

为什么要单独一层：AstrBot 的插件配置（config.json / _conf_schema.json 默认值）
**存在插件目录里**，而插件目录每次升级部署都会被整体替换 —— 把 API Key 存那儿，
一次升级就要重填一次。所以面板改的东西一律写到 plugin_data 下：

    <data>/plugin_data/astrbot_plugin_whalechan_meme/site.json   (0600)

读取优先级：site.json > AstrBot 插件配置（self.conf）> _conf_schema.json 默认值。
密钥类字段（名字含 api_key / secret / token）对外一律走 mask，绝不进日志与接口响应。
"""
from __future__ import annotations

import json
import os

SECRET_MARK = ("api_key", "apikey", "secret", "token", "password")


def is_secret(key: str) -> bool:
    k = str(key or "").lower()
    return any(m in k for m in SECRET_MARK)


def mask(v) -> str:
    """密钥掩码：只显示头 3 尾 2，其余打星。空值返回空串。"""
    s = str(v or "").strip()
    if not s:
        return ""
    return (s[:3] + "****" + s[-2:]) if len(s) > 8 else "****"


CLEAR = "__CLEAR__"      # 面板传这个值 = 明确要求清空（空字符串默认理解为「不改」）
KEEP = "__KEEP__"        # 显式表示保持原值


class SiteConfig:
    def __init__(self, path: str, log=None):
        self.path = path
        self.log = log or (lambda lvl, msg: None)
        self._d: dict = {}
        self.load()

    # ---------------- 读写 ----------------

    def load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self._d = d if isinstance(d, dict) else {}
        except FileNotFoundError:
            self._d = {}
        except Exception as e:
            self.log("warning", f"站点配置读取失败（当作空配置）: {e}")
            self._d = {}
        return self._d

    def get(self, key, default=None):
        return self._d.get(key, default)

    def has(self, key) -> bool:
        return key in self._d

    def overridden(self) -> list:
        return sorted(self._d.keys())

    def update(self, changes: dict) -> list:
        """写入并落盘。密钥键：空值/KEEP 视为不改，CLEAR 视为清空。返回真正改动的键。"""
        applied = []
        for k, v in changes.items():
            if is_secret(k):
                s = str(v if v is not None else "")
                if s in ("", KEEP) or s == mask(self._d.get(k, "")):
                    continue
                v = "" if s == CLEAR else s
            self._d[k] = v
            applied.append(k)
        if applied:
            self._flush()
        return applied

    def _flush(self):
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._d, f, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, self.path)

    # ---------------- 对外呈现 ----------------

    def public(self, keys=None) -> dict:
        """给面板看的快照：密钥打码。keys 为 None 时返回全部。"""
        src = self._d if keys is None else {k: self._d[k] for k in keys if k in self._d}
        return {k: (mask(v) if is_secret(k) else v) for k, v in src.items()}
