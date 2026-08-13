/**
 * 观澜 — 策略回测
 * 表单交互、API 调用、结果渲染、ECharts 图表
 */

// 策略名称映射
var ENTRY_NAMES = {
  'merrill-rotation': '经济周期轮动',
  'dual-ma-trend': '趋势跟踪',
  'rsrs-momentum': '涨跌力度比较',
  'grid-trading': '网格自动买卖',
  'risk-parity': '风险均衡配置',
  'dividend-lowvol': '红利低波',
  'dca': '定投策略',
};

var EXIT_NAMES_ALL = {
  'fixed-tp': '固定止盈',
  'trailing-stop': '移动止盈',
  'time-exit': '时间止盈',
  'technical-exit': '技术指标离场',
  'atr-stop': 'ATR波动止损',
  'scale-out': '分批止盈',
  'max-drawdown': '最大回撤离场',
  'cycle-reversal': '宏观周期反转离场',
  'xuxiaoming-exit': '徐小明解读离场',
  'gold-exit': '黄金离场策略',
};

// 复选框展示顺序（全量 10 个离场策略）
var EXIT_CHECK_ORDER = [
  'trailing-stop', 'fixed-tp', 'time-exit', 'technical-exit',
  'atr-stop', 'max-drawdown', 'scale-out', 'cycle-reversal',
  'gold-exit', 'xuxiaoming-exit',
];

// 默认勾选：7 个通用策略（排除 gold-exit / xuxiaoming-exit）
var DEFAULT_CHECKED_EXITS = [
  'trailing-stop', 'fixed-tp', 'time-exit', 'technical-exit',
  'atr-stop', 'max-drawdown', 'scale-out',
];

// 固定 id → 颜色映射（颜色跟随策略实体，不随选中顺序变化；经 dataviz 校验 ALL CHECKS PASS）
var EXIT_COLORS = {
  'trailing-stop': '#d9480f',
  'fixed-tp': '#845ef7',
  'time-exit': '#2f9e44',
  'technical-exit': '#1971c2',
  'atr-stop': '#e64980',
  'max-drawdown': '#1098ad',
  'scale-out': '#f76707',
  'cycle-reversal': '#3b5bdb',
  'gold-exit': '#f03e3e',
  'xuxiaoming-exit': '#12b886',
};

var BT = { loading: false, result: null, chart: null, compareChart: null };

// 收集当前勾选的离场策略 id
function getCheckedExits() {
  var out = [];
  var boxes = document.querySelectorAll('#btExitCheckboxes input[type=checkbox]:checked');
  for (var i = 0; i < boxes.length; i++) out.push(boxes[i].value);
  return out;
}

// 销毁所有回测图表实例（切换单/对比视图前清理，避免孤儿实例）
function disposeBtCharts() {
  if (BT.chart) { BT.chart.dispose(); BT.chart = null; }
  if (BT.compareChart) { BT.compareChart.dispose(); BT.compareChart = null; }
}

// 渲染离场策略复选框组（含颜色圆点，与图表线条颜色联动）
function buildExitCheckboxes() {
  var container = $('btExitCheckboxes');
  if (!container) return;
  var html = '';
  for (var i = 0; i < EXIT_CHECK_ORDER.length; i++) {
    var id = EXIT_CHECK_ORDER[i];
    var checked = DEFAULT_CHECKED_EXITS.indexOf(id) !== -1 ? ' checked' : '';
    html += '<label class="bt-exit-check">' +
      '<input type="checkbox" value="' + id + '"' + checked + '>' +
      '<span class="bt-exit-dot" style="background:' + (EXIT_COLORS[id] || '#999') + ';"></span>' +
      escHtml(EXIT_NAMES_ALL[id] || id) +
      '</label>';
  }
  container.innerHTML = html;

  $('btExitSelectAll').addEventListener('click', function() {
    var boxes = container.querySelectorAll('input[type=checkbox]');
    for (var i = 0; i < boxes.length; i++) boxes[i].checked = true;
    loadStrategyInfo();
  });
  $('btExitClearAll').addEventListener('click', function() {
    var boxes = container.querySelectorAll('input[type=checkbox]');
    for (var i = 0; i < boxes.length; i++) boxes[i].checked = false;
    loadStrategyInfo();
  });
}

// ── 运行回测 ────────────────────────────────────────

