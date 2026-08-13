/**
 * 观澜 v2 — 宏观仪表盘
 * 防御式 ECharts 初始化 + 骨架屏
 */

async function loadDash() {
  const data = await get('/dashboard');
  if (!data) {
    $('cycleName').textContent = '数据加载失败';
    _setDashTime('加载失败');
    return;
  }
  APP.dash = data;
  // 显示数据截止时间
  _setDashTime(data.last_updated || '');
  renderCycle(data);
  renderDataQualityBanner(data);
  renderIndicators(data.indicators);
  renderAlloc(data.allocation);
  // 图表延迟渲染，确保 DOM 可见
  setTimeout(() => {
    renderRose(data);
    renderQuad(data);
    renderCsi300PE(data);
    renderValuation(data);
  }, 50);

  // 推荐标的独立加载（不阻塞仪表盘主内容）
  loadRecommendations();

  // 资金流向独立加载（不阻塞仪表盘主内容）
  loadFundFlow();
}

function _setDashTime(lastUpdated) {
  var el = $('dashUpdateTime');
  if (!el) return;
  if (!lastUpdated) {
    el.textContent = '🕐 数据时间：--';
    return;
  }
  var d = new Date(lastUpdated);
  var timeStr = d.toLocaleString('zh-CN', { hour12: false });
  el.textContent = '🕐 数据截止：' + timeStr;
}

async function refreshDashNow() {
  var btn = $('btnRefreshDash');
  if (btn) {
    btn.textContent = '⏳ 刷新中...';
    btn.classList.add('loading');
  }
  var result = await post('/refresh/macro');
  if (btn) {
    btn.textContent = '🔄 刷新宏观数据';
    btn.classList.remove('loading');
  }
  if (result?.success) {
    APP.dash = null;
    await loadDash();
  } else {
    _setDashTime('刷新失败: ' + (result?.message || '未知错误'));
  }
}

// ── Cycle ───────────────────────────────────────

const ICONS = { '衰退期':'🔴','复苏期':'🟢','过热期':'🟡','滞胀期':'🔵' };

function renderCycle(d) {
  $('cycleBadge').textContent = ICONS[d.cycle] || '❓';
  $('cycleName').textContent = d.cycle;
  $('confVal').textContent = ((d.cycle_confidence||0)*100).toFixed(0) + '%';

  // 置信度备注：显示数据质量问题
  var meta = d.source_metadata || {};
  var defaultCount = 0, conflictCount = 0;
  for (var k in meta) {
    if (meta[k].source === 'default') defaultCount++;
    if (meta[k].conflict) conflictCount++;
  }
  var confNote = '';
  if (defaultCount > 0 || conflictCount > 0) {
    var parts = [];
    if (defaultCount > 0) parts.push(defaultCount + '默认');
    if (conflictCount > 0) parts.push(conflictCount + '冲突');
    confNote = ' (' + parts.join(', ') + ')';
  }
  var confSubEl = document.getElementById('confSub');
  if (confSubEl) confSubEl.textContent = confNote;

  // 增长/通胀动量 — 带颜色和箭头
  var gVal = d.growth_momentum || 0;
  var iVal = d.inflation_momentum || 0;
  var gSign = gVal >= 0 ? '+' : '';
  var iSign = iVal >= 0 ? '+' : '';
  var gColor = gVal >= 0.1 ? 'mtm-up' : gVal <= -0.1 ? 'mtm-down' : 'mtm-flat';
  var iColor = iVal >= 0.1 ? 'mtm-up' : iVal <= -0.1 ? 'mtm-down' : 'mtm-flat';
  var gArrow = gVal >= 0.1 ? ' ↗' : gVal <= -0.1 ? ' ↘' : ' →';
  var iArrow = iVal >= 0.1 ? ' ↗' : iVal <= -0.1 ? ' ↘' : ' →';

  $('gMtm').innerHTML = gSign + gVal.toFixed(3) + gArrow;
  $('gMtm').className = gColor;
  $('iMtm').innerHTML = iSign + iVal.toFixed(3) + iArrow;
  $('iMtm').className = iColor;

  renderExplain(d);
}

// ── Plain-language cycle explanation ────────────

const EXPLAIN = {
  '衰退期': `<strong>当前经济偏冷。</strong>增长放缓、物价走低。这个阶段央行通常会降息刺激经济，<strong>债券</strong>是最受益的资产——利息下降，债券价格上涨。防御性配置为主，少碰股票，多拿债券和货币基金。`,
  '复苏期': `<strong>经济正在回暖！</strong>增长开始加速，但物价还没大涨，这是对投资者最友好的阶段。企业盈利改善、利率还在低位，<strong>股票</strong>尤其是成长型股票往往表现最好。建议多配股票、少配现金。`,
  '过热期': `<strong>经济火热，但物价也涨得快了。</strong>大家都在担心通胀，央行可能会加息降温。这个阶段<strong>大宗商品</strong>（原油、铜、钢材）和<strong>黄金</strong>表现好——因为它们是实物资产，天然抗通胀。股票要减仓。`,
  '滞胀期': `<strong>最难受的阶段：增长不行，物价还涨。</strong>企业盈利下滑但成本上升，股市承压。这个时候<strong>现金为王</strong>——拿着现金等待机会，配一些黄金保值。尽量避免重仓股票和长久期债券。`,
};

