"""
观澜 — FastAPI 主应用
个人投资辅助工具: 宏观周期分析 + 投资占比建议 + 量化策略
"""

import os
import json
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from models import (
    DashboardResponse, AllocationItem, AllocationResult,
    InsightsResult, ArticleItem, QuantStrategy, StrategySignal,
    RefreshResponse, IndicatorData, CycleStage, ChartData,
    StockRankingItem, StockRankingsResponse,
    RecommendedETF, RecommendedStock, StrategySummary, MacroRecommendations,
    GoldenBullSummary,
    BacktestResult, BacktestMetrics, BacktestTradeRecord,
    ValuationData,
)
from data_fetcher import fetch_all_indicators
from cycle_analyzer import analyze_cycle
from allocator import (
    get_allocation,
    get_allocation_chart_data,
    get_quadrant_chart_data,
    get_etf_recommendations,
    adjust_allocation_by_valuation,
)

# ── 路径配置 ───────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(os.path.dirname(BASE_DIR), "web")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── LLM 配置 (复用 DeepSeek API) ─────────────────────

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ── 全局状态 ───────────────────────────────────────────

# 缓存最新的分析结果
_latest_dashboard: dict | None = None
_latest_insights: InsightsResult | None = None
_latest_rankings: dict | None = None


def _load_json(filename: str, default=None):
    """加载 JSON 文件"""
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _save_json(filename: str, data):
    """保存 JSON 文件"""
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _normalize_rankings_cache(data: dict) -> dict:
    """向后兼容：为旧缓存补全新增字段的默认值"""
    for item in data.get("rankings", []):
        item.setdefault("adjusted_score", item.get("composite_score"))
        item.setdefault("financial_health", None)
        item.setdefault("health_flags", [])
        item.setdefault("cfps", None)
        item.setdefault("roe", None)
        item.setdefault("net_profit_growth", None)
    for item in data.get("rankings_all", []):
        item.setdefault("adjusted_score", item.get("composite_score"))
        item.setdefault("financial_health", None)
        item.setdefault("health_flags", [])
        item.setdefault("cfps", None)
        item.setdefault("roe", None)
        item.setdefault("net_profit_growth", None)
    data.setdefault("rankings_all", [])
    data.setdefault("total_all", data.get("total_filtered", 0))
    data.setdefault("soe_excluded", 0)
    data.setdefault("fin_excluded", 0)
    return data


# ── 应用初始化 ─────────────────────────────────────────

def _compute_quality_warnings(source_metadata: dict) -> list[str]:
    """根据 source_metadata 生成人类可读的数据质量警告"""
    warnings = []
    default_codes = []
    conflict_codes = []
    for code, meta in source_metadata.items():
        if meta.get("source") == "default":
            default_codes.append(code)
        if meta.get("conflict"):
            conflict_codes.append(code)

    if len(default_codes) >= 3:
        warnings.append(f"{len(default_codes)}个指标使用内置默认值，数据可能未反映最新情况")
    elif len(default_codes) > 0:
        warnings.append(f"{len(default_codes)}个指标({','.join(default_codes)})使用默认值")
    if len(conflict_codes) > 0:
        warnings.append(f"{len(conflict_codes)}个指标来源间存在显著差异(>10%)，数据可信度降低")
    return warnings


def _build_default_dashboard():
    """用默认指标快速构建 dashboard，无需等待外部 API"""
    from data_fetcher import DEFAULT_INDICATORS, _build_indicator_list, INDICATOR_DEFS
    indicators = _build_indicator_list(DEFAULT_INDICATORS)
    cycle_result = analyze_cycle(indicators)
    allocation = get_allocation(cycle_result["cycle"])
    chart_raw = get_allocation_chart_data(allocation)
    quadrant = get_quadrant_chart_data(cycle_result["growth_momentum"], cycle_result["inflation_momentum"])
    charts = ChartData(rose_data=chart_raw["rose_data"], pie_data=chart_raw["pie_data"], quadrant=quadrant, csi300_pe=[])
    # 默认仪表盘：所有指标来自 default 源
    default_meta = {d["code"]: {"source": "default", "data_date": "", "conflict": False,
                                "chinadata_value": None, "nbs_value": None}
                    for d in INDICATOR_DEFS}
    return DashboardResponse(
        cycle=cycle_result["cycle"],
        cycle_confidence=cycle_result["confidence"],
        indicators=indicators,
        allocation=allocation,
        charts=charts,
        growth_momentum=cycle_result["growth_momentum"],
        inflation_momentum=cycle_result["inflation_momentum"],
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source_metadata=default_meta,
        data_quality_warning=True,
        quality_warnings=[f"所有指标使用内置默认值，宏观数据源(chinadata/NBS)不可用"],
        valuation=None,
    ).model_dump()