async function runBacktest() {
  if (BT.loading) return;

  var checked = getCheckedExits();
  if (checked.length === 0) {
    showBtError('请至少选择一个离场策略');
    return;
  }

  var today = new Date().toISOString().slice(0, 10);
  var params = new URLSearchParams({
    fund_code: $('btFundCode').value.trim() || '510300',
    entry_strategy: $('btEntryStrategy').value,
    start_date: $('btStartDate').value || '2021-01-01',
    end_date: $('btEndDate').value || today,
    initial_capital: $('btCapital').value || '100000',
    position_size: $('btPositionSize').value || '1.0',
    cycle_assumption: $('btCycle').value,
  });

  // 1 个 → 现有单策略端点；>1 个 → 对比端点
  var isCompare = checked.length > 1;
  var url;
  if (isCompare) {
    params.set('exit_strategies', checked.join(','));
    url = API + '/backtest/compare-exits?' + params.toString();
  } else {
    params.set('exit_strategy', checked[0]);
    url = API + '/backtest?' + params.toString();
  }

  BT.loading = true;
  var btn = $('btRunBtn');
  btn.textContent = '⏳ 回测运行中...';
  btn.disabled = true;
  $('btResults').style.display = 'none';
  $('btError').style.display = 'none';

  try {
    var resp = await fetch(url);
    var data = await resp.json();
    if (!resp.ok) {
      showBtError(data.detail || '回测失败 (HTTP ' + resp.status + ')');
      BT.loading = false;
      btn.textContent = '▶ 运行回测';
      btn.disabled = false;
      return;
    }
    BT.result = data;
    if (isCompare && data.mode === 'compare') {
      renderCompareExits(data);
    } else {
      renderBacktestResults(data);
    }
  } catch (e) {
    showBtError('回测请求失败: ' + (e.message || '网络错误'));
  }

  BT.loading = false;
  btn.textContent = '▶ 运行回测';
  btn.disabled = false;
}

function showBtError(msg) {
  var el = $('btError');
  el.textContent = '⚠️ ' + msg;
  el.style.display = 'block';
}

// ── 渲染结果 ─────────────────────────────────────────

function renderBacktestResults(data) {
  if (!data || !data.metrics) {
    showBtError('回测返回数据异常');
    return;
  }

  disposeBtCharts();

  $('btResults').style.display = 'block';
  $('btError').style.display = 'none';

  var m = data.metrics;

  // 1. 摘要行
  var summaryHtml =
    '<div class="bt-summary">' +
      '<span><strong>' + escHtml(data.fund_name) + '</strong> (' + escHtml(data.fund_code) + ')</span>' +
      '<span>策略: ' + escHtml(ENTRY_NAMES[data.entry_strategy] || data.entry_strategy) +
        ' → ' + escHtml(EXIT_NAMES_ALL[data.exit_strategy] || data.exit_strategy) + '</span>' +
      '<span>' + escHtml(data.start_date) + ' ~ ' + escHtml(data.end_date) + '</span>' +
      '<span>初始 ¥' + data.initial_capital.toLocaleString() + ' → 最终 ¥' + data.final_equity.toLocaleString() + '</span>' +
    '</div>';

  // 2. 绩效卡片
  var cardsHtml = '<div class="bt-metrics-grid">' +
    btCard('累计收益', m.total_return_pct, '%', m.total_return_pct >= 0) +
    btCard('年化收益率', m.cagr_pct, '%', m.cagr_pct >= 0) +
    btCard('夏普比率', m.sharpe_ratio, '', m.sharpe_ratio >= 1) +
    btCard('最大回撤', m.max_drawdown_pct, '%', false, true) +
    btCard('胜率', m.win_rate_pct, '%', m.win_rate_pct >= 50) +
    btCard('盈亏比', m.profit_factor, '', m.profit_factor >= 1.5) +
    btCard('交易次数', m.total_trades, '笔', true) +
    btCard('基准收益', m.benchmark_return_pct, '%', m.benchmark_return_pct >= 0) +
    btCard('超额α', m.alpha_pct, '%', m.alpha_pct >= 0) +
    '</div>';

  // 3. 图表容器
  var chartHtml =
    '<div class="bt-chart-container">' +
      '<div class="card-label">📈 权益曲线</div>' +
      '<div id="btEquityChart" class="bt-chart"></div>' +
    '</div>';

  // 4. 交易明细
  var tradeHtml = renderTradeTable(data.trade_log || []);

  $('btResults').innerHTML = summaryHtml + cardsHtml + chartHtml + tradeHtml;

  // 延迟渲染图表（等 DOM 就绪）
  setTimeout(function() {
    renderEquityChart(data.equity_curve || []);
  }, 150);
}

