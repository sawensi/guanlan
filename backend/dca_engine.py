"""
观澜 — 定投 (DCA) 引擎

定投为主的使用定位下，这是观澜最核心的回测与决策模块。

提供：
1. valuation_to_multiplier   — 估值温度计 → 定投倍数（低估值加码/高估值减码）
2. dca_target_exit            — 定投止盈 / 再平衡建议（止盈导向，替代止损导向）
3. xirr                       — 资金加权年化收益率（多期现金流唯一正确的口径）
4. run_dca_backtest           — 定投模拟：固定定投 vs 估值加码定投 vs 一次性买入

关键口径：
- 场外基金：按当日净值（收盘）确认，T+1 到账不影响长期定投成本摊薄；申购/赎回费阶梯计入
- ETF/指数/黄金：按收盘价成交，计低交易成本 + 滑点
- 价格指数不含分红（红利/债券再投收益无法计入，已在 data_note 明示）
- 估值加码模式用"价格在自身历史区间中的分位"作为 PE 分位的代理
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta


# ── 估值温度计 → 定投倍数 ──────────────────────────────

def valuation_to_multiplier(percentile: float) -> tuple[float, str]:
    """
    把 PE(或 PB) 分位（0~1）映射为定投倍数。

    percentile 越小 = 越低估 = 越多投；越大 = 越高估 = 越少投/暂停。
    返回 (multiplier, note)。
    """
    p = max(0.0, min(1.0, percentile))
    if p < 0.2:
        return 1.5, "估值处于历史低位（<20%分位），低位多攒份额"
    if p < 0.6:
        return 1.0, "估值中性（20%~60%分位），按计划定投"
    if p < 0.8:
        return 0.5, "估值偏高（60%~80%分位），本期减码"
    return 0.0, "估值过热（>80%分位），建议暂停定投、现金留待低位"


# ── 定投止盈 / 再平衡建议 ──────────────────────────────

def dca_target_exit(percentile: float | None, xirr_pct: float | None,
                    target_xirr_pct: float = 8.0) -> dict:
    """
    定投离场（止盈导向，而非止损）。

    定投靠"低位不割肉、高位止盈"赚钱，因此离场只看两件事：
    1) 组合资金加权收益是否达到目标（XIRR ≥ target）
    2) 估值是否进入高估区（percentile 高）

    返回 {action, ratio, reason}，ratio 为建议保留仓位比例。
    """
    p = max(0.0, min(1.0, percentile)) if percentile is not None else None
    x = xirr_pct if xirr_pct is not None else None

    if p is not None and p >= 0.8:
        return {"action": "止盈赎回", "ratio": 0.3,
                "reason": f"估值已进入历史高位（{p:.0%}分位），建议分批赎回至 3 成，转债券/黄金"}
    if p is not None and p >= 0.6 and x is not None and x >= target_xirr_pct:
        return {"action": "目标止盈", "ratio": 0.5,
                "reason": f"定投年化 {x:.1f}% 已达目标 {target_xirr_pct:.0f}%，且估值不低，建议减半仓落袋"}
    if x is not None and x >= target_xirr_pct * 1.25:
        return {"action": "目标止盈", "ratio": 0.5,
                "reason": f"定投年化 {x:.1f}% 显著超过目标，建议减半仓锁定利润"}
    if p is not None and p < 0.2:
        return {"action": "继续持有", "ratio": 1.0,
                "reason": f"估值仍处低位（{p:.0%}分位），继续持有并维持定投"}
    return {"action": "继续持有", "ratio": 1.0, "reason": "未触发止盈或高估条件，按计划持有"}


# ── XIRR（资金加权年化收益率）──────────────────────────

def xirr(cashflows: list[tuple], guess: float = 0.1, tol: float = 1e-7,
         max_iter: int = 200) -> float | None:
    """
    计算一组不固定日期现金流的资金加权年化收益率 (XIRR)。

    cashflows: [(datetime|str, amount), ...]，投入为负、回收为正。
    用二分法求解净现值=0 的折现率，稳健不依赖 scipy。
    """
    def _to_dt(d):
        if isinstance(d, datetime):
            return d
        s = str(d)[:10].replace("/", "-")
        return datetime.strptime(s, "%Y-%m-%d")

    flows = sorted(((_to_dt(d), float(a)) for d, a in cashflows), key=lambda x: x[0])
    if not flows:
        return None

    t0 = flows[0][0]

    def npv(rate: float) -> float:
        total = 0.0
        for dt, amt in flows:
            years = (dt - t0).days / 365.0
            total += amt / ((1.0 + rate) ** years)
        return total

    f0 = npv(0.0)

    if f0 >= 0:
        # 盈利：根在 [0, hi]
        lo, hi = 0.0, 1.0
        fhi = npv(hi)
        while fhi > 0 and hi < 1e4:
            hi *= 2.0
            fhi = npv(hi)
        if fhi > 0:
            return None
    else:
        # 亏损：根在 [-0.9999, 0]
        lo, hi = -0.9999, 0.0
        flo = npv(lo)
        if flo < 0:
            return None

    flo = npv(lo)
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        fmid = npv(mid)
        if abs(fmid) < tol:
            return mid
        if fmid * flo < 0:
            hi = mid
        else:
            lo = mid
            flo = fmid
    return (lo + hi) / 2.0


# ── 定投模拟 ───────────────────────────────────────────

def _contribution_indices(dates: list[str], start_idx: int, end_idx: int,
                          period: str, day_of_month: int) -> list[int]:
    """
    生成定投扣款日对应的交易日索引列表。

    月定投：每月同一天（缺日则取当月最后一天），找该日之后最近的交易日。
    周定投：每 7 天一次。
    """
    def parse(d):
        return datetime.strptime(d, "%Y-%m-%d")

    date_objs = [parse(d) for d in dates]
    start_dt = date_objs[start_idx]
    end_dt = date_objs[end_idx]

    targets: list[datetime] = []

    if period == "weekly":
        cur = start_dt
        while cur <= end_dt:
            targets.append(cur)
            cur = cur + timedelta(days=7)
    else:  # monthly
        year, month = start_dt.year, start_dt.month
        while (year, month) <= (end_dt.year, end_dt.month):
            dim = calendar.monthrange(year, month)[1]
            day = min(day_of_month, dim)
            t = datetime(year, month, day)
            if t < start_dt:
                # 起始月：定投日早于回测起点，顺延到起点
                t = start_dt
            if start_dt <= t <= end_dt:
                targets.append(t)
            month += 1
            if month > 12:
                month = 1
                year += 1

    # 每个目标日 → 最近（>=）的交易日索引
    indices = []
    i = start_idx
    for t in targets:
        while i <= end_idx and date_objs[i] < t:
            i += 1
        if i <= end_idx:
            indices.append(i)
        else:
            break
    # 去重（同日映射到同一交易日）
    seen = set()
    out = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            out.append(idx)
    return out


def _price_percentile(closes: list[float], idx: int, lookback: int = 500) -> float:
    """当前价格在自身历史 trailing 窗口中的分位（0~1），作为估值分位的代理。"""
    lo = max(0, idx - lookback + 1)
    window = closes[lo:idx + 1]
    if not window or window[-1] is None:
        return 0.5
    cur = window[-1]
    if cur <= 0:
        return 0.5
    rank = sum(1 for c in window if c is not None and c <= cur)
    n = sum(1 for c in window if c is not None)
    return rank / n if n else 0.5


def _valuation_multiplier_for_backtest(percentile: float) -> float:
    """回测内的估值加码倍数（0=暂停当期，留现金；0.5/1.0/1.5 正常）"""
    if percentile < 0.2:
        return 1.5
    if percentile < 0.6:
        return 1.0
    if percentile < 0.8:
        return 0.5
    return 0.0  # 高估暂停，当期现金留待低位


def _simulate_dca(dates, closes, contrib_indices, amount_per_period,
                  mode: str, subscription_fee_pct: float,
                  redemption_fee_pct_fn, end_idx: int) -> dict:
    """
    单模式定投模拟。mode ∈ {"fixed", "valuation"}。
    每个扣款日投入 amount * mult；mult<1 时剩余部分留在现金池（0 收益），
    期末现金池 + 持仓市值（扣赎回费）作为回收现金流。
    """
    shares = 0.0
    cash_pool = 0.0
    invested = 0.0
    cashflows: list[tuple] = []
    curve: list[dict] = []
    contributions: list[dict] = []

    # 用于每日净值曲线（逐交易日记录）
    first_curve_idx = contrib_indices[0] if contrib_indices else end_idx
    curve_start = min(first_curve_idx, end_idx)

    for idx in contrib_indices:
        if idx > end_idx:
            break
        price = closes[idx]
        if price is None or price <= 0:
            continue
        if mode == "valuation":
            mult = _valuation_multiplier_for_backtest(_price_percentile(closes, idx))
        else:
            mult = 1.0

        deploy = amount_per_period * mult
        cash_pool += amount_per_period - deploy
        if deploy > 0:
            fee = deploy * subscription_fee_pct / 100.0
            buy_amount = deploy - fee
            shares += buy_amount / price
            invested += deploy
        # 现金流：本期实际扣款 = amount（固定扣款口径；未投部分记为现金留存）
        cashflows.append((dates[idx], -amount_per_period))
        contributions.append({
            "date": dates[idx], "price": round(price, 4),
            "multiplier": mult, "deploy": round(deploy, 2),
            "shares": round(shares, 4),
        })

    # 每日权益曲线（从首次扣款到期末）
    for idx in range(curve_start, end_idx + 1):
        price = closes[idx] if idx < len(closes) else closes[-1]
        if price is None or price <= 0:
            continue
        curve.append({"date": dates[idx],
                      "equity": round(shares * price + cash_pool, 2)})

    # 期末回收
    final_price = closes[end_idx]
    if final_price is None or final_price <= 0:
        final_price = closes[end_idx - 1]
    market_value = shares * final_price
    redemption_fee = market_value * (redemption_fee_pct_fn(end_idx) or 0.0) / 100.0
    final_value = market_value - redemption_fee + cash_pool
    cashflows.append((dates[end_idx], final_value))

    total_invested = amount_per_period * len(contrib_indices)
    total_return = (final_value - total_invested) / total_invested * 100 if total_invested > 0 else 0.0
    irr = xirr(cashflows)

    # 最大回撤（按每日权益曲线）
    peak = -1e18
    max_dd = 0.0
    for p in curve:
        peak = max(peak, p["equity"])
        if peak > 0:
            dd = (peak - p["equity"]) / peak * 100
            max_dd = max(max_dd, dd)

    return {
        "mode": mode,
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2),
        "xirr_pct": round(irr * 100, 2) if irr is not None else None,
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "contributions": contributions,
        "equity_curve": curve,
    }


def _simulate_lump(dates, closes, start_idx, end_idx, amount_per_period,
                   n_periods, subscription_fee_pct, redemption_fee_pct_fn) -> dict:
    """一次性买入（对比基准）：起点一次性投入 amount*n_periods。"""
    start_price = closes[start_idx]
    final_price = closes[end_idx]
    if start_price is None or start_price <= 0:
        return {"mode": "lump", "xirr_pct": None, "total_return_pct": 0.0,
                "total_invested": 0.0, "final_value": 0.0,
                "max_drawdown_pct": 0.0, "contributions": [], "equity_curve": []}

    total = amount_per_period * n_periods
    fee = total * subscription_fee_pct / 100.0
    shares = (total - fee) / start_price

    curve = []
    peak = -1e18
    max_dd = 0.0
    for idx in range(start_idx, end_idx + 1):
        price = closes[idx]
        if price is None or price <= 0:
            continue
        eq = shares * price
        curve.append({"date": dates[idx], "equity": round(eq, 2)})
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak * 100)

    market_value = shares * final_price
    redemption_fee = market_value * (redemption_fee_pct_fn(end_idx) or 0.0) / 100.0
    final_value = market_value - redemption_fee
    total_return = (final_value - total) / total * 100

    cashflows = [
        (dates[start_idx], -total),
        (dates[end_idx], final_value),
    ]
    irr = xirr(cashflows)

    return {
        "mode": "lump",
        "total_invested": round(total, 2),
        "final_value": round(final_value, 2),
        "xirr_pct": round(irr * 100, 2) if irr is not None else None,
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "contributions": [],
        "equity_curve": curve,
    }


def run_dca_backtest(
    fund_code: str,
    start_date: str,
    end_date: str,
    amount_per_period: float = 2000.0,
    period: str = "monthly",
    subscription_fee_pct: float | None = None,
    dividend_reinvest: bool = True,
) -> dict:
    """
    定投回测主入口：一次拉取行情，输出「固定 / 估值加码 / 一次性」三模式对比。

    参数:
        fund_code: ETF/指数/开放式基金/黄金 代码（同回测引擎）
        start_date/end_date: 定投区间
        amount_per_period: 每期基础金额
        period: "monthly" | "weekly"
        subscription_fee_pct: 申购费率%(None=按类型自动)，ETF/黄金约0.03+滑点，开基约0.15
        dividend_reinvest: 仅作口径提示（开基净值已含再投；价格指数无法计入分红）
    """
    from backtest_engine import _load_history, _locate_range
    from exit_strategies import _redemption_fee

    history = _load_history(fund_code, warmup_days=0)
    dates = history["dates"]
    opens = history["opens"]
    highs = history["highs"]
    lows = history["lows"]
    closes = history["closes"]
    fund_type = history["fund_type"]

    start_idx, end_idx = _locate_range(dates, start_date, end_date, warmup_days=0)

    day_of_month = datetime.strptime(start_date, "%Y-%m-%d").day
    contrib_indices = _contribution_indices(dates, start_idx, end_idx, period, day_of_month)
    if not contrib_indices:
        raise ValueError(f"定投区间内没有可用扣款日（{start_date} ~ {end_date}）")

    # 申购费率：开基默认 0.15%（打折口径），其余 0.08%（佣金+滑点）
    if subscription_fee_pct is None:
        subscription_fee_pct = 0.15 if fund_type == "open" else 0.08

    # 赎回费率函数：开基按持有天数阶梯，其余固定低摩擦
    first_idx = contrib_indices[0]

    def redemption_fee_pct_fn(idx: int) -> float:
        if fund_type == "open":
            return _redemption_fee(idx - first_idx)
        return 0.08

    n_periods = len(contrib_indices)

    fixed = _simulate_dca(dates, closes, contrib_indices, amount_per_period,
                          "fixed", subscription_fee_pct, redemption_fee_pct_fn, end_idx)
    valuation = _simulate_dca(dates, closes, contrib_indices, amount_per_period,
                              "valuation", subscription_fee_pct, redemption_fee_pct_fn, end_idx)
    lump = _simulate_lump(dates, closes, start_idx, end_idx, amount_per_period,
                          n_periods, subscription_fee_pct, redemption_fee_pct_fn)

    # 数据口径说明（诚实化）
    notes = []
    if fund_type in ("etf", "index"):
        notes.append("价格指数数据，未含分红再投资（红利/债券类定投收益被系统性低估）")
    elif fund_type == "gold":
        notes.append("黄金现货价格，未含 ETF 管理费与二级市场折溢价")
    elif fund_type == "qdii":
        notes.append("QDII 标的为境内指数代理，非真实海外净值，回测仅供参考")
    if fund_type == "open":
        notes.append("开放式基金按当日净值确认，净值已含红利再投资；申购/赎回费按默认档估算")
    if not dividend_reinvest:
        notes.append("已选择现金分红口径（价格指数不含分红，二者无差异）")

    return {
        "mode": "dca",
        "fund_code": fund_code,
        "fund_name": history["fund_name"],
        "fund_type": fund_type,
        "start_date": dates[start_idx],
        "end_date": dates[end_idx],
        "period": period,
        "amount_per_period": amount_per_period,
        "subscription_fee_pct": subscription_fee_pct,
        "dividend_reinvest": dividend_reinvest,
        "n_periods": n_periods,
        "results": [fixed, valuation, lump],
        "data_note": " | ".join(notes) if notes else None,
        "generated_at": datetime.now().isoformat(),
    }