function renderExplain(d) {
  const el = $('cycleExplain');
  if (!el) return;
  const growthSign = (d.growth_momentum||0) >=0 ? '加速' : '放缓';
  const inflSign = (d.inflation_momentum||0) >=0 ? '上升' : '走低';
  const explain = EXPLAIN[d.cycle] || '周期判断中...';
  el.innerHTML = explain + `<br><span style="font-size:.73rem;color:var(--text-3);">指标显示：增长<b>${growthSign}</b>，通胀<b>${inflSign}</b>。数据每日更新，仅供参考。</span>`;
}

// ── Data Quality Banner ─────────────────────────

function renderDataQualityBanner(d) {
  var banner = document.getElementById('dataQualityBanner');
  var textEl = document.getElementById('dataQualityText');
  if (!banner || !textEl) return;

  var warnings = d.quality_warnings || [];
  var meta = d.source_metadata || {};
  var defaultCount = 0;
  for (var k in meta) { if (meta[k].source === 'default') defaultCount++; }

  if (warnings.length > 0) {
    textEl.textContent = warnings.join('；');
    banner.style.display = 'flex';
    banner.className = 'data-quality-banner ' +
      (defaultCount >= 5 ? 'banner-critical' : 'banner-warning');
  } else {
    banner.style.display = 'none';
  }
}

function dismissQualityBanner() {
  var banner = document.getElementById('dataQualityBanner');
  if (banner) banner.style.display = 'none';
}

// ── Indicators ──────────────────────────────────

// 指标含义解释
var INDICATOR_EXPLAIN = {
  'cpi': '消费者物价指数，衡量一篮子商品服务的价格变化，反映居民消费端的通胀水平',
  'ppi': '工业生产者出厂价格指数，衡量工业品出厂价格变化，反映生产端的通胀压力',
  'pmi': '制造业采购经理人指数，50以上=经济扩张，50以下=收缩，是企业采购经理对经济的信心晴雨表',
  'm2': '广义货币供应量增速，反映市场上"钱"的增长速度，增速高=货币政策宽松',
  'gdp': '国内生产总值增速，衡量一国经济总量的增长速度，最核心的经济增长指标',
  'retail': '社会消费品零售总额增速，反映居民消费意愿和能力，是内需的晴雨表',
  'fai': '固定资产投资增速，反映企业建厂买设备的意愿，是投资需求的晴雨表',
  'unemploy': '城镇调查失业率，反映劳动力市场松紧程度，失业率低=经济健康',
  'caixin_pmi': '财新制造业PMI，由财新/Markit编制的独立PMI，样本偏重中小出口企业，与官方PMI互补对照',
};

function sourceLabel(src) {
  if (src === 'default') return '<span class="src-tag src-default">默认</span>';
  if (src === 'nbs') return '<span class="src-tag src-nbs">统计局</span>';
  if (src === 'chinadata') return '<span class="src-tag src-cd">第三方</span>';
  if (src === 'caixin') return '<span class="src-tag src-cx">财新</span>';
  return '';
}

function renderIndicators(list) {
  if (!list || !list.length) return;

  $('indicatorsRow').innerHTML = list.map(function(i) {
    var tc = i.trend==='up'?'t-up':i.trend==='down'?'t-down':'t-flat';
    var arrow = i.trend==='up'?'↑':i.trend==='down'?'↓':'→';
    var label = sourceLabel(i.source || '');
    var conflictIcon = i.conflict ? ' <span class="conflict-icon" title="来源间数据差异>10%">⚡</span>' : '';
    var explain = INDICATOR_EXPLAIN[i.code] || '';
    return '<div class="ind-card" title="' + explain + '">' +
      '<div class="ind-label">' + i.name + conflictIcon + '</div>' +
      '<div class="ind-val">' + i.value + i.unit + '</div>' +
      '<div class="ind-trend ' + tc + '">' + arrow + ' ' + label + '</div>' +
    '</div>';
  }).join('');
}

// ── Allocation list ─────────────────────────────

function renderAlloc(items) {
  if (!items?.length) return;
  const sorted = [...items].sort((a,b) => b.ratio - a.ratio);
  const rk = ['r1','r2','r3'];
  $('allocList').innerHTML = sorted.map((x,i) => {
    const pct = Math.round(x.ratio*100);
    return `<div class="alloc-row">
      <div class="alloc-rank ${rk[i]||''}">${i+1}</div>
      <div class="alloc-info">
        <div class="alloc-name">${x.asset}</div>
        <div class="alloc-reason">${x.reason||''}</div>
      </div>
      <div class="alloc-bar"><div class="alloc-bar-inner" style="width:${pct}%"></div></div>
      <div class="alloc-pct">${pct}%</div>
    </div>`;
  }).join('');
}

// ── Rose chart ──────────────────────────────────

