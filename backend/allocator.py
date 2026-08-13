"""
观澜 — 资产配置计算模块

基于美林时钟框架，根据经济周期阶段输出各类资产建议占比
"""

from models import CycleStage, AllocationItem, ChartData, RecommendedETF

# ── 美林时钟资产配置矩阵 (中国适配版) ────────────────

ALLOCATION_MATRIX: dict[CycleStage, list[dict]] = {
    CycleStage.RECESSION: [
        {"asset": "债券 (长久期)",  "ratio": 0.35, "reason": "利率下行，债券牛市"},
        {"asset": "货币基金",       "ratio": 0.20, "reason": "流动性充裕，稳健收益"},
        {"asset": "黄金",          "ratio": 0.15, "reason": "避险需求上升"},
        {"asset": "债券 (短久期)",  "ratio": 0.15, "reason": "信用利差收窄"},
        {"asset": "防御性股票",     "ratio": 0.10, "reason": "公用事业/必选消费抗跌"},
        {"asset": "现金",          "ratio": 0.05, "reason": "保持流动性"},
    ],
    CycleStage.RECOVERY: [
        {"asset": "成长型股票",     "ratio": 0.30, "reason": "盈利预期改善，估值扩张"},
        {"asset": "价值型股票",     "ratio": 0.20, "reason": "经济回暖带动蓝筹修复"},
        {"asset": "债券 (中久期)",  "ratio": 0.15, "reason": "利率低位，适度配置"},
        {"asset": "商品 (工业金属)","ratio": 0.15, "reason": "工业需求回升"},
        {"asset": "REITs",         "ratio": 0.10, "reason": "资产价格上涨"},
        {"asset": "现金",          "ratio": 0.10, "reason": "保持灵活"},
    ],
    CycleStage.OVERHEAT: [
        {"asset": "商品 (能源)",    "ratio": 0.25, "reason": "通胀推升大宗商品"},
        {"asset": "周期股",        "ratio": 0.20, "reason": "盈利峰值阶段"},
        {"asset": "黄金",          "ratio": 0.20, "reason": "抗通胀属性"},
        {"asset": "债券 (短久期)",  "ratio": 0.15, "reason": "防御利率上行"},
        {"asset": "新兴市场股票",   "ratio": 0.10, "reason": "全球同步过热"},
        {"asset": "现金",          "ratio": 0.10, "reason": "等待回调机会"},
    ],
    CycleStage.STAGFLATION: [
        {"asset": "现金 / 存款",    "ratio": 0.30, "reason": "不确定性高，现金为王"},
        {"asset": "黄金",          "ratio": 0.25, "reason": "滞胀期黄金表现最优"},
        {"asset": "债券 (短久期)",  "ratio": 0.20, "reason": "规避长久期利率风险"},
        {"asset": "商品 (能源)",    "ratio": 0.15, "reason": "供给约束推升能源"},
        {"asset": "防御性股票",     "ratio": 0.05, "reason": "仅保留必需消费"},
        {"asset": "货币基金",       "ratio": 0.05, "reason": "保持流动性"},
    ],
}


def get_allocation(cycle: CycleStage) -> list[AllocationItem]:
    """根据周期阶段获取资产配置建议"""
    items = ALLOCATION_MATRIX.get(cycle, ALLOCATION_MATRIX[CycleStage.RECESSION])

    return [
        AllocationItem(
            asset=item["asset"],
            ratio=item["ratio"],
            reason=item.get("reason", ""),
        )
        for item in items
    ]


def get_allocation_chart_data(allocation: list[AllocationItem]) -> dict:
    """生成 ECharts 图表数据"""
    # 玫瑰图数据
    rose_data = [
        {"name": item.asset, "value": round(item.ratio * 100, 1)}
        for item in allocation
    ]

    # 饼图数据 (带颜色)
    COLORS = [
        "#c23531", "#2f4554", "#61a0a8", "#d48265",
        "#91c7ae", "#749f83", "#ca8622", "#bda29a",
        "#6e7074", "#546570",
    ]
    pie_data = [
        {
            "name": item.asset,
            "value": round(item.ratio * 100, 1),
            "itemStyle": {"color": COLORS[i % len(COLORS)]},
        }
        for i, item in enumerate(allocation)
    ]

    return {"rose_data": rose_data, "pie_data": pie_data}


def get_quadrant_chart_data(growth_momentum: float,
                            inflation_momentum: float) -> dict:
    """
    生成四象限散点图数据 (增长 vs 通胀)
    """
    # 四个象限的背景标签
    quadrants = [
        {"name": "过热期", "x": 1, "y": 1},
        {"name": "复苏期", "x": 1, "y": -1},
        {"name": "滞胀期", "x": -1, "y": 1},
        {"name": "衰退期", "x": -1, "y": -1},
    ]

    # 当前位置 (放大坐标以便在图上显示)
    current = {
        "name": "当前位置",
        "x": round(growth_momentum * 3, 2),
        "y": round(inflation_momentum * 3, 2),
    }

    return {
        "quadrants": quadrants,
        "current": current,
        "growth_momentum": growth_momentum,
        "inflation_momentum": inflation_momentum,
    }


# ── 资产类别 → ETF 映射 ─────────────────────────────────

# 资产名关键词 → 首选 ETF 类别（一对一映射，避免噪声）
ASSET_TO_ETF_CATEGORY: dict[str, str] = {
    "成长型股票":   "growth",
    "价值型股票":   "value",
    "周期股":       "broad",
    "新兴市场股票": "broad",
    "防御性股票":   "dividend",
    "REITs":        "broad",
    "债券":          "bond",
    "黄金":          "gold",
    "商品":          "commodity",
    "现金":          "cash",
    "存款":          "cash",
    "货币基金":      "cash",
}


def get_etf_recommendations(allocation: list[AllocationItem]) -> list[RecommendedETF]:
    """根据资产配置方案推荐具体 ETF 标的"""
    # 延迟导入避免循环依赖
    from quant_strategies import ETF_PICKS

    seen_codes: set[str] = set()
    recommendations: list[RecommendedETF] = []

    for item in allocation:
        # 匹配资产名关键词 → 首选 ETF 类别
        category = "broad"  # 兜底
        for keyword, cat in ASSET_TO_ETF_CATEGORY.items():
            if keyword in item.asset:
                category = cat
                break

        etfs = ETF_PICKS.get(category, ETF_PICKS.get("broad", []))
        for etf in etfs:
            if etf["code"] not in seen_codes:
                seen_codes.add(etf["code"])
                recommendations.append(RecommendedETF(
                    asset_class=item.asset,
                    etf_name=etf["name"],
                    etf_code=etf["code"],
                    allocation_pct=item.ratio,
                    reason=item.reason,
                ))

    return recommendations
