# 观澜 — 产品说明书

> 版本：v7 | 更新日期：2026-06-15  
> 访问地址：`http://<your-server-ip>/guanlan/`

---

## 一、产品概述

**观澜**是一个个人投资辅助 Web 工具，部署在阿里云 ECS 上。面向个人投资者（主要在手机微信内置浏览器中使用），提供宏观周期分析、公众号内容解读、量化策略参考、A股选股排名四大功能模块。

**设计原则**：
- 所有分析结论仅供参考，不构成投资建议
- 数据来源公开免费，不依赖付费 API
- 个人使用为先，无需注册/登录/备案
- 服务轻量（~180MB 内存），与通玄（经典文言翻译）共存于同一服务器

---

## 二、系统架构

```
                    Nginx (:80)
                   /           \
          /guanlan/             / (通玄)
              |
       FastAPI + uvicorn
       (:8002, systemd)
              |
    ┌─────────┼─────────┐
    │         │         │
  backend/   web/    /opt/guanlan-venv/
    │         │
    ├─ data_fetcher.py    (宏观数据)
    ├─ cycle_analyzer.py  (周期分析)
    ├─ allocator.py       (资产配置)
    ├─ stock_fetcher.py   (选股排名)
    ├─ wechat_reader.py   (文章获取)
    ├─ llm_summarizer.py  (LLM解读)
    ├─ quant_strategies.py(量化策略)
    ├─ models.py          (数据模型)
    └─ main.py            (API入口)
    
    web/
    ├─ index.html         (SPA入口)
    ├─ css/style.css
    ├─ js/
    │   ├─ app.js         (路由+API)
    │   ├─ dashboard.js   (宏观仪表盘)
    │   ├─ insights.js    (每日解读)
    │   ├─ strategies.js  (量化策略)
    │   └─ rankings.js    (选股排名)
    └─ lib/echarts.min.js
```

### 部署组件

| 组件 | 配置 | 说明 |
|------|------|------|
| Web 服务器 | Nginx, port 80 | `/guanlan/` → `127.0.0.1:8002` |
| 应用服务 | systemd `guanlan.service` | 开机自启 |
| 虚拟环境 | `/opt/guanlan-venv/` | Python 3.12 |
| 定时任务 | cron | 3 个定时刷新任务 |

### 定时任务

| 时间 | 任务 | 说明 |
|------|------|------|
| 7:00 每日 | `curl -X POST /guanlan/api/refresh/macro` | 刷新宏观数据 |
| 19:00 每日 | `curl -X POST /guanlan/api/refresh/insights` | 刷新公众号解读 |
| 15:30 工作日 | `curl -X POST /guanlan/api/refresh/rankings` | 刷新选股排名 |

---

## 三、功能模块

### 模块 1：宏观仪表盘 📊

**数据来源**：
1. chinadata.live（第三方聚合 API）
2. 国家统计局 easyquery API（官方，权威来源）
3. 财新 PMI（独立第三方，官方 PMI 对照）
4. 内置默认值（以上来源均不可用时兜底）

**指标体系**（9 项）：

| 指标 | 代码 | 来源标注 |
|------|------|----------|
| CPI 同比 | cpi | chinadata / nbs / default |
| PPI 同比 | ppi | chinadata / nbs / default |
| PMI 制造业 | pmi | chinadata / nbs / default |
| M2 同比 | m2 | chinadata / nbs / default |
| GDP 增速 | gdp | chinadata / nbs / default |
| 社零增速 | retail | chinadata / nbs / default |
| 固投增速 | fai | chinadata / nbs / default |
| 失业率 | unemploy | chinadata / nbs / default |
| 财新 PMI 制造业 | caixin_pmi | caixin（独立） |

**分析方法**：改进版美林时钟

- **增长动量** = GDP(30%) + PMI(30%) + 社零(20%) + 固投(15%) + 失业率反向(5%)
- **通胀动量** = CPI(45%) + PPI(35%) + M2(20%)
- Z-score 标准化（2020-2025 基线），归一化到 [-1, 1]
- 根据两维度符号判定四象限周期：复苏 / 过热 / 滞胀 / 衰退

**置信度机制**：
- 基础置信度 = 距离原点 × 0.7（距离越远越确定）
- 每个使用默认值的指标：-0.2
- 每个双源冲突的指标：-0.1
- 下限 0.05，上限 1.0
- 当前（API 不可用时）：5.0%（诚实反映数据不可靠）

