"""
观澜 — Pydantic 数据模型
"""

from pydantic import BaseModel
from typing import Optional
from enum import Enum


class CycleStage(str, Enum):
    RECESSION = "衰退期"
    RECOVERY = "复苏期"
    OVERHEAT = "过热期"
    STAGFLATION = "滞胀期"


class IndicatorData(BaseModel):
    """单个宏观指标数据点"""
    name: str           # 指标中文名
    code: str           # 指标代码
    value: float        # 最新值
    unit: str           # 单位 (%)
    change: Optional[float] = None     # 环比变化
    trend: Optional[str] = None        # "up" | "down" | "flat"
    date: str = ""                     # 数据日期
    source: str = ""                   # 数据来源: chinadata|nbs|default|caixin
    data_date: str = ""                # 实际数据观测日期
    conflict: bool = False             # 双源差异 > 10%


class MacroSnapshot(BaseModel):
    """宏观数据快照"""
    indicators: list[IndicatorData]
    growth_momentum: float        # 经济增长动量得分 (-1 ~ 1)
    inflation_momentum: float     # 通胀动量得分 (-1 ~ 1)
    cycle: CycleStage             # 当前周期阶段
    cycle_confidence: float       # 周期判断置信度 (0 ~ 1)
    last_updated: str             # 更新时间


class AllocationItem(BaseModel):
    """单个资产配置项"""
    asset: str            # 资产名称
    ratio: float          # 占比
    reason: str = ""      # 配置理由


class AllocationResult(BaseModel):
    """资产配置结果"""
    cycle: CycleStage
    cycle_confidence: float
    allocation: list[AllocationItem]
    indicators_summary: dict = {}   # 关键指标概要
    last_updated: str = ""


class ChartData(BaseModel):
    """图表数据（供 ECharts 使用）"""
    rose_data: list[dict]          # 南丁格尔玫瑰图
    pie_data: list[dict]           # 饼图
    quadrant: dict                 # 四象限散点图
    csi300_pe: list[dict] = []     # 沪深300 PE 历史数据 [{date, pe}, ...]


class ValuationData(BaseModel):
    """估值温度计数据"""
    pe: float = 0                  # 沪深300 滚动市盈率
    pe_percentile: float = 0       # PE 近10年分位数 (0~1)
    pb: float = 0                  # 沪深300 市净率
    pb_percentile: float = 0       # PB 近10年分位数 (0~1)
    erp: float = 0                 # 股债性价比 (1/PE - 10Y国债)
    bond_10y: float = 0            # 10年期国债收益率
    signal: str = "正常"           # 超配 | 正常 | 低配
    data_date: str = ""            # 数据日期
    equity_weight: float = 0       # 建议股票仓位% (0~100, 由ERP+PE分位映射)
    equity_band: str = ""          # 建议仓位区间描述
    dividend_yield: Optional[float] = None  # 沪深300股息率% (暂无稳定数据源, 置空)


class DashboardResponse(BaseModel):
    """仪表盘完整响应"""
    cycle: CycleStage
    cycle_confidence: float
    indicators: list[IndicatorData]
    allocation: list[AllocationItem]
    charts: ChartData
    growth_momentum: float
    inflation_momentum: float
    last_updated: str
    source_metadata: dict = {}            # {code: {source, data_date, conflict, ...}}
    data_quality_warning: bool = False    # 数据质量警告
    quality_warnings: list[str] = []      # 人类可读的警告信息
    valuation: Optional[ValuationData] = None  # 估值温度计
    allocation_note: str = ""             # 估值温度计调整资产配置的说明


class ArticleItem(BaseModel):
    """公众号文章"""
    title: str
    url: str = ""
    summary: str = ""          # 原文摘要
    content: str = ""          # 文章全文（用于前端展示和 LLM 分析）
    key_point: str = ""        # LLM 提炼的一句话观点
    publish_time: str = ""     # 发布时间
    source: str = ""           # 来源: wewe_rss / sina_blog / sogou / baidu


class InsightsResult(BaseModel):
    """每日解读结果"""
    date: str
    articles_count: int
    articles: list[ArticleItem]
    common_themes: list[str] = []
    investment_advice: str = ""
    cycle_relevance: str = ""
    full_interpretation: str = ""   # LLM 生成的完整解读
    generated_at: str = ""
    xu_xiaoming_stance: Optional["XuXiaomingStance"] = None  # 徐小明交易立场提取


class XuXiaomingStance(BaseModel):
    """从徐小明文章中提取的结构化交易立场（独立 LLM 调用）"""
    date: str = ""                              # 分析的文章日期
    market_stance: str = ""                     # "看多" | "看空" | "震荡"
    position_recommendation: str = ""           # "满仓" | "重仓" | "半仓" | "轻仓" | "清仓"
    key_reason: str = ""                        # 一句话理由（LLM 提炼，100字内）
    confidence: float = 0.0                     # LLM 自评置信度 0.0~1.0
    generated_at: str = ""                      # 提取时间 ISO
    articles_analyzed: int = 0                  # 分析的文章数量