function renderRose(d) {
  const dom = $('roseChart');
  if (!dom || typeof echarts === 'undefined') return;
  dom.innerHTML = '';  // clear skeleton

  const raw = d?.charts?.rose_data || d?.allocation || [];
  const data = Array.isArray(raw)
    ? raw.map(x => ({ name: x.asset||x.name, value: x.ratio ? Math.round(x.ratio*100) : (x.value||0) }))
    : [];

  if (!data.length) return;

  const ch = echarts.init(dom, null, { width: dom.clientWidth, height: dom.clientHeight||340 });
  ch.setOption({
    tooltip: { trigger:'item', formatter:'{b}: {c}%', backgroundColor:'#fff', borderColor:'#e8e8e0', textStyle:{color:'#1a1a1a',fontSize:13} },
    legend: { bottom:0, textStyle:{color:'#666',fontSize:10}, itemWidth:9, itemHeight:9 },
    series: [{
      type:'pie', radius:['28%','68%'], center:['50%','45%'], roseType:'area',
      itemStyle:{ borderRadius:5 },
      label: { color:'#666', fontSize:10, formatter:'{b}\n{d}%' },
      labelLine: { lineStyle:{ color:'#ddd' } },
      data,
      color: ['#2c5f2d','#4a9b4e','#7ebd57','#a8d878','#c9e8a0','#3b7fd4','#60a5fa','#e8b86d','#e0882e','#8898aa'],
    }]
  });
  addResize(dom, ch);
}

// ── Quadrant chart ──────────────────────────────

function renderQuad(d) {
  var dom = $('quadrantChart');
  if (!dom || typeof echarts === 'undefined') return;
  dom.innerHTML = '';

  var g = d.growth_momentum || 0;
  var inf = d.inflation_momentum || 0;
  var ch = echarts.init(dom, null, { width: dom.clientWidth, height: dom.clientHeight || 340 });

  // 象限背景色
  var quadColors = {
    '复苏': 'rgba( 76,175, 80,0.08)',  // 右上 (增长↑通胀↓) → 实际是左上
    '过热': 'rgba(244, 67, 54,0.08)',  // 右上 (增长↑通胀↑)
    '滞胀': 'rgba(255,152,  0,0.08)',  // 左上 → 实际是右下 (增长↓通胀↑)
    '衰退': 'rgba(158,158,158,0.08)',  // 左下 (增长↓通胀↓)
  };

  var quadrantAreas = [
    // 复苏: growth>0, inflation<0 (右下象限 → x>0, y<0)
    [{xAxis: 0, yAxis: -3.5}, {xAxis: 3.5, yAxis: 0}],
    // 过热: growth>0, inflation>0 (右上象限)
    [{xAxis: 0, yAxis: 0}, {xAxis: 3.5, yAxis: 3.5}],
    // 滞胀: growth<0, inflation>0 (左上象限)
    [{xAxis: -3.5, yAxis: 0}, {xAxis: 0, yAxis: 3.5}],
    // 衰退: growth<0, inflation<0 (左下象限)
    [{xAxis: -3.5, yAxis: -3.5}, {xAxis: 0, yAxis: 0}],
  ];

  ch.setOption({
    tooltip: {
      trigger: 'item',
      formatter: function(p) {
        if (p.seriesType === 'scatter') {
          return '<b>📍 当前位置</b><br/>增长动量: ' + g.toFixed(3) + '<br/>通胀动量: ' + inf.toFixed(3);
        }
        return '';
      },
      backgroundColor: '#fff',
      borderColor: '#e0e0d8',
      textStyle: { color: '#1a1a1a', fontSize: 12 }
    },
    xAxis: {
      name: '经济增长动量 →',
      nameLocation: 'center',
      nameGap: 28,
      nameTextStyle: { color: '#666', fontSize: 11, fontWeight: 'bold' },
      min: -3.5, max: 3.5,
      axisLine: { lineStyle: { color: '#ccc', width: 2 } },
      axisLabel: { color: '#999', fontSize: 9 },
      splitLine: { lineStyle: { color: '#f0f0ea', type: 'dashed' } },
    },
    yAxis: {
      name: '通胀动量 →',
      nameLocation: 'center',
      nameGap: 36,
      nameTextStyle: { color: '#666', fontSize: 11, fontWeight: 'bold' },
      min: -3.5, max: 3.5,
      axisLine: { lineStyle: { color: '#ccc', width: 2 } },
      axisLabel: { color: '#999', fontSize: 9 },
      splitLine: { lineStyle: { color: '#f0f0ea', type: 'dashed' } },
    },
    series: [
      // 象限背景
      {
        type: 'scatter',
        data: [],
        markArea: {
          silent: true,
          label: {
            fontSize: 13,
            fontWeight: 'bold',
            color: 'rgba(0,0,0,0.18)',
            position: 'inside',
            offset: [0, 0],
          },
          data: [
            [{ name: '复苏期', xAxis: 0.5, yAxis: -1.5, itemStyle: { color: quadColors['复苏'] } },
             { xAxis: 3.5, yAxis: -0.1 }],
            [{ name: '过热期', xAxis: 0.5, yAxis: 1.5, itemStyle: { color: quadColors['过热'] } },
             { xAxis: 3.5, yAxis: 3.5 }],
            [{ name: '滞胀期', xAxis: -1.8, yAxis: 1.5, itemStyle: { color: quadColors['滞胀'] } },
             { xAxis: -3.5, yAxis: 3.5 }],
            [{ name: '衰退期', xAxis: -1.8, yAxis: -1.5, itemStyle: { color: quadColors['衰退'] } },
             { xAxis: -3.5, yAxis: -3.5 }],
          ],
        },
      },
      // 原点十字参考线
      {
        type: 'scatter',
        data: [],
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#d0d0c8', width: 1, type: 'dashed' },
          data: [
            { xAxis: 0 },
            { yAxis: 0 },
          ],
        },
      },
      // 当前位置散点
      {
        type: 'scatter',
        symbolSize: 16,
        data: [[g * 3, inf * 3]],
        itemStyle: {
          color: '#2c5f2d',
          borderColor: '#fff',
          borderWidth: 2,
          shadowBlur: 16,
          shadowColor: 'rgba(44,95,45,0.4)',
        },
        label: {
          show: true,
          position: 'top',
          fontSize: 11,
          color: '#2c5f2d',
          fontWeight: 'bold',
          formatter: '📍 当前位置',
          offset: [0, -10],
        },
      },
    ],
  });

  addResize(dom, ch);

  // 下方解释文字
  renderQuadExplain(d);
}

