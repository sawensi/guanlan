"""
观澜 — 量化交易策略库 (人话版)

5 种参考性策略，用大白话解释。
注意: 仅供学习参考，不构成投资建议。
"""

from models import QuantStrategy, StrategySignal, CycleStage

STRATEGY_DEFS = [
    {
        "id": "merrill-rotation",
        "etf_category": "broad",
        "name": "经济周期轮动",
        "tagline": "经济好不好、物价涨不涨，决定了现在该买什么",
        "description": """
### 一句话解释

经济就像四季更替——有时候冷、有时候热。不同的季节穿不同的衣服，不同的经济阶段也应该配置不同的资产。

### 怎么用

每个月看两个关键问题：
1. **经济在加速还是减速？**（看 GDP、PMI 这些数据）
2. **物价在涨还是跌？**（看 CPI、PPI 这些数据）

根据答案分成四种情况：
- 🟢 **经济好转 + 物价温和** → 多买股票（企业赚钱了）
- 🟡 **经济好 + 物价涨得快** → 多买商品、黄金（通胀来了）
- 🔵 **经济不好 + 物价高** → 多留现金、黄金（保值为主）
- 🔴 **经济不好 + 物价低** → 多买债券（央行会降息）

### 具体买什么

直接用 ETF 就能实现：股票 ETF（如沪深300、创业板）、债券 ETF（如国债ETF）、商品 ETF、黄金 ETF。每月检查一次，切换到最适合当前阶段的品种。

### 风险提示

经济数据有滞后性，有时候等你看到数据，市场已经提前反应了。建议配合其他信号一起看。
""",
        "suitable_cycle": ["衰退期", "复苏期", "过热期", "滞胀期"],
        "rules": "每月初看经济数据 → 判断四个阶段 → 切换到对应 ETF",
        "frequency": "每月调一次",
        "risk_level": "中",
    },
    {
        "id": "dual-ma-trend",
        "etf_category": "broad",
        "name": "趋势跟踪",
        "tagline": "短期均线上穿长期均线就是上涨信号，跟着趋势走",
        "description": """
### 一句话解释

股价像海浪，有涨潮也有退潮。不用预测，只要识别出正在涨还是正在跌，跟着方向走就行。

### 怎么用

拿两条均线做比较：
- **短期线（20天平均价）**：反映最近动向
- **长期线（60天平均价）**：反映大方向

当短期线从下往上穿过长期线（金叉）→ **该买了，趋势向上**
当短期线从上往下穿过长期线（死叉）→ **该卖了，趋势向下**

### 加个过滤器

市场来回震荡的时候，均线会反复交叉，这种假信号要过滤掉。当每天的涨跌幅度太大（超过3%）时，先不急着做决定，观望一下。

### 适合谁

适合不想天天盯盘、抓大趋势的人。不适合窄幅震荡的行情（会被反复打脸）。用在沪深300、创业板这类趋势性强的指数上效果更好。
""",
        "suitable_cycle": ["复苏期", "过热期"],
        "rules": "短期线上穿长期线 → 买入；下穿 → 卖出；震荡剧烈时不动",
        "frequency": "每天看一次",
        "risk_level": "中",
    },
    {
        "id": "rsrs-momentum",
        "etf_category": "growth",
        "name": "涨跌力度比较",
        "tagline": "比较每天的上涨力度，力度增强就跟进，力度减弱就减仓",
        "description": """
### 一句话解释

不看价格高低，看涨跌的"力气"大不大。好比举重——不是看杠铃在什么位置，而是看举起来的速度和力道。

### 怎么用

每天记录两个数据：当日最高价、当日最低价。
然后把最近18天的数据放在一起，算一个叫"RSRS得分"的东西（压缩到 -1 ~ +1 之间）：
- **得分高（>0.4）**：说明每次跌下去都有人接盘，支撑很强 → **持有或买入**
- **得分低（≤0）**：说明涨上去就被打下来，阻力很大 → **减仓或观望**

### 多个品种比较

不只是看一个品种，而是同时看几个（比如沪深300、中证500、创业板），谁的RSRS得分最高就买谁。每周比较一次，换到最强的品种上。

### 背景

这个方法由光大证券研发，在中国市场回测效果不错——比单纯持有沪深300每年多赚5-8%，跌的时候也少亏一些。适合每周或每两周调一次仓。
""",
        "suitable_cycle": ["复苏期", "过热期", "衰退期"],
        "rules": "RSRS得分>0.4 → 买入；>0 → 持有；≤0 → 观望；买得分最高的品种",
        "frequency": "每周调一次",
        "risk_level": "中",
    },
    {
        "id": "grid-trading",
        "etf_category": "broad",
        "name": "网格自动买卖",
        "tagline": "设定价格上下限，跌了就买、涨了就卖，震荡市里来回赚差价",
        "description": """
### 一句话解释

把资金分成很多份，价格每跌一点就买一份，每涨一点就卖一份。不预测方向，就是来回赚差价。像在价格的地板上画了很多格子，所以叫"网格"。

### 怎么用

1. 先看最近60天价格在什么范围波动（比如10-12元之间）
2. 把这个范围分成10档（10、10.2、10.4……12）
3. 价格跌到某一档，自动买一份
4. 价格涨到某一档，自动卖一份
5. 突破范围上沿（>12元）→ 暂停卖出（可能要起飞了）
6. 跌破范围下沿（<10元）→ 暂停买入（可能还要跌）

### 什么时候好用

- ✅ 价格在一个区间内来回晃的时候（震荡市）
- ❌ 价格一路狂奔的时候（单边牛市你会卖飞，单边熊市你会抄底抄在半山腰）

### 注意事项

网格交易看起来简单，但需要**严格执行纪律**。震荡市赚的都是辛苦钱——每次只赚2-3%，但积少成多。如果遇到大单边行情，一定要及时暂停或调整网格区间。
""",
        "suitable_cycle": ["衰退期", "滞胀期"],
        "rules": "设定价格上下限 → 分10档 → 跌买涨卖 → 突破上下限则暂停",
        "frequency": "每天检查",
        "risk_level": "低",
    },
    {
        "id": "risk-parity",
        "etf_category": "broad",
        "name": "风险均衡配置",
        "tagline": "不押注单一品种，让每类资产承担差不多的风险，安稳赚长期收益",
        "description": """
### 一句话解释

传统的"各买三分之一"（股票、债券、黄金各33%）其实很不均衡——股票的波动比债券大得多，组合的风险几乎全来自股票。风险均衡的做法是：让每类资产贡献差不多大小的风险。

### 怎么用

选4-6种相关性低的资产（比如A股、国债、黄金、商品），然后：
1. 算出每种资产过去60天的波动程度（波动越大，仓位越小）
2. 按波动率倒数来分配——越稳定的资产买越多
3. 控制整个组合的波动率在8%左右（适合大多数人）
4. 每季度再平衡一次

### 具体例子

假设你有10万元：
- 国债波动小（5%）→ 分配最多，约4万
- 股票波动大（20%）→ 分配较少，约1万
- 黄金波动中等（12%）→ 分配中等，约1.7万
- 商品ETF波动中等（15%）→ 约1.3万
- 剩下的放货币基金

这样股票虽然仓位小，但波动大，对整体风险的贡献和国债差不多。

### 背景

桥水基金靠这个思路管理了上千亿美元，被称为"全天候策略"——在各种经济环境下都能存活。长期年化收益6-8%，最大回撤一般不超过12%，适合追求稳健的人。
""",
        "suitable_cycle": ["复苏期", "过热期", "衰退期", "滞胀期"],
        "rules": "选4-6种低相关资产 → 波动大的少买、波动小的多买 → 每季度调整",
        "frequency": "每季度调一次",
        "risk_level": "低",
    },
    {
        "id": "dividend-lowvol",
        "etf_category": "dividend",
        "name": "红利低波",
        "tagline": "买分红多、波动小的公司，稳稳吃股息，熊市更抗跌",
        "description": """
### 一句话解释

专挑那些分红大方、经营稳健、股价不折腾的公司。赚两份钱：每年拿分红（股息率 4-6%），长期股价也慢慢涨。

### 怎么用

选股标准很简单：
1. **连续 3 年以上分红** — 说明公司真赚钱（假账公司没钱分红）
2. **股息率 > 3%** — 比银行理财高
3. **波动率在同行业偏低** — 不追暴涨暴跌的妖股
4. **PB < 1.5** — 不要买太贵的

可以直接买中证红利 ETF（512890）或红利低波 ETF（512880），一键打包一篮子高股息公司。

### 为什么有效

- 熊市时，高股息提供"下跌保护"——就算股价跌，分红收益还在
- A股市场越来越重视分红，监管也在推动上市公司提高分红比例
- 历史回测：中证红利全收益指数长期跑赢沪深300约 2-3%/年

### 什么时候用

- ✅ 利率下行期（理财收益低，股息更有吸引力）
- ✅ 市场波动大（红利低波的防守属性突出）
- ✅ 经济不明朗（不管经济好坏，好公司都会分红）
- ❌ 大牛市（别人涨 50% 你只涨 20%，会焦虑）
""",
        "suitable_cycle": ["滞胀期", "衰退期", "复苏期"],
        "rules": "选连续分红+股息率>3%+低波动+PB<1.5 → 买红利ETF长期持有",
        "frequency": "每季度检视一次",
        "risk_level": "低",
    },
    {
        "id": "dca",
        "etf_category": "broad",
        "name": "定投策略",
        "tagline": "每月固定金额买入，不问涨跌，用时间换空间",
        "description": """
### 一句话解释

定投（定期定额投资）是最朴素的策略——每月固定拿出 X 元买指数基金，不择时、不猜方向、不看新闻。坚持 3-5 年，大概率赚钱。

### 怎么用

1. 选一个宽基指数：**沪深300**（代表大盘蓝筹）或**中证500**（代表中盘成长）
2. 每月固定日期（比如发工资后第 2 天），买入固定金额
3. 不管市场涨跌，雷打不动执行
4. 坚持至少 3 年，最好 5 年以上

### 为什么有效

- **低位多买**：跌的时候同样的钱买到更多份额
- **高位少买**：涨的时候同样的钱买到较少份额
- 长期来看，你的持仓成本接近市场平均价，而市场长期趋势是向上的

### 举个例子

假设每月投 2000 元买入沪深300 ETF：
- 第一个月价格 4 元 → 买 500 份
- 第二个月跌到 3.2 元 → 买 625 份（多买了 125 份！）
- 第三个月涨到 4.8 元 → 买 417 份

三个月总共 6000 元买了 1542 份，平均成本 3.89 元。如果一次性在第一个月买入，成本是 4 元。定投帮你把成本摊低了。

### 适用人群

- ✅ 有稳定月收入的上班族
- ✅ 不想花时间研究股票的"懒人投资者"
- ✅ 认同"长期持有好过频繁交易"理念的人
- 核心就一句话：**开始得早 + 坚持得久 > 择时精准**
""",
        "suitable_cycle": ["衰退期", "复苏期", "过热期", "滞胀期"],
        "rules": "每月固定金额买入沪深300或中证500ETF → 坚持3年以上 → 不择时不定量",
        "frequency": "每月执行一次",
        "risk_level": "低",
    },
]

