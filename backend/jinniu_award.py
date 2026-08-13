"""
观澜 — 金牛奖获奖数据模块

第22届中国基金业金牛奖 (2025-12-30)
数据来源: 中国证券报·金牛理财网
更新频率: 年度 (每年金牛奖颁奖后手动更新)

本次评选是证监会《推动公募基金高质量发展行动方案》发布后的首届，
核心原则从"重规模"转向"重回报"，取消三年期奖项，采用五年及以上长周期考核。
"""

from models import GoldenBullCompany, GoldenBullProduct, GoldenBullManager, GoldenBullSummary

# ── 奖项信息 ──────────────────────────────────────────

JINNIU_YEAR = "第22届"
JINNIU_DATE = "2025-12-30"
JINNIU_SOURCE = "中国证券报"


# ── 1. 获奖基金公司 (10家) ────────────────────────────
# 前5家为金牛基金管理公司奖（最高荣誉），后5家为专项奖代表性公司

JINNIU_COMPANIES: list[dict] = [
    # ═══ 金牛基金管理公司 (top honor) ═══
    {
        "name": "大成基金",
        "award_level": "company",
        "award_name": "金牛基金管理公司 + 主动权益 + 长期回报",
        "award_category": "全能型",
        "star_products": ["大成高鑫股票", "大成策略回报混合", "大成精选增值混合"],
        "star_managers": ["徐彦", "刘旭"],
    },
    {
        "name": "华泰柏瑞基金",
        "award_level": "company",
        "award_name": "金牛基金管理公司 + 被动投资 + 逆向销售",
        "award_category": "被动投资领军",
        "star_products": ["华泰柏瑞沪深300ETF", "华泰柏瑞红利ETF"],
        "star_managers": ["张慧", "柳军"],
    },
    {
        "name": "工银瑞信基金",
        "award_level": "company",
        "award_name": "金牛基金管理公司",
        "award_category": "银行系头部",
        "star_products": ["工银创新动力股票", "工银文体产业股票"],
        "star_managers": ["郑泽鸿", "欧阳凯"],
    },
    {
        "name": "建信基金",
        "award_level": "company",
        "award_name": "金牛基金管理公司",
        "award_category": "银行系头部",
        "star_products": ["建信健康民生混合", "建信改革红利股票"],
        "star_managers": ["姜锋", "陶灿"],
    },
    {
        "name": "国泰基金",
        "award_level": "company",
        "award_name": "金牛基金管理公司 + 全球配置",
        "award_category": "全球配置",
        "star_products": ["国泰金鹏蓝筹价值混合", "国泰估值优势混合"],
        "star_managers": ["程洲", "李恒"],
    },
    # ═══ 专项奖代表性公司 ═══
    {
        "name": "景顺长城基金",
        "award_level": "special",
        "award_name": "主动权益投资金牛基金公司",
        "award_category": "主动权益",
        "star_products": ["景顺长城鼎益混合(LOF)", "景顺长城成长之星股票"],
        "star_managers": ["刘彦春"],
    },
    {
        "name": "国海富兰克林基金",
        "award_level": "special",
        "award_name": "主动权益投资 + 长期回报金牛奖",
        "award_category": "主动权益",
        "star_products": ["国富中小盘股票", "国富弹性市值混合"],
        "star_managers": ["赵晓东"],
    },
    {
        "name": "华商基金",
        "award_level": "special",
        "award_name": "主动权益投资金牛基金公司",
        "award_category": "主动权益",
        "star_products": ["华商改革创新股票", "华商新锐产业混合"],
        "star_managers": ["李双全"],
    },
    {
        "name": "广发基金",
        "award_level": "special",
        "award_name": "全球配置金牛基金公司",
        "award_category": "全球配置",
        "star_products": ["广发睿毅领先混合", "广发多因子混合"],
        "star_managers": ["林英睿"],
    },
    {
        "name": "兴业基金",
        "award_level": "special",
        "award_name": "固收投资金牛基金公司",
        "award_category": "固定收益",
        "star_products": ["兴业定开债券", "兴业添利债券"],
        "star_managers": ["王筱苓"],
    },
    # ═══ 历史金牛常客头部公司 ═══
    {
        "name": "易方达基金",
        "award_level": "historical",
        "award_name": "金牛常客 · 历届多次获奖",
        "award_category": "行业龙头",
        "star_products": ["易方达蓝筹精选混合", "易方达优质精选混合", "易方达消费行业股票"],
        "star_managers": ["张坤", "萧楠"],
    },
    {
        "name": "华夏基金",
        "award_level": "historical",
        "award_name": "金牛常客 · 历届多次获奖",
        "award_category": "行业龙头",
        "star_products": ["华夏沪深300ETF联接A", "华夏回报混合A", "华夏大盘精选混合"],
        "star_managers": ["张弘弢", "徐猛"],
    },
    {
        "name": "嘉实基金",
        "award_level": "historical",
        "award_name": "金牛常客 · 历届多次获奖",
        "award_category": "行业龙头",
        "star_products": ["嘉实增长混合", "嘉实沪深300ETF联接A", "嘉实新兴产业股票"],
        "star_managers": ["归凯", "洪流"],
    },
    {
        "name": "南方基金",
        "award_level": "historical",
        "award_name": "金牛常客 · 历届多次获奖",
        "award_category": "行业龙头",
        "star_products": ["南方中证500ETF联接A", "南方优选价值混合A", "南方新优享灵活配置"],
        "star_managers": ["史博", "茅炜"],
    },
    {
        "name": "富国基金",
        "award_level": "historical",
        "award_name": "金牛常客 · 历届多次获奖",
        "award_category": "行业龙头",
        "star_products": ["富国天惠成长混合A", "富国低碳环保混合", "富国中证红利指数增强"],
        "star_managers": ["朱少醒", "李元博"],
    },
]


