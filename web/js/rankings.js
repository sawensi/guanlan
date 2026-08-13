/**
 * 观澜 — 每日选股排名（双榜：全量 + 民企）
 */

async function loadRankings() {
  const data = await get('/rankings');
  if (!data || (!data.rankings_all?.length && !data.rankings?.length)) {
    document.getElementById('rankingsTableWrapAll').innerHTML =
      '<p style="color:var(--text-3);text-align:center;padding:40px;">暂无排名数据<br><small>系统将在每日15:30自动更新</small></p>';
    document.getElementById('rankingsTableWrap').innerHTML = '';
    return;
  }
  APP.rankings = data;
  renderRankings(data);
}

// 金融板块列表
var FINANCIAL_SECTORS = ['银行Ⅱ', '证券Ⅱ', '保险Ⅱ', '多元金融'];

function _buildTable(rankings, metaElId, tableWrapId, extraMeta) {
  if (!rankings || !rankings.length) {
    document.getElementById(tableWrapId).innerHTML =
      '<p style="color:var(--text-3);text-align:center;padding:20px;">暂无符合条件的股票</p>';
    return;
  }

  var html = '<table class="ranking-table">' +
    '<thead><tr>' +
      '<th>#</th><th>代码</th><th>名称</th><th>行业</th><th class="num">PB</th><th class="num">PE</th>' +
      '<th class="num">营收增长</th><th class="num">毛利率</th><th class="num">净利率</th>' +
      '<th class="num">健康度</th><th class="num">综合评分</th><th class="num">调整评分</th>' +
    '</tr></thead><tbody>';

  rankings.forEach(function(s, i) {
    var score = (s.composite_score * 100).toFixed(1);
    var scoreClass = '';
    if (score >= 80) scoreClass = 'score-high';
    else if (score >= 60) scoreClass = 'score-mid';
    else scoreClass = 'score-low';

    var health = s.financial_health;
    var healthDisplay = '--';
    var healthClass = '';
    if (health != null) {
      healthDisplay = (health * 100).toFixed(0) + '%';
      if (health >= 0.9) healthClass = 'score-high';
      else if (health >= 0.7) healthClass = 'score-mid';
      else healthClass = 'score-low';
    }
    var flagIcon = '';
    if (s.health_flags && s.health_flags.length > 0) {
      flagIcon = ' <span class="health-warn-icon" title="' +
        s.health_flags.join('; ') + '">⚠️</span>';
    }
    var adjScore = '--';
    if (s.adjusted_score != null) {
      adjScore = (s.adjusted_score * 100).toFixed(1);
    }

    var sector = s.sector || '--';
    var isFinancial = FINANCIAL_SECTORS.indexOf(sector) >= 0;
    var sectorClass = isFinancial ? 'sector-badge sector-financial' : 'sector-badge';

    html += '<tr>' +
      '<td class="rank-num">' + (i + 1) + '</td>' +
      '<td class="code">' + s.code + '</td>' +
      '<td class="name">' + s.name + '</td>' +
      '<td><span class="' + sectorClass + '">' + sector + '</span></td>' +
      '<td class="num">' + fmtNum(s.pb) + '</td>' +
      '<td class="num">' + fmtNum(s.pe) + '</td>' +
      '<td class="num">' + fmtPct(s.revenue_growth) + '</td>' +
      '<td class="num">' + fmtPct(s.gross_margin) + '</td>' +
      '<td class="num">' + fmtPct(s.net_margin) + '</td>' +
      '<td class="num ' + healthClass + '">' + healthDisplay + flagIcon + '</td>' +
      '<td class="num score ' + scoreClass + '">' + score + '</td>' +
      '<td class="num score">' + adjScore + '</td>' +
    '</tr>';
  });

  html += '</tbody></table>';
  document.getElementById(tableWrapId).innerHTML = html;
}

