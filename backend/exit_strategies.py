"""
观澜 — 基金/QDII 离场策略库

9 种离场策略，覆盖止盈、止损、时间、技术、黄金等类型。
输出比例式离场信号（减仓至 x%/清仓），而非简单买卖。
"""

from datetime import datetime, timedelta
from models import (
    ExitStrategy, ExitStrategySignal,
    ExitAction, ExitConditionDetail,
)

# ── 策略定义 ─────────────────────────────────────────────

EXIT_STRATEGY_DEFS = [
    {
        "id": "fixed-tp",
        "category": "止盈",
        "fund_type": "domestic",
        "name": "固定止盈",
        "tagline": "盈利达到预设目标即分批减仓，落袋为安",
        "description": """
### 一句话解释

设定几个盈利目标，每到一档就减一部分仓位。赚到了就锁定，不贪最后一口。

### 怎么用

分三档止盈：
- **+8%** → 减仓至 70%（先锁定本金）
- **+15%** → 减仓至 50%（利润留存一半）
- **+25%** → 清仓（赚够了走人）

### 赎回费提醒

如果当前赎回费还很高（持有不足 30 天），且距下一档费率断点不到 10 天，会建议再等等——省下的赎回费也是利润。

### 适合谁

适合有明确盈利预期、不想天天盯盘的人。宽基指数基金年化收益 8-12% 是合理预期，8% 止盈第一档不贪心。
""",
        "rules": "+8%→减至70% | +15%→减至50% | +25%→清仓 | 结合赎回费断点优化",
        "frequency": "每周检查一次",
        "risk_level": "低",
    },
    {
        "id": "trailing-stop",
        "category": "止盈",
        "fund_type": "domestic",
        "name": "移动止盈（追踪止损）",
        "tagline": "让利润奔跑，但设好回撤底线——净值从高点回落触发离场",
        "description": """
### 一句话解释

不预设固定的止盈价，而是跟随净值上涨不断提高止盈线。当净值从最高点回落一定幅度时，触发离场。

### 怎么用

- 盈利超过 **10%** 后激活追踪（先有利润安全垫）
- 从持仓期间最高净值回撤 **5%** → 减仓至 50%
- 回撤 **8%** → 清仓

### 举例

你 3.00 元买入沪深300ETF，涨到 3.50（+16.7%），追踪激活。
最高涨到 3.80 → 回撤到 3.61（-5%从高点）→ 减半仓。
继续跌到 3.50（-8%）→ 清仓。

你锁定了约 +17% 的利润（而不是眼睁睁看着全部回吐）。

### 适合谁

适合趋势性行情——牛市涨得多，能吃到大部分涨幅；震荡市会被频繁震出去。宽基 ETF 回撤 5-8% 是合理阈值。
""",
        "rules": "盈利>10%激活追踪 | 回撤5%→减至50% | 回撤8%→清仓",
        "frequency": "每天检查",
        "risk_level": "中",
    },
    {
        "id": "time-exit",
        "category": "混合",
        "fund_type": "all",
        "name": "时间止盈（费率优化）",
        "tagline": "持有到期 + 费率断点优化——不浪费在惩罚赎回费上",
        "description": """
### 一句话解释

基金有赎回费阶梯：持有不到 7 天罚 1.5%，30 天内 0.5%，一年以上才免费。时间止盈帮你对齐费率断点，避免"赚了净值亏了手续费"。

### 怎么用

| 持有天数 | 赎回费率 | 策略建议 |
|---------|---------|---------|
| <7 天 | 1.5% | ⚠️ 警告高惩罚费，除非极端情况不建议赎回 |
| 7-30 天 | 0.5% | 若盈利 >5% 可减仓至 50%；否则持有等费率降 |
| 30-180 天 | 0.1% | 正常评估，低成本灵活操作 |
| 180-365 天 | 0.05% | 几乎无摩擦成本，看信号本身 |
| >365 天 | 0% | 免费赎回，只看信号 |

### 适合谁

适合定投族和长期持有者。很多人频繁申赎基金，一年手续费吃掉 2-3% 的收益——时间止盈帮你省下这笔钱。
""",
        "rules": "<7天警告 | 7-30天盈利>5%可减 | 30-180天正常评估 | >180天低成本 | >365天免费",
        "frequency": "每周检查",
        "risk_level": "低",
    },
    {
        "id": "technical-exit",
        "category": "信号",
        "fund_type": "all",
        "name": "技术指标离场",
        "tagline": "均线死叉 + RSI超买 + MACD转空 + 动量转负，综合判断该撤了",
        "description": """
### 一句话解释

不看盈亏，只看盘面语言。四个经典技术指标一起说话：
1. **MA 死叉**：短期均线下穿长期均线
2. **RSI 超买**：涨得太猛该歇歇了
3. **MACD 死叉**：动能转弱
4. **动量转负**：最近确实在跌

### 怎么用

四个条件分别是独立判断维度，触发越多信号越强：
- 触发 **2 个** → 减仓至 70%（多个信号共振，注意风险）
- 触发 **3 个** → 减仓至 50%（信号强烈，减半仓防守）
- 触发 **4 个** → 清仓（全面转空，走为上）

### 注意

技术指标在趋势市中好用，在窄幅震荡中会频繁给出假信号。建议搭配其他策略交叉验证。
""",
        "rules": "MA死叉+RSI>70+MACD死叉+动量<-3% | 2个→减至70% | 3个→减至50% | 4个→清仓",
        "frequency": "每天检查",
        "risk_level": "中",
    },
    {
        "id": "atr-stop",
        "category": "止损",
        "fund_type": "all",
        "name": "ATR 波动止损",
        "tagline": "根据基金自身的波动程度动态设定止损位——波动大的放宽，波动小的收紧",
        "description": """
### 一句话解释

每只基金的"脾气"不一样——有的每天上下 2%，有的不到 0.5%。用 ATR（平均真实波幅）来量化这个脾气，然后按 2.5 倍 ATR 设定止损距离。

### 怎么用

- **止损位** = 入场净值 − 2.5 × ATR(14)
- 当前净值触及止损位 → **清仓**
- 接近止损位（距止损线不到 1 倍 ATR）→ **减仓至 50%**

### 为什么是 2.5 倍（不是个股常用的 2 倍）

宽基指数基金的波动率只有个股的 1/3 到 1/2。如果用 2 倍 ATR，正常波动就会频繁触发止损。2.5 倍给了足够的"呼吸空间"。

### 举例

沪深300ETF 入场净值 3.50，ATR(14)=0.06（约 1.7%）。
止损位 = 3.50 − 2.5×0.06 = 3.35（跌 4.3% 触发清仓）。

### 适合谁

适合重视风险控制、能接受小额亏损的纪律型投资者。
""",
        "rules": "止损位=入场价−2.5×ATR(14) | 触及→清仓 | 接近→减至50%",
        "frequency": "每天检查",
        "risk_level": "中",
    },
    {
        "id": "scale-out",
        "category": "止盈",
        "fund_type": "domestic",
        "name": "分批止盈",
        "tagline": "三阶段纪律性减仓：先回收本金，再锁定利润，最后让子弹飞",
        "description": """
### 一句话解释

不要一次性全卖了——太粗糙。分三阶段减仓：第一档回收本金，第二档锁定大部分利润，剩下的仓位让趋势继续跑。

### 怎么用

| 阶段 | 触发条件 | 操作 |
|------|---------|------|
| 第一阶段 | 盈利 +10% | 减仓至 70%（回收本金 + 部分利润） |
| 第二阶段 | 盈利 +20% | 再减仓至 30%（大部分利润已入袋） |
| 第三阶段 | 剩余 30% 仓位 | 启动移动止盈，回撤 8% 清仓 |

### 为什么好用

- 不会卖飞：最后 30% 仓位跟着趋势走
- 不会坐过山车：前两阶段已经锁定了大部分利润
- 心理舒服：始终有仓位，心态更稳

### 适合谁

适合定投累计型持仓。你通过定投慢慢攒了很多份额，一次性清仓心理压力大——分批止盈让每次操作都很轻。
""",
        "rules": "+10%→减至70% | +20%→减至30% | 剩余30%移动止盈(回撤8%清仓)",
        "frequency": "每周检查",
        "risk_level": "低",
    },
    {
        "id": "max-drawdown",
        "category": "止损",
        "fund_type": "all",
        "name": "最大回撤离场",
        "tagline": "从最高点回撤超过阈值就减仓——宁可卖早，不坐过山车",
        "description": """
### 一句话解释

不看盈利目标，看回撤幅度。从持仓期间的最高净值算起，跌了多少就触发离场。

### 怎么用

- 从最高点回撤 **10%** → 减仓至 50%
- 回撤 **15%** → 清仓

### 为什么基金用 10/15%（不是个股的 15/25%）

宽基指数的最大回撤通常在 15-25%（熊市极端可达 30-40%）。10% 回撤是一个合理的"注意信号"，15% 是"可能趋势反转了"的信号。如果等到 25% 再走，心态早崩了。

### 无入场参数时

用基金过去 60 日和 120 日的最高点作为参考基准，评估当前位置的回撤幅度。

### 适合谁

适合风险厌恶型投资者。"少赚可以，大亏不行"——这个策略就是为这个心态设计的。
""",
        "rules": "回撤10%→减至50% | 回撤15%→清仓 | 无入场价用60/120日最高点",
        "frequency": "每周检查",
        "risk_level": "中",
    },
    {
        "id": "cycle-reversal",
        "category": "信号",
        "fund_type": "all",
        "name": "宏观周期反转离场",
        "tagline": "经济周期变了，持仓逻辑就变了——周期不适合就撤",
        "description": """
### 一句话解释

你当初买股票型基金，是因为经济在复苏/过热期。如果经济周期已经进入滞胀或衰退期，持有逻辑就不成立了——这时候应该离场。

### 怎么用

| 宏观周期 | 股票型基金 | 债券型基金 | 黄金 |
|---------|-----------|-----------|------|
| 复苏期 | ✅ 持有 | 正常 | 减仓至 70%（资金偏好风险资产） |
| 过热期 | 减仓至 50%（通胀风险） | 减仓至 70% | 减仓至 50%（实际利率上升压力） |
| 滞胀期 | 减仓至 30%（最差环境） | 持有 | ✅ 持有（避险需求） |
| 衰退期 | 清仓 | ✅ 持有 | ✅ 持有（降息利好黄金） |

### QDII 额外维度

对于 QDII 基金，还会叠加汇率判断：人民币升值超过 3% 会侵蚀海外收益。

### 适合谁

适合做资产配置、根据经济周期切换品种的投资者。这个策略和观澜的宏观仪表盘天然配合。
""",
        "rules": "复苏期→股票持有 | 过热期→股票减半 | 滞胀期→股票减至30% | 衰退期→股票清仓",
        "frequency": "每月检查",
        "risk_level": "中",
    },
    {
        "id": "xuxiaoming-exit",
        "category": "解读",
        "fund_type": "all",
        "name": "徐小明解读离场",
        "tagline": "根据徐小明每日文章的看多/看空立场和仓位建议，量化离场决策",
        "description": """
### 一句话解释

徐小明（「投资明见」公众号）每日盘后评论中会表达对后市的立场和仓位建议。系统通过独立的 LLM 调用将文章内容结构化提取为市场立场（看多/看空/震荡）和仓位建议（满仓/重仓/半仓/轻仓/清仓），并据此给出离场信号。

### 怎么用

系统每天自动从最新文章中提取：
- **市场立场**：看多 / 看空 / 震荡
- **仓位建议**：满仓 / 重仓 / 半仓 / 轻仓 / 清仓

综合判断逻辑：

| 立场 | 仓位建议 | 离场信号 |
|------|---------|---------|
| 看多 | 满仓/重仓 | **持有** — 坚定看多，维持仓位 |
| 看多 | 半仓/轻仓 | **持有** — 偏谨慎看多，保持观察 |
| 看空 | 清仓/轻仓 | **清仓** — 强烈一致看空，建议离场 |
| 看空 | 重仓/半仓 | **减仓至30%** — 看空信号明确，大幅降低风险 |
| 震荡 | 满仓/重仓 | **持有** — 震荡但偏积极 |
| 震荡 | 半仓 | **持有** — 平衡市，不动 |
| 震荡 | 清仓/轻仓 | **减仓至50%** — 震荡+保守仓位，降仓防守 |

### 注意事项

- 数据来源为「投资明见」博客（新浪博客同步），每天通过 LLM 自动分析
- LLM 提取可能存在偏差，建议结合其他策略（如宏观周期反转离场、技术指标离场）交叉验证
- 如果当日无文章或 LLM 提取失败，信号显示"观望"

### 与「宏观周期反转离场」的关系

两个策略互补：
- **周期反转离场**：从宏观周期角度判断持仓逻辑是否成立
- **徐小明解读离场**：从市场实战派角度捕捉短期方向变化

两者可能给出矛盾信号——这恰恰是价值所在：不同维度的独立判断帮助你更全面地评估风险。
""",
        "rules": "LLM提取↑立场(看多/看空/震荡)+仓位(满仓~清仓) | 看空→减仓/清仓 | 看多→持有 | 震荡→持有或减仓",
        "frequency": "每日更新（跟随解读）",
        "risk_level": "中",
    },
    {
        "id": "gold-exit",
        "category": "黄金",
        "fund_type": "gold",
        "name": "黄金离场策略",
        "tagline": "黄金不看盈利目标，看超买程度、实际利率和美元——五大条件加权判断",
        "description": """
### 一句话解释

黄金不是生息资产，不适用「盈利 N% 就走」的逻辑。黄金离场要看它真正的定价因子：超买程度、实际利率方向、美元强弱、以及宏观周期是否支持持有。

### 五大离场条件（加权判定）

| # | 条件 | 触发逻辑 | 权重 |
|---|------|---------|------|
| ① | 短期超买 | RSI(14) > 80 且 1 月涨幅 > 12% | 35% |
| ② | 均线死叉 | MA20 下穿 MA60 | 25% |
| ③ | 实际利率上升 | PPI 连续下行 + 名义利率上行 | 20% |
| ④ | 美元走强 | USD/CNY 1 月涨幅 > 1.5% | 10% |
| ⑤ | 周期不利 | 处于复苏期或过热期 | 10% |

**加权得分 ≥ 50% → 减仓至 50%；≥ 70% → 清仓。**

### 为什么黄金不同

- 黄金不产生现金流，没有"盈利目标"一说
- 黄金的均值回复性强于股票——暴涨后回调概率极高
- 实际利率是黄金的"万有引力"——利率升、黄金跌
- 黄金 RSI 超买阈值设为 80（高于基金策略的 70），因为黄金在趋势中天然偏高

### 适用标的

518880（黄金ETF）、159934（黄金ETF）、160719（嘉实黄金 QDII）等。
""",
        "rules": "RSI>80+涨>12%【35%】| MA死叉【25%】| 实际利率升【20%】| 美元走强【10%】| 周期不利【10%】| 加权≥50%减至50%，≥70%清仓",
        "frequency": "每周检查",
        "risk_level": "中",
    },
]


