# 观澜 — 项目开发记录

## 定投为主定位优化（2026-08-17）

按「定投为主、基金+黄金标的、其他策略作为投多少钱参考」的使用定位，全面优化回测/策略/选股：

### 回测
- 新增 `dca_engine.py` 定投引擎：固定定投 / 估值加码定投 / 一次性买入三模式对比，XIRR 资金加权年化（多期现金流唯一正确口径），T+1 净值、申赎费阶梯、红利再投口径、留存现金计入。
- `backtest_engine` 补齐 Calmar / Sortino / 年化波动率 / 最长连续亏损指标；新增滑点与无风险利率参数；单策略回测复用预计算；红利/债券价格指数低估明示。

### 策略
- 入场信号新增 `dca_multiplier` 定投档位（0.5x/1x/1.5x）与 `dca_reason`，新增 `synthesize_dca_decision` 定投档位共识 + 估值温度计叠加（低估值加码/高估值减码/暂停）。
- 修复入场共识「全持有→偏多」评分偏差（持有权重 0.35→0）；统一 RSRS 阈值口径（>0.4 买入）。
- 黄金离场③④接入真实 10Y 国债收益率与 USD/CNY 月涨跌（失败回退周期推断）。
- `strategy_engine` 去重，指标统一复用 `indicators.py` 单源实现。

### 选股
- PE 改为滚动 12 个月（TTM）口径，修复报告期累计 EPS 导致 PE 系统性偏低；亏损股 PE 记最低分（此前误给中性分）；PB 阈值常量化可配。

### 前端
- 回测页新增「定投回测」卡片（三模式对比表 + 权益曲线）；策略页决策面板新增定投档位建议横幅；选股口径说明更新。

## 发布说明（2026-08-16）

- 代码首次发布到 GitHub（`sawensi/guanlan`），用于代码托管与版本管理；线上服务仍部署在个人 ECS。
- 发布前脱敏：文档中的服务器公网 IP 已替换为 `<your-server-ip>` 占位符。
- 敏感配置（`DEEPSEEK_API_KEY`、`WEWE_RSS_URL`、`WEWE_FEED_ID`）一律从环境变量读取，无硬编码；`.gitignore` 排除 `backend/data/`（定时刷新缓存）、`.venv/`、`__pycache__/`。

## 项目概述

**观澜**是一个个人投资辅助 Web 工具，部署在阿里云 ECS（`<your-server-ip>`），与通玄（经典文言翻译）共存于同一台服务器。

- **访问地址**: `http://<your-server-ip>/guanlan/`
- **部署模式**: 参考通玄 — Nginx + FastAPI，不买域名、不备案、个人使用
- **适用场景**: 手机微信内置浏览器 / 桌面浏览器

---

## 核心需求（初始）

1. **宏观周期分析 + 投资占比建议**
   - 搜索国家统计局宏观数据（GDP/CPI/PMI/M2/PPI 等）
   - 基于美林时钟判断经济周期阶段
   - 输出资产配置占比，ECharts 图形可视化
   - 每日更新

2. **公众号内容聚合解读**
   - 每晚 19:00 获取微信公众号"投资明见"当日文章
   - 用 DeepSeek LLM 进行专业摘要解读

3. **量化交易策略方案**
   - 基于投资占比提供量化交易战略
   - 引入 5 种量化策略（参考/教育性质，不执行实盘）

---

## 版本迭代

### v1 — 初始实现（2026-06-10）

**新增文件**:
```
/opt/guanlan/
├── backend/
│   ├── main.py              # FastAPI 应用入口 + API 路由
│   ├── models.py            # Pydantic 数据模型
│   ├── data_fetcher.py      # NBS 数据抓取（chinadata.live + NBS easyquery）
│   ├── cycle_analyzer.py    # 经济周期分析（改进版美林时钟）
│   ├── allocator.py         # 资产配置计算（4 阶段 × 6 类资产矩阵）
│   ├── wechat_reader.py     # 公众号文章获取（搜狗微信搜索）
│   ├── llm_summarizer.py    # LLM 摘要（DeepSeek API）
│   ├── quant_strategies.py  # 5 种量化策略
│   └── requirements.txt
├── web/
│   ├── index.html           # SPA 入口（三 Tab：宏观/解读/策略）
│   ├── css/style.css        # 暗色调样式
│   └── js/
│       ├── app.js           # 路由 + API 封装
│       ├── dashboard.js     # ECharts 玫瑰图 + 四象限 + 指标卡片
│       ├── insights.js      # 文章解读 + 历史存档
│       └── strategies.js    # 策略卡片展开
└── /opt/guanlan-venv/       # Python 虚拟环境
```