**资产配置**：根据周期阶段推荐 6 类资产占比（股票/债券/现金/黄金/大宗商品/货币基金）

**前端展示**：
- 周期卡片 + 置信度 + 数据质量备注
- 9 项指标卡片（含来源色点：NBS 蓝 / chinadata 绿 / 默认红 / 财新金）
- 数据质量警告横幅（默认值 ≥3 时显示）
- ECharts 玫瑰图 + 四象限散点图 + 配置饼图
- 白话经济周期解读

---

### 模块 2：每日解读 📰

**工作流程**：
```
新浪博客 xuxiaoming8 → wechat_reader.py → 文章全文获取
    → llm_summarizer.py (DeepSeek) → AI 深度解读
    → 前端：原文卡片（上）+ AI 解读（下）
```

**数据来源优先级**：
1. WeWe RSS（微信读书 Docker，备用）
2. **新浪博客 blog.sina.com.cn/xuxiaoming8**（当前主力，徐小明同步更新）
3. 搜狗微信搜索 type=2（文章搜索）
4. 百度 site:mp.weixin.qq.com（兜底）

**LLM 解读**：使用 DeepSeek API 对当日文章进行专业金融解读，生成约 1800 字分析

**前端布局**：
- 上部：原文卡片（标题 + 来源标签 + 正文 + 原文链接 + 发布时间）
- 分隔线
- 下部：🤖 AI 深度解读（Markdown 渲染）
- 手动刷新按钮

---

### 模块 3：量化策略 📈

5 种量化策略，大白话描述，教育参考性质：

| 策略 | 核心思想 | 适用周期 |
|------|----------|----------|
| 经济周期轮动 | "经济好不好、物价涨不涨，决定了该买什么" | 衰退→复苏→过热→滞胀 |
| 趋势跟踪 | "短期均线上穿长期均线就是上涨信号" | 趋势市场 |
| 涨跌力度比较 | "比较每天的涨跌力度，力度强就跟进" | 震荡转趋势 |
| 网格自动买卖 | "设定一个价格区间，跌了自动买、涨了自动卖" | 震荡市场 |
| 风险均衡配置 | "让每类资产的风险贡献差不多" | 长期持有 |

每个策略展示：名称 + 一句话描述 + 详细逻辑 + 适用场景 + 当前周期下的信号

---

### 模块 4：A股选股排名 🏷️

**筛选流程**：
```
A 股全量 (~5500只)
  → 合并财务数据 (stock_yjbb_em)
  → 过滤 PB < 2 (~1800只)
  → 过滤 ST/*ST
  → 5 维度综合评分
  → 财务健康度调整
  → 板块封顶选择
  → Top 50
```

**综合评分**（百分位排名，0~1）：

| 维度 | 权重 | 方向 |
|------|------|------|
| 主营增长率 | 25% | 越高越好 |
| 主营利润率 | 20% | 越高越好 |
| 净利润率 | 25% | 越高越好 |
| 低 PE | 20% | 越低越好 |
| 低 PB | 10% | 越低越好 |

缺失指标用中性值 0.5 替代，不重归一化。超过 2 个指标缺失则排除。

**财务健康度**（五维度，惩罚系数 0.30~1.0）：

| # | 维度 | 检测逻辑 | 扣分 |
|---|------|----------|------|
| 1 | 现金流质量 | 经营现金流/每股收益 < 0 | -25% |
| | | < 0.3 | -15% |
| | | < 0.5 | -8% |
| 2 | ROE 合理性 | ROE > 50% | -10% |
| | | ROE < -20% | -10% |
| 3 | 利润增速偏离 | 利润增速 - 营收增速 > 30pp | -12% |
| | | > 20pp | -6% |
| 4 | 营业利润质量 | 营业利润/利润总额 < 0.3 | -15% |
| | | < 0.5 | -8% |
| | | > 1.2（非经常性亏损） | -5% |
| 5 | 应计项目占比 | (净利润-经营CF)/|净利润| > 80% | -10% |

**调整后评分 = 综合评分 × 健康度**（按调整后评分排序）

**板块封顶**：
- 单板块最多 3 只（申万 128 行业分类）
- 金融大类（银行/证券/保险/多元金融）合计最多 8 只

