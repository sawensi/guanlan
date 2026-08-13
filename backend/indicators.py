"""
观澜 — 共用技术指标计算函数

从 fund_data.py 和 strategy_engine.py 提取，供:
- strategy_engine.py (实时信号)
- fund_data.py (基金数据)
- backtest_engine.py (回测)
共用，避免重复代码。
"""

import math


def compute_ma(values: list[float], window: int) -> list[float | None]:
    """计算移动均线，不足窗口返回 None"""
    if len(values) < window:
        return [None] * len(values)
    result = []
    for i in range(len(values)):
        if i < window - 1:
            result.append(None)
        else:
            result.append(sum(values[i - window + 1:i + 1]) / window)
    return result


def compute_atr(highs: list[float], lows: list[float], closes: list[float],
                window: int = 14) -> float | None:
    """Average True Range"""
    if len(closes) < window + 1:
        return None
    tr_list = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)
    if len(tr_list) < window:
        return None
    atr = sum(tr_list[:window]) / window
    for i in range(window, len(tr_list)):
        atr = (atr * (window - 1) + tr_list[i]) / window
    return round(atr, 4)


def compute_rsi(closes: list[float], window: int = 14) -> float | None:
    """Relative Strength Index"""
    if len(closes) < window + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains[-window:]) / window
    avg_loss = sum(losses[-window:]) / window
    for i in range(window, len(gains)):
        avg_gain = (avg_gain * (window - 1) + gains[i]) / window
        avg_loss = (avg_loss * (window - 1) + losses[i]) / window
    if avg_loss == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 2)


def compute_macd(closes: list[float],
                 fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD (12, 26, 9)"""
    if len(closes) < slow + signal:
        return {"macd": None, "signal": None, "hist": None}

    def _ema(data: list[float], period: int) -> list[float]:
        k = 2 / (period + 1)
        result = [data[0]]
        for i in range(1, len(data)):
            result.append(data[i] * k + result[-1] * (1 - k))
        return result

    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(closes))]
    signal_line = _ema(macd_line, signal)
    hist = macd_line[-1] - signal_line[-1]

    return {
        "macd": round(macd_line[-1], 4),
        "signal": round(signal_line[-1], 4),
        "hist": round(hist, 4),
    }


def compute_ma_status(ma20: list, ma60: list) -> str:
    """判断 MA20 vs MA60 排列状态"""
    cur20 = ma20[-1] if len(ma20) > 0 and ma20[-1] is not None else None
    cur60 = ma60[-1] if len(ma60) > 0 and ma60[-1] is not None else None
    prev20 = ma20[-2] if len(ma20) > 1 and ma20[-2] is not None else None
    prev60 = ma60[-2] if len(ma60) > 1 and ma60[-2] is not None else None
    if cur20 and cur60:
        if cur20 > cur60:
            if prev20 and prev60 and prev20 <= prev60:
                return "金叉(刚突破)"
            return "多头排列"
        else:
            if prev20 and prev60 and prev20 >= prev60:
                return "死叉(刚破位)"
            return "空头排列"
    return "未知"


def compute_volatility(closes: list[float], days: int = 60) -> float | None:
    """年化波动率 (%)"""
    if len(closes) < days + 1:
        return None
    idx = len(closes) - days - 1
    recent = closes[idx:]
    returns = []
    for i in range(1, len(recent)):
        if recent[i - 1] and recent[i - 1] != 0:
            returns.append((recent[i] - recent[i - 1]) / recent[i - 1])
    if not returns:
        return None
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    return round(math.sqrt(variance) * math.sqrt(250) * 100, 2)


def compute_momentum(closes: list[float], period: int) -> float | None:
    """计算 period 日动量 (%)"""
    if len(closes) <= period:
        return None
    prev = closes[-period - 1]
    cur = closes[-1]
    if prev and prev != 0:
        return round((cur - prev) / prev * 100, 2)
    return None


def compute_rsrs(highs: list[float], lows: list[float], window: int = 18) -> dict:
    """
    RSRS (阻力支撑相对强度) 计算

    用最近 window 天的 (low, high) 做 OLS 回归:
      high = beta * low + alpha
    RSRS 得分 = beta 的 Z-score (相对过去 60 天)

    返回: {score, status, beta, zscore}
    """
    if len(highs) < window or len(lows) < window:
        return {"score": None, "status": "数据不足", "beta": None, "zscore": None}

    # 取最近 window 天
    h = highs[-window:]
    l = lows[-window:]

    # OLS: high = beta * low + alpha
    n = len(l)
    mean_l = sum(l) / n
    mean_h = sum(h) / n
    cov = sum((l[i] - mean_l) * (h[i] - mean_h) for i in range(n))
    var_l = sum((l[i] - mean_l) ** 2 for i in range(n))
    if var_l == 0:
        return {"score": None, "status": "无法计算", "beta": None, "zscore": None}
    beta = cov / var_l

    # 计算过去 60 天每天的 beta（滑动窗口），用于 Z-score
    betas = []
    for i in range(window - 1, len(highs)):
        hw = highs[i - window + 1:i + 1]
        lw = lows[i - window + 1:i + 1]
        mean_lw = sum(lw) / n
        mean_hw = sum(hw) / n
        cov_w = sum((lw[j] - mean_lw) * (hw[j] - mean_hw) for j in range(n))
        var_lw = sum((lw[j] - mean_lw) ** 2 for j in range(n))
        if var_lw > 0:
            betas.append(cov_w / var_lw)

    if len(betas) < 5:
        return {"score": beta, "status": "beta=" + str(round(beta, 3)), "beta": beta, "zscore": None}

    mean_beta = sum(betas) / len(betas)
    std_beta = (sum((b - mean_beta) ** 2 for b in betas) / len(betas)) ** 0.5
    if std_beta == 0:
        zscore = 0
    else:
        zscore = (beta - mean_beta) / std_beta

    # RSRS 得分 = tanh(zscore)，压缩到 [-1, 1]
    score = math.tanh(zscore * 0.5)

    if zscore > 0.7:
        status = "支撑强于阻力"
    elif zscore > 0:
        status = "支撑略强"
    elif zscore > -0.7:
        status = "阻力略强"
    else:
        status = "阻力强于支撑"

    return {"score": round(score, 4), "status": status, "beta": round(beta, 4), "zscore": round(zscore, 4)}


def compute_consecutive_direction(closes: list[float]) -> int:
    """连续涨跌天数 (正=连涨, 负=连跌, 0=平盘)"""
    if len(closes) < 2:
        return 0
    direction = None
    count = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            cur_dir = 1
        elif closes[i] < closes[i - 1]:
            cur_dir = -1
        else:
            cur_dir = 0
        if direction is None:
            direction = cur_dir
            count = 1 if cur_dir != 0 else 0
        elif cur_dir == direction and cur_dir != 0:
            count += 1
        else:
            break
    return direction * count if direction and count > 0 else 0
