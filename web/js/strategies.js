/**
 * 观澜 v3 — 量化策略
 * 展示策略信号 + 更新时间 + 调仓频率
 */

// 当前策略标签: 'entry' | 'exit'
var STRAT_TAB = 'entry';

function switchStrategyTab(tab) {
  STRAT_TAB = tab;
  var tabEntry = $('tabEntry');
  var tabExit = $('tabExit');
  var stratsList = $('strategiesList');
  var exitsContainer = $('exitsContainer');
  var stratStatusBar = $('stratStatusBar');
  var decisionOverview = $('decisionOverview');

  if (tab === 'entry') {
    tabEntry.classList.add('active');
    tabExit.classList.remove('active');
    stratsList.style.display = '';
    exitsContainer.style.display = 'none';
    stratStatusBar.style.display = '';
    if (decisionOverview) decisionOverview.style.display = '';
    if (!APP.strats) { loadStrats(); }
    loadDecisionOverview();
  } else {
    tabEntry.classList.remove('active');
    tabExit.classList.add('active');
    stratsList.style.display = 'none';
    exitsContainer.style.display = '';
    stratStatusBar.style.display = 'none';
    if (decisionOverview) decisionOverview.style.display = 'none';
    // 自动加载（如果还没加载过）
    if (!EXIT_STATE || !EXIT_STATE.data) {
      applyExitParams();
    }
  }
}

async function loadStrats() {
  const data = await get('/strategies');
  if (!data?.strategies?.length) {
    // 兼容旧版数组格式
    if (Array.isArray(data) && data.length) {
      APP.strats = { strategies: data, last_updated: '' };
      renderStrats(APP.strats);
      return;
    }
    $('strategiesList').innerHTML =
      '<div style="color:var(--text-3);text-align:center;padding:40px;">策略数据加载失败</div>';
    return;
  }
  APP.strats = data;
  renderStrats(data);
}

// ── 信号一致性面板 ──────────────────────────────

async function loadDecisionOverview() {
  const el = $('decisionOverview');
  if (!el) return;
  const data = await get('/decision-overview');
  if (!data || !data.entry_consensus) {
    el.innerHTML = '';
    return;
  }
  renderDecisionOverview(data);
}

function renderDecisionOverview(data) {
  const el = $('decisionOverview');
  if (!el) return;
  const ec = data.entry_consensus || {};
  const v = data.valuation || {};

  const bullish = ec.consensus === '偏多共识';
  const bearish = ec.consensus === '偏空共识';
  const sigColor = bullish ? '#2c5f2d' : bearish ? '#d94444' : '#e0882e';
  const sigBg = bullish ? '#e8f5e9' : bearish ? '#fce4e4' : '#fef3e0';
  const sigIcon = bullish ? '🟢' : bearish ? '🔴' : '🟡';

  const badgeMap = { '买入':'badge-buy', '卖出':'badge-sell', '持有':'badge-hold', '观望':'badge-wait' };

  const votesHtml = (ec.votes || []).map(function(x) {
    return '<span style="display:inline-flex;align-items:center;gap:4px;background:#f5f6f8;border-radius:14px;padding:3px 10px;font-size:.78rem;">' +
      '<span class="badge ' + (badgeMap[x.signal] || 'badge-wait') + '">' + escHtml(x.signal) + '</span>' +
      escHtml(x.strategy_name) + ' · ' + Math.round((x.confidence || 0) * 100) + '%</span>';
  }).join('');

  const reasonsHtml = (ec.key_reasons || []).map(function(r) {
    return '<li style="margin:3px 0;">' + escHtml(r) + '</li>';
  }).join('');

  const posLine = (v.equity_weight > 0 ? ' · 建议股票仓位 ' + Math.round(v.equity_weight) + '%' : '');

  el.innerHTML =
    '<div style="background:#fff;border:1px solid #eee;border-radius:12px;padding:14px 16px;margin-bottom:14px;">' +
      '<div style="display:flex;align-items:center;gap:10px;background:' + sigBg + ';border-radius:8px;padding:10px 14px;">' +
        '<span style="font-size:1.3rem;">' + sigIcon + '</span>' +
        '<div style="flex:1;">' +
          '<div style="font-weight:700;color:' + sigColor + ';">入场信号一致性 · ' + escHtml(ec.consensus) + '（' + (ec.score != null ? ec.score : '--') + '分）</div>' +
          '<div style="font-size:.78rem;color:#666;">' + escHtml(ec.recommendation || '') +
            ' · 周期 ' + escHtml(data.cycle || '—') + posLine + '</div>' +
        '</div>' +
      '</div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">' + votesHtml + '</div>' +
      (reasonsHtml ? '<ul style="margin:10px 0 0 18px;font-size:.78rem;color:#555;">' + reasonsHtml + '</ul>' : '') +
    '</div>';
}

