"""
观澜 — 经济周期分析引擎

改进版美林时钟 + 中国市场适配
用经济增长动量 + 通胀动量 两个维度判断经济周期阶段
"""

from models import IndicatorData, CycleStage


# ── 评分权重 ───────────────────────────────────────────

GROWTH_WEIGHTS = {
    "gdp":       0.30,
    "pmi":       0.30,
    "retail":    0.20,
    "fai":       0.15,
    "unemploy":  0.05,    # 失业率反向: 低失业 → 高增长
}

INFLATION_WEIGHTS = {
    "cpi":   0.45,
    "ppi":   0.35,
    "m2":    0.20,
}

# ── 指标基准值 (用于 Z-score 标准化) ──────────────────

BASELINE = {
    "gdp":       {"mean": 4.8, "std": 1.2},    # GDP 增速
    "pmi":       {"mean": 50.4, "std": 1.1},   # PMI
    "retail":    {"mean": 4.0, "std": 3.5},    # 社零增速
    "fai":       {"mean": 4.5, "std": 2.5},    # 固投增速
    "unemploy":  {"mean": 5.2, "std": 0.3},    # 失业率 (反向)
    "cpi":       {"mean": 1.5, "std": 1.0},    # CPI
    "ppi":       {"mean": 0.5, "std": 2.5},    # PPI
    "m2":        {"mean": 8.5, "std": 1.5},    # M2 增速
    "caixin_pmi": {"mean": 50.5, "std": 1.0}, # 财新PMI
}


def _zscore(value: float, mean: float, std: float) -> float:
    """计算 Z-score，并压缩到 [-2, 2]"""
    if std == 0:
        return 0
    z = (value - mean) / std
    return max(-2.0, min(2.0, z))


def _momentum_score(indicators: list[IndicatorData],
                    weights: dict[str, float],
                    reverse_codes: set[str] | None = None) -> float:
    """
    计算加权动量得分 (归一化到 [-1, 1])
    reverse_codes: 反向指标 (值越小越好，如失业率)
    """
    if reverse_codes is None:
        reverse_codes = set()

    total_weight = 0.0
    weighted_sum = 0.0

    ind_map = {i.code: i.value for i in indicators}

    for code, weight in weights.items():
        if code not in ind_map:
            continue
        value = ind_map[code]
        bl = BASELINE.get(code, {"mean": 0, "std": 1})
        z = _zscore(value, bl["mean"], bl["std"])

        # 反向指标取反
        if code in reverse_codes:
            z = -z

        # Z-score 映射到 [-1, 1]: z=-2→-1, z=0→0, z=2→1
        normalized = z / 2.0

        weighted_sum += normalized * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return round(weighted_sum / total_weight, 3)


def analyze_cycle(indicators: list[IndicatorData], source_metadata: dict = None) -> dict:
    """
    分析当前经济周期

    返回:
        cycle: 周期阶段
        confidence: 置信度 (0~1)
        growth_momentum: 增长动量 (-1~1)
        inflation_momentum: 通胀动量 (-1~1)
    """
    # 计算两个维度的动量得分
    growth_momentum = _momentum_score(
        indicators,
        GROWTH_WEIGHTS,
        reverse_codes={"unemploy"},   # 失业率越低越好
    )
    inflation_momentum = _momentum_score(
        indicators,
        INFLATION_WEIGHTS,
    )

    # 判定周期阶段
    cycle, confidence = _classify_cycle(growth_momentum, inflation_momentum, source_metadata)

    return {
        "cycle": cycle,
        "confidence": round(confidence, 3),
        "growth_momentum": growth_momentum,
        "inflation_momentum": inflation_momentum,
    }


def _classify_cycle(growth: float, inflation: float,
                    source_metadata: dict = None) -> tuple[CycleStage, float]:
    """
    根据增长和通胀动量判定周期 + 置信度

    四象限:
        growth > 0  & inflation < 0 → 复苏
        growth > 0  & inflation > 0 → 过热
        growth < 0  & inflation > 0 → 滞胀
        growth < 0  & inflation < 0 → 衰退

    置信度 = 基础置信度 - 默认值惩罚 - 冲突惩罚
    """
    # 基础置信度: 距离原点越远越确定 (无 0.5 底线)
    distance = (growth**2 + inflation**2) ** 0.5
    base_confidence = min(1.0, distance * 0.7)

    # 数据质量惩罚
    default_count = 0
    conflict_count = 0
    if source_metadata:
        for code, meta in source_metadata.items():
            if meta.get("source") == "default":
                default_count += 1
            if meta.get("conflict"):
                conflict_count += 1

    default_penalty = 0.2 * default_count
    conflict_penalty = 0.1 * conflict_count

    confidence = base_confidence - default_penalty - conflict_penalty
    confidence = max(0.05, min(1.0, confidence))  # 底线 0.05

    if growth >= 0 and inflation < 0:
        cycle = CycleStage.RECOVERY
    elif growth >= 0 and inflation >= 0:
        cycle = CycleStage.OVERHEAT
    elif growth < 0 and inflation >= 0:
        cycle = CycleStage.STAGFLATION
    else:
        cycle = CycleStage.RECESSION

    return cycle, confidence