**数据来源**：
- Sina 新浪财经（价格）：`ak.stock_zh_a_spot()`
- 东方财富 datacenter（财务）：`ak.stock_yjbb_em()`
- 东方财富（现金流）：`ak.stock_xjll_em()`
- 东方财富（利润表）：`ak.stock_lrb_em()`
- ST 列表：`ak.stock_zh_a_st_em()`
- 5 个批量调用 asyncio.gather 并行化，总耗时 ~18s

**前端展示**：
- 板块分布摘要：`银行Ⅱ(3) · 证券Ⅱ(2) · 电力(2) · ...`
- 排名表格：代码 | 名称 | 行业标签 | PB | PE | 营收增长 | 毛利率 | 净利率 | 健康度 | 综合评分 | 调整评分
- 行业标签：绿色（非金融）/ 橙色（金融）
- 健康度警示图标（⚠️，hover 显示具体问题）
- 手动刷新按钮

---

## 四、API 路由

| 方法 | 路径 | 说明 | 响应时间 |
|------|------|------|----------|
| GET | `/guanlan/` | 前端页面 | — |
| GET | `/guanlan/api/dashboard` | 仪表盘全量数据 | <5ms（内存） |
| GET | `/guanlan/api/indicators` | 宏观指标 | <5ms |
| GET | `/guanlan/api/allocation` | 投资占比 | <5ms |
| GET | `/guanlan/api/insights` | 当日解读 | <5ms |
| GET | `/guanlan/api/insights/history` | 历史解读 | <5ms |
| GET | `/guanlan/api/strategies` | 策略列表 | <5ms |
| GET | `/guanlan/api/strategies/{id}` | 策略详情 | <5ms |
| GET | `/guanlan/api/rankings` | 选股 Top 50 | <5ms |
| POST | `/guanlan/api/refresh/macro` | 手动刷新宏观 | ~7s |
| POST | `/guanlan/api/refresh/insights` | 手动刷新解读 | ~10s |
| POST | `/guanlan/api/refresh/rankings` | 手动刷新选股 | ~18s |

---

## 五、版本历史

| 版本 | 日期 | 核心内容 |
|------|------|----------|
| v1 | 2026-06-10 | 初始实现：FastAPI + SPA + 宏观/解读/策略三大模块 |
| v2 | 06-10 下午 | 前端性能：ECharts 本地化（5.8s→25ms）、暗色调 UI |
| v3 | 06-10 傍晚 | 明亮 UI、启动异步化（1.5s→5ms）、手动刷新、策略人话版 |
| v4 | 06-10 晚 | 图表加载 bug 修复、白话周期解读 |
| v4.x | 06-10~11 | 新增选股（AKShare PB<2 Top 50）、公众号修复、异常值过滤 |
| v5 | 06-12 | 文章来源切换到新浪博客、解读页上下布局重构、ES5 兼容 |
| v6 | 06-15 | 板块占比优化（85%→40%）、财务健康度（零新API）、ST 过滤 |
| v7 | 06-15 | 宏观数据可信度（并行双源+财新PMI+置信度改革）、更深选股信号（五维度健康度+并行化） |

---

## 六、关键技术决策

1. **为什么用 FastAPI？** 与通玄技术栈统一，异步支持适合并发 API 调用。

2. **为什么不用 Docker？** 服务器内存仅 1.6GB，无 Docker 环境。systemd + venv 更轻量。

3. **为什么 ECharts 本地化？** CDN 跨境加载 5.8s 阻塞渲染，本地 serve 25ms。

4. **为什么不做微信小程序？** 纯 Web 响应式在微信内置浏览器体验一致，省去备案/审核。

5. **为什么用新浪博客而非搜狗微信？** 搜狗反爬严格且搜索结果不精确。新浪博客完全开放，徐小明每日同步更新。

6. **为什么用申万 128 行业分类？** `stock_yjbb_em` 自带 `所处行业` 字段，无需额外 API。

7. **为什么并行化所有批量 API？** 选股刷新从 30s 降至 18s，宏观刷新从 12s 降至 7s，总耗时 = 最慢单次而非累加。

8. **为什么置信度能从 91.8% 降到 5%？** 0.5 底线是人造的乐观偏差。诚实反映数据质量比看起来好看更重要。

---

## 七、数据流总览

