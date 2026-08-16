"""
观澜 — 策略回测引擎

逐日 walk-forward 模拟：在每个历史时点用"到当天为止"的数据计算指标，
生成入场/离场信号，次日开盘价执行交易。

核心约束：
- 无未来信息泄露：指标计算仅使用 ≤当天 的数据
- 交易执行在次日开盘价
- 热身期 120 天不产生信号
"""

from datetime import datetime, timedelta

from indicators import (
    compute_ma, compute_atr, compute_rsi, compute_macd,
    compute_ma_status, compute_volatility, compute_momentum,
    compute_rsrs, compute_consecutive_direction,
)

# ═══════════════════════════════════════════════════════════
# 信号快照计算
# ═══════════════════════════════════════════════════════════

def _compute_snapshot_signals(closes: list[float],
                               highs: list[float],
                               lows: list[float]) -> dict:
    """
    给定截至某天的 OHLCV 数组，计算 strategy_engine 风格的技术指标。

    返回的 dict 以 "sh000001" 和 "sh000300" 为 key（兼容 quant_strategies
    的信号函数），两个 key 下填充相同的数据。
    """
    if len(closes) < 65:
        return {}

    # ── MA 交叉 ──
    ma20 = compute_ma(closes, 20)
    ma60 = compute_ma(closes, 60)
    cur_ma20 = ma20[-1] if ma20[-1] is not None else None
    cur_ma60 = ma60[-1] if ma60[-1] is not None else None
    prev_ma20 = ma20[-2] if len(ma20) > 1 and ma20[-2] is not None else None
    prev_ma60 = ma60[-2] if len(ma60) > 1 and ma60[-2] is not None else None

    ma_status = "未知"
    if cur_ma20 and cur_ma60:
        if cur_ma20 > cur_ma60:
            if prev_ma20 and prev_ma60 and prev_ma20 <= prev_ma60:
                ma_status = "金叉(刚突破)"
            else:
                ma_status = "多头排列"
        else:
            if prev_ma20 and prev_ma60 and prev_ma20 >= prev_ma60:
                ma_status = "死叉(刚破位)"
            else:
                ma_status = "空头排列"

    # ── 波动率 ──
    vol = compute_volatility(closes, 60)

    # ── 价格网格 ──
    recent_closes = closes[-60:]
    grid_high = round(max(recent_closes), 2)
    grid_low = round(min(recent_closes), 2)
    grid_mid = round((grid_high + grid_low) / 2, 2)

    # ── 动量 ──
    mom_1m = compute_momentum(closes, 21)
    mom_3m = compute_momentum(closes, 63)

    # ── RSRS ──
    rsrs = compute_rsrs(highs, lows, window=18)

    # ── ATR(14) ──
    atr14 = compute_atr(highs, lows, closes, 14)

    # ── RSI(14) ──
    rsi14 = compute_rsi(closes, 14)

    # ── MACD ──
    macd_result = compute_macd(closes)

    signal_block = {
        "name": "回测标的",
        "latest_close": round(closes[-1], 2),
        "ma20": round(cur_ma20, 2) if cur_ma20 else None,
        "ma60": round(cur_ma60, 2) if cur_ma60 else None,
        "ma_status": ma_status,
        "volatility_60d": vol,
        "grid_high": grid_high,
        "grid_low": grid_low,
        "grid_mid": grid_mid,
        "momentum_1m": mom_1m,
        "momentum_3m": mom_3m,
        "rsrs_score": rsrs["score"],
        "rsrs_status": rsrs["status"],
        "rsrs_beta": rsrs["beta"],
        "rsrs_zscore": rsrs["zscore"],
        "atr_14": atr14,
        "rsi_14": rsi14,
        "macd": macd_result.get("macd"),
        "macd_signal": macd_result.get("signal"),
        "macd_hist": macd_result.get("hist"),
    }

    return {
        "sh000001": signal_block,
        "sh000300": signal_block,
    }


# ═══════════════════════════════════════════════════════════
# 基金数据快照（供离场策略使用）
# ═══════════════════════════════════════════════════════════

