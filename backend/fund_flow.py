"""
观澜 — 资金流向模块

数据源:
- 同花顺 (THS) 行业资金流向: stock_fund_flow_industry
- 同花顺 (THS) 个股资金流向: stock_fund_flow_individual

图表:
1. 行业板块资金净流入 Top/Bottom 10 — 横向柱状图
2. 个股主力资金净流入 Top 10 — 主力资金去向
"""

import os
import json
import asyncio
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_FILE = os.path.join(DATA_DIR, "fund_flow_cache.json")


# ── 金额解析 ──────────────────────────────────────────

def _parse_amount(raw: str) -> float:
    """解析同花顺个股资金流金额字符串 → float (亿元)

    个股 API 返回带后缀的字符串:
    '7.04亿' → 7.04, '9600.47万' → 0.96, '-7200.36万' → -0.72
    无后缀的极小值(元): '9284.00' → 0.000093
    """
    if raw is None or not isinstance(raw, str):
        return 0.0
    raw = raw.strip()
    if not raw:
        return 0.0
    try:
        if raw.endswith("亿"):
            return float(raw[:-1])
        elif raw.endswith("万"):
            return round(float(raw[:-1]) / 10000, 6)
        else:
            # 无后缀 → 极小值，原始单位是"元"，转亿
            return round(float(raw) / 1e8, 6)
    except (ValueError, TypeError):
        return 0.0


def _parse_industry_amount(val) -> float:
    """解析行业资金流金额 → float (亿元)

    行业 API 返回无后缀的数值，单位已是亿:
    208.32 → 208.32, -156.71 → -156.71
    """
    if val is None:
        return 0.0
    try:
        raw = str(val).strip()
        if not raw or raw == "nan":
            return 0.0
        # 行业 API 数值无后缀，单位即亿
        if raw.endswith("亿"):
            return float(raw[:-1])
        elif raw.endswith("万"):
            return round(float(raw[:-1]) / 10000, 6)
        else:
            return round(float(raw), 2)
    except (ValueError, TypeError):
        return 0.0


# ── 缓存 ──────────────────────────────────────────────

def _load_cache() -> dict | None:
    """加载缓存，仅当日有效"""
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


# ── 行业资金流向 ──────────────────────────────────────

async def _fetch_industry_flow() -> list[dict]:
    """获取行业板块资金流向"""
    import akshare as ak

    try:
        df = await asyncio.to_thread(
            ak.stock_fund_flow_industry, symbol="即时"
        )
        if df is None or len(df) == 0:
            print("[fund_flow] Industry flow returned empty")
            return []

        results = []
        for _, row in df.iterrows():
            try:
                name = str(row.get("行业", "")).strip()
                if not name:
                    continue
                inflow = _parse_industry_amount(row.get("流入资金"))
                outflow = _parse_industry_amount(row.get("流出资金"))
                net = _parse_industry_amount(row.get("净额"))
                change_pct_str = str(row.get("行业-涨跌幅", "0")).replace("%", "")
                try:
                    change_pct = float(change_pct_str)
                except (ValueError, TypeError):
                    change_pct = 0.0

                results.append({
                    "name": name,
                    "inflow": round(inflow, 2),
                    "outflow": round(outflow, 2),
                    "net": round(net, 2),
                    "change_pct": round(change_pct, 2),
                    "company_count": int(row.get("公司家数", 0) or 0),
                })
            except Exception:
                continue

        print(f"[fund_flow] Got {len(results)} industry sectors")
        return results

    except Exception as e:
        print(f"[fund_flow] Industry flow fetch failed: {type(e).__name__}: {e}")
        return []


# ── 个股资金流向 ──────────────────────────────────────