# ── 辅助函数 ────────────────────────────────────────────

def _redemption_fee(days_held: int | None) -> float:
    """根据持有天数估算赎回费率 (%)"""
    if days_held is None:
        return 0.5  # 默认保守估计
    if days_held < 7:
        return 1.5
    elif days_held < 30:
        return 0.5
    elif days_held < 180:
        return 0.1
    elif days_held < 365:
        return 0.05
    return 0.0


def _next_fee_breakpoint(days_held: int | None) -> int | None:
    """距下一费率断点的天数，None 表示无需等待"""
    if days_held is None:
        return None
    breakpoints = [7, 30, 180, 365]
    for bp in breakpoints:
        if days_held < bp:
            return bp - days_held
    return None  # 已超过 365 天，免费


def _compute_pnl(fund_data: dict, entry_price: float | None) -> float | None:
    """计算当前盈亏百分比"""
    # 如果手动提供了收益率，直接使用（优先级高于 entry_price 计算）
    manual_rate = fund_data.get("_manual_return_rate")
    if manual_rate is not None:
        return round(float(manual_rate), 2)
    if entry_price is None or entry_price <= 0:
        return None
    latest = fund_data.get("latest_nav")
    if latest is None or latest <= 0:
        return None
    return round((latest - entry_price) / entry_price * 100, 2)


def _compute_days_held(entry_date: str | None, fund_data: dict | None = None) -> int | None:
    """计算持有天数（基于数据最新日期，而非系统时间）"""
    if not entry_date:
        return None
    try:
        entry = datetime.strptime(entry_date, "%Y-%m-%d")
        # 优先用数据最新日期，确保 days_held 与 latest_nav 对应
        ref_date_str = (fund_data or {}).get("latest_nav_date")
        if ref_date_str:
            ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
        else:
            ref_date = datetime.now()
        return (ref_date - entry).days
    except (ValueError, TypeError):
        return None


def _highest_since_entry(fund_data: dict, entry_date: str | None) -> float | None:
    """找入场以来的最高净值"""
    closes = fund_data.get("closes", [])
    dates = fund_data.get("dates", [])
    if not closes or not entry_date:
        return None
    try:
        entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
        peak = None
        for i, d in enumerate(dates):
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                continue
            if dt >= entry_dt and i < len(closes):
                if peak is None or closes[i] > peak:
                    peak = closes[i]
        return round(peak, 4) if peak else None
    except (ValueError, TypeError):
        return None


# ── 双维度风险评估辅助函数 ──────────────────────────────

def _volatility_risk(fund_data: dict) -> dict:
    """
    维度 A：波动率突变检测
    比较 20 日波动率 vs 60 日波动率，判断是否出现波动率突变。

    Returns:
        ratio: 20日vol / 60日vol
        level: "calm" | "normal" | "elevated" | "extreme"
        signal: 波动率维度独立建议
        multiplier: 阈值调节系数 (<1=收紧, >1=放宽)
        label: 用于前端展示的简短描述
    """
    vol20 = fund_data.get("volatility_20d")
    vol60 = fund_data.get("volatility_60d")

    # 数据不足时退化为 normal
    if vol20 is None or vol60 is None or vol60 <= 0:
        return {
            "ratio": None, "level": "normal", "signal": "持有",
            "multiplier": 1.0, "label": "波动率数据不足",
            "confidence": 0.40,
        }

    ratio = round(vol20 / vol60, 2)

    if ratio > 2.5:
        return {
            "ratio": ratio, "level": "extreme", "signal": "清仓",
            "multiplier": 0.65,  # 收紧阈值 35%，更快离场
            "label": f"🔴 波动激增 · {ratio}x",
            "confidence": 0.85,
        }
    elif ratio > 1.5:
        return {
            "ratio": ratio, "level": "elevated", "signal": "减仓",
            "multiplier": 0.80,  # 收紧阈值 20%
            "label": f"⚠ 波动升高 · {ratio}x",
            "confidence": 0.70,
        }
    elif ratio < 0.7:
        return {
            "ratio": ratio, "level": "calm", "signal": "持有",
            "multiplier": 1.15,  # 放松阈值 15%，安心持有
            "label": f"波动放缓 · {ratio}x",
            "confidence": 0.55,
        }
    else:
        return {
            "ratio": ratio, "level": "normal", "signal": "持有",
            "multiplier": 1.0,
            "label": f"波动稳定 · {ratio}x",
            "confidence": 0.55,
        }