def _compute_fund_scalar_bundle(closes: list[float],
                                 highs: list[float],
                                 lows: list[float]) -> dict:
    """
    计算截至某天的离场侧纯指标标量（策略无关，不嵌入数组）。

    这是 _compute_snapshot_fund_data 中昂贵的部分；多离场对比时预计算一次，
    各策略共享，避免 N× 重复计算。返回空 dict 表示数据不足。
    """
    if len(closes) < 20:
        return {}

    ma5 = compute_ma(closes, 5)
    ma10 = compute_ma(closes, 10)
    ma20 = compute_ma(closes, 20)
    ma60 = compute_ma(closes, 60)
    atr14 = compute_atr(highs, lows, closes, 14)
    rsi14 = compute_rsi(closes, 14)
    macd = compute_macd(closes)
    vol20 = compute_volatility(closes, 20)
    vol60 = compute_volatility(closes, 60)
    mom5d = compute_momentum(closes, 5)
    mom1m = compute_momentum(closes, 21)
    mom3m = compute_momentum(closes, 63)
    consecutive = compute_consecutive_direction(closes)

    recent = closes[-60:]
    grid_high = round(max(recent), 2)
    grid_low = round(min(recent), 2)
    grid_mid = round((grid_high + grid_low) / 2, 2)

    return {
        "ma5": round(ma5[-1], 4) if ma5[-1] is not None else None,
        "ma10": round(ma10[-1], 4) if ma10[-1] is not None else None,
        "ma20": round(ma20[-1], 4) if ma20[-1] is not None else None,
        "ma60": round(ma60[-1], 4) if ma60[-1] is not None else None,
        "ma_status": compute_ma_status(ma20, ma60),
        "atr_14": atr14,
        "rsi_14": rsi14,
        "macd": macd,
        "volatility_20d": vol20,
        "volatility_60d": vol60,
        "grid_high": grid_high,
        "grid_low": grid_low,
        "grid_mid": grid_mid,
        "momentum_5d": mom5d,
        "momentum_1m": mom1m,
        "momentum_3m": mom3m,
        "consecutive_direction": consecutive,
    }


def _assemble_fund_data(fund_code: str, fund_name: str,
                         fund_type: str, dates: list[str],
                         opens: list[float], highs: list[float],
                         lows: list[float], closes: list[float],
                         scalars: dict) -> dict:
    """
    把预计算的指标标量 + 当日切片数组组装成离场策略所需的 fund_data dict。
    scalars 为空（数据不足）时返回 {}。
    """
    if not scalars:
        return {}

    return {
        "fund_code": fund_code,
        "fund_name": fund_name,
        "fund_type": fund_type,
        "dates": dates,
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "closes": closes,
        "latest_nav": round(closes[-1], 4),
        "latest_nav_date": dates[-1] if dates else "",
        **scalars,
    }


def _compute_snapshot_fund_data(fund_code: str, fund_name: str,
                                 fund_type: str, dates: list[str],
                                 opens: list[float], highs: list[float],
                                 lows: list[float], closes: list[float]) -> dict:
    """
    给定截至某天的 OHLCV 数组，计算 fund_data.fetch_fund_history() 风格的数据，
    供 exit_strategies 各信号函数使用。
    """
    return _assemble_fund_data(
        fund_code, fund_name, fund_type,
        dates, opens, highs, lows, closes,
        _compute_fund_scalar_bundle(closes, highs, lows),
    )


# ═══════════════════════════════════════════════════════════
# 入场 / 离场信号适配器
# ═══════════════════════════════════════════════════════════

def _check_entry_signal(strategy_id: str, snapshot_signals: dict,
                         current_cycle: str) -> tuple:
    """
    调用 quant_strategies._make_signal()，返回 (signal, confidence, reasoning)。
    """
    from quant_strategies import _make_signal
    sig = _make_signal(strategy_id, current_cycle, snapshot_signals)
    return sig.signal, sig.confidence, sig.reasoning


def _check_exit_signal(strategy_id: str, fund_data: dict,
                        entry_price: float | None,
                        entry_date: str | None,
                        current_cycle: str) -> tuple:
    """
    调用 exit_strategies._make_signal()，返回 (signal, confidence)。

    注意：离场策略依赖 entry_price/entry_date 来计算盈亏和持有天数；
    如果未持仓则不应调用此函数。
    """
    from exit_strategies import _make_signal as _make_exit_signal
    sig = _make_exit_signal(strategy_id, fund_data, entry_price, entry_date, current_cycle)
    return sig.signal, sig.confidence


# ═══════════════════════════════════════════════════════════
# 绩效指标计算
# ═══════════════════════════════════════════════════════════