// ── 四象限解释 ────────────────────────────────

var QUAD_EXPLAIN = {
  '复苏期': '<b>📈 复苏期</b>：增长加速 + 通胀温和。<br>经济走出低谷，盈利改善、利率低位。<br>✅ 最佳资产：<b>股票</b>（成长型）+ 债券',
  '过热期': '<b>🔥 过热期</b>：增长强劲 + 通胀上升。<br>经济火热，央行可能加息降温。<br>✅ 最佳资产：<b>大宗商品</b> + <b>黄金</b>',
  '滞胀期': '<b>💀 滞胀期</b>：增长放缓 + 通胀持续。<br>企业盈利下滑但成本上升，最难熬。<br>✅ 最佳资产：<b>现金</b> + <b>黄金</b>',
  '衰退期': '<b>🧊 衰退期</b>：增长萎缩 + 物价走低。<br>央行降息刺激，避险情绪主导。<br>✅ 最佳资产：<b>债券</b> + 货币基金',
};

function renderQuadExplain(d) {
  var el = document.getElementById('quadrantExplain');
  if (!el) return;

  var cycle = d.cycle || '';
  var g = d.growth_momentum || 0;
  var inf = d.inflation_momentum || 0;

  var gStatus = g >= 0.1 ? '扩张' : g <= -0.1 ? '收缩' : '持平';
  var iStatus = inf >= 0.1 ? '上升' : inf <= -0.1 ? '走低' : '持平';
  var gColor = g >= 0.1 ? '#4caf50' : g <= -0.1 ? '#f44336' : '#999';
  var iColor = inf >= 0.1 ? '#f44336' : inf <= -0.1 ? '#4caf50' : '#999';

  var explainHtml = QUAD_EXPLAIN[cycle] || '';
  el.innerHTML =
    '<div class="quad-summary">' +
      '<span>增长动量：<b style="color:' + gColor + '">' + g.toFixed(3) + '</b>（' + gStatus + '）</span>' +
      '<span class="dot-divider">·</span>' +
      '<span>通胀动量：<b style="color:' + iColor + '">' + inf.toFixed(3) + '</b>（' + iStatus + '）</span>' +
    '</div>' +
    '<div class="quad-explain">' + explainHtml + '</div>' +
    '<div class="quad-note">📍 位置 = 增长/通胀动量 × 3（放大便于观察）。数据每日更新，仅供参考。</div>';
}

function addResize(dom, ch) {
  const fn = () => { if (dom.offsetParent) ch.resize(); };
  window.addEventListener('resize', fn);
  new MutationObserver(() => { if (dom.offsetParent) ch.resize(); }).observe(dom, {attributes:true,attributeFilter:['style']});
}

// ── CSI300 PE Line Chart ─────────────────────────

function renderCsi300PE(data) {
  var dom = document.getElementById('csi300PeChart');
  if (!dom || typeof echarts === 'undefined') return;
  dom.innerHTML = '';

  var peData = (data && data.charts && data.charts.csi300_pe) || [];
  if (!peData.length) {
    dom.innerHTML = '<div class="chart-skeleton">暂无沪深300 PE 数据</div>';
    return;
  }

  var dates = peData.map(function(d) { return d.date; });
  var values = peData.map(function(d) { return d.pe; });

  var minPE = Math.floor(Math.min.apply(null, values) - 1);
  var maxPE = Math.ceil(Math.max.apply(null, values) + 1);
  var labelInterval = Math.max(1, Math.floor(dates.length / 12));

  var chart = echarts.init(dom, null, {
    width: dom.clientWidth,
    height: dom.clientHeight || 340
  });

  chart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#fff',
      borderColor: '#e8e8e0',
      textStyle: { color: '#1a1a1a', fontSize: 12 },
      formatter: function(p) {
        var item = p[0];
        return '<b>' + item.axisValue + '</b><br/>' +
               item.marker + ' 滚动市盈率: <b>' + item.value.toFixed(2) + '</b>';
      }
    },
    grid: { left: 55, right: 25, top: 20, bottom: 35 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        interval: labelInterval,
        fontSize: 10,
        color: '#999'
      },
      axisLine: { lineStyle: { color: '#e0e0d8' } },
    },
    yAxis: {
      type: 'value',
      name: 'PE',
      min: minPE,
      max: maxPE,
      nameTextStyle: { color: '#999', fontSize: 10 },
      axisLabel: { color: '#999', fontSize: 9 },
      splitLine: { lineStyle: { color: '#f0f0ea', type: 'dashed' } },
    },
    series: [{
      name: '沪深300 PE(TTM)',
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#3b7fd4', width: 2 },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(59,127,212,0.15)' },
          { offset: 1, color: 'rgba(59,127,212,0.02)' }
        ])
      },
      markLine: {
        silent: true,
        symbol: 'none',
        data: [
          {
            yAxis: values[values.length - 1],
            lineStyle: { color: '#e0882e', type: 'dashed', width: 1 },
            label: { fontSize: 10, color: '#e0882e', formatter: '当前 {c}' }
          },
          {
            yAxis: 12.5,
            lineStyle: { color: '#d94444', type: 'solid', width: 1.5 },
            label: { fontSize: 10, color: '#d94444', formatter: '中枢 {c}' }
          }
        ]
      }
    }]
  });

  addResize(dom, chart);
}

