"""
观澜 — LLM 摘要解读模块

使用 DeepSeek API 对公众号文章进行专业财经解读
优先使用文章全文内容（content），降级使用摘要（summary）
"""

import json
import os
from datetime import datetime

from openai import OpenAI
from models import InsightsResult, ArticleItem

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

SUMMARY_PROMPT = """你是一位资深宏观分析师和财经评论员。请对以下来自微信公众号「投资明见」（徐小明）的**最新发布**文章进行专业解读。

{articles_text}

{extra_note}
请按以下结构输出（Markdown 格式）：

## 一、核心观点提炼
对每篇文章用 2-3 句话提炼最核心的观点，标注文章序号。

## 二、共同主题归纳
这些文章反映了哪些共同的宏观主题？梳理 2-3 个关键词或趋势。

## 三、对投资者的实操建议
基于今日内容，对个人投资者有什么可操作的建议？要求具体、可执行。

## 四、与当前经济周期的关联
当前经济处于 **{cycle}** 阶段。这些文章的观点与当前周期有何关联？是验证还是背离？

---

要求：
- 专业但易懂，面向有基础金融知识的个人投资者
- 总字数控制在 600-1000 字
- 深入分析，不要简单重复原文
- 如果文章之间有矛盾观点，请明确指出
- 基于文章的实际内容进行分析，不要凭空发挥
"""


STANCE_EXTRACTION_PROMPT = """你是一位专业的金融文本分析师。请阅读以下徐小明（「投资明见」公众号）的最新文章，提取其中表达的市场交易立场和仓位建议。

{articles_text}

请严格按以下 JSON 格式输出（只输出 JSON，不要有任何其他文字）：

```json
{{
  "market_stance": "看多",
  "position_recommendation": "半仓",
  "key_reason": "徐小明今日核心观点，50字以内",
  "confidence": 0.85
}}
```

判断规则：
- **market_stance**（看多/看空/震荡）：
  - "看多" — 文章中明确看涨后市、认为上涨趋势延续、建议买入或加仓
  - "看空" — 文章中明确看跌后市、认为下跌趋势已形成、建议卖出或减仓
  - "震荡" — 文章认为市场将横盘整理、无明确方向、或强调"等待信号确认"

- **position_recommendation**（满仓/重仓/半仓/轻仓/清仓）：
  - 优先查找文章中是否出现"满仓""重仓""半仓""轻仓""清仓"这些词
  - 如果没有明确出现，根据语气推断：
    - 强烈看多 + 建议积极操作 → "重仓"
    - 温和看多 + 建议谨慎操作 → "半仓"
    - 看空 + 建议减仓 → "轻仓" 或 "清仓"
    - 震荡 + 建议控制仓位 → "半仓" 或 "轻仓"

- **confidence**（0.0-1.0）：
  - 0.8-1.0：文章明确给出了方向判断和操作建议
  - 0.5-0.8：需要从语气中推断，但有较强线索
  - 0.3-0.5：信号模糊，仅能从上下文推测

如果文章完全无法提供任何立场信息（例如纯粹声明或非行情分析），market_stance 设为"震荡"，position_recommendation 设为"半仓"，confidence 设为 0.3。"""


def _get_client() -> OpenAI | None:
    """获取 DeepSeek API 客户端"""
    if not DEEPSEEK_API_KEY:
        print("[llm_summarizer] DEEPSEEK_API_KEY is not set!")
        return None
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


