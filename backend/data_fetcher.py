"""
观澜 — 国家统计局宏观数据获取模块

数据源:
1. chinadata.live 免费 REST API
2. 国家统计局 easyquery API (官方)
3. 财新 PMI (独立第三方对照)
4. 内置默认值 (兜底)

改版亮点:
- chinadata 和 NBS 并行请求 (不再串行回退)
- 双源交叉验证 (差异>10%标记conflict)
- 每项指标标注来源
"""

import json
import os
import asyncio
import httpx
from datetime import datetime, timedelta
from models import IndicatorData

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_FILE = os.path.join(DATA_DIR, "macro_cache.json")

# ── 指标定义 ──────────────────────────────────────────
INDICATOR_DEFS = [
    {"name": "CPI 同比",   "code": "cpi",       "unit": "%", "category": "inflation"},
    {"name": "PPI 同比",   "code": "ppi",       "unit": "%", "category": "inflation"},
    {"name": "PMI 制造业", "code": "pmi",       "unit": "%", "category": "growth"},
    {"name": "M2 同比",    "code": "m2",        "unit": "%", "category": "inflation"},
    {"name": "GDP 增速",   "code": "gdp",       "unit": "%", "category": "growth"},
    {"name": "社零增速",   "code": "retail",    "unit": "%", "category": "growth"},
    {"name": "固投增速",   "code": "fai",       "unit": "%", "category": "growth"},
    {"name": "失业率",     "code": "unemploy",  "unit": "%", "category": "growth"},
    {"name": "财新PMI 制造业", "code": "caixin_pmi", "unit": "%", "category": "growth"},
]

# ── chinadata.live API ────────────────────────────────
CHINADATA_BASE = "https://chinadata.live/api/v2/data"

CHINADATA_MAP = {
    "cpi":       "/cpi",
    "ppi":       "/ppi",
    "pmi":       "/pmi",
    "m2":        "/m2",
    "gdp":       "/gdp",
    "retail":    "/total_retail_sales",
    "fai":       "/fixed_asset_investment",
    "unemploy":  "/unemployment",
}


async def fetch_chinadata() -> dict[str, float]:
    """从 chinadata.live 获取数据"""
    results = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for code, path in CHINADATA_MAP.items():
            try:
                resp = await client.get(f"{CHINADATA_BASE}{path}")
                if resp.status_code == 200:
                    data = resp.json()
                    value = _parse_chinadata(data, code)
                    if value is not None:
                        results[code] = value
            except Exception:
                continue
    return results


def _parse_chinadata(data, code: str) -> float | None:
    """解析 chinadata.live 返回数据"""
    try:
        if isinstance(data, dict):
            records = data.get("data", data.get("records", []))
        elif isinstance(data, list):
            records = data
        else:
            return None

        if not records:
            return None

        sorted_records = sorted(
            records,
            key=lambda r: str(r.get("date", r.get("year", ""))),
            reverse=True,
        )
        latest = sorted_records[0]

        value_fields = ["value", "cpi", "ppi", "pmi", "m2", "gdp",
                        "growth", "rate", "total_retail_sales"]
        for field in value_fields:
            if field in latest and latest[field] is not None:
                return float(latest[field])
        return None
    except Exception:
        return None


# ── 国家统计局 easyquery API ───────────────────────────

NBS_BASE = "https://data.stats.gov.cn/easyquery.htm"

NBS_INDICATORS = {
    "cpi":       {"db": "hgyd", "code": "A01010G"},
    "ppi":       {"db": "hgyd", "code": "A0102"},
    "pmi":       {"db": "hgyd", "code": "A0B01"},
    "m2":        {"db": "hgyd", "code": "A0D01"},
    "gdp":       {"db": "hgjd", "code": "A0201"},
    "retail":    {"db": "hgyd", "code": "A0701"},
    "fai":       {"db": "hgyd", "code": "A0401"},
    "unemploy":  {"db": "hgyd", "code": "A0E01"},
}