# ── ETF 推荐 ─────────────────────────────────────────────

ETF_PICKS = {
    "broad":     [{"name": "沪深300ETF", "code": "510300"}, {"name": "中证500ETF", "code": "510500"}],
    "growth":    [{"name": "创业板ETF", "code": "159915"}, {"name": "科创50ETF", "code": "588000"}],
    "value":     [{"name": "上证50ETF", "code": "510050"}, {"name": "中证红利ETF", "code": "512890"}],
    "bond":      [{"name": "国债ETF", "code": "511010"}, {"name": "可转债ETF", "code": "511380"}],
    "gold":      [{"name": "黄金ETF", "code": "518880"}],
    "commodity": [{"name": "有色ETF", "code": "159980"}, {"name": "豆粕ETF", "code": "159985"}],
    "cash":      [{"name": "货币基金", "code": "511880"}, {"name": "逆回购", "code": "GC001"}],
    "dividend":  [{"name": "中证红利ETF", "code": "512890"}, {"name": "红利低波ETF", "code": "512880"}],
}

# ── 信号生成 ───────────────────────────────────────────

def _make_signal(sid: str, current_cycle: str, signals: dict = None) -> StrategySignal:
    """基于真实市场数据 + 经济周期生成信号。signals: strategy_engine.compute_all_signals()"""
    sh = (signals or {}).get("sh000001", {})
    hs300 = (signals or {}).get("sh000300", {})

    if sid == "merrill-rotation":
        return _signal_merrill(current_cycle, hs300)
    elif sid == "dual-ma-trend":
        return _signal_ma_trend(sh, hs300)
    elif sid == "rsrs-momentum":
        return _signal_rsrs(sh, hs300)
    elif sid == "grid-trading":
        return _signal_grid(sh, current_cycle)
    elif sid == "risk-parity":
        return _signal_risk_parity(sh, hs300, current_cycle)
    elif sid == "dividend-lowvol":
        return _signal_dividend(sh, current_cycle)
    elif sid == "dca":
        return _signal_dca(hs300)
    else:
        return StrategySignal(strategy_id=sid, strategy_name="",
                             signal="持有", confidence=0.50, reasoning="暂无数据")