def _trend_risk(fund_data: dict) -> dict:
    """
    维度 B：近期净值涨跌趋势评估
    综合 5 日收益率、连续涨跌天数、MA 排列，判断短期趋势强度。

    Returns:
        trend_strength: "strong_up" | "weak_up" | "neutral" | "weak_down" | "strong_down"
        signal: 趋势维度独立建议
        mom_5d: 近5日收益率
        consecutive: 连续涨/跌天数 (正=涨, 负=跌)
        ma_align: MA排列描述
        label: 用于前端展示
    """
    mom_5d = fund_data.get("momentum_5d")
    consecutive = fund_data.get("consecutive_direction", 0)
    ma5 = fund_data.get("ma5")
    ma10 = fund_data.get("ma10")
    ma20 = fund_data.get("ma20")
    latest = fund_data.get("latest_nav")

    # MA 排列判断
    if ma5 and ma10 and ma20:
        if ma5 < ma10 < ma20:
            ma_align = "空头排列"
        elif ma5 > ma10 > ma20:
            ma_align = "多头排列"
        elif ma5 < ma10:
            ma_align = "MA5<MA10 偏弱"
        elif ma5 > ma10:
            ma_align = "MA5>MA10 偏强"
        else:
            ma_align = "均线缠绕"
    else:
        ma_align = "数据不足"

    # 数据不足
    if mom_5d is None:
        return {
            "trend_strength": "neutral", "signal": "持有",
            "mom_5d": None, "consecutive": 0, "ma_align": ma_align,
            "label": "趋势数据不足", "confidence": 0.40,
        }

    # ── 强下跌判断 ──
    is_strong_down = (
        mom_5d < -3.0
        or consecutive <= -5
        or ma_align == "空头排列"
    )
    is_extreme_down = (
        (mom_5d is not None and mom_5d < -5.0)
        or consecutive <= -8
    )

    if is_extreme_down:
        return {
            "trend_strength": "strong_down", "signal": "清仓",
            "mom_5d": mom_5d, "consecutive": consecutive, "ma_align": ma_align,
            "label": f"↘ {mom_5d:+.1f}% · 连跌{abs(consecutive)}天" if consecutive < 0
                     else f"↘ {mom_5d:+.1f}% · {ma_align}",
            "confidence": 0.82,
        }
    elif is_strong_down:
        return {
            "trend_strength": "strong_down", "signal": "减仓",
            "mom_5d": mom_5d, "consecutive": consecutive, "ma_align": ma_align,
            "label": f"↘ {mom_5d:+.1f}% · {ma_align}",
            "confidence": 0.72,
        }
    elif mom_5d < -1.0:
        return {
            "trend_strength": "weak_down", "signal": "持有",
            "mom_5d": mom_5d, "consecutive": consecutive, "ma_align": ma_align,
            "label": f"↘ {mom_5d:+.1f}% · 偏弱",
            "confidence": 0.50,
        }
    elif mom_5d > 3.0:
        return {
            "trend_strength": "strong_up", "signal": "持有",
            "mom_5d": mom_5d, "consecutive": consecutive, "ma_align": ma_align,
            "label": f"↗ {mom_5d:+.1f}% · {ma_align}",
            "confidence": 0.60,
        }
    elif mom_5d > 1.0:
        return {
            "trend_strength": "weak_up", "signal": "持有",
            "mom_5d": mom_5d, "consecutive": consecutive, "ma_align": ma_align,
            "label": f"↗ {mom_5d:+.1f}% · 偏强",
            "confidence": 0.52,
        }
    else:
        return {
            "trend_strength": "neutral", "signal": "持有",
            "mom_5d": mom_5d, "consecutive": consecutive, "ma_align": ma_align,
            "label": f"→ {mom_5d:+.1f}% · 横盘",
            "confidence": 0.48,
        }


# ── 各策略信号函数 ──────────────────────────────────────

def _signal_fixed_tp(fund_data: dict, entry_price: float | None,
                     entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)
    next_bp = _next_fee_breakpoint(days)

    # ── 双维度风险评估 ──
    vol_risk = _volatility_risk(fund_data)
    trend_risk = _trend_risk(fund_data)

    conditions = []
    actions = []
    signal = "持有"
    confidence = 0.60
    reasoning_parts = []

    if pnl is None:
        # 即使无入场参数，也输出波动率和趋势信息
        conditions.append(ExitConditionDetail(
            name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
            current=vol_risk["label"], threshold="稳定",
        ))
        conditions.append(ExitConditionDetail(
            name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
            current=trend_risk["label"], threshold="横盘或向上",
        ))
        return ExitStrategySignal(
            strategy_id="fixed-tp", strategy_name="固定止盈",
            signal="观望", confidence=0.40,
            reasoning="未提供入场净值，无法计算盈亏。请填写入场价以获取止盈信号。",
            pnl_pct=None, days_held=days,
            redemption_fee=fee, next_fee_breakpoint=next_bp,
            conditions=conditions, actions=[],
        )

    vol_mult = vol_risk["multiplier"]

    # 三档止盈（阈值经波动率调节）
    base_tiers = [
        (8.0, "盈利≥8%", 0.70, "减仓至70%（锁定本金）"),
        (15.0, "盈利≥15%", 0.50, "减仓至50%（利润留存一半）"),
        (25.0, "盈利≥25%", 0.00, "清仓（全部落袋为安）"),
    ]

    triggered_tier = None
    for target, name, ratio, action_desc in base_tiers:
        adj_target = round(target * vol_mult, 1)
        threshold_label = f"≥{adj_target:.0f}%" if vol_mult == 1.0 else f"≥{adj_target:.0f}%（原{target:.0f}%×{vol_mult:.2f}）"
        met = pnl >= adj_target
        conditions.append(ExitConditionDetail(
            name=name, met=met,
            current=f"{pnl:+.1f}%",
            threshold=threshold_label,
        ))
        if met:
            triggered_tier = (ratio, action_desc, target, adj_target)

    # ── 波动率极端 + 趋势弱势 → 额外条件 ──
    conditions.append(ExitConditionDetail(
        name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
        current=vol_risk["label"], threshold="稳定",
    ))
    conditions.append(ExitConditionDetail(
        name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
        current=trend_risk["label"], threshold="横盘或向上",
    ))

    if triggered_tier:
        ratio, action_desc, target, adj_target = triggered_tier
        # 赎回费优化
        if fee > 1.0 and next_bp and next_bp <= 10:
            reasoning_parts.append(
                f"已触发 +{adj_target:.0f}% 止盈（当前 {pnl:+.1f}%），"
                f"但当前赎回费 {fee}% 较高，距下一档费率断点仅 {next_bp} 天，建议等断点过后操作"
            )
            actions = [ExitAction(
                name=f"准备{action_desc}（等待{next_bp}天后费率降至{_redemption_fee(days+next_bp)}%）",
                ratio=1.0, reason=f"等待赎回费断点"
            )]
            signal = "减仓" if ratio > 0 else "清仓"
            confidence = 0.70
        else:
            actions = [ExitAction(name=action_desc, ratio=ratio,
                                  reason=f"当前盈利 {pnl:+.1f}%，触发 +{adj_target:.0f}% 止盈档")]
            signal = "清仓" if ratio == 0 else "减仓"
            confidence = 0.85

        reasoning_parts.append(f"当前盈利 {pnl:+.1f}%，触发固定止盈 +{adj_target:.0f}% 档")
    elif vol_risk["signal"] == "清仓":
        # 波动激增但未达止盈阈值 → 强制减仓
        signal, confidence = "减仓", 0.72
        actions = [ExitAction(name="减仓至70%", ratio=0.70,
                              reason=f"波动率激增({vol_risk['ratio']}x)，利润可能快速蒸发，建议提前降仓")]
        reasoning_parts.append(f"当前盈利 {pnl:+.1f}%，未触发止盈，但波动率激增({vol_risk['ratio']}x)建议提前降仓")
    elif vol_risk["signal"] == "减仓" and trend_risk["trend_strength"] == "strong_down":
        # 波动升高 + 趋势转弱 → 提前止盈
        signal, confidence = "减仓", 0.70
        actions = [ExitAction(name="减仓至70%", ratio=0.70,
                              reason=f"波动升高且趋势转弱，建议提前锁定利润")]
        reasoning_parts.append(f"当前盈利 {pnl:+.1f}%，波动升高+趋势转弱，建议提前止盈")
    elif trend_risk["trend_strength"] == "strong_down" and pnl > 5:
        # 盈利可观但趋势已转弱 → 加快止盈
        signal, confidence = "减仓", 0.68
        actions = [ExitAction(name="减仓至70%", ratio=0.70,
                              reason=f"趋势已转弱({trend_risk['label']})，建议提前锁定利润")]
        reasoning_parts.append(f"当前盈利 {pnl:+.1f}%，趋势转弱，建议提前减仓锁定利润")
    else:
        # 找最近的目标
        next_target = 8.0
        for t, _, _, _ in base_tiers:
            if pnl < t * vol_mult:
                next_target = t * vol_mult
                break
        gap = next_target - pnl
        reasoning_parts.append(f"当前盈利 {pnl:+.1f}%，距下一止盈档 +{next_target:.0f}% 还差 {gap:.1f}%")
        actions = [ExitAction(name="继续持有", ratio=1.0, reason="未触发止盈目标")]
        confidence = 0.55

    if fee > 0:
        reasoning_parts.append(f"当前赎回费 {fee}%")
    reasoning_parts.append(f"波动率: {vol_risk['label']} | 近5日趋势: {trend_risk['label']}")

    return ExitStrategySignal(
        strategy_id="fixed-tp", strategy_name="固定止盈",
        signal=signal, confidence=confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=next_bp,
        conditions=conditions, actions=actions,
    )