async function refreshCsi300PeNow() {
  var card = document.getElementById('csi300PeChart').parentElement;
  var btn = card.querySelector('.btn-refresh');
  if (btn) {
    btn.textContent = '⏳ 刷新中...';
    btn.classList.add('loading');
  }
  var result = await post('/refresh/csi300-pe');
  if (btn) {
    btn.textContent = '🔄 刷新';
    btn.classList.remove('loading');
  }
  if (result && result.success) {
    var data = await get('/dashboard');
    if (data) {
      APP.dash = data;
      renderCsi300PE(data);
    }
  }
}

// ── Valuation Thermometer ─────────────────────────

function renderValuation(data) {
  var container = document.getElementById('valuationContent');
  if (!container) return;

  var v = (data && data.valuation) || null;
  if (!v || !v.pe) {
    container.innerHTML = '<div class="loading-shimmer">估值数据暂不可用</div>';
    return;
  }

  // ERP 信号颜色
  var sigColor = v.signal === '超配' ? '#2c5f2d' : v.signal === '低配' ? '#d94444' : '#e0882e';
  var sigBg = v.signal === '超配' ? '#e8f5e9' : v.signal === '低配' ? '#fce4e4' : '#fef3e0';
  var sigIcon = v.signal === '超配' ? '🟢' : v.signal === '低配' ? '🔴' : '🟡';

  // 分位标签
  function pctLabel(pct) {
    if (pct <= 0.25) return '<span style="color:#2c5f2d;font-weight:600;">低估</span>';
    if (pct <= 0.50) return '<span style="color:#4a9b4e;">偏低</span>';
    if (pct <= 0.75) return '<span style="color:#e0882e;">偏高</span>';
    return '<span style="color:#d94444;font-weight:600;">高估</span>';
  }

  // 进度条方向：分位越低越偏左(绿色)，越高越偏右(红色)
  function pctBar(pct) {
    var pos = Math.round(pct * 100);
    var color = pct <= 0.25 ? '#2c5f2d' : pct <= 0.5 ? '#4a9b4e' : pct <= 0.75 ? '#e0882e' : '#d94444';
    return '<div style="background:#eee;border-radius:4px;height:8px;width:100%;margin:4px 0;">' +
      '<div style="background:' + color + ';border-radius:4px;height:8px;width:' + pos + '%;"></div>' +
      '</div><div style="font-size:.65rem;color:#999;">历史分位 ' + pos + '%</div>';
  }

  // ERP 说明
  var erpNote = '';
  if (v.signal === '超配') {
    erpNote = '股票相对债券极具吸引力，可在美林时钟配置基础上<span style="color:#2c5f2d;font-weight:600;">增配股票</span>';
  } else if (v.signal === '低配') {
    erpNote = '股票相对债券性价比低，建议在美林时钟基础上<span style="color:#d94444;font-weight:600;">减配股票</span>，增加债券/现金';
  } else {
    erpNote = '估值处于合理区间，<span style="color:#e0882e;">跟随美林时钟</span>标准配置即可';
  }

  // 双列还是三列取决于PB是否可用
  var hasPB = v.pb > 0;
  var gridCols = hasPB ? '1fr 1fr 1fr' : '1fr 1fr';

  container.innerHTML =
    '<div style="display:grid;grid-template-columns:' + gridCols + ';gap:12px;margin-bottom:12px;">' +
      // PE 分位
      '<div style="background:#f8f9fa;border-radius:8px;padding:12px;text-align:center;">' +
        '<div style="font-size:.7rem;color:#999;margin-bottom:4px;">沪深300 PE(TTM)</div>' +
        '<div style="font-size:1.4rem;font-weight:700;color:#1a1a1a;">' + v.pe.toFixed(1) + '</div>' +
        '<div style="font-size:.7rem;margin-top:2px;">' + pctLabel(v.pe_percentile) + '</div>' +
        pctBar(v.pe_percentile) +
      '</div>' +
      // ERP
      '<div style="background:#f8f9fa;border-radius:8px;padding:12px;text-align:center;">' +
        '<div style="font-size:.7rem;color:#999;margin-bottom:4px;">股债性价比(ERP)</div>' +
        '<div style="font-size:1.4rem;font-weight:700;color:#1a1a1a;">' + v.erp.toFixed(2) + '%</div>' +
        '<div style="font-size:.7rem;margin-top:2px;">10Y国债 ' + v.bond_10y.toFixed(2) + '%</div>' +
        '<div style="font-size:.65rem;color:#999;">ERP = 1/PE − 国债</div>' +
      '</div>' +
      (hasPB ?
        // PB 分位
        '<div style="background:#f8f9fa;border-radius:8px;padding:12px;text-align:center;">' +
          '<div style="font-size:.7rem;color:#999;margin-bottom:4px;">沪深300 PB</div>' +
          '<div style="font-size:1.4rem;font-weight:700;color:#1a1a1a;">' + v.pb.toFixed(2) + '</div>' +
          '<div style="font-size:.7rem;margin-top:2px;">' + pctLabel(v.pb_percentile) + '</div>' +
          pctBar(v.pb_percentile) +
        '</div>' : '') +
    '</div>' +
    // ERP 仓位信号
    '<div style="background:' + sigBg + ';border-radius:8px;padding:10px 14px;display:flex;align-items:center;gap:10px;">' +
      '<span style="font-size:1.2rem;">' + sigIcon + '</span>' +
      '<div>' +
        '<span style="font-weight:700;color:' + sigColor + ';">建议' + v.signal + '股票</span>' +
        '<span style="font-size:.7rem;color:#666;margin-left:6px;">' + erpNote + '</span>' +
      '</div>' +
    '</div>';
}

