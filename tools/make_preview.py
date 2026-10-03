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

# 预览两种装机状态：
#   默认 = 生图连接已配好（老用户升级后的样子）
#   WM_PREVIEW_FRESH=1 = 生图连接没配（新用户第一次打开面板的样子，会自动跳到「模型连接」页）
FRESH = bool(os.environ.get("WM_PREVIEW_FRESH"))
GEN_BASE = "" if FRESH else \
    "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
GEN_KEY_MASKED = "" if FRESH else "sk-****7a"
OVERRIDDEN = [] if FRESH else ["gen_api_key", "gen_base_url", "model"]

canned = {
    "page/stats": {"status": "ok", "message": "", "data": {
        "version": "0.9.1",
        "stats": {"since": now - 3600, "runs": 3, "gens": 3, "ok": 2, "fail": 1,
                  "tokens_in": 45210, "tokens_out": 3120, "tokens": 48330,
                  "images": 2, "avg_ms": 61000},
        "budget_daily": 0, "budget_left": None,
        "card": {"path": "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme/character_front.jpg",
                 "ok": True, "why": "", "exists": True},
        "models": {"gen": "wan2.7-image", "enhance": "", "verify": ""},
        "conn": {"llm_ok": True, "gen_ok": bool(GEN_BASE),
                 "llm_label": "astrbot:bailian/qwen3.8-flash",
                 "gen_label": "panel" if GEN_BASE else "none",
                 "llm_model": "qwen3.8-flash", "gen_model": "wan2.7-image",
                 "i2i": bool(GEN_BASE),
                 "why": "" if GEN_BASE else
                 "生图连接未配置：请在面板「模型连接」填写生图 URL 与 API Key"},
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
        "config": {"llm_source": "astrbot", "llm_base_url": "", "llm_api_key": "",
                   "llm_model": "", "gen_base_url": GEN_BASE, "gen_api_key": "",
                   "provider_source_id": "bailian",
                   "model": "wan2.7-image", "size": "1024*1024", "use_reference": True,
                   "reference_image": "",
                   "max_refs": 3, "allow_text_fallback": False, "max_prompt_chars": 400,
                   "keep_outputs_max": 60, "keep_assets": False, "keep_tmp_days": 3,
                   "enhance_enabled": True, "enhance_model": "",
                   "enhance_temperature": 0.15, "enhance_thinking": True,
                   "enhance_json_mode": True, "enhance_timeout_sec": 240,
                   "enhance_for_llm_tool": False, "asset_enabled": True,
                   "search_enabled": True, "search_order": "baidu,360,bing",
                   "search_cookie_warmup": True, "search_refs": 2, "search_query_max": 3,
                   "search_candidates": 8, "search_min_px": 400, "search_timeout_sec": 12,
                   "search_fallback_asset": True, "verify_enabled": True,
                   "verify_model": "", "verify_max_images": 4,
                   "verify_thumb_px": 256, "verify_timeout_sec": 300,
                   "daily_limit": 0, "hourly_limit": 0, "cooldown_sec": 0,
                   "command_bypass_cooldown": True, "token_budget_daily": 0,
                   "reply_detail": "full", "ack_text": "收到，开始执行",
                   "verbose_progress": False,
                   "character_dna": "固定角色设定，本次与以后每次生图都必须严格遵守，禁止改动：Q版二头身鲸鱼娘少女。深蓝色蓬松长卷发及腰。",
                   "style_prefix": "Q版chibi表情包，干净简洁的浅色背景，构图居中，线条清晰，配色明快"},
        "secrets": {"llm_api_key": "", "gen_api_key": GEN_KEY_MASKED},
        "overridden": OVERRIDDEN,
        "site_path": "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme/site.json",
        "hints": {
            "llm_source": {"description": "语言模型（考据/核对）连接来源", "hint": "astrbot=跟随 AstrBot 当前聊天模型（零配置，推荐）；custom=用下面自己填的 URL 与 API Key。", "type": "string"},
            "llm_base_url": {"description": "自定义 LLM 接口地址", "hint": "OpenAI 兼容地址，写到 /v1 为止。仅 llm_source=custom 时使用。", "type": "string"},
            "llm_api_key": {"description": "自定义 LLM 的 API Key", "hint": "面板里打码显示；保存在 plugin_data/site.json，插件升级不会丢。", "type": "string"},
            "llm_model": {"description": "LLM 模型名（留空=完全跟随）", "hint": "留空时用 AstrBot 聊天模型；填了就只覆盖模型名。", "type": "string"},
            "gen_base_url": {"description": "生图接口地址", "hint": "百炼 token-plan：https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1（支持图生图形象锁）。其它 OpenAI 兼容地址只能纯文生图。", "type": "string"},
            "gen_api_key": {"description": "生图接口的 API Key", "hint": "必填（除非沿用 provider_source_id 兜底）。", "type": "string"},
            "provider_source_id": {"description": "兼容兜底：取用哪个 provider_source", "hint": "v0.9 起只作兜底：gen_base_url/gen_api_key 没填时才用它。", "type": "string"},
            "model": {"description": "生图模型名", "hint": "必须是你生图接口上真实存在的模型名。", "type": "string"},
            "size": {"description": "图片尺寸", "hint": "百炼用星号格式，如 1024*1024。", "type": "string"},
            "enhance_model": {"description": "负责考据的语言模型（留空=跟随 LLM 连接）", "hint": "百炼用户可填 deepseek-v4-pro / qwen3.8-max 提精度。", "type": "string"},
            "verify_model": {"description": "核对用的多模态模型（留空=跟随 LLM 连接）", "hint": "必须支持图片输入；读不了图会自动跳过核对。", "type": "string"},
            "reference_image": {"description": "角色身份卡路径（留空=用默认卡）", "hint": "留空最稳，自动跟随数据目录。", "type": "string"},
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
            "max_prompt_chars": {"description": "考据提示词子句截断长度", "hint": "", "type": "int"},
            "keep_outputs_max": {"description": "图库保留成品张数", "hint": "", "type": "int"},
            "style_prefix": {"description": "画风前缀", "hint": "", "type": "text"},
            "search_query_max": {"description": "最多尝试几组关键词", "hint": "", "type": "int"},
            "search_candidates": {"description": "候选池大小", "hint": "", "type": "int"},
            "search_timeout_sec": {"description": "单次搜索/下载超时", "hint": "", "type": "int"},
            "search_refs": {"description": "最多用几张素材图", "hint": "", "type": "int"},
            "verify_max_images": {"description": "最多核对几张候选图", "hint": "", "type": "int"},
            "verify_thumb_px": {"description": "核对时缩图边长", "hint": "", "type": "int"},
            "verify_timeout_sec": {"description": "核对超时秒数", "hint": "", "type": "int"},
            "enhance_timeout_sec": {"description": "考据超时秒数", "hint": "", "type": "int"},
            "hourly_limit": {"description": "每小时上限", "hint": "", "type": "int"},
            "cooldown_sec": {"description": "两张之间最小间隔", "hint": "", "type": "int"},
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
    "page/conn/info": {"status": "ok", "message": "", "data": {
        "llm": {"ok": True, "label": "astrbot:bailian/qwen3.8-flash",
                "model": "qwen3.8-flash",
                "base": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                "key_masked": "sk-****v4", "dialect": "openai", "why": ""},
        "gen": {"ok": bool(GEN_BASE), "label": "panel" if GEN_BASE else "none",
                "model": "wan2.7-image", "base": GEN_BASE,
                "key_masked": GEN_KEY_MASKED,
                "dialect": "bailian" if GEN_BASE else "openai",
                "why": "" if GEN_BASE else "生图连接未配置：请在面板「模型连接」填写生图 URL 与 API Key"},
        "astrbot_chat": {"provider_id": "bailian/qwen3.8-flash", "model": "qwen3.8-flash",
                         "base": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
                         "key_masked": "sk-****v4"},
        "i2i_supported": bool(GEN_BASE),
        "secrets": {"llm_api_key": "", "gen_api_key": GEN_KEY_MASKED},
        "llm_source": "astrbot",
        "site_path": "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme/site.json",
        "overridden": OVERRIDDEN}},
    "page/test/conn:llm": {"status": "ok", "message": "连通", "data": {
        "ok": True, "which": "llm", "stage": "chat", "status": "ok",
        "model": "qwen3.8-flash", "label": "astrbot:bailian/qwen3.8-flash",
        "base": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "key_masked": "sk-****v4", "error": "", "ms": 812, "in": 18, "out": 2,
        "reply": "在线"}},
    "page/test/conn:gen": {"status": "ok", "message": "连通", "data": {
        "ok": bool(GEN_BASE), "which": "gen",
        "stage": "models" if GEN_BASE else "resolve",
        "status": "http200" if GEN_BASE else "resolve",
        "model": "wan2.7-image", "listed": bool(GEN_BASE), "models": 42 if GEN_BASE else 0,
        "dialect": "bailian" if GEN_BASE else "openai", "i2i": bool(GEN_BASE),
        "note": "" if GEN_BASE else "还没填生图地址与 Key", "ms": 640,
        "label": "panel" if GEN_BASE else "none",
        "base": GEN_BASE, "key_masked": GEN_KEY_MASKED,
        "error": "" if GEN_BASE else "生图连接未配置：请在面板「模型连接」填写生图 URL 与 API Key"}},
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

// --- 迷你后端：把面板保存的改动真的算一遍，好回归「保存 → 状态卡」这条链 ---
function simMask(v){ v = String(v||""); return v.length > 8 ? v.slice(0,3)+"****"+v.slice(-2) : (v?"****":""); }
function simDialect(b){ b = String(b||"").toLowerCase();
  return (b.indexOf("dashscope")>=0 || b.indexOf("aliyuncs")>=0 ||
          b.indexOf("/compatible-mode")>=0 || b.indexOf("maas.")>=0) ? "bailian" : "openai"; }
function simConn(cfgd){
  var c = cfgd.config, s = cfgd.secrets || {};
  var chat = (window.__CANNED["page/conn/info"].data || {}).astrbot_chat || null;
  var src = String(c.llm_source || "astrbot");
  var llm;
  if (src === "custom" && c.llm_base_url && s.llm_api_key) {
    llm = {ok:true, label:"custom", model:c.llm_model || (chat||{}).model || "",
           base:c.llm_base_url, key_masked:simMask(s.llm_api_key), dialect:"openai", why:""};
  } else if (chat) {
    llm = {ok:true, label:"astrbot:"+chat.provider_id, model:c.llm_model || chat.model,
           base:chat.base, key_masked:chat.key_masked, dialect:"openai", why:""};
  } else {
    llm = {ok:false, label:"none", model:c.llm_model||"", base:"", key_masked:"",
           dialect:"openai", why:"LLM 连接不可用：既没解析到 AstrBot 聊天模型，也没有可用 provider_source"};
  }
  var gen;
  if (c.gen_base_url && s.gen_api_key) {
    gen = {ok:true, label:"panel", model:c.model||"", base:c.gen_base_url,
           key_masked:simMask(s.gen_api_key), dialect:simDialect(c.gen_base_url), why:""};
  } else if (c.gen_base_url || s.gen_api_key) {
    gen = {ok:false, label:"panel", model:c.model||"", base:c.gen_base_url||"",
           key_masked:simMask(s.gen_api_key), dialect:simDialect(c.gen_base_url),
           why:"生图连接不完整：URL 与 API Key 必须同时填写"};
  } else {
    gen = {ok:false, label:"none", model:c.model||"", base:"", key_masked:"", dialect:"openai",
           why:"生图连接未配置：请在面板「模型连接」填写生图 URL 与 API Key"};
  }
  return {llm:llm, gen:gen, astrbot_chat:chat, i2i_supported: gen.dialect === "bailian",
          llm_source: src, site_path: cfgd.site_path, overridden: cfgd.overridden};
}

window.AstrBotPluginPage = {
  ready: function(){ return Promise.resolve({isDark:false, locale:"zh-CN"}); },
  getContext: function(){ return {isDark:false, locale:"zh-CN"}; },
  getLocale: function(){ return "zh-CN"; },
  t: function(k,f){ return f||k; },
  onContext: function(){ return function(){}; },
  apiGet: function(ep, params){
    var d = window.__CANNED[ep];
    if (!d) return Promise.resolve({status:"error", message:"stub: no canned data for "+ep, data:{}});
    var out = JSON.parse(JSON.stringify(d));
    // 连接状态跟着当前（可能已被保存改过的）配置走，别一直返回出厂值
    if (ep === "page/conn/info") { out.data = simConn(window.__CANNED["page/config"].data); }
    if (ep === "page/stats" && out.data) {
      // page/stats 里的 conn 是扁平摘要（见 page_api._stats_sync），跟 /conn/info 的嵌套结构不同
      var ci = simConn(window.__CANNED["page/config"].data);
      out.data.conn = {llm_ok: ci.llm.ok, gen_ok: ci.gen.ok,
        llm_label: ci.llm.label, gen_label: ci.gen.label,
        llm_model: ci.llm.model, gen_model: ci.gen.model,
        i2i: ci.i2i_supported, why: ci.gen.why || ci.llm.why || ""};
    }
    return Promise.resolve(out);
  },
  apiPost: function(ep, body){
    if (ep === "page/test/conn") {
      var w = (body && body.which) || "llm";
      // 跟着模拟后的连接状态走：没配好返回 resolve 失败，配好了就现造一个成功结果，
      // 别拿出厂 canned 糊弄（保存后再测会自相矛盾）。
      var ci0 = simConn(window.__CANNED["page/config"].data);
      var cur = w === "gen" ? ci0.gen : ci0.llm;
      if (!cur.ok) {
        return Promise.resolve({status:"ok", message:"", data:{
          which:w, ok:false, stage:"resolve", label:cur.label, model:cur.model,
          base:cur.base, key_masked:cur.key_masked, error:cur.why, ms:0}});
      }
      if (w === "gen") {
        var i2i = cur.dialect === "bailian";
        return Promise.resolve({status:"ok", message:"", data:{
          which:"gen", ok:true, stage:"models", status:"http200", model:cur.model,
          listed:true, models:42, dialect:cur.dialect, i2i:i2i,
          note: i2i ? "" : "该接口只能纯文生图，图生图形象锁不可用",
          ms:640, label:cur.label, base:cur.base, key_masked:cur.key_masked, error:""}});
      }
      var t = window.__CANNED["page/test/conn:" + w];
      if (t) return Promise.resolve(JSON.parse(JSON.stringify(t)));
    }
    if (ep === "page/config") {
      var cfgd = window.__CANNED["page/config"].data;
      var ch = (body && body.changes) || {};
      cfgd.secrets = cfgd.secrets || {};
      Object.keys(ch).forEach(function(k){
        var v = ch[k];
        if (k === "llm_api_key" || k === "gen_api_key") {
          if (v === "__CLEAR__") { cfgd.secrets[k] = ""; }
          else if (v) { cfgd.secrets[k] = simMask(v); }   // 空串 = 不修改；存的也是打码值，跟真后端一致
        } else { cfgd.config[k] = v; }
      });
      cfgd.overridden = Object.keys(cfgd.secrets).filter(function(k){ return cfgd.secrets[k]; })
        .concat(Object.keys(ch).filter(function(k){ return k !== "llm_api_key" && k !== "gen_api_key"; }));
      return Promise.resolve({status:"ok", message:"",
        data:{applied:Object.keys(ch), conn:simConn(cfgd)}});
    }
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
print("preview written:", os.path.join(dst, "index.html"))
print("场景:", "全新装机（生图连接未配置，面板会自动跳到「模型连接」）" if FRESH
      else "已配置好生图连接（老用户升级后的样子）")
print("文件:", sorted(os.listdir(dst)))
