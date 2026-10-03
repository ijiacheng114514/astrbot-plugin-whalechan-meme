# -*- coding: utf-8 -*-
"""模型连接客户端。v0.9.0

职责：**双连接解析**（LLM / 生图各自独立）、chat/completions、多模态核对、
图生图/文生图、**调用阶梯**。每次调用都回报 token 用量（input/output/images），
供 journal 记账。

v0.9.0 起不再假定「所有人都用百炼 token-plan」：
  · LLM 连接默认**跟随 AstrBot 当前聊天模型**（agent_runner → provider → provider_sources），
    也可在面板里填自己的 URL + API Key（llm_source=custom）；
  · 生图连接**必须自己给** URL + API Key（面板「模型连接」），
    老的 provider_source_id 配置仍作为兼容兜底；
  · 生图接口方言自动识别：百炼/DashScope 走原生图生图（带形象锁），
    其它 OpenAI 兼容接口只能纯文生图 —— 此时若无合法参考图许可，
    直接失败并说明原因，**绝不悄悄画出别的角色**。

调用阶梯（修「主角漂移」的核心）：
  1) 角色身份卡 + 素材参考图
  2) 仅角色身份卡（素材图不合法/接口拒绝时）
  3) 纯文生图 —— 默认**禁止**（allow_text_fallback=False），
     因为纯文生图等于放弃形象锁，正是 v0.7.0 漂移的根因。
任何一级失败都记录原因，绝不静默。
"""
from __future__ import annotations
from typing import Any

import base64
import json
import os
import time
import urllib.error
import urllib.request

from . import imaging

NATIVE_MMC_PATH = "/services/aigc/multimodal-generation/generation"
GEN_NOT_CONFIGURED = "生图连接未配置：请在面板「模型连接」填写生图 URL 与 API Key"
NO_I2I = ("当前生图接口不是百炼/DashScope 系，不支持图生图形象锁；"
          "请改用百炼 compatible-mode 地址，或在设置里打开「允许纯文生图兜底」"
          "（allow_text_fallback，注意主角会漂移）")


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


def mask_key(v) -> str:
    """密钥掩码：任何日志/面板/探针输出都必须过这里。"""
    s = str(v or "").strip()
    if not s:
        return ""
    return (s[:3] + "****" + s[-2:]) if len(s) > 8 else "****"