async def _background_refresh():
    """后台异步刷新数据，不阻塞服务启动"""
    try:
        print("[观澜] Background refresh started...")
        await refresh_macro_data()
        print("[观澜] Background refresh done.")
    except Exception as e:
        print(f"[观澜] Background refresh failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动: 秒加载缓存/默认值 → 立即就绪 → 后台可选刷新"""
    global _latest_dashboard, _latest_insights
    print("[观澜] Starting up...")

    # 1. 加载缓存
    cached = _load_json("dashboard_cache.json")
    if cached:
        _latest_dashboard = cached
        print(f"[观澜] Loaded cached dashboard ({cached.get('last_updated', 'unknown')})")
    else:
        # 2. 无缓存 → 用默认值秒启动
        _latest_dashboard = _build_default_dashboard()
        print("[观澜] No cache, using defaults")

    # 3. 加载 insights 缓存
    insights_data = _load_json("insights_cache.json")
    if insights_data:
        try:
            _latest_insights = InsightsResult(**insights_data)
        except Exception:
            pass

    # 4. 加载 rankings 缓存
    rankings_data = _load_json("stock_rankings_cache.json")
    if rankings_data:
        _latest_rankings = _normalize_rankings_cache(rankings_data)
        print(f"[观澜] Loaded cached rankings ({rankings_data.get('date', 'unknown')})")

    # 4. 立即 yield，服务就绪
    yield

    # 5. yield 之后启动后台刷新（不阻塞）
    import asyncio
    asyncio.create_task(_background_refresh())

app = FastAPI(title="观澜", version="1.0.0", lifespan=lifespan)


# 静态文件在文件末尾 mount — 确保 API 路由优先


# ── 核心 API: 宏观仪表盘 ──────────────────────────────

@app.get("/guanlan/api/dashboard", response_model=DashboardResponse)
async def get_dashboard():
    """获取宏观仪表盘数据 (从内存缓存秒返回，不触发外部 API)"""
    global _latest_dashboard
    if _latest_dashboard is None:
        _latest_dashboard = _build_default_dashboard()
    return _latest_dashboard


@app.get("/guanlan/api/indicators")
async def get_indicators():
    """获取 NBS 宏观指标原始数据"""
    global _latest_dashboard
    if _latest_dashboard is None:
        _latest_dashboard = _build_default_dashboard()
    return {
        "indicators": _latest_dashboard.get("indicators", []),
        "growth_momentum": _latest_dashboard.get("growth_momentum", 0),
        "inflation_momentum": _latest_dashboard.get("inflation_momentum", 0),
        "last_updated": _latest_dashboard.get("last_updated", ""),
    }


@app.get("/guanlan/api/allocation")
async def get_allocation_only():
    """仅获取投资占比建议"""
    global _latest_dashboard
    if _latest_dashboard is None:
        _latest_dashboard = _build_default_dashboard()

    return {
        "cycle": _latest_dashboard.get("cycle", ""),
        "cycle_confidence": _latest_dashboard.get("cycle_confidence", 0),
        "allocation": _latest_dashboard.get("allocation", []),
        "last_updated": _latest_dashboard.get("last_updated", ""),
    }


# ── 核心 API: 推荐标的 ────────────────────────────────

@app.get("/guanlan/api/dashboard/recommendations",
         response_model=MacroRecommendations)
async def get_macro_recommendations():
    """获取宏观页面推荐标的：ETF + 优选股票 + 策略信号摘要"""
    global _latest_dashboard, _latest_rankings

    if _latest_dashboard is None:
        _latest_dashboard = _build_default_dashboard()

    cycle = _latest_dashboard.get("cycle", "复苏期")
    allocation_raw = _latest_dashboard.get("allocation", [])

    # 1. ETF 推荐：基于当前周期的配置方案
    allocation_items = [AllocationItem(**a) for a in allocation_raw]
    etf_recs = get_etf_recommendations(allocation_items)

    # 2. 优选股票：从排名缓存取 Top 5
    top_stocks: list[RecommendedStock] = []
    if _latest_rankings:
        rankings = _latest_rankings.get("rankings", [])
        for r in rankings[:5]:
            score = r.get("adjusted_score") or r.get("composite_score", 0)
            sector = r.get("sector") or ""
            # 生成一句话理由
            reasons = []
            if r.get("financial_health") and r["financial_health"] < 0.7:
                reasons.append("注意财务健康度")
            if r.get("health_flags"):
                reasons.append("; ".join(r["health_flags"][:1]))
            reason = "; ".join(reasons) if reasons else f"{sector}低PB标的"
            top_stocks.append(RecommendedStock(
                code=r.get("code", ""),
                name=r.get("name", ""),
                score=round(score, 4),
                sector=sector,
                reason=reason,
            ))

    # 3. 策略信号摘要：筛选当前买入信号
    from quant_strategies import get_all_strategies
    from strategy_engine import compute_all_signals

    signals = compute_all_signals()
    strategies = get_all_strategies(cycle, signals)
    top_strategies: list[StrategySummary] = []
    for s in strategies:
        sig = s.current_signal
        if sig and sig.signal in ("买入",):
            top_strategies.append(StrategySummary(
                strategy_name=s.name,
                signal=sig.signal,
                confidence=sig.confidence,
                one_liner=sig.reasoning[:80],
            ))
        if len(top_strategies) >= 3:
            break

    # 如果没有买入信号，补充持有信号
    if not top_strategies:
        for s in strategies:
            sig = s.current_signal
            if sig and sig.signal in ("持有",):
                top_strategies.append(StrategySummary(
                    strategy_name=s.name,
                    signal=sig.signal,
                    confidence=sig.confidence,
                    one_liner=sig.reasoning[:80],
                ))
            if len(top_strategies) >= 3:
                break

    # 4. 金牛奖基金公司推荐
    from jinniu_award import get_jinniu_data
    golden_bull = get_jinniu_data()

    return MacroRecommendations(
        cycle=cycle,
        etf_recommendations=etf_recs,
        top_stocks=top_stocks,
        top_strategies=top_strategies,
        golden_bull=golden_bull,
        generated_at=datetime.now().isoformat(),
    )


# ── 核心 API: 每日解读 ────────────────────────────────

@app.get("/guanlan/api/insights")
async def get_insights(date: str = Query(default="", description="日期 YYYY-MM-DD")):
    """获取公众号文章解读 (默认当天)"""
    global _latest_insights

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # 如果是今天且有缓存
    if date == datetime.now().strftime("%Y-%m-%d") and _latest_insights:
        return _latest_insights.model_dump()

    # 尝试从历史文件加载
    history = _load_json("insights_history.json", [])
    for item in history:
        if item.get("date") == date:
            return item

    # 如果没有任何数据
    if _latest_insights:
        return _latest_insights.model_dump()

    return {
        "date": date,
        "articles_count": 0,
        "articles": [],
        "common_themes": [],
        "investment_advice": "暂无解读数据，系统将在每日19:00自动更新。",
        "cycle_relevance": "",
        "full_interpretation": "## 暂无数据\n\n系统将在每日19:00自动获取公众号文章并生成解读。您也可以手动触发刷新。",
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/guanlan/api/insights/history")
async def get_insights_history(page: int = Query(1, ge=1),
                               size: int = Query(10, ge=1, le=50)):
    """获取历史解读列表"""
    history = _load_json("insights_history.json", [])
    start = (page - 1) * size
    end = start + size
    return {
        "total": len(history),
        "page": page,
        "size": size,
        "items": history[start:end],
    }


# ── 周度回顾 ────────────────────────────────────────────

@app.get("/guanlan/api/insights/weekly")
async def get_weekly_review():
    """生成最近 7 天的周度回顾（LLM 总结 + 市场走势）"""
    import asyncio
    from strategy_engine import compute_all_signals, signals_summary

    # 加载最近 7 天的解读
    history = _load_json("insights_history.json", [])
    if not history:
        return {"status": "empty", "message": "暂无历史解读数据", "review": ""}

    recent = history[:7]

    # 编译一周文章摘要
    articles_text = ""
    for entry in recent:
        date = entry.get("date", "")
        articles = entry.get("articles", [])
        interpretation = entry.get("full_interpretation", "")
        titles = [a.get("title", "") for a in articles]
        articles_text += f"\n## {date}\n"
        articles_text += f"文章: {', '.join(titles)}\n"
        if interpretation:
            articles_text += f"AI解读摘要: {interpretation[:300]}...\n"

    # 获取当前市场数据
    signals = compute_all_signals()
    market_summary = signals_summary(signals)

    # 调用 LLM 生成周度回顾
    review_prompt = f"""你是一位专业的投资顾问。请根据以下信息，生成一份简洁的「本周投资回顾与下周展望」。

## 本周公众号文章及解读
{articles_text}

## 当前市场数据
{market_summary}

请用以下格式回复（控制在 600 字以内）：
### 本周要点
- 简要总结本周核心观点和市场变化（2-3 点）

### 市场状态
- 当前市场的技术面状态和关键数据

### 下周关注
- 下周需要关注的重点和潜在风险

请用通俗易懂的中文撰写，避免过度使用专业术语。"""

    try:
        from llm_summarizer import _get_client
        client = _get_client()
        if client:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": review_prompt}],
                temperature=0.7,
                max_tokens=1200,
            )
            review = resp.choices[0].message.content
            return {"status": "ok", "review": review, "market_data": signals.get("sh000001", {})}
        else:
            raise RuntimeError("No LLM client")
    except Exception as e:
        print(f"[观澜] Weekly review LLM call failed: {e}")
        fallback = f"## 本周市场数据\n\n{market_summary}\n\n> LLM 服务暂时不可用，以上为本周原始数据摘要。"
        return {"status": "fallback", "review": fallback, "market_data": signals.get("sh000001", {})}


# ── 核心 API: 量化策略 ────────────────────────────────

@app.get("/guanlan/api/strategies")
async def get_strategies():
    """获取量化策略列表（含真实市场信号）"""
    from quant_strategies import get_all_strategies
    from strategy_engine import compute_all_signals
    cycle_str = _latest_dashboard.get("cycle", "复苏期") if _latest_dashboard else "复苏期"
    signals = compute_all_signals()
    strategies = get_all_strategies(cycle_str, signals)
    return {
        "strategies": [{
            **s.model_dump(),
            "market_data": signals.get("sh000001", {}),
        } for s in strategies],
        "last_updated": signals.get("generated_at", ""),
    }


@app.get("/guanlan/api/decision-overview")
async def get_decision_overview(
    fund_code: str = Query(default=None, description="可选基金代码，传入则附离场共识"),
):
    """信号一致性面板：入场共识 + 周期阶段 + 估值信号 + 建议仓位（可选离场共识）"""
    from quant_strategies import (
        get_all_strategies, synthesize_entry_decision, synthesize_dca_decision,
    )
    from strategy_engine import compute_all_signals

    cycle_str = _latest_dashboard.get("cycle", "复苏期") if _latest_dashboard else "复苏期"
    cycle_conf = _latest_dashboard.get("cycle_confidence", 0) if _latest_dashboard else 0
    valuation = (_latest_dashboard or {}).get("valuation") or None

    # 1. 入场共识（7 个入场策略统合）
    signals = compute_all_signals()
    strategies = get_all_strategies(cycle_str, signals)
    entry_consensus = synthesize_entry_decision(strategies)

    # 1.5 定投档位共识（定投为主：其他策略只作为"投多少钱"的参考）
    dca_consensus = synthesize_dca_decision(strategies, valuation)

    # 2. 可选离场共识（需拉取基金数据）
    exit_consensus = None
    if fund_code:
        try:
            from exit_strategies import get_all_exit_strategies, synthesize_exit_decision
            from fund_data import fetch_fund_history
            fund_data = fetch_fund_history(fund_code)
            if fund_data is not None:
                xuxiaoming_stance = None
                if _latest_insights and _latest_insights.xu_xiaoming_stance:
                    xuxiaoming_stance = _latest_insights.xu_xiaoming_stance.model_dump()
                exit_strats = get_all_exit_strategies(
                    fund_data, None, None, cycle_str, None,
                    xuxiaoming_stance=xuxiaoming_stance,
                )
                exit_consensus = synthesize_exit_decision(exit_strats, fund_data)
        except Exception as e:
            print(f"[观澜] decision-overview exit consensus failed (non-fatal): {e}")

    return {
        "cycle": cycle_str,
        "cycle_confidence": cycle_conf,
        "valuation": valuation,
        "entry_consensus": entry_consensus,
        "dca_consensus": dca_consensus,
        "exit_consensus": exit_consensus,
        "fund_code": fund_code,
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/guanlan/api/strategies/{strategy_id}")
async def get_strategy_detail(strategy_id: str):
    """获取特定策略详情（含真实市场信号）"""
    from quant_strategies import get_strategy_by_id
    from strategy_engine import compute_all_signals
    cycle_str = _latest_dashboard.get("cycle", "复苏期") if _latest_dashboard else "复苏期"
    signals = compute_all_signals()
    strategy = get_strategy_by_id(strategy_id, cycle_str, signals)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"策略 {strategy_id} 不存在")
    return strategy.model_dump()


# ── 核心 API: 离场策略 ────────────────────────────────

@app.get("/guanlan/api/exit-strategies")
async def get_exit_strategies(
    fund_code: str = Query(..., description="基金代码，如 510300"),
    entry_price: float = Query(None, description="入场净值"),
    entry_date: str = Query(None, description="入场日期 YYYY-MM-DD"),
    return_rate: float = Query(None, description="手动输入收益率%，如 15 表示 +15%"),
):
    """获取离场策略列表（含真实基金数据信号）"""
    from exit_strategies import get_all_exit_strategies, synthesize_exit_decision
    from fund_data import fetch_fund_history

    cycle_str = _latest_dashboard.get("cycle", "复苏期") if _latest_dashboard else "复苏期"

    # 提取徐小明立场数据
    xuxiaoming_stance = None
    if _latest_insights and _latest_insights.xu_xiaoming_stance:
        xuxiaoming_stance = _latest_insights.xu_xiaoming_stance.model_dump()

    # 拉取基金数据
    fund_data = fetch_fund_history(fund_code)
    if fund_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"无法获取基金 {fund_code} 的数据，请检查代码是否正确",
        )

    strategies = get_all_exit_strategies(fund_data, entry_price, entry_date, cycle_str, return_rate,
                                          xuxiaoming_stance=xuxiaoming_stance)
    decision = synthesize_exit_decision(strategies, fund_data)
    return {
        "decision": decision,
        "fund_code": fund_code,
        "fund_name": fund_data.get("fund_name", fund_code),
        "fund_type": fund_data.get("fund_type", "unknown"),
        "latest_nav": fund_data.get("latest_nav"),
        "latest_nav_date": fund_data.get("latest_nav_date"),
        "entry_price": entry_price,
        "entry_date": entry_date,
        "return_rate": return_rate,
        "strategies": [s.model_dump() for s in strategies],
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/guanlan/api/exit-strategies/{strategy_id}")
async def get_exit_strategy_detail(
    strategy_id: str,
    fund_code: str = Query(..., description="基金代码"),
    entry_price: float = Query(None, description="入场净值"),
    entry_date: str = Query(None, description="入场日期 YYYY-MM-DD"),
    return_rate: float = Query(None, description="手动输入收益率%"),
):
    """获取特定离场策略详情"""
    from exit_strategies import get_exit_strategy_by_id
    from fund_data import fetch_fund_history

    cycle_str = _latest_dashboard.get("cycle", "复苏期") if _latest_dashboard else "复苏期"

    # 提取徐小明立场数据
    xuxiaoming_stance = None
    if _latest_insights and _latest_insights.xu_xiaoming_stance:
        xuxiaoming_stance = _latest_insights.xu_xiaoming_stance.model_dump()

    fund_data = fetch_fund_history(fund_code)
    if fund_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"无法获取基金 {fund_code} 的数据",
        )

    strategy = get_exit_strategy_by_id(strategy_id, fund_data, entry_price, entry_date, cycle_str, return_rate,
                                        xuxiaoming_stance=xuxiaoming_stance)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"离场策略 {strategy_id} 不存在")

    return {
        "fund_code": fund_code,
        "fund_name": fund_data.get("fund_name", fund_code),
        "fund_type": fund_data.get("fund_type", "unknown"),
        "latest_nav": fund_data.get("latest_nav"),
        "latest_nav_date": fund_data.get("latest_nav_date"),
        "entry_price": entry_price,
        "entry_date": entry_date,
        "return_rate": return_rate,
        **strategy.model_dump(),
    }