def _signal_trailing_stop(fund_data: dict, entry_price: float | None,
                          entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)
    latest = fund_data.get("latest_nav")
    closes = fund_data.get("closes", [])

    # ── 双维度风险评估 ──
    vol_risk = _volatility_risk(fund_data)
    trend_risk = _trend_risk(fund_data)
    vol_mult = vol_risk["multiplier"]

    conditions = []
    actions = []
    signal = "持有"
    confidence = 0.55

    # 追踪激活线经波动率调节
    tracking_threshold = round(10.0 * vol_mult, 1)
    tracking_active = pnl is not None and pnl >= tracking_threshold

    # 找最高点
    if entry_price and entry_date:
        peak = _highest_since_entry(fund_data, entry_date) or latest
    else:
        peak = max(closes[-60:]) if len(closes) >= 60 else latest

    if latest and peak and peak > 0:
        drawdown = round((peak - latest) / peak * 100, 2)
    else:
        drawdown = None

    # 回撤阈值经波动率调节
    dd5_threshold = round(5.0 * vol_mult, 1)
    dd8_threshold = round(8.0 * vol_mult, 1)

    if pnl is None:
        # 无入场参数：用 60 日高点评估
        if drawdown is not None:
            if drawdown >= dd8_threshold:
                signal, confidence = "减仓", 0.65
                actions = [ExitAction(name="减仓至50%", ratio=0.50,
                                      reason=f"60日高点回撤 {drawdown:.1f}%，超过{dd8_threshold:.0f}%阈值")]
            elif drawdown >= dd5_threshold:
                signal, confidence = "减仓", 0.60
                actions = [ExitAction(name="减仓至70%", ratio=0.70,
                                      reason=f"60日高点回撤 {drawdown:.1f}%，超过{dd5_threshold:.0f}%阈值")]
            else:
                actions = [ExitAction(name="继续持有", ratio=1.0,
                                      reason=f"60日高点回撤 {drawdown:.1f}%，未触发")]
        return ExitStrategySignal(
            strategy_id="trailing-stop", strategy_name="移动止盈",
            signal=signal, confidence=confidence,
            reasoning=f"无入场参数，基于60日高点 {peak} 评估，当前回撤 {drawdown}% | 波动率: {vol_risk['label']} | 趋势: {trend_risk['label']}",
            pnl_pct=None, days_held=days,
            redemption_fee=fee, next_fee_breakpoint=None,
            conditions=[
                ExitConditionDetail(name="追踪激活(盈利≥10%)", met=False,
                                     current="未知", threshold=f"≥{tracking_threshold:.0f}%"),
                ExitConditionDetail(name=f"回撤≥{dd5_threshold:.0f}%", met=drawdown is not None and drawdown >= dd5_threshold,
                                     current=f"{drawdown}%" if drawdown else "--", threshold=f"≥{dd5_threshold:.0f}%"),
                ExitConditionDetail(name=f"回撤≥{dd8_threshold:.0f}%", met=drawdown is not None and drawdown >= dd8_threshold,
                                     current=f"{drawdown}%" if drawdown else "--", threshold=f"≥{dd8_threshold:.0f}%"),
                ExitConditionDetail(name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
                                     current=vol_risk["label"], threshold="稳定"),
                ExitConditionDetail(name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
                                     current=trend_risk["label"], threshold="横盘或向上"),
            ], actions=actions,
        )

    # 有入场参数
    conditions = [
        ExitConditionDetail(name=f"追踪激活(盈利≥{tracking_threshold:.0f}%)", met=tracking_active,
                             current=f"{pnl:+.1f}%", threshold=f"≥{tracking_threshold:.0f}%"),
        ExitConditionDetail(name=f"回撤≥{dd5_threshold:.0f}%", met=drawdown is not None and drawdown >= dd5_threshold,
                             current=f"{drawdown}%" if drawdown else "--", threshold=f"≥{dd5_threshold:.0f}%"),
        ExitConditionDetail(name=f"回撤≥{dd8_threshold:.0f}%", met=drawdown is not None and drawdown >= dd8_threshold,
                             current=f"{drawdown}%" if drawdown else "--", threshold=f"≥{dd8_threshold:.0f}%"),
        ExitConditionDetail(name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
                             current=vol_risk["label"], threshold="稳定"),
        ExitConditionDetail(name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
                             current=trend_risk["label"], threshold="横盘或向上"),
    ]

    reasoning_parts = [f"入场净值 {entry_price}，当前 {latest}，盈利 {pnl:+.1f}%"]

    if tracking_active and drawdown is not None:
        reasoning_parts.append(f"追踪已激活，持仓最高 {peak}，回撤 {drawdown}%")
        if drawdown >= dd8_threshold:
            signal, confidence = "清仓", 0.85
            actions = [ExitAction(name="清仓", ratio=0.0,
                                  reason=f"回撤 {drawdown:.1f}% ≥ {dd8_threshold:.0f}%，移动止盈触发清仓")]
        elif drawdown >= dd5_threshold:
            signal, confidence = "减仓", 0.78
            actions = [ExitAction(name="减仓至50%", ratio=0.50,
                                  reason=f"回撤 {drawdown:.1f}% ≥ {dd5_threshold:.0f}%，移动止盈触发减仓")]
        else:
            actions = [ExitAction(name="继续持有", ratio=1.0,
                                  reason=f"追踪中，回撤 {drawdown:.1f}% 未触发")]
    elif not tracking_active:
        gap = tracking_threshold - (pnl or 0)
        reasoning_parts.append(f"追踪尚未激活（需盈利≥{tracking_threshold:.0f}%，尚差 {gap:.1f}%）")
        actions = [ExitAction(name="继续持有，等待追踪激活", ratio=1.0,
                              reason=f"盈利 {pnl:+.1f}%，未达到追踪激活线 {tracking_threshold:.0f}%")]

    # 趋势强下跌 → 即使未触发回撤也提示风险
    if trend_risk["trend_strength"] == "strong_down" and signal == "持有":
        reasoning_parts.append(f"⚠ 近期趋势转弱({trend_risk['label']})，需密切关注")
        confidence = max(confidence, 0.62)

    reasoning_parts.append(f"波动率: {vol_risk['label']} | 近5日趋势: {trend_risk['label']}")

    return ExitStrategySignal(
        strategy_id="trailing-stop", strategy_name="移动止盈",
        signal=signal, confidence=confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
        conditions=conditions, actions=actions,
    )


def _signal_time_exit(fund_data: dict, entry_price: float | None,
                      entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)
    next_bp = _next_fee_breakpoint(days)

    # ── 双维度风险评估 ──
    vol_risk = _volatility_risk(fund_data)
    trend_risk = _trend_risk(fund_data)

    conditions = []
    actions = []
    signal = "持有"
    confidence = 0.60

    if days is None:
        return ExitStrategySignal(
            strategy_id="time-exit", strategy_name="时间止盈",
            signal="观望", confidence=0.40,
            reasoning="未提供入场日期，无法计算持有天数和赎回费。请填写入场日期。",
            pnl_pct=pnl, days_held=None,
            redemption_fee=None, next_fee_breakpoint=None,
            conditions=[], actions=[],
        )

    # 构建费率阶段条件
    fee_stages = [
        (7, 1.5, "持有<7天"),
        (30, 0.5, "持有7-30天"),
        (180, 0.1, "持有30-180天"),
        (365, 0.05, "持有180-365天"),
        (float("inf"), 0.0, "持有>365天"),
    ]

    current_stage = ""
    for bp_days, bp_fee, stage_name in fee_stages:
        if days < bp_days:
            current_stage = stage_name
            break

    reasoning_parts = [f"已持有 {days} 天，{current_stage}（费率 {fee}%）"]

    if days < 7:
        # 极端波动时可考虑承担赎回费离场
        if vol_risk["level"] == "extreme" and trend_risk["trend_strength"] == "strong_down":
            signal = "减仓"
            confidence = 0.72
            reasoning_parts.append("⚠️ 波动激增+趋势转弱，虽持有不足7天（费率1.5%），但极端行情下可考虑承担赎回费离场")
            actions = [ExitAction(name="建议评估是否离场", ratio=1.0,
                                  reason=f"极端波动+弱趋势，考虑承担{fee}%赎回费")]
        else:
            signal = "持有"
            confidence = 0.90
            reasoning_parts.append("⚠️ 持有不足7天，赎回费高达1.5%，强烈建议等待")
            actions = [ExitAction(name="不建议赎回", ratio=1.0,
                                  reason=f"惩罚赎回费 {fee}%，再等 {7-days} 天费率降至 0.5%")]
        conditions.append(ExitConditionDetail(
            name="持有<7天(费率1.5%)", met=True,
            current=f"{days}天", threshold="<7天",
        ))
    elif days < 30:
        if pnl is not None and pnl > 5:
            signal = "减仓"
            confidence = 0.68
            actions = [ExitAction(name="减仓至50%", ratio=0.50,
                                  reason=f"盈利 {pnl:+.1f}% > 5%，虽费率 {fee}% 但利润覆盖")]
        else:
            actions = [ExitAction(name="继续持有", ratio=1.0,
                                  reason=f"费率 {fee}%，距30天断点还有 {30-days} 天")]
        conditions.append(ExitConditionDetail(
            name="持有7-30天(费率0.5%)", met=True,
            current=f"{days}天", threshold="7-30天",
        ))
    elif days < 180:
        signal = "持有" if pnl is None or pnl >= 0 else "减仓"
        confidence = 0.55
        actions = [ExitAction(name="可正常评估离场", ratio=1.0,
                              reason=f"费率仅 {fee}%，摩擦成本低")]
        conditions.append(ExitConditionDetail(
            name="持有30-180天(费率0.1%)", met=True,
            current=f"{days}天", threshold="30-180天",
        ))
    elif days < 365:
        confidence = 0.55
        actions = [ExitAction(name="低成本灵活操作", ratio=1.0,
                              reason=f"费率仅 {fee}%")]
        conditions.append(ExitConditionDetail(
            name="持有180-365天(费率0.05%)", met=True,
            current=f"{days}天", threshold="180-365天",
        ))
    else:
        confidence = 0.50
        actions = [ExitAction(name="免费赎回，只看信号", ratio=1.0,
                              reason="持有超1年，赎回免费")]
        conditions.append(ExitConditionDetail(
            name="持有>365天(免费)", met=True,
            current=f"{days}天", threshold=">365天",
        ))

    # 趋势+波动维度条件
    conditions.append(ExitConditionDetail(
        name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
        current=vol_risk["label"], threshold="稳定",
    ))
    conditions.append(ExitConditionDetail(
        name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
        current=trend_risk["label"], threshold="横盘或向上",
    ))

    # 趋势强下跌+有盈利 → 建议了结
    if trend_risk["trend_strength"] == "strong_down" and pnl is not None and pnl > 0 and signal == "持有":
        reasoning_parts.append("趋势已转弱且当前盈利，建议考虑提前了结")
        confidence = max(confidence, 0.65)

    if next_bp:
        reasoning_parts.append(f"距下一费率断点还有 {next_bp} 天")
    reasoning_parts.append(f"波动率: {vol_risk['label']} | 近5日趋势: {trend_risk['label']}")

    return ExitStrategySignal(
        strategy_id="time-exit", strategy_name="时间止盈",
        signal=signal, confidence=confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=next_bp,
        conditions=conditions, actions=actions,
    )


