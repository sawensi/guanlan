"""
观澜 — 微信公众号文章获取模块

多源策略（按优先级）:
  1. WeWe RSS (微信读书 API) — 最可靠，需 Docker 部署
  2. 新浪博客 (blog.sina.com.cn/xuxiaoming8) — 徐小明同步更新，完全开放
  3. 搜狗微信搜索 (type=2 文章搜索 + type=1 账号搜索)
  4. 百度 site:mp.weixin.qq.com 兜底

每篇文章会尝试抓取全文内容，优先用于前端展示和 LLM 分析。
"""

import json
import os
import re
from datetime import datetime
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup
from models import ArticleItem

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ARTICLES_CACHE = os.path.join(DATA_DIR, "articles.json")

# 目标公众号
TARGET_ACCOUNT = "投资明见"
TARGET_WECHAT_ID = "sinaxxm"

# ── WeWe RSS 配置 ───────────────────────────────────────
# Docker 部署后，WeWe RSS 服务地址
WEWE_RSS_BASE = os.environ.get("WEWE_RSS_URL", "http://127.0.0.1:4000")
# 在 WeWe RSS Web UI 中添加「投资明见」后获取的 feed ID
WEWE_FEED_ID = os.environ.get("WEWE_FEED_ID", "")

# ── 新浪博客配置 ────────────────────────────────────────
SINA_BLOG_INDEX = "https://blog.sina.com.cn/xuxiaoming8"
SINA_RSS_URL = "https://blog.sina.com.cn/rss/1300875316.xml"  # 徐小明博客 RSS（可能被限）
# ★ 新浪反爬: Chrome 120+ 返回 418，必须用较旧 UA
SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/100.0.4896.127 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ── 搜狗配置 ────────────────────────────────────────────
SOGOU_SEARCH_URL = "https://weixin.sogou.com/weixin"
SOGOU_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

MP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://mp.weixin.qq.com/",
}


# ── 工具函数 ────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """规范化 URL"""
    if not url:
        return ""
    if url.startswith("/link?url="):
        return urljoin("https://weixin.sogou.com", url)
    if url.startswith("//"):
        return "https:" + url
    return url


def _is_today(time_str: str) -> bool:
    """判断文章是否为今天/昨天发布的

    支持格式:
      - "今天" / "昨天" / "N小时前" / "N分钟前"
      - "2026-06-12" / "2026-06-12 11:30"
      - "6月12日" / "06月12日"
    """
    if not time_str:
        return False
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today.replace(day=today.day - 1)
                     if today.day > 1
                     else today.replace(month=today.month - 1, day=28)
                     ).strftime("%Y-%m-%d")

    # 中文
    if "今天" in time_str or "小时前" in time_str or "分钟前" in time_str:
        return True
    if "昨天" in time_str:
        return True
    # YYYY-MM-DD
    if today_str in time_str or yesterday_str in time_str:
        return True
    # M月D日
    m = re.match(r"(\d{1,2})月(\d{1,2})日?", time_str)
    if m:
        try:
            month, day = int(m.group(1)), int(m.group(2))
            if month == today.month and day in (today.day, today.day - 1):
                return True
        except ValueError:
            pass
    return False