# ── 核心 API: 股票排名 ────────────────────────────────

@app.get("/guanlan/api/rankings")
async def get_rankings():
    """获取每日股票排名 (从内存缓存秒返回)"""
    global _latest_rankings
    if _latest_rankings is None:
        _latest_rankings = _load_json("stock_rankings_cache.json")
        if _latest_rankings:
            _latest_rankings = _normalize_rankings_cache(_latest_rankings)
    if _latest_rankings is None:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_all": 0,
            "total_filtered": 0,
            "soe_excluded": 0,
            "fin_excluded": 0,
            "rankings_all": [],
            "rankings": [],
            "generated_at": datetime.now().isoformat(),
        }
    return _latest_rankings


@app.post("/guanlan/api/rankings/recompute")
async def recompute_rankings(data: dict = None):
    """用自定义权重重新排序（使用缓存中的完整过滤数据，秒级返回）"""
    global _latest_rankings
    from stock_fetcher import _score_and_rank, _select_top_n_with_diversity, FINANCIAL_SECTORS

    weights = (data or {}).get("weights", [0.25, 0.20, 0.25, 0.20, 0.10])
    if not _latest_rankings:
        return {"date": "", "total_all": 0, "total_filtered": 0,
                "soe_excluded": 0, "fin_excluded": 0,
                "rankings_all": [], "rankings": [], "generated_at": ""}

    filtered_data = _latest_rankings.get("filtered_data", [])
    if not filtered_data:
        return _latest_rankings

    soe_codes = set(_latest_rankings.get("soe_codes", []))

    # 重新评分
    scored = _score_and_rank(filtered_data, weights=weights)

    # 全量 Top 50
    top_all = _select_top_n_with_diversity(scored)

    # 去SOE + 去金融
    civil_scored = [s for s in scored if s["code"] not in soe_codes
                    and s.get("sector") not in FINANCIAL_SECTORS]
    top_civil = _select_top_n_with_diversity(civil_scored) if civil_scored else []

    def _fmt(s):
        return {
            "code": s.get("code", ""), "name": s.get("name", ""),
            "pb": s.get("pb", 0), "pe": s.get("pe"),
            "revenue_growth": s.get("revenue_growth"),
            "gross_margin": s.get("gross_margin"),
            "net_margin": s.get("net_margin"),
            "composite_score": s.get("composite_score", 0),
            "adjusted_score": s.get("adjusted_score"),
            "financial_health": s.get("financial_health"),
            "health_flags": s.get("health_flags", []),
            "cfps": s.get("cfps"), "roe": s.get("roe"),
            "net_profit_growth": s.get("net_profit_growth"),
            "sector": s.get("sector"),
        }

    return {
        "date": _latest_rankings.get("date", ""),
        "total_all": len(scored),
        "total_filtered": len(civil_scored),
        "soe_excluded": _latest_rankings.get("soe_excluded", 0),
        "fin_excluded": _latest_rankings.get("fin_excluded", 0),
        "rankings_all": [_fmt(s) for s in top_all],
        "rankings": [_fmt(s) for s in top_civil],
        "generated_at": datetime.now().isoformat(),
    }


