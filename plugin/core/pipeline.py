# -*- coding: utf-8 -*-
"""生图流水线编排。v0.9.0

考据 → 诉求守卫 → 搜图 → 核对 → 合成生图（调用阶梯）→ 落盘记账。
不依赖 AstrBot，可独立 import 自测（tools/selftest.py）。
"""
from __future__ import annotations
from typing import Any

import json
import os
import re
import shutil
import time

from . import imaging, search
from .client import BailianClient
from .journal import Journal
from .prompts import (DEFAULT_DNA, DEFAULT_STYLE, DNA_LOCK_TAIL, ENHANCE_SYSTEM,
                      IDENTITY_NOTE, RAW_SCENE_CLAUSE, VERIFY_SYSTEM)


class Pipeline:
    def __init__(self, conf, client: BailianClient, journal: Journal,
                 paths: dict, log=None):
        """conf: callable(key, default) -> value；paths: state/tmp/outputs/ref 目录与文件。"""
        self.c = conf
        self.client = client
        self.journal = journal
        self.p = paths
        self.log = log or (lambda lvl, msg: None)

    # ---------------- 小工具 ----------------

    def _ci(self, key, default):
        try:
            return int(self.c(key, default))
        except (TypeError, ValueError):
            return default

    def _build_prompt(self, llm_prompt: str, scene: str, caption: str, has_refs: bool) -> str:
        dna = str(self.c("character_dna", "") or "").strip() or DEFAULT_DNA
        style = str(self.c("style_prefix", "") or "").strip() or DEFAULT_STYLE
        parts = [p for p in (dna, DNA_LOCK_TAIL, style) if p]
        if llm_prompt:
            parts.append(llm_prompt.strip()[: self._ci("max_prompt_chars", 400)])
        # 用户原话子句不参与截断：这是防漂移的兜底，必须完整
        parts.append(RAW_SCENE_CLAUSE.format(scene=scene.strip()))
        if caption:
            parts.append(f"图上文字：{caption}")
        txt = "。".join(p.rstrip("。，") for p in parts if p) + "。"
        if has_refs:
            txt += IDENTITY_NOTE
        return txt

    @staticmethod
    def _parse_json_loose(txt: str):
        txt = (txt or "").strip()
        txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
        try:
            return json.loads(txt)
        except Exception:
            m = re.search(r"\{.*\}", txt, flags=re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
        return None

    def guard_scene(self, scene: str, plan: dict | None) -> tuple[str, list]:
        """诉求守卫：把考据出的纠错应用到用户原话上，作为最终提示词的兜底子句。

        返回 (纠正后的原话, 纠错列表[(raw, cn)])。零 LLM 成本，保证用户诉求不丢。
        """
        fixes = []
        out = scene
        for e in (plan or {}).get("entities") or []:
            if not isinstance(e, dict):
                continue
            raw = str(e.get("raw") or "").strip()
            cn = str(e.get("canonical_cn") or "").strip()
            try:
                conf = float(e.get("confidence") or 0)
            except (TypeError, ValueError):
                conf = 0.0
            if raw and cn and raw != cn and conf >= 0.6 and raw in out:
                out = out.replace(raw, cn)
                fixes.append((raw, cn))
        return out, fixes

    # ---------------- 考据 ----------------

    def enhance(self, scene: str, caption: str, conn: dict | None = None) -> tuple[dict | None, dict]:
        """前置考据。conn = client.resolve_llm() 的结果；enhance_model 留空则跟随该连接。"""
        conn = conn if isinstance(conn, dict) else {}
        model = str(self.c("enhance_model", "") or "").strip() or str(conn.get("model") or "")
        if not conn.get("ok"):
            why = conn.get("why") or "LLM 连接不可用"
            self.log("error", f"跳过考据：{why}")
            return None, {"model": model, "status": "no_llm", "error": why,
                          "in": 0, "out": 0, "ms": 0}
        if not model:
            self.log("error", "跳过考据：未能确定考据模型（enhance_model 与 LLM 连接都为空）")
            return None, {"model": "", "status": "no_model", "in": 0, "out": 0, "ms": 0}
        user = scene
        if caption:
            user += f"\n（用户指定图上文字：{caption}）"
        msgs = [{"role": "system", "content": ENHANCE_SYSTEM},
                {"role": "user", "content": user}]
        txt, usage, meta = self.client.chat(
            model, msgs,
            temperature=float(self.c("enhance_temperature", 0.15)),
            timeout=self._ci("enhance_timeout_sec", 240),
            thinking=bool(self.c("enhance_thinking", True)),
            json_mode=bool(self.c("enhance_json_mode", True)),
            key=str(conn.get("key") or ""), base=str(conn.get("base") or ""))
        rec = {"model": model, "conn": conn.get("label", ""),
               **usage.as_dict(), **meta}
        if txt is None:
            self.log("error", f"考据调用失败: {meta}")
            return None, rec
        plan = self._parse_json_loose(txt)
        if not isinstance(plan, dict):
            self.log("error", f"考据未返回 JSON: {txt[:200]}")
            rec["status"] = "bad_json"
            return None, rec
        self.log("info", f"考据完成: {str(plan.get('analysis'))[:60]}")
        return plan, rec

    # ---------------- 搜图 + 核对 ----------------

    def search_refs(self, queries, names, tmpdir, conn: dict | None = None) -> tuple[list, dict]:
        rec = {"queries": queries[: self._ci("search_query_max", 3)],
               "candidates": 0, "downloaded": 0, "kept": 0, "ms": 0,
               "in": 0, "out": 0, "model": ""}
        t0 = time.time()
        if not self.c("search_enabled", True):
            return [], rec
        queries = [q for q in (queries or []) if q and str(q).strip()][: self._ci("search_query_max", 3)]
        if not queries:
            return [], rec

        provider = str(self.c("search_provider", "") or "").lower().strip()
        if provider not in ("", "none", "off", "builtin"):
            return [], rec  # 外部 tavily 通道在 v0.8 移除（实测本机不通）

        want = max(1, self._ci("search_refs", 2))
        pool = max(want, self._ci("search_candidates", 8))
        order = [s.strip().lower() for s in
                 str(self.c("search_order", "baidu,360,bing")).split(",") if s.strip()]
        min_px = max(imaging.MIN_SIDE, self._ci("search_min_px", imaging.MIN_SIDE))
        opener = search.warm_opener(bool(self.c("search_cookie_warmup", True)),
                                    self.log) if "baidu" in order else None

        cands, seen = [], set()
        for qi, q in enumerate(queries):
            got_any = False
            for src in order:
                try:
                    if src == "baidu":
                        rows = search.search_baidu(q, opener, self._ci("search_timeout_sec", 12), min_px)
                    elif src == "360":
                        rows = search.search_360(q, self._ci("search_timeout_sec", 12))
                    elif src == "bing":
                        rows = search.search_bing(q, self._ci("search_timeout_sec", 12))
                    else:
                        continue
                except Exception as e:
                    self.log("warning", f"图源 {src} 搜索异常: {e}")
                    continue
                if rows:
                    got_any = True
                for r in rows:
                    u = r.get("url") or ""
                    if not u or u in seen:
                        continue
                    seen.add(u)
                    r.update(src=src, query=q, qrank=qi,
                             score=search.title_score(r.get("title", ""), names or []))
                    cands.append(r)
            self.log("info", f"关键词「{q[:20]}」累计 {len(cands)} 个候选")
            if sum(1 for x in cands if x["score"] > 0) >= pool:
                break
            if not got_any and qi >= 1:
                continue
        rec["candidates"] = len(cands)
        if not cands:
            rec["ms"] = int((time.time() - t0) * 1000)
            return [], rec

        src_rank = {s: i for i, s in enumerate(order)}
        cands.sort(key=lambda x: (-x["score"], x["qrank"], src_rank.get(x["src"], 9)))

        saved: list[str] = []
        meta: list[dict] = []
        for cd in cands:
            if len(saved) >= pool:
                break
            raw = self.client.download(cd["url"], timeout=self._ci("search_timeout_sec", 12),
                                       ua=search.UA_HEADER["User-Agent"])
            if not raw or len(raw) < 2000:
                continue
            p = imaging.normalize(raw, os.path.join(tmpdir, f"ref_{len(saved)}_{cd['src']}.jpg"),
                                  max_side=1024, min_side=min_px)
            if p:
                saved.append(p)
                meta.append(cd)
        rec["downloaded"] = len(saved)
        if not saved:
            rec["ms"] = int((time.time() - t0) * 1000)
            return [], rec
        self.log("info", f"下载到 {len(saved)} 张候选（{','.join(sorted({m['src'] for m in meta}))}）")

        keep = self.verify(saved, meta, names or [], rec, conn)
        rec["ms"] = int((time.time() - t0) * 1000)
        if keep is None:
            rec["kept"] = len(saved[:want])
            return saved[:want], rec
        rec["kept"] = len(keep[:want])
        if not keep:
            self.log("warning", "核对后没有一张合格素材")
        return keep[:want], rec

    def verify(self, paths, meta, names, rec, conn: dict | None = None) -> list | None:
        if not self.c("verify_enabled", True) or not paths:
            return None
        conn = conn if isinstance(conn, dict) else {}
        if not conn.get("ok"):
            self.log("warning", f"跳过素材核对：{conn.get('why') or 'LLM 连接不可用'}")
            return None
        model = str(self.c("verify_model", "") or "").strip() or str(conn.get("model") or "")
        if not model:
            self.log("warning", "跳过素材核对：verify_model 与 LLM 连接都为空")
            return None
        rec["model"] = model
        max_n = min(len(paths), self._ci("verify_max_images", 4))
        side = self._ci("verify_thumb_px", 256)
        import base64
        import io as _io
        from PIL import Image as PILImage
        b64s, idxs = [], []
        for i, p in enumerate(paths[:max_n]):
            try:
                with PILImage.open(p) as im:
                    im = im.convert("RGB") # type: ignore
                    im.thumbnail((side, side))
                    buf = _io.BytesIO()
                    im.save(buf, "JPEG", quality=70)
                b64s.append(base64.b64encode(buf.getvalue()).decode())
                idxs.append(i)
            except Exception as e:
                self.log("warning", f"核对缩图失败: {e}")
        if not b64s:
            return None
        lines = ["目标对象：" + ("、".join(names) or "（未给出名称）")]
        for j, i in enumerate(idxs):
            t = meta[i].get("title") if i < len(meta) else ""
            if t:
                lines.append(f"第{j}张（搜索词「{meta[i].get('query', '')}」，网页标题：{t[:40]}）")
        content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}}
                   for b in b64s]
        content.append({"type": "text", "text": "\n".join(lines)})
        txt, usage, m2 = self.client.chat(
            model, [{"role": "system", "content": VERIFY_SYSTEM},
                    {"role": "user", "content": content}],
            temperature=0.1, timeout=self._ci("verify_timeout_sec", 300),
            key=str(conn.get("key") or ""), base=str(conn.get("base") or ""))
        rec["in"] += usage.in_tok
        rec["out"] += usage.out_tok
        if txt is None:
            self.log("warning", "素材核对调用失败，跳过核对")
            return None
        m = re.search(r"\[.*\]", txt, flags=re.S)
        if not m:
            self.log("warning", f"核对未返回 JSON，跳过核对: {txt[:120]}")
            return None
        try:
            arr = json.loads(m.group(0))
        except Exception:
            return None
        keep: list[str] = []
        checked = 0
        for item in arr:
            if not isinstance(item, dict):
                continue
            j_val = item.get("i")
            if not isinstance(j_val, int) or j_val >= len(idxs):
                continue
            checked += 1
            idx_i = idxs[int(j_val)]
            self.log("info", f"核对[{idx_i}] {'通过' if item.get('ok') else '剔除'}："
                             f"{str(item.get('who'))[:24]} {str(item.get('note'))[:24]}")
            if item.get("ok"):
                keep.append(paths[idx_i])
        rec["checked"] = checked
        return keep

    # ---------------- 主流程 ----------------

    def run(self, scene: str, caption: str, enhanced: bool,
            trigger: str = "cmd", session: str = "") -> dict:
        t0 = time.time()
        rid = self.journal.new_id()
        rec: dict[str, Any] = {"id": rid, "kind": "gen", "trigger": trigger, "session": session,
                               "scene": scene[:300], "caption": caption, "status": "failed",
                               "error": "", "enhance": None, "search": None, "verify": None,
                               "refs": [], "gen": [], "tokens_in": 0, "tokens_out": 0,
                               "images": 0, "ms": 0, "out": ""}
        tmpdir = os.path.join(self.p["tmp"], time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(tmpdir, exist_ok=True)

        try:
            return self._run_impl(t0, rid, rec, tmpdir, scene, caption, enhanced)
        finally:
            if not self.c("keep_assets", True) and os.path.isdir(tmpdir):
                shutil.rmtree(tmpdir, ignore_errors=True)
            else:
                self._prune_tmp()

    def _run_impl(self, t0: float, rid: str, rec: dict, tmpdir: str, scene: str, caption: str, enhanced: bool) -> dict:
        # ---- v0.9.0：两条连接各解析一次（LLM 可跟随 AstrBot，生图必须自配）----
        llm_conn = self.client.resolve_llm(self.c)
        gen_conn = self.client.resolve_gen(self.c)
        rec["conn"] = {
            "llm": {k: llm_conn.get(k) for k in ("ok", "label", "model", "base", "why")},
            "gen": {k: gen_conn.get(k) for k in
                    ("ok", "label", "model", "base", "dialect", "why")}}
        self.log("info", f"连接解析：LLM={llm_conn.get('label')}({llm_conn.get('model')}) "
                         f"{'ok' if llm_conn.get('ok') else '不可用:' + str(llm_conn.get('why'))}"
                         f"｜生图={gen_conn.get('label')}({gen_conn.get('model')}/"
                         f"{gen_conn.get('dialect')}) "
                         f"{'ok' if gen_conn.get('ok') else '不可用:' + str(gen_conn.get('why'))}")
        gen_model = str(gen_conn.get("model") or "").strip() or \
            str(self.c("model", "wan2.7-image"))

        # 生图连接没配好 → 立刻失败，别浪费考据/搜图/核对的额度
        if not gen_conn.get("ok"):
            why = gen_conn.get("why") or "生图连接未配置"
            self.log("error", f"终止本次生图：{why}")
            rec["error"] = why
            rec["gen"] = [{"kind": "cred", "refs": 0, "in": 0, "out": 0, "images": 0,
                           "status": "no_gen_conn", "ms": 0, "error": why}]
            rec["names"] = []
            rec["ms"] = int((time.time() - t0) * 1000)
            self.journal.append(rec)
            return {"img": None, "rec": rec, "caption": caption}

        llm_prompt = ""
        fixes: list[tuple[str, str]] = []
        names: list[str] = []
        queries: list[str] = []
        plan: dict[str, Any] | None = None
        if enhanced:
            plan, erec = self.enhance(scene, caption, llm_conn)
            rec["enhance"] = erec
            if plan:
                if plan.get("prompt"):
                    llm_prompt = str(plan["prompt"]).strip()
                if not caption and plan.get("caption"):
                    caption = str(plan["caption"]).strip()[:12]
                for e in plan.get("entities") or []:
                    if not isinstance(e, dict):
                        continue
                    for k in ("canonical_cn", "canonical_en", "canonical_jp"):
                        v = str(e.get(k) or "").strip()
                        if v and v not in names:
                            names.append(v)
                sq = plan.get("search_queries")
                if isinstance(sq, list):
                    queries = [str(x).strip() for x in sq if str(x).strip()]
                elif plan.get("asset_query"):
                    queries = [str(plan["asset_query"]).strip()]

        scene_final, fixes = self.guard_scene(scene, plan)
        rec["fixes"] = fixes

        extra_refs = []
        need_asset = bool((plan or {}).get("needs_asset")) and self.c("asset_enabled", True)
        if enhanced and need_asset and self.c("search_enabled", True) and queries:
            found, srec = self.search_refs(queries, names, tmpdir, llm_conn)
            rec["search"] = srec
            extra_refs.extend(found)

        # 搜不到 → 自绘素材图（多花一次生图额度）
        if enhanced and need_asset and not extra_refs and gen_conn.get("ok") and \
                self.c("search_fallback_asset", True) and (plan or {}).get("asset_prompt"):
            raw, atts = self.client.generate(
                gen_model,
                str((plan or {}).get("asset_prompt", "")).strip(), [], str(self.c("size", "1024*1024")),
                allow_text_fallback=True,
                key=str(gen_conn.get("key") or ""), base=str(gen_conn.get("base") or ""),
                dialect=str(gen_conn.get("dialect") or ""))
            gen_list = rec.get("gen")
            if isinstance(gen_list, list):
                gen_list.extend({"kind": "asset:" + str(a.get("kind", "")), **{k: a[k] for k in
                                 ("status", "in", "out", "ms") if k in a}} for a in atts)
            if raw:
                p = imaging.normalize(raw, os.path.join(tmpdir, "asset.jpg"))
                if p:
                    extra_refs.append(p)

        # 角色身份卡永远排第一
        refs = []
        card = imaging.card_path(self.c("reference_image", ""), self.p["ref_default"])
        if bool(self.c("use_reference", True)):
            ok, why = imaging.check_ref(card)
            if ok:
                refs.append(card)
            else:
                self.log("error", f"角色身份卡不可用: {why} —— 本次将无形象锁！")
                rec["error"] = f"身份卡不可用:{why}"
        max_refs = self._ci("max_refs", 3)
        refs.extend(extra_refs[: max(0, max_refs - len(refs))])
        rec["refs"] = [os.path.basename(r) for r in refs]

        prompt = self._build_prompt(llm_prompt, scene_final, caption, bool(refs))
        # 关掉参考图（use_reference=False）= 用户主动选择纯文生图，这时才允许 text 档
        allow_text = bool(self.c("allow_text_fallback", False)) or \
            not bool(self.c("use_reference", True))
        img, attempts = self.client.generate(
            gen_model, prompt, refs,
            str(self.c("size", "1024*1024")),
            allow_text_fallback=allow_text,
            key=str(gen_conn.get("key") or ""), base=str(gen_conn.get("base") or ""),
            dialect=str(gen_conn.get("dialect") or ""))
        gen_list = rec.get("gen")
        if isinstance(gen_list, list):
            gen_list.extend(attempts)

        for a in rec["gen"]:
            rec["tokens_in"] += int(a.get("in", 0) or 0)
            rec["tokens_out"] += int(a.get("out", 0) or 0)
            rec["images"] += int(a.get("images", 0) or 0)
        for key in ("enhance", "search"):
            d = rec.get(key)
            if isinstance(d, dict):
                rec["tokens_in"] += int(d.get("in", 0) or 0)
                rec["tokens_out"] += int(d.get("out", 0) or 0)

        if img:
            out_dir = self.p["outputs"]
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, rid + ".png")
            try:
                with open(out_path, "wb") as f:
                    f.write(img)
                rec["out"] = os.path.basename(out_path)
                self._prune_outputs()
            except Exception as e:
                self.log("warning", f"成品落盘失败: {e}")
            rec["status"] = "ok"
            rec["error"] = ""
        else:
            why = ""
            for a in attempts or []:
                if a.get("status") in ("no_valid_ref", "no_i2i_support") and a.get("error"):
                    why = str(a["error"])
                    break
            rec["error"] = rec["error"] or why or "生图失败（调用阶梯全部失败，见 gen 明细）"

        rec["ms"] = int((time.time() - t0) * 1000)
        rec["prompt"] = prompt[:600]
        rec["llm_prompt"] = llm_prompt[:300]
        rec["names"] = names[:6]
        self.journal.append(rec)
        return {"img": img, "rec": rec, "caption": caption}

    def _prune_outputs(self):
        try:
            keep = self._ci("keep_outputs_max", 60)
            d = self.p["outputs"]
            files = sorted((f for f in os.listdir(d) if f.endswith(".png")),
                           key=lambda f: os.path.getmtime(os.path.join(d, f)),
                           reverse=True)
            for f in files[keep:]:
                os.remove(os.path.join(d, f))
        except Exception:
            pass

    def _prune_tmp(self):
        """keep_assets 开着时，按天数清理素材临时目录，防止磁盘无限增长。"""
        try:
            days = self._ci("keep_tmp_days", 3)
            if days <= 0:
                return
            root = self.p["tmp"]
            if not os.path.isdir(root):
                return
            cutoff = time.time() - days * 86400
            for name in os.listdir(root):
                d = os.path.join(root, name)
                if os.path.isdir(d) and os.path.getmtime(d) < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass

    # ---------------- 解析文案（QQ 回复用） ----------------

    def parse_text(self, rec: dict, detail: str = "full") -> str:
        if detail == "none" or not rec:
            return ""
        sec = rec.get("ms", 0) / 1000.0
        tok = (rec.get("tokens_in", 0) + rec.get("tokens_out", 0)) / 1000.0
        if detail == "short":
            names = "、".join(rec.get("names") or []) or "通用画面"
            return f"解析：{names}｜{sec:.0f}s"
        lines = []
        names = "、".join(rec.get("names") or [])
        fixes = rec.get("fixes") or []
        head = "解析：" + (names or "通用画面")
        if fixes:
            head += "｜纠错：" + "、".join(f"{a}→{b}" for a, b in fixes[:3])
        lines.append(head)
        s = rec.get("search")
        if s and s.get("downloaded"):
            lines.append(f"参考：身份卡+{s.get('kept', 0)}张搜图"
                         f"（候选{s.get('candidates', 0)}下载{s.get('downloaded', 0)}）")
        lp = rec.get("llm_prompt") or ""
        if lp:
            lines.append("词：" + lp[:90])
        lines.append(f"{sec:.1f}s · {tok:.1f}k tokens")
        return "\n".join(lines)