**部署配置**:
- Nginx: `location /guanlan/` → proxy_pass `127.0.0.1:8002`
- systemd: `guanlan.service`（环境变量 `DEEPSEEK_API_KEY`）
- cron: `0 7 * * *` 刷新宏观数据，`0 19 * * *` 刷新公众号解读

**技术选型**:
- 后端: Python 3.12 / FastAPI / httpx / Pydantic v2
- LLM: DeepSeek API（复用通玄的 key）
- 前端: 原生 JS SPA / ECharts 5.x（CDN）/ 暗色调
- 数据: chinadata.live API → 国家统计局 easyquery API → 内置默认值

**遗留问题**: 前端 CDN 阻塞（ECharts 5.8s）、暗色调界面粗糙

---

### v2 — 前端性能 + 视觉修复（2026-06-10 下午）

**用户反馈**:
1. 进入界面很慢
2. 前端界面很丑
3. 前端按钮点不动

**根因诊断**:
- ECharts CDN（`cdn.jsdelivr.net`）在 `<head>` 中同步加载，耗时 5.8s
- 期间页面白屏、DOMContentLoaded 不触发、所有 JS 事件未绑定
- CSS 暗色调过于简陋

**修复方案**:

| 修复 | 文件 | 改动 |
|------|------|------|
| 速度 | `index.html` | ECharts 从 CDN 改为本地 `/lib/echarts.min.js`，所有 `<script>` 加 `defer` |
| 速度 | `main.py` | 添加 `StaticFiles` mount 以 serve 本地静态文件 |
| 界面 | `css/style.css` | 重写为毛玻璃暗色调（`backdrop-filter: blur`）、更好的间距和卡片层次 |
| 按钮 | `js/app.js` | 路由优先初始化，`defer` 保证 DOM 就绪即绑定事件 |

**效果**:
- 页面加载：5.8s → **< 0.03s**
- ECharts：CDN 阻塞 → 本地 25ms
- 按钮：6 秒延迟 → 立即可点击

---

### v3 — 明亮 UI + 启动优化 + 功能完善（2026-06-10 傍晚）

**用户反馈**:
1. 界面太暗，需要简约大气的明亮界面
2. 图表加载太慢（如果已获取过数据，不要再调取）
3. 解读功能没有手动刷新按钮
4. 策略描述太专业，看不懂

**根因诊断**:
- 界面：v2 暗色调不符合需求
- 慢：`lifespan()` 中 `refresh_macro_data()` 同步阻塞启动
- 无刷新：insights 页面缺少 UI 按钮
- 难懂：策略描述用金融术语（OLS 回归、金叉死叉、波动率倒数等）

**修复方案**:

| # | 修复 | 文件 | 改动 |
|---|------|------|------|
| 1 | 明亮 UI | `css/style.css` | 全重写：暖白背景 `#f2f3f0`、白色卡片、森林绿 `#2c5f2d` 主色、去毛玻璃 |
| 2 | 启动优化 | `main.py` | `lifespan` 秒加载缓存/默认值 → 立即 yield → `asyncio.create_task` 后台刷新；`get_dashboard` 永远从内存返回不阻塞 |
| 3 | 手动刷新 | `index.html` + `js/app.js` | insights 卡片加 `🔄 刷新` 按钮，调用 `POST /api/refresh/insights` |
| 4 | 人话策略 | `quant_strategies.py` | 5 个策略全部用大白话重写，去专业术语 |
| - | 配套 | `js/dashboard.js` | 图表配色适配明亮主题 |
| - | 配套 | `js/app.js` | 添加 `refreshInsightsNow()` 全局函数 |

**效果**:
- API 响应：1.5s+（阻塞启动） → **< 5ms**（内存秒返）
- 界面：暗黑 → 明亮简约（暖白 + 森林绿）
- 策略：术语堆砌 → 大白话（如"经济好不好、物价涨不涨，决定了该买什么"）

---

## 当前架构

### 文件清单

