"""
观澜 — 策略信号计算引擎

从真实市场数据中计算策略所需的指标:
- MA20/MA60 均线交叉状态
- RSRS 涨跌力度得分
- 60日波动率
- 60日价格网格区间
- 各类资产近期动量

缓存当日有效，避免重复 API 调用。
"""

import json
import os
from datetime import datetime

from indicators import compute_ma, compute_rsrs

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_FILE = os.path.join(DATA_DIR, "strategy_signals_cache.json")

# 指数配置
INDEX_CONFIG = {
    "sh000001": {"name": "上证指数", "type": "broad"},
    "sh000300": {"name": "沪深300", "type": "broad"},
    "sz399006": {"name": "创业板指", "type": "growth"},
    "sh000016": {"name": "上证50", "type": "value"},
}


def _load_cache() -> dict | None:
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                data = json.load(f)
            if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                return data
    except Exception:
        pass
    return None


def _save_cache(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    data["date"] = datetime.now().strftime("%Y-%m-%d")
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _fetch_index_data(symbol: str, days: int = 120):
    """获取指数日线数据，返回最近 days 行"""
    import akshare as ak
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or len(df) == 0:
            return None
        return df.tail(days)
    except Exception as e:
        print(f"[strategy_engine] Fetch {symbol} failed: {e}")
        return None


# ── 指标计算（从 indicators.py 导入，见文件顶部） ────────


def compute_all_signals() -> dict:
    """计算所有策略信号，带缓存"""
    cached = _load_cache()
    if cached:
        return cached

    print("[strategy_engine] Computing fresh signals...")
    result = {}

    # 1. 抓取上证指数和沪深300数据
    sh_df = _fetch_index_data("sh000001", days=120)
    hs300_df = _fetch_index_data("sh000300", days=120)

    def _calc_broad(df, label):
        if df is None or len(df) < 65:
            return
        closes = df["close"].tolist()
        highs = df["high"].tolist()
        lows = df["low"].tolist()

        # MA 交叉
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

        # 60 日波动率 (年化)
        returns = []
        for i in range(1, min(61, len(closes))):
            if closes[-i] and closes[-i-1] and closes[-i-1] != 0:
                returns.append((closes[-i] - closes[-i-1]) / closes[-i-1])
        vol = None
        if returns:
            daily_std = (sum((r - sum(returns)/len(returns))**2 for r in returns) / len(returns)) ** 0.5
            vol = round(daily_std * (250 ** 0.5) * 100, 2)  # 年化波动率 %

        # 60 日价格区间 (网格)
        recent_closes = closes[-60:]
        grid_high = round(max(recent_closes), 2)
        grid_low = round(min(recent_closes), 2)
        grid_mid = round((grid_high + grid_low) / 2, 2)

        # 近期动量
        if len(closes) >= 42:
            mom_1m = round((closes[-1] - closes[-21]) / closes[-21] * 100, 2) if closes[-21] else None
        else:
            mom_1m = None
        if len(closes) >= 84:
            mom_3m = round((closes[-1] - closes[-63]) / closes[-63] * 100, 2) if closes[-63] else None
        else:
            mom_3m = None

        # RSRS
        rsrs = compute_rsrs(highs, lows, window=18)

        # ATR(14) — Average True Range
        atr14 = None
        if len(highs) >= 15:
            tr_vals = []
            for i in range(1, len(highs)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]),
                )
                tr_vals.append(tr)
            if len(tr_vals) >= 14:
                atr14 = round(sum(tr_vals[:14]) / 14, 4)
                for i in range(14, len(tr_vals)):
                    atr14 = round((atr14 * 13 + tr_vals[i]) / 14, 4)

        # RSI(14) — Relative Strength Index
        rsi14 = None
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i - 1]
                gains.append(diff if diff > 0 else 0)
                losses.append(-diff if diff < 0 else 0)
            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
            for i in range(14, len(gains)):
                avg_gain = (avg_gain * 13 + gains[i]) / 14
                avg_loss = (avg_loss * 13 + losses[i]) / 14
            if avg_loss == 0:
                rsi14 = 100.0
            else:
                rsi14 = round(100 - 100 / (1 + avg_gain / avg_loss), 2)

        # MACD(12,26,9)
        macd_val, macd_signal, macd_hist = None, None, None
        if len(closes) >= 35:
            def _ema(data, period):
                k = 2 / (period + 1)
                out = [data[0]]
                for i in range(1, len(data)):
                    out.append(data[i] * k + out[-1] * (1 - k))
                return out
            ema12 = _ema(closes, 12)
            ema26 = _ema(closes, 26)
            macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
            sig_line = _ema(macd_line, 9)
            macd_val = round(macd_line[-1], 4)
            macd_signal = round(sig_line[-1], 4)
            macd_hist = round(macd_line[-1] - sig_line[-1], 4)

        result[label] = {
            "name": INDEX_CONFIG.get(label, {}).get("name", label),
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
            "macd": macd_val,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
        }

    _calc_broad(sh_df, "sh000001")
    _calc_broad(hs300_df, "sh000300")

    # 创业板
    cy_df = _fetch_index_data("sz399006", days=120)
    _calc_broad(cy_df, "sz399006")

    result["generated_at"] = datetime.now().isoformat()

    _save_cache(result)
    print(f"[strategy_engine] Signals computed for {len(result)} indices")
    return result


def signals_summary(signals: dict) -> str:
    """生成信号摘要文本，供 LLM 使用"""
    lines = []
    for k, v in signals.items():
        if not isinstance(v, dict):
            continue
        name = v.get("name", k)
        close = v.get("latest_close", "--")
        ma_s = v.get("ma_status", "--")
        vol = v.get("volatility_60d", "--")
        mom = v.get("momentum_1m", "--")
        rsrs = v.get("rsrs_status", "--")
        lines.append(
            f"{name} 收盘{close} | MA:{ma_s} | 1月动量{mom}% | 波动率{vol}% | RSRS:{rsrs}"
        )
    return "\n".join(lines)