@app.post("/guanlan/api/refresh/rankings", response_model=RefreshResponse)
async def refresh_rankings_endpoint():
    """手动刷新股票排名"""
    try:
        rankings_data, success, error_msg = await refresh_rankings()
        if success:
            count = len(rankings_data.get("rankings", [])) if rankings_data else 0
            return RefreshResponse(
                success=True,
                message=f"股票排名已刷新，共 {count} 只",
                updated_at=datetime.now().isoformat(),
            )
        else:
            return RefreshResponse(
                success=False,
                message=f"{error_msg}，已保留上次数据",
                updated_at=datetime.now().isoformat(),
            )
    except Exception as e:
        return RefreshResponse(
            success=False,
            message=f"刷新异常: {str(e)}",
            updated_at=datetime.now().isoformat(),
        )


# ── 刷新接口 ──────────────────────────────────────────

@app.post("/guanlan/api/refresh/macro", response_model=RefreshResponse)
async def refresh_macro_endpoint():
    """手动刷新宏观数据"""
    await refresh_macro_data()
    return RefreshResponse(
        success=True,
        message="宏观数据已刷新",
        updated_at=datetime.now().isoformat(),
    )


@app.post("/guanlan/api/refresh/strategies", response_model=RefreshResponse)
async def refresh_strategies_endpoint():
    """清除策略信号缓存，下次请求将重新计算"""
    import os
    cache_file = os.path.join(DATA_DIR, "strategy_signals_cache.json")
    try:
        if os.path.exists(cache_file):
            os.remove(cache_file)
        return RefreshResponse(
            success=True,
            message="策略信号缓存已清除，请刷新页面获取最新信号",
            updated_at=datetime.now().isoformat(),
        )
    except Exception as e:
        return RefreshResponse(
            success=False,
            message=f"清除缓存失败: {str(e)}",
            updated_at=datetime.now().isoformat(),
        )