class StrategySignal(BaseModel):
    """量化策略信号"""
    strategy_id: str
    strategy_name: str
    signal: str               # "买入" | "卖出" | "持有" | "观望"
    confidence: float         # 信号置信度
    reasoning: str            # 信号逻辑
    suggested_allocation: dict = {}  # 建议配置


class QuantStrategy(BaseModel):
    """量化策略定义"""
    id: str
    name: str
    tagline: str              # 一句话描述
    description: str          # 策略原理
    suitable_cycle: list[str] # 适用周期
    rules: str                # 信号规则
    frequency: str            # 调仓频率
    risk_level: str           # 风险等级: "低" | "中" | "高"
    current_signal: Optional[StrategySignal] = None
    etf_picks: list[dict] = []    # 推荐 ETF 列表 [{"name": "...", "code": "..."}]


class RefreshResponse(BaseModel):
    """手动刷新响应"""
    success: bool
    message: str
    updated_at: str = ""


class StockRankingItem(BaseModel):
    """单只股票排名数据"""
    code: str                       # 股票代码，如 "000001"
    name: str                       # 股票名称，如 "平安银行"
    pb: float                       # 市净率
    pe: Optional[float] = None      # 市盈率（亏损企业可为 None）
    revenue_growth: Optional[float] = None    # 主营增长率 (%)
    gross_margin: Optional[float] = None      # 主营利润率 / 销售毛利率 (%)
    net_margin: Optional[float] = None        # 净利润率 (%)
    shareholders: Optional[int] = None        # 股东人数
    composite_score: float                    # 综合评分 (0~1，越高越好)
    adjusted_score: Optional[float] = None    # 财务健康度调整后评分
    financial_health: Optional[float] = None  # 财务健康度 (0.3~1.0)
    health_flags: list[str] = []              # 健康警示标签
    cfps: Optional[float] = None              # 每股经营现金流
    roe: Optional[float] = None               # 净资产收益率 (%)
    net_profit_growth: Optional[float] = None # 净利润同比增长 (%)
    sector: Optional[str] = None              # 申万行业分类


class StockRankingsResponse(BaseModel):
    """每日股票排名响应"""
    date: str                       # 交易日日期
    total_all: int = 0              # 全量池（PB<2+去ST）股票数
    total_filtered: int             # 去SOE+金融后股票数
    soe_excluded: int = 0           # 排除的国企/央企数量
    fin_excluded: int = 0           # 排除的金融行业数量
    rankings_all: list[StockRankingItem] = []  # 全量 Top 50
    rankings: list[StockRankingItem]  # 民企 Top 50（去SOE+金融）
    generated_at: str               # 生成时间 ISO
    data_date: str = ""             # 财务数据日期 YYYYMMDD
    data_period: str = ""           # 财务数据季度 2026Q1


# ── 宏观推荐标的模型 ─────────────────────────────────────

class RecommendedETF(BaseModel):
    """推荐ETF标的"""
    asset_class: str            # 对应的大类资产名（如"成长型股票"）
    etf_name: str               # ETF名称
    etf_code: str               # ETF代码
    allocation_pct: float       # 该资产类别的配置比例 (0~1)
    reason: str = ""            # 配置理由


class RecommendedStock(BaseModel):
    """推荐股票标的（从排名中精选）"""
    code: str
    name: str
    score: float                # 调整后评分
    sector: str = ""
    reason: str = ""            # 一句话入选理由


class StrategySummary(BaseModel):
    """策略信号摘要"""
    strategy_name: str
    signal: str                 # "买入" | "持有" | "卖出" | "观望"
    confidence: float           # 信号置信度
    one_liner: str              # 一句话理由


# ── 金牛奖推荐模型 ─────────────────────────────────────

class GoldenBullCompany(BaseModel):
    """金牛奖获奖基金公司"""
    name: str                       # 公司名称，如"大成基金"
    award_level: str = "company"    # "company"（金牛基金管理公司）| "special"（专项奖）
    award_name: str = ""            # 奖项全称，如"金牛基金管理公司"
    award_category: str = ""        # 专项奖细分，如"主动权益" / "固定收益"
    star_products: list[str] = []   # 该公司获奖/明星产品名称列表
    star_managers: list[str] = []   # 该公司明星基金经理姓名列表