function _setStratTime(lastUpdated) {
  var el = $('stratUpdateTime');
  if (!el) return;
  if (!lastUpdated) {
    el.textContent = '🕐 信号时间：--';
    return;
  }
  var d = new Date(lastUpdated);
  var timeStr = d.toLocaleString('zh-CN', { hour12: false });
  el.textContent = '🕐 信号时间：' + timeStr;
}

async function refreshStratsNow() {
  var btn = $('btnRefreshStrats');
  if (btn) {
    btn.textContent = '⏳ 刷新中...';
    btn.classList.add('loading');
  }
  var result = await post('/refresh/strategies');
  if (btn) {
    btn.textContent = '🔄 刷新策略信号';
    btn.classList.remove('loading');
  }
  if (result?.success) {
    APP.strats = null;
    await loadStrats();
  } else {
    _setStratTime('刷新失败: ' + (result?.message || '未知错误'));
  }
}

function renderStrats(data) {
  var list = data.strategies || [];
  var lastUpdated = data.last_updated || '';
  var sigMap = { '买入':'badge-buy','卖出':'badge-sell','持有':'badge-hold','观望':'badge-wait' };

  // 更新顶部状态栏时间
  _setStratTime(lastUpdated);

  // 格式化更新时间（卡片区内的小提示）
  var updateHtml = '';
  if (lastUpdated) {
    var d = new Date(lastUpdated);
    var timeStr = d.toLocaleString('zh-CN', { hour12: false });
    updateHtml = '<div class="strategies-update">📡 数据基于 ' + timeStr + ' 的市场快照</div>';
  }

  // 频率说明映射
  var freqLabelMap = {
    '每天看一次': '每日更新',
    '每天检查': '每日更新',
    '每周调一次': '每周更新',
    '每月调一次': '每月更新',
    '每月执行一次': '每月更新',
    '每季度调一次': '每季度更新',
    '每季度检视一次': '每季度更新'
  };

  var cardsHtml = list.map(function(s, i) {
    var sig = s.current_signal || {};
    var sc = sigMap[sig.signal] || 'badge-wait';
    var freq = s.frequency || '--';
    var freqLabel = freqLabelMap[freq] || freq;

    return '<div class="strat-card" id="sc-' + s.id + '" onclick="toggleStrat(\'' + s.id + '\')">' +
      '<div class="strat-head">' +
        '<div>' +
          '<div class="strat-title">' + (i+1) + '. ' + s.name + '</div>' +
          '<div class="strat-sub">' + s.tagline + '</div>' +
        '</div>' +
        '<div class="strat-badges">' +
          '<span class="badge ' + sc + '">' + (sig.signal||'--') + '</span>' +
          '<span class="badge badge-freq">' + freqLabel + '</span>' +
          '<span class="badge badge-risk">风险' + (s.risk_level||'--') + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="strat-body">' +
        md(s.description||'') +
        '<div class="strat-signal">' +
          '<div class="sig-head">📶 当前信号 · 调仓频率: ' + freq + ' · 适用周期: ' + (s.suitable_cycle||[]).join(' / ') + '</div>' +
          '<div class="sig-body">' +
            '<strong style="color:' + (sig.signal==='买入'?'var(--green)':sig.signal==='卖出'?'var(--red)':'var(--blue)') + '">【' + (sig.signal||'--') + '】</strong>' +
            ' 置信度 ' + ((sig.confidence||0)*100).toFixed(0) + '%' +
            ' &nbsp;—&nbsp; ' + (sig.reasoning||'') +
          '</div>' +
        '</div>' +
        renderEtfPicks(s.etf_picks||[]) +
      '</div>' +
    '</div>';
  }).join('');

  $('strategiesList').innerHTML =
    '<div class="strategies-list">' + updateHtml + cardsHtml + '</div>';
}

function renderEtfPicks(etfs) {
  if (!etfs || !etfs.length) return '';
  var items = etfs.map(function(e) {
    return '<span class="etf-tag">' + e.name + ' <code>' + e.code + '</code></span>';
  }).join(' ');
  return '<div class="strat-etf">🛒 推荐标的：' + items + '</div>';
}

function toggleStrat(id) {
  var card = document.getElementById('sc-' + id);
  if (!card) return;
  var was = card.classList.contains('open');
  document.querySelectorAll('.strat-card').forEach(function(c) { c.classList.remove('open'); });
  if (!was) {
    card.classList.add('open');
    card.scrollIntoView({ behavior:'smooth', block:'nearest' });
  }
}