async def summarize_articles(
    articles: list[dict],
    current_cycle: str = "",
    max_articles_for_llm: int = 3,
) -> InsightsResult | None:
    """
    使用 LLM 对文章进行摘要解读

    优先使用文章的 content（全文），降级使用 summary（摘要）
    只对最近 max_articles_for_llm 篇文章进行深度 LLM 解读，其余文章保留在前端展示

    参数:
        articles: 文章列表，每个 dict 含 title, url, summary, content, publish_time, source
        current_cycle: 当前经济周期
        max_articles_for_llm: 送入 LLM 深度解读的最大文章数（默认 3）

    返回:
        InsightsResult: 包含完整解读, 如果 LLM 调用失败则返回 None
    """
    client = _get_client()
    if client is None:
        print("[llm_summarizer] No API client available, using fallback")
        return _fallback_summary(articles, current_cycle, max_articles_for_llm)

    # ── 拆分文章：近 N 篇送 LLM 深度解读，其余仅保留 ──
    articles_for_llm = articles[:max_articles_for_llm]
    rest_count = len(articles) - len(articles_for_llm)

    # ── 构建文章文本（仅用近 N 篇）──
    articles_text_parts = []
    for i, a in enumerate(articles_for_llm, 1):
        title = a.get("title", "无标题")
        content = a.get("content", "")
        summary = a.get("summary", "")
        source = a.get("source", "")

        # 优先使用全文，降级使用摘要
        body = content if content and len(content) > 50 else summary
        # 如果全文太长，截断到 3000 字（避免超出 token 限制）
        if len(body) > 3000:
            body = body[:3000] + "\n\n（内容过长，已截断）"

        source_label = f" [来源: {source}]" if source else ""
        articles_text_parts.append(
            f"### 文章{i}: {title}{source_label}\n\n{body}"
        )

    articles_text = "\n\n---\n\n".join(articles_text_parts)

    if not articles:
        return _fallback_summary([], current_cycle)

    # 提示 LLM 还有更多文章未纳入深度解读
    extra_note = ""
    if rest_count > 0:
        extra_note = (f"（注：今日还有 {rest_count} 篇更早发布的文章，已放入历史记录，"
                       f"此处仅对最新 {len(articles_for_llm)} 篇进行深度解读。）\n")

    cycle_str = current_cycle or "未知"

    prompt = SUMMARY_PROMPT.format(
        articles_text=articles_text,
        cycle=cycle_str,
        extra_note=extra_note,
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位资深宏观分析师，擅长解读财经资讯并提供投资建议。请基于文章实际内容进行深入分析。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        interpretation = response.choices[0].message.content

        now = datetime.now()

        # 构建 ArticleItem 列表（保留 content 和 source）
        article_items = [
            ArticleItem(
                title=a.get("title", "无标题"),
                url=a.get("url", ""),
                summary=a.get("summary", ""),
                content=a.get("content", ""),
                key_point="",
                publish_time=a.get("publish_time", ""),
                source=a.get("source", ""),
            )
            for a in articles
        ]

        result = InsightsResult(
            date=now.strftime("%Y-%m-%d"),
            articles_count=len(articles),
            articles=article_items,
            common_themes=[],
            investment_advice="",
            cycle_relevance="",
            full_interpretation=interpretation or "解读生成失败",
            generated_at=now.isoformat(),
        )

        print(f"[llm_summarizer] Summary generated ({len(interpretation or '')} chars "
              f"from {len(articles)} articles)")
        return result

    except Exception as e:
        print(f"[llm_summarizer] LLM call failed: {e}")
        return _fallback_summary(articles, current_cycle)


def _fallback_summary(
    articles: list[dict], cycle: str = "", max_articles_for_llm: int = 3
) -> InsightsResult:
    """LLM 不可用时的降级摘要"""
    now = datetime.now()

    if not articles:
        return InsightsResult(
            date=now.strftime("%Y-%m-%d"),
            articles_count=0,
            articles=[],
            common_themes=[],
            investment_advice="今日暂无新文章。",
            cycle_relevance="",
            full_interpretation="## 今日暂无新文章\n\n「投资明见」今日未检测到新发布内容。",
            generated_at=now.isoformat(),
        )

    recent_articles = articles[:max_articles_for_llm]
    rest_count = len(articles) - len(recent_articles)
    titles = [a.get("title", "无标题") for a in recent_articles]
    titles_md = "\n".join(f"- **{t}**" for t in titles)

    rest_note = ""
    if rest_count > 0:
        rest_note = (f"\n\n另有 {rest_count} 篇更早发布的文章，已放入页面下方的「历史记录」。\n")

    interpretation = f"""## 今日文章概览 ({len(articles)}篇，展示最新 {len(recent_articles)} 篇)

{titles_md}
{rest_note}
---

> ⚠️ **注意**: LLM 摘要服务暂时不可用，以上为文章列表。系统将在下次刷新时尝试生成专业解读。

当前经济周期: **{cycle or '未知'}**

您可以在下方查看近 3 篇文章的完整内容。专业的 LLM 解读将在 DeepSeek API 恢复后自动生成。
"""

    article_items = [
        ArticleItem(
            title=a.get("title", "无标题"),
            url=a.get("url", ""),
            summary=a.get("summary", ""),
            content=a.get("content", ""),
            key_point="",
            publish_time=a.get("publish_time", ""),
            source=a.get("source", ""),
        )
        for a in articles
    ]

    return InsightsResult(
        date=now.strftime("%Y-%m-%d"),
        articles_count=len(articles),
        articles=article_items,
        common_themes=[],
        investment_advice="请先查看原文，等待 LLM 解读。",
        cycle_relevance="",
        full_interpretation=interpretation,
        generated_at=now.isoformat(),
    )


async def extract_stance_from_articles(
    articles: list[dict],
    max_articles: int = 2,
) -> dict | None:
    """
    从徐小明文章中提取结构化交易立场（独立 LLM 调用，与解读分开）

    参数:
        articles: 文章列表，每个 dict 含 title, content
        max_articles: 送入 LLM 的最大文章数（默认 2）

    返回:
        dict with keys: market_stance, position_recommendation,
            key_reason, confidence, articles_analyzed
        如果 LLM 调用失败或 API 不可用则返回 None
    """
    client = _get_client()
    if client is None:
        print("[llm_summarizer] No API client for stance extraction")
        return None

    if not articles:
        print("[llm_summarizer] No articles for stance extraction")
        return None

    # 只用最近的文章做提取
    articles_for_llm = articles[:max_articles]

    # 构建输入文本
    parts = []
    for i, a in enumerate(articles_for_llm, 1):
        title = a.get("title", "无标题")
        content = a.get("content", "") or a.get("summary", "")
        if len(content) > 2000:
            content = content[:2000] + "\n\n（内容过长，已截断）"
        parts.append(f"## 文章{i}: {title}\n\n{content}")

    articles_text = "\n\n---\n\n".join(parts)

    prompt = STANCE_EXTRACTION_PROMPT.format(articles_text=articles_text)

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的金融文本分析器。你只输出合法的 JSON，不要添加任何解释或额外文字。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"},
        )

        raw_output = response.choices[0].message.content
        print(f"[llm_summarizer] Stance extraction raw: {raw_output[:200] if raw_output else 'None'}")

        if not raw_output:
            print("[llm_summarizer] Stance extraction returned empty response")
            return None

        # 解析 JSON
        data = json.loads(raw_output)

        # 验证并规范化字段
        valid_stances = {"看多", "看空", "震荡"}
        valid_positions = {"满仓", "重仓", "半仓", "轻仓", "清仓"}

        market_stance = data.get("market_stance", "震荡")
        if market_stance not in valid_stances:
            market_stance = "震荡"

        position = data.get("position_recommendation", "半仓")
        if position not in valid_positions:
            position = "半仓"

        key_reason = str(data.get("key_reason", ""))[:100]
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        result = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "market_stance": market_stance,
            "position_recommendation": position,
            "key_reason": key_reason,
            "confidence": confidence,
            "generated_at": datetime.now().isoformat(),
            "articles_analyzed": len(articles_for_llm),
        }

        print(f"[llm_summarizer] Stance extracted: {market_stance} / {position} "
              f"(confidence={confidence:.2f}, articles={len(articles_for_llm)})")
        return result

    except json.JSONDecodeError as e:
        print(f"[llm_summarizer] Stance JSON parse failed: {e}")
        return None
    except Exception as e:
        print(f"[llm_summarizer] Stance extraction failed: {e}")
        return None
