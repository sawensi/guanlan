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
  (data.holdings || []).forEach(function (h) { html += renderHoldingCard(h); });
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