def _compute_metrics(equity_curve: list[dict], trade_log: list[dict],
                     initial_capital: float, benchmark_curve: list[float],
                     trading_days: int, risk_free_rate: float = 0.02) -> dict:
    """
    根据权益曲线和交易日志计算绩效指标。
    """
    if not equity_curve or trading_days < 5:
        return {
            "total_return_pct": 0.0, "cagr_pct": 0.0, "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0, "max_drawdown_duration_days": 0,
            "win_rate_pct": 0.0, "profit_factor": 0.0, "total_trades": 0,
            "benchmark_return_pct": 0.0, "alpha_pct": 0.0,
            "calmar_ratio": 0.0, "sortino_ratio": 0.0,
            "annualized_volatility_pct": 0.0, "max_consecutive_losses": 0,
        }

    final_equity = equity_curve[-1]["equity"]

    # 累计收益
    total_return_pct = round((final_equity - initial_capital) / initial_capital * 100, 2)

    # 年化收益 (CAGR)
    years = trading_days / 252
    if years > 0 and initial_capital > 0:
        cagr_pct = round(((final_equity / initial_capital) ** (1 / years) - 1) * 100, 2)
    else:
        cagr_pct = 0.0

    # 夏普比率
    daily_returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["equity"]
        cur = equity_curve[i]["equity"]
        if prev > 0:
            daily_returns.append((cur - prev) / prev)

    sortino_ratio = 0.0
    annualized_vol_pct = 0.0
    if len(daily_returns) > 5:
        mean_ret = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
        std_ret = variance ** 0.5
        risk_free_daily = risk_free_rate / 252
        if std_ret > 0:
            sharpe_ratio = round((mean_ret - risk_free_daily) / std_ret * (252 ** 0.5), 2)
        else:
            sharpe_ratio = 0.0

        # 年化波动率
        annualized_vol_pct = round(std_ret * (252 ** 0.5) * 100, 2)

        # Sortino：下行标准差（相对无风险利率的下方偏差）
        downside = [min(0.0, r - risk_free_daily) for r in daily_returns]
        downside_var = sum(d * d for d in downside) / len(downside)
        downside_std = downside_var ** 0.5
        if downside_std > 0:
            sortino_ratio = round((mean_ret - risk_free_daily) / downside_std * (252 ** 0.5), 2)
        else:
            sortino_ratio = 0.0
    else:
        sharpe_ratio = 0.0

    # 最大回撤
    max_drawdown_pct = 0.0
    max_drawdown_days = 0
    peak = initial_capital
    peak_idx = 0
    for i, point in enumerate(equity_curve):
        eq = point["equity"]
        if eq > peak:
            peak = eq
            peak_idx = i
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        if dd > max_drawdown_pct:
            max_drawdown_pct = round(dd, 2)
            max_drawdown_days = i - peak_idx

    # 胜率 & 盈亏比（只统计完整闭环：清仓/卖出/期末清仓；减仓不计为独立交易）
    profitable = 0
    gross_profit = 0.0
    gross_loss = 0.0
    full_exit_actions = {"卖出", "清仓", "期末清仓"}
    completed_trades = [t for t in trade_log if t.get("action") in full_exit_actions]
    for t in completed_trades:
        pnl_pct = t.get("pnl_pct", 0) or 0
        if pnl_pct > 0:
            profitable += 1
        # 金额口径盈亏（优先 pnl_amount，缺失则跳过该笔的金额贡献）
        pnl_amt = t.get("pnl_amount")
        if pnl_amt is not None:
            if pnl_amt > 0:
                gross_profit += pnl_amt
            else:
                gross_loss += abs(pnl_amt)

    total_trades = len(completed_trades)
    win_rate_pct = round(profitable / total_trades * 100, 1) if total_trades > 0 else 0.0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (
        999.0 if gross_profit > 0 else 0.0
    )

    # 最长连续亏损交易次数（按交易发生顺序）
    max_consecutive_losses = 0
    cur_streak = 0
    for t in completed_trades:
        pnl_amt = t.get("pnl_amount")
        pnl_pct = t.get("pnl_pct", 0) or 0
        is_loss = (pnl_amt is not None and pnl_amt < 0) or (pnl_amt is None and pnl_pct <= 0)
        if is_loss:
            cur_streak += 1
            max_consecutive_losses = max(max_consecutive_losses, cur_streak)
        else:
            cur_streak = 0

    # 基准收益 (buy-and-hold)
    if len(benchmark_curve) > 0:
        bench_start = benchmark_curve[0]
        bench_end = benchmark_curve[-1]
        benchmark_return_pct = round((bench_end - bench_start) / bench_start * 100, 2) if bench_start > 0 else 0.0
    else:
        benchmark_return_pct = 0.0

    alpha_pct = round(total_return_pct - benchmark_return_pct, 2)

    # Calmar = 年化收益 / 最大回撤绝对值（回撤为 0 时记 0）
    if max_drawdown_pct > 0:
        calmar_ratio = round(cagr_pct / max_drawdown_pct, 2)
    else:
        calmar_ratio = 0.0

    return {
        "total_return_pct": total_return_pct,
        "cagr_pct": cagr_pct,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "max_drawdown_duration_days": max_drawdown_days,
        "win_rate_pct": win_rate_pct,
        "profit_factor": profit_factor,
        "total_trades": total_trades,
        "benchmark_return_pct": benchmark_return_pct,
        "alpha_pct": alpha_pct,
        "calmar_ratio": calmar_ratio,
        "sortino_ratio": sortino_ratio,
        "annualized_volatility_pct": annualized_vol_pct,
        "max_consecutive_losses": max_consecutive_losses,
    }


