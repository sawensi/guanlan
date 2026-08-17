/**
 * 观澜 — 当日持仓优化建议
 * 输入持仓列表（代码+收益率+建仓时间），综合离场策略 + 定投档位 + 估值 + 技术面
 * 输出每只基金的加仓/持有/减仓/清仓建议。持仓保存在浏览器 localStorage。
 */

var HOLDINGS_KEY = 'guanlan.holdings';

// ── 本地持久化 ─────────────────────────────────

function readHoldings() {
  try {
    var raw = localStorage.getItem(HOLDINGS_KEY);
    if (!raw) return [];
    var arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch (e) {
    return [];
  }
}

function saveHoldings() {
  try {
    localStorage.setItem(HOLDINGS_KEY, JSON.stringify(collectHoldings()));
  } catch (e) { /* 隐私模式等场景忽略 */ }
}

// ── 编辑器 ─────────────────────────────────────

function loadHoldings() {
  APP.holdings = true;
  var rowsEl = $('holdingsRows');
  if (!rowsEl) return;
  rowsEl.innerHTML = '';
  var saved = readHoldings();
  if (saved.length === 0) {
    addHoldingRow();
  } else {
    saved.forEach(function (h) {
      addHoldingRow(h.fund_code, h.return_rate, h.entry_date);
    });
  }
}

function addHoldingRow(fund_code, return_rate, entry_date) {
  var rowsEl = $('holdingsRows');
  if (!rowsEl) return;
  var row = document.createElement('div');
  row.className = 'holdings-row';
  row.innerHTML =
    '<input class="holdings-input holdings-col-code" type="text" list="btEtfList" placeholder="如 510300" value="' + escHtml(fund_code || '') + '">' +
    '<input class="holdings-input holdings-col-return" type="number" step="0.1" placeholder="如 12.5" value="' + escHtml(return_rate != null ? return_rate : '') + '">' +
    '<input class="holdings-input holdings-col-date" type="date" value="' + escHtml(entry_date || '') + '">' +
    '<button type="button" class="holdings-del" onclick="removeHoldingRow(this)" title="删除该持仓">×</button>';
  rowsEl.appendChild(row);
  row.querySelectorAll('input').forEach(function (inp) {
    inp.addEventListener('input', saveHoldings);
    inp.addEventListener('change', saveHoldings);
  });
}

function removeHoldingRow(btn) {
  var row = btn.parentNode;
  row.parentNode.removeChild(row);
  saveHoldings();
  if ($('holdingsRows').children.length === 0) addHoldingRow();
}

function collectHoldings() {
  var rows = $('holdingsRows').children;
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var inputs = rows[i].querySelectorAll('input');
    var code = (inputs[0].value || '').trim();
    if (!code) continue; // 空行跳过
    var ret = inputs[1].value;
    var date = inputs[2].value;
    out.push({
      fund_code: code,
      return_rate: ret === '' ? null : parseFloat(ret),
      entry_date: date || null
    });
  }
  return out;
}

// ── 查询 ───────────────────────────────────────

async function queryAdvice() {
  var errEl = $('holdingsError');
  var resEl = $('holdingsResults');
  errEl.style.display = 'none';
  resEl.style.display = 'none';

  var holdings = collectHoldings();
  if (holdings.length === 0) {
    errEl.textContent = '请至少输入一只持仓的基金代码';
    errEl.style.display = 'block';
    return;
  }
  saveHoldings();

  var btn = $('holdingsQueryBtn');
  btn.textContent = '⏳ 分析中...';
  btn.disabled = true;

  var data = await post('/position-optimization', { holdings: holdings });

  btn.textContent = '▶ 查询当日建议';
  btn.disabled = false;

  if (!data) {
    errEl.textContent = '请求失败，请稍后重试';
    errEl.style.display = 'block';
    return;
  }
  renderAdvice(data);
}

// ── 渲染 ───────────────────────────────────────