@app.post("/guanlan/api/refresh/insights", response_model=RefreshResponse)
async def refresh_insights_endpoint():
    """手动刷新公众号解读"""
    try:
        await refresh_insights()
        return RefreshResponse(
            success=True,
            message="公众号解读已刷新",
            updated_at=datetime.now().isoformat(),
        )
    except Exception as e:
        return RefreshResponse(
            success=False,
            message=f"刷新失败: {str(e)}",
            updated_at=datetime.now().isoformat(),
        )


# ── 资金流向 API ─────────────────────────────────────

# 资金流全局缓存（与 rankings/dashboard 模式一致）
_latest_fund_flow: dict | None = None


def _load_cached_fund_flow() -> dict | None:
    """加载当日资金流缓存"""
    global _latest_fund_flow
    import os as _os
    cache_file = _os.path.join(DATA_DIR, "fund_flow_cache.json")
    if not _os.path.exists(cache_file):
        return None
    try:
        with open(cache_file) as f:
            data = json.load(f)
        if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
            _latest_fund_flow = data
            return data
    except Exception:
        pass
    return None


@app.get("/guanlan/api/fund-flow")
async def get_fund_flow():
    """获取资金流向数据（行业板块 + 个股主力资金）"""
    global _latest_fund_flow

    if _latest_fund_flow is None:
        _latest_fund_flow = _load_cached_fund_flow()

    if _latest_fund_flow is None:
        # 缓存缺失，返回空结构
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "industries": [],
            "individuals": [],
            "generated_at": datetime.now().isoformat(),
            "error": "暂无资金流数据，请点击刷新",
        }

    return _latest_fund_flow


@app.post("/guanlan/api/refresh/fund-flow", response_model=RefreshResponse)
async def refresh_fund_flow_endpoint():
    """手动刷新资金流向数据"""
    global _latest_fund_flow
    try:
        from fund_flow import fetch_fund_flow_data
        data, error = await fetch_fund_flow_data(force=True)
        if data is not None:
            _latest_fund_flow = data
            return RefreshResponse(
                success=True,
                message=f"资金流向已刷新，{len(data.get('industries', []))} 个行业",
                updated_at=datetime.now().isoformat(),
            )
        else:
            return RefreshResponse(
                success=False,
                message=error or "资金流数据获取失败",
                updated_at=datetime.now().isoformat(),
            )
    except Exception as e:
        return RefreshResponse(
            success=False,
            message=f"刷新异常: {str(e)}",
            updated_at=datetime.now().isoformat(),
        )


@app.post("/guanlan/api/refresh/csi300-pe", response_model=RefreshResponse)
async def refresh_csi300_pe_endpoint():
    """手动刷新沪深300 PE 历史数据（轻量，不触发全量宏观刷新）"""
    global _latest_dashboard
    try:
        from data_fetcher import fetch_csi300_pe_history
        csi300_pe = await fetch_csi300_pe_history(force=True)
        if _latest_dashboard and "charts" in _latest_dashboard:
            _latest_dashboard["charts"]["csi300_pe"] = csi300_pe
            _save_json("dashboard_cache.json", _latest_dashboard)
        return RefreshResponse(
            success=True,
            message=f"PE 数据已刷新，{len(csi300_pe)} 条月度记录",
            updated_at=datetime.now().isoformat(),
        )
    except Exception as e:
        return RefreshResponse(
            success=False,
            message=f"刷新异常: {str(e)}",
            updated_at=datetime.now().isoformat(),
        )


