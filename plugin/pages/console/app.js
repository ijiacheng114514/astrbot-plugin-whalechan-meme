/* 鲸鱼娘生图 · 控制台面板前端
 * 只依赖 AstrBot 注入的 window.AstrBotPluginPage 桥，无外部库。
 * 后端路由：/astrbot_plugin_whalechan_meme/page/*（桥会自动补插件名前缀，这里只写 "page/xxx"）。
 */
(function () {
  "use strict";

  var bridge = window.AstrBotPluginPage;
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  // ---------------------------------------------------------------- 工具

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function unwrap(res, silent) {
    if (res && res.status === "error") { throw new Error(res.message || "请求失败"); }
    if (res && res.status === "ok" && Object.prototype.hasOwnProperty.call(res, "data")) {
      if (!silent && res.message) { toast(res.message, "ok"); }
      return res.data;
    }
    return res || {};
  }
  function apiGet(path, params) {
    return bridge.apiGet("page/" + path, params || {}).then(function (r) { return unwrap(r, true); });
  }
  function apiPost(path, body) {
    return bridge.apiPost("page/" + path, body || {}).then(function (r) { return unwrap(r); });
  }
  function toast(msg, kind) {
    var wrap = $("#toastWrap");
    var el = document.createElement("div");
    el.className = "toast " + (kind || "");
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(function () { el.style.opacity = "0"; el.style.transition = "opacity .3s"; }, 3600);
    setTimeout(function () { if (el.parentNode) { el.parentNode.removeChild(el); } }, 4000);
  }
  function fmtTs(ts) {
    if (!ts) { return "—"; }
    var d = new Date(ts * 1000);
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return (d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }
  function fmtMs(ms) { return ms ? (ms / 1000).toFixed(1) + "s" : "—"; }
  function fmtTok(n) { return n ? (n / 1000).toFixed(1) + "k" : "0"; }
  function fmtBytes(n) {
    if (!n) { return "0 B"; }
    if (n < 1024) { return n + " B"; }
    if (n < 1048576) { return (n / 1024).toFixed(0) + " KB"; }
    return (n / 1048576).toFixed(2) + " MB";
  }
  function kv(obj) {
    return Object.keys(obj).map(function (k) {
      return "<tr><th>" + esc(k) + "</th><td>" + obj[k] + "</td></tr>";
    }).join("");
  }
  function badge(ok, textOk, textBad) {
    return '<span class="badge ' + (ok ? "ok" : "bad") + '">' + esc(ok ? textOk : textBad) + "</span>";
  }
  function lightbox(src) {
    var lb = $("#lightbox");
    $("img", lb).src = src;
    lb.classList.remove("hidden");
  }

  // ---------------------------------------------------------------- 选项卡

  var LOADER = {};
  var current = "overview";
  var autoTimer = null;

  function switchTab(name) {
    current = name;
    $$(".tab").forEach(function (b) { b.classList.toggle("active", b.dataset.tab === name); });
    $$(".panel").forEach(function (p) { p.classList.toggle("active", p.id === "tab-" + name); });
    load(name);
  }
  function load(name) {
    var fn = LOADER[name || current];
    if (!fn) { return; }
    Promise.resolve()
      .then(fn)
      .catch(function (e) { toast(e && e.message ? e.message : String(e), "err"); });
  }
  function refresh() { load(current); }

  // ---------------------------------------------------------------- 概览

  LOADER.overview = function () {
    return Promise.all([apiGet("stats"), apiGet("ref/info")]).then(function (rs) {
      var d = rs[0], ref = rs[1] || {};
      var st = d.stats || {};
      $("#verTag").textContent = "v" + (d.version || "?");

      var budget = d.budget_daily > 0 ? d.budget_daily : 0;
      var cards = [
        { k: "今日生图", v: (st.gens || 0) + "<small>成功 " + (st.ok || 0) + "</small>" },
        { k: "失败", v: (st.fail || 0), cls: st.fail ? "bad" : "ok" },
        { k: "今日 token", v: fmtTok(st.tokens), cls: budget && st.tokens > budget * 0.8 ? "warn" : "" },
        { k: "输入 / 输出", v: fmtTok(st.tokens_in) + "<small>/ " + fmtTok(st.tokens_out) + "</small>" },
        { k: "平均耗时", v: st.avg_ms ? (st.avg_ms / 1000).toFixed(1) + "<small>s</small>" : "—" },
        { k: "今日预算", v: budget ? fmtTok(budget) : "不限" }
      ];
      $("#statCards").innerHTML = cards.map(function (c) {
        return '<div class="stat ' + (c.cls || "") + '"><div class="k">' + esc(c.k) +
          '</div><div class="v">' + c.v + "</div></div>";
      }).join("");

      var m = d.models || {};
      $("#modelKv").innerHTML = kv({
        "生图模型": "<b>" + esc(m.gen) + "</b>",
        "考据优化模型": esc(m.enhance),
        "素材核对模型": esc(m.verify),
        "近一小时 / 今日出图": (d.usage || [0, 0])[0] + " / " + (d.usage || [0, 0])[1]
      });

      var c = ref.card || {};
      var img = c.b64 ? '<img src="data:image/jpeg;base64,' + c.b64 + '" alt="身份卡">' : "";
      $("#cardBox").innerHTML = img + "<div>" +
        "<div>" + badge(!!c.ok, "可用", "不可用") + " " + (c.exists === false ? '<span class="badge bad">文件不存在</span>' : "") + "</div>" +
        '<div class="meta" style="margin-top:6px">' +
        (c.w ? "<b>" + c.w + "×" + c.h + "</b> · " + esc(c.fmt) + " · " + fmtBytes(c.bytes) + "<br>" : "") +
        esc(c.path || "") +
        (c.ok ? "" : "<br><span style='color:var(--bad)'>" + esc(c.why || "") + "</span>") +
        "</div></div>";

      var L = d.limits || {};
      $("#limitKv").innerHTML = kv({
        "每日上限": L.daily > 0 ? L.daily + " 张" : "不限",
        "每小时上限": L.hourly > 0 ? L.hourly + " 张" : "不限",
        "冷却": L.cooldown > 0 ? L.cooldown + " 秒" : "无",
        "token 预算": budget ? fmtTok(budget) + "／日" +
          (d.budget_left != null ? "（剩 " + fmtTok(Math.max(0, d.budget_left)) + "）" : "") : "不限",
        "身份卡路径": "<code>" + esc(c.path || "") + "</code>"
      });
    });
  };

  // ---------------------------------------------------------------- 运行日志

  LOADER.runs = function () {
    var limit = $("#runLimit").value;
    return apiGet("runs", { limit: limit }).then(function (d) {
      var rows = d.runs || [];
      $("#runCount").textContent = rows.length ? "最近 " + rows.length + " 条" : "";
      var tb = $("#runTable tbody");
      if (!rows.length) {
        tb.innerHTML = '<tr><td colspan="8" class="empty">还没有运行记录。在 QQ 里发 <code>/生图 关键词</code> 试试。</td></tr>';
        return;
      }
      tb.innerHTML = rows.map(function (r) {
        var tok = (r.tokens_in || 0) + (r.tokens_out || 0);
        var st = r.status === "ok" ? '<span class="badge ok">成功</span>'
          : '<span class="badge bad">' + esc(r.error ? "失败" : (r.status || "?")) + "</span>";
        return "<tr data-id='" + esc(r.id) + "'>" +
          "<td class='mono'>" + esc(fmtTs(r.ts)) + "</td>" +
          "<td>" + esc(r.trigger === "tool" ? "自主" : (r.trigger || "cmd")) + "</td>" +
          "<td class='scene' title='" + esc(r.scene) + "'>" + esc(r.scene || "—") + "</td>" +
          "<td>" + st + "</td>" +
          "<td class='mono'>" + esc((r.refs || []).length ? r.refs.length + " 张" : "0") + "</td>" +
          "<td class='mono'>" + fmtTok(tok) + "</td>" +
          "<td class='mono'>" + fmtMs(r.ms) + "</td>" +
          "<td class='mono'>" + (r.out ? "🖼" : "") + "</td></tr>";
      }).join("");
      $$("#runTable tbody tr").forEach(function (tr) {
        tr.addEventListener("click", function () { showRun(tr.dataset.id, tr); });
      });
    });
  };

  function showRun(rid, tr) {
    $$("#runTable tbody tr").forEach(function (x) { x.classList.remove("sel"); });
    if (tr) { tr.classList.add("sel"); }
    var box = $("#runDetail");
    box.classList.remove("hidden");
    box.innerHTML = '<h3>记录 ' + esc(rid) + '</h3><div class="muted"><span class="spin"></span>读取中…</div>';
    apiGet("run/" + encodeURIComponent(rid)).then(function (r) {
      renderRun(box, r);
    }).catch(function (e) {
      box.innerHTML = '<h3>记录 ' + esc(rid) + "</h3><div style='color:var(--bad)'>" + esc(e.message) + "</div>";
    });
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function renderRun(box, r) {
    var h = [];
    h.push('<div class="detail">');
    h.push("<h3>" + esc(r.id) + " " + (r.status === "ok" ? badge(true, "成功", "") : badge(false, "", "失败")) + "</h3>");
    h.push('<table class="kv">' + kv({
      "时间": esc(fmtTs(r.ts)),
      "触发": esc(r.trigger || "") + (r.session ? "（会话 " + esc(r.session) + "）" : ""),
      "画面": esc(r.scene || "") + (r.caption ? " ｜ 文字：" + esc(r.caption) : ""),
      "纠错回拼": (r.fixes || []).length
        ? esc((r.fixes || []).map(function (f) { return f[0] + " → " + f[1]; }).join("、"))
        : "无",
      "识别到的对象": esc((r.names || []).join("、") || "—"),
      "参考图": esc((r.refs || []).join("、") || "无"),
      "token": "输入 " + fmtTok(r.tokens_in) + " ／ 输出 " + fmtTok(r.tokens_out),
      "耗时": fmtMs(r.ms),
      "错误": r.error ? "<span style='color:var(--bad)'>" + esc(r.error) + "</span>" : "—"
    }) + "</table>");

    if (r.prompt) {
      h.push('<div class="sec"><h3>最终提示词</h3><pre>' + esc(r.prompt) + "</pre></div>");
    }
    var e = r.enhance;
    if (e) {
      h.push('<div class="sec"><h3>考据调用</h3><table class="kv">' + kv({
        "模型": esc(e.model || "—"),
        "token": "输入 " + fmtTok(e["in"]) + " ／ 输出 " + fmtTok(e.out),
        "耗时": fmtMs(e.ms),
        "状态": esc(e.status || "ok") + (e.error ? " · " + esc(e.error) : "")
      }) + "</table></div>");
    }
    var s = r.search;
    if (s) {
      h.push('<div class="sec"><h3>搜图与核对</h3><table class="kv">' + kv({
        "关键词": esc((s.queries || []).join(" ｜ ") || "—"),
        "候选 / 下载 / 保留": (s.candidates || 0) + " / " + (s.downloaded || 0) + " / " + (s.kept || 0),
        "核对模型": esc(s.model || "未启用"),
        "核对 token": "输入 " + fmtTok(s["in"]) + " ／ 输出 " + fmtTok(s.out),
        "耗时": fmtMs(s.ms)
      }) + "</table></div>");
    }
    if ((r.gen || []).length) {
      h.push('<div class="sec"><h3>生图调用阶梯</h3>');
      r.gen.forEach(function (a, i) {
        var rn = Array.isArray(a.refs) ? a.refs.length : (a.refs || 0);
        h.push('<div class="attempt ' + (a.status === "ok" ? "ok" : "bad") + '">' +
          "<b>#" + (i + 1) + "</b> " + esc(a.kind || "") + " · 参考图 " + esc(rn) + " 张 · " +
          "in " + fmtTok(a["in"]) + " / out " + fmtTok(a.out) + " · " + fmtMs(a.ms) +
          " · " + (a.status === "ok" ? badge(true, "成功", "") : badge(false, "", a.error || "失败")) +
          "</div>");
      });
      h.push("</div>");
    }
    if (r.out) {
      h.push('<div class="sec"><h3>成品</h3><div id="runImg" class="muted"><span class="spin"></span>载入图片…</div></div>');
    }
    h.push("</div>");
    box.innerHTML = h.join("");
    if (r.out) {
      apiGet("image", { name: r.out }).then(function (d) {
        var host = $("#runImg");
        if (!host) { return; }
        var src = "data:image/png;base64," + d.b64;
        host.innerHTML = '<img class="out" src="' + src + '" alt="成品">';
        $(".out", host).addEventListener("click", function () { lightbox(src); });
      }).catch(function () {
        var host = $("#runImg");
        if (host) { host.textContent = "图片已不在 outputs 目录（可能已被清理）。"; }
      });
    }
  }

  // ---------------------------------------------------------------- 图库

  LOADER.gallery = function () {
    return apiGet("gallery", { limit: $("#galLimit").value }).then(function (d) {
      var items = d.items || [];
      $("#galCount").textContent = items.length ? items.length + " 张" : "";
      var g = $("#galGrid");
      if (!items.length) {
        g.innerHTML = '<div class="empty">还没有成品图。</div>';
        return;
      }
      g.innerHTML = items.map(function (it) {
        return '<div class="gal" data-name="' + esc(it.name) + '">' +
          '<img src="data:image/jpeg;base64,' + it.thumb + '" alt="">' +
          '<div class="cap"><div class="s" title="' + esc(it.scene) + '">' + esc(it.scene || "（无描述）") + "</div>" +
          '<div class="m">' + esc(fmtTs(it.ts)) + " · " + fmtTok(it.tokens) + "</div></div></div>";
      }).join("");
      $$(".gal", g).forEach(function (el) {
        el.addEventListener("click", function () { openFull(el.dataset.name, el); });
      });
    });
  };

  function openFull(name, el) {
    apiGet("image", { name: name }).then(function (d) {
      lightbox("data:image/png;base64," + d.b64);
    }).catch(function (e) { toast(e.message, "err"); });
  }

  // ---------------------------------------------------------------- 设置

  var GROUPS = [
    { t: "生图与形象锁", keys: ["model", "size", "use_reference", "reference_image", "max_refs",
      "allow_text_fallback", "max_prompt_chars", "keep_outputs_max", "keep_assets",
      "keep_tmp_days"] },
    { t: "提示词考据", keys: ["enhance_enabled", "enhance_model", "enhance_temperature",
      "enhance_thinking", "enhance_json_mode", "enhance_timeout_sec", "enhance_for_llm_tool",
      "asset_enabled"] },
    { t: "搜图与核对", keys: ["search_enabled", "search_order", "search_cookie_warmup",
      "search_refs", "search_query_max", "search_candidates", "search_min_px",
      "search_timeout_sec", "search_fallback_asset", "verify_enabled", "verify_model",
      "verify_max_images", "verify_thumb_px", "verify_timeout_sec"] },
    { t: "额度与 token 预算", keys: ["daily_limit", "hourly_limit", "cooldown_sec",
      "command_bypass_cooldown", "token_budget_daily"] },
    { t: "QQ 回复", keys: ["reply_detail", "ack_text", "verbose_progress"] },
    { t: "角色设定文本", wide: true, keys: ["character_dna", "style_prefix"] }
  ];
  var MODEL_KEYS = { model: 1, enhance_model: 1, verify_model: 1 };
  var cfgState = { config: {}, hints: {}, models: [], orig: {} };

  function control(key, val) {
    var type = (cfgState.hints[key] || {}).type || "string";
    if (type === "bool") {
      return '<label class="switch"><input type="checkbox" data-k="' + key + '"' + (val ? " checked" : "") +
        '><span>' + (val ? "开" : "关") + "</span></label>";
    }
    if (key === "reply_detail") {
      return ["full", "short", "none"].map(function (o) {
        return '<label class="switch" style="margin-right:12px"><input type="radio" name="rd" data-k="' + key +
          '" value="' + o + '"' + (String(val) === o ? " checked" : "") + '><span>' +
          ({ full: "完整解析", short: "一行", none: "只发图" }[o]) + "</span></label>";
      }).join("");
    }
    if (MODEL_KEYS[key]) {
      return '<input type="text" list="modelList" data-k="' + key + '" value="' + esc(val) + '">';
    }
    if (type === "text") {
      return '<textarea data-k="' + key + '" rows="' + (key === "character_dna" ? 7 : 3) + '">' + esc(val) + "</textarea>";
    }
    if (type === "int" || type === "float") {
      var step = type === "int" ? "1" : "0.05";
      return '<input type="number" step="' + step + '" data-k="' + key + '" value="' + esc(val) + '">';
    }
    return '<input type="text" data-k="' + key + '" value="' + esc(val) + '">';
  }

  function renderCfg() {
    var html = '<datalist id="modelList">' + cfgState.models.map(function (m) {
      return '<option value="' + esc(m) + '">';
    }).join("") + "</datalist>";
    GROUPS.forEach(function (g) {
      html += '<div class="field' + (g.wide ? " group" : "") + '"><div class="ftitle">' + esc(g.t) + "</div>";
      g.keys.forEach(function (k) {
        if (!(k in cfgState.config)) { return; }
        var hint = cfgState.hints[k] || {};
        html += '<div class="fitem" data-f="' + k + '"><div class="fl"><div class="n">' +
          esc(hint.description || k) + "</div><code>" + esc(k) + "</code></div>" +
          '<div class="fc">' + control(k, cfgState.config[k]) +
          (hint.hint ? '<div class="hint">' + esc(hint.hint) + "</div>" : "") + "</div></div>";
      });
      html += "</div>";
    });
    $("#cfgForm").innerHTML = html;
    bindCfg();
  }

  function readVal(el, key) {
    var type = (cfgState.hints[key] || {}).type || "string";
    if (el.type === "checkbox") { return el.checked; }
    if (el.type === "radio") { return el.value; }
    if (type === "int") { var n = parseInt(el.value, 10); return isNaN(n) ? 0 : n; }
    if (type === "float") { var f = parseFloat(el.value); return isNaN(f) ? 0 : f; }
    return el.value;
  }

  function norm(v) {
    // 数字串与数字视为同值，避免 hints 缺 type 时整表假脏
    if (typeof v === "string" && v !== "" && !isNaN(Number(v))) { return Number(v); }
    return v;
  }

  function dirtyChanges() {
    var changes = {};
    $$("#cfgForm [data-k]").forEach(function (el) {
      var k = el.dataset.k;
      if (el.type === "radio" && !el.checked) { return; }
      var v = readVal(el, k);
      var o = cfgState.orig[k];
      if (JSON.stringify(norm(v)) !== JSON.stringify(norm(o))) { changes[k] = v; }
    });
    return changes;
  }

  function bindCfg() {
    var mark = function () {
      var changes = dirtyChanges();
      $$("#cfgForm .fitem").forEach(function (f) {
        f.classList.toggle("dirty", Object.prototype.hasOwnProperty.call(changes, f.dataset.f));
      });
      $$("#cfgForm .switch span").forEach(function (s) {
        var inp = $("input", s.parentNode);
        if (inp && inp.type === "checkbox") { s.textContent = inp.checked ? "开" : "关"; }
      });
      $("#btnSaveCfg").textContent = Object.keys(changes).length ? "保存（" + Object.keys(changes).length + " 项）" : "保存";
    };
    $$("#cfgForm [data-k]").forEach(function (el) {
      el.addEventListener("input", mark);
      el.addEventListener("change", mark);
    });
    if (cfgState.models.length) { mark(); }
  }

  LOADER.settings = function (keep) {
    return Promise.all([apiGet("config"), apiGet("models").catch(function () { return { models: [] }; })])
      .then(function (rs) {
        cfgState.config = rs[0].config || {};
        cfgState.hints = rs[0].hints || {};
        cfgState.orig = JSON.parse(JSON.stringify(cfgState.config));
        var list = (rs[1] && rs[1].models) || [];
        cfgState.models = list.map(function (m) { return typeof m === "string" ? m : (m.id || m.name || ""); })
          .filter(Boolean);
        if (!cfgState.models.length) {
          cfgState.models = ["wan2.7-image", "wan2.7-image-pro", "deepseek-v4-pro",
            "qwen3.8-max", "qwen3.8-flash"];
        }
        renderCfg();
      });
  };

  function saveCfg() {
    var changes = dirtyChanges();
    var keys = Object.keys(changes);
    if (!keys.length) { toast("没有改动", "warn"); return; }
    if ("search_min_px" in changes && Number(changes.search_min_px) < 400) {
      toast("search_min_px 不能低于 400：小图会让整次图生图报 InvalidParameter", "err");
      return;
    }
    var btn = $("#btnSaveCfg");
    btn.disabled = true;
    apiPost("config", { changes: changes }).then(function () {
      toast("已保存 " + keys.length + " 项：" + keys.join("、"), "ok");
      cfgState.orig = JSON.parse(JSON.stringify(cfgState.config));
      keys.forEach(function (k) { cfgState.config[k] = changes[k]; cfgState.orig[k] = changes[k]; });
      bindCfg();
      load("overview");
    }).catch(function (e) { toast(e.message, "err"); })
      .then(function () { btn.disabled = false; });
  }

  // ---------------------------------------------------------------- 参考图

  function refPane(host, info, tag) {
    if (!info || info.exists === false) {
      host.innerHTML = '<div class="badge bad">文件不存在</div><div class="meta" style="margin-top:6px"><code>' +
        esc((info || {}).path || "") + "</code></div>";
      return;
    }
    host.innerHTML =
      (info.b64 ? '<img src="data:image/jpeg;base64,' + info.b64 + '" alt="' + tag + '">' : "") +
      "<div>" + badge(!!info.ok, "可作参考图", "不能作参考图") + "</div>" +
      '<div class="meta" style="margin-top:6px"><b>' + info.w + "×" + info.h + "</b> · " +
      esc(info.fmt) + " · " + fmtBytes(info.bytes) + "<br><code>" + esc(info.path) + "</code>" +
      (info.ok ? "" : "<br><span style='color:var(--bad)'>" + esc(info.why || "") + "</span>") + "</div>";
    var img = $("img", host);
    if (img) { img.style.cursor = "zoom-in"; img.addEventListener("click", function () { lightbox(img.src); }); }
  }

  LOADER.ref = function () {
    return apiGet("ref/info").then(function (d) {
      refPane($("#refCard"), d.card, "身份卡");
      refPane($("#refSheet"), d.sheet, "三视图");
    });
  };

  function uploadRef() {
    var inp = $("#refFile");
    var file = inp.files && inp.files[0];
    if (!file) { toast("先选一张图", "warn"); return; }
    if (file.size > 8 * 1024 * 1024) { toast("图片超过 8MB，先压一下", "err"); return; }
    var btn = $("#btnUploadRef");
    btn.disabled = true;
    btn.textContent = "上传中…";
    bridge.upload("page/ref/upload", file)
      .then(function (r) { return unwrap(r); })
      .then(function () { inp.value = ""; $("#refFileName").textContent = "把图片拖到这里，或点击选择"; load("ref"); load("overview"); })
      .catch(function (e) { toast(e.message || String(e), "err"); })
      .then(function () { btn.disabled = false; btn.textContent = "上传并替换"; });
  }

  function recrop() {
    var ids = ["#cropL", "#cropT", "#cropR", "#cropB"];
    var vals = ids.map(function (s) { return $(s).value.trim(); });
    var body = {};
    if (vals.every(function (v) { return v !== ""; })) {
      body.crop = vals.map(function (v) { return parseInt(v, 10); });
    } else if (vals.some(function (v) { return v !== ""; })) {
      toast("裁剪框要么四个都填，要么都留空", "warn");
      return;
    }
    apiPost("ref/card", body).then(function () { load("ref"); load("overview"); })
      .catch(function (e) { toast(e.message, "err"); });
  }

  // ---------------------------------------------------------------- 考据自测

  function runProbe() {
    var scene = $("#probeScene").value.trim();
    if (!scene) { toast("先写画面描述", "warn"); return; }
    var btn = $("#btnProbe");
    var out = $("#probeOut");
    btn.disabled = true;
    out.classList.remove("hidden");
    out.innerHTML = '<h3>考据中…</h3><div class="muted"><span class="spin"></span>正在调用优化模型（十几秒到一分钟）</div>';
    apiPost("test/enhance", { scene: scene, caption: $("#probeCaption").value.trim() })
      .then(function (d) {
        var p = d.plan || {};
        var h = ['<div class="detail"><h3>考据结果</h3>'];
        h.push('<table class="kv">' + kv({
          "模型 / token": esc((d.usage || {}).model || "—") + " · in " + fmtTok((d.usage || {})["in"]) +
            " / out " + fmtTok((d.usage || {}).out) + " · " + fmtMs((d.usage || {}).ms),
          "推理": esc(p.analysis || "—"),
          "视觉特征": esc(p.visual_traits || "—"),
          "需要搜参考图": p.needs_asset ? "是" : "否",
          "搜图关键词": esc((p.search_queries || []).join(" ｜ ") || (p.asset_query || "—")),
          "纠错回拼": (d.fixes || []).length
            ? esc(d.fixes.map(function (f) { return f[0] + " → " + f[1]; }).join("、")) : "无"
        }) + "</table>");
        if ((p.entities || []).length) {
          h.push('<div class="sec"><h3>实体考据</h3><table class="kv">' + kv(
            p.entities.reduce(function (acc, e) {
              acc[(e.raw || "?")] = esc(e.canonical_cn || "—") + " ／ " + esc(e.canonical_en || "-") +
                " ／ " + esc(e.canonical_jp || "-") + " · " + esc(e.work || "-") +
                " · 置信度 " + esc(e.confidence) + (e.note ? "<br><span class='muted'>" + esc(e.note) + "</span>" : "");
              return acc;
            }, {})) + "</table></div>");
        }
        h.push('<div class="sec"><h3>模型给出的提示词</h3><pre>' + esc(p.prompt || "—") + "</pre></div>");
        h.push('<div class="sec"><h3>回拼后的用户原话（最高优先级子句）</h3><pre>' + esc(d.scene_final || "") + "</pre></div>");
        if (p.asset_prompt) { h.push('<div class="sec"><h3>道具素材图提示词</h3><pre>' + esc(p.asset_prompt) + "</pre></div>"); }
        h.push("</div>");
        out.innerHTML = h.join("");
      })
      .catch(function (e) { out.innerHTML = '<h3>考据失败</h3><div style="color:var(--bad)">' + esc(e.message) + "</div>"; })
      .then(function () { btn.disabled = false; });
  }

  // ---------------------------------------------------------------- 启动

  function bind() {
    $$(".tab").forEach(function (b) {
      b.addEventListener("click", function () { switchTab(b.dataset.tab); });
    });
    $("#btnRefresh").addEventListener("click", refresh);
    $("#runLimit").addEventListener("change", function () { load("runs"); });
    $("#galLimit").addEventListener("change", function () { load("gallery"); });
    $("#btnSaveCfg").addEventListener("click", saveCfg);
    $("#btnReloadCfg").addEventListener("click", function () { load("settings"); toast("已还原为服务器上的值"); });
    $("#btnUploadRef").addEventListener("click", uploadRef);
    $("#btnRecrop").addEventListener("click", recrop);
    $("#btnProbe").addEventListener("click", runProbe);
    $("#probeScene").addEventListener("keydown", function (e) { if (e.key === "Enter") { runProbe(); } });

    var dz = $("#dropzone"), inp = $("#refFile");
    ["dragenter", "dragover"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("over"); });
    });
    dz.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
        inp.files = e.dataTransfer.files;
        $("#refFileName").textContent = e.dataTransfer.files[0].name;
      }
    });
    inp.addEventListener("change", function () {
      $("#refFileName").textContent = (inp.files && inp.files[0]) ? inp.files[0].name : "把图片拖到这里，或点击选择";
    });

    $("#autoRefresh").addEventListener("change", function (e) {
      if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
      if (e.target.checked) {
        autoTimer = setInterval(function () {
          if (current === "runs" || current === "overview") { load(current); }
        }, 15000);
      }
    });

    var lb = $("#lightbox");
    lb.addEventListener("click", function () { lb.classList.add("hidden"); });
  }

  function waitBridge(timeoutMs) {
    // 桥脚本由 AstrBot 注入到 </body> 前，执行时机晚于本脚本，只能轮询等；
    // 本地预览的 stub 桥是同步存在的，会立即通过。
    return new Promise(function (resolve) {
      if (window.AstrBotPluginPage) { resolve(window.AstrBotPluginPage); return; }
      var t0 = Date.now();
      var timer = setInterval(function () {
        if (window.AstrBotPluginPage) {
          clearInterval(timer);
          resolve(window.AstrBotPluginPage);
        } else if (Date.now() - t0 > timeoutMs) {
          clearInterval(timer);
          resolve(null);
        }
      }, 25);
    });
  }

  function boot() {
    waitBridge(10000).then(function (b) {
      bridge = b;
      if (!bridge) { $("#noBridge").classList.remove("hidden"); return; }
      bind();
      return bridge.ready().then(function (ctx) {
        if (ctx && typeof ctx.isDark === "boolean") {
          document.documentElement.setAttribute("data-theme", ctx.isDark ? "dark" : "light");
        }
        load("overview");
        load("settings");
      });
    }).catch(function (e) {
      $("#noBridge").classList.remove("hidden");
      $("#noBridge").textContent = "桥接初始化失败：" + (e && e.message ? e.message : e);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
