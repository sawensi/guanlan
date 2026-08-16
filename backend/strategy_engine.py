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

from indicators import (
    compute_ma, compute_ma_status, compute_rsrs, compute_atr, compute_rsi,
    compute_macd, compute_volatility, compute_momentum,
)

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

        # 全部指标复用 indicators.py 单源实现（避免与回测引擎口径漂移）
        ma20 = compute_ma(closes, 20)
        ma60 = compute_ma(closes, 60)
        ma_status = compute_ma_status(ma20, ma60)
        vol = compute_volatility(closes, 60)

        recent_closes = closes[-60:]
        grid_high = round(max(recent_closes), 2)
        grid_low = round(min(recent_closes), 2)
        grid_mid = round((grid_high + grid_low) / 2, 2)

        mom_1m = compute_momentum(closes, 21)
        mom_3m = compute_momentum(closes, 63)
        rsrs = compute_rsrs(highs, lows, window=18)
        atr14 = compute_atr(highs, lows, closes, 14)
        rsi14 = compute_rsi(closes, 14)
        macd = compute_macd(closes)

        result[label] = {
            "name": INDEX_CONFIG.get(label, {}).get("name", label),
            "latest_close": round(closes[-1], 2),
            "ma20": round(ma20[-1], 2) if ma20[-1] is not None else None,
            "ma60": round(ma60[-1], 2) if ma60[-1] is not None else None,
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
            "macd": macd["macd"],
            "macd_signal": macd["signal"],
            "macd_hist": macd["hist"],
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