# ═══════════════════════════════════════════════════════════
# 数据加载 / 区间定位 / 快照预计算（供单策略与多离场对比共用）
# ═══════════════════════════════════════════════════════════

def _load_history(fund_code: str, warmup_days: int = 120) -> dict:
    """获取基金全量历史（网络调用，只做一次）。返回共享数据包。"""
    from fund_data import ETF_INDEX_MAP, _fetch_index_data, _fetch_gold_spot, _fetch_open_fund_nav

    fund_name = fund_code
    fund_type = "unknown"

    # ── 解析基金代码：ETF映射 → 指数直连 → 开放式基金 ──
    mapped = ETF_INDEX_MAP.get(fund_code)
    is_open_fund = False

    if mapped is None:
        # 未在映射表中 → 尝试作为指数代码直连 (sh000xxx / sz399xxx)
        if fund_code.startswith("sh") or fund_code.startswith("sz"):
            mapped = {"symbol": fund_code, "name": f"指数{fund_code}", "type": "index"}
        else:
            # 最后尝试：开放式基金（天天基金/支付宝任意代码，如 000628）
            mapped = None  # 稍后用 _fetch_open_fund_nav 直接获取

    # ── 获取全量历史数据 ──
    raw = None

    if mapped is not None:
        fund_name = mapped["name"]
        fund_type = mapped["type"]
        symbol = mapped["symbol"]

        if symbol == "Au99.99":
            raw = _fetch_gold_spot(days=2500)
        elif symbol.startswith("intl_"):
            if symbol == "intl_ndx":
                raw = _fetch_index_data("sz399006", days=2500)
            elif symbol == "intl_spx":
                raw = _fetch_index_data("sh000300", days=2500)
            elif symbol == "intl_hsi":
                raw = _fetch_index_data("sh000001", days=2500)
            else:
                raw = _fetch_index_data("sh000300", days=2500)
        else:
            raw = _fetch_index_data(symbol, days=2500)
    else:
        # 开放式基金：通过东方财富 API 获取净值历史
        raw = _fetch_open_fund_nav(fund_code, days=2500)
        if raw is not None:
            fund_name = raw.get("fund_name", fund_code)
            fund_type = "open"
            is_open_fund = True

    if raw is None or len(raw.get("closes", [])) < warmup_days + 20:
        common = [k for k in sorted(ETF_INDEX_MAP.keys()) if not k.startswith("sh") and not k.startswith("sz")]
        raise ValueError(
            f"无法获取 {fund_code} 的足够历史数据。"
            f"常用ETF: {', '.join(common[:10])}。"
            f"也可输入指数代码如 sh000300、sz399006，或开放式基金代码如 000628。"
        )

    return {
        "fund_code": fund_code,
        "fund_name": fund_name,
        "fund_type": fund_type,
        "dates": raw["dates"],
        "opens": raw["opens"],
        "highs": raw["highs"],
        "lows": raw["lows"],
        "closes": raw["closes"],
    }


def _locate_range(dates: list[str], start_date: str, end_date: str,
                  warmup_days: int = 120) -> tuple[int, int]:
    """把日期字符串映射到数组索引，并应用热身期调整。返回 (start_idx, end_idx)。"""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"日期格式错误: {e}")

    start_idx = None
    end_idx = None
    for i, d in enumerate(dates):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        if start_idx is None and dt >= start_dt:
            start_idx = i
        if dt <= end_dt:
            end_idx = i

    if start_idx is None:
        raise ValueError(f"起始日期 {start_date} 超出数据范围（{dates[0]} ~ {dates[-1]}）")
    if end_idx is None or end_idx <= start_idx:
        raise ValueError(f"回测区间无效：{start_date} ~ {end_date}")

    # 热身期检查
    if start_idx < warmup_days:
        # 如果数据允许，从 warmup_days 开始；否则调整
        actual_start = max(start_idx, warmup_days)
        if actual_start >= end_idx:
            raise ValueError(f"数据不足以完成热身期（需要 {warmup_days} 天热身，实际可用 {end_idx} 天）")
        start_idx = actual_start

    return start_idx, end_idx


