# -*- coding: utf-8 -*-
"""本地生成控制台面板预览（假 bridge + 假数据），用于在浏览器里目检 UI。"""
import base64
import json
import os
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(ROOT, "plugin", "pages", "console")
dst = os.environ.get("WM_PREVIEW_OUT") or os.path.join(ROOT, "_preview")
os.makedirs(dst, exist_ok=True)
for f in ("app.js", "styles.css"):
    shutil.copy(os.path.join(src, f), os.path.join(dst, f))

card = open(os.path.join(ROOT, "assets", "character_front.jpg"), "rb").read()
card_b64 = base64.b64encode(card).decode()
sample = os.environ.get("WM_SAMPLE_PNG") or os.path.join(ROOT, "docs", "img", "sample.png")
out_png = open(sample, "rb").read()
out_b64 = base64.b64encode(out_png).decode()
now = time.time()

canned = {
    "page/stats": {"status": "ok", "message": "", "data": {
        "version": "0.8.0",
        "stats": {"since": now - 3600, "runs": 3, "gens": 3, "ok": 2, "fail": 1,
                  "tokens_in": 45210, "tokens_out": 3120, "tokens": 48330,
                  "images": 2, "avg_ms": 61000},
        "budget_daily": 0, "budget_left": None,
        "card": {"path": "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme/character_front.jpg",
                 "ok": True, "why": "", "exists": True},
        "models": {"gen": "wan2.7-image", "enhance": "deepseek-v4-pro", "verify": "qwen3.8-max"},
        "limits": {"daily": 0, "hourly": 0, "cooldown": 0},
        "usage": [1, 3, 42.0]}},
    "page/ref/info": {"status": "ok", "message": "", "data": {
        "card": {"path": "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme/character_front.jpg",
                 "w": 544, "h": 599, "fmt": "JPEG", "bytes": len(card), "ok": True,
                 "why": "", "b64": card_b64},
        "sheet": {"path": "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme/character_ref.jpg",
                  "w": 1448, "h": 1086, "fmt": "JPEG", "bytes": 319334, "ok": True,
                  "why": "", "b64": card_b64}}},
    "page/runs": {"status": "ok", "message": "", "data": {"total": 3, "offset": 0, "runs": [
        {"id": "20261001-175142-10d6", "ts": now - 600, "trigger": "cmd", "session": "123456",
         "scene": "明日方舟的斯卡蒂抱着鲸鱼玩偶发呆", "caption": "摸鱼中", "status": "ok", "error": "",
         "tokens_in": 21987, "tokens_out": 2480, "images": 1, "ms": 61056,
         "refs": ["character_front.jpg", "ref_0_baidu.jpg", "ref_1_baidu.jpg"],
         "fixes": [], "names": ["斯卡蒂", "Skadi", "スカジ"], "out": "20261001-175142-10d6.png"},
        {"id": "20261001-170000-abcd", "ts": now - 3600, "trigger": "tool", "session": "",
         "scene": "偷吃被发现，嘴里塞满饼干", "caption": "", "status": "ok", "error": "",
         "tokens_in": 9412, "tokens_out": 301, "images": 1, "ms": 45210,
         "refs": ["character_front.jpg"], "fixes": [], "names": [], "out": "20261001-170000-abcd.png"},
        {"id": "20261001-160000-ef01", "ts": now - 7200, "trigger": "cmd", "session": "123456",
         "scene": "抱着键盘加班到深夜", "caption": "", "status": "failed",
         "error": "生图失败（调用阶梯全部失败，见 gen 明细）", "tokens_in": 1203, "tokens_out": 0,
         "images": 0, "ms": 30012, "refs": [], "fixes": [], "names": [], "out": ""}]}},
    "page/run/20261001-175142-10d6": {"status": "ok", "message": "", "data": {
        "id": "20261001-175142-10d6", "ts": now - 600, "kind": "gen", "trigger": "cmd",
        "session": "123456", "scene": "明日方舟的斯卡蒂抱着鲸鱼玩偶发呆", "caption": "摸鱼中",
        "status": "ok", "error": "",
        "enhance": {"model": "deepseek-v4-pro", "in": 1203, "out": 604, "images": 0,
                    "status": "ok", "ms": 14100},
        "search": {"queries": ["明日方舟 斯卡蒂 立绘"], "candidates": 49, "downloaded": 8,
                   "kept": 2, "ms": 28000, "in": 691, "out": 760, "model": "qwen3.8-max",
                   "checked": 4},
        "refs": ["character_front.jpg", "ref_0_baidu.jpg", "ref_1_baidu.jpg"],
        "gen": [{"kind": "char+assets", "refs": 3, "in": 20087, "out": 2, "images": 1,
                 "status": "ok", "ms": 7892}],
        "tokens_in": 21987, "tokens_out": 2480, "images": 1, "ms": 61056,
        "fixes": [], "names": ["斯卡蒂", "Skadi", "スカジ"],
        "out": "20261001-175142-10d6.png",
        "prompt": "固定角色设定，本次与以后每次生图都必须严格遵守，禁止改动：Q版二头身鲸鱼娘少女。……用户原始要求（最高优先级，必须全部体现，不得省略）：明日方舟的斯卡蒂抱着鲸鱼玩偶发呆。图上文字：摸鱼中。",
        "llm_prompt": "Q版二头身少女，穿着明日方舟斯卡蒂的服装，双手抱着一个蓝色鲸鱼玩偶，发呆无表情。"}},
    "page/config": {"status": "ok", "message": "", "data": {
        "config": {"model": "wan2.7-image", "size": "1024*1024", "use_reference": True,
                   "reference_image": "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme/character_front.jpg",
                   "max_refs": 3, "allow_text_fallback": False, "max_prompt_chars": 400,
                   "keep_outputs_max": 60, "keep_assets": False, "keep_tmp_days": 3,
                   "enhance_enabled": True, "enhance_model": "deepseek-v4-pro",
                   "enhance_temperature": 0.15, "enhance_thinking": True,
                   "enhance_json_mode": True, "enhance_timeout_sec": 240,
                   "enhance_for_llm_tool": False, "asset_enabled": True,
                   "search_enabled": True, "search_order": "baidu,360,bing",
                   "search_cookie_warmup": True, "search_refs": 2, "search_query_max": 3,
                   "search_candidates": 8, "search_min_px": 400, "search_timeout_sec": 12,
                   "search_fallback_asset": True, "verify_enabled": True,
                   "verify_model": "qwen3.8-max", "verify_max_images": 4,
                   "verify_thumb_px": 256, "verify_timeout_sec": 300,
                   "daily_limit": 0, "hourly_limit": 0, "cooldown_sec": 0,
                   "command_bypass_cooldown": True, "token_budget_daily": 0,
                   "reply_detail": "full", "ack_text": "收到，开始执行",
                   "verbose_progress": False,
                   "character_dna": "固定角色设定，本次与以后每次生图都必须严格遵守，禁止改动：Q版二头身鲸鱼娘少女。深蓝色蓬松长卷发及腰。",
                   "style_prefix": "Q版chibi表情包，干净简洁的浅色背景，构图居中，线条清晰，配色明快"},
        "hints": {
            "model": {"description": "生图模型", "hint": "token-plan 套餐下实测可用的是 wan2.7-image / wan2.7-image-pro。", "type": "string"},
            "search_min_px": {"description": "素材图最小边长（像素）", "hint": "过滤掉缩略图标；低于 400 会让整次图生图报 InvalidParameter。", "type": "int"},
            "character_dna": {"description": "角色 DNA", "hint": "每次生图都会拼在提示词最前面。", "type": "text"},
            "enhance_temperature": {"description": "考据温度", "hint": "", "type": "float"},
            "reply_detail": {"description": "QQ 解析详细度", "hint": "", "type": "string"},
            "daily_limit": {"description": "每日最多生成张数", "hint": "0 = 不限", "type": "int"},
            "token_budget_daily": {"description": "每日 token 预算", "hint": "0 = 不限", "type": "int"},
            "ack_text": {"description": "接单回执文案", "hint": "", "type": "string"},
            "use_reference": {"description": "启用参考图图生图", "hint": "", "type": "bool"},
            "keep_assets": {"description": "保留素材临时文件", "hint": "", "type": "bool"},
            "keep_tmp_days": {"description": "素材临时目录保留天数", "hint": "", "type": "int"},
            "max_refs": {"description": "单次生图最多喂几张参考图", "hint": "", "type": "int"},
            "allow_text_fallback": {"description": "允许纯文生图兜底", "hint": "默认关：没参考图就直接失败，避免主角漂移。", "type": "bool"},
            "enhance_thinking": {"description": "优化时开启深度思考", "hint": "", "type": "bool"},
            "enhance_json_mode": {"description": "考据强制 JSON 输出", "hint": "", "type": "bool"},
            "verify_enabled": {"description": "用多模态模型核对搜到的图", "hint": "", "type": "bool"},
            "search_enabled": {"description": "联网搜真实素材图", "hint": "", "type": "bool"},
            "verbose_progress": {"description": "过程消息", "hint": "", "type": "bool"},
            "command_bypass_cooldown": {"description": "命令触发时跳过间隔限制", "hint": "", "type": "bool"},
            "enhance_for_llm_tool": {"description": "群里自主触发生图时也做优化", "hint": "", "type": "bool"},
            "search_cookie_warmup": {"description": "搜图前先做 Cookie 预热", "hint": "", "type": "bool"},
            "search_fallback_asset": {"description": "搜不到时改为自绘素材图", "hint": "", "type": "bool"},
            "enhance_enabled": {"description": "/生图 是否先让大模型优化提示词", "hint": "", "type": "bool"},
            "asset_enabled": {"description": "允许先单独生成道具素材参考图", "hint": "", "type": "bool"}},
        "editable": []}},
    "page/models": {"status": "ok", "message": "", "data": {"models": [
        "auto", "deepseek-v4-flash-0731", "deepseek-v4-pro", "deepseek-v4.1-flash",
        "glm-5.2", "glm-5.3", "qwen3.6-flash", "qwen3.7-max", "qwen3.7-plus",
        "qwen3.8-flash", "qwen3.8-max", "wan2.7-image", "wan2.7-image-pro"]}},
    "page/gallery": {"status": "ok", "message": "", "data": {"items": [
        {"name": "20261001-175142-10d6.png", "ts": now - 600,
         "scene": "明日方舟的斯卡蒂抱着鲸鱼玩偶发呆", "caption": "摸鱼中", "status": "ok",
         "tokens": 24467, "ms": 61056, "thumb": card_b64},
        {"name": "20261001-170000-abcd.png", "ts": now - 3600,
         "scene": "偷吃被发现，嘴里塞满饼干", "caption": "", "status": "ok",
         "tokens": 9713, "ms": 45210, "thumb": card_b64}]}},
    "page/image": {"status": "ok", "message": "", "data": {
        "name": "20261001-175142-10d6.png", "b64": out_b64}},
    "page/test/enhance": {"status": "ok", "message": "", "data": {
        "plan": {"analysis": "用户想画明日方舟的斯卡蒂，需要考据服装要素。",
                 "entities": [{"raw": "斯卡蒂", "canonical_cn": "斯卡蒂", "canonical_en": "Skadi",
                               "canonical_jp": "スカジ", "work": "明日方舟", "confidence": 0.98,
                               "note": "本体立绘为白发黑帽巨剑"}],
                 "visual_traits": "黑色立领长外套，红色内衬", "needs_asset": True,
                 "search_queries": ["明日方舟 斯卡蒂 立绘"],
                 "prompt": "Q版二头身少女穿着斯卡蒂服装抱鲸鱼玩偶发呆。",
                 "asset_prompt": "明日方舟斯卡蒂服装，白底"},
        "fixes": [], "scene_final": "明日方舟的斯卡蒂抱着鲸鱼玩偶发呆",
        "usage": {"model": "deepseek-v4-pro", "in": 1203, "out": 604, "ms": 14100}}},
}

