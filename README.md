# 观澜 (Guanlan) · 个人量化投资辅助工具

一个面向个人投资者的量化投资辅助 Web 工具：宏观周期分析 + A 股选股排名 + 量化策略回测 + 公众号财经解读。后端 FastAPI + Python 3.12，前端原生 JS SPA + ECharts，无需登录/注册，数据全部来自公开免费来源。

> ⚠️ **免责声明**：本项目所有分析结论、策略信号、配置建议仅供学习与参考，**不构成任何投资建议**。量化策略为教育性质，不执行实盘。投资有风险，决策需独立判断。

## 功能

六大模块（SPA 单页应用，移动端优先）：

- **宏观仪表盘** — 美林时钟周期判断 + 9 项宏观指标（GDP/CPI/PMI/M2/PPI 等）+ ECharts 可视化 + 资产配置建议 + 数据来源可信度横幅
- **推荐标的** — ETF 推荐 + Top 5 股票 + 策略信号 + 金牛奖基金
- **每日解读** — 徐小明博客全文聚合 + DeepSeek LLM 财经解读
- **量化策略** — 7 种入场策略 + 10 种离场策略，策略一致性面板 + 定投档位共识（本期投 0.5x/1x/1.5x）
- **选股排名** — A 股低 PB Top 50，PE-TTM 口径，五维度财务健康度，板块封顶，SOE 过滤
- **回测** — 逐日 walk-forward 回测引擎，多离场策略批量对比叠加权益曲线（Calmar/Sortino 等指标）
- **定投回测** — DCA 引擎：固定/估值加码/一次性三模式对比，XIRR 资金加权年化，T+1 净值与申赎费计入

## 技术栈

- 后端：FastAPI + Python 3.12 + APScheduler（定时刷新）+ DeepSeek API（LLM 解读）
- 前端：原生 JS SPA + ECharts 5.5（本地化），无框架、无构建步骤
- 数据源：akshare（行情/财务）、国家统计局、新浪博客、财新 PMI（公开免费）

## 目录结构

```
guanlan/
├── backend/
│   ├── main.py              # FastAPI 入口 + API 路由
│   ├── models.py            # Pydantic 数据模型
│   ├── data_fetcher.py      # 宏观数据抓取
│   ├── cycle_analyzer.py    # 美林时钟周期分析
│   ├── allocator.py         # 资产配置
│   ├── stock_fetcher.py     # 选股排名
│   ├── wechat_reader.py     # 公众号文章获取
│   ├── llm_summarizer.py    # DeepSeek LLM 解读
│   ├── quant_strategies.py  # 入场策略
│   ├── exit_strategies.py   # 离场策略
│   ├── strategy_engine.py   # 策略引擎
│   ├── fund_data.py         # 基金数据
│   ├── fund_flow.py         # 资金流向
│   ├── indicators.py        # 技术指标
│   ├── backtest_engine.py   # 回测引擎（walk-forward，一次性买卖）
│   ├── dca_engine.py        # 定投引擎（XIRR + 估值加码 + 止盈再平衡）
│   ├── jinniu_award.py      # 金牛奖数据
│   └── requirements.txt     # 依赖清单
├── web/
│   ├── index.html           # SPA 入口
│   ├── css/style.css        # 样式（暗色调）
│   ├── js/                  # app.js 路由 + 各模块脚本
│   └── lib/echarts.min.js   # ECharts 本地化
├── PRODUCT_MANUAL.md        # 产品说明书
└── CHANGELOG.md             # 开发记录
```

## 本地部署

```bash
# 1. 创建虚拟环境并安装依赖
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 2. 配置环境变量
export DEEPSEEK_API_KEY="sk-..."          # 必填，LLM 解读（不配置则解读降级为文章列表）
export WEWE_RSS_URL="http://127.0.0.1:4000"   # 可选，公众号 RSS 源
export WEWE_FEED_ID=""                    # 可选，公众号 feed id

# 3. 启动服务
uvicorn backend.main:app --host 127.0.0.1 --port 8002
```

浏览器访问 `http://127.0.0.1:8002`。生产部署参考 `PRODUCT_MANUAL.md`（Nginx 反向代理 + systemd 守护）。

## 数据来源

| 数据 | 来源 |
|------|------|
| A 股行情 / 财务 / 指数估值 | akshare |
| 宏观指标（GDP/CPI/PMI/M2/PPI） | 国家统计局、财新 |
| 公众号文章 | 新浪博客 / RSS |
| 财经解读 | DeepSeek API（LLM） |

## 免责声明

本项目为个人学习项目，所有数据延迟与口径差异已在界面以 `data_note` 提示条明示。不构成投资建议，使用本项目产生的任何决策与损失由使用者自行承担。