def _precompute_entry_snapshots(closes: list[float], highs: list[float],
                                 lows: list[float], start_idx: int, end_idx: int) -> list:
    """预计算回测区间内每天截止的入场快照（策略无关，只读共享）。下标=day_idx - start_idx。"""
    return [_compute_snapshot_signals(closes[:i + 1], highs[:i + 1], lows[:i + 1])
            for i in range(start_idx, end_idx + 1)]


def _precompute_fund_scalars(closes: list[float], highs: list[float],
                              lows: list[float], start_idx: int, end_idx: int) -> list:
    """预计算回测区间内每天截止的离场指标标量（策略无关，只读共享）。下标=day_idx - start_idx。"""
    return [_compute_fund_scalar_bundle(closes[:i + 1], highs[:i + 1], lows[:i + 1])
            for i in range(start_idx, end_idx + 1)]


# ═══════════════════════════════════════════════════════════
# 主回测函数
# ═══════════════════════════════════════════════════════════

def _simulate(
    fund_code: str,
    fund_name: str,
    fund_type: str,
    dates: list[str],
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    entry_strategy_id: str,
    exit_strategy_id: str,
    start_idx: int,
    end_idx: int,
    initial_capital: float = 100000.0,
    position_size: float = 1.0,
    transaction_cost: float = 0.0003,
    slippage: float = 0.0005,
    min_holding_days: int = 5,
    cycle_assumption: str = "复苏期",
    risk_free_rate: float = 0.02,
    precomputed_snapshots: list | None = None,
    precomputed_fund_scalars: list | None = None,
) -> dict:
    """
    对一份已拉取的行情数据运行单个「入场+离场」策略组合的 walk-forward 模拟。

    参数:
        fund_code/fund_name/fund_type: 标的元信息
        dates/opens/highs/lows/closes: 全量行情（已由 _load_history 获取）
        entry_strategy_id: 入场策略 ID
        exit_strategy_id: 离场策略 ID
        start_idx/end_idx: 回测区间索引（已由 _locate_range 定位）
        precomputed_snapshots: 预计算的入场快照列表（下标=day_idx）；None 时现场计算
        precomputed_fund_scalars: 预计算的离场指标标量列表；None 时现场计算

    返回:
        dict: 与历史版本 run_backtest 完全一致的结构
    """
    n = len(closes)

    # ── Walk-Forward 模拟 ────────────────────────────
    cash = initial_capital
    shares = 0.0
    entry_price = None
    entry_date = None
    entry_idx = None
    pending = None            # 挂单: {"exec_idx", "kind": "buy"|"sell", ...}

    equity_curve = []          # [{date, equity, benchmark_value}]
    trade_log = []             # [{date, action, price, shares, amount, cash_after, equity, pnl_pct, pnl_amount, reason}]

    # 计费模型：开放式基金有申购/赎回费，ETF/指数/黄金/债券仅低交易成本
    from exit_strategies import _redemption_fee

    def buy_cost() -> float:
        return 0.0015 if fund_type == "open" else (transaction_cost + slippage)

    def sell_cost(holding_days) -> float:
        if fund_type == "open":
            return _redemption_fee(holding_days) / 100.0
        return transaction_cost + slippage

    # 基准：buy-and-hold 的收盘价序列（用于对比图表）
    base_close = closes[start_idx] if start_idx < n else 0

    for day_idx in range(start_idx, end_idx + 1):
        trade_executed = False

        # ── (A) 执行到期挂单：昨日信号，今日开盘成交 ──
        if pending is not None and pending["exec_idx"] == day_idx:
            fill_price = opens[day_idx] if day_idx < n else closes[day_idx]
            if pending["kind"] == "buy":
                if fill_price <= 0:
                    pass  # 开盘价缺失，放弃本次入场
                else:
                    deploy_cash = cash * position_size
                    cost = deploy_cash * buy_cost()
                    available = deploy_cash - cost
                    shares = available / fill_price
                    cash -= deploy_cash
                    entry_price = fill_price
                    entry_date = dates[day_idx]
                    entry_idx = day_idx

                    trade_log.append({
                        "date": dates[day_idx],
                        "action": "买入",
                        "price": round(fill_price, 4),
                        "shares": round(shares, 2),
                        "amount": round(deploy_cash, 2),
                        "cash_after": round(cash, 2),
                        "equity": 0.0,  # 下面会更新
                        "pnl_pct": None,
                        "pnl_amount": None,
                        "reason": pending.get("reason", ""),
                    })
                    trade_executed = True
            else:  # sell
                if fill_price <= 0:
                    pass
                else:
                    sell_shares = shares * pending["sell_fraction"]
                    sell_value = sell_shares * fill_price
                    cost = sell_value * sell_cost(day_idx - entry_idx if entry_idx is not None else None)
                    cash += sell_value - cost
                    shares -= sell_shares

                    # 计算盈亏（百分比 + 金额，金额扣除卖出成本）
                    pnl_pct = round((fill_price - entry_price) / entry_price * 100, 2) if entry_price and entry_price > 0 else None
                    pnl_amount = round(sell_value - cost - sell_shares * entry_price, 2) if entry_price and entry_price > 0 else None

                    trade_log.append({
                        "date": dates[day_idx],
                        "action": pending["action_name"],
                        "price": round(fill_price, 4),
                        "shares": round(sell_shares, 2),
                        "amount": round(sell_value, 2),
                        "cash_after": round(cash, 2),
                        "equity": 0.0,
                        "pnl_pct": pnl_pct,
                        "pnl_amount": pnl_amount,
                        "reason": pending.get("reason", ""),
                    })

                    if shares < 0.01:  # 几乎清仓
                        shares = 0.0
                        entry_price = None
                        entry_date = None
                        entry_idx = None

                    trade_executed = True
            pending = None

        # ── (B) 计算当天截止的指标 → 生成次日挂单 ──
        sliced_closes = closes[:day_idx + 1]
        sliced_highs = highs[:day_idx + 1]
        sliced_lows = lows[:day_idx + 1]
        sliced_dates = dates[:day_idx + 1]
        sliced_opens = opens[:day_idx + 1]

        if precomputed_snapshots is not None:
            snapshot = precomputed_snapshots[day_idx - start_idx]
        else:
            snapshot = _compute_snapshot_signals(sliced_closes, sliced_highs, sliced_lows)

        # 次日成交；末日（day_idx+1 > end_idx）不再挂单，避免用当日收盘信息成交当日开盘
        exec_idx = day_idx + 1
        if exec_idx <= end_idx:
            # ── 空仓：检查入场信号 ──
            if shares <= 0 and snapshot:
                signal, confidence, reasoning = _check_entry_signal(
                    entry_strategy_id, snapshot, cycle_assumption
                )
                if signal == "买入" and confidence >= 0.5:
                    pending = {"exec_idx": exec_idx, "kind": "buy",
                               "reason": reasoning[:100] if reasoning else ""}

            # ── 持仓：检查离场信号 ──
            elif shares > 0:
                holding_days = day_idx - entry_idx if entry_idx is not None else 999

                if holding_days >= min_holding_days:
                    if precomputed_fund_scalars is not None:
                        fund_data = _assemble_fund_data(
                            fund_code, fund_name, fund_type,
                            sliced_dates, sliced_opens, sliced_highs, sliced_lows, sliced_closes,
                            precomputed_fund_scalars[day_idx - start_idx],
                        )
                    else:
                        fund_data = _compute_snapshot_fund_data(
                            fund_code, fund_name, fund_type,
                            sliced_dates, sliced_opens, sliced_highs, sliced_lows, sliced_closes,
                        )
                    if fund_data:
                        exit_signal, exit_conf = _check_exit_signal(
                            exit_strategy_id, fund_data, entry_price, entry_date, cycle_assumption,
                        )

                        # 决定卖出比例
                        sell_fraction = 0.0
                        action_name = ""
                        if exit_signal == "清仓":
                            sell_fraction = 1.0
                            action_name = "清仓"
                        elif exit_signal == "减仓":
                            sell_fraction = 0.5
                            action_name = "减仓"

                        if sell_fraction > 0:
                            pending = {"exec_idx": exec_idx, "kind": "sell",
                                       "sell_fraction": sell_fraction,
                                       "action_name": action_name,
                                       "reason": f"离场信号: {exit_signal} (置信度 {exit_conf:.0%})"}

        # ── (C) 记录每日权益 ──
        mark_price = closes[day_idx]
        equity = cash + shares * mark_price

        # 计算基准净值（buy-and-hold）
        benchmark_value = initial_capital * (closes[day_idx] / base_close) if base_close > 0 else initial_capital

        equity_curve.append({
            "date": dates[day_idx],
            "equity": round(equity, 2),
            "benchmark": round(benchmark_value, 2),
        })

        # 更新当天交易记录的权益
        if trade_executed and trade_log:
            trade_log[-1]["equity"] = round(equity, 2)

    # ── 期末强平（如果仍持仓） ──
    if shares > 0:
        final_price = closes[end_idx]
        final_value = shares * final_price
        cost = final_value * sell_cost(end_idx - entry_idx if entry_idx is not None else None)
        cash += final_value - cost
        pnl_pct = round((final_price - entry_price) / entry_price * 100, 2) if entry_price and entry_price > 0 else None
        pnl_amount = round(final_value - cost - shares * entry_price, 2) if entry_price and entry_price > 0 else None

        trade_log.append({
            "date": dates[end_idx],
            "action": "期末清仓",
            "price": round(final_price, 4),
            "shares": round(shares, 2),
            "amount": round(final_value, 2),
            "cash_after": round(cash, 2),
            "equity": round(cash, 2),
            "pnl_pct": pnl_pct,
            "pnl_amount": pnl_amount,
            "reason": "回测到期自动清仓",
        })
        shares = 0.0

        # 更新最后一天的权益
        if equity_curve:
            equity_curve[-1]["equity"] = round(cash, 2)

    # ── 计算绩效指标 ──
    trading_days = end_idx - start_idx + 1
    benchmark_closes = closes[start_idx:end_idx + 1]

    final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
    metrics = _compute_metrics(equity_curve, trade_log, initial_capital,
                                benchmark_closes, trading_days, risk_free_rate)

    # 数据来源说明（回测数字诚实化：价格指数/QDII 代理等提示）
    data_note = None
    if fund_type == "qdii":
        data_note = "QDII 标的为境内指数代理，非真实海外净值"
    elif fund_type in ("etf", "index"):
        # 红利/债券类标的的核心收益来自分红/票息再投资，价格指数会系统性低估
        div_or_bond = (fund_code in ("512890", "512880", "sh000922")
                       or "红利" in fund_name or "债" in fund_name)
        if div_or_bond:
            data_note = "红利/债券为价格指数，未含分红/票息再投资——回测收益显著低于真实 ETF 表现（红利再投年化约+2~3%）"
        else:
            data_note = "价格指数数据，未含分红再投资"
    elif fund_type == "gold":
        data_note = "黄金现货价格，未含 ETF 管理费(~0.5%/年)与二级市场折溢价"

    return {
        "fund_code": fund_code,
        "fund_name": fund_name,
        "entry_strategy": entry_strategy_id,
        "exit_strategy": exit_strategy_id,
        "start_date": dates[start_idx],
        "end_date": dates[end_idx],
        "initial_capital": initial_capital,
        "final_equity": round(final_equity, 2),
        "metrics": metrics,
        "equity_curve": equity_curve,
        "trade_log": trade_log,
        "cycle_assumption": cycle_assumption,
        "data_note": data_note,
        "generated_at": datetime.now().isoformat(),
    }


