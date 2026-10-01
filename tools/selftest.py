# -*- coding: utf-8 -*-
"""容器内端到端自测（不依赖 AstrBot）。

用法（在 astrbot 容器里）：
  python3 /AstrBot/data/wm-selftest/selftest.py \
      --plugin /AstrBot/data/wm-selftest/plugin \
      --scene "捧着白米饭眼睛发亮" --caption "白饭优先"

分阶段跑，每阶段独立可跳过：
  1 conf      读 _conf_schema.json 默认值当配置
  2 imaging   身份卡校验 / 从三视图裁剪
  3 journal   JSONL 读写与 token 统计
  4 models    列出 token-plan 可用模型
  5 enhance   考据（真实调用，低温 + JSON）
  6 guard     诉求守卫（零成本纠错回拼）
  7 search    搜图 + 多模态核对（真实出网）
  8 generate  身份卡图生图（调用阶梯，真实出图）
  9 full      直接跑生产入口 pipeline.run()（一条命令走完全流程）

凭据只从 /AstrBot/data/cmd_config.json 里读，绝不打印。
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys
import time

REAL_STATE = "/AstrBot/data/plugin_data/astrbot_plugin_whalechan_meme"
CONFIG_PATH = "/AstrBot/data/cmd_config.json"


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
    for sub in ("imaging", "journal", "prompts", "search", "client", "pipeline", "page_api"):
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
    ap.add_argument("--stages", default="conf,imaging,journal,models,enhance,guard,search,generate")
    ap.add_argument("--set", action="append", default=[], metavar="K=V",
                    help="临时覆盖配置，例：--set model=wan2.7-image-pro")
    args = ap.parse_args()

    stages = {s.strip() for s in args.stages.split(",") if s.strip()}
    core = load_core(args.plugin)
    imaging, journal_mod = core.imaging, core.journal
    BailianClient, Journal, Pipeline = core.BailianClient, core.Journal, core.Pipeline

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
    if "conf" in stages:
        hr("1/8 配置（_conf_schema.json 默认值）")
        sp = os.path.join(args.plugin, "_conf_schema.json")
        with open(sp, encoding="utf-8") as f:
            schema = json.load(f)
        for k, v in schema.items():
            conf[k] = v.get("default") if isinstance(v, dict) else v
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
                print(f"  覆盖 {k}: {old!r} -> {conf[k]!r}")
        keys = ("model", "size", "enhance_model", "enhance_temperature", "enhance_json_mode",
                "verify_model", "search_min_px", "max_refs", "allow_text_fallback",
                "use_reference", "reference_image")
        for k in keys:
            print(f"  {k:22} = {conf.get(k)!r}")
        print(f"  character_dna 长度 = {len(str(conf.get('character_dna') or ''))}")
    else:
        sp = os.path.join(args.plugin, "_conf_schema.json")
        if os.path.isfile(sp):
            with open(sp, encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    conf[k] = v.get("default") if isinstance(v, dict) else v

    def cget(key, default=None):
        v = conf.get(key, None)
        return default if v is None else v

    client = BailianClient(CONFIG_PATH, str(cget("provider_source_id", "bailian")), log=log)

    # ---------------- 2 imaging ----------------
    card = args.card or paths["ref_default"]
    if "imaging" in stages:
        hr("2/8 身份卡与参考图硬闸门")
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

    # ---------------- 3 journal ----------------
    journal = Journal(paths["state"])
    if "journal" in stages:
        hr("3/8 运行日志与 token 记账")
        rid = journal.new_id()
        journal.append({"id": rid, "kind": "selftest", "ts": time.time(),
                        "status": "ok", "tokens_in": 1234, "tokens_out": 56,
                        "images": 0, "ms": 42, "scene": "selftest"})
        got = journal.get(rid)
        st = journal.stats()
        print(f"  写入 {rid} -> 读回 {'成功' if got else '失败'}")
        print(f"  stats(today) = {json.dumps(st, ensure_ascii=False)}")
        print(f"  日志文件 = {journal.path}")

    # ---------------- 4 models ----------------
    if "models" in stages:
        hr("4/8 token-plan 可用模型")
        t0 = time.time()
        models = client.list_models()
        print(f"  {len(models)} 个（{time.time() - t0:.1f}s）")
        for m in models:
            print("   -", m)
        if not models:
            print("  !! 取不到模型列表：凭据或网关有问题")

    pipeline = Pipeline(cget, client, journal, paths, log=log)

    # ---------------- 5 enhance ----------------
    plan = None
    if "enhance" in stages:
        hr("5/8 考据（低温 + JSON 模式）")
        print(f"  scene = {args.scene!r} caption = {args.caption!r}")
        t0 = time.time()
        plan, erec = pipeline.enhance(args.scene, args.caption)
        print(f"  耗时 {time.time() - t0:.1f}s  status={erec.get('status')} "
              f"in={erec.get('in')} out={erec.get('out')} model={erec.get('model')}")
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

    # ---------------- 6 guard ----------------
    if "guard" in stages:
        hr("6/8 诉求守卫（零 LLM 成本）")
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

    # ---------------- 7 search ----------------
    found = []
    if "search" in stages:
        hr("7/8 搜图 + 多模态核对")
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
            found, srec = pipeline.search_refs(queries, names, tmpdir)
            print(f"  耗时 {time.time() - t0:.1f}s")
            print(f"  候选 {srec.get('candidates')} / 下载 {srec.get('downloaded')} / "
                  f"核对通过 {srec.get('kept')} / 核对模型 {srec.get('model') or '-'} / "
                  f"token in={srec.get('in')} out={srec.get('out')}")
            for p in found:
                okf, why = imaging.check_ref(p)
                print(f"   - {os.path.basename(p)} ok={okf} {why}")

    # ---------------- 8 generate ----------------
    if "generate" in stages:
        hr("8/8 身份卡图生图（调用阶梯）")
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
        print(f"  提示词 {len(prompt)} 字，模型 {cget('model')}，尺寸 {cget('size')}")
        allow_text = bool(cget("allow_text_fallback", False)) or not bool(cget("use_reference", True))
        t0 = time.time()
        raw, attempts = client.generate(str(cget("model", "wan2.7-image")), prompt, refs,
                                        str(cget("size", "1024*1024")),
                                        allow_text_fallback=allow_text)
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

    # ---------------- 9 full：生产入口 pipeline.run ----------------
    if "full" in stages:
        hr("9/9 生产入口 pipeline.run()（考据→搜图→核对→阶梯生图→落盘记账）")
        t0 = time.time()
        res = pipeline.run(args.scene, args.caption, True, trigger="selftest",
                           session="selftest")
        r = res["rec"]
        print(f"  耗时 {time.time() - t0:.1f}s  status={r['status']}  id={r['id']}")
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