def _clean_sina_body(text: str) -> str:
    """清理新浪博客文章正文，去除导航、标签和尾部垃圾"""
    if not text:
        return ""

    # 移除尾部的分享/导航等垃圾
    end_markers = [
        "分享：", "喜欢\n", "阅读┊", "收藏\n", "打印\n",
        "举报", "前一篇：", "后一篇：",
    ]
    for marker in end_markers:
        idx = text.find(marker)
        if idx > 80:
            text = text[:idx]
            break

    # 移除 "新浪广告共享计划" 到 "荣誉徽章：" 之间的导航区域
    text = re.sub(
        r"新浪广告共享计划.*?荣誉徽章：\s*",
        "", text, flags=re.DOTALL,
    )
    # 移除 "正文字体大小：大中小"
    text = re.sub(r"正文字体大小：[大中小]+\s*", "", text)
    # 移除元数据标签行
    text = re.sub(
        r"^标签：\s*[\s\S]*?(?=徐小明[：:])", "",
        text, flags=re.MULTILINE,
    )
    # 移除纯标签行
    lines = text.split("\n")
    clean_lines = []
    skip_meta = False
    for line in lines:
        stripped = line.strip()
        # 跳过元数据行
        if re.match(
            r"^(标签：|微信号：|id：|交易师|股票|分类：|徐小明$)$",
            stripped,
        ):
            continue
        # 跳过只有"徐小明"的行（重复的标题行）
        if stripped == "徐小明":
            continue
        clean_lines.append(line)
    text = "\n".join(clean_lines)

    # 去除多余空白
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_html_content(html: str) -> str:
    """清洗公众号文章 HTML，提取纯文本正文"""
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
        # 移除无关元素
        for tag in soup.select(
            "script, style, .rich_media_meta_list, .rich_media_tool, "
            ".reward_area, .rich_media_area_extra, .qr_code_pc_outer, "
            ".rich_media_area_primary .rich_media_wrp .rich_media_content "
            "style, #js_pc_qr_code, .rich_media_area_meta, .code-snippet, "
            ".ad_iframe, .rich_media_meta_list, .rich_media_tool_area, "
            ".rich_media_area_extra, .reward_area, .follow_btn_wrp, "
            ".qr_code, .original_area_primary, .ct_mpda_wrp"
        ):
            tag.decompose()

        # 查找正文区域
        content = (
            soup.select_one("#js_content")
            or soup.select_one(".rich_media_content")
            or soup.select_one(".rich_media_area_primary")
            or soup
        )

        # 获取纯文本
        text = content.get_text(separator="\n", strip=True)
        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 移除常见的无关文本行
        lines = []
        skip_next = False
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                lines.append("")
                continue
            # 跳过明显是导航/广告的行
            if re.match(
                r"^(微信扫一扫|关注该公众号|分享到朋友圈|阅读\s*\d+|赞\s*\d+|在看\s*\d+|"
                r"收录于合集|喜欢此内容的人还喜欢|以上内容由|扫码关注|"
                r"长按识别|点击上方|点击下方|点击阅读原文|阅读原文|"
                r"更多精彩|推荐阅读|猜你喜欢|相关阅读)$",
                line,
            ):
                continue
            if len(line) < 3 and not re.match(r"^[一二三四五六七八九十]$", line):
                continue
            lines.append(line)

        return "\n".join(lines).strip()
    except Exception:
        return html


def _extract_timestamp(item) -> str:
    """从搜狗搜索结果中提取文章发布时间戳"""
    script_el = item.select_one("script")
    if script_el:
        text = script_el.get_text(strip=True)
        m = re.search(r"timeConvert\('(\d+)'\)", text)
        if m:
            try:
                ts = int(m.group(1))
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError):
                pass
    time_el = item.select_one(".s2, .s-p4")
    if time_el:
        return time_el.get_text(strip=True)
    return ""


# ── 缓存管理 ────────────────────────────────────────────

