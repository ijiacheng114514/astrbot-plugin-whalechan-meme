# -*- coding: utf-8 -*-
"""鲸鱼娘表情包生成 · AstrBot 插件入口。v0.9.0

v0.9.0 相对 v0.8.0 的改造（适配性）：
 1. LLM 连接默认**跟随 AstrBot 当前聊天模型**，也可在面板填自己的 URL + API Key；
 2. 生图连接**由使用者自己填** URL + API Key（面板「模型连接」），
    老的 provider_source_id 仍作兼容兜底；没配就明确报错，不静默失败；
 3. 生图接口方言自动识别：百炼/DashScope 支持图生图形象锁，
    其它 OpenAI 兼容接口只能纯文生图（会如实说明，不假装锁住了形象）。

v0.8.0 的五处改造（仍然有效）：
 1. 身份锁：正面身份卡为唯一角色参考；参考图入参前硬校验；
    调用阶梯 char+素材 → 仅char →（默认禁止）纯文生图，杜绝静默回退丢形象。
 2. 思考稳定：考据 temperature 0.15 + 「不得删改用户核心诉求」铁律 + 原话回拼守卫。
 3. QQ 回复精简：「收到，开始执行」+「图 + 解析」两条，中间不再刷屏。
 4. token 记账：每次调用记 input/output tokens，runs.jsonl 可查，可设每日预算闸。
 5. 控制台面板：pages/console/ + /astrbot_plugin_whalechan_meme/page/* 路由
    （运行日志 / token 记账 / 出图相册 / 模型与参考图在线更换 / 连接配置与自测）。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.core.message.message_event_result import MessageChain

from .core import BailianClient, Journal, Pipeline, SiteConfig
from .core import imaging
from .core.page_api import PAGE_PREFIX, PageApi
from .core.prompts import LOG_TAG

PLUGIN_VERSION = "0.9.0"


def _data_path() -> str:
    """AstrBot 数据目录：优先用官方 API，取不到再退回容器默认路径（保证能跑）。"""
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path
        p = get_astrbot_data_path()
        if p:
            return str(p)
    except Exception:
        pass
    for guess in ("/AstrBot/data", os.path.join(os.getcwd(), "data")):
        if os.path.isdir(guess):
            return guess
    return "/AstrBot/data"


def _config_path() -> str:
    """cmd_config.json 路径：官方常量优先，其次数据目录拼接。"""
    env = os.environ.get("WHALECHAN_CMD_CONFIG", "").strip()
    if env:
        return env
    try:
        from astrbot.core.config.astrbot_config import ASTRBOT_CONFIG_PATH
        if ASTRBOT_CONFIG_PATH:
            return str(ASTRBOT_CONFIG_PATH)
    except Exception:
        pass
    return os.path.join(_data_path(), "cmd_config.json")


DATA_DIR = _data_path()
CONFIG_PATH = _config_path()
STATE_DIR = os.path.join(DATA_DIR, "plugin_data", "astrbot_plugin_whalechan_meme")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_conf_schema.json")
# 面板改的配置（含 API Key）写这里：在 plugin_data 下，插件升级/重新部署都不会丢
SITE_CONF_PATH = os.path.join(STATE_DIR, "site.json")

COMMAND_TOKENS = ("生图", "画图", "画表情包", "生成表情包", "draw", "meme", "genmeme")
FAST_TOKENS = ("快图", "速图", "fastdraw")
WAKE_TOKENS = ("大肥鱼", "肥鱼", "鲸鱼娘", "鲸鱼")


class WhaleChanMemePlugin(star.Star):
    """鲸鱼娘表情包：考据→诉求守卫→搜图核对→身份卡图生图；带控制台面板与 token 记账。"""

    def __init__(self, context, config=None):
        super().__init__(context)
        self.conf = config or {}
        self.version = PLUGIN_VERSION
        self.paths = {
            "state": STATE_DIR,
            "tmp": os.path.join(STATE_DIR, "tmp"),
            "outputs": os.path.join(STATE_DIR, "outputs"),
            "logs": os.path.join(STATE_DIR, "logs"),
            "ref_default": os.path.join(STATE_DIR, "character_front.jpg"),
            "sheet": os.path.join(STATE_DIR, "character_ref.jpg"),
        }
        self._ts: list[float] = []
        self._load_state()
        self.site = SiteConfig(SITE_CONF_PATH, log=self._log)
        self.journal = Journal(STATE_DIR)
        self.client = BailianClient(CONFIG_PATH,
                                    str(self._c("provider_source_id", "bailian")),
                                    log=self._log)
        self.pipeline = Pipeline(self._c, self.client, self.journal, self.paths,
                                 log=self._log)
        self._ensure_identity_card()
        self._register_page()
        llm, gen = self.client.resolve_llm(self._c), self.client.resolve_gen(self._c)
        self._log("info", f"v{PLUGIN_VERSION} 初始化完成："
                          f"LLM={llm.get('label')}/{llm.get('model')}"
                          f"{'' if llm.get('ok') else ' 不可用：' + str(llm.get('why'))}"
                          f"｜生图={gen.get('label')}/{gen.get('model')}({gen.get('dialect')})"
                          f"{'' if gen.get('ok') else ' 不可用：' + str(gen.get('why'))}"
                          f"｜身份卡={'有' if os.path.isfile(self._card()) else '无'}")

    # ---------------- 日志桥 ----------------

    @staticmethod
    def _log(level, msg):
        getattr(logger, level, logger.info)(f"[{LOG_TAG}] {msg}")

    # ---------------- 配置 ----------------

    def _c(self, key, default=None):
        """配置读取优先级：面板保存的 site.json > AstrBot 插件配置 > schema 默认值。"""
        v = self.site.get(key, None)
        if v is None:
            v = self.conf.get(key, None)
        return default if v is None else v

    def _cfg_int(self, key, default):
        try:
            return int(self._c(key, default))
        except (TypeError, ValueError):
            return default

    def _read_schema(self):
        try:
            with open(SCHEMA_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self._log("error", f"读 _conf_schema.json 失败: {e}")
            return None

    # ---------------- 身份卡 ----------------

    def _card(self) -> str:
        """角色身份卡的实际路径（配置留空时用数据目录里的默认卡）。"""
        return imaging.card_path(self._c("reference_image", ""), self.paths["ref_default"])

    def _ensure_identity_card(self):
        """首次启动时从三视图源稿裁出正面身份卡（已存在则不动）。"""
        card = self._card()
        if os.path.isfile(card):
            okf, why = imaging.check_ref(card)
            if okf:
                return
            self._log("warning", f"现有身份卡不合格({why})，尝试重裁")
        if os.path.isfile(self.paths["sheet"]):
            okf, info = imaging.make_identity_card(self.paths["sheet"], card)
            self._log("info", f"身份卡{'生成' if okf else '生成失败'}: {info}")
        else:
            self._log("warning", "没有三视图源稿也没有身份卡，形象锁失效！请在面板上传参考图")

    def _register_page(self):
        try:
            if PageApi(self).register():
                self._log("info", f"控制台面板路由已注册: {PAGE_PREFIX}/*")
        except Exception as e:
            self._log("error", f"面板路由注册失败: {e}")

    # ---------------- 限额 / 预算 ----------------

    def _load_state(self):
        try:
            with open(os.path.join(STATE_DIR, "state.json"), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._ts = [float(x) for x in data]
        except Exception:
            self._ts = []
        self._prune()

    def _save_state(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(os.path.join(STATE_DIR, "state.json"), "w", encoding="utf-8") as f:
                json.dump(self._ts[-200:], f)
        except Exception as e:
            self._log("warning", f"限额状态写入失败: {e}")

    def _prune(self):
        cutoff = time.time() - 86400
        self._ts = [t for t in self._ts if t > cutoff]

    def _usage(self):
        now = time.time()
        hour = sum(1 for t in self._ts if t > now - 3600)
        day = len(self._ts)
        last = (now - self._ts[-1]) if self._ts else 1e9
        return hour, day, last

    def _check_quota(self, bypass_cooldown: bool = False):
        hour, day, since = self._usage()
        daily = self._cfg_int("daily_limit", 0)
        hourly = self._cfg_int("hourly_limit", 0)
        cooldown = self._cfg_int("cooldown_sec", 0)
        if daily > 0 and day >= daily:
            return False, f"今日已达上限 {daily} 张"
        if hourly > 0 and hour >= hourly:
            return False, f"近一小时已达上限 {hourly} 张"
        if not bypass_cooldown and cooldown > 0 and since < cooldown:
            return False, f"冷却中（还差 {int(cooldown - since)}s）"
        return True, ""

    def _check_budget(self):
        budget = self._cfg_int("token_budget_daily", 0)
        if budget <= 0:
            return True, ""
        used = self.journal.stats()["tokens"]
        if used >= budget:
            return False, f"今日 token 预算已用完（{used // 1000}k/{budget // 1000}k）"
        return True, ""

    def _record(self):
        self._ts.append(time.time())
        self._save_state()

    def _enabled_here(self, event) -> bool:
        if not self._c("enable", True):
            return False
        wl = self._c("group_whitelist", []) or []
        if not wl:
            return True
        try:
            gid = str(event.get_group_id() or "")
        except Exception:
            gid = ""
        if not gid:
            return True
        return gid in [str(x) for x in wl]

    # ---------------- 命令 ----------------

    @staticmethod
    def _message_str(event) -> str:
        try:
            s = event.get_message_str()
        except Exception:
            s = getattr(event, "message_str", "") or ""
        return (s or "").strip()

    @staticmethod
    def _strip_command(raw: str) -> str:
        s = raw.strip()
        if s.startswith("/"):
            s = s[1:]
        changed = True
        while changed:
            changed = False
            for tok in WAKE_TOKENS + COMMAND_TOKENS + FAST_TOKENS:
                if s.lower().startswith(tok.lower()):
                    rest = s[len(tok):]
                    if rest.strip(" :：,，"):
                        s = rest.lstrip(" :：,，")
                        changed = True
                        break
        return s.strip(" :：,，")

    async def _do_draw(self, event, enhanced: bool):
        if not self._enabled_here(event):
            yield event.plain_result("生图当前未启用。")
            return
        raw = self._strip_command(self._message_str(event))
        if not raw:
            yield event.plain_result("用法：生图 <画面描述> [# 图上文字]　例：生图 捧着白米饭眼睛发亮 # 白饭优先")
            return
        scene, caption = raw, ""
        if "#" in raw:
            a, b = raw.split("#", 1)
            scene, caption = a.strip(), b.strip()

        ok, why = self._check_quota(bypass_cooldown=bool(self._c("command_bypass_cooldown", True)))
        if not ok:
            yield event.plain_result(why + "。")
            return
        ok, why = self._check_budget()
        if not ok:
            yield event.plain_result(why + "。")
            return
        gen = self.client.resolve_gen(self._c)
        if not gen.get("ok"):
            # 连接没配好就别发「收到，开始执行」了，直接说清楚缺什么
            yield event.plain_result(f"{gen.get('why') or '生图连接未配置'}。")
            return

        # 第一条：接单回执（全流程仅此一条过程消息）
        ack = str(self._c("ack_text", "收到，开始执行"))
        if ack:
            try:
                await event.send(MessageChain([Plain(ack)]))
            except Exception:
                pass

        if self._c("verbose_progress", False):
            pass  # Progress callback not supported by pipeline in this version

        # 流水线是同步阻塞实现（requests + PIL），必须丢线程池，别卡事件循环
        res = await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.pipeline.run(
                scene, caption, enhanced, trigger="cmd",
                session=self._session_of(event)))
        rec = res["rec"]
        if not res["img"]:
            yield event.plain_result(f"画失败了：{rec.get('error') or '未知'}（日志 #{rec['id']}）")
            return
        detail = str(self._c("reply_detail", "full"))
        note = self.pipeline.parse_text(rec, detail)
        comps = [Image.fromBytes(res["img"])]
        if note:
            comps.append(Plain("\n" + note))
        try:
            yield event.chain_result(comps)
        except Exception as e:
            self._log("error", f"发送图片失败: {e}")
            yield event.plain_result("图生成了但发送失败。")
            return
        self._record()

    @staticmethod
    def _session_of(event) -> str:
        try:
            return str(event.get_group_id() or event.get_sender_id() or "")
        except Exception:
            return ""

    @filter.command("生图", alias={"画图", "画表情包", "生成表情包", "draw"})
    async def cmd_draw(self, event: AstrMessageEvent):
        """生图 <画面描述> [# 图上文字]：考据+搜图核对+身份卡合成（慢但准）"""
        async for r in self._do_draw(event, enhanced=bool(self._c("enhance_enabled", True))):
            yield r

    @filter.command("快图", alias={"速图", "直接画", "fastdraw"})
    async def cmd_fast_draw(self, event: AstrMessageEvent):
        """快图 <画面描述>：跳过考据与搜图，直接身份卡出图"""
        async for r in self._do_draw(event, enhanced=False):
            yield r

    @filter.command("生图额度", alias={"meme额度", "画图额度"})
    async def cmd_quota(self, event: AstrMessageEvent):
        """查看今日用量与预算"""
        hour, day, _ = self._usage()
        st = self.journal.stats()
        budget = self._cfg_int("token_budget_daily", 0)
        b = "不限" if budget <= 0 else f"{budget // 1000}k"
        yield event.plain_result(
            f"今日 {day} 张 / 上限 {self._cfg_int('daily_limit', 0) or '不限'}；"
            f"token {st['tokens'] // 1000}k / {b}。")

    @filter.command("考据", alias={"考据一下", "看看理解"})
    async def cmd_inspect(self, event: AstrMessageEvent):
        """考据 <描述>：只看模型怎么理解，不出图（排查认错人）"""
        raw = self._strip_command(self._message_str(event))
        raw = re.sub(r"^(考据一下|考据|看看理解)", "", raw, flags=re.I).strip(" :：,，")
        if not raw:
            yield event.plain_result("用法：考据 <画面描述>")
            return
        plan, rec = await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.pipeline.enhance(raw, "", self.client.resolve_llm(self._c)))
        if not plan:
            yield event.plain_result(f"考据失败（{rec.get('status')}）"
                                     f"{('：' + str(rec.get('error'))) if rec.get('error') else ''}。")
            return
        lines = []
        if plan.get("analysis"):
            lines.append("【推理】" + str(plan["analysis"]))
        for e in (plan.get("entities") or []):
            if isinstance(e, dict):
                lines.append(f"【考据】{e.get('raw')} → {e.get('canonical_cn')} / "
                             f"{e.get('canonical_en') or '-'} / {e.get('canonical_jp') or '-'}"
                             f"（{e.get('work') or '-'}，{e.get('confidence')}）"
                             f"{(' ｜ ' + str(e.get('note'))) if e.get('note') else ''}")
        if plan.get("visual_traits"):
            lines.append("【视觉特征】" + str(plan["visual_traits"]))
        lines.append(f"【需要搜参考图】{'是' if plan.get('needs_asset') else '否'}")
        if plan.get("search_queries"):
            lines.append("【搜图关键词】" + " ｜ ".join(str(x) for x in plan["search_queries"]))
        if plan.get("prompt"):
            lines.append("【最终提示词】" + str(plan["prompt"]))
        scene_final, fixes = self.pipeline.guard_scene(raw, plan)
        lines.append("【回拼原话】" + scene_final + (f"（纠错 {fixes}）" if fixes else ""))
        yield event.plain_result("\n".join(lines))

    @filter.command("试搜图", alias={"搜图测试", "searchtest"})
    async def cmd_search_test(self, event: AstrMessageEvent):
        """试搜图 <关键词>[|<关键词2>]：单测搜图+核对链路"""
        q = self._strip_command(self._message_str(event))
        q = re.sub(r"^(试搜图|搜图测试|searchtest)", "", q, flags=re.I).strip(" :：,，")
        if not q:
            yield event.plain_result("用法：试搜图 明日方舟 斯卡蒂　多组用竖线分隔")
            return
        queries = [x.strip() for x in re.split(r"[|｜]", q) if x.strip()]
        names = [w for w in re.split(r"[\s,，]+", q) if len(w) >= 2]
        tmpdir = os.path.join(self.paths["tmp"], "searchtest-" + time.strftime("%H%M%S"))
        os.makedirs(tmpdir, exist_ok=True)
        t0 = time.time()

        try:
            found, srec = await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.pipeline.search_refs(
                    queries, names, tmpdir, self.client.resolve_llm(self._c)))
            cost = time.time() - t0

            if not found:
                yield event.plain_result(f"没搜到合格素材（{cost:.1f}s，候选{srec.get('candidates')}）。")
                return
            yield event.plain_result(f"合格 {len(found)} 张（{cost:.1f}s）：")
            for p in found[:3]:
                try:
                    with open(p, "rb") as f:
                        yield event.chain_result([Image.fromBytes(f.read())])
                except Exception as e:
                    self._log("error", f"发送测试图失败: {e}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @filter.command("生图连接", alias={"模型连接", "连接状态"})
    async def cmd_conn(self, event: AstrMessageEvent):
        """查看 LLM / 生图 两条连接的解析结果（密钥打码，不花钱）"""
        info = await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.client.conn_info(self._c))
        lines = []
        for name, zh in (("llm", "语言模型"), ("gen", "生图")):
            d = info.get(name) or {}
            lines.append(f"{zh}：{'可用' if d.get('ok') else '不可用'}｜"
                         f"{d.get('label') or '未配置'}｜{d.get('model') or '未指定模型'}")
            if d.get("base"):
                lines.append(f"  地址 {d['base']}")
            if d.get("key_masked"):
                lines.append(f"  密钥 {d['key_masked']}")
            if not d.get("ok") and d.get("why"):
                lines.append(f"  原因 {d['why']}")
        if info.get("gen", {}).get("ok") and not info.get("i2i_supported"):
            lines.append("注意：当前生图地址不支持图生图，形象锁无法生效"
                         "（需要百炼/DashScope 的 compatible-mode 地址）。")
        lines.append("改配置：控制台面板 →「模型连接」。")
        yield event.plain_result("\n".join(lines))

    # ---------------- LLM 工具（群里自主触发） ----------------
    @filter.llm_tool(name="generate_meme")
    async def generate_meme(self, event: AstrMessageEvent, scene: str,
                            caption: str = "") -> str:
        """生成一张"蓝色鲸鱼娘/大肥鱼"表情包图片并直接发到当前会话。

        只在情绪很到位、用文字不够劲的时候才用：吐槽、得意、偷吃被发现、
        甩锅、傲娇否认、摸鱼被抓包这类有画面的瞬间。
        普通闲聊、回答正经问题、别人在聊别人的事时不要用。
        角色外貌已由身份卡锁定，scene 里不要描述外貌服装，只写表情、动作、场景和道具。

        Args:
            scene(string): 画面内容描述，只写表情、动作、场景道具，例如"捧着一大碗白米饭，眼睛发亮"。
            caption(string): 图上要写的中文短句，不超过 12 个字，可留空。
        """
        if not self._enabled_here(event):
            return "表情包生成功能当前未启用，用文字回复。"
        if not self.client.resolve_gen(self._c).get("ok"):
            return "生图连接还没配置好，本轮不要生图，用文字回复。"
        ok, why = self._check_quota()
        if not ok:
            return why + "，本轮不要生图，用文字回复。"
        ok, why = self._check_budget()
        if not ok:
            return why + "，本轮不要生图，用文字回复。"
        scene = (scene or "").strip()
        if not scene:
            return "没有给出画面描述，本次不生图，用文字回复。"

        res = await asyncio.get_running_loop().run_in_executor(
            None, lambda: self.pipeline.run(
                scene, caption, bool(self._c("enhance_for_llm_tool", False)),
                trigger="tool", session=self._session_of(event)))
        if not res["img"]:
            return "生图失败了，用文字回复。"
        try:
            await event.send(MessageChain([Image.fromBytes(res["img"])]))
        except Exception as e:
            self._log("error", f"发送图片失败: {e}")
            return "图生成了但发送失败，用文字回复。"
        self._record()
        return "表情包已发出。配一句简短的话就行，别解释这张图。"