# ── 后台刷新逻辑 ──────────────────────────────────────

async def refresh_macro_data():
    """刷新宏观数据: 抓取指标 → 分析周期 → 计算配置 → 生成图表"""
    global _latest_dashboard

    print("[观澜] Refreshing macro data...")

    # 1. 获取指标 + source metadata
    indicators, source_metadata = await fetch_all_indicators(force=True)

    # 1.5 计算数据质量警告
    quality_warnings = _compute_quality_warnings(source_metadata)
    data_quality_warning = len(quality_warnings) > 0

    # 2. 分析周期 (传入 source_metadata 用于置信度惩罚)
    cycle_result = analyze_cycle(indicators, source_metadata)
    cycle = cycle_result["cycle"]
    confidence = cycle_result["confidence"]
    growth_momentum = cycle_result["growth_momentum"]
    inflation_momentum = cycle_result["inflation_momentum"]

    # 3. 计算资产配置
    allocation = get_allocation(cycle)

    # 4. 生成图表数据
    chart_raw = get_allocation_chart_data(allocation)
    quadrant = get_quadrant_chart_data(growth_momentum, inflation_momentum)

    # 4.5 获取沪深300 PE 历史数据（非阻塞，失败不影响主流程）
    from data_fetcher import fetch_csi300_pe_history
    try:
        csi300_pe = await fetch_csi300_pe_history(force=True)
    except Exception as e:
        print(f"[观澜] CSI300 PE fetch failed (non-fatal): {e}")
        csi300_pe = []

    # 4.6 获取估值温度计（PE/PB分位 + ERP）
    from data_fetcher import fetch_csi300_valuation
    from models import ValuationData
    try:
        val_raw = await fetch_csi300_valuation(force=True)
        valuation = ValuationData(**val_raw) if val_raw else None
    except Exception as e:
        print(f"[观澜] Valuation fetch failed (non-fatal): {e}")
        valuation = None

    # 4.7 估值温度计 → 调整股票类占比（B1）
    allocation_note = ""
    if valuation is not None and valuation.equity_weight > 0:
        allocation, allocation_note = adjust_allocation_by_valuation(
            allocation, valuation.equity_weight
        )
        chart_raw = get_allocation_chart_data(allocation)

    charts = ChartData(
        rose_data=chart_raw["rose_data"],
        pie_data=chart_raw["pie_data"],
        quadrant=quadrant,
        csi300_pe=csi300_pe,
    )

    # 5. 构建响应
    dashboard = DashboardResponse(
        cycle=cycle,
        cycle_confidence=confidence,
        indicators=indicators,
        allocation=allocation,
        charts=charts,
        growth_momentum=growth_momentum,
        inflation_momentum=inflation_momentum,
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        source_metadata=source_metadata,
        data_quality_warning=data_quality_warning,
        quality_warnings=quality_warnings,
        valuation=valuation,
        allocation_note=allocation_note,
    )

    _latest_dashboard = dashboard.model_dump()
    _save_json("dashboard_cache.json", _latest_dashboard)

    default_count = sum(1 for m in source_metadata.values() if m.get("source") == "default")
    conflict_count = sum(1 for m in source_metadata.values() if m.get("conflict"))
    print(f"[观澜] Macro refresh done. Cycle: {cycle.value} "
          f"(confidence: {confidence:.0%}), "
          f"growth={growth_momentum:+.3f}, inflation={inflation_momentum:+.3f}, "
          f"defaults={default_count}, conflicts={conflict_count}")

    return _latest_dashboard


async def refresh_insights():
    """刷新公众号解读: 获取文章 → LLM 摘要 → 存储"""
    global _latest_insights

    from wechat_reader import fetch_articles_today
    from llm_summarizer import summarize_articles, extract_stance_from_articles

    print("[观澜] Refreshing insights...")

    # 1. 获取今日文章
    articles = await fetch_articles_today()

    if not articles:
        # 创建空解读
        insights = InsightsResult(
            date=datetime.now().strftime("%Y-%m-%d"),
            articles_count=0,
            articles=[],
            common_themes=[],
            investment_advice="今日暂无新文章。",
            cycle_relevance="",
            full_interpretation="## 今日暂无新文章\n\n「投资明见」今日未发布新内容。请明日19:00后再查看。",
            generated_at=datetime.now().isoformat(),
        )
    else:
        # 2. LLM 摘要
        # 将 Pydantic model 转为 dict（保留 content 字段）
        articles_dicts = []
        for a in articles:
            if isinstance(a, ArticleItem):
                articles_dicts.append(a.model_dump())
            else:
                articles_dicts.append(a)

        cycle_str = ""
        if _latest_dashboard:
            cycle_str = _latest_dashboard.get("cycle", "")

        insights = await summarize_articles(articles_dicts, cycle_str, max_articles_for_llm=3)

        # ── 新增: 从文章中提取结构化交易立场（独立 LLM 调用）──
        if insights is not None:
            try:
                stance_dict = await extract_stance_from_articles(
                    articles_dicts, max_articles=2
                )
                if stance_dict:
                    from models import XuXiaomingStance
                    insights.xu_xiaoming_stance = XuXiaomingStance(**stance_dict)
                    print(f"[观澜] XuXiaoming stance: {stance_dict.get('market_stance')} "
                          f"/ {stance_dict.get('position_recommendation')}")
            except Exception as e:
                print(f"[观澜] Stance extraction failed (non-fatal): {e}")

        if insights is None:
            # LLM 失败时的降级 — 保留文章全文内容
            fallback_article_items = []
            for a in articles_dicts:
                fallback_article_items.append(ArticleItem(
                    title=a.get("title", "无标题"),
                    url=a.get("url", ""),
                    summary=a.get("summary", ""),
                    content=a.get("content", ""),
                    key_point="",
                    publish_time=a.get("publish_time", ""),
                    source=a.get("source", ""),
                ))

            insights = InsightsResult(
                date=datetime.now().strftime("%Y-%m-%d"),
                articles_count=len(articles),
                articles=fallback_article_items,
                common_themes=[],
                investment_advice="LLM 摘要生成失败，请稍后重试。",
                cycle_relevance="",
                full_interpretation=f"## 今日文章 ({len(articles)}篇)\n\n"
                                   f"LLM 摘要服务暂时不可用。请查看下方原文。\n\n" +
                                   "\n".join(f"- **{a.get('title', '')}**" for a in articles_dicts),
                generated_at=datetime.now().isoformat(),
            )

    _latest_insights = insights

    # 追加到历史记录
    insights_dict = insights.model_dump() if isinstance(insights, InsightsResult) else insights
    history = _load_json("insights_history.json", [])
    # 替换同一天的记录
    today = datetime.now().strftime("%Y-%m-%d")
    history = [h for h in history if h.get("date") != today]
    history.insert(0, insights_dict)
    # 只保留最近 90 天
    history = history[:90]
    _save_json("insights_history.json", history)
    _save_json("insights_cache.json", insights_dict)

    print(f"[观澜] Insights refresh done. {insights_dict.get('articles_count', 0)} articles.")

    return insights_dict