async def _fetch_individual_flow() -> list[dict]:
    """获取个股资金流向排名（主力资金去向）"""
    import akshare as ak

    try:
        df = await asyncio.to_thread(
            ak.stock_fund_flow_individual, symbol="即时"
        )
        if df is None or len(df) == 0:
            print("[fund_flow] Individual flow returned empty")
            return []

        results = []
        for _, row in df.iterrows():
            try:
                code = str(row.get("股票代码", "")).strip()
                name = str(row.get("股票简称", "")).strip()
                if not code or not name:
                    continue

                price_str = str(row.get("最新价", "0"))
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    price = 0.0

                change_pct_str = str(row.get("涨跌幅", "0")).replace("%", "")
                try:
                    change_pct = float(change_pct_str)
                except (ValueError, TypeError):
                    change_pct = 0.0

                inflow = _parse_amount(str(row.get("流入资金", "0")))
                outflow = _parse_amount(str(row.get("流出资金", "0")))
                net = _parse_amount(str(row.get("净额", "0")))
                turnover = _parse_amount(str(row.get("成交额", "0")))

                results.append({
                    "code": code,
                    "name": name,
                    "price": round(price, 2),
                    "change_pct": round(change_pct, 2),
                    "inflow": round(inflow, 2),
                    "outflow": round(outflow, 2),
                    "net": round(net, 2),
                    "turnover": round(turnover, 2),
                })
            except Exception:
                continue

        print(f"[fund_flow] Got {len(results)} individual stocks")
        return results

    except Exception as e:
        print(f"[fund_flow] Individual flow fetch failed: {type(e).__name__}: {e}")
        return []


# ── 主入口 ────────────────────────────────────────────

async def fetch_fund_flow_data(force: bool = False) -> tuple[dict | None, str]:
    """
    获取资金流向数据

    参数:
        force: 是否强制刷新（忽略当日缓存）

    返回:
        (data, error_msg)
        - 成功: (dict, "")
        - 失败: (None, "错误原因")
    """
    # 1. 尝试加载缓存
    if not force:
        cached = _load_cache()
        if cached:
            print(f"[fund_flow] Using cached data from {cached.get('date')}")
            return cached, ""

    print("[fund_flow] Fetching fresh fund flow data...")

    # 2. 并行获取行业和个股数据
    industry_task = _fetch_industry_flow()
    individual_task = _fetch_individual_flow()

    industries, individuals = await asyncio.gather(
        industry_task, individual_task,
        return_exceptions=True,
    )

    if isinstance(industries, Exception):
        print(f"[fund_flow] Industry task exception: {industries}")
        industries = []
    if isinstance(individuals, Exception):
        print(f"[fund_flow] Individual task exception: {individuals}")
        individuals = []

    if not industries and not individuals:
        return None, "行业和个股资金流向数据均获取失败"

    # 3. 按净额排序
    industries.sort(key=lambda x: x["net"], reverse=True)
    individuals.sort(key=lambda x: x["net"], reverse=True)

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "industries": industries,
        "individuals": individuals,
        "generated_at": datetime.now().isoformat(),
    }

    # 4. 保存缓存
    _save_cache(result)

    top_industry = industries[0]["name"] if industries else "N/A"
    print(f"[fund_flow] Done. {len(industries)} industries, {len(individuals)} stocks. "
          f"Top sector: {top_industry}")

    return result, ""


# ── 命令行测试 ────────────────────────────────────────

if __name__ == "__main__":
    async def test():
        print("Testing fund_flow...")
        result, error = await fetch_fund_flow_data(force=True)
        if result is None:
            print(f"FAILED: {error}")
            return
        print(f"\nDate: {result['date']}")
        print(f"Industries: {len(result['industries'])}")
        print(f"Top 5 sector inflows:")
        for i, s in enumerate(result["industries"][:5], 1):
            print(f"  {i}. {s['name']}: net={s['net']:.2f}亿  inflow={s['inflow']:.2f}亿  outflow={s['outflow']:.2f}亿")
        print(f"\nTop 5 individual net flows:")
        for i, s in enumerate(result["individuals"][:5], 1):
            print(f"  {i}. {s['code']} {s['name']}: net={s['net']:.2f}亿  chg={s['change_pct']}%")

    asyncio.run(test())