def _signal_merrill(cycle: str, hs300: dict) -> StrategySignal:
    mom = hs300.get("momentum_1m")
    vol = hs300.get("volatility_60d")
    cycle_map = {
        "复苏期": ("买入", 0.82, "经济回暖 + 盈利改善，股票配置价值高", 1.5),
        "过热期": ("买入", 0.70, "通胀抬头，多配商品和周期股", 1.0),
        "滞胀期": ("卖出", 0.68, "增长放缓 + 通胀高企，减少风险资产", 0.5),
        "衰退期": ("持有", 0.75, "经济偏冷，债券和黄金是较好选择", 0.5),
    }
    sig, conf, reason, dca_mult = cycle_map.get(cycle, ("持有", 0.50, "", 1.0))
    if mom is not None:
        reason += f" | 沪深300近1月{mom:+.1f}%，波动率{vol}%"
    dca_reason = {"复苏期": "复苏期股票性价比高，本期可加码", "过热期": "过热期按计划定投即可",
                  "滞胀期": "滞胀期风险资产承压，本期减码", "衰退期": "衰退期少投股票，现金留待低位"}
    return StrategySignal(strategy_id="merrill-rotation", strategy_name="经济周期轮动",
                          signal=sig, confidence=conf, reasoning=reason,
                          dca_multiplier=dca_mult, dca_reason=dca_reason.get(cycle, "按计划定投"))