```
/opt/guanlan/
├── CHANGELOG.md                    # 本文件
├── backend/
│   ├── main.py                     # FastAPI 应用（异步启动、非阻塞 API）
│   ├── models.py                   # Pydantic 数据模型
│   ├── data_fetcher.py             # 宏观数据获取（缓存优先）
│   ├── cycle_analyzer.py           # 美林时钟周期判断
│   ├── allocator.py                # 资产配置矩阵
│   ├── wechat_reader.py            # 搜狗微信文章获取
│   ├── llm_summarizer.py           # DeepSeek LLM 摘要
│   ├── quant_strategies.py         # 5 种量化策略（人话版）
│   ├── requirements.txt            # Python 依赖
│   └── data/                       # JSON 缓存目录
│       ├── dashboard_cache.json    # 宏观数据缓存
│       ├── allocation.json         # 资产配置缓存
│       ├── articles.json           # 文章缓存
│       ├── insights_cache.json     # 解读缓存
│       └── insights_history.json   # 解读历史
├── web/
│   ├── index.html                  # SPA 入口（四 Tab：宏观/解读/策略/选股）
│   ├── css/style.css               # 明亮简约样式
│   ├── js/
│   │   ├── app.js                  # 路由 + API + 刷新逻辑
│   │   ├── dashboard.js            # 仪表盘（ECharts 图表）
│   │   ├── insights.js             # 每日解读
│   │   └── strategies.js           # 量化策略卡片
│   └── lib/
│       └── echarts.min.js          # ECharts 5.5 本地文件
└── /opt/guanlan-venv/              # Python 3.12 虚拟环境
```

### 部署组件

| 组件 | 配置 | 说明 |
|------|------|------|
| Nginx | port 80, `location /guanlan/` → `127.0.0.1:8002` | 与通玄（`/` → 8001）共存 |
| systemd | `guanlan.service` | 开机自启，环境变量含 `DEEPSEEK_API_KEY` |
| cron | `0 7 * * *` curl refresh/macro | 每日刷新宏观数据 |
| cron | `0 19 * * *` curl refresh/insights | 每日刷新公众号解读 |
| cron | `30 15 * * 1-5` curl refresh/rankings | 工作日 A 股收盘后刷新选股 |

### API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/guanlan/` | 前端页面 |
| GET | `/guanlan/api/dashboard` | 仪表盘全量数据（内存缓存秒返） |
| GET | `/guanlan/api/indicators` | 宏观指标 |
| GET | `/guanlan/api/allocation` | 投资占比 |
| GET | `/guanlan/api/insights` | 当日解读 |
| GET | `/guanlan/api/insights/history` | 历史解读 |
| GET | `/guanlan/api/strategies` | 策略列表 |
| GET | `/guanlan/api/strategies/{id}` | 策略详情 |
| GET | `/guanlan/api/rankings` | 每日选股 Top 50 |
| POST | `/guanlan/api/refresh/macro` | 手动刷新宏观数据 |
| POST | `/guanlan/api/refresh/insights` | 手动刷新解读 |
| POST | `/guanlan/api/refresh/rankings` | 手动刷新选股 |

### 数据流

```
NBS/chinadata API ──→ data_fetcher.py ──→ cycle_analyzer.py ──→ allocator.py
       (07:00 cron)        │                      │                    │
                           ▼                      ▼                    ▼
                      macro_cache.json      周期 + 置信度        配置占比矩阵
                           │                      │                    │
                           └──────────────────────┴────────────────────┘
                                                  │
                                                  ▼
                                          _latest_dashboard (内存)
                                                  │
                                                  ▼
                                          /api/dashboard (4ms)

搜狗微信搜索 ──→ wechat_reader.py ──→ llm_summarizer.py (DeepSeek)
  (19:00 cron)         │                       │
                       ▼                       ▼
                 articles.json         InsightsResult
                       │                       │
                       └───────────────────────┘
                                  │
                                  ▼
                          _latest_insights (内存)
                                  │
                                  ▼
                          /api/insights
```

---

## 关键技术决策

1. **为什么用 FastAPI 而不是 Flask/Django？**
   与通玄技术栈统一，复用现有知识。FastAPI 的异步支持也适合并发 API 调用。

2. **为什么不用 Docker？**
   服务器内存仅 1.6GB，无 Docker 环境。直接 systemd + venv 更轻量。

3. **为什么 ECharts 本地化而不是 CDN？**
   CDN 跨墙加载 5.8s，阻塞页面渲染。本地 serve 25ms。

4. **为什么不做微信小程序？**
   用户不注册小程序。纯 Web 响应式在微信内置浏览器中体验一致，且省去备案/审核。

5. **为什么用搜狗微信搜索而不是 wechat-download-api？**
   搜狗方案无需登录凭证，适合低频个人使用。如果反爬严格，可切换到后者。

