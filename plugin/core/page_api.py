# -*- coding: utf-8 -*-
"""控制台面板后端：注册 /astrbot_plugin_whalechan_meme/page/* 路由。v0.8.0

前端是插件自带的 pages/console/（AstrBot 控制台会自动发现并挂进侧边栏），
通过 window.AstrBotPluginPage.apiGet / apiPost / upload 访问这里的路由。
控制台会把 endpoint 拼成 /api/v1/plugins/extensions/<metadata.name>/<endpoint>，
所以注册的 route 必须以 metadata.yaml 里的 name 开头。

返回约定：{"status":"ok"|"error","message":...,"data":...}
所有会阻塞的活（读 JSONL、PIL 缩图、requests 出网）都走 asyncio.to_thread，
不许卡 AstrBot 的事件循环——卡住会连带 QQ 消息一起卡。
"""
from __future__ import annotations

import asyncio
import json
import os
import time

from . import imaging
from .prompts import PLUGIN_NAME

PAGE_PREFIX = f"/{PLUGIN_NAME}/page"

# 允许在面板里改的配置键（其余键只能改 _conf_schema.json）
# 故意不开放：provider_source_id（客户端启动时读取，改了要重启才生效）、
#            enable、group_whitelist（属于开关面板职责）。
EDITABLE = {
    "model", "size", "use_reference", "max_refs", "allow_text_fallback",
    "reference_image", "max_prompt_chars", "keep_assets", "keep_outputs_max",
    "keep_tmp_days",
    "enhance_enabled", "enhance_model", "enhance_temperature", "enhance_thinking",
    "enhance_json_mode", "enhance_timeout_sec", "enhance_for_llm_tool",
    "asset_enabled", "search_enabled", "search_order", "search_cookie_warmup",
    "search_refs", "search_min_px", "search_query_max", "search_candidates",
    "search_timeout_sec", "search_fallback_asset",
    "verify_enabled", "verify_model", "verify_max_images", "verify_thumb_px",
    "verify_timeout_sec",
    "daily_limit", "hourly_limit", "cooldown_sec", "command_bypass_cooldown",
    "token_budget_daily", "reply_detail", "verbose_progress", "ack_text",
    "character_dna", "style_prefix",
}


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
        card = str(p._c("reference_image", p.paths["ref_default"]))
        cok, cwhy = imaging.check_ref(card)
        return {
            "version": p.version,
            "stats": st,
            "budget_daily": budget,
            "budget_left": (budget - st["tokens"]) if budget > 0 else None,
            "card": {"path": card, "ok": cok, "why": cwhy,
                     "exists": os.path.isfile(card)},
            "models": {"gen": p._c("model", ""), "enhance": p._c("enhance_model", ""),
                       "verify": p._c("verify_model", "")},
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
        data = {k: p._c(k, None) for k in sorted(EDITABLE)}
        schema = await asyncio.to_thread(p._read_schema) or {}
        hints = {}
        for k, v in schema.items():
            if isinstance(v, dict):
                hints[k] = {"description": v.get("description", ""),
                            "hint": v.get("hint", ""), "type": v.get("type", "")}
        return self.ok({"config": data, "hints": hints, "editable": sorted(EDITABLE)})

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

        def apply():
            schema = p._read_schema()
            if not schema:
                return None
            applied = []
            for k, v in changes.items():
                if k not in schema:
                    continue
                schema[k]["default"] = v
                p.conf[k] = v          # 运行期立即生效
                applied.append(k)
            if applied and not p._write_schema(schema):
                return False
            return applied

        applied = await asyncio.to_thread(apply)
        if applied is None:
            return self.err("读不到 _conf_schema.json")
        if applied is False:
            return self.err("写入 _conf_schema.json 失败")
        return self.ok({"applied": applied}, f"已应用 {len(applied)} 项（即时生效）")

    async def get_models(self):
        try:
            models = await asyncio.to_thread(self.plugin.client.list_models)
        except Exception as e:
            return self.err(f"查询模型失败: {e}")
        return self.ok({"models": models})

    # ---------------- 参考图 ----------------

    def _ref_info_sync(self):
        p = self.plugin
        card = str(p._c("reference_image", p.paths["ref_default"]))
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
            card = str(p._c("reference_image", p.paths["ref_default"]))
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
        pipe = self.plugin.pipeline
        try:
            plan, rec = await asyncio.to_thread(pipe.enhance, scene, caption)
        except Exception as e:
            return self.err(f"考据异常: {e}")
        if plan is None:
            return self.err(f"考据失败: {rec.get('status', 'error')} {rec.get('error', '')}")
        scene_final, fixes = pipe.guard_scene(scene, plan)
        return self.ok({"plan": plan, "fixes": fixes, "scene_final": scene_final,
                        "usage": rec})
