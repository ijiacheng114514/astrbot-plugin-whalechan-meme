# -*- coding: utf-8 -*-
"""控制台面板后端：注册 /astrbot_plugin_whalechan_meme/page/* 路由。v0.9.0

前端是插件自带的 pages/console/（AstrBot 控制台会自动发现并挂进侧边栏），
通过 window.AstrBotPluginPage.apiGet / apiPost / upload 访问这里的路由。
控制台会把 endpoint 拼成 /api/v1/plugins/extensions/<metadata.name>/<endpoint>，
所以注册的 route 必须以 metadata.yaml 里的 name 开头。

v0.9.0：面板改的配置写进 plugin_data/site.json（不在插件目录里，升级不丢），
新增「模型连接」相关路由：/conn/info（连接解析状态，密钥打码）、/test/conn（连通性自测）。

返回约定：{"status":"ok"|"error","message":...,"data":...}
所有会阻塞的活（读 JSONL、PIL 缩图、requests 出网）都走 asyncio.to_thread，
不许卡 AstrBot 的事件循环——卡住会连带 QQ 消息一起卡。
"""
from __future__ import annotations

import asyncio
import os
import time

from . import imaging
from .prompts import PLUGIN_NAME
from .siteconf import is_secret, mask

PAGE_PREFIX = f"/{PLUGIN_NAME}/page"

# 允许在面板里改的配置键（其余键只能改 _conf_schema.json）
# 故意不开放：enable、group_whitelist（属于开关面板职责，改错了会整个失联）。
EDITABLE = {
    # 连接（v0.9.0）
    "llm_source", "llm_base_url", "llm_api_key", "llm_model",
    "gen_base_url", "gen_api_key", "provider_source_id",
    # 生图
    "model", "size", "use_reference", "max_refs", "allow_text_fallback",
    "reference_image", "max_prompt_chars", "keep_assets", "keep_outputs_max",
    "keep_tmp_days",
    # 考据
    "enhance_enabled", "enhance_model", "enhance_temperature", "enhance_thinking",
    "enhance_json_mode", "enhance_timeout_sec", "enhance_for_llm_tool",
    # 素材
    "asset_enabled", "search_enabled", "search_order", "search_cookie_warmup",
    "search_refs", "search_min_px", "search_query_max", "search_candidates",
    "search_timeout_sec", "search_fallback_asset",
    "verify_enabled", "verify_model", "verify_max_images", "verify_thumb_px",
    "verify_timeout_sec",
    # 限额 / 回复
    "daily_limit", "hourly_limit", "cooldown_sec", "command_bypass_cooldown",
    "token_budget_daily", "reply_detail", "verbose_progress", "ack_text",
    "character_dna", "style_prefix",
}

# 这些键改完必须重启插件才真正生效（客户端在 __init__ 里取了 source_id）
NEEDS_RELOAD = {"provider_source_id"}