def _signal_technical_exit(fund_data: dict, entry_price: float | None,
                           entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    ma_status = fund_data.get("ma_status", "未知")
    rsi = fund_data.get("rsi_14")
    macd = fund_data.get("macd", {}) or {}
    mom = fund_data.get("momentum_1m")
    latest = fund_data.get("latest_nav")
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)

    # ── 双维度风险评估 ──
    vol_risk = _volatility_risk(fund_data)
    trend_risk = _trend_risk(fund_data)

    # 四个条件
    cond_ma = "死叉" in ma_status or ma_status == "空头排列"
    cond_rsi = rsi is not None and rsi >= 70
    cond_macd = (macd.get("hist") or 0) < 0  # MACD 柱为负 = 死叉
    cond_mom = mom is not None and mom < -3.0

    conditions = [
        ExitConditionDetail(name="MA死叉/空头排列", met=cond_ma,
                             current=ma_status, threshold="死叉或空头"),
        ExitConditionDetail(name="RSI≥70(超买)", met=cond_rsi,
                             current=f"{rsi}" if rsi else "--", threshold="≥70"),
        ExitConditionDetail(name="MACD死叉", met=cond_macd,
                             current=f"柱={macd.get('hist')}" if macd.get('hist') else "--",
                             threshold="柱<0"),
        ExitConditionDetail(name="1月动量<-3%", met=cond_mom,
                             current=f"{mom:+.1f}%" if mom else "--", threshold="<-3%"),
    ]

    raw_count = sum(1 for c in conditions if c.met)

    # 波动率激增 → 技术信号 +1（不确定性升高，更应重视技术面警告）
    vol_boost = 1 if vol_risk["ratio"] is not None and vol_risk["ratio"] > 2.0 else 0
    # 趋势强烈下行 → 技术信号 +1
    trend_boost = 1 if trend_risk["trend_strength"] == "strong_down" else 0

    effective_count = min(raw_count + vol_boost + trend_boost, 4)

    # 双维度条件行
    conditions.append(ExitConditionDetail(
        name="波动率状态", met=vol_boost > 0,
        current=vol_risk["label"], threshold="稳定",
    ))
    conditions.append(ExitConditionDetail(
        name="近期趋势", met=trend_boost > 0,
        current=trend_risk["label"], threshold="横盘或向上",
    ))

    if effective_count >= 4:
        signal, confidence = "清仓", 0.82
        actions = [ExitAction(name="清仓", ratio=0.0, reason=f"{effective_count}/{len(conditions)} 指标看空（含波动/趋势加成），全面转空")]
    elif effective_count >= 3:
        signal, confidence = "减仓", 0.75
        actions = [ExitAction(name="减仓至50%", ratio=0.50, reason=f"{effective_count}/{len(conditions)} 指标共振看空")]
    elif effective_count >= 2:
        signal, confidence = "减仓", 0.62
        actions = [ExitAction(name="减仓至70%", ratio=0.70, reason=f"{effective_count}/{len(conditions)} 指标提示注意风险")]
    else:
        signal, confidence = "持有", 0.55
        actions = [ExitAction(name="继续持有", ratio=1.0, reason=f"仅 {effective_count}/{len(conditions)} 指标触发")]

    reasoning_parts = [f"技术指标: {raw_count}/4 触发（MA:{'死叉' if cond_ma else 'OK'} "
                       f"RSI:{rsi} MACD:{'空' if cond_macd else '多'} 动量:{mom}%）"]
    if vol_boost or trend_boost:
        reasoning_parts.append(f"加成: 波动{'+1' if vol_boost else '+0'} 趋势{'+1' if trend_boost else '+0'} → 有效 {effective_count}/4")

    if pnl is not None:
        reasoning_parts.append(f"当前盈亏 {pnl:+.1f}%")
    reasoning_parts.append(f"波动率: {vol_risk['label']} | 近5日趋势: {trend_risk['label']}")

    return ExitStrategySignal(
        strategy_id="technical-exit", strategy_name="技术指标离场",
        signal=signal, confidence=confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
        conditions=conditions, actions=actions,
    )


def _signal_atr_stop(fund_data: dict, entry_price: float | None,
                     entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    atr = fund_data.get("atr_14")
    latest = fund_data.get("latest_nav")
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)

    # ── 双维度风险评估 ──
    vol_risk = _volatility_risk(fund_data)
    trend_risk = _trend_risk(fund_data)

    # ATR 倍数动态调整：高波时收紧（更快离场），低波时放宽
    vol_ratio = vol_risk["ratio"] if vol_risk["ratio"] is not None else 1.0
    atr_mult = round(1.5 + vol_ratio, 2)
    atr_mult = max(1.5, min(3.5, atr_mult))  # 限制范围

    conditions = []
    actions = []
    signal = "持有"
    confidence = 0.55

    if atr is None or latest is None:
        return ExitStrategySignal(
            strategy_id="atr-stop", strategy_name="ATR波动止损",
            signal="观望", confidence=0.35,
            reasoning="数据不足，无法计算 ATR",
            pnl_pct=pnl, days_held=days, redemption_fee=fee,
            conditions=[], actions=[],
        )

    if entry_price is None:
        # 无入场参数：给出参考止损位
        stop_price = round(latest - atr_mult * atr, 4)
        near_stop = round(latest - (atr_mult * 0.6) * atr, 4)
        conditions = [
            ExitConditionDetail(name="ATR(14)", met=True,
                                 current=f"{atr}", threshold="--"),
            ExitConditionDetail(name=f"建议止损位({atr_mult}×ATR)", met=False,
                                 current=f"{stop_price}", threshold=f"入场价−{atr_mult}×{atr}"),
            ExitConditionDetail(name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
                                 current=vol_risk["label"], threshold="稳定"),
            ExitConditionDetail(name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
                                 current=trend_risk["label"], threshold="横盘或向上"),
        ]
        return ExitStrategySignal(
            strategy_id="atr-stop", strategy_name="ATR波动止损",
            signal="持有", confidence=0.50,
            reasoning=f"无入场参数。当前净值 {latest}，ATR(14)={atr}，参考止损位 {stop_price}（-{round(atr_mult*atr/latest*100,1)}%）| 波动率: {vol_risk['label']} | 趋势: {trend_risk['label']}",
            pnl_pct=None, days_held=days, redemption_fee=fee,
            conditions=conditions, actions=[
                ExitAction(name="持有", ratio=1.0,
                           reason=f"设止损于 {stop_price}（入场价−{atr_mult}×ATR）")
            ],
        )

    # 趋势强下跌 → 止损位抬高（更保守）
    trend_adj = 0.85 if trend_risk["trend_strength"] == "strong_down" else 1.0
    effective_mult = round(atr_mult * trend_adj, 2)

    stop_price = round(entry_price - effective_mult * atr, 4)
    near_price = round(entry_price - effective_mult * 0.6 * atr, 4)
    breached = latest <= stop_price
    near = not breached and latest <= near_price

    mult_label = f"{effective_mult}×ATR" if effective_mult == atr_mult else f"{effective_mult}×ATR（{atr_mult}×{trend_adj:.0%}趋势调节）"

    conditions = [
        ExitConditionDetail(name=f"ATR(14)={atr}", met=True,
                             current=f"{atr}", threshold="--"),
        ExitConditionDetail(name=f"止损位 {stop_price}（入场−{mult_label}）", met=breached,
                             current=f"净值 {latest}", threshold=f"≤{stop_price}"),
        ExitConditionDetail(name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
                             current=vol_risk["label"], threshold="稳定"),
        ExitConditionDetail(name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
                             current=trend_risk["label"], threshold="横盘或向上"),
    ]

    reasoning_parts = [f"入场 {entry_price}，当前 {latest}，ATR(14)={atr}，倍数={effective_mult}"]
    reasoning_parts.append(f"止损位 {stop_price}（入场−{round(effective_mult*atr,2)}）")

    if breached:
        signal, confidence = "清仓", 0.85
        actions = [ExitAction(name="清仓", ratio=0.0,
                              reason=f"净值 {latest} 跌破止损位 {stop_price}")]
        reasoning_parts.append("⚠️ 已触发止损！")
    elif near:
        signal, confidence = "减仓", 0.72
        actions = [ExitAction(name="减仓至50%", ratio=0.50,
                              reason=f"净值 {latest} 接近止损位 {stop_price}")]
        reasoning_parts.append(f"接近止损位（距止损 {round(latest-stop_price,4)}）")
    else:
        distance = round(latest - stop_price, 4)
        reasoning_parts.append(f"距止损位还有 {distance}（{round(distance/atr,1)}×ATR）")
        actions = [ExitAction(name="继续持有", ratio=1.0,
                              reason=f"距止损 {round(distance/atr,1)}×ATR")]

    if pnl is not None:
        reasoning_parts.append(f"当前盈亏 {pnl:+.1f}%")
    reasoning_parts.append(f"波动率: {vol_risk['label']} | 近5日趋势: {trend_risk['label']}")

    return ExitStrategySignal(
        strategy_id="atr-stop", strategy_name="ATR波动止损",
        signal=signal, confidence=confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
        conditions=conditions, actions=actions,
    )