function renderRankings(d) {
  var period = d.data_period || '';
  var periodStr = period ? ' · 财报：' + period : '';
  var genTime = '';
  if (d.generated_at) {
    var gd = new Date(d.generated_at);
    genTime = ' · 🕐 ' + gd.toLocaleString('zh-CN', { hour12: false });
  }

  // 全量榜 meta
  document.getElementById('rankingsMetaAll').textContent =
    '📅 ' + (d.date || '--') + ' · 筛选 ' + (d.total_all || 0) + ' 只' + periodStr + genTime;

  // 民企榜 meta
  var soeCount = d.soe_excluded;
  var finCount = d.fin_excluded;
  var filterStr = '';
  if (soeCount != null && finCount != null) {
    filterStr = ' · 去国企 ' + soeCount + ' 只' + ' · 去金融 ' + finCount + ' 只';
  }
  document.getElementById('rankingsMeta').textContent =
    '📅 ' + (d.date || '--') + ' · 筛选 ' + (d.total_filtered || 0) + ' 只' + filterStr + periodStr + genTime;

  // 渲染两张表
  _buildTable(d.rankings_all, 'rankingsMetaAll', 'rankingsTableWrapAll');
  _buildTable(d.rankings, 'rankingsMeta', 'rankingsTableWrap');
}

function fmtNum(v) {
  if (v == null || isNaN(v)) return '--';
  return parseFloat(v).toFixed(2);
}

function fmtPct(v) {
  if (v == null || isNaN(v)) return '--';
  return parseFloat(v).toFixed(1) + '%';
}

async function refreshRankingsNow() {
  const btn = document.getElementById('btnRefreshRankings');
  const metaEl = document.getElementById('rankingsMeta');

  if (btn) {
    btn.textContent = '⏳ 刷新中...';
    btn.classList.add('loading');
  }

  const result = await post('/refresh/rankings');

  if (btn) {
    btn.textContent = '🔄 刷新';
    btn.classList.remove('loading');
  }

  if (result?.success) {
    APP.rankings = null;
    await loadRankings();
    if (metaEl) {
      metaEl.textContent += ' · ✅ 已刷新';
      setTimeout(function() {
        if (APP.rankings) {
          renderRankings(APP.rankings);
        }
      }, 3000);
    }
  } else {
    var msg = result?.message || '未知错误';
    if (metaEl) {
      metaEl.textContent = (metaEl.textContent || '') + ' · ⚠️ ' + msg;
      setTimeout(function() {
        if (APP.rankings) renderRankings(APP.rankings);
      }, 5000);
    }
    console.warn('Rankings refresh failed:', msg);
  }
}

// ── 权重滑块 ──────────────────────────────

function onWeightChange() {
  var sliders = document.querySelectorAll('#weightSliders input[type=range]');
  var total = 0;
  sliders.forEach(function(s) { total += parseInt(s.value); });
  sliders.forEach(function(s, i) {
    var pct = total > 0 ? Math.round(s.value / total * 100) : 0;
    s.parentElement.querySelector('span').textContent = pct + '%';
  });
}

async function applyWeights() {
  var sliders = document.querySelectorAll('#weightSliders input[type=range]');
  var weights = [];
  sliders.forEach(function(s) { weights.push(parseInt(s.value) / 100); });

  var btn = document.getElementById('btnApplyWeights');
  btn.textContent = '⏳ 重新计算中...';
  btn.disabled = true;

  try {
    var resp = await fetch('/guanlan/api/rankings/recompute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weights: weights }),
    });
    var data = await resp.json();
    if (data && (data.rankings_all?.length || data.rankings?.length)) {
      APP.rankings = data;
      renderRankings(data);
      document.getElementById('rankingsMeta').textContent += ' · ✅ 权重已更新';
    }
  } catch(e) {
    console.warn('Recompute failed:', e);
  }
  btn.textContent = '应用权重重新排名';
  btn.disabled = false;
}