6. **为什么用默认数据兜底？**
   外部 API 可能挂掉。内置合理默认值确保应用始终可用。

---

## 待优化项（发版备忘）

### 功能增强
- [x] 公众号文章获取成功率优化（改用新浪博客 xuxiaoming8 主力源，WeWe RSS 备用接口就绪）✅ v5
- [x] 桌面浏览器兼容性修复（ES5 语法 + Cache-Control 缓存头 + 防御式 DOM）✅ v5
- [ ] 更多宏观指标（社融、进出口、汇率）
- [ ] 资产配置中加入具体的 ETF 代码建议
- [ ] 回测数据展示（策略历史表现）
- [ ] 用户自定义风险偏好调整配置
- [ ] 邮件/微信推送每日报告

### 技术优化
- [ ] 前端引入构建工具（Vite）压缩 JS/CSS
- [ ] ECharts 按需加载减小体积
- [ ] API 响应加 gzip 压缩
- [ ] 增加简单的访问鉴权（个人使用，防爬）
- [ ] 数据存储从 JSON 迁移到 SQLite

### UI/UX
- [ ] 仪表盘增加加载进度条
- [ ] 图表支持手势缩放（移动端）
- [ ] 深色/浅色主题切换
- [ ] 离线缓存（Service Worker）

---

### v4 — 修复图表加载 + 白话解读（2026-06-10 晚）

**问题**：
1. ECharts 图表仍然加载失败
2. 宏观界面缺少通俗易懂的文字说明

**根因诊断**：
- `app.js` 的 `boot()` 中直接调用 `loadDash()`，但该函数定义在 `dashboard.js`
- `defer` 脚本按序执行：`echarts.js`(1) → `app.js`(2) → `dashboard.js`(3)
- `app.js` 执行时 `loadDash` 尚未定义 → `ReferenceError` → 图表渲染崩溃
- 同时 `get_dashboard()` 等函数缺少 `global _latest_dashboard` 声明 → `UnboundLocalError` → API 500

**修复**：
- `app.js`: `boot()` 改为 `setTimeout(() => go('dashboard'), 10)` — 等所有 defer 脚本就绪后再触发
- `main.py`: 修复 3 个函数缺少的 `global` 声明
- `index.html`: 周期卡片下方添加 `#cycleExplain` 白话解读区
- `css/style.css`: 添加 `.cycle-explain` 和 `.intro-text` 样式
- `dashboard.js`: 添加 `renderExplain()` 函数，根据四个周期阶段输出通俗解释，如：
  - 复苏期 → "经济正在回暖！增长开始加速，但物价还没大涨...股票尤其是成长型股票往往表现最好"
  - 衰退期 → "当前经济偏冷...债券是最受益的资产"

---

## v4.x — 新增选股 + 修复公众号获取 + 轻量优化（2026-06-10 晚 ~ 06-11）

**新增**:
- 股票排名功能：AKShare 获取 A 股 PB<2 股票，综合评分 Top 50
- Tab 从「宏观/解读/策略」扩展为「宏观/解读/策略/选股」四 Tab
- 公众号搜索关键词修正为「徐小明 投资明见」
- 搜狗链接解析修复（`/link?url=` 相对路径补全）
- 百度备用搜索 `site:mp.weixin.qq.com`
- 股票排名异常值过滤（PB<0 视为缺失）

**新增文件**: `backend/stock_fetcher.py`, `web/js/rankings.js`
**新增 API**: `GET /api/rankings`, `POST /api/refresh/rankings`
**新增 cron**: 工作日 15:30 刷新股票排名

---

### v5 — 修复文章源 + 重构解读页布局（2026-06-12）

**用户反馈**:
1. 解读页获取的内容不是「投资明见」徐小明的真实文章
2. 希望原文内容显示在上半部分，AI 解读放在下半部分
3. 桌面浏览器一直显示「正在加载文章」

**根因诊断**:

1. **文章来源不准**: 搜狗微信搜索按关键词匹配，返回的是「提及」投资明见的文章（来源为"投资策略明见"、"9527的回忆录"等），而非徐小明本人发布的文章。百度同理。
2. **桌面加载卡死**: 
   - Nginx 未设 Cache-Control，浏览器缓存了旧版 HTML（`#insightsBody`）
   - 新版 JS 查找 `#articlesContent` 元素 → 找不到 → `null.innerHTML = ...` 报错 → loading 状态卡住
   - JS 使用 ES6+ 语法（模板字面量、箭头函数、可选链、`const`/`let`），部分桌面浏览器兼容性差