def _signal_scale_out(fund_data: dict, entry_price: float | None,
                      entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)
    latest = fund_data.get("latest_nav")
    closes = fund_data.get("closes", [])

    conditions = []
    actions = []
    signal = "持有"
    confidence = 0.55

    if pnl is None:
        return ExitStrategySignal(
            strategy_id="scale-out", strategy_name="分批止盈",
            signal="观望", confidence=0.40,
            reasoning="未提供入场净值，无法计算盈亏。分批止盈依赖精确的盈利计算。",
            pnl_pct=None, days_held=days, redemption_fee=fee,
            conditions=[], actions=[],
        )

    # ── 双维度风险评估 ──
    vol_risk = _volatility_risk(fund_data)
    trend_risk = _trend_risk(fund_data)
    vol_mult = vol_risk["multiplier"]

    # 三阶段（阈值经波动率调节）
    tier1_threshold = round(10.0 * vol_mult, 1)  # 第一阶段
    tier2_threshold = round(20.0 * vol_mult, 1)  # 第二阶段
    tier3_threshold = round(8.0 * vol_mult, 1)   # 第三阶段回撤
    tier1_met = pnl >= tier2_threshold  # 第二阶段
    tier2_met = pnl >= tier1_threshold  # 第一阶段

    # 找持仓期最高点
    peak = _highest_since_entry(fund_data, entry_date) or latest
    drawdown = round((peak - latest) / peak * 100, 2) if peak and latest and peak > 0 else 0

    conditions = [
        ExitConditionDetail(name=f"第一阶段 +{tier1_threshold:.0f}%（减至70%）", met=tier2_met,
                             current=f"{pnl:+.1f}%", threshold=f"≥{tier1_threshold:.0f}%"),
        ExitConditionDetail(name=f"第二阶段 +{tier2_threshold:.0f}%（减至30%）", met=tier1_met,
                             current=f"{pnl:+.1f}%", threshold=f"≥{tier2_threshold:.0f}%"),
        ExitConditionDetail(name=f"第三阶段 移动止盈（回撤{tier3_threshold:.0f}%清仓）",
                             met=tier1_met and drawdown >= tier3_threshold,
                             current=f"回撤{drawdown}%",
                             threshold=f"回撤≥{tier3_threshold:.0f}%"),
        ExitConditionDetail(name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
                             current=vol_risk["label"], threshold="稳定"),
        ExitConditionDetail(name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
                             current=trend_risk["label"], threshold="横盘或向上"),
    ]

    reasoning_parts = [f"入场 {entry_price}，当前 {latest}，盈利 {pnl:+.1f}%"]

    if tier1_met:
        # 第二阶段已触发 → 剩余 30% 启动移动止盈
        reasoning_parts.append(f"已触发第二阶段 +{tier2_threshold:.0f}%，剩余30%仓位追踪中（最高{peak}，回撤{drawdown}%）")
        if drawdown >= tier3_threshold:
            signal, confidence = "清仓", 0.88
            actions = [
                ExitAction(name="清仓（第三阶段触发）", ratio=0.0,
                           reason=f"剩余仓位回撤 {drawdown}% ≥ {tier3_threshold:.0f}%，移动止盈触发")
            ]
        else:
            signal, confidence = "减仓", 0.82
            actions = [
                ExitAction(name="维持30%仓位", ratio=0.30,
                           reason=f"前两阶段已完成减仓，剩余30%追踪中")
            ]
    elif tier2_met:
        reasoning_parts.append(f"已触发第一阶段 +{tier1_threshold:.0f}%，减仓至 70%")
        signal, confidence = "减仓", 0.78
        actions = [ExitAction(name="减仓至70%", ratio=0.70,
                              reason=f"盈利 {pnl:+.1f}% ≥ {tier1_threshold:.0f}%，第一阶段触发")]
    else:
        gap = tier1_threshold - pnl
        reasoning_parts.append(f"距第一阶段 +{tier1_threshold:.0f}% 还差 {gap:.1f}%")
        actions = [ExitAction(name="继续持有", ratio=1.0,
                              reason=f"盈利 {pnl:+.1f}%，未触发分批止盈")]

    # 趋势强下跌 + 已有一定盈利 → 提示提前止盈
    if trend_risk["trend_strength"] == "strong_down" and pnl > 3 and signal == "持有":
        reasoning_parts.append("⚠ 趋势已转弱，虽未到止盈线但建议关注")
        confidence = max(confidence, 0.65)

    reasoning_parts.append(f"波动率: {vol_risk['label']} | 近5日趋势: {trend_risk['label']}")

    return ExitStrategySignal(
        strategy_id="scale-out", strategy_name="分批止盈",
        signal=signal, confidence=confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
        conditions=conditions, actions=actions,
    )


def _signal_max_drawdown(fund_data: dict, entry_price: float | None,
                         entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    latest = fund_data.get("latest_nav")
    closes = fund_data.get("closes", [])
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)

    # ── 双维度风险评估 ──
    vol_risk = _volatility_risk(fund_data)
    trend_risk = _trend_risk(fund_data)
    vol_mult = vol_risk["multiplier"]

    conditions = []
    actions = []
    signal = "持有"
    confidence = 0.55

    # 确定最高点
    if entry_price and entry_date:
        peak = _highest_since_entry(fund_data, entry_date) or latest
        peak_source = "持仓期"
    else:
        # 无入场参数：用 60 日和 120 日最高点
        peak_60 = max(closes[-60:]) if len(closes) >= 60 else latest
        peak_120 = max(closes[-120:]) if len(closes) >= 120 else peak_60
        peak = max(peak_60, peak_120)
        peak_source = "60/120日"

    if latest and peak and peak > 0:
        drawdown = round((peak - latest) / peak * 100, 2)
    else:
        drawdown = None

    if drawdown is None:
        return ExitStrategySignal(
            strategy_id="max-drawdown", strategy_name="最大回撤离场",
            signal="观望", confidence=0.35,
            reasoning="数据不足，无法计算回撤",
            pnl_pct=pnl, days_held=days, redemption_fee=fee,
            conditions=[], actions=[],
        )

    # 回撤阈值经波动率调节
    dd10_threshold = round(10.0 * vol_mult, 1)
    dd15_threshold = round(15.0 * vol_mult, 1)

    cond_10 = drawdown >= dd10_threshold
    cond_15 = drawdown >= dd15_threshold

    conditions = [
        ExitConditionDetail(name=f"回撤≥{dd10_threshold:.0f}%", met=cond_10,
                             current=f"{drawdown}%", threshold=f"≥{dd10_threshold:.0f}%"),
        ExitConditionDetail(name=f"回撤≥{dd15_threshold:.0f}%", met=cond_15,
                             current=f"{drawdown}%", threshold=f"≥{dd15_threshold:.0f}%"),
        ExitConditionDetail(name="波动率状态", met=vol_risk["level"] in ("elevated", "extreme"),
                             current=vol_risk["label"], threshold="稳定"),
        ExitConditionDetail(name="近期趋势", met=trend_risk["trend_strength"] == "strong_down",
                             current=trend_risk["label"], threshold="横盘或向上"),
    ]

    reasoning_parts = [f"{peak_source}最高净值 {peak}，当前 {latest}，回撤 {drawdown}%"]

    if cond_15:
        signal, confidence = "清仓", 0.85
        actions = [ExitAction(name="清仓", ratio=0.0,
                              reason=f"回撤 {drawdown}% ≥ {dd15_threshold:.0f}%，触发清仓")]
    elif cond_10:
        signal, confidence = "减仓", 0.75
        actions = [ExitAction(name="减仓至50%", ratio=0.50,
                              reason=f"回撤 {drawdown}% ≥ {dd10_threshold:.0f}%，触发减仓")]
    else:
        actions = [ExitAction(name="继续持有", ratio=1.0,
                              reason=f"回撤 {drawdown}%，未触发离场")]

    # 趋势强下跌 + 回撤接近阈值 → 增强信号
    if trend_risk["trend_strength"] == "strong_down" and drawdown >= dd10_threshold * 0.7:
        if signal == "持有":
            signal, confidence = "减仓", 0.68
            actions = [ExitAction(name="减仓至70%", ratio=0.70,
                                  reason=f"回撤接近阈值且趋势转弱，建议提前降仓")]

    if pnl is not None:
        reasoning_parts.append(f"当前盈亏 {pnl:+.1f}%")
    reasoning_parts.append(f"波动率: {vol_risk['label']} | 近5日趋势: {trend_risk['label']}")

    return ExitStrategySignal(
        strategy_id="max-drawdown", strategy_name="最大回撤离场",
        signal=signal, confidence=confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
        conditions=conditions, actions=actions,
    )


def _signal_cycle_reversal(fund_data: dict, entry_price: float | None,
                           entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)
    fund_type = fund_data.get("fund_type", "etf")

    # 周期 → (股票型, 债券型, 黄金型) 信号映射
    cycle_map = {
        "复苏期": ("持有", "持有", "减仓"),
        "过热期": ("减仓", "减仓", "减仓"),
        "滞胀期": ("减仓", "持有", "持有"),
        "衰退期": ("清仓", "持有", "持有"),
    }

    # 简化基金类型判断
    if fund_type == "gold":
        asset_class = "黄金"
        idx = 2
    elif fund_type in ("bond", "money"):
        asset_class = "债券"
        idx = 1
    else:
        asset_class = "股票"
        idx = 0

    mapped = cycle_map.get(current_cycle, ("持有", "持有", "持有"))
    action_signal = mapped[idx]

    # 映射到比例
    ratio_map = {"持有": 1.0, "减仓": 0.30 if action_signal == "减仓" and idx == 0 and current_cycle == "滞胀期"
                             else 0.50, "清仓": 0.0}
    action_ratio = ratio_map.get(action_signal, 1.0)

    conditions = [
        ExitConditionDetail(name=f"当前周期: {current_cycle}", met=True,
                             current=current_cycle, threshold="周期映射"),
        ExitConditionDetail(name=f"{asset_class}型资产在{current_cycle}建议", met=action_signal != "持有",
                             current=f"{action_signal}（剩余{action_ratio*100:.0f}%）",
                             threshold="按周期表"),
    ]

    desc_map = {
        "复苏期": "经济回暖，股票为王；黄金吸引力下降",
        "过热期": "通胀上升，逐步减仓风险资产",
        "滞胀期": "增长放缓+通胀高企，股票最差环境",
        "衰退期": "经济偏冷，清仓股票转债券/黄金",
    }

    reasoning = f"当前{current_cycle}：{desc_map.get(current_cycle, '')}"
    reasoning += f" | {asset_class}型资产建议：{action_signal}"

    actions = []
    if action_signal == "清仓":
        actions = [ExitAction(name="清仓", ratio=0.0,
                              reason=f"{current_cycle}不适合持有{asset_class}型资产")]
    elif action_signal == "减仓":
        ratio_str = f"{action_ratio*100:.0f}%"
        actions = [ExitAction(name=f"减仓至{ratio_str}", ratio=action_ratio,
                              reason=f"{current_cycle}应降低{asset_class}型资产仓位")]

    if pnl is not None:
        reasoning += f" | 当前盈亏 {pnl:+.1f}%"

    return ExitStrategySignal(
        strategy_id="cycle-reversal", strategy_name="宏观周期反转离场",
        signal=action_signal, confidence=0.75,
        reasoning=reasoning,
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
        conditions=conditions, actions=actions,
    )


