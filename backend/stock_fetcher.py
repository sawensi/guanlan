"""
观澜 — 股票排名抓取模块

数据源:
- Sina 新浪财经 (stock_zh_a_spot): 价格 + 代码 + 名称
- 东方财富 datacenter (stock_yjbb_em): 财务数据（增长率、毛利率、净利率、每股净资产、每股收益）

PB = 最新价 / 每股净资产
PE = 最新价 / 每股收益

筛选: 市净率 < 2
综合评分: 主营增长率 25% + 主营利润率 20% + 净利润率 25% + 低PE 20% + 低PB 10%
取 Top 50, JSON 缓存, 当日有效
"""

import os
import json
import asyncio
from datetime import datetime


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_FILE = os.path.join(DATA_DIR, "stock_rankings_cache.json")


# ── 缓存 ──────────────────────────────────────────────────

def _load_cache() -> dict | None:
    """加载缓存, 仅当日有效"""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
        if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
            return data
    except Exception:
        pass
    return None


def _save_cache(data: dict) -> None:
    """保存缓存到磁盘"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# ── 价格数据抓取 (Sina 新浪财经) ──────────────────────────

async def _fetch_price_data_sina() -> tuple[list[dict], str]:
    """
    从 Sina 新浪财经获取全 A 股价数据
    返回: (data_list, error_msg)
      - 成功: ([...], "")
      - 失败: ([], "具体错误原因")
    使用 asyncio.to_thread 避免同步 requests 阻塞事件循环
    """
    import time

    last_error = ""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            # ★ 在独立线程中执行同步的 AKShare 调用, 避免阻塞 uvicorn 事件循环
            df = await asyncio.to_thread(_call_sina_spot)
            if df is None or len(df) == 0:
                msg = f"Sina 新浪财经返回空数据 (第{attempt+1}次)"
                print(f"[stock_fetcher] {msg}")
                last_error = msg
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                return [], last_error

            results = []
            for _, row in df.iterrows():
                try:
                    raw_code = str(row.get("代码", "")).strip()
                    name = str(row.get("名称", "")).strip()
                    price_val = row.get("最新价")

                    if not raw_code or not name:
                        continue

                    # Sina 代码格式: sh600000 / sz000001 / bj920000
                    # 提取纯数字代码
                    if len(raw_code) > 2 and raw_code[:2] in ("sh", "sz", "bj"):
                        code = raw_code[2:]
                    else:
                        code = raw_code

                    try:
                        price = float(price_val) if price_val is not None else None
                    except (ValueError, TypeError):
                        price = None

                    if price is None or price <= 0:
                        continue

                    results.append({
                        "code": code,
                        "name": name,
                        "price": round(price, 4),
                    })
                except Exception:
                    continue

            print(f"[stock_fetcher] Sina: got {len(results)} stocks with price data")
            return results, ""

        except Exception as e:
            msg = f"Sina 新浪财经接口异常: {type(e).__name__}"
            print(f"[stock_fetcher] {msg} (attempt {attempt+1}): {e}")
            last_error = msg
            if attempt < max_retries - 1:
                await asyncio.sleep(5)

    return [], last_error


def _call_sina_spot():
    """同步调用 AKShare Sina 接口 (在独立线程中运行)"""
    import akshare as ak
    return ak.stock_zh_a_spot()


# ── 数据日期自动探测 ──────────────────────────────────────

def _detect_latest_data_date() -> str:
    """自动探测最新的财务数据日期，避免硬编码过期

    至少需要 1000 只股票有财报数据才认为该日期"可用"。
    全 A 股正常报告期有 5000+ 只，报告初期（如 Q2 刚结束）仅零星披露，
    阈值 1000 足以过滤掉这类不完全数据。
    """
    import akshare as ak
    from datetime import datetime

    MIN_STOCKS = 1000  # 最少需要多少只股票有数据

    now = datetime.now()
    candidates = []
    if now.month >= 7:
        candidates.append(f"{now.year}0630")
    candidates.append(f"{now.year}0331")
    candidates.append(f"{now.year - 1}1231")
    candidates.append(f"{now.year - 1}0930")
    candidates.append(f"{now.year - 1}0630")
    candidates.append(f"{now.year - 1}0331")
    candidates.append(f"{now.year - 2}1231")

    for date_str in candidates:
        try:
            df = ak.stock_yjbb_em(date=date_str)
            if df is not None and len(df) >= MIN_STOCKS:
                print(f"[stock_fetcher] Auto-detected data date: {date_str} "
                      f"({len(df)} stocks)")
                return date_str
            elif df is not None:
                print(f"[stock_fetcher] Skipping {date_str}: only {len(df)} stocks "
                      f"(need >= {MIN_STOCKS})")
        except Exception as e:
            print(f"[stock_fetcher] Probing {date_str} failed: {e}")
            continue
    print(f"[stock_fetcher] WARNING: No date with >= {MIN_STOCKS} stocks found, "
          f"falling back to {candidates[0]}")
    return candidates[0]


_LATEST_DATA_DATE = None

def _get_data_date() -> str:
    global _LATEST_DATA_DATE
    if _LATEST_DATA_DATE is None:
        _LATEST_DATA_DATE = _detect_latest_data_date()
    return _LATEST_DATA_DATE


def _ttm_component_dates(date_str: str) -> tuple[str, str]:
    """由报告期(YYYYMMDD)推导 TTM 需要的两个历史日期: 上年年报 + 上年同期"""
    y = int(date_str[:4])
    mmdd = date_str[4:]
    return f"{y - 1}1231", f"{y - 1}{mmdd}"


# ── 财务数据抓取 (东方财富 datacenter) ───────────────────

async def _fetch_financial_data_batch() -> dict[str, dict]:
    """
    批量获取财务指标: 主营增长率、毛利率、净利率、每股净资产、每股收益
    使用 AKShare 的 stock_yjbb_em (业绩报表, datacenter-web.eastmoney.com)
    在独立线程中执行以避免阻塞事件循环
    """
    import akshare as ak

    results: dict[str, dict] = {}

    try:
        # ★ 在独立线程中执行同步 AKShare 调用
        df = await asyncio.to_thread(ak.stock_yjbb_em, date=_get_data_date())
        if df is None or len(df) == 0:
            print("[stock_fetcher] yjbb_em returned empty")
            return results

        # TTM 组件：上年年报 + 上年同期累计每股收益（失败不阻断，PE 退化为累计口径）
        prev_annual_date, prev_period_date = _ttm_component_dates(_get_data_date())
        eps_prev_annual: dict[str, float] = {}
        eps_prev_period: dict[str, float] = {}
        for d, target in ((prev_annual_date, eps_prev_annual),
                          (prev_period_date, eps_prev_period)):
            try:
                pdf = await asyncio.to_thread(ak.stock_yjbb_em, date=d)
                if pdf is None or len(pdf) == 0:
                    continue
                for _, prow in pdf.iterrows():
                    pcode = str(prow.get("股票代码", "")).strip()
                    pv = prow.get("每股收益")
                    if pcode and pv is not None and str(pv) != "nan":
                        try:
                            target[pcode] = float(pv)
                        except (ValueError, TypeError):
                            pass
            except Exception as e:
                print(f"[stock_fetcher] TTM component {d} fetch failed: {e}")

        for _, row in df.iterrows():
            try:
                code = str(row.get("股票代码", "")).strip()
                if not code:
                    continue

                # 主营增长率: 营业总收入-同比增长
                revenue_growth = None
                val = row.get("营业总收入-同比增长")
                if val is not None and str(val) != "nan":
                    try:
                        revenue_growth = round(float(val), 2)
                    except (ValueError, TypeError):
                        pass

                # 主营利润率: 销售毛利率
                gross_margin = None
                val = row.get("销售毛利率")
                if val is not None and str(val) != "nan":
                    try:
                        gross_margin = round(float(val), 2)
                    except (ValueError, TypeError):
                        pass

                # 净利润率: 从 净利润/营业总收入 计算
                net_margin = None
                net_profit = row.get("净利润-净利润")
                revenue = row.get("营业总收入-营业总收入")
                if (net_profit is not None and str(net_profit) != "nan"
                        and revenue is not None and str(revenue) != "nan"):
                    try:
                        np_val = float(net_profit)
                        rev_val = float(revenue)
                        if rev_val > 0:
                            net_margin = round(np_val / rev_val * 100, 2)
                    except (ValueError, TypeError):
                        pass

                # 每股净资产 (用于计算 PB)
                book_value = None
                bv_val = row.get("每股净资产")
                if bv_val is not None and str(bv_val) != "nan":
                    try:
                        book_value = float(bv_val)
                        if book_value <= 0:
                            book_value = None
                    except (ValueError, TypeError):
                        pass

                # 每股收益 (累计口径，用于计算 PE-TTM 与财务健康度)
                eps = None
                eps_cum = None
                eps_val = row.get("每股收益")
                if eps_val is not None and str(eps_val) != "nan":
                    try:
                        eps_cum = float(eps_val)
                        if eps_cum > 0:
                            eps = eps_cum   # 亏损企业 PE 无意义，累计 eps 置 None
                    except (ValueError, TypeError):
                        pass

                # TTM 每股收益 = 当期累计 + 上年年报 - 上年同期累计
                # （报告期累计 EPS 直接算 PE 会系统性偏低，Q1/Q2/Q3 尤其严重）
                eps_ttm = None
                if eps_cum is not None:
                    pa = eps_prev_annual.get(code)
                    pp = eps_prev_period.get(code)
                    if pa is not None and pp is not None:
                        eps_ttm = round(eps_cum + pa - pp, 4)
                    else:
                        eps_ttm = round(eps_cum, 4)

                # 每股经营现金流量 (Operating CF per share) — 财务造假核心指标
                cfps = None
                cfps_val = row.get("每股经营现金流量")
                if cfps_val is not None and str(cfps_val) != "nan":
                    try:
                        cfps = float(cfps_val)
                    except (ValueError, TypeError):
                        pass

                # 净资产收益率 (ROE)
                roe = None
                roe_val = row.get("净资产收益率")
                if roe_val is not None and str(roe_val) != "nan":
                    try:
                        roe = float(roe_val)
                    except (ValueError, TypeError):
                        pass

                # 净利润-同比增长
                net_profit_growth = None
                npg_val = row.get("净利润-同比增长")
                if npg_val is not None and str(npg_val) != "nan":
                    try:
                        net_profit_growth = round(float(npg_val), 2)
                    except (ValueError, TypeError):
                        pass

                # 所处行业（申万分类）
                industry = str(row.get("所处行业", "")).strip()
                industry = industry if industry and industry != "nan" else None

                results[code] = {
                    "revenue_growth": revenue_growth,
                    "gross_margin": gross_margin,
                    "net_margin": net_margin,
                    "book_value": book_value,
                    "eps": eps,
                    "eps_ttm": eps_ttm,
                    "cfps": cfps,
                    "roe": roe,
                    "net_profit_growth": net_profit_growth,
                    "industry": industry,
                }

            except Exception:
                continue

        print(f"[stock_fetcher] Got financial data for {len(results)} stocks from yjbb_em")

    except Exception as e:
        print(f"[stock_fetcher] yjbb_em fetch failed: {e}")

    return results


# ── 现金流量表批量抓取 (东方财富 datacenter) ────────────

async def _fetch_cashflow_data_batch() -> dict[str, dict]:
    """
    批量获取现金流量表数据。
    使用 AKShare stock_xjll_em (全部A股，单次调用)。
    返回 {code: {operating_cf, investing_cf, financing_cf}}
    """
    import akshare as ak

    results: dict[str, dict] = {}

    try:
        df = await asyncio.to_thread(ak.stock_xjll_em, date=_get_data_date())
        if df is None:
            print(f"[stock_fetcher] xjll_em returned None for date={_get_data_date()}")
            return results
        if len(df) == 0:
            print("[stock_fetcher] xjll_em returned empty DataFrame")
            return results

        for _, row in df.iterrows():
            try:
                code = str(row.get("股票代码", "")).strip()
                if not code:
                    continue

                def _safe_float(val):
                    if val is not None and str(val) != "nan":
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            pass
                    return None

                results[code] = {
                    "operating_cf": _safe_float(row.get("经营性现金流-现金流量净额")),
                    "investing_cf": _safe_float(row.get("投资性现金流-现金流量净额")),
                    "financing_cf": _safe_float(row.get("融资性现金流-现金流量净额")),
                }

            except Exception:
                continue

        print(f"[stock_fetcher] Got cashflow data for {len(results)} stocks from xjll_em")

    except TypeError as e:
        print(f"[stock_fetcher] xjll_em fetch failed (TypeError, possibly bad date={_get_data_date()}): {e}")
    except Exception as e:
        print(f"[stock_fetcher] xjll_em fetch failed: {type(e).__name__}: {e}")

    return results


# ── 利润表批量抓取 (东方财富 datacenter) ─────────────────

async def _fetch_income_statement_batch() -> dict[str, dict]:
    """
    批量获取利润表数据。
    使用 AKShare stock_lrb_em (全部A股，单次调用)。
    返回 {code: {operating_profit, total_profit, net_profit_amount, ...}}
    """
    import akshare as ak

    results: dict[str, dict] = {}

    try:
        df = await asyncio.to_thread(ak.stock_lrb_em, date=_get_data_date())
        if df is None:
            print(f"[stock_fetcher] lrb_em returned None for date={_get_data_date()}")
            return results
        if len(df) == 0:
            print("[stock_fetcher] lrb_em returned empty DataFrame")
            return results

        for _, row in df.iterrows():
            try:
                code = str(row.get("股票代码", "")).strip()
                if not code:
                    continue

                def _safe_float(val):
                    if val is not None and str(val) != "nan":
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            pass
                    return None

                results[code] = {
                    "operating_profit": _safe_float(row.get("营业利润")),
                    "total_profit": _safe_float(row.get("利润总额")),
                    "net_profit_amount": _safe_float(row.get("净利润")),
                    "admin_expense": _safe_float(row.get("营业总支出-管理费用")),
                    "selling_expense": _safe_float(row.get("营业总支出-销售费用")),
                    "finance_expense": _safe_float(row.get("营业总支出-财务费用")),
                }

            except Exception:
                continue

        print(f"[stock_fetcher] Got income statement data for {len(results)} stocks from lrb_em")

    except TypeError as e:
        print(f"[stock_fetcher] lrb_em fetch failed (TypeError, possibly bad date={_get_data_date()}): {e}")
    except Exception as e:
        print(f"[stock_fetcher] lrb_em fetch failed: {type(e).__name__}: {e}")

    return results


# ── 板块封顶配置 ─────────────────────────────────────────

SECTOR_CAP = 3           # 单板块最多 3 只
FINANCIAL_CAP = 10       # 金融大类合计最多 10 只 (Top 50 时占比 20%)
FINANCIAL_SECTORS = {"银行Ⅱ", "证券Ⅱ", "保险Ⅱ", "多元金融"}

PB_MAX = 2.0             # 低PB池硬过滤阈值（可调；值越大纳入越多成长股）


def _calculate_financial_health(stock: dict, cashflows: dict = None, income_stmts: dict = None) -> tuple[float, list[str]]:
    """
    计算财务健康度评分，返回 (health_score, warning_flags)。

    health_score 范围 [0.30, 1.0]，作为 multiplier 乘到 composite_score 上。
    扣分维度：
    1. 经营现金流/每股收益比值 — 识别虚增利润（有利润无现金）
    2. ROE 极端值 — 异常高可能是财务操纵
    3. 利润增速 vs 营收增速偏离 — 利润增长远快于收入增长不自然
    """
    health = 1.0
    flags = []

    cfps = stock.get("cfps")
    eps = stock.get("eps")

    # --- 维度 1: 经营现金流质量 ---
    if cfps is not None and eps is not None and eps > 0:
        ocf_ratio = cfps / eps
        if ocf_ratio < 0:
            health -= 0.25
            flags.append(f"经营现金流为负(CFPS/EPS={ocf_ratio:.1f})")
        elif ocf_ratio < 0.3:
            health -= 0.15
            flags.append(f"经营现金流/净利润偏低({ocf_ratio:.1f})")
        elif ocf_ratio < 0.5:
            health -= 0.08
            flags.append(f"经营现金流/净利润偏弱({ocf_ratio:.1f})")

    # --- 维度 2: ROE 合理性 ---
    roe = stock.get("roe")
    if roe is not None:
        if roe > 50:
            health -= 0.10
            flags.append(f"ROE异常高({roe:.1f}%)")
        elif roe < -20:
            health -= 0.10
            flags.append(f"ROE严重亏损({roe:.1f}%)")

    # --- 维度 3: 利润增速 vs 营收增速偏离 ---
    rev_g = stock.get("revenue_growth")
    np_g = stock.get("net_profit_growth")
    if rev_g is not None and np_g is not None:
        div = np_g - rev_g
        if div > 30:
            health -= 0.12
            flags.append(f"利润增速远超营收(差{div:.0f}pp)")
        elif div > 20:
            health -= 0.06
            flags.append(f"利润增速显著超营收(差{div:.0f}pp)")

    # --- 维度 4: 营业利润 vs 利润总额 ---
    # 非经常性收益检测：营业利润/利润总额偏低说明利润主要来自一次性收益
    code = stock.get("code", "")
    if income_stmts and code in income_stmts:
        inc = income_stmts[code]
        op_profit = inc.get("operating_profit")
        total_profit = inc.get("total_profit")
        if op_profit is not None and total_profit is not None and total_profit > 0:
            ratio = op_profit / total_profit
            if ratio < 0.3:
                health -= 0.15
                flags.append(f"营业利润/利润总额极低({ratio:.1%})")
            elif ratio < 0.5:
                health -= 0.08
                flags.append(f"非经常性收益占比偏高({ratio:.1%})")
            elif ratio > 1.2:
                health -= 0.05
                flags.append(f"非经常性亏损拖累利润({ratio:.1%})")

    # --- 维度 5: 应计项目占比 ---
    # (净利润 - 经营CF) / |净利润| 过高说明盈利质量差
    if cashflows and income_stmts and code in cashflows and code in income_stmts:
        cf = cashflows[code]
        inc = income_stmts[code]
        op_cf = cf.get("operating_cf")
        np_amt = inc.get("net_profit_amount")
        if op_cf is not None and np_amt is not None and abs(np_amt) > 0:
            accrual_ratio = (np_amt - op_cf) / abs(np_amt)
            if accrual_ratio > 0.8:
                health -= 0.10
                flags.append(f"应计项目占比过高({accrual_ratio:.1%})")

    health = max(0.30, health)
    return round(health, 4), flags


def _select_top_n_with_diversity(scored: list[dict], n: int = 50) -> list[dict]:
    """
    按评分顺序选取 Top N，同时保证板块多样性:

    - 每个板块最多 SECTOR_CAP 只
    - 金融大类（银行/证券/保险/多元金融）合计最多 FINANCIAL_CAP 只
    - 如果封顶后不足 N 只，二轮无封顶补充
    """
    selected = []
    sector_counts: dict[str, int] = {}
    financial_count = 0

    for s in scored:
        if len(selected) >= n:
            break
        sector = s.get("sector") or "未知"

        # 单板块封顶
        if sector_counts.get(sector, 0) >= SECTOR_CAP:
            continue
        # 金融大类合计封顶
        if sector in FINANCIAL_SECTORS and financial_count >= FINANCIAL_CAP:
            continue

        selected.append(s)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if sector in FINANCIAL_SECTORS:
            financial_count += 1

    # 如果封顶后仍不足 N 只，二轮无封顶补充
    if len(selected) < n:
        selected_codes = {s["code"] for s in selected}
        for s in scored:
            if len(selected) >= n:
                break
            if s["code"] not in selected_codes:
                selected.append(s)

    return selected


# ── 评分算法 ────────────────────────────────────────────

def _percentile_rank(values: list[float], higher_is_better: bool = True) -> list[float]:
    """
    计算百分位排名, 返回 [0, 1] 的归一化分数
    - higher_is_better=True: 值越大分越高 (如增长率)
    - higher_is_better=False: 值越小分越高 (如 PE、PB)
    """
    if not values:
        return []

    n = len(values)
    sorted_idx = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    for rank_pos, idx in enumerate(sorted_idx):
        ranks[idx] = rank_pos / max(n - 1, 1)

    if not higher_is_better:
        ranks = [1.0 - r for r in ranks]

    return ranks


def _score_and_rank(stocks: list[dict], cashflows: dict = None, income_stmts: dict = None,
                    weights: list[float] = None) -> list[dict]:
    """
    对股票做综合评分, 返回按 composite_score 降序排列的列表

    权重默认: 主营增长率 25% + 主营利润率 20% + 净利润率 25% + 低PE 20% + 低PB 10%
    可通过 weights 参数自定义 [w1, w2, w3, w4, w5]，自动归一化
    """
    if not stocks:
        return []

    # 自定义权重（归一化）
    if weights is None:
        weights = [0.25, 0.20, 0.25, 0.20, 0.10]
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    # 提取各指标到 list
    revenue_growth_vals = [s.get("revenue_growth") for s in stocks]
    gross_margin_vals   = [s.get("gross_margin") for s in stocks]
    net_margin_vals     = [s.get("net_margin") for s in stocks]
    pe_vals             = [s.get("pe") for s in stocks]
    pb_vals             = [s.get("pb") for s in stocks]

    def _safe_percentile(vals, higher_is_better):
        clean = [(i, v) for i, v in enumerate(vals) if v is not None]
        if not clean:
            return [None] * len(vals)
        indices, clean_vals = zip(*clean)
        clean_ranks = _percentile_rank(list(clean_vals), higher_is_better)
        result = [None] * len(vals)
        for idx, rank in zip(indices, clean_ranks):
            result[idx] = rank
        return result

    pgrow  = _safe_percentile(revenue_growth_vals, higher_is_better=True)
    pgross = _safe_percentile(gross_margin_vals, higher_is_better=True)
    pnet   = _safe_percentile(net_margin_vals, higher_is_better=True)
    # PE 特殊处理：亏损股(eps<=0) PE 无意义 → 记 0 分（最差）；真缺失 → 0.5 中性；有值 → 分位
    pe_valid_idx = [i for i, v in enumerate(pe_vals) if v is not None]
    pe_clean_ranks = _percentile_rank([pe_vals[i] for i in pe_valid_idx],
                                      higher_is_better=False) if pe_valid_idx else []
    ppe = [None] * len(stocks)
    for pos, idx in enumerate(pe_valid_idx):
        ppe[idx] = pe_clean_ranks[pos]
    for i, s in enumerate(stocks):
        if ppe[i] is None:
            eps_ttm = s.get("eps_ttm")
            if eps_ttm is not None and eps_ttm <= 0:
                ppe[i] = 0.0   # 亏损股：低PE因子给最差分
            else:
                ppe[i] = 0.5   # 数据缺失：中性分
    ppb    = _safe_percentile(pb_vals, higher_is_better=False)

    scored = []
    for i, s in enumerate(stocks):
        ranks = [pgrow[i], pgross[i], pnet[i], ppe[i], ppb[i]]
        missing_count = sum(1 for r in ranks if r is None)
        if missing_count > 2:
            continue

        composite = sum(
            (rank if rank is not None else 0.5) * w
            for rank, w in zip(ranks, weights)
        )

        s["composite_score"] = round(composite, 4)

        health, flags = _calculate_financial_health(s, cashflows, income_stmts)
        s["financial_health"] = health
        s["health_flags"] = flags
        s["adjusted_score"] = round(composite * health, 4)

        scored.append(s)

    scored.sort(key=lambda x: x.get("adjusted_score", x.get("composite_score", 0)), reverse=True)
    return scored


# ── 日期格式化 ───────────────────────────────────────────

def _data_date_to_period(date_str: str) -> str:
    """20260331 → 2026Q1, 20251231 → 2025Q4"""
    y = date_str[:4]
    m = date_str[4:6]
    q_map = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}
    return y + q_map.get(m, "")


# ── ST/*ST 过滤 ─────────────────────────────────────────

async def _fetch_st_stocks() -> set[str]:
    """获取所有 ST/*ST 股票代码（需排除）"""
    import akshare as ak
    try:
        df = await asyncio.to_thread(ak.stock_zh_a_st_em)
        if df is None or len(df) == 0:
            return set()
        st_codes = set()
        for _, row in df.iterrows():
            code = str(row.get("股票代码", "")).strip()
            if code:
                st_codes.add(code)
        print(f"[stock_fetcher] Excluding {len(st_codes)} ST/*ST stocks")
        return st_codes
    except Exception as e:
        print(f"[stock_fetcher] ST list fetch failed: {e}")
        return set()


# ── 国企/央企过滤 ─────────────────────────────────────

SOE_CACHE_FILE = os.path.join(DATA_DIR, "soe_blacklist_cache.json")
SOE_CACHE_MAX_AGE_HOURS = 168  # 7 天

_SOE_CONTROLLER_KEYWORDS = [
    # 国资直接标识
    "国资委", "国有资产", "国务院", "中央汇金",
    "财政部", "人民政府", "中投公司", "国有",
    # 央企集团通用前缀
    "中国", "国家",
    # 知名国资集团
    "招商局集团", "华润", "中信集团", "光大集团",
    # 科研院所
    "中国科学院", "中国工程院", "中国工程物理",
    # 地方政府平台
    "财政厅", "财政局", "公有资产", "交通运输厅",
    "国有资产经营", "开发区管理委员会", "管委会",
    "省国有资产", "市国有资产", "新区管委会",
]


def _is_soe_controller(controller_name: str) -> bool:
    """判断实际控制人名称是否属于国资背景"""
    if not controller_name or not isinstance(controller_name, str):
        return False
    name = controller_name.strip()
    for kw in _SOE_CONTROLLER_KEYWORDS:
        if kw in name:
            return True
    return False


def _load_soe_cache() -> set[str] | None:
    """加载 SOE 黑名单缓存（7 天有效），过期或损坏返回 None"""
    if not os.path.exists(SOE_CACHE_FILE):
        return None
    try:
        with open(SOE_CACHE_FILE) as f:
            data = json.load(f)
        gen_time = data.get("generated_at", "")
        if gen_time:
            gen_dt = datetime.fromisoformat(gen_time)
            age_hours = (datetime.now() - gen_dt).total_seconds() / 3600
            if age_hours < SOE_CACHE_MAX_AGE_HOURS:
                codes = set(data.get("soe_codes", []))
                print(f"[stock_fetcher] Loaded {len(codes)} SOE codes from cache "
                      f"({age_hours:.0f}h old)")
                return codes
        print(f"[stock_fetcher] SOE cache expired ({gen_time})")
    except Exception as e:
        print(f"[stock_fetcher] SOE cache load error: {e}")
    return None


def _save_soe_cache(soe_codes: set[str]) -> None:
    """保存 SOE 黑名单到磁盘"""
    os.makedirs(DATA_DIR, exist_ok=True)
    data = {
        "generated_at": datetime.now().isoformat(),
        "source": "stock_hold_control_cninfo",
        "total_soe": len(soe_codes),
        "soe_codes": sorted(list(soe_codes)),
    }
    with open(SOE_CACHE_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def _fetch_soe_blacklist(force: bool = False) -> set[str]:
    """
    获取国企/央企股票代码集合

    策略:
    1. 非强制刷新时优先读缓存
    2. 缓存缺失/过期 -> 批量调用 stock_hold_control_cninfo
    3. API 不可用 -> 返回空 set (pass-through, 不过滤)

    返回: 需要排除的股票代码 set
    """
    if not force:
        cached = _load_soe_cache()
        if cached is not None:
            return cached

    print("[stock_fetcher] Fetching fresh SOE blacklist...")

    try:
        import akshare as ak
        df = await asyncio.to_thread(ak.stock_hold_control_cninfo, symbol="全部")
        if df is None or len(df) == 0:
            print("[stock_fetcher] stock_hold_control_cninfo returned empty, "
                  "SOE filter disabled")
            return set()

        soe_codes = set()
        for _, row in df.iterrows():
            code = str(row.get("证券代码", "")).strip()
            controller = str(row.get("实际控制人名称", "")).strip()
            direct_ctrl = str(row.get("直接控制人名称", "")).strip()
            if code and (_is_soe_controller(controller) or _is_soe_controller(direct_ctrl)):
                soe_codes.add(code)

        print(f"[stock_fetcher] Identified {len(soe_codes)} SOE stocks "
              f"from {len(df)} total")
        _save_soe_cache(soe_codes)
        return soe_codes

    except AttributeError:
        print("[stock_fetcher] stock_hold_control_cninfo not available — "
              "upgrade akshare to >= 1.16.40 for SOE filtering")
        return set()

    except Exception as e:
        print(f"[stock_fetcher] SOE batch fetch failed: {type(e).__name__}: {e}")
        print("[stock_fetcher] SOE filter disabled (pass-through)")
        return set()


# ── 主入口 ─────────────────────────────────────────────

async def fetch_stock_rankings(force: bool = False) -> tuple[dict | None, str]:
    """
    获取股票排名

    参数:
        force: 是否强制刷新 (忽略当日缓存)

    返回:
        (data, error_msg)
        - 成功: (dict, "")
        - API失败: (None, "错误原因")  — 调用方应保留旧缓存
    """
    # 1. 尝试加载缓存
    if not force:
        cached = _load_cache()
        if cached:
            print(f"[stock_fetcher] Using cached rankings from {cached.get('date')}")
            return cached, ""

    print("[stock_fetcher] Fetching fresh stock data...")

    # 2-3.5 并行获取所有批量数据
    price_task = _fetch_price_data_sina()
    financials_task = _fetch_financial_data_batch()
    cashflow_task = _fetch_cashflow_data_batch()
    incomestmt_task = _fetch_income_statement_batch()
    st_task = _fetch_st_stocks()
    soe_task = _fetch_soe_blacklist(force=force)

    results = await asyncio.gather(
        price_task, financials_task, cashflow_task, incomestmt_task,
        st_task, soe_task,
        return_exceptions=True,
    )

    price_data, price_error = (
        results[0] if not isinstance(results[0], Exception) else ([], str(results[0]))
    )
    financials = results[1] if not isinstance(results[1], Exception) else {}
    cashflows = results[2] if not isinstance(results[2], Exception) else {}
    income_stmts = results[3] if not isinstance(results[3], Exception) else {}
    st_codes = results[4] if not isinstance(results[4], Exception) else set()
    soe_codes = results[5] if not isinstance(results[5], Exception) else set()

    if not price_data:
        error_msg = price_error or "未能获取股价数据"
        print(f"[stock_fetcher] No price data — {error_msg}, keeping old cache")
        return None, error_msg

    # 4. 合并价格和财务数据, 计算 PB/PE
    merged = []
    for s in price_data:
        code = s["code"]
        price = s["price"]

        fin = financials.get(code, {})

        # 计算 PB = 价格 / 每股净资产
        pb = None
        if fin.get("book_value") is not None and fin["book_value"] > 0:
            pb = round(price / fin["book_value"], 4)

        # 计算 PE-TTM = 价格 / 滚动12个月每股收益（避免累计口径低估 PE）
        pe = None
        eps_ttm = fin.get("eps_ttm")
        if eps_ttm is not None and eps_ttm > 0:
            pe = round(price / eps_ttm, 4)

        merged.append({
            "code": code,
            "name": s["name"],
            "price": price,
            "pb": pb,
            "pe": pe,
            "eps": fin.get("eps"),
            "eps_ttm": eps_ttm,
            "revenue_growth": fin.get("revenue_growth"),
            "gross_margin": fin.get("gross_margin"),
            "net_margin": fin.get("net_margin"),
            "cfps": fin.get("cfps"),
            "roe": fin.get("roe"),
            "net_profit_growth": fin.get("net_profit_growth"),
            "sector": fin.get("industry"),
        })

    print(f"[stock_fetcher] Merged: {len(merged)} stocks with price+financials")

    # 5. 过滤 PB < PB_MAX（默认 2.0，可调）
    filtered = [s for s in merged if s.get("pb") is not None and s["pb"] < PB_MAX]
    print(f"[stock_fetcher] PB < {PB_MAX} filter: {len(filtered)} / {len(merged)} stocks")

    if not filtered:
        # 防御性诊断: 可能是财报日期数据不完整导致 PB 无法计算
        with_book = sum(1 for s in merged if s.get("pb") is not None)
        print(f"[stock_fetcher] WARNING: 0 stocks pass PB<2 filter! "
              f"({with_book}/{len(merged)} have PB data, "
              f"data_date={_get_data_date()})")

    # 5.5 过滤 ST/*ST 股票
    if st_codes:
        before_st = len(filtered)
        filtered = [s for s in filtered if s["code"] not in st_codes]
        print(f"[stock_fetcher] ST filter: removed {before_st - len(filtered)}, {len(filtered)} remain")

    total_all = len(filtered)

    if not filtered:
        result = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_all": 0,
            "total_filtered": 0,
            "soe_excluded": len(soe_codes),
            "fin_excluded": 0,
            "rankings_all": [],
            "rankings": [],
            "generated_at": datetime.now().isoformat(),
        }
        _save_cache(result)
        return result, ""

    # 6. 评分 & 排名（在全量 PB<2+去ST 池上，不做国企/金融过滤）
    scored = _score_and_rank(filtered, cashflows, income_stmts)

    # 7. 全量 Top 50
    top_all = _select_top_n_with_diversity(scored)

    # 8. 过滤国企/央企 + 金融行业（在已评分列表上做，用于民企榜）
    fin_excluded = 0
    filtered_scored = scored
    if soe_codes:
        before_soe = len(filtered_scored)
        filtered_scored = [s for s in filtered_scored if s["code"] not in soe_codes]
        print(f"[stock_fetcher] SOE filter: removed {before_soe - len(filtered_scored)}, {len(filtered_scored)} remain")
    else:
        print("[stock_fetcher] SOE filter: no data, skipped")

    before_fin = len(filtered_scored)
    filtered_scored = [s for s in filtered_scored if s.get("sector") not in FINANCIAL_SECTORS]
    fin_excluded = before_fin - len(filtered_scored)
    print(f"[stock_fetcher] Financial filter: removed {fin_excluded}, {len(filtered_scored)} remain")

    # 9. 民企 Top 50
    top_civil = _select_top_n_with_diversity(filtered_scored) if filtered_scored else []

    # 10. 清理输出
    def _fmt(s):
        return {
            "code": s.get("code", ""),
            "name": s.get("name", ""),
            "pb": s.get("pb", 0),
            "pe": s.get("pe"),
            "eps_ttm": s.get("eps_ttm"),
            "revenue_growth": s.get("revenue_growth"),
            "gross_margin": s.get("gross_margin"),
            "net_margin": s.get("net_margin"),
            "composite_score": s.get("composite_score", 0),
            "adjusted_score": s.get("adjusted_score"),
            "financial_health": s.get("financial_health"),
            "health_flags": s.get("health_flags", []),
            "cfps": s.get("cfps"),
            "roe": s.get("roe"),
            "net_profit_growth": s.get("net_profit_growth"),
            "sector": s.get("sector"),
        }

    rankings_all = [_fmt(s) for s in top_all]
    rankings = [_fmt(s) for s in top_civil]

    # 保存全量评分数据用于后续换权重重排
    filtered_slim = []
    for s in scored:
        filtered_slim.append({
            "code": s.get("code", ""),
            "name": s.get("name", ""),
            "pb": s.get("pb"),
            "pe": s.get("pe"),
            "eps": s.get("eps"),
            "eps_ttm": s.get("eps_ttm"),
            "revenue_growth": s.get("revenue_growth"),
            "gross_margin": s.get("gross_margin"),
            "net_margin": s.get("net_margin"),
            "cfps": s.get("cfps"),
            "roe": s.get("roe"),
            "net_profit_growth": s.get("net_profit_growth"),
            "sector": s.get("sector"),
            "composite_score": s.get("composite_score"),
            "adjusted_score": s.get("adjusted_score"),
            "financial_health": s.get("financial_health"),
            "health_flags": s.get("health_flags", []),
        })

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_all": total_all,
        "total_filtered": len(filtered_scored),
        "soe_excluded": len(soe_codes),
        "fin_excluded": fin_excluded,
        "soe_codes": sorted(list(soe_codes)),
        "rankings_all": rankings_all,
        "rankings": rankings,
        "filtered_data": filtered_slim,
        "generated_at": datetime.now().isoformat(),
        "data_date": _get_data_date(),
        "data_period": _data_date_to_period(_get_data_date()),
    }

    # 9. 保存缓存
    _save_cache(result)

    print(f"[stock_fetcher] Rankings done. All: {len(rankings_all)}, Civil: {len(rankings)} from {total_all} scored stocks.")
    return result, ""


# ── 命令行测试 ─────────────────────────────────────────

if __name__ == "__main__":
    async def test():
        print("Testing stock_fetcher...")
        result, error = await fetch_stock_rankings(force=True)
        if result is None:
            print(f"FAILED: {error}")
            return
        print(f"\nDate: {result['date']}")
        print(f"Total filtered: {result['total_filtered']}")
        print(f"Top 50:")
        for i, s in enumerate(result["rankings"], 1):
            print(f"  {i:2d}. {s['code']} {s['name']}  "
                  f"PB={s['pb']:.2f}  PE={s.get('pe') or '--'}  "
                  f"Score={s['composite_score']:.3f}")

    asyncio.run(test())
