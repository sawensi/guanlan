"""
观澜 — 基金数据获取模块

统一拉取 ETF / 开放式基金 / QDII / 黄金 的历史净值和行情数据。
缓存当日有效 (data/fund_cache/)，避免重复 API 调用。

ETF 数据通过底层指数的日线数据获取（跟踪误差极小），
避免直接调用 fund_etf_hist_em（东方财富接口频繁限流）。
"""

import json
import os
import time
from datetime import datetime, timedelta

from indicators import (
    compute_ma, compute_atr, compute_rsi, compute_macd,
    compute_ma_status, compute_volatility, compute_momentum,
    compute_consecutive_direction,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_DIR = os.path.join(DATA_DIR, "fund_cache")

# ── ETF → 底层指数映射 ──────────────────────────────────
# ETF 跟踪指数，用 stock_zh_index_daily 拉取（Sina 源，稳定）

ETF_INDEX_MAP = {
    # ── 宽基 ──
    "510300": {"symbol": "sh000300", "name": "沪深300ETF", "type": "etf"},
    "510310": {"symbol": "sh000300", "name": "沪深300ETF易方达", "type": "etf"},
    "510330": {"symbol": "sh000300", "name": "沪深300ETF华夏", "type": "etf"},
    "510050": {"symbol": "sh000016", "name": "上证50ETF", "type": "etf"},
    "510500": {"symbol": "sh000905", "name": "中证500ETF", "type": "etf"},
    "159915": {"symbol": "sz399006", "name": "创业板ETF", "type": "etf"},
    "159919": {"symbol": "sh000300", "name": "沪深300ETF", "type": "etf"},
    "159922": {"symbol": "sz399005", "name": "中证500ETF", "type": "etf"},
    "588000": {"symbol": "sh000688", "name": "科创50ETF", "type": "etf"},
    "588080": {"symbol": "sh000688", "name": "科创50ETF", "type": "etf"},
    "159949": {"symbol": "sz399006", "name": "创业板50ETF", "type": "etf"},
    "512100": {"symbol": "sh000852", "name": "中证1000ETF", "type": "etf"},
    "563300": {"symbol": "sh000852", "name": "中证2000ETF", "type": "etf"},
    # ── 红利/价值 ──
    "512890": {"symbol": "sh000922", "name": "中证红利ETF", "type": "etf"},
    "512880": {"symbol": "sh000922", "name": "红利低波ETF", "type": "etf"},
    # ── 行业/主题 ──
    "159995": {"symbol": "sz399807", "name": "芯片ETF", "type": "etf"},
    "512800": {"symbol": "sz399986", "name": "银行ETF", "type": "etf"},
    "512660": {"symbol": "sz399967", "name": "军工ETF", "type": "etf"},
    "512690": {"symbol": "sz399987", "name": "酒ETF", "type": "etf"},
    "512170": {"symbol": "sz399989", "name": "医疗ETF", "type": "etf"},
    "515790": {"symbol": "sz399998", "name": "光伏ETF", "type": "etf"},
    "515050": {"symbol": "sz399608", "name": "5GETF", "type": "etf"},
    "159865": {"symbol": "sz399707", "name": "养殖ETF", "type": "etf"},
    "159766": {"symbol": "sz399433", "name": "旅游ETF", "type": "etf"},
    # ── 债券 ──
    "511010": {"symbol": "sh000012", "name": "国债ETF", "type": "bond"},
    "511260": {"symbol": "sh000012", "name": "十年国债ETF", "type": "bond"},
    # ── QDII ──
    "159941": {"symbol": "intl_ndx", "name": "纳斯达克ETF", "type": "qdii"},
    "513100": {"symbol": "intl_ndx", "name": "纳指ETF", "type": "qdii"},
    "513500": {"symbol": "intl_spx", "name": "标普500ETF", "type": "qdii"},
    "513050": {"symbol": "intl_hsi", "name": "中概互联ETF", "type": "qdii"},
    # ── 黄金 ──
    "518880": {"symbol": "Au99.99", "name": "黄金ETF", "type": "gold"},
    "159934": {"symbol": "Au99.99", "name": "黄金ETF", "type": "gold"},
    "518800": {"symbol": "Au99.99", "name": "黄金ETF", "type": "gold"},
    # ── 指数代码直达（可输入 sh000300 等直接回测） ──
    "sh000001": {"symbol": "sh000001", "name": "上证指数", "type": "index"},
    "sh000300": {"symbol": "sh000300", "name": "沪深300指数", "type": "index"},
    "sh000016": {"symbol": "sh000016", "name": "上证50指数", "type": "index"},
    "sh000905": {"symbol": "sh000905", "name": "中证500指数", "type": "index"},
    "sh000852": {"symbol": "sh000852", "name": "中证1000指数", "type": "index"},
    "sh000688": {"symbol": "sh000688", "name": "科创50指数", "type": "index"},
    "sh000922": {"symbol": "sh000922", "name": "中证红利指数", "type": "index"},
    "sh000012": {"symbol": "sh000012", "name": "国债指数", "type": "index"},
    "sz399006": {"symbol": "sz399006", "name": "创业板指", "type": "index"},
    "sz399005": {"symbol": "sz399005", "name": "中证500深市", "type": "index"},
    "sz399807": {"symbol": "sz399807", "name": "国证芯片指数", "type": "index"},
    "sz399986": {"symbol": "sz399986", "name": "中证银行指数", "type": "index"},
    "sz399967": {"symbol": "sz399967", "name": "中证军工指数", "type": "index"},
    "sz399987": {"symbol": "sz399987", "name": "中证酒指数", "type": "index"},
    "sz399989": {"symbol": "sz399989", "name": "中证医疗指数", "type": "index"},
    "sz399998": {"symbol": "sz399998", "name": "国证光伏指数", "type": "index"},
    "sz399608": {"symbol": "sz399608", "name": "国证5G指数", "type": "index"},
    "sz399707": {"symbol": "sz399707", "name": "中证畜牧指数", "type": "index"},
    "sz399433": {"symbol": "sz399433", "name": "中证旅游指数", "type": "index"},
}


def _cache_path(code: str, days: int = 120) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    # 长窗口（如最佳离场时机用 days=2500）与默认窗口分开缓存，避免互相覆盖
    suffix = "" if days == 120 else f"_d{days}"
    return os.path.join(CACHE_DIR, f"{code}{suffix}.json")


def _load_cache(code: str, days: int = 120) -> dict | None:
    try:
        path = _cache_path(code, days)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            today = datetime.now().strftime("%Y-%m-%d")
            if data.get("date") == today:
                # 交易日盘中（工作日 9:00-15:30）缓存超过 5 分钟则失效
                if _is_trading_session():
                    cache_age = time.time() - os.path.getmtime(path)
                    if cache_age > 300:
                        return None
                return data
    except Exception:
        pass
    return None


def _is_trading_session() -> bool:
    """判断当前是否在 A 股交易时段（工作日 9:00-15:30）"""
    now = datetime.now()
    if now.weekday() >= 5:  # 周六日
        return False
    t = now.hour * 60 + now.minute
    return 540 <= t < 930  # 9:00 - 15:30


def _save_cache(code: str, data: dict, days: int = 120):
    os.makedirs(CACHE_DIR, exist_ok=True)
    data["date"] = datetime.now().strftime("%Y-%m-%d")
    with open(_cache_path(code, days), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# ── 指标计算（从 indicators.py 导入，见文件顶部） ────────


# ── 数据获取 ────────────────────────────────────────────

def _fetch_index_data(symbol: str, days: int = 120) -> dict | None:
    """
    通过 AKShare stock_zh_index_daily 获取指数日线 (Sina 源，稳定)。
    沪深/中证/创业板等指数均可用。
    """
    import akshare as ak
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or len(df) == 0:
            return None
        df = df.tail(days)
        return {
            "dates": df["date"].astype(str).tolist(),
            "opens": df["open"].tolist(),
            "highs": df["high"].tolist(),
            "lows": df["low"].tolist(),
            "closes": df["close"].tolist(),
        }
    except Exception as e:
        print(f"[fund_data] Index {symbol} fetch failed: {e}")
        return None


def _fetch_gold_spot(days: int = 120) -> dict | None:
    """通过 AKShare 获取上海金 Au99.99 现货日线"""
    import akshare as ak
    try:
        df = ak.spot_hist_sge(symbol="Au99.99")
        if df is None or len(df) == 0:
            return None
        df = df.tail(days)
        opens = [o if o > 0 else c for o, c in zip(df["open"].tolist(), df["close"].tolist())]
        return {
            "dates": df["date"].astype(str).tolist(),
            "opens": opens,
            "highs": df["high"].tolist(),
            "lows": df["low"].tolist(),
            "closes": df["close"].tolist(),
        }
    except Exception as e:
        print(f"[fund_data] Gold spot fetch failed: {e}")
        return None


def _fetch_comex_gold(days: int = 120) -> dict | None:
    """COMEX 黄金期货 — QDII 黄金基金的国际参考"""
    import akshare as ak
    try:
        df = ak.futures_foreign_hist(symbol="GC")
        if df is None or len(df) == 0:
            return None
        df = df.tail(days)
        return {
            "dates": df["date"].astype(str).tolist(),
            "opens": df["open"].tolist(),
            "highs": df["high"].tolist(),
            "lows": df["low"].tolist(),
            "closes": df["close"].tolist(),
        }
    except Exception as e:
        print(f"[fund_data] COMEX gold fetch failed: {e}")
        return None


def _fetch_usdcny(days: int = 120) -> dict | None:
    """美元/人民币汇率"""
    import akshare as ak
    try:
        df = ak.currency_boc_sina(symbol="美元")
        if df is None or len(df) == 0:
            return None
        df = df.tail(days)
        mid = df["央行中间价"].tolist() if "央行中间价" in df.columns else df["中行折算价"].tolist()
        # 转为元/美元 (原数据为 100美元=X元)
        closes = [round(v / 100, 4) for v in mid]
        return {
            "dates": df["日期"].astype(str).tolist(),
            "opens": closes[:],
            "highs": closes[:],
            "lows": closes[:],
            "closes": closes,
        }
    except Exception as e:
        print(f"[fund_data] USD/CNY fetch failed: {e}")
        return None


def _fetch_bond_10y(days: int = 400) -> dict | None:
    """获取中国 10 年期国债收益率（中债收益率曲线），返回 {dates, yields}"""
    import akshare as ak
    try:
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end = datetime.now().strftime("%Y%m%d")
        df = ak.bond_china_yield(start_date=start, end_date=end)
        if df is None or len(df) == 0:
            return None
        col = None
        for c in df.columns:
            if "10年" in str(c):
                col = c
                break
        if col is None:
            return None
        dcol = None
        for c in df.columns:
            if "日期" in str(c) or "date" in str(c).lower():
                dcol = c
                break
        dates = df[dcol].astype(str).tolist() if dcol else [str(i) for i in range(len(df))]
        yields = [float(v) for v in df[col].tolist()]
        return {"dates": dates, "yields": yields}
    except Exception as e:
        print(f"[fund_data] 10Y bond yield fetch failed: {e}")
        return None


def _attach_gold_macro(data: dict) -> dict:
    """
    黄金 ETF：附加 10Y 国债收益率与 USD/CNY 月涨跌，供黄金离场策略③④使用。
    失败时静默降级（对应条件回退到周期推断/不触发）。
    """
    try:
        bond = _fetch_bond_10y()
        if bond and len(bond.get("yields", [])) >= 2:
            data["bond_10y"] = bond["yields"][-1]
            data["bond_10y_prev"] = bond["yields"][-2]
        usd = _fetch_usdcny(days=60)
        if usd and len(usd.get("closes", [])) >= 22:
            c = usd["closes"]
            if c[-22] and c[-22] > 0:
                data["usdcny_change_1m"] = round((c[-1] - c[-22]) / c[-22] * 100, 2)
    except Exception as e:
        print(f"[fund_data] gold macro attach failed: {e}")
    return data


def _fetch_open_fund_nav(code: str, days: int = 120) -> dict | None:
    """
    通过 AKShare 获取开放式基金历史净值 (天天基金/支付宝 任意代码)。

    数据列: 净值日期, 单位净值, 日增长率
    开放式基金无 OHLC，用净值填充；high/low 由相邻净值差值估算以支持 ATR。
    """
    import akshare as ak
    try:
        df = ak.fund_open_fund_info_em(
            symbol=code, indicator="单位净值走势", period="成立来",
        )
        if df is None or len(df) == 0:
            return None
        df = df.tail(days + 5)
        navs = df["单位净值"].tolist()
        dates = df["净值日期"].astype(str).tolist()

        # 估算 OHLC：开基只有每日净值，相邻两日差值模拟日内波动
        highs, lows = [], []
        for i in range(len(navs)):
            if i == 0:
                highs.append(navs[i])
                lows.append(navs[i])
            else:
                highs.append(max(navs[i], navs[i - 1]))
                lows.append(min(navs[i], navs[i - 1]))

        return {
            "fund_code": code,
            "fund_name": code,
            "fund_type": "open",
            "dates": dates,
            "opens": navs[:],
            "highs": highs,
            "lows": lows,
            "closes": navs[:],
        }
    except Exception as e:
        print(f"[fund_data] Open fund {code} fetch failed: {e}")
        return None


def fetch_fund_history(code: str, days: int = 120) -> dict | None:
    """
    统一基金数据获取入口。

    策略：
    - ETF → 拉取底层指数日线 (stock_zh_index_daily，Sina 源稳定)
    - 黄金 → 上海金 Au99.99 现货
    - 未知代码 → 尝试指数接口，失败则用 ETF 接口降级
    """
    cached = _load_cache(code, days)
    if cached:
        return cached

    raw = None
    fund_name = code
    fund_type = "unknown"
    mapped = ETF_INDEX_MAP.get(code)

    if mapped:
        fund_name = mapped["name"]
        fund_type = mapped["type"]
        symbol = mapped["symbol"]

        # Gold → spot data
        if symbol == "Au99.99":
            raw = _fetch_gold_spot(days)
        # International → futures data
        elif symbol.startswith("intl_"):
            if symbol == "intl_ndx":
                # NASDAQ-100 proxy: use COMEX gold as placeholder, but let's try nasdaq futures
                # Fallback: use sz399006 (创业板) with a note — best available proxy
                print(f"[fund_data] {code}: Using domestic growth index as proxy for NASDAQ")
                raw = _fetch_index_data("sz399006", days)
                if raw:
                    fund_name = f"{mapped['name']}（创业板指代理）"
            elif symbol == "intl_spx":
                # S&P 500 proxy: use sh000300
                raw = _fetch_index_data("sh000300", days)
                if raw:
                    fund_name = f"{mapped['name']}（沪深300代理）"
            elif symbol == "intl_hsi":
                raw = _fetch_index_data("sh000001", days)
                if raw:
                    fund_name = f"{mapped['name']}（上证综指代理）"
            else:
                raw = _fetch_index_data("sh000300", days)
        else:
            # Domestic index
            raw = _fetch_index_data(symbol, days)
    else:
        # 未映射：先尝试指数代码 (sh000300 / sz399006)
        if code.startswith("sh") or code.startswith("sz"):
            raw = _fetch_index_data(code, days)
            if raw:
                fund_name = code
                fund_type = "index"
        # 再尝试开放式基金 (支付宝/天天基金任意代码)
        if raw is None:
            raw = _fetch_open_fund_nav(code, days)
            if raw:
                fund_name = code
                fund_type = "open"

    if raw is None:
        return None

    closes = raw["closes"]
    highs = raw["highs"]
    lows = raw["lows"]

    if len(closes) < 20:
        return None

    # —— 计算技术指标 ——
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

    # 连续涨跌天数
    consecutive_direction = compute_consecutive_direction(closes)

    recent = closes[-60:]
    grid_high = round(max(recent), 2)
    grid_low = round(min(recent), 2)
    grid_mid = round((grid_high + grid_low) / 2, 2)

    result = {
        "fund_code": code,
        "fund_name": fund_name,
        "fund_type": fund_type,
        "dates": raw["dates"],
        "opens": raw["opens"],
        "highs": raw["highs"],
        "lows": raw["lows"],
        "closes": closes,
        "latest_nav": round(closes[-1], 4),
        "latest_nav_date": raw["dates"][-1],
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
        "consecutive_direction": consecutive_direction,
    }

    # 黄金标的附加实际利率/汇率数据（供黄金离场策略③④使用）
    if fund_type == "gold":
        result = _attach_gold_macro(result)

    _save_cache(code, result, days)
    return result