def _signal_xuxiaoming_exit(fund_data: dict, entry_price: float | None,
                             entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    """徐小明解读离场 — 从每日文章中提取结构化立场，映射为离场信号"""
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)

    # 从 fund_data 中读取注入的姿态数据
    stance = fund_data.get("_xuxiaoming_stance")

    if stance is None:
        return ExitStrategySignal(
            strategy_id="xuxiaoming-exit", strategy_name="徐小明解读离场",
            signal="观望", confidence=0.30,
            reasoning="暂无徐小明解读数据。请在「每日解读」页面点击刷新，系统将自动提取文章中的立场信号。",
            pnl_pct=pnl, days_held=days,
            redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
            conditions=[
                ExitConditionDetail(name="徐小明立场数据", met=False,
                                     current="无数据", threshold="需先刷新解读"),
            ], actions=[],
        )

    market_stance = stance.get("market_stance", "震荡")
    position = stance.get("position_recommendation", "半仓")
    key_reason = stance.get("key_reason", "")
    llm_confidence = stance.get("confidence", 0.5)
    stance_date = stance.get("date", "")
    articles_count = stance.get("articles_analyzed", 0)

    # ── 信号映射逻辑 ──
    signal = "持有"
    confidence = 0.60
    actions = []
    action_reason = ""

    if market_stance == "看空":
        if position in ("清仓", "轻仓"):
            signal = "清仓"
            confidence = 0.88 if position == "清仓" else 0.82
            action_reason = f"徐小明明确看空（{market_stance}）且建议{position}，强烈一致看空信号"
            actions = [ExitAction(name="清仓", ratio=0.0, reason=action_reason)]
        else:  # 重仓 or 半仓
            signal = "减仓"
            confidence = 0.78
            action_reason = f"徐小明看空（{market_stance}），建议大幅降低风险敞口"
            actions = [ExitAction(name="减仓至30%", ratio=0.30, reason=action_reason)]

    elif market_stance == "看多":
        signal = "持有"
        if position in ("满仓", "重仓"):
            confidence = 0.80
            action_reason = f"徐小明看多（{market_stance}）且建议{position}，坚定持有"
        else:
            confidence = 0.68
            action_reason = f"徐小明看多（{market_stance}），偏谨慎（建议{position}），保持持有观察"
        actions = [ExitAction(name="继续持有", ratio=1.0, reason=action_reason)]

    elif market_stance == "震荡":
        if position in ("清仓", "轻仓"):
            signal = "减仓"
            confidence = 0.65
            action_reason = f"徐小明判断震荡（{market_stance}）但偏保守（建议{position}），适度降仓防守"
            actions = [ExitAction(name="减仓至50%", ratio=0.50, reason=action_reason)]
        else:
            signal = "持有"
            confidence = 0.58
            action_reason = f"徐小明判断震荡（{market_stance}），建议维持现状观察"
            actions = [ExitAction(name="继续持有", ratio=1.0, reason=action_reason)]

    # 用 LLM 自评置信度微调最终置信度
    adjusted_confidence = round(confidence * (0.7 + 0.3 * llm_confidence), 2)

    # ── 构建条件明细 ──
    conditions = [
        ExitConditionDetail(
            name=f"市场立场: {market_stance}",
            met=market_stance == "看空",
            current=market_stance,
            threshold="看空触发离场",
        ),
        ExitConditionDetail(
            name=f"仓位建议: {position}",
            met=position in ("清仓", "轻仓"),
            current=position,
            threshold="清仓/轻仓强化信号",
        ),
        ExitConditionDetail(
            name=f"LLM 置信度: {llm_confidence:.0%}",
            met=llm_confidence >= 0.7,
            current=f"{llm_confidence:.0%}",
            threshold=">=70%",
        ),
    ]

    # ── 构建推理文本 ──
    reasoning_parts = [
        f"数据日期: {stance_date}（{articles_count}篇文章）" if stance_date else f"分析{articles_count}篇文章",
        f"徐小明立场: {market_stance}，仓位建议: {position}",
        f"LLM提取置信度: {llm_confidence:.0%}",
    ]
    if key_reason:
        reasoning_parts.append(f"核心观点: {key_reason}")
    reasoning_parts.append(action_reason)
    if pnl is not None:
        reasoning_parts.append(f"当前盈亏 {pnl:+.1f}%")

    return ExitStrategySignal(
        strategy_id="xuxiaoming-exit", strategy_name="徐小明解读离场",
        signal=signal, confidence=adjusted_confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
        conditions=conditions, actions=actions,
    )