function btCard(label, value, unit, positive, isRisk) {
  var color;
  if (isRisk) {
    // 风险指标：低 = 好（绿色）
    color = Math.abs(value) < 15 ? '#38a169' : Math.abs(value) < 30 ? '#ed8936' : '#e53e3e';
  } else {
    color = positive ? '#e53e3e' : '#38a169';
  }
  if (typeof value === 'number' && !isFinite(value)) value = '--';
  var displayVal = typeof value === 'number' ? value.toFixed(2) : value;
  return '<div class="bt-metric-card">' +
    '<div class="bt-metric-label">' + escHtml(label) + '</div>' +
    '<div class="bt-metric-value" style="color:' + color + ';">' + displayVal + '<small>' + (unit || '') + '</small></div>' +
    '</div>';
}

// ── 权益曲线图 ───────────────────────────────────────

function renderEquityChart(equityData) {
  var dom = document.getElementById('btEquityChart');
  if (!dom) return;
  if (typeof echarts === 'undefined') {
    dom.innerHTML = '<div style="padding:40px;text-align:center;color:#999;">ECharts 加载中...</div>';
    return;
  }

  if (BT.chart) { BT.chart.dispose(); }
  BT.chart = echarts.init(dom);

  var dates = equityData.map(function(d) { return d.date; });
  var equity = equityData.map(function(d) { return d.equity; });
  var benchmark = equityData.map(function(d) { return d.benchmark; });

  // 智能 x 轴标签间隔
  var labelInterval = Math.max(1, Math.floor(dates.length / 12));

  BT.chart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: function(params) {
        var s = params[0].axisValue + '<br/>';
        for (var i = 0; i < params.length; i++) {
          s += params[i].marker + ' ' + params[i].seriesName + ': ¥' +
               Number(params[i].value).toLocaleString() + '<br/>';
        }
        return s;
      },
    },
    legend: { data: ['策略净值', '买入持有'], bottom: 0 },
    grid: { left: 70, right: 20, top: 20, bottom: 35 },
    xAxis: {
      type: 'category', data: dates,
      axisLabel: {
        interval: labelInterval,
        formatter: function(v) { return v ? v.slice(0, 7) : ''; },
        fontSize: 10,
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: function(v) {
          if (v >= 10000) return (v / 10000).toFixed(1) + '万';
          return v;
        },
      },
    },
    series: [
      {
        name: '策略净值', type: 'line', data: equity,
        smooth: true, symbol: 'none',
        lineStyle: { color: '#2c5f2d', width: 2 },
        areaStyle: { color: 'rgba(44,95,45,0.08)' },
      },
      {
        name: '买入持有', type: 'line', data: benchmark,
        smooth: true, symbol: 'none',
        lineStyle: { color: '#a0aec0', width: 1, type: 'dashed' },
      },
    ],
  });

  // 响应式
  window.addEventListener('resize', function() {
    if (BT.chart) BT.chart.resize();
  });
}

// ── 交易明细表 ───────────────────────────────────────

// 自适应价格精度：高价保 2 位，低价保 4 位
function fmtBtPrice(p) {
  var n = Number(p);
  if (p === null || p === undefined || isNaN(n)) return '--';
  if (n >= 1000) return n.toFixed(2);
  if (n >= 10) return n.toFixed(3);
  return n.toFixed(4);
}

// 账户余额：交易后总资产（¥ 千分位整数）
function fmtAccountBalance(v) {
  if (v === null || v === undefined || isNaN(v)) return '--';
  return '¥' + Math.round(v).toLocaleString('zh-CN');
}