async def fetch_nbs() -> dict[str, float]:
    """从国家统计局 easyquery API 获取数据"""
    results = {}
    now = datetime.now()
    end_month = f"{now.year}{now.month:02d}"
    start_month = f"{now.year - 1}{now.month:02d}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        for code, info in NBS_INDICATORS.items():
            try:
                params = {
                    "m": "QueryData",
                    "dbcode": info["db"],
                    "rowcode": "zb",
                    "colcode": "sj",
                    "wds": "[]",
                    "dfwds": json.dumps([
                        {"wdcode": "zb", "valuecode": info["code"]},
                        {"wdcode": "sj", "valuecode": f"{start_month}-{end_month}"},
                    ]),
                }
                resp = await client.get(NBS_BASE, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    value = _parse_nbs(data)
                    if value is not None:
                        results[code] = value
            except Exception:
                continue
    return results


def _parse_nbs(data) -> float | None:
    """解析 NBS API 返回数据"""
    try:
        records = data.get("returndata", {}).get("datanodes", [])
        if not records:
            return None
        latest = records[-1]
        val = latest.get("data", {}).get("strdata", "")
        if val:
            return float(val)
        return None
    except Exception:
        return None


# ── 财新 PMI (独立第三方对照) ──────────────────────────

async def fetch_caixin_pmi() -> float | None:
    """获取财新制造业 PMI，作为官方 PMI 的独立交叉验证"""
    import akshare as ak
    try:
        df = await asyncio.to_thread(ak.index_pmi_man_cx)
        if df is None or len(df) == 0:
            return None
        latest = df.iloc[-1]
        val = latest.get("制造业PMI")
        return float(val) if val is not None else None
    except Exception as e:
        print(f"[data_fetcher] Caixin PMI fetch failed: {e}")
        return None


# ── 默认兜底数据 ──────────────────────────────────────
DEFAULT_INDICATORS = {
    "cpi":       0.1,
    "ppi":      -2.2,
    "pmi":      50.1,
    "m2":        7.0,
    "gdp":       5.2,
    "retail":    4.7,
    "fai":       4.2,
    "unemploy":  5.1,
}


# ── 缓存 ──────────────────────────────────────────────

def load_cache() -> dict | None:
    """读取本地缓存 (兼容新旧格式)"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
                cache_date = cache.get("date", "")
                today = datetime.now().strftime("%Y-%m-%d")
                if cache_date == today:
                    return cache
        except Exception:
            pass
    return None


def save_cache(indicators: dict[str, float], metadata: dict = None) -> None:
    """保存到本地缓存 (新格式含 source_metadata)"""
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "indicators": indicators,
        "source_metadata": metadata or {},
    }
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── AKShare 宏观数据 (第三数据源) ─────────────────────

async def _fetch_akshare_macro() -> dict[str, float]:
    """用 AKShare 东方财富宏观接口作为第三数据源"""
    import akshare as ak
    results = {}
    try:
        # CPI
        df = await asyncio.to_thread(ak.macro_china_cpi_yearly)
        if df is not None and len(df) > 0:
            latest = df.dropna(subset=["今值"]).tail(1)
            if len(latest) > 0:
                val = latest.iloc[-1].get("今值")
                if val is not None and not (isinstance(val, float) and (val != val)):
                    results["cpi"] = float(val)
    except Exception:
        pass

    try:
        # PMI
        df = await asyncio.to_thread(ak.macro_china_pmi)
        if df is not None and len(df) > 0:
            latest = df.tail(1)
            if len(latest) > 0:
                val = latest.iloc[-1].get("制造业-指数")
                if val is not None:
                    results["pmi"] = float(val)
    except Exception:
        pass

    try:
        # M2
        df = await asyncio.to_thread(ak.macro_china_m2_yearly)
        if df is not None and len(df) > 0:
            latest = df.dropna(subset=["今值"]).tail(1)
            if len(latest) > 0:
                val = latest.iloc[-1].get("今值")
                if val is not None and not (isinstance(val, float) and (val != val)):
                    results["m2"] = float(val)
    except Exception:
        pass

    try:
        # GDP
        df = await asyncio.to_thread(ak.macro_china_gdp_yearly)
        if df is not None and len(df) > 0:
            latest = df.dropna(subset=["今值"]).tail(1)
            if len(latest) > 0:
                val = latest.iloc[-1].get("今值")
                if val is not None and not (isinstance(val, float) and (val != val)):
                    results["gdp"] = float(val)
    except Exception:
        pass

    if results:
        print(f"[data_fetcher] AKShare macro got {len(results)} indicators: {list(results.keys())}")
    return results


# ── 主入口 ─────────────────────────────────────────────

async def fetch_all_indicators(force: bool = False) -> tuple[list[IndicatorData], dict]:
    """
    获取所有宏观指标 (并行双源 + 交叉验证)

    返回:
        (indicators_list, source_metadata)

    source_metadata: {code: {source, data_date, conflict, chinadata_value, nbs_value}}
    """
    # 1. 优先读缓存（同时保存旧值用于趋势对比）
    old_indicators = {}
    if not force:
        cache = load_cache()
        if cache:
            raw = cache["indicators"]
            meta = cache.get("source_metadata", {})
            return _build_indicator_list(raw, meta, old_indicators), meta
    else:
        # force=True 时也加载旧缓存用于趋势计算
        old_cache = load_cache()
        if old_cache:
            old_indicators = old_cache.get("indicators", {})

    # 2. 并行请求: chinadata + NBS + Caixin PMI
    chinadata_task = fetch_chinadata()
    nbs_task = fetch_nbs()
    caixin_task = fetch_caixin_pmi()
    akshare_task = _fetch_akshare_macro()

    chinadata_results, nbs_results, caixin_value, akshare_results = await asyncio.gather(
        chinadata_task, nbs_task, caixin_task, akshare_task,
        return_exceptions=True,
    )

    if isinstance(chinadata_results, Exception):
        print(f"[data_fetcher] chinadata.live failed: {chinadata_results}")
        chinadata_results = {}
    if isinstance(nbs_results, Exception):
        print(f"[data_fetcher] NBS failed: {nbs_results}")
        nbs_results = {}
    if isinstance(caixin_value, Exception):
        print(f"[data_fetcher] Caixin PMI failed: {caixin_value}")
        caixin_value = None
    if isinstance(akshare_results, Exception):
        print(f"[data_fetcher] AKShare macro failed: {akshare_results}")
        akshare_results = {}

    # 3. 合并 + 交叉验证 + 来源标注
    indicators = {}
    source_metadata = {}
    conflict_count = 0
    default_count = 0

    for defn in INDICATOR_DEFS:
        code = defn["code"]

        # Caixin PMI 独立处理（不与 chinadata/NBS 冲突检测）
        if code == "caixin_pmi":
            if caixin_value is not None:
                indicators[code] = caixin_value
                source_metadata[code] = {
                    "source": "caixin",
                    "data_date": "",
                    "conflict": False,
                    "chinadata_value": None,
                    "nbs_value": None,
                }
            continue

        val_cd = chinadata_results.get(code)
        val_nbs = nbs_results.get(code)

        # 冲突检测：双源都有值时差异 > 10%
        conflict = False
        if val_cd is not None and val_nbs is not None:
            avg = (abs(val_cd) + abs(val_nbs)) / 2
            if avg > 0 and abs(val_cd - val_nbs) / avg > 0.10:
                conflict = True
                conflict_count += 1

        # 优先级: chinadata → NBS → akshare → default
        val_ak = (akshare_results or {}).get(code)
        if val_cd is not None:
            indicators[code] = val_cd
            source = "chinadata"
        elif val_nbs is not None:
            indicators[code] = val_nbs
            source = "nbs"
        elif val_ak is not None:
            indicators[code] = val_ak
            source = "akshare"
        else:
            indicators[code] = DEFAULT_INDICATORS.get(code, 0)
            source = "default"
            default_count += 1

        source_metadata[code] = {
            "source": source,
            "data_date": "",
            "conflict": conflict,
            "chinadata_value": val_cd,
            "nbs_value": val_nbs,
        }

    # 4. 缓存
    save_cache(indicators, source_metadata)

    sources_used = set(m["source"] for m in source_metadata.values())
    print(f"[data_fetcher] Sources: {', '.join(sorted(sources_used))} | "
          f"defaults: {default_count} | conflicts: {conflict_count} | "
          f"coverage: {len(indicators)}/{len(INDICATOR_DEFS)}")

    return _build_indicator_list(indicators, source_metadata, old_indicators), source_metadata


def _build_indicator_list(
    raw: dict[str, float],
    metadata: dict = None,
    old_indicators: dict[str, float] = None,
) -> list[IndicatorData]:
    """将原始数据字典转换为 IndicatorData 列表"""
    now = datetime.now().strftime("%Y-%m")
    if old_indicators is None:
        old_indicators = {}

    # 基准值（用于判断指标方向：高于/低于正常水平）
    from cycle_analyzer import BASELINE

    result = []
    for defn in INDICATOR_DEFS:
        code = defn["code"]
        value = raw.get(code)
        if value is None:
            continue

        # 趋势计算：优先用旧值对比，无旧值时用基线判断方向
        trend = "flat"
        prev = old_indicators.get(code)
        if prev is not None and prev != 0 and value != prev:
            trend = "up" if value > prev else "down"
        else:
            # 无历史对比时：高于基线=扩张/偏高，低于基线=收缩/偏低
            bl = BASELINE.get(code)
            if bl:
                if value > bl["mean"] + bl["std"] * 0.3:
                    trend = "up"
                elif value < bl["mean"] - bl["std"] * 0.3:
                    trend = "down"

        meta = (metadata or {}).get(code, {})

        result.append(IndicatorData(
            name=defn["name"],
            code=code,
            value=round(value, 2),
            unit=defn["unit"],
            trend=trend,
            date=now,
            source=meta.get("source", ""),
            data_date=meta.get("data_date", ""),
            conflict=meta.get("conflict", False),
        ))
    return result


# ── 沪深300 PE 历史数据 ──────────────────────────────

CSI300_PE_CACHE = os.path.join(DATA_DIR, "csi300_pe_cache.json")


def _load_csi300_pe_cache() -> list[dict] | None:
    """加载 PE 缓存（当日有效）"""
    try:
        if os.path.exists(CSI300_PE_CACHE):
            with open(CSI300_PE_CACHE) as f:
                cache = json.load(f)
                cache_date = cache.get("date", "")
                today = datetime.now().strftime("%Y-%m-%d")
                if cache_date == today:
                    return cache.get("data", [])
    except Exception:
        pass
    return None


def _save_csi300_pe_cache(data: list[dict]) -> None:
    """保存 PE 缓存"""
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "data": data,
    }
    with open(CSI300_PE_CACHE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


async def fetch_csi300_pe_history(force: bool = False) -> list[dict]:
    """
    获取沪深300近3年滚动市盈率(PE TTM)月度历史数据。

    数据源: akshare stock_index_pe_lg (乐股网)
    返回: [{"date": "2024-01", "pe": 12.5}, ...] 约36条月度数据
    失败时返回空列表，不抛异常。
    """
    # 优先读缓存
    if not force:
        cached = _load_csi300_pe_cache()
        if cached is not None:
            return cached

    try:
        import akshare as ak
        import pandas as pd

        df = await asyncio.to_thread(ak.stock_index_pe_lg, symbol="沪深300")
        if df is None or len(df) == 0:
            print("[data_fetcher] CSI300 PE: empty DataFrame from akshare")
            return []

        # 日期解析 + 排序
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.set_index("日期").sort_index()

        # 取近3年，月度重采样取月末滚动市盈率
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=3)
        recent = df[df.index >= cutoff]
        if recent.empty:
            print("[data_fetcher] CSI300 PE: no data in last 3 years")
            return []

        monthly = recent["滚动市盈率"].resample("ME").last().dropna()

        result = [
            {"date": d.strftime("%Y-%m"), "pe": round(float(v), 2)}
            for d, v in monthly.items()
        ]

        _save_csi300_pe_cache(result)
        print(f"[data_fetcher] CSI300 PE: {len(result)} monthly points "
              f"({result[0]['date']} ~ {result[-1]['date']})")
        return result

    except Exception as e:
        print(f"[data_fetcher] CSI300 PE fetch failed (non-fatal): {e}")
        return []


# ── 沪深300 估值温度计 ───────────────────────────────

VALUATION_CACHE = os.path.join(DATA_DIR, "csi300_valuation_cache.json")


def _load_valuation_cache() -> dict | None:
    """加载估值缓存（当日有效）"""
    try:
        if os.path.exists(VALUATION_CACHE):
            with open(VALUATION_CACHE) as f:
                cache = json.load(f)
                cache_date = cache.get("date", "")
                today = datetime.now().strftime("%Y-%m-%d")
                if cache_date == today:
                    return cache.get("data")
    except Exception:
        pass
    return None


def _save_valuation_cache(data: dict) -> None:
    """保存估值缓存"""
    os.makedirs(DATA_DIR, exist_ok=True)
    cache = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "data": data,
    }
    with open(VALUATION_CACHE, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


async def fetch_csi300_valuation(force: bool = False) -> dict | None:
    """
    获取沪深300估值温度计数据: PE/PB分位 + ERP(股债性价比)

    返回: {pe, pe_percentile, pb, pb_percentile, erp, bond_10y, signal, data_date}
    失败时返回 None。
    """
    if not force:
        cached = _load_valuation_cache()
        if cached is not None:
            return cached

    try:
        import akshare as ak
        import pandas as pd

        # 并行获取 PE、PB、国债收益率
        pe_task = asyncio.to_thread(ak.stock_index_pe_lg, symbol="沪深300")
        pb_task = asyncio.to_thread(ak.stock_index_pb_lg, symbol="沪深300")
        bond_task = asyncio.to_thread(ak.bond_zh_us_rate)

        pe_df, pb_df, bond_df = await asyncio.gather(
            pe_task, pb_task, bond_task, return_exceptions=True
        )

        # ── PE 分位 ──
        pe = 0.0
        pe_pct = 0.0
        if not isinstance(pe_df, Exception) and pe_df is not None and len(pe_df) > 0:
            pe_df["日期"] = pd.to_datetime(pe_df["日期"])
            pe_df = pe_df.set_index("日期").sort_index()
            cutoff = pd.Timestamp.now() - pd.DateOffset(years=10)
            pe_10y = pe_df[pe_df.index >= cutoff]["滚动市盈率"].dropna()
            if len(pe_10y) > 0:
                pe = round(float(pe_10y.iloc[-1]), 2)
                pe_pct = round(float((pe_10y < pe).mean()), 4)

        # ── PB 分位 ──
        pb = 0.0
        pb_pct = 0.0
        if isinstance(pb_df, Exception) or pb_df is None or len(pb_df) == 0:
            # 重试一次（AKShare 并发时偶发内部错误）
            print(f"[data_fetcher] PB fetch retrying...")
            await asyncio.sleep(3)
            try:
                pb_df = await asyncio.to_thread(ak.stock_index_pb_lg, symbol="沪深300")
            except Exception:
                pb_df = None
        if not isinstance(pb_df, Exception) and pb_df is not None and len(pb_df) > 0:
            try:
                pb_df["日期"] = pd.to_datetime(pb_df["日期"])
                pb_df = pb_df.set_index("日期").sort_index()
                cutoff = pd.Timestamp.now() - pd.DateOffset(years=10)
                pb_10y = pb_df[pb_df.index >= cutoff]["市净率"].dropna()
                if len(pb_10y) > 0:
                    pb = round(float(pb_10y.iloc[-1]), 2)
                    pb_pct = round(float((pb_10y < pb).mean()), 4)
            except Exception:
                pass  # PB 获取偶发失败，非关键指标

        # ── 10Y 国债收益率 ──
        bond_10y = 0.0
        if not isinstance(bond_df, Exception) and bond_df is not None and len(bond_df) > 0:
            bond_10y_raw = bond_df["中国国债收益率10年"].dropna()
            if len(bond_10y_raw) > 0:
                bond_10y = round(float(bond_10y_raw.iloc[-1]), 2)

        # ── ERP ──
        erp = 0.0
        if pe > 0 and bond_10y > 0:
            erp = round(100.0 / pe - bond_10y, 2)

        # ── 仓位信号 ──
        if erp > 5.5:
            signal = "超配"
        elif erp < 2.5:
            signal = "低配"
        else:
            signal = "正常"

        data_date = datetime.now().strftime("%Y-%m-%d")
        result = {
            "pe": pe, "pe_percentile": pe_pct,
            "pb": pb, "pb_percentile": pb_pct,
            "erp": erp, "bond_10y": bond_10y,
            "signal": signal, "data_date": data_date,
        }

        _save_valuation_cache(result)
        print(f"[data_fetcher] CSI300 Valuation: PE={pe}(Pct={pe_pct*100:.0f}%) "
              f"PB={pb}(Pct={pb_pct*100:.0f}%) ERP={erp}% → {signal}")
        return result

    except Exception as e:
        print(f"[data_fetcher] CSI300 valuation fetch failed (non-fatal): {e}")
        return None