var ACTION_MAP = {
  '加仓': { badge: 'badge-buy',  color: '#2c5f2d', bg: '#e8f5e9', icon: '🟢' },
  '持有': { badge: 'badge-hold', color: '#3b7fd4', bg: '#e8eff8', icon: '🔵' },
  '减仓': { badge: 'badge-wait', color: '#e0882e', bg: '#fef3e0', icon: '🟠' },
  '清仓': { badge: 'badge-sell', color: '#d94444', bg: '#fce4e4', icon: '🔴' },
  '数据不足': { badge: 'badge-wait', color: '#999999', bg: '#f0f0ea', icon: '⚪' }
};
var DCA_TIER_COLOR = { '加码': '#2c5f2d', '正常': '#2f6fed', '减码': '#e0882e', '暂停': '#d94444' };
var DCA_TIER_BG = { '加码': '#e8f5e9', '正常': '#e8f1fd', '减码': '#fef3e0', '暂停': '#fce4e4' };

function renderAdvice(data) {
  var resEl = $('holdingsResults');
  resEl.style.display = 'block';
  var html = renderMarketContext(data.market_context || {});
  html += renderSummary(data);
  html += renderHoldingTable(data.holdings || []);
  if (data.data_note) {
    html += '<div class="holdings-note">ⓘ ' + escHtml(data.data_note) + '</div>';
  }
  resEl.innerHTML = html;
}

function renderMarketContext(mc) {
  var v = mc.valuation || {};
  var dc = mc.dca_consensus || {};

  var pe = v.pe_percentile != null ? Math.round(v.pe_percentile * 100) + '%' : '--';
  var erp = v.erp != null ? Number(v.erp).toFixed(2) + '%' : '--';
  var eq = (v.equity_weight && v.equity_weight > 0) ? Math.round(v.equity_weight) + '%' : '--';
  var tier = dc.tier || '正常';
  var dcaMult = dc.multiplier != null ? dc.multiplier + 'x' : '--';

  return '<div class="holdings-mc">' +
    '<div class="holdings-mc-title">🌏 大盘环境（所有持仓共享）</div>' +
    '<div class="holdings-mc-row">' +
      '<span>周期 <b>' + escHtml(mc.cycle || '—') + '</b></span>' +
      '<span>沪深300 PE分位 <b>' + pe + '</b></span>' +
      '<span>ERP股债性价比 <b>' + erp + '</b></span>' +
      '<span>建议股票仓位 <b>' + eq + '</b></span>' +
    '</div>' +
    (dc.multiplier != null ?
      '<div style="display:flex;align-items:center;gap:8px;background:' + (DCA_TIER_BG[tier] || '#f5f6f8') + ';border-radius:8px;padding:8px 12px;margin-top:8px;">' +
        '<span>💰</span>' +
        '<span style="font-weight:700;color:' + (DCA_TIER_COLOR[tier] || '#333') + ';">定投档位 ' + escHtml(tier) + '（' + dcaMult + '）</span>' +
        '<span style="font-size:.78rem;color:#666;">' + escHtml(dc.label || '') + '</span>' +
      '</div>' : '') +
  '</div>';
}