class GoldenBullProduct(BaseModel):
    """金牛奖获奖基金产品"""
    fund_name: str                  # 基金名称，如"大成高新技术产业股票"
    fund_code: str = ""             # 基金代码，如"000628"
    company_name: str = ""          # 所属基金公司
    award_name: str = ""            # 奖项全称，如"七年期开放式股票型持续优胜金牛基金"
    award_category: str = ""        # 大类：股票型 / 混合型 / 债券型


class GoldenBullManager(BaseModel):
    """金牛基金经理 / 明星基金经理"""
    name: str                       # 经理姓名
    company_name: str = ""          # 所属公司
    title: str = ""                 # 职务，如"权益投资总监"
    representative_funds: list[str] = []  # 代表产品名称列表
    achievement: str = ""           # 一句话业绩简介


class GoldenBullSummary(BaseModel):
    """金牛奖推荐摘要"""
    award_info: str = "第22届金牛奖 (2025-12-30)"
    companies: list[GoldenBullCompany] = []
    products: list[GoldenBullProduct] = []
    managers: list[GoldenBullManager] = []


class MacroRecommendations(BaseModel):
    """宏观页面推荐标的聚合响应"""
    cycle: str
    etf_recommendations: list[RecommendedETF] = []
    top_stocks: list[RecommendedStock] = []
    top_strategies: list[StrategySummary] = []
    golden_bull: Optional[GoldenBullSummary] = None
    generated_at: str = ""


# ── 离场策略模型 ─────────────────────────────────────────

class ExitAction(BaseModel):
    """单个离场操作建议"""
    name: str               # "减仓至70%仓位" / "清仓"
    ratio: float            # 建议剩余仓位比例 0.0~1.0
    reason: str = ""        # 简短原因


class ExitConditionDetail(BaseModel):
    """离场条件明细"""
    name: str               # 条件名，如 "盈利≥15%"
    met: bool               # 是否触发
    current: str = ""       # 当前值，如 "+18.3%"
    threshold: str = ""     # 触发阈值，如 "≥15%"
    weight: float = 0.0     # 权重（黄金策略用）


class ExitStrategySignal(BaseModel):
    """离场策略信号"""
    strategy_id: str
    strategy_name: str
    signal: str                     # "清仓" | "减仓" | "持有" | "观望"
    confidence: float               # 信号置信度 0~1
    reasoning: str                  # 信号逻辑
    actions: list[ExitAction] = []  # 具体操作建议
    pnl_pct: Optional[float] = None         # 当前盈亏百分比
    days_held: Optional[int] = None         # 已持有天数
    redemption_fee: Optional[float] = None  # 当前赎回费率 (%)
    next_fee_breakpoint: Optional[int] = None  # 距下一费率断点天数
    conditions: list[ExitConditionDetail] = []  # 条件明细
    suggested_allocation: dict = {}   # 建议配置（预留）


class ExitStrategy(BaseModel):
    """离场策略定义"""
    id: str
    name: str
    category: str               # "止盈" | "止损" | "混合" | "信号" | "黄金"
    tagline: str                # 一句话描述
    description: str            # 策略原理 (Markdown)
    rules: str                  # 信号规则
    frequency: str              # 检查频率
    risk_level: str             # "低" | "中" | "高"
    fund_type: str = "domestic" # "domestic" | "qdii" | "gold" | "all"
    current_signal: Optional[ExitStrategySignal] = None


# ── 回测模型 ─────────────────────────────────────────────

class BacktestTradeRecord(BaseModel):
    """单笔回测交易记录"""
    date: str                           # 交易日期
    action: str                         # "买入" | "卖出" | "清仓" | "减仓" | "期末清仓"
    price: float                        # 成交价
    shares: float                       # 成交份额
    amount: float                       # 成交金额
    cash_after: float                   # 交易后现金
    equity: float = 0.0                 # 交易后总权益
    pnl_pct: Optional[float] = None     # 盈亏百分比（卖出时）
    reason: str = ""                    # 触发原因


class BacktestMetrics(BaseModel):
    """回测绩效指标"""
    total_return_pct: float             # 累计收益率 %
    cagr_pct: float                     # 年化收益率 %
    sharpe_ratio: float                 # 夏普比率
    max_drawdown_pct: float             # 最大回撤 %
    max_drawdown_duration_days: int     # 最大回撤持续天数
    win_rate_pct: float                 # 胜率 %
    profit_factor: float                # 盈亏比
    total_trades: int                   # 总交易次数
    benchmark_return_pct: float         # 基准收益率 (buy-and-hold)
    alpha_pct: float                    # 超额收益


class BacktestResult(BaseModel):
    """回测完整结果"""
    fund_code: str
    fund_name: str
    entry_strategy: str
    exit_strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float
    metrics: BacktestMetrics
    equity_curve: list[dict]            # [{date, equity, benchmark}, ...]
    trade_log: list[BacktestTradeRecord]
    cycle_assumption: str
    generated_at: str