async def refresh_rankings():
    """刷新股票排名: 抓取 → 评分 → Top 50 → 缓存
    返回 (rankings_data, success, error_msg)
    """
    global _latest_rankings
    from stock_fetcher import fetch_stock_rankings

    print("[观澜] Refreshing stock rankings...")
    rankings_data, error_msg = await fetch_stock_rankings(force=True)

    if rankings_data is None:
        # ★ API 获取失败, 保留旧缓存不覆盖
        print(f"[观澜] Rankings refresh FAILED: {error_msg} — keeping old cache")
        return _latest_rankings, False, error_msg

    # ★ 只有成功获取到数据才更新缓存
    _latest_rankings = rankings_data
    _save_json("stock_rankings_cache.json", rankings_data)
    count = len(rankings_data.get("rankings", []))
    print(f"[观澜] Rankings refresh done. "
          f"{rankings_data.get('total_filtered', 0)} filtered, {count} ranked.")
    return rankings_data, True, ""


# ── 策略回测 API ─────────────────────────────────────

def _default_position_size_from_valuation() -> float:
    """position_size 未显式传入时，回退到估值温度计建议股票仓位（0~1）。"""
    global _latest_dashboard
    try:
        val = (_latest_dashboard or {}).get("valuation") or {}
        w = val.get("equity_weight")
        if w and w > 0:
            return max(0.1, min(1.0, round(w / 100.0, 2)))
    except Exception:
        pass
    return 1.0



@app.get("/guanlan/api/backtest")
async def run_backtest_endpoint(
    fund_code: str = Query(default="510300", description="ETF代码，如 510300"),
    entry_strategy: str = Query(default="dual-ma-trend", description="入场策略ID"),
    exit_strategy: str = Query(default="trailing-stop", description="离场策略ID"),
    start_date: str = Query(default="2021-01-01", description="回测起始日期"),
    end_date: str = Query(default="2025-12-31", description="回测结束日期"),
    initial_capital: float = Query(default=100000, ge=1000, description="初始资金"),
    position_size: float = Query(default=None, ge=0.1, le=1.0, description="仓位比例（缺省按估值建议仓位）"),
    cycle_assumption: str = Query(default="复苏期", description="宏观周期假设"),
):
    """运行策略回测：在历史数据上模拟入场+离场策略组合"""
    from backtest_engine import run_backtest as _run_backtest

    if position_size is None:
        position_size = _default_position_size_from_valuation()

    # 验证入场策略
    from quant_strategies import STRATEGY_DEFS
    valid_entry_ids = {s["id"] for s in STRATEGY_DEFS}
    if entry_strategy not in valid_entry_ids:
        available = ", ".join(sorted(valid_entry_ids))
        raise HTTPException(status_code=400, detail=f"未知入场策略: {entry_strategy}。可用: {available}")

    # 验证离场策略
    from exit_strategies import EXIT_STRATEGY_DEFS
    valid_exit_ids = {s["id"] for s in EXIT_STRATEGY_DEFS}
    if exit_strategy not in valid_exit_ids:
        available = ", ".join(sorted(valid_exit_ids))
        raise HTTPException(status_code=400, detail=f"未知离场策略: {exit_strategy}。可用: {available}")

    # 验证周期假设
    valid_cycles = {"复苏期", "过热期", "滞胀期", "衰退期"}
    if cycle_assumption not in valid_cycles:
        raise HTTPException(status_code=400,
                          detail=f"未知周期: {cycle_assumption}。可用: {', '.join(sorted(valid_cycles))}")

    try:
        result = _run_backtest(
            fund_code=fund_code,
            entry_strategy_id=entry_strategy,
            exit_strategy_id=exit_strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            position_size=position_size,
            cycle_assumption=cycle_assumption,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"回测执行失败: {str(e)}")