def _signal_ma_trend(sh: dict, hs300: dict) -> StrategySignal:
    ma_status = sh.get("ma_status", "未知")
    ma20 = sh.get("ma20")
    ma60 = sh.get("ma60")
    vol = sh.get("volatility_60d", 0) or 0
    if "金叉" in ma_status or ma_status == "多头排列":
        conf = 0.82 if "刚突破" in ma_status else 0.75
        return StrategySignal(strategy_id="dual-ma-trend", strategy_name="趋势跟踪",
            signal="买入", confidence=conf,
            reasoning=f"MA20({ma20}) > MA60({ma60})，{ma_status}，趋势向上",
            dca_multiplier=1.5, dca_reason="趋势向上，顺势加码定投")
    elif "死叉" in ma_status or ma_status == "空头排列":
        return StrategySignal(strategy_id="dual-ma-trend", strategy_name="趋势跟踪",
            signal="卖出", confidence=0.78,
            reasoning=f"MA20({ma20}) < MA60({ma60})，{ma_status}，趋势向下",
            dca_multiplier=0.5, dca_reason="趋势向下，本期减码等待企稳")
    else:
        return StrategySignal(strategy_id="dual-ma-trend", strategy_name="趋势跟踪",
            signal="观望", confidence=0.55, reasoning=f"均线方向不明确，建议观望",
            dca_multiplier=1.0, dca_reason="方向不明，按计划定投")


def _signal_rsrs(sh: dict, hs300: dict) -> StrategySignal:
    score = sh.get("rsrs_score")
    status = sh.get("rsrs_status", "")
    zscore = sh.get("rsrs_zscore")
    if score is None:
        return StrategySignal(strategy_id="rsrs-momentum", strategy_name="涨跌力度比较",
            signal="观望", confidence=0.50, reasoning="RSRS数据不足",
            dca_multiplier=1.0, dca_reason="数据不足，按计划定投")
    if score > 0.4:
        return StrategySignal(strategy_id="rsrs-momentum", strategy_name="涨跌力度比较",
            signal="买入", confidence=min(0.85, 0.6 + score * 0.3),
            reasoning=f"RSRS得分{score:.3f}，{status}，上涨力度强",
            dca_multiplier=1.5, dca_reason="上涨力度强，本期加码")
    elif score > 0:
        return StrategySignal(strategy_id="rsrs-momentum", strategy_name="涨跌力度比较",
            signal="持有", confidence=0.60, reasoning=f"RSRS得分{score:.3f}，{status}",
            dca_multiplier=1.0, dca_reason="力度中性，按计划定投")
    else:
        return StrategySignal(strategy_id="rsrs-momentum", strategy_name="涨跌力度比较",
            signal="观望", confidence=0.50, reasoning=f"RSRS得分{score:.3f}，{status}",
            dca_multiplier=0.5, dca_reason="上涨力度不足，本期减码观望")