def run_backtest(
    fund_code: str,
    entry_strategy_id: str,
    exit_strategy_id: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    position_size: float = 1.0,
    warmup_days: int = 120,
    transaction_cost: float = 0.0003,
    slippage: float = 0.0005,
    min_holding_days: int = 5,
    cycle_assumption: str = "复苏期",
    risk_free_rate: float = 0.02,
) -> dict:
    """
    主回测函数：walk-forward 模拟（单入场+单离场）。

    参数:
        fund_code: ETF/指数代码，如 "510300"
        entry_strategy_id: 入场策略 ID
        exit_strategy_id: 离场策略 ID
        start_date: 回测开始日期 "YYYY-MM-DD"
        end_date: 回测结束日期 "YYYY-MM-DD"
        initial_capital: 初始资金
        position_size: 每次买入仓位比例 (0~1)
        warmup_days: 热身天数（不产生交易信号）
        transaction_cost: 单边交易成本（默认 0.03%）
        slippage: 滑点（默认 0.05%，非开放式基金计入）
        min_holding_days: 最短持有天数（期间不检查离场）
        cycle_assumption: 宏观周期假设
        risk_free_rate: 无风险利率（用于 Sharpe/Sortino，默认 2%）

    返回:
        dict: 包含 metrics, equity_curve, trade_log 等
    """
    history = _load_history(fund_code, warmup_days)
    start_idx, end_idx = _locate_range(history["dates"], start_date, end_date, warmup_days)

    # 预计算策略无关快照（单策略也复用，避免 O(n²) 重复切片计算）
    entry_snapshots = _precompute_entry_snapshots(history["closes"], history["highs"],
                                                   history["lows"], start_idx, end_idx)
    fund_scalars = _precompute_fund_scalars(history["closes"], history["highs"],
                                             history["lows"], start_idx, end_idx)

    return _simulate(
        fund_code=fund_code,
        fund_name=history["fund_name"],
        fund_type=history["fund_type"],
        dates=history["dates"],
        opens=history["opens"],
        highs=history["highs"],
        lows=history["lows"],
        closes=history["closes"],
        entry_strategy_id=entry_strategy_id,
        exit_strategy_id=exit_strategy_id,
        start_idx=start_idx,
        end_idx=end_idx,
        initial_capital=initial_capital,
        position_size=position_size,
        transaction_cost=transaction_cost,
        slippage=slippage,
        min_holding_days=min_holding_days,
        cycle_assumption=cycle_assumption,
        risk_free_rate=risk_free_rate,
        precomputed_snapshots=entry_snapshots,
        precomputed_fund_scalars=fund_scalars,
    )