class BailianClient:
    """名字叫 BailianClient 是历史包袱（v0.6 只支持百炼），现在它是通用连接层。"""

    def __init__(self, config_path: str, source_id: str, log=None):
        self.config_path = config_path
        self.source_id = source_id
        self.log = log or (lambda lvl, msg: None)
        self._cfg_cache: dict[str, Any] | None = None
        self._cfg_mtime = 0.0
        self._cfg_err_seen = False

    # ---------------- 凭据解析 ----------------

    def _cmd_config(self, fresh: bool = False) -> dict | None:
        """读 AstrBot 的 cmd_config.json（按 mtime 缓存，面板改完立刻生效）。

        读失败也要按 mtime 记住：一次 pipeline.run 里 resolve_llm/resolve_gen/conn_info
        会连着读好几次，不缓存就会把同一条错误刷满日志。
        """
        try:
            mt = os.path.getmtime(self.config_path)
        except Exception:
            mt = 0.0
        if not fresh and mt == self._cfg_mtime:
            if self._cfg_cache is not None:
                return self._cfg_cache
            if self._cfg_err_seen:
                return None
        self._cfg_err_seen = False
        try:
            with open(self.config_path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except Exception as e:
            self.log("error", f"读取 cmd_config.json 失败: {e}")
            self._cfg_err_seen = True
            self._cfg_mtime = mt
            return None
        self._cfg_mtime = mt
        if not isinstance(cfg, dict):
            self._cfg_err_seen = True
            return None
        self._cfg_cache = cfg
        return cfg

    @staticmethod
    def _first_key(v):
        if isinstance(v, list):
            v = v[0] if v else ""
        return str(v or "").strip()

    def _find_source(self, cfg, sid):
        """按 id 在 provider_sources 里找 (key, api_base)。"""
        if not isinstance(cfg, dict) or not sid:
            return None
        for s in cfg.get("provider_sources") or []:
            if not isinstance(s, dict) or str(s.get("id")) != str(sid):
                continue
            key = self._first_key(s.get("key")) or self._first_key(s.get("api_key"))
            base = str(s.get("api_base", "")).rstrip("/")
            if key and base:
                return key, base
        return None

    def credentials(self):
        """老逻辑（v0.8 及以前）：按插件配置 provider_source_id 取凭据。保留作兼容兜底。"""
        cfg = self._cmd_config(fresh=True)
        if cfg is None:
            return None
        got = self._find_source(cfg, self.source_id)
        if got:
            return got
        self.log("error", f"找不到 provider_source: {self.source_id}")
        return None

    def astrbot_chat_provider(self) -> dict | None:
        """跟随 AstrBot 当前聊天模型：
        agent_runner.config.model.provider_id -> provider[] 条目 -> provider_sources[] 凭据。
        返回 {key, base, model, provider_id, label} 或 None。
        """
        cfg = self._cmd_config()
        if not isinstance(cfg, dict):
            return None
        ar = cfg.get("agent_runner")
        if not isinstance(ar, dict):
            return None
        c = ar.get("config") if isinstance(ar.get("config"), dict) else {}
        m_val = c.get("model") if isinstance(c, dict) else {}
        m = m_val if isinstance(m_val, dict) else {}
        pid = str(m.get("provider_id") or "").strip()
        if not pid:
            return None
        entry = None
        for p in cfg.get("provider") or []:
            if isinstance(p, dict) and str(p.get("id")) == pid:
                entry = p
                break
        model = str((entry or {}).get("model") or "").strip()
        if not model and "/" in pid:
            model = pid.split("/", 1)[1]
        sid = str((entry or {}).get("provider_source_id") or "").strip()
        if not sid and "/" in pid:
            sid = pid.split("/", 1)[0]
        cred = self._find_source(cfg, sid)
        if not cred:
            # 有的 provider 条目自带 key/api_base
            k = self._first_key((entry or {}).get("key"))
            b = str((entry or {}).get("api_base", "")).rstrip("/")
            if k and b:
                cred = (k, b)
        if not cred or not model:
            return None
        return {"key": cred[0], "base": cred[1], "model": model,
                "provider_id": pid, "label": f"astrbot:{pid}"}

    def resolve_llm(self, c) -> dict:
        """LLM（考据/核对）连接解析。c(key, default) 是插件配置读取器。

        llm_source=custom 时用面板填的 URL/Key；否则跟随 AstrBot 聊天模型。
        llm_model 非空时覆盖模型名（凭据仍按上面规则），留空则完全跟随。
        """
        want_model = str(c("llm_model", "") or "").strip()
        src = str(c("llm_source", "astrbot") or "astrbot").strip().lower()
        if src in ("custom", "self", "own"):
            base = str(c("llm_base_url", "") or "").strip().rstrip("/")
            key = str(c("llm_api_key", "") or "").strip()
            if base and key:
                model = want_model
                if not model:
                    p = self.astrbot_chat_provider()
                    model = (p or {}).get("model", "")
                if not model:
                    return {"ok": False, "label": "custom", "model": "", "base": base,
                            "key": key, "dialect": "openai",
                            "why": "自定义 LLM 连接缺少模型名：请在面板填写 llm_model"}
                return {"ok": True, "label": "custom", "model": model,
                        "base": base, "key": key, "dialect": "openai", "why": ""}
            p = self.astrbot_chat_provider()
            if p:
                return {"ok": True, "label": p["label"] + "(custom 未填全)",
                        "model": want_model or p["model"], "base": p["base"],
                        "key": p["key"], "dialect": "openai", "why": ""}
            return {"ok": False, "label": "custom", "model": want_model, "base": base,
                    "key": key, "dialect": "openai",
                    "why": "自定义 LLM 连接不完整：需要 URL 与 API Key；"
                           "且无法回落到 AstrBot 聊天模型"}
        p = self.astrbot_chat_provider()
        if p:
            return {"ok": True, "label": p["label"], "model": want_model or p["model"],
                    "base": p["base"], "key": p["key"], "dialect": "openai",
                    "why": ""}
        cred = self.credentials()
        if cred:
            model = want_model or str(c("enhance_model", "") or "").strip() or "qwen-plus"
            return {"ok": True, "label": f"provider:{self.source_id}", "model": model,
                    "base": cred[1], "key": cred[0], "dialect": "openai", "why": ""}
        return {"ok": False, "label": "none", "model": want_model, "base": "", "key": "",
                "dialect": "openai",
                "why": "LLM 连接不可用：既没解析到 AstrBot 聊天模型，也没有可用 provider_source"}

    def resolve_gen(self, c) -> dict:
        """生图连接解析。面板 URL+Key 优先，其次老的 provider_source_id。"""
        base = str(c("gen_base_url", "") or "").strip().rstrip("/")
        key = str(c("gen_api_key", "") or "").strip()
        model = str(c("model", "") or "").strip()
        if base and key:
            return {"ok": True, "label": "panel", "model": model, "base": base,
                    "key": key, "dialect": self.gen_dialect(base), "why": ""}
        if base or key:
            return {"ok": False, "label": "panel", "model": model, "base": base,
                    "key": key, "dialect": self.gen_dialect(base),
                    "why": "生图连接不完整：URL 与 API Key 必须同时填写"}
        cred = self.credentials()
        if cred:
            return {"ok": True, "label": f"provider:{self.source_id}", "model": model,
                    "base": cred[1], "key": cred[0],
                    "dialect": self.gen_dialect(cred[1]), "why": ""}
        return {"ok": False, "label": "none", "model": model, "base": "", "key": "",
                "dialect": "openai", "why": GEN_NOT_CONFIGURED}

    @staticmethod
    def gen_dialect(base: str) -> str:
        """生图接口方言：百炼/DashScope 系支持原生图生图，其余按 OpenAI 兼容处理。"""
        b = str(base or "").lower()
        if "dashscope" in b or "aliyuncs" in b or "/compatible-mode" in b or "maas." in b:
            return "bailian"
        return "openai"

    @staticmethod
    def native_base(base: str) -> str:
        """从 compatible-mode 地址推出百炼原生 API 根。"""
        b = str(base or "").rstrip("/")
        if "/compatible-mode" in b:
            return b.split("/compatible-mode")[0].rstrip("/") + "/api/v1"
        if b.endswith("/api/v1"):
            return b
        if b.endswith("/v1"):
            return b[:-3] + "/api/v1"
        return b + "/api/v1"

    def conn_info(self, c) -> dict[str, Any]:
        """给面板看的连接状态（密钥一律掩码，绝不出明文）。"""
        llm, gen = self.resolve_llm(c), self.resolve_gen(c)
        out: dict[str, Any] = {}
        for name, r in (("llm", llm), ("gen", gen)):
            out[name] = {"ok": bool(r.get("ok")), "label": r.get("label", ""),
                         "model": r.get("model", ""), "base": r.get("base", ""),
                         "key_masked": mask_key(r.get("key", "")),
                         "dialect": r.get("dialect", ""), "why": r.get("why", "")}
        out["astrbot_chat"] = (lambda p: {"provider_id": p.get("provider_id", ""),
                                          "model": p.get("model", ""),
                                          "base": p.get("base", ""),
                                          "key_masked": mask_key(p.get("key", ""))}
                               if p else None)(self.astrbot_chat_provider())
        out["i2i_supported"] = out["gen"]["dialect"] == "bailian"
        return out

    # ---------------- HTTP ----------------

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

    def list_models(self, key: str = "", base: str = "") -> list[str]:
        if not (key and base):
            cred = self.credentials()
            if not cred:
                return []
            key, base = cred
        st, body = self.http_json(base.rstrip("/") + "/models",
                                  headers={"Authorization": "Bearer " + key}, timeout=60)
        if st != 200 or not isinstance(body, dict):
            return []
        return sorted(m.get("id", "") for m in body.get("data", []) if isinstance(m, dict))

    # ---------------- 文本 / 多模态 chat ----------------

    def chat(self, model: str, messages: list, temperature: float = 0.15,
             timeout: int = 240, thinking: bool = False, json_mode: bool = False,
             key: str = "", base: str = "") -> tuple[str | None, Usage, dict]:
        """返回 (content, usage, meta)。meta 含 status / error / ms。

        key/base 由调用方（pipeline 的连接解析结果）显式传入；不传则回落到
        老的 provider_source_id 凭据，保证 v0.8 的行为不变。
        """
        if not (key and base):
            cred = self.credentials()
            if not cred:
                return None, Usage(), {"status": "no_cred", "ms": 0,
                                       "error": GEN_NOT_CONFIGURED}
            key, base = cred
        url = base.rstrip("/") + "/chat/completions"
        payload = {"model": model, "messages": messages, "temperature": temperature}
        if thinking:
            payload["enable_thinking"] = True
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": "Bearer " + key}

        def once(p):
            t = time.time()
            st, body = self.http_json(url, p, headers=headers, timeout=timeout)
            return st, body, int((time.time() - t) * 1000)

        st, body, ms = once(payload)
        # 网关不支持 json_mode / enable_thinking 时逐个退让（400 不花钱）
        if st == 400 and json_mode:
            payload.pop("response_format", None)
            st, body, ms = once(payload)
        if st == 400 and thinking:
            payload.pop("enable_thinking", None)
            st, body, ms = once(payload)
        if st != 200 or not isinstance(body, dict):
            return None, Usage(), {"status": f"http{st}", "ms": ms,
                                   "error": str(body)[:300]}
        try:
            msg = body["choices"][0]["message"]
            txt = msg.get("content") or ""
            if isinstance(txt, list):  # 多模态返回分片
                txt = "".join(str(p.get("text", "")) for p in txt if isinstance(p, dict))
        except Exception:
            return None, _parse_usage(body), {"status": "bad_shape", "ms": ms}
        return txt, _parse_usage(body), {"status": "ok", "ms": ms}

    # ---------------- 连通性自测（面板按钮用） ----------------

    def test_llm(self, conn: dict, timeout: int = 40) -> dict:
        if not conn.get("ok"):
            return {"ok": False, "stage": "resolve", "error": conn.get("why") or "连接不可用",
                    "ms": 0, "in": 0, "out": 0}
        txt, usage, meta = self.chat(
            conn["model"], [{"role": "user", "content": "只回复两个字：在线"}],
            temperature=0, timeout=timeout, key=conn["key"], base=conn["base"])
        return {"ok": meta.get("status") == "ok" and txt is not None, "stage": "chat",
                "model": conn["model"], "label": conn.get("label", ""),
                "status": meta.get("status", ""), "error": meta.get("error", ""),
                "ms": meta.get("ms", 0), "in": usage.in_tok, "out": usage.out_tok,
                "reply": (txt or "")[:40]}

    def test_gen(self, conn: dict, timeout: int = 40) -> dict:
        """只探连通性 + 模型是否在列表里，**不生图**（生图很贵）。"""
        if not conn.get("ok"):
            return {"ok": False, "stage": "resolve", "error": conn.get("why") or "连接不可用",
                    "ms": 0}
        base, key, model = conn["base"], conn["key"], conn.get("model", "")
        t0 = time.time()
        st, body = self.http_json(base.rstrip("/") + "/models",
                                  headers={"Authorization": "Bearer " + key}, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        ids = []
        if st == 200 and isinstance(body, dict):
            ids = [str(m.get("id", "")) for m in body.get("data", []) if isinstance(m, dict)]
        listed = model in ids if model else False
        note = ""
        if st == 200 and model and not listed:
            note = f"模型「{model}」不在 /models 列表里（部分网关不列全，仍可能可用）"
        return {"ok": st == 200, "stage": "models", "status": f"http{st}",
                "error": "" if st == 200 else str(body)[:200], "ms": ms,
                "model": model, "listed": listed, "models": len(ids),
                "dialect": conn.get("dialect", ""), "note": note,
                "i2i": conn.get("dialect") == "bailian"}

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
        payload = {"model": model,
                   "input": {"messages": [{"role": "user", "content": content}]},
                   "parameters": {"size": size, "n": 1}}
        t0 = time.time()
        st, body = self.http_json(self.native_base(base) + NATIVE_MMC_PATH, payload,
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
        """百炼 compatible-mode 上的生图模型（qwen-image / wan 系）走 chat/completions。"""
        payload = {"model": model,
                   "messages": [{"role": "user",
                                 "content": [{"type": "text", "text": prompt}]}],
                   "parameters": {"size": size, "n": 1}}
        t0 = time.time()
        st, body = self.http_json(base.rstrip("/") + "/chat/completions", payload,
                                  headers={"Authorization": "Bearer " + key}, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        if st != 200 or not isinstance(body, dict):
            return None, Usage(), {"status": f"http{st}", "ms": ms,
                                   "error": str(body)[:300]}
        raw = self._extract(body)
        if raw is None:
            return None, _parse_usage(body), {"status": "no_image", "ms": ms}
        return raw, _parse_usage(body), {"status": "ok", "ms": ms}

    def _gen_openai(self, key, base, model, prompt, size, timeout=240):
        """通用 OpenAI 兼容文生图：POST /images/generations。"""
        payload = {"model": model, "prompt": prompt, "n": 1}
        if size:
            payload["size"] = str(size).replace("*", "x")
        t0 = time.time()
        st, body = self.http_json(base.rstrip("/") + "/images/generations", payload,
                                  headers={"Authorization": "Bearer " + key}, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        if st != 200 or not isinstance(body, dict):
            return None, Usage(), {"status": f"http{st}", "ms": ms,
                                   "error": str(body)[:300]}
        raw = self._extract_openai(body)
        if raw is None:
            return None, _parse_usage(body), {"status": "no_image", "ms": ms}
        return raw, _parse_usage(body), {"status": "ok", "ms": ms}

    @staticmethod
    def _extract_openai(body) -> bytes | None:
        try:
            d = body["data"][0]
        except Exception:
            return None
        if not isinstance(d, dict):
            return None
        b64 = d.get("b64_json")
        if b64:
            try:
                return base64.b64decode(b64)
            except Exception:
                return None
        url = d.get("url")
        return BailianClient.download(url) if url else None

    @staticmethod
    def _extract(body) -> bytes | None:
        url = None
        try:
            content = body["output"]["choices"][0]["message"]["content"]
        except Exception:
            content = None
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("image"):
                    url = part["image"]
                    break
        if not url:
            res = (body.get("output") or {}).get("results") if isinstance(body, dict) else None
            if isinstance(res, list) and res and isinstance(res[0], dict):
                url = res[0].get("url") or res[0].get("b64_image")
        if not url:
            return None
        if str(url).startswith("data:"):
            try:
                return base64.b64decode(str(url).split(",", 1)[1])
            except Exception:
                return None
        return BailianClient.download(url)

    def generate(self, model: str, prompt: str, ref_paths: list, size: str,
                 allow_text_fallback: bool = False, key: str = "", base: str = "",
                 dialect: str = "") -> tuple[bytes | None, list]:
        """调用阶梯。返回 (图片字节, attempts 列表)。

        key/base/dialect 由 pipeline 的 resolve_gen() 结果传入；不传则回落老凭据。
        """
        if not (key and base):
            cred = self.credentials()
            if not cred:
                return None, [{"kind": "cred", "refs": 0, "in": 0, "out": 0, "images": 0,
                               "status": "no_cred", "ms": 0, "error": GEN_NOT_CONFIGURED}]
            key, base = cred
        dialect = dialect or self.gen_dialect(base)

        valid: list[str] = []
        dropped: list[str] = []
        for p in ref_paths:
            ok, why = imaging.check_ref(p)
            (valid if ok else dropped).append(p if ok else f"{p}({why})")
        if dropped:
            self.log("warning", f"参考图被硬闸门拦下: {dropped}")

        ladder = []
        if valid and dialect == "bailian":
            ladder.append(("char+assets" if len(valid) > 1 else "char", valid))
            if len(valid) > 1:
                ladder.append(("char", valid[:1]))
        if allow_text_fallback or not valid:
            ladder.append(("text", []))
        if not ladder:
            # 有合法参考图但接口不支持图生图 / 参考图全不合格且不许纯文生图
            # → 直接失败，绝不悄悄画出「别的角色」
            why = NO_I2I if valid else \
                "参考图全部不合格，且 allow_text_fallback=False（拒绝无形象锁出图）"
            return None, [{"kind": "blocked", "refs": len(valid), "in": 0, "out": 0,
                           "images": 0,
                           "status": "no_i2i_support" if valid else "no_valid_ref",
                           "ms": 0, "error": why}]

        attempts = []
        for kind, refs in ladder:
            if refs:
                raw, usage, meta = self._gen_native(key, base, model, prompt, refs, size)
            elif dialect == "bailian":
                raw, usage, meta = self._gen_text(key, base, model, prompt, size)
            else:
                raw, usage, meta = self._gen_openai(key, base, model, prompt, size)
            att = {"kind": kind, "refs": len(refs), "dialect": dialect,
                   **usage.as_dict(), **meta}
            attempts.append(att)
            self.log("info", f"生图[{kind}/{dialect}] {meta.get('status')} "
                     f"in={usage.in_tok} out={usage.out_tok} {meta.get('ms')}ms")
            if raw:
                return raw, attempts
        return None, attempts