@app.get("/guanlan/api/backtest/compare-exits")
async def run_backtest_compare_endpoint(
    fund_code: str = Query(default="510300", description="ETF代码，如 510300"),
    entry_strategy: str = Query(default="dual-ma-trend", description="入场策略ID"),
    exit_strategies: str = Query(
        default="trailing-stop,fixed-tp,time-exit,technical-exit,atr-stop,max-drawdown,scale-out",
        description="逗号分隔的离场策略ID列表"),
    start_date: str = Query(default="2021-01-01", description="回测起始日期"),
    end_date: str = Query(default="2025-12-31", description="回测结束日期"),
    initial_capital: float = Query(default=100000, ge=1000, description="初始资金"),
    position_size: float = Query(default=None, ge=0.1, le=1.0, description="仓位比例（缺省按估值建议仓位）"),
    cycle_assumption: str = Query(default="复苏期", description="宏观周期假设"),
):
    """单入场 + 多离场策略对比回测：一次拉取行情，多个离场策略独立模拟，返回对比数据包。"""
    from backtest_engine import run_backtest_multi_exit as _run_multi

    if position_size is None:
        position_size = _default_position_size_from_valuation()

    # 验证入场策略
    from quant_strategies import STRATEGY_DEFS
    valid_entry_ids = {s["id"] for s in STRATEGY_DEFS}
    if entry_strategy not in valid_entry_ids:
        available = ", ".join(sorted(valid_entry_ids))
        raise HTTPException(status_code=400, detail=f"未知入场策略: {entry_strategy}。可用: {available}")

    # 解析并验证离场策略列表
    from exit_strategies import EXIT_STRATEGY_DEFS
    valid_exit_ids = {s["id"] for s in EXIT_STRATEGY_DEFS}
    exit_ids = [x.strip() for x in exit_strategies.split(",") if x.strip()]
    exit_ids = list(dict.fromkeys(exit_ids))  # 去重保序
    if not exit_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个离场策略")
    unknown = [x for x in exit_ids if x not in valid_exit_ids]
    if unknown:
        available = ", ".join(sorted(valid_exit_ids))
        raise HTTPException(status_code=400,
                          detail=f"未知离场策略: {', '.join(unknown)}。可用: {available}")

    # 验证周期假设
    valid_cycles = {"复苏期", "过热期", "滞胀期", "衰退期"}
    if cycle_assumption not in valid_cycles:
        raise HTTPException(status_code=400,
                          detail=f"未知周期: {cycle_assumption}。可用: {', '.join(sorted(valid_cycles))}")

    try:
        result = _run_multi(
            fund_code=fund_code,
            entry_strategy_id=entry_strategy,
            exit_strategy_ids=exit_ids,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            position_size=position_size,
            cycle_assumption=cycle_assumption,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"对比回测执行失败: {str(e)}")


# ── 定投 (DCA) API ────────────────────────────────────

@app.get("/guanlan/api/dca/decision")
async def get_dca_decision():
    """定投档位决策：综合各策略定投档位 + 估值温度计，输出本期定投倍数建议。"""
    from quant_strategies import get_all_strategies, synthesize_dca_decision
    from strategy_engine import compute_all_signals
    from dca_engine import dca_target_exit

    cycle_str = _latest_dashboard.get("cycle", "复苏期") if _latest_dashboard else "复苏期"
    valuation = (_latest_dashboard or {}).get("valuation") or None

    signals = compute_all_signals()
    strategies = get_all_strategies(cycle_str, signals)
    dca = synthesize_dca_decision(strategies, valuation)

    # 定投止盈/再平衡建议（止盈导向，而非止损）
    pe_pct = (valuation or {}).get("pe_percentile")
    exit_sig = dca_target_exit(pe_pct, None)

    return {
        "cycle": cycle_str,
        "valuation": valuation,
        "dca": dca,
        "exit_suggestion": exit_sig,
        "generated_at": datetime.now().isoformat(),
    }


@app.get("/guanlan/api/dca/backtest")
async def run_dca_backtest_endpoint(
    fund_code: str = Query(default="510300", description="ETF/指数/基金/黄金代码"),
    start_date: str = Query(default="2021-01-01", description="定投起始日期"),
    end_date: str = Query(default="2025-12-31", description="定投结束日期"),
    amount_per_period: float = Query(default=2000.0, ge=100, description="每期金额"),
    period: str = Query(default="monthly", description="定投周期 monthly|weekly"),
    subscription_fee_pct: float = Query(default=None, description="申购费率%(缺省按类型自动)"),
    dividend_reinvest: bool = Query(default=True, description="分红再投资口径"),
):
    """定投回测：固定定投 vs 估值加码定投 vs 一次性买入 三模式对比（含 XIRR）。"""
    from dca_engine import run_dca_backtest as _run_dca

    if period not in ("monthly", "weekly"):
        raise HTTPException(status_code=400, detail="period 仅支持 monthly 或 weekly")

    try:
        return _run_dca(
            fund_code=fund_code,
            start_date=start_date,
            end_date=end_date,
            amount_per_period=amount_per_period,
            period=period,
            subscription_fee_pct=subscription_fee_pct,
            dividend_reinvest=dividend_reinvest,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"定投回测执行失败: {str(e)}")


# ── 策略静态元信息 API ───────────────────────────────

@app.get("/guanlan/api/strategy-info")
async def get_strategy_info(
    exit_strategy: str = Query(None, description="离场策略ID"),
    entry_strategy: str = Query(None, description="入场策略ID"),
):
    """返回策略静态元信息（名称/简介/规则/说明），不计算信号、不拉取行情。"""
    from exit_strategies import EXIT_STRATEGY_DEFS
    from quant_strategies import STRATEGY_DEFS

    if not exit_strategy and not entry_strategy:
        raise HTTPException(status_code=400, detail="需提供 exit_strategy 或 entry_strategy 参数")

    out = {"exit": None, "entry": None}

    if exit_strategy:
        m = next((s for s in EXIT_STRATEGY_DEFS if s["id"] == exit_strategy), None)
        if m is None:
            raise HTTPException(status_code=404, detail=f"未知离场策略: {exit_strategy}")
        out["exit"] = {k: m.get(k) for k in ("id", "name", "category", "tagline",
                       "description", "rules", "frequency", "risk_level", "fund_type")}

    if entry_strategy:
        m = next((s for s in STRATEGY_DEFS if s["id"] == entry_strategy), None)
        if m is None:
            raise HTTPException(status_code=404, detail=f"未知入场策略: {entry_strategy}")
        out["entry"] = {k: m.get(k) for k in ("id", "name", "tagline",
                       "description", "rules", "frequency", "risk_level")}

    return out


# ── 静态文件 (mount 在 API 之后，确保 API 路由优先) ──

app.mount("/guanlan/", StaticFiles(directory=WEB_DIR, html=True), name="guanlan_static")


# ── 手动启动入口 ──────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("[观澜] Starting server on http://127.0.0.1:8002")
    uvicorn.run(app, host="127.0.0.1", port=8002)