**修复方案**:

| # | 修复 | 文件 | 改动 |
|---|------|------|------|
| 1 | 文章来源 | `wechat_reader.py` | 重写为多源架构：WeWe RSS（备用）→ **新浪博客 xuxiaoming8**（主力）→ 搜狗 → 百度 |
| 2 | 文章全文 | `wechat_reader.py` | 新增 `_fetch_sina_blog_articles()`：解析博客首页 HTML，抓取每篇文章全文（需 Referer 防盗链） |
| 3 | 全文清洗 | `wechat_reader.py` | 新增 `_clean_sina_body()`：去除新浪博客元数据（标签、微信号、id 等）、广告导航、尾部垃圾 |
| 4 | 数据模型 | `models.py` | `ArticleItem` 新增 `content: str`（全文）和 `source: str`（来源标识）字段 |
| 5 | LLM 分析 | `llm_summarizer.py` | 优先使用 `content`（全文）做分析，降级使用 `summary`；prompt 升级 |
| 6 | 文章卡片 | `web/js/insights.js` | 上半部分渲染文章原文（标题 + 编号 + 来源标签 + 正文 + 原文链接 + 发布时间） |
| 7 | AI 解读 | `web/js/insights.js` | 下半部分渲染 LLM 解读（markdown），分隔线标注「🤖 AI 深度解读」 |
| 8 | HTML 结构 | `web/index.html` | `#insightsBody` 拆分为 `#articlesContent` + `#insightsDivider` + `#llmInterpretation` |
| 9 | 卡片样式 | `web/css/style.css` | 新增 `.article-card`（左绿边 + 浅色背景）、`.article-header`、`.article-body`（max-height 600px 可滚动）、`.article-footer`、`.insights-divider` 等 |
| 10 | 浏览器兼容 | `web/js/insights.js` | 全部改为 ES5 语法：`var` 替代 `const`/`let`，字符串拼接替代模板字面量，`function(){}` 替代箭头函数，显式检查替代可选链 `?.` |
| 11 | 缓存修复 | Nginx `/etc/nginx/sites-available/default` | `/guanlan/` location 加入 `expires -1` + `Cache-Control: no-cache, must-revalidate` |
| 12 | 防御式渲染 | `web/js/insights.js` | 新增 `_insightsError()` + 旧 DOM 回退提示 |
| 13 | Docker 尝试 | — | 安装 Docker + 配置镜像源 + 拉取 WeWe RSS 镜像 → 超时失败（国内无法访问 Docker Hub），接口留好备用 |

**新数据流**:

```
新浪博客 xuxiaoming8 ──→ wechat_reader._fetch_sina_blog_articles()
        │                        │
        │                 解析首页 HTML 获取文章列表
        │                 带 Referer 抓取每篇全文
        │                 _clean_sina_body() 清洗正文
        │                        │
        ▼                        ▼
   5 篇今日文章 (title + url + content + source)
        │
        ▼
  llm_summarizer.summarize_articles()  ← 使用全文
        │
        ▼
  InsightsResult (articles + full_interpretation)
        │
        ▼
  前端: 上半文章卡片 + 下半 AI 解读
```

**多源降级链**:
```
WeWe RSS (微信读书 Docker, 备用)
  ↓ 不可用
新浪博客 blog.sina.com.cn/xuxiaoming8  ← 当前主力（徐小明同步更新，完全开放）
  ↓ 不可用
搜狗微信搜索 type=2 文章搜索
  ↓ 不可用
搜狗微信搜索 type=1 账号搜索
  ↓ 不可用
百度 site:mp.weixin.qq.com
```

**效果**:
- 文章来源：❌ 搜狗"提及"文章 → ✅ 徐小明新浪博客 5 篇真实文章（已验证标题：反弹、周五操作策略、盘中同步直播、末期、个股风险大）
- 文章正文：❌ 仅摘要 → ✅ 每篇 126~1096 字全文
- LLM 解读：基于徐小明真实分析内容生成 1800+ 字专业解读
- 桌面浏览器：✅ ES5 兼容语法 + 缓存头 fix
- 页面布局：上半文章原文 + 分隔线 + 下半 AI 解读

---

### v6 — 板块占比优化 + 选股财务健康度（2026-06-15）

**用户反馈**：
1. 选股 Top 50 中银行/证券/保险占比过高（~85%）
2. 财务造假风险：如何识别虚增利润的公司

**修复方案**：