function renderHoldingCard(h) {
  var a = ACTION_MAP[h.action] || ACTION_MAP['数据不足'];

  var nav = (h.latest_nav != null && typeof h.latest_nav === 'number') ? h.latest_nav.toFixed(4) : '--';
  var retHtml = '--';
  if (h.return_rate != null && h.return_rate !== '') {
    var pnl = parseFloat(h.return_rate);
    if (!isNaN(pnl)) {
      retHtml = '<span class="' + (pnl >= 0 ? 'pnl-up' : 'pnl-down') + '">' +
        (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + '%</span>';
    }
  }

  var typeTag = h.fund_type === 'gold' ? '🥇黄金' : h.fund_type === 'open' ? '📦场外' : '📊ETF';
  var errHtml = h.error ? '<div style="font-size:.76rem;color:var(--red);margin-top:6px;">⚠️ ' + escHtml(h.error) + '</div>' : '';

  var addHtml = '';
  if (h.add_signal && h.add_signal.multiplier != null) {
    addHtml = '<div style="font-size:.76rem;color:#666;margin-top:8px;">📈 加仓档位 <b>' + escHtml(h.add_signal.tier) + '</b>（' + h.add_signal.multiplier + 'x）</div>';
  }

  var reasonsHtml = (h.key_reasons || []).map(function (r) {
    return '<li>' + escHtml(r) + '</li>';
  }).join('');

  return '<div class="holdings-card">' +
    '<div class="holdings-card-head">' +
      '<div class="holdings-card-title">' +
        '<span>' + escHtml(h.fund_name || h.fund_code) + '</span>' +
        '<span class="holdings-card-code">' + escHtml(h.fund_code) + '</span>' +
        '<span class="holdings-card-type">' + typeTag + '</span>' +
      '</div>' +
      '<span class="badge ' + a.badge + '">' + escHtml(h.action) + '</span>' +
    '</div>' +
    '<div class="holdings-card-meta">' +
      '<span>净值 ' + nav + '</span>' +
      '<span>收益率 ' + retHtml + '</span>' +
      '<span>持有 ' + (h.days_held != null ? h.days_held + '天' : '--') + '</span>' +
      (h.latest_nav_date ? '<span>数据日 ' + escHtml(h.latest_nav_date) + '</span>' : '') +
    '</div>' +
    '<div class="holdings-verdict" style="background:' + a.bg + ';color:' + a.color + ';border:1px solid ' + a.color + ';">' +
      a.icon + ' ' + escHtml(h.action_detail || '') +
    '</div>' +
    addHtml +
    errHtml +
    (reasonsHtml ? '<ul class="holdings-reasons">' + reasonsHtml + '</ul>' : '') +
  '</div>';
}

// ── 汇总建议（顶部） ─────────────────────────────

function renderSummary(data) {
  var holdings = data.holdings || [];
  var reduce = holdings.filter(function (h) { return h.action === '减仓' || h.action === '清仓'; });
  var cands = (data.summary && data.summary.add_candidates) || [];

  var html = '<div class="holdings-summary">' +
    '<div class="holdings-summary-title">📋 汇总建议</div>';

  // 减仓/清仓当前持仓
  html += '<div class="holdings-summary-block">' +
    '<div class="holdings-summary-label">🔻 建议减仓 / 清仓的当前持仓</div>';
  if (reduce.length === 0) {
    html += '<div class="holdings-summary-empty">当前无需要减仓或清仓的持仓，全部可继续持有</div>';
  } else {
    html += '<div class="holdings-summary-list">';
    reduce.forEach(function (h) {
      var a = ACTION_MAP[h.action] || ACTION_MAP['数据不足'];
      html += '<span class="holdings-summary-item" style="border-color:' + a.color + ';">' +
        escHtml(h.fund_name || h.fund_code) +
        ' <span class="badge ' + a.badge + '">' + escHtml(h.action) + '</span>' +
        (h.action_detail ? '<span class="holdings-summary-reason">' + escHtml(h.action_detail) + '</span>' : '') +
        '</span>';
    });
    html += '</div>';
  }
  html += '</div>';

  // 加仓其他基金
  html += '<div class="holdings-summary-block">' +
    '<div class="holdings-summary-label">🟢 建议加仓的其他基金（非当前持仓）</div>';
  if (cands.length === 0) {
    html += '<div class="holdings-summary-empty">暂无可用候选标的</div>';
  } else {
    var allPaused = cands.every(function (c) { return c.add_signal && c.add_signal.tier === '暂停'; });
    if (allPaused) {
      html += '<div class="holdings-summary-note">当前大盘估值偏高、定投档位暂停，以下为相对最便宜的候选，待档位回升后再加仓</div>';
    }
    html += '<div class="holdings-summary-list">';
    cands.forEach(function (c) {
      var sig = c.add_signal || {};
      var tier = sig.tier || '正常';
      var color = DCA_TIER_COLOR[tier] || '#2f6fed';
      var bg = DCA_TIER_BG[tier] || '#e8f1fd';
      var reason = (sig.reasons && sig.reasons[0]) ? sig.reasons[0] : '';
      html += '<span class="holdings-summary-item" style="border-color:' + color + ';">' +
        escHtml(c.fund_name || c.fund_code) +
        ' <span class="holdings-tier-badge" style="background:' + bg + ';color:' + color + ';">' +
          escHtml(tier) + (sig.multiplier != null ? ' ' + sig.multiplier + 'x' : '') +
        '</span>' +
        (reason ? '<span class="holdings-summary-reason">' + escHtml(reason) + '</span>' : '') +
        '</span>';
    });
    html += '</div>';
  }
  html += '</div></div>';

  return html;
}

// ── 持仓表格 ─────────────────────────────────────

function renderHoldingTable(holdings) {
  var html = '<div class="holdings-table-wrap"><table class="bt-compare-table">' +
    '<thead><tr>' +
    '<th class="bt-cmp-metric">基金</th>' +
    '<th>净值</th><th>收益率</th><th>持有天数</th>' +
    '<th>最佳离场时机</th><th>当日建议</th><th>理由</th>' +
    '</tr></thead><tbody>';

  holdings.forEach(function (h) {
    var a = ACTION_MAP[h.action] || ACTION_MAP['数据不足'];
    var typeTag = h.fund_type === 'gold' ? '🥇' : h.fund_type === 'open' ? '📦' : '📊';

    var nav = (h.latest_nav != null && typeof h.latest_nav === 'number') ? h.latest_nav.toFixed(4) : '--';
    var navDate = h.latest_nav_date ? '<div class="holdings-sub">' + escHtml(h.latest_nav_date) + '</div>' : '';

    var retHtml = '--';
    if (h.return_rate != null && h.return_rate !== '') {
      var pnl = parseFloat(h.return_rate);
      if (!isNaN(pnl)) {
        retHtml = '<span class="' + (pnl >= 0 ? 'pnl-up' : 'pnl-down') + '">' +
          (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + '%</span>';
      }
    }

    var reasonsHtml = (h.key_reasons || []).map(function (r) { return escHtml(r); }).join('；');

    html += '<tr>' +
      '<td class="bt-cmp-metric">' +
        '<div>' + escHtml(h.fund_name || h.fund_code) + ' <span class="holdings-card-type">' + typeTag + '</span></div>' +
        '<div class="holdings-card-code">' + escHtml(h.fund_code) + '</div>' +
      '</td>' +
      '<td>' + nav + navDate + '</td>' +
      '<td>' + retHtml + '</td>' +
      '<td>' + (h.days_held != null ? h.days_held + '天' : '--') + '</td>' +
      '<td>' + renderBestExit(h) + '</td>' +
      '<td><span class="badge ' + a.badge + '">' + escHtml(h.action) + '</span></td>' +
      '<td class="holdings-reason-cell">' + (reasonsHtml || '--') + '</td>' +
      '</tr>';
  });

  return html + '</tbody></table></div>';
}

function renderBestExit(h) {
  var be = h.best_exit || {};
  if (!be.peak_nav || !be.peak_date) {
    return '<span class="holdings-sub">--</span>';
  }

  var dd = be.drawdown_from_peak;
  var ddHtml = '';
  if (dd != null) {
    if (dd < 0) {
      ddHtml = '<div class="holdings-best-dd">距峰值回撤 <b>' + Math.abs(dd).toFixed(2) + '%</b></div>';
    } else if (dd === 0) {
      ddHtml = '<div class="holdings-best-dd">正处峰值</div>';
    } else {
      ddHtml = '<div class="holdings-best-dd">较峰值 +' + dd.toFixed(2) + '%</div>';
    }
  }

  var gainHtml = be.peak_gain != null
    ? '<div class="holdings-sub">峰值时收益率≈' + be.peak_gain.toFixed(2) + '%</div>' : '';
  var truncHtml = be.window_truncated
    ? '<div class="holdings-sub">峰值取自可用窗口</div>' : '';

  return '<div class="holdings-best-exit">' +
    '<div class="holdings-sub">' + escHtml(be.peak_date) + ' · ' + be.peak_nav.toFixed(4) + '</div>' +
    ddHtml + gainHtml + truncHtml +
    '</div>';
}