class PageApi:
    def __init__(self, plugin):
        self.plugin = plugin

    # ---------------- 注册 ----------------

    def register(self):
        ctx = getattr(self.plugin, "context", None)
        reg = getattr(ctx, "register_web_api", None)
        if not reg:
            return False
        R = [
            (f"{PAGE_PREFIX}/stats", self.get_stats, ["GET"], "鲸鱼娘生图 概览"),
            (f"{PAGE_PREFIX}/runs", self.get_runs, ["GET"], "鲸鱼娘生图 运行日志"),
            (f"{PAGE_PREFIX}/run/<rid>", self.get_run, ["GET"], "鲸鱼娘生图 单条详情"),
            (f"{PAGE_PREFIX}/config", self.get_config, ["GET"], "鲸鱼娘生图 配置"),
            (f"{PAGE_PREFIX}/config", self.set_config, ["POST"], "鲸鱼娘生图 改配置"),
            (f"{PAGE_PREFIX}/conn/info", self.conn_info, ["GET"], "鲸鱼娘生图 连接状态"),
            (f"{PAGE_PREFIX}/test/conn", self.test_conn, ["POST"], "鲸鱼娘生图 连接自测"),
            (f"{PAGE_PREFIX}/models", self.get_models, ["GET"], "鲸鱼娘生图 可用模型"),
            (f"{PAGE_PREFIX}/ref/info", self.ref_info, ["GET"], "鲸鱼娘生图 参考图信息"),
            (f"{PAGE_PREFIX}/ref/upload", self.ref_upload, ["POST"], "鲸鱼娘生图 上传参考图"),
            (f"{PAGE_PREFIX}/ref/card", self.ref_card, ["POST"], "鲸鱼娘生图 重裁身份卡"),
            (f"{PAGE_PREFIX}/gallery", self.gallery, ["GET"], "鲸鱼娘生图 图库"),
            (f"{PAGE_PREFIX}/image", self.image, ["GET"], "鲸鱼娘生图 取图"),
            (f"{PAGE_PREFIX}/test/enhance", self.test_enhance, ["POST"], "鲸鱼娘生图 考据自测"),
        ]
        for route, fn, methods, desc in R:
            reg(route, fn, methods, desc)
        return True

    @staticmethod
    def ok(data=None, message=""):
        return {"status": "ok", "message": message,
                "data": data if data is not None else {}}

    @staticmethod
    def err(message):
        return {"status": "error", "message": message, "data": {}}

    # ---------------- 概览 / 日志 ----------------

    def _stats_sync(self):
        p = self.plugin
        st = p.journal.stats()
        budget = p._cfg_int("token_budget_daily", 0)
        card = p._card()
        cok, cwhy = imaging.check_ref(card)
        llm = p.client.resolve_llm(p._c)
        gen = p.client.resolve_gen(p._c)
        return {
            "version": p.version,
            "stats": st,
            "budget_daily": budget,
            "budget_left": (budget - st["tokens"]) if budget > 0 else None,
            "card": {"path": card, "ok": cok, "why": cwhy,
                     "exists": os.path.isfile(card)},
            "models": {"gen": gen.get("model", ""), "enhance": p._c("enhance_model", ""),
                       "verify": p._c("verify_model", "")},
            "conn": {"llm_ok": bool(llm.get("ok")), "gen_ok": bool(gen.get("ok")),
                     "llm_label": llm.get("label", ""), "gen_label": gen.get("label", ""),
                     "llm_model": llm.get("model", ""), "gen_model": gen.get("model", ""),
                     "i2i": gen.get("dialect") == "bailian",
                     "why": gen.get("why") or llm.get("why") or ""},
            "limits": {"daily": p._cfg_int("daily_limit", 0),
                       "hourly": p._cfg_int("hourly_limit", 0),
                       "cooldown": p._cfg_int("cooldown_sec", 0)},
            "usage": list(p._usage()),
        }

    async def get_stats(self):
        return self.ok(await asyncio.to_thread(self._stats_sync))

    async def get_runs(self):
        from astrbot.api.web import request
        try:
            limit = min(int(request.query.get("limit", "40") or 40), 200)
            offset = int(request.query.get("offset", "0") or 0)
        except (TypeError, ValueError):
            limit, offset = 40, 0
        rows = await asyncio.to_thread(self.plugin.journal.read, limit, offset)
        keys = ("id", "ts", "trigger", "session", "scene", "caption", "status", "error",
                "tokens_in", "tokens_out", "images", "ms", "refs", "fixes", "names", "out")
        brief = [{k: r.get(k) for k in keys} for r in rows]
        return self.ok({"runs": brief, "total": len(brief), "offset": offset})

    async def get_run(self, rid):
        r = await asyncio.to_thread(self.plugin.journal.get, rid)
        if not r:
            return self.err(f"没有这条记录: {rid}")
        return self.ok(r)

    # ---------------- 配置 ----------------

    async def get_config(self):
        p = self.plugin
        data, secrets = {}, {}
        for k in sorted(EDITABLE):
            v = p._c(k, None)
            if is_secret(k):
                secrets[k] = mask(v)
                data[k] = ""          # 明文密钥绝不出接口
            else:
                data[k] = v
        schema = await asyncio.to_thread(p._read_schema) or {}
        hints = {}
        for k, v in schema.items():
            if isinstance(v, dict):
                hints[k] = {"description": v.get("description", ""),
                            "hint": v.get("hint", ""), "type": v.get("type", "")}
        return self.ok({"config": data, "secrets": secrets, "hints": hints,
                        "editable": sorted(EDITABLE),
                        "overridden": p.site.overridden(),
                        "site_path": p.site.path})

    async def set_config(self):
        from astrbot.api.web import request
        body = await request.json(default={}) or {}
        changes = body.get("changes") or body or {}
        if not isinstance(changes, dict):
            return self.err("body 应为 {changes:{key:value}}")
        bad = [k for k in changes if k not in EDITABLE]
        if bad:
            return self.err("这些键不允许在面板修改: " + ",".join(bad[:8]))
        p = self.plugin

        # URL 类先做基本校验：写错了会让每次生图都失败，宁可在保存时拦住
        for k in ("llm_base_url", "gen_base_url"):
            if k in changes:
                v = str(changes[k] or "").strip()
                if v and not v.lower().startswith(("http://", "https://")):
                    return self.err(f"{k} 必须是 http(s):// 开头的完整地址")
                changes[k] = v.rstrip("/")
        for k in ("llm_source",):
            if k in changes and str(changes[k]).strip().lower() not in ("astrbot", "custom"):
                return self.err("llm_source 只能是 astrbot 或 custom")

        # 换参考图路径前先校验：不合格的路径会让每次生图都丢掉形象锁
        new_ref = changes.get("reference_image")
        if isinstance(new_ref, str) and new_ref.strip():
            okf, why = await asyncio.to_thread(imaging.check_ref, new_ref.strip())
            if not okf:
                return self.err(f"这个路径不能当参考图（{why}）；要换图请用「角色参考图」页上传")
            changes["reference_image"] = new_ref.strip()
        if "search_min_px" in changes:
            try:
                if int(changes["search_min_px"]) < imaging.MIN_SIDE:
                    return self.err(f"search_min_px 不能低于 {imaging.MIN_SIDE}："
                                    f"短边过小的图会让整次图生图报 InvalidParameter")
            except (TypeError, ValueError):
                return self.err("search_min_px 必须是整数")

        applied = await asyncio.to_thread(p.site.update, changes)
        if "provider_source_id" in applied:
            p.client.source_id = str(p._c("provider_source_id", "bailian"))
        msg = f"已保存 {len(applied)} 项（即时生效，存在 plugin_data/site.json）"
        if any(k in applied for k in NEEDS_RELOAD):
            msg += "；provider_source_id 已同步到运行中的客户端"
        if not applied:
            msg = "没有需要保存的改动（密钥留空视为不修改）"
        return self.ok({"applied": applied,
                        "conn": await asyncio.to_thread(p.client.conn_info, p._c)}, msg)

    # ---------------- 模型连接（v0.9.0） ----------------

    async def conn_info(self):
        """连接解析结果：LLM 跟随谁、生图配没配、密钥打码、能不能图生图。"""
        p = self.plugin
        info = await asyncio.to_thread(p.client.conn_info, p._c)
        info["secrets"] = {k: mask(p._c(k, "")) for k in
                           ("llm_api_key", "gen_api_key") if k in EDITABLE}
        info["llm_source"] = str(p._c("llm_source", "astrbot"))
        info["site_path"] = p.site.path
        info["overridden"] = p.site.overridden()
        return self.ok(info)

    async def test_conn(self):
        """连通性自测：LLM 发一句极短的 chat；生图只 GET /models（都不烧生图额度）。"""
        from astrbot.api.web import request
        body = await request.json(default={}) or {}
        which = str(body.get("which") or "llm").strip().lower()
        p = self.plugin
        if which == "gen":
            conn = await asyncio.to_thread(p.client.resolve_gen, p._c)
            r = await asyncio.to_thread(p.client.test_gen, conn)
        elif which == "llm":
            conn = await asyncio.to_thread(p.client.resolve_llm, p._c)
            r = await asyncio.to_thread(p.client.test_llm, conn)
        else:
            return self.err("which 只能是 llm 或 gen")
        r["which"] = which
        r["label"] = conn.get("label", "")
        r["base"] = conn.get("base", "")
        r["key_masked"] = mask(conn.get("key", ""))
        return (self.ok(r, "连通" if r.get("ok") else "不通")
                if r.get("ok") else self.ok(r, str(r.get("error") or "不通")))

    async def get_models(self):
        """列模型：which=gen（默认）用生图连接，which=llm 用语言模型连接。"""
        from astrbot.api.web import request
        which = str(request.query.get("which", "gen") or "gen").strip().lower()
        p = self.plugin

        def go():
            conn = (p.client.resolve_gen(p._c) if which == "gen"
                    else p.client.resolve_llm(p._c))
            if not conn.get("ok"):
                return None, conn.get("why") or "连接未配置"
            return p.client.list_models(conn.get("key", ""), conn.get("base", "")), ""

        try:
            models, why = await asyncio.to_thread(go)
        except Exception as e:
            return self.err(f"查询模型失败: {e}")
        if models is None:
            return self.err(why)
        return self.ok({"models": models, "which": which, "count": len(models)})

    # ---------------- 参考图 ----------------

    def _ref_info_sync(self):
        p = self.plugin
        card = p._card()
        out = {}
        for tag, path in (("card", card), ("sheet", p.paths["sheet"])):
            if os.path.isfile(path):
                okf, why = imaging.check_ref(path)
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(path) as im:
                        w, h = im.size
                        fmt = im.format
                except Exception:
                    w = h = 0
                    fmt = "?"
                out[tag] = {"path": path, "w": w, "h": h, "fmt": fmt,
                            "bytes": os.path.getsize(path), "ok": okf, "why": why,
                            "b64": imaging.thumb_b64(path, 320)}
            else:
                out[tag] = {"path": path, "exists": False}
        return out

    async def ref_info(self):
        return self.ok(await asyncio.to_thread(self._ref_info_sync))

    async def ref_upload(self):
        from astrbot.api.web import request
        files = await request.files()
        f = files.get("file")
        if f is None:
            return self.err("没有收到文件（字段名应为 file）")
        p = self.plugin
        tmp = os.path.join(p.paths["tmp"], "upload-" + time.strftime("%H%M%S") + ".jpg")
        await asyncio.to_thread(os.makedirs, os.path.dirname(tmp), exist_ok=True)
        await f.save(tmp)

        def commit():
            okf, why = imaging.check_ref(tmp)
            if not okf:
                if os.path.isfile(tmp):
                    os.remove(tmp)
                return False, why
            card = p._card()
            os.makedirs(os.path.dirname(card), exist_ok=True)
            os.replace(tmp, card)
            return True, card

        okf, info = await asyncio.to_thread(commit)
        if not okf:
            return self.err(f"上传的图不能当参考图: {info}")
        return self.ok({"path": info}, "角色参考图已更换，下一次生图即生效")

    async def ref_card(self):
        from astrbot.api.web import request
        body = await request.json(default={}) or {}
        p = self.plugin
        sheet = p.paths["sheet"]
        if not os.path.isfile(sheet):
            return self.err("容器里没有三视图源稿 character_ref.jpg，无法重裁")
        crop = body.get("crop") or None
        if crop:
            try:
                crop = tuple(int(x) for x in crop[:4])
            except Exception:
                return self.err("crop 应为 [l,t,r,b] 四个整数")
        okf, info = await asyncio.to_thread(
            imaging.make_identity_card, sheet, p.paths["ref_default"], crop)
        if not okf:
            return self.err(f"裁剪失败: {info}")
        return self.ok({"size": info}, f"身份卡已重裁（{info}），下一次生图即生效")

    # ---------------- 图库 ----------------

    def _gallery_sync(self, limit):
        p = self.plugin
        d = p.paths["outputs"]
        items = []
        if os.path.isdir(d):
            names = sorted((f for f in os.listdir(d) if f.endswith(".png")),
                           key=lambda f: os.path.getmtime(os.path.join(d, f)),
                           reverse=True)[:limit]
            for n in names:
                thumb = imaging.thumb_b64(os.path.join(d, n), 220)
                if not thumb:
                    continue
                rec = p.journal.get(n[:-4]) or {}
                items.append({"name": n, "ts": os.path.getmtime(os.path.join(d, n)),
                              "scene": rec.get("scene", ""),
                              "caption": rec.get("caption", ""),
                              "status": rec.get("status", ""),
                              "tokens": rec.get("tokens_in", 0) + rec.get("tokens_out", 0),
                              "ms": rec.get("ms", 0),
                              "thumb": thumb})
        return items

    async def gallery(self):
        from astrbot.api.web import request
        try:
            limit = min(int(request.query.get("limit", "24") or 24), 100)
        except (TypeError, ValueError):
            limit = 24
        return self.ok({"items": await asyncio.to_thread(self._gallery_sync, limit)})

    async def image(self):
        from astrbot.api.web import request
        name = (request.query.get("name") or "").strip()
        if not name or "/" in name or "\\" in name or ".." in name or not name.endswith(".png"):
            return self.err("非法文件名")
        path = os.path.join(self.plugin.paths["outputs"], name)
        if not os.path.isfile(path):
            return self.err("文件不存在")
        return self.ok({"name": name, "b64": await asyncio.to_thread(imaging.file_b64, path)})

    # ---------------- 考据自测 ----------------

    async def test_enhance(self):
        from astrbot.api.web import request
        body = await request.json(default={}) or {}
        scene = str(body.get("scene") or "").strip()
        caption = str(body.get("caption") or "").strip()
        if not scene:
            return self.err("scene 不能为空")
        p, pipe = self.plugin, self.plugin.pipeline
        try:
            conn = await asyncio.to_thread(p.client.resolve_llm, p._c)
            plan, rec = await asyncio.to_thread(pipe.enhance, scene, caption, conn)
        except Exception as e:
            return self.err(f"考据异常: {e}")
        if plan is None:
            return self.err(f"考据失败: {rec.get('status', 'error')} {rec.get('error', '')}")
        scene_final, fixes = pipe.guard_scene(scene, plan)
        return self.ok({"plan": plan, "fixes": fixes, "scene_final": scene_final,
                        "usage": rec})