function renderTradeTable(trades) {
  if (!trades || trades.length === 0) {
    return '<div class="bt-trade-section">' +
      '<div class="card-label">📋 交易记录</div>' +
      '<div style="color:var(--text-3);text-align:center;padding:24px;">回测期间无交易</div>' +
      '</div>';
  }

  var rows = '';
  for (var i = 0; i < trades.length; i++) {
    var t = trades[i];
    var actionClass = (t.action === '买入') ? 'bt-buy' : 'bt-sell';
    var pnlStr = '';
    if (t.pnl_pct !== null && t.pnl_pct !== undefined) {
      var pnlColor = t.pnl_pct >= 0 ? 'color:#e53e3e;' : 'color:#38a169;';
      pnlStr = '<td class="num" style="' + pnlColor + '">' + (t.pnl_pct >= 0 ? '+' : '') + t.pnl_pct.toFixed(2) + '%</td>';
    } else {
      pnlStr = '<td class="num" style="color:#999;">--</td>';
    }

    rows += '<tr>' +
      '<td>' + escHtml(t.date) + '</td>' +
      '<td class="' + actionClass + '">' + escHtml(t.action) + '</td>' +
      '<td class="num">' + fmtBtPrice(t.price) + '</td>' +
      '<td class="num">' + (Math.round(t.amount || 0)).toLocaleString('zh-CN') + '</td>' +
      '<td class="num">' + fmtAccountBalance(t.equity - t.cash_after) + '</td>' +
      '<td class="num bt-balance">' + fmtAccountBalance(t.equity) + '</td>' +
      pnlStr +
      '<td class="bt-reason" title="' + escHtml(t.reason || '') + '">' + escHtml(t.reason || '') + '</td>' +
      '</tr>';
  }

  return '<div class="bt-trade-section">' +
    '<div class="card-label">📋 交易记录 (' + trades.length + ' 笔)' +
      '<span class="bt-legend">' +
        '<span class="legend-dot legend-buy"></span>买入' +
        '<span class="legend-dot legend-sell"></span>卖出' +
      '</span></div>' +
    '<div class="bt-trade-wrap">' +
    '<table class="bt-trade-table">' +
    '<thead><tr>' +
    '<th>日期</th><th>操作</th><th>价格</th><th>金额</th><th>持仓金额</th><th>余额</th><th>盈亏</th><th>原因</th>' +
    '</tr></thead>' +
    '<tbody>' + rows + '</tbody>' +
    '</table></div></div>';
}

// ── 多离场策略对比视图 ─────────────────────────────

// 按盈利金额（最终资产 − 初始资金）降序排列；并列保持原顺序（稳定）
function sortResultsByProfit(results, initialCapital) {
  return results.slice().sort(function(a, b) {
    var pa = (a.final_equity || 0) - (initialCapital || 0);
    var pb = (b.final_equity || 0) - (initialCapital || 0);
    if (pb !== pa) return pb - pa;
    return results.indexOf(a) - results.indexOf(b);
  });
}

function renderCompareExits(data) {
  if (!data || !data.exit_results || !data.exit_results.length) {
    showBtError('对比回测返回数据异常');
    return;
  }

  disposeBtCharts();
  $('btResults').style.display = 'block';
  $('btError').style.display = 'none';

  var results = sortResultsByProfit(data.exit_results, data.initial_capital);
  var bench = data.benchmark_curve || [];

  // 1. 摘要行
  var benchStart = bench.length ? bench[0].benchmark : data.initial_capital;
  var benchEnd = bench.length ? bench[bench.length - 1].benchmark : data.initial_capital;
  var benchRet = benchStart > 0 ? ((benchEnd - benchStart) / benchStart * 100).toFixed(2) : '--';
  var summaryHtml =
    '<div class="bt-summary">' +
      '<span><strong>' + escHtml(data.fund_name) + '</strong> (' + escHtml(data.fund_code) + ')</span>' +
      '<span>策略: ' + escHtml(data.entry_strategy_name || data.entry_strategy) + ' → ' + results.length + ' 个离场策略对比</span>' +
      '<span>' + escHtml(data.start_date) + ' ~ ' + escHtml(data.end_date) + '</span>' +
      '<span>初始 ¥' + data.initial_capital.toLocaleString() + ' · 基准收益 ' + benchRet + '%</span>' +
    '</div>';

  // 2. 权益曲线对比图
  var chartHtml =
    '<div class="bt-chart-container">' +
      '<div class="card-label">📈 权益曲线对比（' + results.length + ' 个离场策略）</div>' +
      '<div id="btEquityChart" class="bt-chart"></div>' +
    '</div>';

  // 3. 指标对比表
  var tableHtml = renderCompareTable(results);

  // 4. 每策略交易明细（可折叠）
  var detailsHtml = '';
  for (var i = 0; i < results.length; i++) {
    var r = results[i];
    detailsHtml += '<details class="bt-compare-trade-details">' +
      '<summary>' +
        '<span class="bt-exit-dot" style="background:' + (EXIT_COLORS[r.exit_strategy] || '#999') + ';"></span>' +
        escHtml(r.exit_strategy_name || r.exit_strategy) +
        '<span class="bt-cmp-trade-count">' + (r.trade_log ? r.trade_log.length : 0) + ' 笔</span>' +
      '</summary>' +
      renderTradeTable(r.trade_log || []) +
      '</details>';
  }

  $('btResults').innerHTML = summaryHtml + chartHtml + tableHtml +
    '<div class="bt-trade-section"><div class="card-label">📋 各策略交易明细</div>' + detailsHtml + '</div>';

  // 延迟渲染图表（等 DOM 就绪）
  setTimeout(function() {
    renderCompareChart(results, data);
  }, 150);
}