# ── 2. 获奖基金产品 (10只) ────────────────────────────
# 涵盖7年期/5年期股票型、混合型、债券型持续优胜金牛基金

JINNIU_PRODUCTS: list[dict] = [
    # 七年期开放式股票型
    {
        "fund_name": "大成高新技术产业股票A",
        "fund_code": "000628",
        "company_name": "大成基金",
        "award_name": "七年期开放式股票型持续优胜金牛基金",
        "award_category": "股票型",
    },
    {
        "fund_name": "招商量化精选股票发起式",
        "fund_code": "001917",
        "company_name": "招商基金",
        "award_name": "七年期开放式股票型持续优胜金牛基金",
        "award_category": "股票型",
    },
    {
        "fund_name": "工银创新动力股票",
        "fund_code": "000893",
        "company_name": "工银瑞信基金",
        "award_name": "七年期开放式股票型持续优胜金牛基金",
        "award_category": "股票型",
    },
    # 七年期开放式混合型
    {
        "fund_name": "大成策略回报混合A",
        "fund_code": "090007",
        "company_name": "大成基金",
        "award_name": "七年期开放式混合型持续优胜金牛基金",
        "award_category": "混合型",
    },
    {
        "fund_name": "大成精选增值混合",
        "fund_code": "090004",
        "company_name": "大成基金",
        "award_name": "七年期开放式混合型持续优胜金牛基金",
        "award_category": "混合型",
    },
    # 五年期开放式混合型
    {
        "fund_name": "国泰金鹏蓝筹价值混合",
        "fund_code": "020009",
        "company_name": "国泰基金",
        "award_name": "五年期开放式混合型持续优胜金牛基金",
        "award_category": "混合型",
    },
    {
        "fund_name": "大成创新成长混合(LOF)",
        "fund_code": "160910",
        "company_name": "大成基金",
        "award_name": "五年期开放式混合型持续优胜金牛基金",
        "award_category": "混合型",
    },
    {
        "fund_name": "大成优选混合(LOF)",
        "fund_code": "160916",
        "company_name": "大成基金",
        "award_name": "五年期开放式混合型持续优胜金牛基金",
        "award_category": "混合型",
    },
    # 七年期开放式债券型
    {
        "fund_name": "鹏华丰禄债券",
        "fund_code": "003547",
        "company_name": "鹏华基金",
        "award_name": "七年期开放式债券型持续优胜金牛基金",
        "award_category": "债券型",
    },
    # 五年期开放式股票型
    {
        "fund_name": "景顺长城成长之星股票",
        "fund_code": "000418",
        "company_name": "景顺长城基金",
        "award_name": "五年期开放式股票型持续优胜金牛基金",
        "award_category": "股票型",
    },
    # ── 历史金牛常客头部公司代表产品 ──
    {
        "fund_name": "易方达蓝筹精选混合",
        "fund_code": "005827",
        "company_name": "易方达基金",
        "award_name": "五年期开放式混合型持续优胜金牛基金（多次获奖）",
        "award_category": "混合型",
    },
    {
        "fund_name": "富国天惠成长混合A",
        "fund_code": "161005",
        "company_name": "富国基金",
        "award_name": "七年期开放式混合型持续优胜金牛基金（多次获奖）",
        "award_category": "混合型",
    },
    {
        "fund_name": "嘉实增长混合",
        "fund_code": "070002",
        "company_name": "嘉实基金",
        "award_name": "七年期开放式混合型持续优胜金牛基金（多次获奖）",
        "award_category": "混合型",
    },
]