def _signal_gold_exit(fund_data: dict, entry_price: float | None,
                      entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    """黄金专属离场策略 — 五大条件加权判定"""
    rsi = fund_data.get("rsi_14")
    mom = fund_data.get("momentum_1m")
    ma_status = fund_data.get("ma_status", "未知")
    latest = fund_data.get("latest_nav")
    pnl = _compute_pnl(fund_data, entry_price)
    days = _compute_days_held(entry_date, fund_data)
    fee = _redemption_fee(days)

    # 条件 ①: 短期超买 — RSI > 80 且 1月涨幅 > 12%  (权重 35%)
    cond_overbought_rsi = rsi is not None and rsi > 80
    cond_overbought_mom = mom is not None and mom > 12
    cond_overbought = cond_overbought_rsi and cond_overbought_mom

    # 条件 ②: 均线死叉 (权重 25%)
    cond_ma_death = "死叉" in ma_status or ma_status == "空头排列"

    # 条件 ③: 实际利率上升 — 名义利率上行（PPI 下行+利率升的简化代理）(权重 20%)
    bond_10y = fund_data.get("bond_10y")
    bond_10y_prev = fund_data.get("bond_10y_prev")
    if bond_10y is not None and bond_10y_prev is not None:
        cond_real_rate = bond_10y > bond_10y_prev
        real_rate_current = f"10Y国债 {bond_10y}% vs 前值 {bond_10y_prev}%"
        real_rate_threshold = "10Y收益率上行"
    else:
        # 无真实利率数据时回退到周期推断（保持原行为）
        cond_real_rate = current_cycle in ("过热期", "滞胀期")
        real_rate_current = f"{current_cycle}(周期推断)"
        real_rate_threshold = "过热期或滞胀期"

    # 条件 ④: 美元走强 — USD/CNY 月涨 > 1.5% (权重 10%)
    usd_chg = fund_data.get("usdcny_change_1m")
    if usd_chg is not None:
        cond_usd_strong = usd_chg > 1.5
        usd_current = f"USD/CNY 月涨{usd_chg:+.2f}%"
    else:
        cond_usd_strong = False
        usd_current = "待接入"

    # 条件 ⑤: 宏观周期不利 (权重 10%)
    cond_cycle_bad = current_cycle in ("复苏期", "过热期")

    conditions = [
        ExitConditionDetail(name="① 短期超买 (RSI>80 & 月涨>12%)",
                             met=cond_overbought, weight=35,
                             current=f"RSI={rsi}, 月涨={mom:+.1f}%" if rsi and mom else "--",
                             threshold="RSI>80 且 月涨>12%"),
        ExitConditionDetail(name="② 均线死叉",
                             met=cond_ma_death, weight=25,
                             current=ma_status, threshold="死叉或空头排列"),
        ExitConditionDetail(name="③ 实际利率上升",
                             met=cond_real_rate, weight=20,
                             current=real_rate_current, threshold=real_rate_threshold),
        ExitConditionDetail(name="④ 美元走强 (USD/CNY月涨>1.5%)",
                             met=cond_usd_strong, weight=10,
                             current=usd_current, threshold="USD/CNY月涨>1.5%"),
        ExitConditionDetail(name="⑤ 宏观周期不利",
                             met=cond_cycle_bad, weight=10,
                             current=current_cycle, threshold="复苏期或过热期"),
    ]

    # 加权计算
    total_weight = 0
    triggered_weight = 0
    for c in conditions:
        total_weight += c.weight
        if c.met:
            triggered_weight += c.weight

    weighted_score = round(triggered_weight / total_weight * 100, 1) if total_weight > 0 else 0

    signal = "持有"
    confidence = 0.55
    actions = []

    if weighted_score >= 70:
        signal, confidence = "清仓", 0.82
        actions = [ExitAction(name="清仓", ratio=0.0,
                              reason=f"黄金离场加权得分 {weighted_score}% ≥ 70%，建议清仓")]
    elif weighted_score >= 50:
        signal, confidence = "减仓", 0.72
        actions = [ExitAction(name="减仓至50%", ratio=0.50,
                              reason=f"黄金离场加权得分 {weighted_score}% ≥ 50%，建议减半仓")]
    else:
        actions = [ExitAction(name="继续持有", ratio=1.0,
                              reason=f"加权得分 {weighted_score}% < 50%，黄金可持有")]

    reasoning_parts = [f"黄金离场加权得分: {weighted_score}% (触发 {triggered_weight}/{total_weight} 权重)"]
    triggered_names = [c.name for c in conditions if c.met]
    if triggered_names:
        reasoning_parts.append(f"触发条件: {'; '.join(triggered_names)}")
    else:
        reasoning_parts.append("无离场条件触发")

    if pnl is not None:
        reasoning_parts.append(f"当前盈亏 {pnl:+.1f}%")
    reasoning_parts.append(f"当前净值 {latest}")

    return ExitStrategySignal(
        strategy_id="gold-exit", strategy_name="黄金离场策略",
        signal=signal, confidence=confidence,
        reasoning=" | ".join(reasoning_parts),
        pnl_pct=pnl, days_held=days,
        redemption_fee=fee, next_fee_breakpoint=_next_fee_breakpoint(days),
        conditions=conditions, actions=actions,
    )


# ── 信号派发 ────────────────────────────────────────────

_SIGNAL_FUNCS = {
    "fixed-tp": _signal_fixed_tp,
    "trailing-stop": _signal_trailing_stop,
    "time-exit": _signal_time_exit,
    "technical-exit": _signal_technical_exit,
    "atr-stop": _signal_atr_stop,
    "scale-out": _signal_scale_out,
    "max-drawdown": _signal_max_drawdown,
    "cycle-reversal": _signal_cycle_reversal,
    "xuxiaoming-exit": _signal_xuxiaoming_exit,
    "gold-exit": _signal_gold_exit,
}


def _make_signal(sid: str, fund_data: dict, entry_price: float | None,
                 entry_date: str | None, current_cycle: str) -> ExitStrategySignal:
    """派发到对应的信号函数"""
    func = _SIGNAL_FUNCS.get(sid)
    if func is None:
        return ExitStrategySignal(
            strategy_id=sid, strategy_name="未知策略",
            signal="观望", confidence=0.30,
            reasoning=f"策略 {sid} 未实现",
            actions=[],
        )
    return func(fund_data, entry_price, entry_date, current_cycle)


# ── 公开 API ────────────────────────────────────────────

def get_all_exit_strategies(fund_data: dict, entry_price: float = None,
                            entry_date: str = None,
                            current_cycle: str = "复苏期",
                            return_rate: float = None,
                            xuxiaoming_stance: dict = None) -> list[ExitStrategy]:
    """获取全部离场策略及信号"""
    # 将手动收益率注入 fund_data，_compute_pnl 中统一检查
    if return_rate is not None:
        fund_data["_manual_return_rate"] = return_rate
    # 将徐小明立场注入 fund_data（供 _signal_xuxiaoming_exit 读取）
    if xuxiaoming_stance is not None:
        fund_data["_xuxiaoming_stance"] = xuxiaoming_stance
    fund_type = fund_data.get("fund_type", "etf")

    # 黄金 ETF → 只显示黄金策略 + 通用策略
    # 普通基金 → 不显示黄金策略
    if fund_type == "gold":
        eligible = ["gold-exit", "trailing-stop", "time-exit", "technical-exit",
                    "atr-stop", "max-drawdown", "cycle-reversal", "xuxiaoming-exit"]
    else:
        eligible = ["fixed-tp", "trailing-stop", "time-exit", "technical-exit",
                    "atr-stop", "scale-out", "max-drawdown", "cycle-reversal",
                    "xuxiaoming-exit"]

    result = []
    for s in EXIT_STRATEGY_DEFS:
        if s["id"] not in eligible:
            continue
        sig = _make_signal(s["id"], fund_data, entry_price, entry_date, current_cycle)
        sig.strategy_name = s["name"]
        result.append(ExitStrategy(
            id=s["id"], name=s["name"], category=s["category"],
            tagline=s["tagline"], description=s["description"],
            rules=s["rules"], frequency=s["frequency"],
            risk_level=s["risk_level"], fund_type=s.get("fund_type", "domestic"),
            current_signal=sig,
        ))
    return result


def get_exit_strategy_by_id(strategy_id: str, fund_data: dict,
                            entry_price: float = None,
                            entry_date: str = None,
                            current_cycle: str = "复苏期",
                            return_rate: float = None,
                            xuxiaoming_stance: dict = None) -> ExitStrategy | None:
    """获取特定离场策略"""
    if return_rate is not None:
        fund_data["_manual_return_rate"] = return_rate
    if xuxiaoming_stance is not None:
        fund_data["_xuxiaoming_stance"] = xuxiaoming_stance
    for s in EXIT_STRATEGY_DEFS:
        if s["id"] == strategy_id:
            sig = _make_signal(s["id"], fund_data, entry_price, entry_date, current_cycle)
            sig.strategy_name = s["name"]
            return ExitStrategy(
                id=s["id"], name=s["name"], category=s["category"],
                tagline=s["tagline"], description=s["description"],
                rules=s["rules"], frequency=s["frequency"],
                risk_level=s["risk_level"], fund_type=s.get("fund_type", "domestic"),
                current_signal=sig,
            )
    return None


# ── 汇总决策 ────────────────────────────────────────────

# 类别权重：解读(徐小明)最高 > 止损 > 信号 > 止盈 > 混合
CATEGORY_WEIGHTS = {
    "解读": 1.5,
    "止损": 1.2,
    "信号": 1.0,
    "止盈": 0.9,
    "混合": 0.8,
    "黄金": 1.0,
}

# 信号强度量化
SIGNAL_SCORES = {
    "清仓": 3,
    "减仓": 2,
    "持有": 1,
    "观望": 0,
}


def synthesize_exit_decision(strategies: list[ExitStrategy], fund_data: dict = None) -> dict:
    """综合所有离场策略，给出汇总决策（含每策略贡献度+双维度风险）"""
    if not strategies:
        return {
            "recommendation": "数据不足",
            "confidence": 0,
            "consensus": "无法判断",
            "breakdown": {},
            "key_reasons": [],
            "suggested_action": None,
            "contributions": [],
            "vol_risk": None,
            "trend_risk": None,
        }

    # ── 双维度风险独立评估 ──
    vol_risk = _volatility_risk(fund_data) if fund_data else None
    trend_risk = _trend_risk(fund_data) if fund_data else None

    # 1. 计数分布 + 加权得分
    breakdown = {"清仓": 0, "减仓": 0, "持有": 0, "观望": 0}
    total_score = 0.0
    max_possible = 0.0
    scored = []  # (weighted_score, strategy_name, signal, reasoning)
    contrib_details = []  # 每策略贡献明细

    for s in strategies:
        sig = s.current_signal
        if sig is None:
            breakdown["观望"] = breakdown.get("观望", 0) + 1
            continue

        signal = sig.signal or "观望"
        breakdown[signal] = breakdown.get(signal, 0) + 1

        cat_weight = CATEGORY_WEIGHTS.get(s.category, 1.0)
        sig_score = SIGNAL_SCORES.get(signal, 0)
        conf = sig.confidence or 0.5

        weighted = sig_score * cat_weight * conf
        total_score += weighted
        max_possible += 3 * cat_weight * 1.0  # 理论最高分

        scored.append((weighted, s.name, signal, sig.reasoning or ""))

        # 记录贡献明细
        short_reason = (sig.reasoning or "").split("|")[0].strip()
        if len(short_reason) > 40:
            short_reason = short_reason[:40] + "…"
        contrib_details.append({
            "strategy_id": s.id,
            "strategy_name": s.name,
            "category": s.category,
            "signal": signal,
            "confidence": conf,
            "weighted_score": round(weighted, 3),
            "contribution_pct": 0.0,  # 先占位，后面统一算
            "reasoning_short": short_reason,
        })

    # ── 注入虚拟贡献项：波动率风险 ──
    vol_contrib = None
    if vol_risk and vol_risk["ratio"] is not None:
        vol_cat_weight = CATEGORY_WEIGHTS.get("止损", 1.2)
        vol_sig_score = SIGNAL_SCORES.get(vol_risk["signal"], 0)
        vol_conf = vol_risk["confidence"]
        vol_weighted = vol_sig_score * vol_cat_weight * vol_conf
        total_score += vol_weighted
        max_possible += 3 * vol_cat_weight * 1.0

        # 更新 breakdown
        breakdown[vol_risk["signal"]] = breakdown.get(vol_risk["signal"], 0) + 1

        vol_contrib = {
            "strategy_id": "_volatility_risk",
            "strategy_name": "波动率风险",
            "category": "止损",
            "signal": vol_risk["signal"],
            "confidence": round(vol_conf, 2),
            "weighted_score": round(vol_weighted, 3),
            "contribution_pct": 0.0,
            "reasoning_short": f"波动率 {vol_risk['ratio']}x · {vol_risk['level']}",
        }

    # ── 注入虚拟贡献项：近期趋势 ──
    trend_contrib = None
    if trend_risk and trend_risk["mom_5d"] is not None:
        trend_cat_weight = CATEGORY_WEIGHTS.get("信号", 1.0)
        trend_sig_score = SIGNAL_SCORES.get(trend_risk["signal"], 0)
        trend_conf = trend_risk["confidence"]
        trend_weighted = trend_sig_score * trend_cat_weight * trend_conf
        total_score += trend_weighted
        max_possible += 3 * trend_cat_weight * 1.0

        # 更新 breakdown
        breakdown[trend_risk["signal"]] = breakdown.get(trend_risk["signal"], 0) + 1

        trend_contrib = {
            "strategy_id": "_trend_risk",
            "strategy_name": "近期趋势",
            "category": "信号",
            "signal": trend_risk["signal"],
            "confidence": round(trend_conf, 2),
            "weighted_score": round(trend_weighted, 3),
            "contribution_pct": 0.0,
            "reasoning_short": f"近5日 {trend_risk['label']}",
        }

    # 2. 归一化到 0-100
    if max_possible > 0:
        normalized = round(total_score / max_possible * 100, 1)
    else:
        normalized = 0

    # 2b. 计算每策略贡献百分比
    if total_score > 0:
        for c in contrib_details:
            c["contribution_pct"] = round(c["weighted_score"] / total_score * 100, 1)
        if vol_contrib:
            vol_contrib["contribution_pct"] = round(vol_contrib["weighted_score"] / total_score * 100, 1)
        if trend_contrib:
            trend_contrib["contribution_pct"] = round(trend_contrib["weighted_score"] / total_score * 100, 1)
    # 按贡献度降序排列
    contrib_details.sort(key=lambda x: x["contribution_pct"], reverse=True)
    # 虚拟项也插入贡献列表（但排在实际策略之后，用特殊标记）
    all_contributions = list(contrib_details)
    if vol_contrib:
        all_contributions.append(vol_contrib)
    if trend_contrib:
        all_contributions.append(trend_contrib)

    # 3. 最终建议
    if normalized >= 55:
        recommendation = "建议清仓"
    elif normalized >= 28:
        recommendation = "建议减仓"
    else:
        recommendation = "建议继续持有"

    # 4. 共识度
    total_strategies = sum(breakdown.values())
    max_count = max(breakdown.values()) if breakdown else 0
    if max_count >= 5:
        consensus = "强共识"
    elif max_count >= 3:
        consensus = "多数共识"
    else:
        consensus = "存在分歧"

    # 5. 关键理由：得分最高的 3 个策略
    scored.sort(key=lambda x: x[0], reverse=True)
    key_reasons = []
    for _, name, signal, reasoning in scored[:3]:
        short = reasoning.split("|")[0].strip() if reasoning else ""
        if len(short) > 60:
            short = short[:60] + "…"
        key_reasons.append(f"【{name}】{signal} — {short}")

    # 6. 建议操作
    if recommendation == "建议清仓":
        suggested_action = {
            "action": "清仓",
            "ratio": 0.0,
            "detail": f"综合得分 {normalized}%，{breakdown.get('清仓', 0)}个策略建议清仓，建议全部离场"
        }
    elif recommendation == "建议减仓":
        suggested_action = {
            "action": "减仓至 50%",
            "ratio": 0.5,
            "detail": f"综合得分 {normalized}%，{breakdown.get('减仓', 0)}个策略建议减仓，建议先减半仓观察"
        }
    else:
        suggested_action = {
            "action": "继续持有",
            "ratio": 1.0,
            "detail": f"综合得分 {normalized}%，多数策略建议持有，暂无需操作"
        }

    return {
        "recommendation": recommendation,
        "confidence": normalized,
        "consensus": consensus,
        "breakdown": breakdown,
        "key_reasons": key_reasons,
        "suggested_action": suggested_action,
        "contributions": all_contributions,
        "total_strategies": total_strategies,
        "vol_risk": {
            "ratio": vol_risk["ratio"],
            "level": vol_risk["level"],
            "signal": vol_risk["signal"],
            "label": vol_risk["label"],
        } if vol_risk and vol_risk["ratio"] is not None else None,
        "trend_risk": {
            "trend_strength": trend_risk["trend_strength"],
            "signal": trend_risk["signal"],
            "mom_5d": trend_risk["mom_5d"],
            "consecutive": trend_risk["consecutive"],
            "ma_align": trend_risk["ma_align"],
            "label": trend_risk["label"],
        } if trend_risk and trend_risk["mom_5d"] is not None else None,
    }