// 指标对比表：行为指标、列为策略，每行最优格高亮
function renderCompareTable(results) {

  // key: 取值路径（final_equity 为顶层字段，其余在 metrics 内）
  // dir: 1 = 越高越好（红加粗），-1 = 越低越好（绿加粗），0 = 不比较
  // sentinel: 999 → 盈亏比哨兵，显示 ∞ 且计最优
  var rows = [
    { key: 'final_equity', label: '最终资产', dir: 1, money: true },
    { key: 'total_return_pct', label: '累计收益', dir: 1, unit: '%', dp: 2 },
    { key: 'cagr_pct', label: '年化收益率', dir: 1, unit: '%', dp: 2 },
    { key: 'sharpe_ratio', label: '夏普比率', dir: 1, dp: 2 },
    { key: 'max_drawdown_pct', label: '最大回撤', dir: -1, unit: '%', dp: 2 },
    { key: 'max_drawdown_duration_days', label: '回撤持续(天)', dir: -1, dp: 0 },
    { key: 'win_rate_pct', label: '胜率', dir: 1, unit: '%', dp: 1 },
    { key: 'profit_factor', label: '盈亏比', dir: 1, dp: 2, sentinel: 999 },
    { key: 'total_trades', label: '交易次数', dir: 0, unit: '笔', dp: 0 },
    { key: 'alpha_pct', label: '超额α', dir: 1, unit: '%', dp: 2 },
  ];

  // 计算每行最优值（考虑方向与哨兵）
  var best = {};
  for (var ri = 0; ri < rows.length; ri++) {
    var r = rows[ri];
    if (r.dir === 0) continue;
    var bestScore = (r.dir === 1) ? -Infinity : Infinity;
    for (var i = 0; i < results.length; i++) {
      var v = (r.key === 'final_equity') ? results[i].final_equity : results[i].metrics[r.key];
      if (v === null || v === undefined) continue;
      var score = v;
      if (r.sentinel === 999 && v === 999) score = (r.dir === 1) ? Infinity : -Infinity;
      if (r.dir === 1) { if (score > bestScore) bestScore = score; }
      else { if (score < bestScore) bestScore = score; }
    }
    best[r.key] = bestScore;
  }

  // 列头（带颜色圆点）
  var head = '<tr><th class="bt-cmp-metric">指标</th>';
  for (var i = 0; i < results.length; i++) {
    var res = results[i];
    head += '<th><span class="bt-exit-dot" style="background:' + (EXIT_COLORS[res.exit_strategy] || '#999') + ';"></span>' +
      escHtml(res.exit_strategy_name || res.exit_strategy) + '</th>';
  }
  head += '</tr>';

  // 表体
  var body = '';
  for (var ri = 0; ri < rows.length; ri++) {
    var row = rows[ri];
    body += '<tr><td class="bt-cmp-metric">' + escHtml(row.label) + '</td>';
    for (var i = 0; i < results.length; i++) {
      var res = results[i];
      var v = (row.key === 'final_equity') ? res.final_equity : res.metrics[row.key];
      var cls = '';
      if (row.dir !== 0 && v !== null && v !== undefined) {
        if (v === best[row.key]) cls = 'bt-best-cell ' + (row.dir === 1 ? 'bt-best-up' : 'bt-best-down');
      }
      body += '<td class="' + cls + '">' + fmtCompareValue(row, v) + '</td>';
    }
    body += '</tr>';
  }

  return '<div class="bt-compare-wrap"><div class="card-label">📊 指标对比（红 = 该指标最优）</div>' +
    '<div class="bt-compare-scroll"><table class="bt-compare-table">' +
    '<thead>' + head + '</thead><tbody>' + body + '</tbody></table></div></div>';
}

function fmtCompareValue(row, v) {
  if (v === null || v === undefined || isNaN(v)) return '--';
  if (row.sentinel === 999 && v === 999) return '∞';
  if (row.money) return '¥' + Math.round(v).toLocaleString('zh-CN');
  var s = (row.dp !== undefined ? v.toFixed(row.dp) : String(v));
  if (row.unit === '%') s += '%';
  else if (row.unit === '笔') s += '笔';
  return s;
}