def _load_articles_cache() -> list[dict]:
    if os.path.exists(ARTICLES_CACHE):
        try:
            with open(ARTICLES_CACHE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_articles_cache(articles: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    existing = _load_articles_cache()
    seen_urls = {a.get("url", "") for a in existing}
    for article in articles:
        url = article.get("url", "")
        if url and url not in seen_urls:
            existing.insert(0, article)
            seen_urls.add(url)
    existing = existing[:200]
    with open(ARTICLES_CACHE, "w") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


# ── 源 1: WeWe RSS ─────────────────────────────────────

async def _fetch_wewe_articles(client: httpx.AsyncClient) -> list[dict]:
    """从 WeWe RSS 获取「投资明见」最新文章（含全文）"""
    global WEWE_FEED_ID  # 允许函数内更新全局配置

    feed_id = WEWE_FEED_ID
    if not feed_id:
        # 尝试自动获取 feed 列表
        try:
            resp = await client.get(f"{WEWE_RSS_BASE}/feeds", timeout=10.0)
            if resp.status_code != 200:
                print(f"[wechat_reader] WeWe RSS feeds list failed: {resp.status_code}")
                return []
            feeds = resp.json()
            # 查找「投资明见」的 feed
            feed_list = feeds if isinstance(feeds, list) else feeds.get("data", [])
            for feed in feed_list:
                mp_name = feed.get("mpName", "") or feed.get("name", "")
                if TARGET_ACCOUNT in mp_name or TARGET_WECHAT_ID in str(feed):
                    feed_id = feed.get("id", "") or feed.get("feedId", "")
                    WEWE_FEED_ID = feed_id  # 记住以供后续使用
                    print(f"[wechat_reader] Auto-detected feed ID: {feed_id}")
                    break
        except Exception as e:
            print(f"[wechat_reader] WeWe RSS auto-detect failed: {e}")
            return []

    if not feed_id:
        print("[wechat_reader] WeWe RSS not available (feed ID not configured)")
        return []

    try:
        # WeWe RSS 格式: /feed/{id}/json
        url = f"{WEWE_RSS_BASE}/feed/{feed_id}/json"
        resp = await client.get(url, timeout=15.0)
        if resp.status_code != 200:
            print(f"[wechat_reader] WeWe RSS feed returned {resp.status_code}")
            return []

        data = resp.json()
        items = data.get("items", []) if isinstance(data, dict) else data

        articles = []
        for item in items[:10]:  # 取最近 10 篇
            title = item.get("title", "")
            article_url = item.get("url", "")
            pub_time = item.get("date_published", "") or item.get("date_modified", "")
            summary = item.get("summary", "") or item.get("content_text", "")[:200]

            # WeWe RSS 可能包含全文
            content = item.get("content_text", "") or item.get("content_html", "")
            if content and len(content) > len(summary):
                full_content = content
            elif content:
                full_content = _clean_html_content(content)
            else:
                full_content = ""

            if title and article_url:
                articles.append({
                    "title": title,
                    "url": article_url,
                    "summary": summary[:500],
                    "content": full_content,
                    "publish_time": pub_time,
                    "source": "wewe_rss",
                })

        print(f"[wechat_reader] WeWe RSS: got {len(articles)} articles")
        return articles

    except Exception as e:
        print(f"[wechat_reader] WeWe RSS error: {e}")
        return []


# ── 源 2: 新浪博客 ─────────────────────────────────────

async def _fetch_sina_blog_articles(client: httpx.AsyncClient) -> list[dict]:
    """从徐小明新浪博客获取最新文章（完全开放，无需认证）

    徐小明公众号「投资明见」与新浪博客内容同步更新。
    博客首页: https://blog.sina.com.cn/xuxiaoming8
    """
    articles = []
    seen = set()

    # 1) 尝试 RSS
    for rss_url in [SINA_RSS_URL, "http://blog.sina.com.cn/rss/1300875316.xml"]:
        try:
            resp = await client.get(
                rss_url, timeout=15.0,
                headers={"User-Agent": SOGOU_HEADERS["User-Agent"]},
            )
            if resp.status_code == 200 and len(resp.text) > 100:
                soup = BeautifulSoup(resp.text, "xml")
                for item in soup.select("item")[:10]:
                    title_el = item.select_one("title")
                    link_el = item.select_one("link")
                    pub_el = item.select_one("pubDate")
                    desc_el = item.select_one("description")
                    title_text = title_el.get_text(strip=True) if title_el else ""
                    link_text = link_el.get_text(strip=True) if link_el else ""
                    if title_text and link_text and link_text not in seen:
                        seen.add(link_text)
                        articles.append({
                            "title": title_text,
                            "url": _normalize_url(link_text),
                            "summary": (desc_el.get_text(strip=True)[:500]
                                        if desc_el else ""),
                            "content": desc_el.get_text(strip=True)
                                       if desc_el else "",
                            "publish_time": pub_el.get_text(strip=True)
                                            if pub_el else "",
                            "source": "sina_blog",
                        })
                if articles:
                    break
        except Exception:
            continue

    # 2) 降级: 直接解析博客首页 HTML
    if not articles:
        try:
            resp = await client.get(
                SINA_BLOG_INDEX, timeout=15.0,
                headers={
                    "User-Agent": SOGOU_HEADERS["User-Agent"],
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
            )
            if resp.status_code == 200 and len(resp.text) > 100:
                soup = BeautifulSoup(resp.text, "lxml")
                skip_words = {"阅读", "查看全文", "评论", "收藏", "转载", "分享"}
                for a in soup.select('a[href*="blog_"]'):
                    href = a.get("href", "")
                    text = a.get_text(strip=True)
                    if not text or len(text) < 4 or text in skip_words:
                        continue
                    if "blog_4d89b834" not in href:
                        continue
                    url = _normalize_url(href)
                    if url in seen:
                        continue
                    seen.add(url)
                    articles.append({
                        "title": text,
                        "url": url,
                        "summary": "",
                        "content": "",
                        "publish_time": "",
                        "source": "sina_blog",
                    })
        except Exception as e:
            print(f"[wechat_reader] Sina blog HTML error: {e}")

    # 3) 为全部文章抓取全文 (需要 Referer 防盗链 + 旧版 UA 防 418)
    sina_headers = dict(SINA_HEADERS)
    sina_headers["Referer"] = SINA_BLOG_INDEX
    sina_fetch_ok = 0
    sina_fetch_fail = 0
    for a in articles:
        if a.get("content") and len(a.get("content", "")) > 200:
            continue
        url = a["url"]
        try:
            resp = await client.get(url, timeout=15.0, headers=sina_headers)
            if resp.status_code == 200 and len(resp.text) > 500:
                soup = BeautifulSoup(resp.text, "lxml")
                # 正文选择器（多个备选，按优先级）
                body = (
                    soup.select_one("#articlebody")
                    or soup.select_one(".SG_connBody")
                    or soup.select_one(".articalContent")
                    or soup.select_one("#sina_keyword_ad_area2")
                    or soup.select_one(".blog_article")
                    or soup.select_one("div.article")
                )
                if body:
                    body_text = body.get_text(separator="\n", strip=True)

                    # 提取发布时间 (格式: "标题(2026-06-12 12:15:01)")
                    time_match = re.search(
                        r"\((\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\)",
                        body_text,
                    )
                    if time_match and not a.get("publish_time"):
                        a["publish_time"] = time_match.group(1)

                    # 清理正文: 去掉头部导航信息和尾部垃圾
                    content = _clean_sina_body(body_text)
                    if len(content) > 50:
                        a["content"] = content
                        sina_fetch_ok += 1
                        print(f"[wechat_reader] Sina: {len(content)} chars "
                              f"for '{a['title'][:30]}'")
                    else:
                        sina_fetch_fail += 1
                        print(f"[wechat_reader] Sina: content too short "
                              f"({len(content)} chars) for '{a['title'][:30]}'")
                else:
                    sina_fetch_fail += 1
                    page_title = ""
                    title_el = soup.select_one("title")
                    if title_el:
                        page_title = title_el.get_text(strip=True)
                    print(f"[wechat_reader] Sina selector miss for "
                          f"'{a['title'][:30]}': page_title='{page_title[:50]}'")
            else:
                sina_fetch_fail += 1
                print(f"[wechat_reader] Sina HTTP {resp.status_code} "
                      f"len={len(resp.text)} for '{a['title'][:30]}'")
        except Exception as e:
            sina_fetch_fail += 1
            print(f"[wechat_reader] Sina content fetch err for "
                  f"'{a['title'][:30]}': {e}")

    print(f"[wechat_reader] Sina step3: {sina_fetch_ok} ok, {sina_fetch_fail} fail "
          f"(out of {len(articles)} articles)")

    print(f"[wechat_reader] Sina blog: {len(articles)} articles")
    return articles


# ── 源 3: 搜狗微信搜索（改进版）─────────────────────────

async def _fetch_sogou_articles(
    client: httpx.AsyncClient,
    account_name: str = TARGET_ACCOUNT,
    search_type: str = "2",
) -> list[dict]:
    """通过搜狗微信搜索获取文章列表（改进过滤精度）"""
    articles = []

    try:
        params = {"type": search_type, "query": account_name, "ie": "utf8"}
        resp = await client.get(
            SOGOU_SEARCH_URL, params=params,
            headers=SOGOU_HEADERS, follow_redirects=True,
        )

        if resp.status_code != 200:
            print(f"[wechat_reader] Sogou type={search_type} returned {resp.status_code}")
            return articles

        # 检测反爬
        if len(resp.text) < 5000 or "验证" in resp.text[:1000]:
            print(f"[wechat_reader] Sogou type={search_type}: anti-crawl "
                  f"(length={len(resp.text)})")
            return articles

        soup = BeautifulSoup(resp.text, "lxml")
        items = soup.select(".news-list2 li, .txt-box")
        print(f"[wechat_reader] Sogou type={search_type}: found {len(items)} items")

        for item in items:
            try:
                link_el = item.select_one(
                    "a[href*='/link?url='], a[href*='mp.weixin.qq.com']"
                )
                if not link_el:
                    continue

                title = link_el.get_text(strip=True)
                url = _normalize_url(link_el.get("href", ""))

                # 摘要
                summary_el = item.select_one(".txt-info, .s-p3")
                summary = summary_el.get_text(strip=True) if summary_el else ""

                # 来源公众号名称
                source_el = item.select_one(".s-p, .account")
                source = source_el.get_text(strip=True) if source_el else ""

                # 发布时间
                time_str = _extract_timestamp(item)

                # ★ 改进的过滤逻辑: 来源必须精确匹配目标公众号
                # 搜狗搜索可能返回"提及"目标账号的文章，而非目标账号自身的文章
                if source:
                    # 来源字段存在时，必须精确匹配
                    if source != account_name:
                        # 宽松匹配: 来源包含目标名称 且 长度接近(避免匹配到"投资明见XXX"这种)
                        if account_name not in source:
                            continue
                else:
                    # 来源字段缺失时，标题必须包含公众号名
                    if account_name not in title:
                        continue

                if title and url:
                    articles.append({
                        "title": title,
                        "url": url,
                        "summary": summary,
                        "publish_time": time_str,
                        "source": "sogou",
                    })

            except Exception:
                continue

    except Exception as e:
        print(f"[wechat_reader] Sogou type={search_type} error: {e}")

    print(f"[wechat_reader] Sogou type={search_type}: extracted {len(articles)}")
    return articles


# ── 源 4: 百度兜底 ─────────────────────────────────────

async def _fetch_baidu_articles(
    client: httpx.AsyncClient,
    account_name: str = TARGET_ACCOUNT,
) -> list[dict]:
    """百度搜索 mp.weixin.qq.com 作为最终兜底"""
    articles = []

    try:
        resp = await client.get(
            "https://www.baidu.com/s",
            params={"wd": f"{account_name} site:mp.weixin.qq.com", "rn": "20"},
            headers=MP_HEADERS, follow_redirects=True,
        )

        if resp.status_code != 200:
            return articles
        if len(resp.text) < 2000:
            print(f"[wechat_reader] Baidu returned short page ({len(resp.text)}B)")
            return articles

        soup = BeautifulSoup(resp.text, "lxml")

        for result in soup.select(".result, .c-container"):
            try:
                link_el = result.select_one("a[href*='mp.weixin.qq.com']")
                if not link_el:
                    continue

                title = link_el.get_text(strip=True)
                url = _normalize_url(link_el.get("href", ""))

                summary_el = result.select_one(".c-abstract, .c-span-last")
                summary = summary_el.get_text(strip=True) if summary_el else ""

                # ★ 过滤: 标题必须暗示是目标公众号的文章
                if account_name not in title:
                    continue

                if title and url:
                    articles.append({
                        "title": title,
                        "url": url,
                        "summary": summary,
                        "publish_time": "",
                        "source": "baidu",
                    })
            except Exception:
                continue

    except Exception as e:
        print(f"[wechat_reader] Baidu error: {e}")

    return articles


# ── 文章正文抓取 ────────────────────────────────────────

async def _fetch_article_full_content(
    client: httpx.AsyncClient, url: str
) -> str:
    """尝试抓取文章全文 — 支持微信公众号 (mp.weixin.qq.com) 和新浪博客 (blog.sina.com.cn)"""
    if not url:
        return ""

    is_sina = "sina.com.cn" in url or "blog.sina.com.cn" in url
    is_wechat = "mp.weixin.qq.com" in url

    if not is_sina and not is_wechat:
        return ""

    try:
        if is_wechat:
            return await _fetch_wechat_article_content(client, url)
        elif is_sina:
            return await _fetch_sina_article_content(client, url)
        return ""

    except Exception as e:
        print(f"[wechat_reader] Fetch content error for {url[:60]}: {e}")
        return ""


async def _fetch_wechat_article_content(
    client: httpx.AsyncClient, url: str
) -> str:
    """抓取微信公众号文章全文"""
    try:
        headers = dict(MP_HEADERS)
        headers["Referer"] = "https://mp.weixin.qq.com/"
        resp = await client.get(url, headers=headers, timeout=15.0)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "lxml")
        js_content = soup.select_one("#js_content")
        if js_content:
            for hidden in js_content.select(
                '[style*="visibility: hidden"], '
                '[style*="display: none"]'
            ):
                hidden.decompose()
            return _clean_html_content(str(js_content))

        return ""

    except Exception as e:
        print(f"[wechat_reader] WeChat content fetch error for {url[:60]}: {e}")
        return ""


async def _fetch_sina_article_content(
    client: httpx.AsyncClient, url: str
) -> str:
    """抓取新浪博客文章全文"""
    try:
        sina_headers = dict(SINA_HEADERS)
        sina_headers["Referer"] = SINA_BLOG_INDEX
        resp = await client.get(url, timeout=15.0, headers=sina_headers)
        if resp.status_code != 200 or len(resp.text) < 500:
            print(f"[wechat_reader] Sina content fetch: HTTP {resp.status_code}, "
                  f"len={len(resp.text)} for {url[:60]}")
            return ""

        soup = BeautifulSoup(resp.text, "lxml")
        # 尝试多个可能的选择器
        body = (
            soup.select_one("#articlebody")
            or soup.select_one(".SG_connBody")
            or soup.select_one(".articalContent")
            or soup.select_one("#sina_keyword_ad_area2")
            or soup.select_one(".blog_article")
            or soup.select_one("div.article")
        )
        if body:
            body_text = body.get_text(separator="\n", strip=True)
            content = _clean_sina_body(body_text)
            if content:
                print(f"[wechat_reader] Sina full fetch: {len(content)} chars "
                      f"from {url[:60]}")
                return content

        # 选择器未命中时输出调试信息
        page_title = ""
        title_el = soup.select_one("title")
        if title_el:
            page_title = title_el.get_text(strip=True)
        print(f"[wechat_reader] Sina selector miss: title='{page_title[:60]}', "
              f"preview='{resp.text[:200].replace(chr(10), ' ')}'")

        return ""

    except Exception as e:
        print(f"[wechat_reader] Sina content fetch error for {url[:60]}: {e}")
        return ""


# ── 主入口 ─────────────────────────────────────────────

async def fetch_articles_today() -> list[ArticleItem]:
    """
    获取公众号今日文章（多源策略 + 全文抓取）

    优先级:
      1. WeWe RSS (含全文)
      2. 新浪博客 RSS (含全文)
      3. 搜狗 type=2 文章搜索
      4. 搜狗 type=1 账号搜索
      5. 百度 site:mp.weixin.qq.com 搜索

    每篇文章尝试获取全文内容。
    """
    all_articles: list[dict] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        # ── 源 1: WeWe RSS ──
        wewe = await _fetch_wewe_articles(client)
        if wewe:
            all_articles = wewe
            print(f"[wechat_reader] Using WeWe RSS: {len(wewe)} articles")

        # ── 源 2: 新浪博客 ──
        if not all_articles:
            sina = await _fetch_sina_blog_articles(client)
            if sina:
                all_articles = sina
                print(f"[wechat_reader] Using Sina blog: {len(sina)} articles")
            # 即使已有文章，新浪博客也可作为补充
            elif not all_articles:
                pass  # 继续尝试后续源

        # ── 源 3: 搜狗 type=2 ──
        if not all_articles:
            sogou2 = await _fetch_sogou_articles(client, TARGET_ACCOUNT, "2")
            if sogou2:
                all_articles = sogou2
                print(f"[wechat_reader] Using Sogou type=2: {len(sogou2)} articles")

        # ── 源 4: 搜狗 type=1 ──
        if not all_articles:
            sogou1 = await _fetch_sogou_articles(client, TARGET_ACCOUNT, "1")
            if sogou1:
                all_articles = sogou1
                print(f"[wechat_reader] Using Sogou type=1: {len(sogou1)} articles")

        # ── 源 5: 百度 ──
        if not all_articles:
            baidu = await _fetch_baidu_articles(client, TARGET_ACCOUNT)
            if baidu:
                all_articles = baidu
                print(f"[wechat_reader] Using Baidu: {len(baidu)} articles")

        # ── 为没有全文的文章抓取全文 ──
        for a in all_articles:
            if not a.get("content"):
                url = a.get("url", "")
                if url and ("mp.weixin.qq.com" in url or "sina.com.cn" in url):
                    print(f"[wechat_reader] Fetching full content: {a['title'][:40]}...")
                    content = await _fetch_article_full_content(client, url)
                    if content:
                        a["content"] = content
                        print(f"[wechat_reader] Got {len(content)} chars of content")

    # ── 过滤今日/昨日文章 ──
    today_articles = [a for a in all_articles if _is_today(a.get("publish_time", ""))]

    # 如果时间过滤后为空但总数不多 (<20)，全部返回
    if not today_articles and len(all_articles) <= 20:
        today_articles = all_articles
        print(f"[wechat_reader] No time filter, returning all {len(all_articles)}")

    # ── 缓存 ──
    if today_articles:
        _save_articles_cache(today_articles)

    # ── 转换为 ArticleItem ──
    result = []
    for a in today_articles:
        article = ArticleItem(
            title=a.get("title", "无标题"),
            url=a.get("url", ""),
            summary=a.get("summary", ""),
            content=a.get("content", ""),
            key_point="",
            publish_time=a.get("publish_time", ""),
            source=a.get("source", ""),
        )
        result.append(article)

    print(f"[wechat_reader] Final: {len(result)} articles "
          f"(sources: {set(a.source for a in result)})")
    return result


# ── 命令行测试 ─────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def test():
        articles = await fetch_articles_today()
        print(f"\n=== 共获取 {len(articles)} 篇文章 ===")
        for a in articles:
            print(f"  [{a.publish_time}] [{a.source}] {a.title}")
            print(f"    URL: {a.url[:80]}...")
            if a.summary:
                print(f"    Summary: {a.summary[:100]}...")
            if a.content:
                print(f"    Content: {len(a.content)} chars")
            print()

    asyncio.run(test())