def run_backtest_multi_exit(
    fund_code: str,
    entry_strategy_id: str,
    exit_strategy_ids: list[str],
    start_date: str,
    end_date: str,
    initial_capital: float = 100000.0,
    position_size: float = 1.0,
    warmup_days: int = 120,
    transaction_cost: float = 0.0003,
    slippage: float = 0.0005,
    min_holding_days: int = 5,
    cycle_assumption: str = "复苏期",
    risk_free_rate: float = 0.02,
) -> dict:
    """
    单入场 + 多离场策略对比回测：拉取一次行情数据，对每个离场策略独立模拟，
    共享预计算的入场快照与离场指标标量。返回对比数据包。
    """
    exit_strategy_ids = list(dict.fromkeys(exit_strategy_ids))
    if not exit_strategy_ids:
        raise ValueError("请至少选择一个离场策略")

    # 惰性导入策略定义做名称映射（避免模块顶部新增导入）
    from quant_strategies import STRATEGY_DEFS
    from exit_strategies import EXIT_STRATEGY_DEFS
    entry_name_map = {s["id"]: s.get("name", s["id"]) for s in STRATEGY_DEFS}
    exit_name_map = {s["id"]: s.get("name", s["id"]) for s in EXIT_STRATEGY_DEFS}

    history = _load_history(fund_code, warmup_days)
    dates = history["dates"]
    opens = history["opens"]
    highs = history["highs"]
    lows = history["lows"]
    closes = history["closes"]

    start_idx, end_idx = _locate_range(dates, start_date, end_date, warmup_days)

    # 预计算策略无关的快照与指标标量，各策略共享（避免 N× 重复计算）
    entry_snapshots = _precompute_entry_snapshots(closes, highs, lows, start_idx, end_idx)
    fund_scalars = _precompute_fund_scalars(closes, highs, lows, start_idx, end_idx)

    raw_runs = []
    for exit_id in exit_strategy_ids:
        raw_runs.append(_simulate(
            fund_code=fund_code,
            fund_name=history["fund_name"],
            fund_type=history["fund_type"],
            dates=dates,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            entry_strategy_id=entry_strategy_id,
            exit_strategy_id=exit_id,
            start_idx=start_idx,
            end_idx=end_idx,
            initial_capital=initial_capital,
            position_size=position_size,
            transaction_cost=transaction_cost,
            slippage=slippage,
            min_holding_days=min_holding_days,
            cycle_assumption=cycle_assumption,
            risk_free_rate=risk_free_rate,
            precomputed_snapshots=entry_snapshots,
            precomputed_fund_scalars=fund_scalars,
        ))

    # 基准曲线各策略相同，提升到顶层；剥离每个 exit 的 equity_curve 中重复的 benchmark
    first_run = raw_runs[0]
    benchmark_curve = [
        {"date": p["date"], "benchmark": p["benchmark"]}
        for p in first_run["equity_curve"]
    ]

    exit_results = []
    for run in raw_runs:
        exit_results.append({
            "exit_strategy": run["exit_strategy"],
            "exit_strategy_name": exit_name_map.get(run["exit_strategy"], run["exit_strategy"]),
            "final_equity": run["final_equity"],
            "metrics": run["metrics"],
            "equity_curve": [
                {"date": p["date"], "equity": p["equity"]}
                for p in run["equity_curve"]
            ],
            "trade_log": run["trade_log"],
        })

    return {
        "mode": "compare",
        "fund_code": fund_code,
        "fund_name": history["fund_name"],
        "fund_type": history["fund_type"],
        "entry_strategy": entry_strategy_id,
        "entry_strategy_name": entry_name_map.get(entry_strategy_id, entry_strategy_id),
        "start_date": first_run["start_date"],
        "end_date": first_run["end_date"],
        "initial_capital": initial_capital,
        "position_size": position_size,
        "cycle_assumption": cycle_assumption,
        "warmup_days": warmup_days,
        "transaction_cost": transaction_cost,
        "min_holding_days": min_holding_days,
        "benchmark_curve": benchmark_curve,
        "exit_results": exit_results,
        "data_note": first_run.get("data_note"),
        "generated_at": datetime.now().isoformat(),
    }
