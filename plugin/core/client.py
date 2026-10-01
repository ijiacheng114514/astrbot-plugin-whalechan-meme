# -*- coding: utf-8 -*-
"""百炼 token-plan 客户端。v0.8.0

职责：凭据解析、chat/completions、多模态核对、图生图/文生图、**调用阶梯**。
每次调用都回报 token 用量（input/output/images），供 journal 记账。

调用阶梯（修「主角漂移」的核心）：
  1) 角色身份卡 + 素材参考图
  2) 仅角色身份卡（素材图不合法/接口拒绝时）
  3) 纯文生图 —— 默认**禁止**（allow_text_fallback=False），
     因为纯文生图等于放弃形象锁，正是 v0.7.0 漂移的根因。
任何一级失败都记录原因，绝不静默。
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request

from . import imaging

NATIVE_MMC_PATH = "/services/aigc/multimodal-generation/generation"


class Usage:
    __slots__ = ("in_tok", "out_tok", "images")

    def __init__(self, in_tok=0, out_tok=0, images=0):
        self.in_tok = in_tok
        self.out_tok = out_tok
        self.images = images

    def as_dict(self):
        return {"in": self.in_tok, "out": self.out_tok, "images": self.images}


def _parse_usage(body) -> Usage:
    u = Usage()
    if not isinstance(body, dict):
        return u
    d = body.get("usage") or {}
    if not isinstance(d, dict):
        return u
    u.in_tok = int(d.get("input_tokens") or d.get("prompt_tokens") or 0)
    u.out_tok = int(d.get("output_tokens") or d.get("completion_tokens") or 0)
    u.images = int(d.get("image_count") or 0)
    return u


class BailianClient:
    def __init__(self, config_path: str, source_id: str, log=None):
        self.config_path = config_path
        self.source_id = source_id
        self.log = log or (lambda lvl, msg: None)

    # ---------------- 凭据 / HTTP ----------------

    def credentials(self):
        try:
            with open(self.config_path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except Exception as e:
            self.log("error", f"读取 cmd_config.json 失败: {e}")
            return None
        for s in cfg.get("provider_sources", []):
            if s.get("id") != self.source_id:
                continue
            key = s.get("key")
            if isinstance(key, list):
                key = key[0] if key else ""
            base = str(s.get("api_base", "")).rstrip("/")
            if key and base:
                return key, base
        self.log("error", f"找不到 provider_source: {self.source_id}")
        return None

    @staticmethod
    def http_json(url, payload=None, headers=None, timeout=240):
        data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        h = dict(headers or {})
        if data is not None:
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=h,
                                     method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            return e.code, body
        except Exception as e:
            return -1, repr(e)

    @staticmethod
    def download(url, timeout=120, ua=None) -> bytes | None:
        h = {}
        if ua:
            h["User-Agent"] = ua
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            return None

    def list_models(self) -> list[str]:
        cred = self.credentials()
        if not cred:
            return []
        key, base = cred
        st, body = self.http_json(base + "/models", headers={"Authorization": "Bearer " + key},
                                  timeout=60)
        if st != 200 or not isinstance(body, dict):
            return []
        return sorted(m.get("id", "") for m in body.get("data", []) if isinstance(m, dict))

    # ---------------- 文本 / 多模态 chat ----------------

    def chat(self, model: str, messages: list, temperature: float = 0.15,
             timeout: int = 240, thinking: bool = False,
             json_mode: bool = False) -> tuple[str | None, Usage, dict]:
        """返回 (content, usage, meta)。meta 含 status / error / ms。"""
        cred = self.credentials()
        if not cred:
            return None, Usage(), {"status": "no_cred", "ms": 0}
        key, base = cred
        payload = {"model": model, "messages": messages, "temperature": temperature}
        if thinking:
            payload["enable_thinking"] = True
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.time()
        st, body = self.http_json(base + "/chat/completions", payload,
                                  headers={"Authorization": "Bearer " + key}, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        # json_mode 不被网关支持时退一次（400 不花钱）
        if st == 400 and json_mode:
            payload.pop("response_format", None)
            t0 = time.time()
            st, body = self.http_json(base + "/chat/completions", payload,
                                      headers={"Authorization": "Bearer " + key}, timeout=timeout)
            ms = int((time.time() - t0) * 1000)
        if st != 200 or not isinstance(body, dict):
            return None, Usage(), {"status": f"http{st}", "ms": ms,
                                   "error": str(body)[:300]}
        try:
            txt = body["choices"][0]["message"].get("content") or ""
        except Exception:
            return None, _parse_usage(body), {"status": "bad_shape", "ms": ms}
        return txt, _parse_usage(body), {"status": "ok", "ms": ms}

    # ---------------- 生图 ----------------

    def _gen_native(self, key, base, model, prompt, ref_paths, size, timeout=300):
        content = []
        for p in ref_paths:
            try:
                with open(p, "rb") as f:
                    blob = f.read()
                mime = "image/png" if str(p).lower().endswith(".png") else "image/jpeg"
                content.append({"image": f"data:{mime};base64," +
                                         base64.b64encode(blob).decode()})
            except Exception as e:
                self.log("error", f"读取参考图 {p} 失败: {e}")
        if not content:
            return None, Usage(), {"status": "no_ref", "ms": 0}
        content.append({"text": prompt})
        native = base.split("/compatible-mode")[0].rstrip("/") + "/api/v1"
        payload = {"model": model,
                   "input": {"messages": [{"role": "user", "content": content}]},
                   "parameters": {"size": size, "n": 1}}
        t0 = time.time()
        st, body = self.http_json(native + NATIVE_MMC_PATH, payload,
                                  headers={"Authorization": "Bearer " + key}, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        if st != 200 or not isinstance(body, dict):
            return None, Usage(), {"status": f"http{st}", "ms": ms,
                                   "error": str(body)[:300]}
        raw = self._extract(body)
        if raw is None:
            return None, _parse_usage(body), {"status": "no_image", "ms": ms}
        return raw, _parse_usage(body), {"status": "ok", "ms": ms}

    def _gen_text(self, key, base, model, prompt, size, timeout=240):
        payload = {"model": model,
                   "messages": [{"role": "user",
                                 "content": [{"type": "text", "text": prompt}]}],
                   "parameters": {"size": size, "n": 1}}
        t0 = time.time()
        st, body = self.http_json(base + "/chat/completions", payload,
                                  headers={"Authorization": "Bearer " + key}, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        if st != 200 or not isinstance(body, dict):
            return None, Usage(), {"status": f"http{st}", "ms": ms,
                                   "error": str(body)[:300]}
        raw = self._extract(body)
        if raw is None:
            return None, _parse_usage(body), {"status": "no_image", "ms": ms}
        return raw, _parse_usage(body), {"status": "ok", "ms": ms}

    @staticmethod
    def _extract(body) -> bytes | None:
        try:
            content = body["output"]["choices"][0]["message"]["content"]
        except Exception:
            return None
        url = None
        for part in content:
            if isinstance(part, dict) and part.get("image"):
                url = part["image"]
                break
        if not url:
            return None
        return BailianClient.download(url)

    def generate(self, model: str, prompt: str, ref_paths: list, size: str,
                 allow_text_fallback: bool = False) -> tuple[bytes | None, list]:
        """调用阶梯。返回 (图片字节, attempts 列表)。"""
        cred = self.credentials()
        if not cred:
            return None, [{"kind": "cred", "status": "no_cred", "ms": 0}]
        key, base = cred

        valid, dropped = [], []
        for p in ref_paths:
            ok, why = imaging.check_ref(p)
            (valid if ok else dropped).append(p if ok else f"{p}({why})")
        if dropped:
            self.log("warning", f"参考图被硬闸门拦下: {dropped}")

        ladder = []
        if valid:
            ladder.append(("char+assets" if len(valid) > 1 else "char", valid))
            if len(valid) > 1:
                ladder.append(("char", valid[:1]))
        if allow_text_fallback:
            ladder.append(("text", []))
        if not ladder:
            # 没有任何合法参考图，又不许纯文生图 → 直接失败，绝不悄悄画出「别的角色」
            return None, [{"kind": "blocked", "refs": 0, "in": 0, "out": 0,
                           "images": 0, "status": "no_valid_ref", "ms": 0,
                           "error": "参考图全部不合格，且 allow_text_fallback=False（拒绝无形象锁出图）"}]

        attempts = []
        for kind, refs in ladder:
            if refs:
                raw, usage, meta = self._gen_native(key, base, model, prompt, refs, size)
            else:
                raw, usage, meta = self._gen_text(key, base, model, prompt, size)
            att = {"kind": kind, "refs": len(refs), **usage.as_dict(), **meta}
            attempts.append(att)
            self.log("info", f"生图[{kind}] {meta.get('status')} "
                             f"in={usage.in_tok} out={usage.out_tok} {meta.get('ms')}ms")
            if raw:
                return raw, attempts
        return None, attempts
