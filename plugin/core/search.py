# -*- coding: utf-8 -*-
"""联网搜素材：多图源 + Cookie 预热 + 标题打分。v0.8.0

实测结论（运维手册 §8.6，2026-09-30）：
  百度 acjson 裸请求被反爬，先 GET 首页拿 BAIDUID 再带 jar 请求即正常；
  360 用 thumb 字段（img 原图 403）；必应能搜但第三方防盗链下载全挂，仅兜底。
v0.8.0 变更：下载门槛从 200px 提到 400px（imaging.MIN_SIDE），
  因为短边 <300 的图会让生图接口整单 400。
"""
from __future__ import annotations

import gzip
import http.cookiejar
import json
import re
import urllib.parse
import urllib.request

UA_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


def http_get(url, ref=None, timeout=15, opener=None):
    h = dict(UA_HEADER)
    if ref:
        h["Referer"] = ref
    req = urllib.request.Request(url, headers=h)
    try:
        r = opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return r.status, data
    except Exception:
        return -1, b""


def warm_opener(enabled: bool, log=None):
    """Cookie 预热：先访问百度图片首页拿 BAIDUID，后续请求带同一个 jar。"""
    if not enabled:
        return None
    try:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        http_get("https://image.baidu.com/", timeout=12, opener=opener)
        if log:
            log("info", f"Cookie 预热完成，拿到 {len(list(jar))} 个 cookie")
        return opener
    except Exception as e:
        if log:
            log("warning", f"Cookie 预热失败，走裸请求: {e}")
        return None


def search_baidu(query, opener, timeout=12, min_px=400) -> list:
    q = urllib.parse.quote(query)
    url = f"https://image.baidu.com/search/acjson?tn=resultjson_com&word={q}&pn=0&rn=12"
    st, data = http_get(url, ref="https://image.baidu.com/", timeout=timeout, opener=opener)
    if st != 200 or not data:
        return []
    try:
        j = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return []
    out = []
    for x in j.get("data", []):
        if not isinstance(x, dict):
            continue
        w, h = x.get("width") or 0, x.get("height") or 0
        if w and h and min(w, h) < min_px:
            continue
        u = x.get("thumbURL") or x.get("middleURL") or x.get("hoverURL")
        if u and u.startswith("http"):
            out.append({"url": u,
                        "title": str(x.get("fromPageTitleEnc") or x.get("fromPageTitle") or "")})
    return out


def search_360(query, timeout=12, min_px=0) -> list:
    q = urllib.parse.quote(query)
    url = f"https://image.so.com/j?q={q}&pn=0&sn=12&src=srp"
    st, data = http_get(url, ref="https://image.so.com/", timeout=timeout)
    if st != 200 or not data:
        return []
    try:
        j = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return []
    out = []
    for x in j.get("list", []):
        if not isinstance(x, dict):
            continue
        u = x.get("thumb") or x.get("img")
        if not u or not isinstance(u, str):
            continue
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith("http"):
            out.append({"url": u, "title": str(x.get("title") or "")})
    return out


def search_bing(query, timeout=12) -> list:
    q = urllib.parse.quote(query)
    url = f"https://cn.bing.com/images/async?q={q}&first=1&count=12&mmasync=1"
    st, data = http_get(url, ref="https://cn.bing.com/images/search", timeout=timeout)
    if st != 200 or not data:
        return []
    txt = data.decode("utf-8", "replace")
    urls = re.findall(r'murl&quot;:&quot;(.*?)&quot;', txt)
    titles = re.findall(r't&quot;:&quot;(.*?)&quot;', txt)
    out = []
    for i, u in enumerate(urls):
        if u.startswith("http"):
            out.append({"url": u, "title": titles[i] if i < len(titles) else ""})
    return out


def title_score(title: str, names: list) -> int:
    """标题命中规范名/英文名/别名越多，越可能是我们要的图。零成本的第一道筛。"""
    if not title or not names:
        return 0
    t = title.lower()
    return sum(1 for n in names if n and len(str(n)) >= 2 and str(n).lower() in t)