// ── Recommendations ──────────────────────────────

async function loadRecommendations() {
  const data = await get('/dashboard/recommendations');
  if (!data) {
    var content = document.getElementById('recommendationsContent');
    if (content) content.innerHTML = '<div class="rec-empty">推荐数据暂不可用</div>';
    return;
  }
  renderRecommendations(data);
}

function renderRecommendations(data) {
  var content = document.getElementById('recommendationsContent');
  if (!content) return;

  var cycle = data.cycle || '';
  var html = '';

  // ── ETF 推荐 ──
  var etfs = data.etf_recommendations || [];
  if (etfs.length > 0) {
    html += '<div class="rec-section">';
    html += '<div class="rec-section-title">📦 推荐 ETF</div>';
    html += '<div class="rec-etf-list">';
    for (var i = 0; i < etfs.length; i++) {
      var e = etfs[i];
      var pct = Math.round((e.allocation_pct || 0) * 100);
      html += '<div class="rec-etf-item">';
      html += '<span class="rec-etf-code">' + escHtml(e.etf_code) + '</span>';
      html += '<span class="rec-etf-name">' + escHtml(e.etf_name) + '</span>';
      html += '<span class="rec-etf-class">' + escHtml(e.asset_class) + ' ' + pct + '%</span>';
      html += '</div>';
    }
    html += '</div></div>';
  }

  // ── 优选股票 ──
  var stocks = data.top_stocks || [];
  if (stocks.length > 0) {
    html += '<div class="rec-section">';
    html += '<div class="rec-section-title">📈 优选股票 <span class="rec-section-note">（来自 Top 50 排名）</span></div>';
    html += '<div class="rec-stock-list">';
    for (var i = 0; i < stocks.length; i++) {
      var s = stocks[i];
      var scoreClass = s.score >= 0.7 ? 'score-good' : s.score >= 0.5 ? 'score-ok' : 'score-low';
      html += '<div class="rec-stock-item">';
      html += '<span class="rec-stock-rank">#' + (i + 1) + '</span>';
      html += '<span class="rec-stock-code">' + escHtml(s.code) + '</span>';
      html += '<span class="rec-stock-name">' + escHtml(s.name) + '</span>';
      html += '<span class="rec-stock-score ' + scoreClass + '">' + (s.score * 100).toFixed(0) + '分</span>';
      html += '<span class="rec-stock-sector">' + escHtml(s.sector || '') + '</span>';
      if (s.reason) {
        html += '<span class="rec-stock-reason">' + escHtml(s.reason) + '</span>';
      }
      html += '</div>';
    }
    html += '</div></div>';
  }

  // ── 策略信号 ──
  var strats = data.top_strategies || [];
  if (strats.length > 0) {
    html += '<div class="rec-section">';
    html += '<div class="rec-section-title">📊 当前策略信号</div>';
    html += '<div class="rec-strat-list">';
    for (var i = 0; i < strats.length; i++) {
      var st = strats[i];
      var sigIcon = st.signal === '买入' ? '🟢' : st.signal === '卖出' ? '🔴' : '🟡';
      html += '<div class="rec-strat-item">';
      html += '<span class="rec-strat-icon">' + sigIcon + '</span>';
      html += '<span class="rec-strat-name">' + escHtml(st.strategy_name) + '</span>';
      html += '<span class="rec-strat-sig">' + escHtml(st.signal) + ' (' + Math.round(st.confidence * 100) + '%)</span>';
      html += '<span class="rec-strat-reason">' + escHtml(st.one_liner || '') + '</span>';
      html += '</div>';
    }
    html += '</div></div>';
  }

  // ── 金牛奖推荐 ──
  var bull = data.golden_bull;
  if (bull && (bull.companies || []).length > 0) {
    html += '<div class="rec-section">';
    html += '<div class="rec-section-title">🏆 金牛奖基金公司 <span class="rec-section-note">（' + escHtml(bull.award_info || '') + '）</span></div>';

    // -- 获奖公司 --
    html += '<div class="rec-bull-subtitle">🏅 获奖基金公司</div>';
    html += '<div class="rec-bull-list">';
    var companies = bull.companies || [];
    for (var i = 0; i < companies.length; i++) {
      var c = companies[i];
      var isTop = c.award_level === 'company';
      html += '<div class="rec-bull-item' + (isTop ? ' rec-bull-top' : '') + '">';
      html += '<span class="rec-bull-medal">' + (isTop ? '🥇' : '🏅') + '</span>';
      html += '<span class="rec-bull-name">' + escHtml(c.name) + '</span>';
      html += '<span class="rec-bull-award">' + escHtml(c.award_name || '') + '</span>';
      if (c.award_category) {
        html += '<span class="rec-bull-cat">' + escHtml(c.award_category) + '</span>';
      }
      if (c.star_products && c.star_products.length > 0) {
        html += '<span class="rec-bull-products">明星产品: ' + escHtml(c.star_products.join(' · ')) + '</span>';
      }
      if (c.star_managers && c.star_managers.length > 0) {
        html += '<span class="rec-bull-managers">经理: ' + escHtml(c.star_managers.join(' · ')) + '</span>';
      }
      html += '</div>';
    }
    html += '</div>';

    // -- 获奖产品 --
    var products = bull.products || [];
    if (products.length > 0) {
      html += '<div class="rec-bull-subtitle">⭐ 获奖基金产品</div>';
      html += '<div class="rec-bull-list">';
      for (var i = 0; i < products.length; i++) {
        var p = products[i];
        html += '<div class="rec-bull-item rec-bull-prod">';
        html += '<span class="rec-bull-star">⭐</span>';
        html += '<span class="rec-bull-code">' + escHtml(p.fund_code || '') + '</span>';
        html += '<span class="rec-bull-name">' + escHtml(p.fund_name) + '</span>';
        html += '<span class="rec-bull-company">' + escHtml(p.company_name) + '</span>';
        html += '<span class="rec-bull-award-detail">' + escHtml(p.award_name || '') + '</span>';
        html += '</div>';
      }
      html += '</div>';
    }

    // -- 明星基金经理 --
    var managers = bull.managers || [];
    if (managers.length > 0) {
      html += '<div class="rec-bull-subtitle">👤 明星基金经理</div>';
      html += '<div class="rec-bull-list">';
      for (var i = 0; i < managers.length; i++) {
        var m = managers[i];
        html += '<div class="rec-bull-item rec-bull-mgr">';
        html += '<span class="rec-bull-mgr-icon">👤</span>';
        html += '<span class="rec-bull-name">' + escHtml(m.name) + '</span>';
        html += '<span class="rec-bull-company">' + escHtml(m.company_name) + '</span>';
        if (m.title) {
          html += '<span class="rec-bull-title">' + escHtml(m.title) + '</span>';
        }
        if (m.representative_funds && m.representative_funds.length > 0) {
          html += '<span class="rec-bull-funds">代表作: ' + escHtml(m.representative_funds.join(' · ')) + '</span>';
        }
        if (m.achievement) {
          html += '<span class="rec-bull-achieve">' + escHtml(m.achievement) + '</span>';
        }
        html += '</div>';
      }
      html += '</div>';
    }

    html += '</div>';  // end rec-section
  }

  if (!html) {
    html = '<div class="rec-empty">暂无推荐数据，请刷新宏观数据后重试</div>';
  }

  // 添加数据质量提示
  var dashData = APP.dash || {};
  var meta = dashData.source_metadata || {};
  var defaultCount = 0;
  for (var k in meta) { if (meta[k].source === 'default') defaultCount++; }
  if (defaultCount >= 3) {
    html += '<div class="rec-disclaimer">⚠️ 当前较多指标使用默认值，推荐标的仅供参考</div>';
  }

  content.innerHTML = html;
}