```
外部数据源                       观澜后端                        前端
──────────────────────────────────────────────────────────────────

chinadata.live ───┐
NBS easyquery ────┼─→ data_fetcher.py ──→ cycle_analyzer.py ──→ dashboard.js
Caixin PMI ───────┘         │                   │                  │
                            │              BASELINE Z-score        │
                            │              四象限判定              │
                            │              置信度+惩罚             │
                            │                   │                  │
                            │              allocator.py            │
                            │              6类资产配置矩阵          │
                            │                   │                  │
                            └───────────────────┴───────────→ ECharts 图表

新浪博客 ──→ wechat_reader.py ──→ llm_summarizer.py ──→ insights.js
xuxiaoming8      │                      │                    │
           多源降级链              DeepSeek API          原文卡片（上）
           (博客→搜狗→百度)        专业金融解读          AI解读（下）

Sina ──────┐
East Money ┼─→ stock_fetcher.py ──→ rankings.js
  yjbb_em  │         │                   │
  xjll_em  │    筛选: PB<2             行业标签
  lrb_em   │    排除: ST/*ST           健康度列
ST list ───┘    评分: 5维度+板块封顶    调整评分
```

---

## 八、性能指标

| 指标 | 值 |
|------|------|
| 页面首次加载 | <100ms |
| Dashboard API 响应 | <5ms（内存返回） |
| 宏观数据刷新 | ~7s（并行双源） |
| 选股排名刷新 | ~18s（并行 5 批量 API） |
| 公众号解读刷新 | ~10s（取决于 DeepSeek API） |
| 服务内存占用 | ~180MB（峰值 ~235MB） |
| 服务启动时间 | ~2s |

---

## 九、待开发项

### 功能增强
- [ ] 更多宏观指标（社融、进出口、汇率）
- [ ] 资产配置中加入 ETF 代码建议
- [ ] 回测数据展示
- [ ] 用户自定义风险偏好
- [ ] 邮件/微信推送每日报告

### 技术优化
- [ ] 前端构建工具压缩 JS/CSS
- [ ] ECharts 按需加载
- [ ] API gzip 压缩
- [ ] 访问鉴权
- [ ] JSON → SQLite 迁移

### UI/UX
- [ ] 加载进度条
- [ ] 图表手势缩放
- [ ] 深色/浅色主题切换
- [ ] Service Worker 离线缓存

---

## 十、文件清单

```
/opt/guanlan/
├── PRODUCT_MANUAL.md                   # 本文件
├── CHANGELOG.md                        # 详细开发记录
├── backend/
│   ├── main.py                         # FastAPI 应用入口（异步启动、12 API 路由）
│   ├── models.py                       # Pydantic 数据模型（10+ 模型）
│   ├── data_fetcher.py                 # 宏观数据获取（并行双源 + 财新PMI）
│   ├── cycle_analyzer.py               # 美林时钟周期分析（置信度改革）
│   ├── allocator.py                    # 资产配置矩阵（4周期 × 6资产）
│   ├── stock_fetcher.py                # 选股排名（5维度健康度 + 板块封顶）
│   ├── wechat_reader.py                # 公众号文章获取（多源降级链）
│   ├── llm_summarizer.py               # DeepSeek LLM 解读
│   ├── quant_strategies.py             # 5 种量化策略（人话版）
│   ├── requirements.txt                # Python 依赖
│   └── data/                           # JSON 缓存目录
│       ├── macro_cache.json            # 宏观数据 + source_metadata
│       ├── dashboard_cache.json        # 仪表盘全量缓存
│       ├── stock_rankings_cache.json   # 选股 Top 50
│       ├── insights_cache.json         # 解读缓存
│       ├── insights_history.json       # 解读历史（90天）
│       └── articles.json               # 文章存档
├── web/
│   ├── index.html                      # SPA 入口（4 Tab）
│   ├── css/style.css                   # 明亮简约样式
│   ├── js/
│   │   ├── app.js                      # 路由 + API 封装 + 全局刷新
│   │   ├── dashboard.js                # 宏观仪表盘（ECharts + 质量横幅）
│   │   ├── insights.js                 # 每日解读（原文+AI）
│   │   ├── strategies.js               # 量化策略卡片
│   │   └── rankings.js                 # 选股排名（行业+健康度）
│   └── lib/
│       └── echarts.min.js              # ECharts 5.5 本地
└── /opt/guanlan-venv/                  # Python 3.12 虚拟环境
```