// 叠加权益曲线对比图
function renderCompareChart(results, data) {
  var dom = document.getElementById('btEquityChart');
  if (!dom) return;
  if (typeof echarts === 'undefined') {
    dom.innerHTML = '<div style="padding:40px;text-align:center;color:#999;">ECharts 加载中...</div>';
    return;
  }

  if (BT.compareChart) BT.compareChart.dispose();
  BT.compareChart = echarts.init(dom);

  var dates = (data.benchmark_curve || []).map(function(d) { return d.date; });
  var labelInterval = Math.max(1, Math.floor(dates.length / 12));

  var series = [];
  for (var i = 0; i < results.length; i++) {
    var r = results[i];
    series.push({
      name: r.exit_strategy_name || r.exit_strategy,
      type: 'line', smooth: true, symbol: 'none',
      data: r.equity_curve.map(function(p) { return p.equity; }),
      lineStyle: { color: EXIT_COLORS[r.exit_strategy] || '#999', width: 2 },
    });
  }
  series.push({
    name: '买入持有', type: 'line', smooth: true, symbol: 'none',
    data: (data.benchmark_curve || []).map(function(p) { return p.benchmark; }),
    lineStyle: { color: '#a0aec0', width: 1.5, type: 'dashed' },
  });

  BT.compareChart.setOption({
    tooltip: {
      trigger: 'axis',
      formatter: function(params) {
        var s = params[0].axisValue + '<br/>';
        for (var i = 0; i < params.length; i++) {
          s += params[i].marker + ' ' + params[i].seriesName + ': ¥' +
               Number(params[i].value).toLocaleString() + '<br/>';
        }
        return s;
      },
    },
    legend: { type: 'scroll', bottom: 0 },
    grid: { left: 70, right: 20, top: 20, bottom: 45 },
    xAxis: {
      type: 'category', data: dates,
      axisLabel: {
        interval: labelInterval,
        formatter: function(v) { return v ? v.slice(0, 7) : ''; },
        fontSize: 10,
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        formatter: function(v) {
          if (v >= 10000) return (v / 10000).toFixed(1) + '万';
          return v;
        },
      },
    },
    series: series,
  });

  // 响应式（复用 dashboard 的 addResize，处理 tab 显隐后自适应）
  if (typeof addResize === 'function') {
    addResize(dom, BT.compareChart);
  } else {
    window.addEventListener('resize', function() {
      if (BT.compareChart) BT.compareChart.resize();
    });
  }
}

// ── 离场策略说明面板 ─────────────────────────────

async function loadStrategyInfo() {
  var el = $('btStrategyInfo');
  if (!el) return;
  el.style.display = 'none';
  // 恰好勾选 1 个时展示说明面板，0 个或多个时隐藏
  var checked = getCheckedExits();
  if (checked.length !== 1) return;
  var info = await get('/strategy-info?exit_strategy=' + encodeURIComponent(checked[0]));
  if (!info || !info.exit) return;
  var s = info.exit;
  el.innerHTML =
    '<div class="bt-info-head" onclick="toggleBtInfo()">' +
      '<div>' +
        '<span class="bt-info-cat">' + escHtml(s.category || '') + '</span>' +
        '<span class="bt-info-title">' + escHtml(s.name) + '</span>' +
        '<div class="bt-info-tagline">' + escHtml(s.tagline || '') + '</div>' +
      '</div>' +
      '<button class="bt-info-toggle" id="btInfoToggle" type="button">▾</button>' +
    '</div>' +
    '<div class="bt-info-body" id="btInfoBody">' + md(s.description || '') + '</div>' +
    '<div class="bt-info-rules">📌 ' + escHtml(s.rules || '') + '</div>';
  el.classList.add('open');
  el.style.display = 'block';
}

function toggleBtInfo() {
  var el = $('btStrategyInfo');
  if (!el) return;
  el.classList.toggle('open');
  var btn = $('btInfoToggle');
  if (btn) btn.textContent = el.classList.contains('open') ? '▾' : '▸';
}

// 初始化：渲染复选框组；勾选变化时刷新说明面板
(function initBtStrategyInfo() {
  buildExitCheckboxes();
  var box = $('btExitCheckboxes');
  if (box) box.addEventListener('change', loadStrategyInfo);
  loadStrategyInfo();
})();