| # | 修复 | 文件 | 改动 |
|---|------|------|------|
| 1 | 板块封顶 | `stock_fetcher.py` | 新增 `_select_top_n_with_diversity()`：单板块≤3只，金融合计≤8只 |
| 2 | 行业分类 | `stock_fetcher.py` | 从已有 `stock_yjbb_em` 提取「所处行业」字段（128申万分类） |
| 3 | 权重修复 | `stock_fetcher.py` | 缺失指标用中性值 0.5 替代，不再重归一化权重（移除金融股1.25x放大） |
| 4 | 健康度评分 | `stock_fetcher.py` | 新增 `_calculate_financial_health()`：三维度反造假评分 |
| 5 | ST过滤 | `stock_fetcher.py` | 新增 `_fetch_st_stocks()` 排除 ST/*ST 股票 |
| 6 | 数据模型 | `models.py` | StockRankingItem 新增 sector/cfps/roe/health 等 8 个字段 |
| 7 | 前端展示 | `rankings.js` + `style.css` + `index.html` | 行业列+板块分布摘要+健康度列+警示图标 |

**财务健康度三维度**：

| 维度 | 检测逻辑 | 扣分 |
|------|----------|------|
| 现金流质量 | CFPS/EPS < 0（经营现金流为负） | -25% |
| 现金流偏弱 | CFPS/EPS < 0.3 ~ 0.5 | -8%~-15% |
| ROE极端 | ROE > 50% 或 < -20% | -10% |
| 利润虚增 | 利润增速 - 营收增速 > 20~30pp | -6%~-12% |

调整后评分 = 综合评分 × 健康度（范围 0.30~1.0）

**效果**:
- 金融股占比：85% (17/20) → 40% (8/20)
- 板块数量：~4 个 → 10 个
- 选股表格新增：行业列、健康度列、调整评分列
- 健康度数据零新API调用（CFPS/ROE来自已有`stock_yjbb_em`）

---

### v7 — 宏观数据可信度 + 更深选股信号（2026-06-15）

**Phase B — 宏观数据可信度**：

| # | 修复 | 文件 | 说明 |
|---|------|------|------|
| 1 | 并行双源 + 财新PMI | `data_fetcher.py` | chinadata + NBS + Caixin PMI 并行请求（asyncio.gather），12s→7s |
| 2 | 交叉验证 | `data_fetcher.py` | 双源差异>10% 标记 conflict |
| 3 | 来源追踪 | `data_fetcher.py` + `models.py` | 每项指标记录 source（chinadata/nbs/default/caixin），缓存含 source_metadata |
| 4 | 置信度改革 | `cycle_analyzer.py` | 移除 0.5 底线；每个默认值-0.2，每个冲突-0.1，底线0.05 |
| 5 | 基线更新 | `cycle_analyzer.py` | Z-score 基线更新为 2020-2025 数据 |
| 6 | 前端横幅 | `dashboard.js` + `index.html` + `style.css` | 默认值≥3时显示红色警告横幅；指标卡片加来源色点；置信度备注 |
| 7 | 管线透传 | `main.py` | refresh_macro_data 传递 source_metadata，计算 quality_warnings |

**Phase C — 更深选股信号**：

| # | 修复 | 文件 | 说明 |
|---|------|------|------|
| 8 | 批量API | `stock_fetcher.py` | 新增 `_fetch_cashflow_data_batch()`（xjll_em）和 `_fetch_income_statement_batch()`（lrb_em） |
| 9 | 并行化 | `stock_fetcher.py` | 5个批量调用 asyncio.gather 并行，刷新 30s→18s |
| 10 | 五维度健康度 | `stock_fetcher.py` | 新增维度4=营业利润/利润总额（非经常性收益检测），维度5=应计项目占比（盈利质量） |

**效果**:
- 置信度：0.918（虚假高值）→ 0.050（全部默认值时诚实显示低置信度）
- 财新PMI：成功获取 51.8，独立验证官方PMI
- 选股刷新：~30s → ~18s（并行化提速 40%）
- 成功检测 国投资本 非经常性亏损拖累利润
- 数据质量不透明 → 前端明确警告 + 来源标注

---

### v9 — 止盈清仓策略模块 + 全基金代码支持（2026-06-30）

**背景**: 观澜原有 7 个策略全部是入场型，缺少结构化离场逻辑；基金数据仅支持 ~25 个硬编码 ETF，支付宝买入的开放式基金无法使用。

**新增文件**:
```
/opt/guanlan/
├── backend/
│   ├── fund_data.py          # 基金数据统一获取（ETF→底层指数，开基→天天基金API，黄金→上海金现货）
│   └── exit_strategies.py    # 9 个离场策略（止盈/止损/时间/技术/黄金，比例式信号输出）
└── web/
    └── js/exits.js           # 前端离场策略卡片渲染（盈亏条、条件明细、操作进度条）
```

**新增模型**（`models.py`）:
- `ExitAction` — 离场操作建议（减仓至 x%/清仓 + 原因）
- `ExitConditionDetail` — 条件明细（是否触发 + 当前值 vs 阈值 + 权重）
- `ExitStrategySignal` — 离场信号（含 PnL、持有天数、赎回费率、费率断点）
- `ExitStrategy` — 离场策略定义（含 fund_type 区分 domestic/qdii/gold）

**新增 API**（`main.py`）:
- `GET /guanlan/api/exit-strategies?fund_code=&entry_price=&entry_date=` — 全部离场策略
- `GET /guanlan/api/exit-strategies/{id}?fund_code=...` — 单个策略详情

**9 个离场策略**（`exit_strategies.py`）:

| # | 策略ID | 类型 | 核心逻辑 |
|---|--------|------|---------|
| 1 | fixed-tp | 止盈 | +8%→减至70%, +15%→减至50%, +25%→清仓，结合赎回费断点优化 |
| 2 | trailing-stop | 止盈 | 盈利>10%激活追踪，回撤5%减半、8%清仓 |
| 3 | time-exit | 混合 | 对齐赎回费断点：<7天警告, 7-30天, 30-180天, 180-365天, >365天免费 |
| 4 | technical-exit | 信号 | MA死叉+RSI>70+MACD死叉+动量<-3%，2个→减至70%, 3个→减至50%, 4个→清仓 |
| 5 | atr-stop | 止损 | 入场价−2.5×ATR(14)，触及清仓，接近减半（基金参数比个股宽） |
| 6 | scale-out | 止盈 | +10%→减至70%, +20%→减至30%, 剩余启动移动止盈 |
| 7 | max-drawdown | 止损 | 回撤10%减半、15%清仓，无入场价用60/120日高点 |
| 8 | cycle-reversal | 信号 | 复苏→持有, 过热→减半, 滞胀→减至30%, 衰退→清仓 |
| 9 | **gold-exit** | 黄金 | 五大条件加权：RSI>80&月涨>12%(35%)+死叉(25%)+实际利率↑(20%)+美元↑(10%)+周期(10%)，≥50%减半≥70%清仓 |

**基金数据源升级**（`fund_data.py`）:
- ETF（510300等）→ 底层指数日线（Sina源 `stock_zh_index_daily`，稳定）
- 黄金ETF（518880等）→ 上海金 Au99.99 现货（`spot_hist_sge`）
- **开放式基金（008252/005827/161725等任意支付宝/天天基金代码）→ `fund_open_fund_info_em`**
- 日缓存（`data/fund_cache/`）

**技术指标扩展**（`strategy_engine.py`）:
- `_calc_broad()` 新增 ATR(14)、RSI(14)、MACD(12,26,9)，向后兼容

**前端**（`index.html` + `exits.js` + `strategies.js` + `style.css`）:
- 策略页标签切换：「📈 入场策略」|「🚪 离场策略」
- 离场标签下：基金代码/入场净值/入场日期表单 + 查询按钮
- 离场卡片：信号徽章 + 盈亏条 + 操作进度条（可视化减仓比例）+ 条件明细标签

**关键设计决策**:
- 基金参数 vs 个股参数：ATR 用 2.5×（vs 个股2×），回撤 10/15%（vs 个股15/25%），止盈 8/15/25%（vs 个股15/25/35%），对齐赎回费断点
- 黄金独立策略：不适用盈利目标止盈，基于实际利率/RSI超买/美元等核心驱动因子加权判定
- ETF 走指数源（Sina稳定），不走东方财富 ETF 接口（频繁限流）；开放式基金无 OHLC，用相邻净值差值模拟日内波动以支持 ATR 计算

**修改文件**: `backend/models.py`, `backend/strategy_engine.py`, `backend/main.py`, `web/index.html`, `web/js/strategies.js`, `web/css/style.css`

---

| 3 | `models.py` | 注释 Top 20 → Top 50 |
| 4 | `index.html` | 选股 Tab 标题 Top 20 → Top 50 |
| 5 | 文档 | PRODUCT_MANUAL / CHANGELOG 同步更新 |

**效果**：
- Top 50 → 约 17 个不同行业（申万 128 行业），金融占比控制在 20% 以内
- 前端表格动态渲染，无需额外改动
- 品质信号不稀释：~1800 只中前 2.8%

---

### v10 — 离场策略引入波动率突变 + 近期涨跌趋势（2026-07-03）

**用户反馈**：
1. 离场策略只考虑「从入场到现在赚/亏了多少」，忽略了基金的近期波动变化和涨跌趋势
2. 波动突然放大本身就是危险信号，应该独立影响离场判断
3. 近期净值在持续跌还是在涨，比入场盈亏更实时

**修复方案**：

| # | 修复 | 文件 | 说明 |
|---|------|------|------|
| 1 | 新增短期指标 | `fund_data.py` | 新增 `volatility_20d`、`ma5`、`ma10`、`momentum_5d`、`consecutive_direction` |
| 2 | 波动率突变检测 | `exit_strategies.py` | `_volatility_risk()`：比较 20日vol/60日vol，分 calm/normal/elevated/extreme 四档 |
| 3 | 近期趋势评估 | `exit_strategies.py` | `_trend_risk()`：综合 5日收益率+连续涨跌天数+MA排列，判断趋势强度 |
| 4 | 7 策略改造 | `exit_strategies.py` | fixed-tp/trailing-stop/scale-out/max-drawdown/atr-stop/technical-exit/time-exit 全部注入双维度 |
| 5 | 综合决策增强 | `exit_strategies.py` | `synthesize_exit_decision` 新增波动率风险+近期趋势两个虚拟贡献项，平等参与投票 |
| 6 | 前端展示 | `exits.js` | 汇总面板新增双维度风险指示器；策略卡片条件明细显示波动率+趋势行 |

**双维度逻辑**：

| 维度 | 检测内容 | 信号级别 |
|------|---------|---------|
| A: 波动率突变 | 20日vol / 60日vol | calm→放松阈值 / normal→不变 / elevated→收紧阈值+减仓 / extreme→强制降仓 |
| B: 近期趋势 | 5日收益+连跌天数+MA排列 | strong_up→安心持有 / neutral→不变 / weak_down→关注 / strong_down→减仓或清仓 |

**各策略影响**：
- 止盈类（fixed-tp/scale-out）：阈值×波动率系数；趋势转弱时提前锁定利润
- 止损类（trailing-stop/max-drawdown/atr-stop）：回撤阈值动态调整；ATR倍数从固定2.5变为 `1.5+vol_ratio`
- 技术类（technical-exit）：波动激增/趋势转弱时技术信号计数+1
- 时间类（time-exit）：极端波动+弱趋势时可考虑承担赎回费提前离场

**效果**：
- 离场信号从单一盈亏维度 → 三维度（盈亏+波动率突变+近期趋势）
- 波动率风险和近期趋势作为独立投票方参与综合决策
- 前端新增波动率状态 + 趋势指示器，一目了然

---

## 待开发项（发版备忘）

### 功能增强
- [x] 公众号文章获取成功率优化（改用新浪博客 xuxiaoming8 主力源，WeWe RSS 备用接口就绪）✅ v5
- [x] 桌面浏览器兼容性修复（ES5 语法 + Cache-Control 缓存头 + 防御式 DOM）✅ v5
- [x] 板块占比优化（单板块≤3只，金融合计≤8只）✅ v6
- [x] 选股财务健康度评分（CFPS/ROE/利润增速偏离）✅ v6
- [x] 宏观数据可信度（并行双源+财新PMI+置信度改革）✅ v7
- [x] 更深选股信号（现金流量表+利润表批量API+五维度健康度）✅ v7
- [x] ST/*ST 股票过滤 ✅ v6
- [ ] 更多宏观指标（社融、进出口、汇率）
- [ ] 资产配置中加入具体的 ETF 代码建议
- [ ] 回测数据展示（策略历史表现）
- [ ] 用户自定义风险偏好调整配置
- [ ] 邮件/微信推送每日报告

### 技术优化
- [ ] 前端引入构建工具（Vite）压缩 JS/CSS
- [ ] ECharts 按需加载减小体积
- [ ] API 响应加 gzip 压缩
- [ ] 增加简单的访问鉴权（个人使用，防爬）
- [ ] 数据存储从 JSON 迁移到 SQLite

### UI/UX
- [ ] 仪表盘增加加载进度条
- [ ] 图表支持手势缩放（移动端）
- [ ] 深色/浅色主题切换
- [ ] 离线缓存（Service Worker）