// ── Fund Flow ──────────────────────────────────────

function _setFundFlowTime(ts) {
  var el = document.getElementById('fundFlowTime');
  if (!el) return;
  if (!ts) { el.textContent = '--'; return; }
  var d = new Date(ts);
  var timeStr = d.toLocaleString('zh-CN', { hour12: false });
  el.textContent = '🕐 ' + timeStr;
}

async function loadFundFlow() {
  var data = await get('/fund-flow');
  if (!data || data.error) {
    var card = document.getElementById('fundFlowCard');
    if (card) card.style.display = 'none';
    return;
  }
  APP.fundFlow = data;
  _setFundFlowTime(data.generated_at || '');
  setTimeout(function () {
    renderSectorFlow(data.industries || []);
    renderStockFlow(data.individuals || []);
  }, 80);
}

async function refreshFundFlowNow() {
  var btns = document.querySelectorAll('#fundFlowCard .btn-refresh');
  btns.forEach(function (b) {
    b.textContent = '⏳ 刷新中...';
    b.classList.add('loading');
  });
  var result = await post('/refresh/fund-flow');
  btns.forEach(function (b) {
    b.textContent = '🔄 刷新';
    b.classList.remove('loading');
  });
  if (result && result.success) {
    await loadFundFlow();
  }
}

