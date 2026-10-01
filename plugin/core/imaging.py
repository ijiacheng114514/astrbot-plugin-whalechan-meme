# -*- coding: utf-8 -*-
"""参考图校验 / 身份卡制作 / 图片规范化。v0.8.0

背景（2026-10-01 实测）：百炼 token-plan 的图生图接口对每张参考图有硬性校验，
短边 < ~300px 的图会让**整个请求**返回 400 InvalidParameter "Error validating image"。
v0.7.0 搜图层的门槛只有 200px，于是 568x228 的素材图把整单打挂，插件静默回退纯文生图，
主角形象就此丢失。本模块把「入参前校验」做成硬闸门。
"""
from __future__ import annotations

import io
import os

# 入参硬闸门（比实测下限 300 留足余量）
MIN_SIDE = 400
MAX_SIDE = 4096
MAX_RATIO = 2.2          # 长边/短边 上限
MAX_BYTES = 8 * 1024 * 1024
OK_FORMATS = ("JPEG", "PNG")


def probe(raw: bytes):
    """返回 (PIL.Image, (w,h)) 或 (None, None)。"""
    try:
        from PIL import Image as PILImage
        im = PILImage.open(io.BytesIO(raw))
        im.load()
        return im, im.size
    except Exception:
        return None, None


def check_ref(path: str) -> tuple[bool, str]:
    """校验一张参考图能否喂给生图接口。返回 (ok, 原因)。"""
    if not path or not os.path.isfile(path):
        return False, "文件不存在"
    try:
        size = os.path.getsize(path)
    except OSError:
        return False, "无法读取"
    if size < 2000:
        return False, "文件过小"
    if size > MAX_BYTES:
        return False, f"超过{MAX_BYTES // 1024 // 1024}MB"
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            fmt = im.format
            w, h = im.size
    except Exception as e:
        return False, f"不是有效图片: {e}"
    if fmt not in OK_FORMATS:
        return False, f"格式{fmt}不支持(仅JPEG/PNG)"
    if min(w, h) < MIN_SIDE:
        return False, f"短边{min(w, h)}<{MIN_SIDE}(接口会400)"
    if max(w, h) > MAX_SIDE:
        return False, f"长边{max(w, h)}>{MAX_SIDE}"
    if max(w, h) / max(1, min(w, h)) > MAX_RATIO:
        return False, "长宽比过扁"
    return True, ""


def normalize(raw: bytes, dst: str, max_side: int = 1024, min_side: int = 0) -> str | None:
    """校验+压缩落盘。min_side>0 时短边不足直接返回 None（用于搜图候选）。"""
    im, size = probe(raw)
    if im is None:
        return None
    w, h = size
    if min_side and min(w, h) < min_side:
        return None
    try:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.save(dst, "JPEG", quality=88)
        return dst
    except Exception:
        return None


def make_identity_card(sheet_path: str, dst: str,
                       crop: tuple[int, int, int, int] | None = None,
                       max_side: int = 768) -> tuple[bool, str]:
    """从三视图设定稿裁出「正面单人身份卡」。

    crop 为 (l,t,r,b) 像素框；None 时按经验值取左上 1/3 宽、上 55% 高
    （本角色稿的正面视图位置）。裁完缩到 max_side 以内存 JPEG。
    """
    try:
        from PIL import Image as PILImage
        with PILImage.open(sheet_path) as im:
            im = im.convert("RGB")
            w, h = im.size
            if crop:
                l, t, r, b = crop
            else:
                l, t, r, b = 0, 0, int(w * 0.376), int(h * 0.552)
            r, b = min(r, w), min(b, h)
            card = im.crop((l, t, r, b))
            card.thumbnail((max_side, max_side))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            card.save(dst, "JPEG", quality=92)
        return True, f"{card.size[0]}x{card.size[1]}"
    except Exception as e:
        return False, repr(e)


def thumb_b64(path: str, side: int = 256, quality: int = 78) -> str | None:
    """生成缩略图 base64（控制台图库用）。"""
    import base64
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((side, side))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def file_b64(path: str) -> str | None:
    import base64
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None