def _signal_grid(sh: dict, cycle: str) -> StrategySignal:
    grid_h = sh.get("grid_high", 0)
    grid_l = sh.get("grid_low", 0)
    close = sh.get("latest_close", 0)
    ma = sh.get("ma_status", "")
    if "金叉" in ma:
        return StrategySignal(strategy_id="grid-trading", strategy_name="网格自动买卖",
            signal="观望", confidence=0.65, reasoning=f"趋势启动，不适合网格 | 区间{grid_l}-{grid_h}",
            dca_multiplier=1.0, dca_reason="趋势启动，按计划定投")
    pos = "偏低" if close < (grid_l + grid_h) * 0.45 else           "偏高" if close > (grid_l + grid_h) * 0.55 else "中间"
    # 定投档位：区间低位多投，高位少投（网格思想直接映射到定投档位）
    dca_mult = 1.5 if pos == "偏低" else (0.5 if pos == "偏高" else 1.0)
    dca_reason = f"当前处于60日区间{pos}位置" + ("，低位多攒份额" if pos == "偏低" else ("，高位少投" if pos == "偏高" else "，按计划定投"))
    return StrategySignal(strategy_id="grid-trading", strategy_name="网格自动买卖",
        signal="买入", confidence=0.68,
        reasoning=f"60日区间{grid_l}-{grid_h}，当前{close}处于{pos}位置，适合网格",
        dca_multiplier=dca_mult, dca_reason=dca_reason)


def _signal_risk_parity(sh: dict, hs300: dict, cycle: str) -> StrategySignal:
    vol = sh.get("volatility_60d", 15) or 15
    if vol > 25:
        return StrategySignal(strategy_id="risk-parity", strategy_name="风险均衡配置",
            signal="持有", confidence=0.82, reasoning=f"波动率偏高({vol}%)，均衡配置抗跌优势明显",
            dca_multiplier=1.0, dca_reason="高波动下按计划均衡定投")
    return StrategySignal(strategy_id="risk-parity", strategy_name="风险均衡配置",
        signal="持有", confidence=0.72, reasoning=f"当前波动率{vol}%，全天候配置在不同周期下均有表现",
        dca_multiplier=1.0, dca_reason="全天候配置，按计划定投")


def _signal_dividend(sh: dict, cycle: str) -> StrategySignal:
    vol = sh.get("volatility_60d", 15) or 15
    mom = sh.get("momentum_1m", 0) or 0
    if cycle in ("滞胀期", "衰退期"):
        return StrategySignal(strategy_id="dividend-lowvol", strategy_name="红利低波",
            signal="买入", confidence=0.80, reasoning=f"{cycle}红利策略防御性强 | 波动率{vol}%",
            dca_multiplier=1.5, dca_reason=f"{cycle}红利防御属性突出，可加码")
    elif vol > 20:
        return StrategySignal(strategy_id="dividend-lowvol", strategy_name="红利低波",
            signal="买入", confidence=0.72, reasoning=f"高波动({vol}%)红利低波抗跌",
            dca_multiplier=1.5, dca_reason="高波动市红利低波抗跌，可加码")
    return StrategySignal(strategy_id="dividend-lowvol", strategy_name="红利低波",
        signal="持有", confidence=0.65, reasoning=f"红利策略适合底仓 | 波动率{vol}%",
        dca_multiplier=1.0, dca_reason="红利适合底仓，按计划定投")


def _signal_dca(hs300: dict) -> StrategySignal:
    mom = hs300.get("momentum_1m")
    vol = hs300.get("volatility_60d", 15) or 15
    reason = "定投不看短期涨跌，坚持纪律长期积累份额"
    dca_mult = 1.0
    dca_reason = "按计划定投"
    if mom is not None and mom < -5:
        reason = f"沪深300近1月跌{mom:.1f}%，正是定投好时机——低位多攒份额"
        dca_mult = 1.5
        dca_reason = "近1月明显下跌，低位多攒份额"
    elif mom is not None and mom > 10:
        reason = f"沪深300近1月涨{mom:.1f}%，定投继续但可考虑减少单次金额"
        dca_mult = 0.5
        dca_reason = "近1月涨幅较大，本期减少单次金额"
    return StrategySignal(strategy_id="dca", strategy_name="定投策略",
        signal="买入", confidence=0.90, reasoning=reason,
        dca_multiplier=dca_mult, dca_reason=dca_reason)