function renderSectorFlow(industries) {
  var dom = document.getElementById('sectorFlowChart');
  if (!dom || typeof echarts === 'undefined') return;
  dom.innerHTML = '';

  if (!industries.length) {
    dom.innerHTML = '<div class="chart-skeleton">暂无行业资金流数据</div>';
    return;
  }

  // 按净额排序，取 Top 20 流入 + Bottom 20 流出
  var sorted = industries.slice().sort(function (a, b) { return b.net - a.net; });
  var top20 = sorted.slice(0, 20);
  var bottom20 = sorted.slice(-20).reverse();

  // 从最大流出 → 最大流入排列（X 轴从左到右）
  var chartData = bottom20.concat(top20);
  var names = chartData.map(function (s) { return s.name; });
  var values = chartData.map(function (s) { return s.net; });
  var barColors = chartData.map(function (s) {
    return s.net >= 0 ? '#d94444' : '#2c5f2d';
  });

  var ch = echarts.init(dom, null, { width: dom.clientWidth, height: dom.clientHeight || 500 });
  ch.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: '#e8e8e0',
      textStyle: { color: '#1a1a1a', fontSize: 12 },
      formatter: function (p) {
        var d = p[0];
        var name = d.name;
        var net = d.value;
        var sign = net >= 0 ? '+' : '';
        var sector = industries.find(function (x) { return x.name === name; });
        var inflow = sector ? sector.inflow : '--';
        var outflow = sector ? sector.outflow : '--';
        var chg = sector ? (sector.change_pct >= 0 ? '+' : '') + sector.change_pct + '%' : '--';
        return '<b>' + name + '</b><br/>' +
               '净流入: ' + sign + net.toFixed(2) + ' 亿<br/>' +
               '流入: ' + inflow + ' 亿 | 流出: ' + outflow + ' 亿<br/>' +
               '涨跌: ' + chg + ' | 公司: ' + (sector ? sector.company_count : '--') + ' 家';
      }
    },
    grid: { left: 50, right: 20, top: 15, bottom: 60 },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { color: '#444', fontSize: 10, rotate: 45 },
      axisLine: { lineStyle: { color: '#e0e0d8' } },
      axisTick: { alignWithLabel: true },
    },
    yAxis: {
      type: 'value',
      name: '净流入（亿元）',
      nameTextStyle: { color: '#999', fontSize: 10 },
      axisLabel: { color: '#999', fontSize: 9 },
      splitLine: { lineStyle: { color: '#f0f0ea', type: 'dashed' } },
    },
    series: [{
      type: 'bar',
      data: values.map(function (v) {
        return {
          value: v,
          itemStyle: {
            color: v >= 0 ? '#d94444' : '#2c5f2d',
            borderRadius: v >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4],
          },
        };
      }),
      barMaxWidth: 14,
    }],
  });
  addResize(dom, ch);
}

function renderStockFlow(individuals) {
  var dom = document.getElementById('stockFlowChart');
  if (!dom || typeof echarts === 'undefined') return;
  dom.innerHTML = '';

  if (!individuals.length) {
    dom.innerHTML = '<div class="chart-skeleton">暂无个股资金流数据</div>';
    return;
  }

  // 取净流入 Top 20
  var top20 = individuals.slice(0, 20);
  var names = top20.map(function (s) {
    return s.name.length > 6 ? s.name.substring(0, 6) + '..' : s.name;
  });
  var values = top20.map(function (s) { return s.net; });

  var ch = echarts.init(dom, null, { width: dom.clientWidth, height: dom.clientHeight || 400 });
  ch.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#fff',
      borderColor: '#e8e8e0',
      textStyle: { color: '#1a1a1a', fontSize: 12 },
      formatter: function (p) {
        var idx = p[0].dataIndex;
        var s = top20[idx];
        var chg = (s.change_pct >= 0 ? '+' : '') + s.change_pct + '%';
        return '<b>' + s.code + ' ' + s.name + '</b><br/>' +
               '最新价: ' + s.price.toFixed(2) + ' (' + chg + ')<br/>' +
               '流入: ' + s.inflow.toFixed(2) + ' 亿<br/>' +
               '流出: ' + s.outflow.toFixed(2) + ' 亿<br/>' +
               '净额: ' + (s.net >= 0 ? '+' : '') + s.net.toFixed(4) + ' 亿<br/>' +
               '成交额: ' + s.turnover.toFixed(2) + ' 亿';
      }
    },
    grid: { left: 50, right: 20, top: 15, bottom: 60 },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { color: '#444', fontSize: 10, rotate: 30 },
      axisLine: { lineStyle: { color: '#e0e0d8' } },
    },
    yAxis: {
      type: 'value',
      name: '净流入（亿元）',
      nameTextStyle: { color: '#999', fontSize: 10 },
      axisLabel: { color: '#999', fontSize: 9 },
      splitLine: { lineStyle: { color: '#f0f0ea', type: 'dashed' } },
    },
    series: [{
      type: 'bar',
      data: values.map(function (v) {
        return {
          value: v,
          itemStyle: {
            color: v >= 0 ? '#d94444' : '#2c5f2d',
            borderRadius: v >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4],
          },
        };
      }),
      barMaxWidth: 18,
    }],
  });
  addResize(dom, ch);
}
