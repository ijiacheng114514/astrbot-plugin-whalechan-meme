# -*- coding: utf-8 -*-
"""运行日志（JSONL）与 token 记账。v0.8.0

每次生图写一条结构化记录到 <state>/logs/runs.jsonl，供控制台面板展示与额度核算。
不依赖 AstrBot，可独立 import 自测。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

MAX_BYTES = 2 * 1024 * 1024  # 单文件上限，超过即轮转


class Journal:
    def __init__(self, state_dir: str):
        self.dir = os.path.join(state_dir, "logs")
        self.path = os.path.join(self.dir, "runs.jsonl")
        self._lock = threading.Lock()
        try:
            os.makedirs(self.dir, exist_ok=True)
        except Exception:
            pass

    # ---------------- 写 ----------------

    @staticmethod
    def new_id() -> str:
        return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]

    def append(self, rec: dict) -> str:
        rid = rec.get("id") or self.new_id()
        rec["id"] = rid
        rec.setdefault("ts", time.time())
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            try:
                self._rotate_if_needed()
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
        return rid

    def _rotate_if_needed(self):
        try:
            if os.path.isfile(self.path) and os.path.getsize(self.path) > MAX_BYTES:
                old = self.path + ".1"
                if os.path.isfile(old):
                    os.remove(old)
                os.replace(self.path, old)
        except Exception:
            pass

    # ---------------- 读 ----------------

    def read(self, limit: int = 50, offset: int = 0) -> list[dict]:
        out: list[dict] = []
        for p in (self.path, self.path + ".1"):
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                continue
        out.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return out[offset:offset + limit]

    def get(self, rid: str) -> dict | None:
        for r in self.read(limit=500):
            if r.get("id") == rid:
                return r
        return None

    # ---------------- 统计 ----------------

    def stats(self, since_ts: float | None = None) -> dict:
        """since_ts=None 表示"今天 0 点起"。"""
        if since_ts is None:
            lt = time.localtime()
            since_ts = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        rows = [r for r in self.read(limit=2000) if r.get("ts", 0) >= since_ts]
        gens = sum(1 for r in rows if r.get("kind") == "gen")
        ok = sum(1 for r in rows if r.get("kind") == "gen" and r.get("status") == "ok")
        t_in = sum(int(r.get("tokens_in", 0) or 0) for r in rows)
        t_out = sum(int(r.get("tokens_out", 0) or 0) for r in rows)
        imgs = sum(int(r.get("images", 0) or 0) for r in rows)
        ms = sum(int(r.get("ms", 0) or 0) for r in rows if r.get("kind") == "gen")
        return {
            "since": since_ts,
            "runs": len(rows),
            "gens": gens,
            "ok": ok,
            "fail": gens - ok,
            "tokens_in": t_in,
            "tokens_out": t_out,
            "tokens": t_in + t_out,
            "images": imgs,
            "avg_ms": int(ms / ok) if ok else 0,
        }