# ── 策略列表 API ─────────────────────────────────────────

def get_all_strategies(current_cycle: str, signals: dict = None) -> list[QuantStrategy]:
    result = []
    for s in STRATEGY_DEFS:
        sig = _make_signal(s["id"], current_cycle, signals)
        sig.strategy_name = s["name"]
        result.append(QuantStrategy(
            id=s["id"], name=s["name"], tagline=s["tagline"],
            description=s["description"], suitable_cycle=s["suitable_cycle"],
            rules=s["rules"], frequency=s["frequency"],
            risk_level=s["risk_level"], current_signal=sig,
            etf_picks=ETF_PICKS.get(s.get("etf_category", ""), []),
        ))
    return result


def get_strategy_by_id(sid: str, current_cycle: str, signals: dict = None) -> QuantStrategy | None:
    for s in STRATEGY_DEFS:
        if s["id"] == sid:
            sig = _make_signal(s["id"], current_cycle, signals)
            sig.strategy_name = s["name"]
            return QuantStrategy(
                id=s["id"], name=s["name"], tagline=s["tagline"],
                description=s["description"], suitable_cycle=s["suitable_cycle"],
                rules=s["rules"], frequency=s["frequency"],
                risk_level=s["risk_level"], current_signal=sig,
                etf_picks=ETF_PICKS.get(s.get("etf_category", ""), []),
            )
    return None


# ── 入场信号综合决策（跨 7 个入场策略统合） ──────────────────

# 入场信号方向权重（买入 +1 / 卖出 -1 / 持有 0 / 观望 0）
# 持有=0：避免"全持有"被误判为偏多（此前 +0.35 会把中性点抬高到 67.5）
ENTRY_SIGNAL_SCORES = {"买入": 1.0, "持有": 0.0, "观望": 0.0, "卖出": -1.0}


def synthesize_entry_decision(strategies: list[QuantStrategy]) -> dict:
    """
    综合所有入场策略，输出偏多/分歧/偏空共识 + 加权得分 + 各策略投票。

    score: 0-100，50 为中性（买入/卖出对称加权）。
    consensus: 偏多共识 | 信号分歧 | 偏空共识。
    """
    if not strategies:
        return {
            "recommendation": "数据不足",
            "consensus": "无法判断",
            "score": 50.0,
            "breakdown": {},
            "key_reasons": [],
            "votes": [],
        }

    breakdown = {"买入": 0, "持有": 0, "观望": 0, "卖出": 0}
    total_score = 0.0
    votes = []

    for s in strategies:
        sig = s.current_signal
        if sig is None:
            breakdown["观望"] = breakdown.get("观望", 0) + 1
            votes.append({"strategy_id": s.id, "strategy_name": s.name,
                          "signal": "观望", "confidence": 0.5, "reasoning": ""})
            continue

        signal = sig.signal or "观望"
        conf = sig.confidence or 0.5
        breakdown[signal] = breakdown.get(signal, 0) + 1
        total_score += ENTRY_SIGNAL_SCORES.get(signal, 0) * conf
        votes.append({
            "strategy_id": s.id,
            "strategy_name": s.name,
            "signal": signal,
            "confidence": round(conf, 2),
            "reasoning": (sig.reasoning or "").split("|")[0].strip(),
        })

    n = len(strategies)
    # 归一化到 0-100：total_score ∈ [-n, n] → score ∈ [0, 100]，50 为中性
    score = round((total_score / n + 1.0) / 2.0 * 100.0, 1)
    score = max(0.0, min(100.0, score))

    if score >= 60:
        consensus = "偏多共识"
        recommendation = "多数策略看多，可分批布局"
    elif score <= 40:
        consensus = "偏空共识"
        recommendation = "多数策略看空，宜观望或减仓"
    else:
        consensus = "信号分歧"
        recommendation = "多空信号打架，等待方向明朗"

    # 关键理由：|加权分| 最高的 3 个策略
    ranked = sorted(votes, key=lambda v: abs(ENTRY_SIGNAL_SCORES.get(v["signal"], 0) * v["confidence"]),
                    reverse=True)
    key_reasons = []
    for v in ranked[:3]:
        r = v["reasoning"]
        if len(r) > 60:
            r = r[:60] + "…"
        key_reasons.append(f"【{v['strategy_name']}】{v['signal']} — {r}")

    return {
        "recommendation": recommendation,
        "consensus": consensus,
        "score": score,
        "breakdown": breakdown,
        "key_reasons": key_reasons,
        "votes": votes,
    }