# ── 3. 明星基金经理 (10位) ────────────────────────────

JINNIU_MANAGERS: list[dict] = [
    {
        "name": "徐彦",
        "company_name": "大成基金",
        "title": "首席权益投资官",
        "representative_funds": ["大成竞争优势混合A", "大成睿享混合A"],
        "achievement": "深度价值投资，连续5年跑赢沪深300",
    },
    {
        "name": "刘旭",
        "company_name": "大成基金",
        "title": "权益投资副总监",
        "representative_funds": ["大成高新技术产业股票A"],
        "achievement": "GARP策略，7年任期回报超200%",
    },
    {
        "name": "张慧",
        "company_name": "华泰柏瑞基金",
        "title": "主动权益投资总监",
        "representative_funds": ["华泰柏瑞创新升级混合A"],
        "achievement": "均衡成长风格，长期年化收益优异",
    },
    {
        "name": "郑泽鸿",
        "company_name": "工银瑞信基金",
        "title": "权益投资部基金经理",
        "representative_funds": ["工银创新动力股票"],
        "achievement": "擅长制造与科技赛道，任期获金牛产品奖",
    },
    {
        "name": "姜锋",
        "company_name": "建信基金",
        "title": "权益投资部副总经理",
        "representative_funds": ["建信健康民生混合A"],
        "achievement": "聚焦消费升级，连续多年正收益",
    },
    {
        "name": "程洲",
        "company_name": "国泰基金",
        "title": "主动权益投资总监",
        "representative_funds": ["国泰金鹏蓝筹价值混合"],
        "achievement": "低估值价值策略，擅长周期反转布局",
    },
    {
        "name": "刘彦春",
        "company_name": "景顺长城基金",
        "title": "副总经理、明星基金经理",
        "representative_funds": ["景顺长城鼎益混合(LOF)", "景顺长城新兴成长混合A"],
        "achievement": "消费赛道旗帜人物，千亿级管理规模",
    },
    {
        "name": "赵晓东",
        "company_name": "国海富兰克林基金",
        "title": "权益投资总监",
        "representative_funds": ["国富中小盘股票A"],
        "achievement": "中小盘价值挖掘，金牛奖与晨星奖双料得主",
    },
    {
        "name": "林英睿",
        "company_name": "广发基金",
        "title": "价值投资部基金经理",
        "representative_funds": ["广发睿毅领先混合A"],
        "achievement": "逆向价值投资，擅长左侧布局困境反转",
    },
    {
        "name": "李双全",
        "company_name": "华商基金",
        "title": "权益投资部基金经理",
        "representative_funds": ["华商改革创新股票A"],
        "achievement": "GARP策略践行者，攻守兼备风格鲜明",
    },
    # ── 历史金牛常客头部公司明星经理 ──
    {
        "name": "张坤",
        "company_name": "易方达基金",
        "title": "副总经理、权益投资决策委员会主席",
        "representative_funds": ["易方达蓝筹精选混合", "易方达优质精选混合"],
        "achievement": "价值投资旗帜人物，首位管理规模破千亿的主动权益基金经理",
    },
    {
        "name": "朱少醒",
        "company_name": "富国基金",
        "title": "副总经理、权益投资总监",
        "representative_funds": ["富国天惠成长混合A"],
        "achievement": "15年+管理单只基金，任期回报超2000%，业界传奇",
    },
    {
        "name": "萧楠",
        "company_name": "易方达基金",
        "title": "消费行业基金经理",
        "representative_funds": ["易方达消费行业股票"],
        "achievement": "消费赛道领军人物，多次获金牛基金奖",
    },
    {
        "name": "归凯",
        "company_name": "嘉实基金",
        "title": "成长投资总监",
        "representative_funds": ["嘉实新兴产业股票"],
        "achievement": "成长股猎手，擅长科技+消费赛道，任期回报行业前列",
    },
]


# ── 获取函数 ──────────────────────────────────────────

def get_jinniu_data() -> GoldenBullSummary:
    """返回第22届金牛奖完整推荐数据（静态数据，年度更新）"""
    companies = [GoldenBullCompany(**c) for c in JINNIU_COMPANIES]
    products = [GoldenBullProduct(**p) for p in JINNIU_PRODUCTS]
    managers = [GoldenBullManager(**m) for m in JINNIU_MANAGERS]

    return GoldenBullSummary(
        award_info=f"第22届金牛奖 ({JINNIU_DATE})",
        companies=companies,
        products=products,
        managers=managers,
    )
