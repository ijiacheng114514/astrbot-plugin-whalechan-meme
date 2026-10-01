# -*- coding: utf-8 -*-
"""容器内端到端自测（不依赖 AstrBot）。

用法（在 astrbot 容器里）：
  python3 /AstrBot/data/wm-selftest/selftest.py \
      --plugin /AstrBot/data/wm-selftest/plugin \
      --scene "捧着白米饭眼睛发亮" --caption "白饭优先"

分阶段跑，每阶段独立可跳过：
  1 conf      读 _conf_schema.json 默认值 + site.json 覆盖当配置
  2 conn      解析 LLM / 生图两条连接（v0.9：LLM 默认跟随 AstrBot 聊天模型）
  3 imaging   身份卡校验 / 从三视图裁剪
  4 journal   JSONL 读写与 token 统计
  5 models    列出生图端可用模型
  6 enhance   考据（真实调用，低温 + JSON）
  7 guard     诉求守卫（零成本纠错回拼）
  8 search    搜图 + 多模态核对（真实出网）
  9 generate  身份卡图生图（调用阶梯，真实出图）
 10 full      直接跑生产入口 pipeline.run()（一条命令走完全流程）

凭据只从 cmd_config.json / site.json 里读，打印时一律脱敏（sk-abc****7a）。
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys
import time

# 路径全部可用环境变量改写，别把容器里的绝对路径写死
REAL_STATE = os.environ.get(
    "WM_STATE", "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme")
CONFIG_PATH = os.environ.get("WM_CMD_CONFIG", "/AstrBot/data/cmd_config.json")


def load_core(plugin_dir: str):
    """把 <plugin_dir>/core 当成包导入（不走 AstrBot 的插件加载器）。"""
    core_dir = os.path.join(plugin_dir, "core")
    if not os.path.isdir(core_dir):
        raise SystemExit(f"找不到 {core_dir}")
    spec = importlib.util.spec_from_file_location(
        "wmcore", os.path.join(core_dir, "__init__.py"),
        submodule_search_locations=[core_dir])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wmcore"] = mod
    spec.loader.exec_module(mod)
    for sub in ("imaging", "journal", "prompts", "search", "siteconf",
                "client", "pipeline", "page_api"):
        importlib.import_module("wmcore." + sub)
    return mod


def hr(title: str):
    print("\n" + "=" * 72)
    print(f"== {title}")
    print("=" * 72, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin", required=True, help="插件目录（含 core/ 与 _conf_schema.json）")
    ap.add_argument("--state", default="/tmp/wm-selftest", help="自测状态目录（不会碰生产数据）")
    ap.add_argument("--sheet", default=os.path.join(REAL_STATE, "character_ref.jpg"),
                    help="三视图源稿路径")
    ap.add_argument("--card", default="", help="身份卡路径（留空=从三视图裁）")
    ap.add_argument("--scene", default="捧着白米饭眼睛发亮")
    ap.add_argument("--caption", default="")
    ap.add_argument("--site", default=os.path.join(REAL_STATE, "site.json"),
                    help="面板保存的站点配置（只读叠加到 schema 默认值上，绝不写回）")
    ap.add_argument("--stages",
                    default="conf,conn,imaging,journal,models,enhance,guard,search,generate")
    ap.add_argument("--set", action="append", default=[], metavar="K=V",
                    help="临时覆盖配置，例：--set model=wan2.7-image-pro")
    ap.add_argument("--test-conn", action="store_true",
                    help="conn 阶段额外做连通性自测：生图端只 GET /models（不花钱），"
                         "LLM 发一条极短对话（几十 token）")
    args = ap.parse_args()

    stages = {s.strip() for s in args.stages.split(",") if s.strip()}
    core = load_core(args.plugin)
    imaging, journal_mod = core.imaging, core.journal
    BailianClient, Journal, Pipeline = core.BailianClient, core.Journal, core.Pipeline
    SiteConfig, mask_key = core.SiteConfig, core.mask_key

    os.makedirs(args.state, exist_ok=True)
    paths = {
        "state": args.state,
        "tmp": os.path.join(args.state, "tmp"),
        "outputs": os.path.join(args.state, "outputs"),
        "logs": os.path.join(args.state, "logs"),
        "ref_default": os.path.join(args.state, "character_front.jpg"),
        "sheet": args.sheet,
    }
    for k in ("tmp", "outputs", "logs"):
        os.makedirs(paths[k], exist_ok=True)

    logs: list[str] = []

    def log(level, msg):
        line = f"[{level}] {msg}"
        logs.append(line)
        print("  " + line, flush=True)

    # ---------------- 1 conf ----------------
    conf: dict = {}
    sp = os.path.join(args.plugin, "_conf_schema.json")
    if os.path.isfile(sp):
        with open(sp, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                conf[k] = v.get("default") if isinstance(v, dict) else v

    # 面板保存的站点配置只读叠加，模拟真插件的 site → schema → 默认 三级取值
    site = SiteConfig(args.site, log=log)
    site_vals = site.load()
    for k, v in site_vals.items():
        conf[k] = v

    is_secret = core.siteconf.is_secret

    def show(k, v):
        """打印配置值：密钥类一律脱敏，长文本只报长度。"""
        if is_secret(k):
            return mask_key(v) or "（空）"
        s = str(v)
        return s if len(s) <= 120 else f"<{len(s)} 字>"

    if "conf" in stages:
        hr("1/10 配置（_conf_schema.json 默认值 + site.json 覆盖）")
        print(f"  schema = {sp}")
        print(f"  site   = {args.site} "
              f"{'（存在）' if os.path.isfile(args.site) else '（不存在，全走默认值）'}")
        if site_vals:
            print(f"  site 覆盖了 {len(site_vals)} 项: {site.overridden()}")
        for kv in args.set:
            if "=" in kv:
                k, v = kv.split("=", 1)
                old = conf.get(k)
                if isinstance(old, bool):
                    conf[k] = v.strip().lower() in ("1", "true", "yes", "on")
                elif isinstance(old, int) and not isinstance(old, bool):
                    conf[k] = int(float(v))
                elif isinstance(old, float):
                    conf[k] = float(v)
                else:
                    conf[k] = v
                print(f"  覆盖 {k}: {show(k, old)} -> {show(k, conf[k])}")
        keys = ("llm_source", "llm_base_url", "llm_api_key", "llm_model",
                "gen_base_url", "gen_api_key", "provider_source_id",
                "model", "size", "enhance_model", "enhance_temperature", "enhance_json_mode",
                "verify_model", "search_min_px", "max_refs", "allow_text_fallback",
                "use_reference", "reference_image")
        for k in keys:
            print(f"  {k:22} = {show(k, conf.get(k))}")
        print(f"  character_dna 长度 = {len(str(conf.get('character_dna') or ''))}")

    def cget(key, default=None):
        v = conf.get(key, None)
        return default if v is None else v

    client = BailianClient(CONFIG_PATH, str(cget("provider_source_id", "bailian")), log=log)

    # ---------------- 2 conn ----------------
    llm_conn = gen_conn = None
    if "conn" in stages:
        hr("2/10 连接解析（LLM 跟随 AstrBot / 生图自配）")
        print(f"  cmd_config = {CONFIG_PATH} "
              f"{'（存在）' if os.path.isfile(CONFIG_PATH) else '（不存在！）'}")
        astrbot_chat = client.astrbot_chat_provider()
        if astrbot_chat:
            print(f"  AstrBot 聊天模型 : {astrbot_chat.get('model')} "
                  f"via {astrbot_chat.get('provider_id')}")
            print(f"    api_base = {astrbot_chat.get('base')}")
            print(f"    key      = {mask_key(astrbot_chat.get('key'))}")
        else:
            print("  !! 没解析到 AstrBot 聊天模型（cmd_config 里 agent_runner/provider 链断了）")

        llm_conn = client.resolve_llm(cget)
        gen_conn = client.resolve_gen(cget)
        for tag, cn in (("LLM", llm_conn), ("生图", gen_conn)):
            flag = "OK " if cn.get("ok") else "FAIL"
            extra = f" dialect={cn.get('dialect')}" if tag == "生图" else ""
            print(f"  [{flag}] {tag:4} 来源={cn.get('label') or '-'} "
                  f"model={cn.get('model') or '-'}{extra}")
            print(f"         base={cn.get('base') or '-'} key={mask_key(cn.get('key'))}")
            if not cn.get("ok"):
                print(f"         why={cn.get('why')}")
        info = client.conn_info(cget)
        print(f"  i2i_supported = {info.get('i2i_supported')} "
              f"（False 时形象锁无法工作，pipeline 会显式拦截而不是偷偷纯文生图）")
        if args.test_conn:
            t0 = time.time()
            g = client.test_gen(gen_conn)
            print(f"  生图连通性 {g.get('status')} ok={g.get('ok')} {g.get('ms')}ms "
                  f"列出 {g.get('models', 0)} 个模型，配置模型在列表内={g.get('listed')} "
                  f"i2i={g.get('i2i')}")
            if g.get("note"):
                print(f"    note: {g['note']}")
            if g.get("error"):
                print(f"    error: {str(g['error'])[:200]}")
            l = client.test_llm(llm_conn)
            print(f"  LLM 连通性 ok={l.get('ok')} model={l.get('model')} "
                  f"in={l.get('in')} out={l.get('out')} {l.get('ms')}ms "
                  f"回复={l.get('reply')!r}")
            if l.get("error"):
                print(f"    error: {str(l['error'])[:200]}")
            print(f"  两项自测共耗时 {time.time() - t0:.1f}s（没有生图，不花出图额度）")

    llm_conn = llm_conn or client.resolve_llm(cget)
    gen_conn = gen_conn or client.resolve_gen(cget)

    # ---------------- 3 imaging ----------------
    card = args.card or paths["ref_default"]
    if "imaging" in stages:
        hr("3/10 身份卡与参考图硬闸门")
        if not os.path.isfile(card):
            if os.path.isfile(paths["sheet"]):
                okf, info = imaging.make_identity_card(paths["sheet"], card)
                print(f"  从三视图裁剪: {'成功' if okf else '失败'} {info}")
            else:
                print(f"  !! 三视图源稿不存在: {paths['sheet']}")
        okf, why = imaging.check_ref(card)
        print(f"  check_ref({os.path.basename(card)}) -> ok={okf} why={why!r}")
        print(f"  MIN_SIDE={imaging.MIN_SIDE} MAX_SIDE={imaging.MAX_SIDE} "
              f"MAX_RATIO={imaging.MAX_RATIO} MAX_BYTES={imaging.MAX_BYTES}")
        # 反例：造一张 300x120 的噪点图（>2KB，避开"文件过小"分支），
        # 确认短边闸门能拦下——v0.7 就是被 568x228 的素材图整单打挂的。
        try:
            from PIL import Image as PILImage
            import random
            bad = os.path.join(paths["tmp"], "bad_ref.jpg")
            rnd = random.Random(7)
            im = PILImage.new("RGB", (300, 120))
            im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                        for _ in range(300 * 120)])
            im.save(bad, "JPEG", quality=90)
            ok2, why2 = imaging.check_ref(bad)
            print(f"  反例 300x120({os.path.getsize(bad)}B) -> ok={ok2} why={why2!r} "
                  f"{'✓ 拦下了' if not ok2 else '✗ 没拦住!'}")
        except Exception as e:
            print(f"  反例跳过: {e}")
    conf["reference_image"] = card

    # ---------------- 4 journal ----------------
    journal = Journal(paths["state"])
    if "journal" in stages:
        hr("4/10 运行日志与 token 记账")
        rid = journal.new_id()
        journal.append({"id": rid, "kind": "selftest", "ts": time.time(),
                        "status": "ok", "tokens_in": 1234, "tokens_out": 56,
                        "images": 0, "ms": 42, "scene": "selftest"})
        got = journal.get(rid)
        st = journal.stats()
        print(f"  写入 {rid} -> 读回 {'成功' if got else '失败'}")
        print(f"  stats(today) = {json.dumps(st, ensure_ascii=False)}")
        print(f"  日志文件 = {journal.path}")

    # ---------------- 5 models ----------------
    if "models" in stages:
        hr("5/10 生图端可用模型（用解析出来的生图凭据）")
        t0 = time.time()
        models = client.list_models(key=str(gen_conn.get("key") or ""),
                                    base=str(gen_conn.get("base") or ""))
        print(f"  {len(models)} 个（{time.time() - t0:.1f}s）")
        for m in models:
            print("   -", m)
        if not models:
            print("  !! 取不到模型列表：生图凭据或网关有问题")
        want = str(cget("model", "") or "").strip()
        if want and models and want not in models:
            print(f"  !! 配置里的生图模型 {want!r} 不在上面列表中，生图会 400")
        elif want:
            print(f"  ✓ 配置的生图模型 {want!r} 在列表中")

    pipeline = Pipeline(cget, client, journal, paths, log=log)

    # ---------------- 6 enhance ----------------
    plan = None
    if "enhance" in stages:
        hr("6/10 考据（低温 + JSON 模式）")
        print(f"  scene = {args.scene!r} caption = {args.caption!r}")
        t0 = time.time()
        plan, erec = pipeline.enhance(args.scene, args.caption, llm_conn)
        print(f"  耗时 {time.time() - t0:.1f}s  status={erec.get('status')} "
              f"in={erec.get('in')} out={erec.get('out')} model={erec.get('model')} "
              f"conn={erec.get('conn')}")
        if erec.get("error"):
            print(f"  error: {str(erec['error'])[:400]}")
        if plan:
            print("  analysis   :", str(plan.get("analysis"))[:160])
            print("  needs_asset:", plan.get("needs_asset"))
            print("  queries    :", plan.get("search_queries") or plan.get("asset_query"))
            for e in (plan.get("entities") or []):
                if isinstance(e, dict):
                    print(f"  entity     : {e.get('raw')} -> {e.get('canonical_cn')} / "
                          f"{e.get('canonical_en')} / {e.get('canonical_jp')} "
                          f"({e.get('work')}, conf={e.get('confidence')})")
            print("  prompt     :", str(plan.get("prompt"))[:300])
        else:
            print("  !! 考据失败")

    # ---------------- 7 guard ----------------
    if "guard" in stages:
        hr("7/10 诉求守卫（零 LLM 成本）")
        scene_final, fixes = pipeline.guard_scene(args.scene, plan)
        print(f"  原话   : {args.scene}")
        print(f"  回拼后 : {scene_final}")
        print(f"  纠错   : {fixes or '无'}")
        prompt = pipeline._build_prompt(
            str((plan or {}).get("prompt") or ""), scene_final, args.caption, True)
        print(f"  最终提示词 {len(prompt)} 字：")
        print("  " + prompt[:600].replace("\n", "\n  "))
        assert args.scene.strip()[:6] in prompt or scene_final[:6] in prompt, "原话没进提示词！"
        print("  ✓ 用户原话确实在提示词里（不可截断）")

    # ---------------- 8 search ----------------
    found = []
    if "search" in stages:
        hr("8/10 搜图 + 多模态核对")
        queries = (plan or {}).get("search_queries") or []
        if not queries and (plan or {}).get("asset_query"):
            queries = [(plan or {})["asset_query"]]
        names = []
        for e in ((plan or {}).get("entities") or []):
            if isinstance(e, dict):
                for k in ("canonical_cn", "canonical_en", "canonical_jp"):
                    v = str(e.get(k) or "").strip()
                    if v and v not in names:
                        names.append(v)
        if not (plan or {}).get("needs_asset"):
            print("  考据判定不需要素材图，跳过（想强测加 --set asset_enabled=true 并换个复杂道具的场景）")
        elif not queries:
            print("  没有搜索关键词，跳过")
        else:
            tmpdir = os.path.join(paths["tmp"], "search-" + time.strftime("%H%M%S"))
            os.makedirs(tmpdir, exist_ok=True)
            print(f"  queries={queries} names={names}")
            t0 = time.time()
            found, srec = pipeline.search_refs(queries, names, tmpdir, llm_conn)
            print(f"  耗时 {time.time() - t0:.1f}s")
            print(f"  候选 {srec.get('candidates')} / 下载 {srec.get('downloaded')} / "
                  f"核对通过 {srec.get('kept')} / 核对模型 {srec.get('model') or '-'} / "
                  f"token in={srec.get('in')} out={srec.get('out')}")
            for p in found:
                okf, why = imaging.check_ref(p)
                print(f"   - {os.path.basename(p)} ok={okf} {why}")

    # ---------------- 9 generate ----------------
    if "generate" in stages:
        hr("9/10 身份卡图生图（调用阶梯）")
        refs = []
        okf, why = imaging.check_ref(card)
        if okf and cget("use_reference", True):
            refs.append(card)
        else:
            print(f"  !! 身份卡不可用: {why}")
        for p in found[: max(0, int(cget("max_refs", 3)) - len(refs))]:
            refs.append(p)
        print(f"  参考图 {len(refs)} 张: {[os.path.basename(r) for r in refs]}")
        prompt = pipeline._build_prompt(str((plan or {}).get("prompt") or ""),
                                        args.scene, args.caption, bool(refs))
        gen_model = str(gen_conn.get("model") or "").strip() or str(cget("model", ""))
        print(f"  提示词 {len(prompt)} 字，模型 {gen_model or '（未配置）'}，"
              f"尺寸 {cget('size')}，dialect={gen_conn.get('dialect')}")
        if not gen_conn.get("ok"):
            print(f"  ✗ 生图连接不可用，跳过：{gen_conn.get('why')}")
            refs = []
        allow_text = bool(cget("allow_text_fallback", False)) or not bool(cget("use_reference", True))
        t0 = time.time()
        raw, attempts = client.generate(gen_model, prompt, refs,
                                        str(cget("size", "1024*1024")),
                                        allow_text_fallback=allow_text,
                                        key=str(gen_conn.get("key") or ""),
                                        base=str(gen_conn.get("base") or ""),
                                        dialect=str(gen_conn.get("dialect") or ""))
        print(f"  耗时 {time.time() - t0:.1f}s")
        for a in attempts:
            print(f"   阶梯[{a.get('kind')}] refs={a.get('refs')} status={a.get('status')} "
                  f"in={a.get('in')} out={a.get('out')} images={a.get('images')} "
                  f"{a.get('ms')}ms {str(a.get('error') or '')[:200]}")
        if raw:
            out = os.path.join(paths["outputs"], "selftest-" + time.strftime("%H%M%S") + ".png")
            with open(out, "wb") as f:
                f.write(raw)
            print(f"  ✓ 出图 {len(raw)} bytes -> {out}")
            try:
                from PIL import Image as PILImage
                with PILImage.open(out) as im:
                    print(f"    尺寸 {im.size} 格式 {im.format}")
            except Exception:
                pass
        else:
            print("  ✗ 没出图")

    # ---------------- 10 full：生产入口 pipeline.run ----------------
    if "full" in stages:
        hr("10/10 生产入口 pipeline.run()（连接解析→考据→搜图→核对→阶梯生图→落盘记账）")
        t0 = time.time()
        res = pipeline.run(args.scene, args.caption, True, trigger="selftest",
                           session="selftest")
        r = res["rec"]
        print(f"  耗时 {time.time() - t0:.1f}s  status={r['status']}  id={r['id']}")
        cn = r.get("conn") or {}
        for tag in ("llm", "gen"):
            c2 = cn.get(tag) or {}
            print(f"  连接[{tag:4}] ok={c2.get('ok')} 来源={c2.get('label') or '-'} "
                  f"model={c2.get('model') or '-'} dialect={c2.get('dialect') or '-'} "
                  f"{c2.get('why') or ''}")
        # 记账里绝不能出现明文密钥
        blob = json.dumps(r, ensure_ascii=False)
        leaked = [k for k in ("llm_api_key", "gen_api_key") if k in blob]
        print(f"  记账无明文密钥: {'✓' if not leaked else '✗ 泄漏字段 ' + str(leaked)}")
        print(f"  纠错回拼: {r.get('fixes') or '无'}")
        print(f"  参考图  : {r.get('refs')}")
        print(f"  token   : in={r['tokens_in']} out={r['tokens_out']} images={r['images']}")
        s = r.get("search") or {}
        if s:
            print(f"  搜图    : 候选{s.get('candidates')} 下载{s.get('downloaded')} "
                  f"核对通过{s.get('kept')} 模型{s.get('model') or '-'} "
                  f"in={s.get('in')} out={s.get('out')}")
        for a in r.get("gen") or []:
            print(f"  生图[{a.get('kind')}] refs={a.get('refs')} status={a.get('status')} "
                  f"in={a.get('in')} out={a.get('out')} {a.get('ms')}ms "
                  f"{str(a.get('error') or '')[:180]}")
        if r.get("error"):
            print(f"  error   : {r['error']}")
        if res["img"]:
            print(f"  ✓ 成品 {len(res['img'])} bytes -> "
                  f"{os.path.join(paths['outputs'], r.get('out', ''))}")
        else:
            print("  ✗ 没出图")
        print("  QQ 解析文案（full）：")
        for line in (pipeline.parse_text(r, "full") or "（空）").split("\n"):
            print("    " + line)

    # ---------------- 汇总 ----------------
    hr("自测结束")
    st = journal.stats()
    print(f"  今日记账: {json.dumps(st, ensure_ascii=False)}")
    print(f"  状态目录: {args.state}")
    print(f"  日志条数: {len(logs)}")


if __name__ == "__main__":
    main()