# ── 定投档位共识（定投为主的使用定位） ──────────────────

# 各策略在"定投档位"里的参考权重：与定投择时直接相关的策略权重更高
DCA_STRATEGY_WEIGHTS = {
    "dca": 1.5,                 # 定投本体
    "dividend-lowvol": 1.2,     # 红利底仓（防御性加码依据）
    "merrill-rotation": 1.2,    # 周期择时
    "dual-ma-trend": 1.0,       # 趋势择时
    "rsrs-momentum": 1.0,       # 力度择时
    "grid-trading": 1.0,        # 区间位置择时
    "risk-parity": 0.5,         # 配置型，对档位贡献小
}


def synthesize_dca_decision(strategies: list[QuantStrategy], valuation: dict = None) -> dict:
    """
    综合各入场策略的定投档位 + 估值温度计，输出本期定投建议（0.5x / 1.0x / 1.5x）。

    估值温度计作为"低买高卖"的锚：PE 分位越低，定投倍数越高（叠加在各策略档位上）。
    返回 multiplier 已被钳制在 [0, 2.0]，tier 为中文档位。
    """
    if not strategies:
        return {
            "multiplier": 1.0, "tier": "正常", "label": "数据不足，按计划定投",
            "valuation_multiplier": 1.0, "votes": [], "key_reasons": [],
        }

    weighted_sum = 0.0
    weight_total = 0.0
    votes = []

    for s in strategies:
        sig = s.current_signal
        if sig is None:
            continue
        mult = getattr(sig, "dca_multiplier", 1.0) or 1.0
        conf = sig.confidence or 0.5
        w = DCA_STRATEGY_WEIGHTS.get(s.id, 1.0)
        weighted_sum += mult * w * (0.6 + 0.4 * conf)
        weight_total += w * (0.6 + 0.4 * conf)
        votes.append({
            "strategy_id": s.id,
            "strategy_name": s.name,
            "dca_multiplier": round(mult, 2),
            "dca_reason": getattr(sig, "dca_reason", "") or "",
            "confidence": round(conf, 2),
        })

    if weight_total <= 0:
        strat_mult = 1.0
    else:
        strat_mult = weighted_sum / weight_total

    # 估值温度计映射（低估值加码、高估值减码）
    valuation_mult = 1.0
    val_note = ""
    if valuation:
        pe_pct = valuation.get("pe_percentile")
        if pe_pct is None:
            pe_pct = valuation.get("pb_percentile")
        if pe_pct is not None:
            try:
                from dca_engine import valuation_to_multiplier
                valuation_mult, val_note = valuation_to_multiplier(float(pe_pct))
            except Exception:
                pass

    # 策略档位与估值档位相乘（估值作为全局乘数），并钳制到 [0, 2.0]
    multiplier = max(0.0, min(2.0, round(strat_mult * valuation_mult, 2)))

    if multiplier >= 1.3:
        tier, label = "加码", f"本期建议加码定投（{multiplier}x）"
    elif multiplier <= 0.2:
        tier, label = "暂停", f"极端高估/风险，建议暂停定投（{multiplier}x）"
    elif multiplier <= 0.6:
        tier, label = "减码", f"本期建议减码定投（{multiplier}x）"
    else:
        tier, label = "正常", f"本期按计划定投（{multiplier}x）"

    # 关键理由：与 1.0 偏离最大的策略档位
    votes_sorted = sorted(votes, key=lambda v: abs(v["dca_multiplier"] - 1.0), reverse=True)
    key_reasons = []
    for v in votes_sorted[:3]:
        if v["dca_reason"]:
            key_reasons.append(f"【{v['strategy_name']}】{v['dca_multiplier']}x — {v['dca_reason']}")
    if val_note:
        key_reasons.append(f"【估值温度计】{valuation_mult}x — {val_note}")

    return {
        "multiplier": multiplier,
        "tier": tier,
        "label": label,
        "valuation_multiplier": round(valuation_mult, 2),
        "votes": votes,
        "key_reasons": key_reasons,
    }