STUB = """
<script>
window.__CANNED = %s;
window.AstrBotPluginPage = {
  ready: function(){ return Promise.resolve({isDark:false, locale:"zh-CN"}); },
  getContext: function(){ return {isDark:false, locale:"zh-CN"}; },
  getLocale: function(){ return "zh-CN"; },
  t: function(k,f){ return f||k; },
  onContext: function(){ return function(){}; },
  apiGet: function(ep, params){
    var d = window.__CANNED[ep];
    if (d) return Promise.resolve(JSON.parse(JSON.stringify(d)));
    return Promise.resolve({status:"error", message:"stub: no canned data for "+ep, data:{}});
  },
  apiPost: function(ep, body){
    var d = window.__CANNED[ep];
    if (d) return Promise.resolve(JSON.parse(JSON.stringify(d)));
    return Promise.resolve({status:"ok", message:"(stub) "+ep+" 已接受",
      data:{applied:Object.keys((body&&body.changes)||{})}});
  },
  upload: function(ep, file){
    return Promise.resolve({status:"ok", message:"(stub) 已上传 "+(file&&file.name), data:{}});
  },
  download: function(){ return Promise.resolve({}); },
  subscribeSSE: function(){ return Promise.resolve("s"); },
  unsubscribeSSE: function(){ return Promise.resolve({}); }
};
</script>
""" % json.dumps(canned, ensure_ascii=False)

html = open(os.path.join(src, "index.html"), encoding="utf-8").read()
# 与真控制台一致：桥脚本在 app.js 之后注入（dashboard 把它插到 </body> 前），
# 这样本地预览能复现「app.js 先跑、桥后到」的时序，回归 waitBridge 轮询逻辑。
html = html.replace('<script src="./app.js"></script>',
                    '<script src="./app.js"></script>' + STUB)
open(os.path.join(dst, "index.html"), "w", encoding="utf-8").write(html)
print("preview written:", sorted(os.listdir(dst)))
