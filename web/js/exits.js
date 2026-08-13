/**
 * 观澜 — 离场策略
 * 基金/QDII/黄金止盈清仓策略展示
 */

var EXIT_STATE = {
  fundCode: '510300',
  entryPrice: null,
  entryDate: null,
  returnRate: null,
  data: null,
};

async function loadExits(fundCode, entryPrice, entryDate, returnRate) {
  var params = 'fund_code=' + encodeURIComponent(fundCode || '510300');
  if (entryPrice && parseFloat(entryPrice) > 0) {
    params += '&entry_price=' + encodeURIComponent(entryPrice);
  }
  if (entryDate) {
    params += '&entry_date=' + encodeURIComponent(entryDate);
  }
  if (returnRate !== null && returnRate !== undefined && returnRate !== '') {
    params += '&return_rate=' + encodeURIComponent(returnRate);
  }
  var data = await get('/exit-strategies?' + params);
  if (!data?.strategies?.length) {
    $('exitsList').innerHTML =
      '<div style="color:var(--text-3);text-align:center;padding:40px;">' +
      '离场策略数据加载失败<br><small>请检查基金代码是否正确</small></div>';
    return;
  }
  EXIT_STATE.data = data;
  EXIT_STATE.fundCode = fundCode;
  EXIT_STATE.entryPrice = entryPrice;
  EXIT_STATE.entryDate = entryDate;
  EXIT_STATE.returnRate = returnRate;
  renderExits(data);
}

function applyExitParams() {
  var code = $('exitFundCode').value.trim() || '510300';
  var price = $('exitEntryPrice').value.trim();
  var date = $('exitEntryDate').value;
  var rate = $('exitReturnRate').value.trim();
  EXIT_STATE.fundCode = code;
  EXIT_STATE.entryPrice = price || null;
  EXIT_STATE.entryDate = date || null;
  EXIT_STATE.returnRate = rate || null;
  $('exitsList').innerHTML = '<div class="loading-shimmer">正在分析基金 ' + code + '...</div>';
  loadExits(code, price || null, date || null, rate || null);
}

function renderRiskIndicators(dec) {
  var vol = (dec && dec.vol_risk) ? dec.vol_risk : null;
  var trend = (dec && dec.trend_risk) ? dec.trend_risk : null;
  if (!vol && !trend) return '';

  var html = '<div class="risk-indicators" style="display:flex;gap:12px;margin:8px 0;flex-wrap:wrap;">';

  // 波动率指示器
  if (vol) {
    var volColor = '#888';
    if (vol.level === 'extreme') volColor = '#e53e3e';
    else if (vol.level === 'elevated') volColor = '#ed8936';
    else if (vol.level === 'calm') volColor = '#38a169';
    else volColor = '#718096';

    html += '<div style="flex:1;min-width:140px;padding:10px 12px;border-radius:8px;background:#f7fafc;border-left:4px solid ' + volColor + ';">' +
      '<div style="font-size:.78rem;color:#718096;margin-bottom:4px;">📐 波动率状态</div>' +
      '<div style="font-size:.9rem;font-weight:600;color:' + volColor + ';">' + (vol.label || '--') + '</div>' +
      '<div style="font-size:.75rem;color:#a0aec0;">信号: ' + (vol.signal || '--') + '</div>' +
      '</div>';
  }

  // 趋势指示器
  if (trend) {
    var trendColor = '#888';
    if (trend.trend_strength === 'strong_down') trendColor = '#e53e3e';
    else if (trend.trend_strength === 'weak_down') trendColor = '#ed8936';
    else if (trend.trend_strength === 'strong_up') trendColor = '#38a169';
    else if (trend.trend_strength === 'weak_up') trendColor = '#68d391';
    else trendColor = '#718096';

    var extraInfo = '';
    if (trend.consecutive && trend.consecutive < 0) {
      extraInfo = ' · 连跌' + Math.abs(trend.consecutive) + '天';
    } else if (trend.consecutive && trend.consecutive > 0) {
      extraInfo = ' · 连涨' + trend.consecutive + '天';
    }

    html += '<div style="flex:1;min-width:140px;padding:10px 12px;border-radius:8px;background:#f7fafc;border-left:4px solid ' + trendColor + ';">' +
      '<div style="font-size:.78rem;color:#718096;margin-bottom:4px;">📈 近期趋势</div>' +
      '<div style="font-size:.9rem;font-weight:600;color:' + trendColor + ';">' + (trend.label || '--') + extraInfo + '</div>' +
      '<div style="font-size:.75rem;color:#a0aec0;">MA: ' + (trend.ma_align || '--') + ' · 信号: ' + (trend.signal || '--') + '</div>' +
      '</div>';
  }

  html += '</div>';
  return html;
}

function renderExits(data) {
  var list = data.strategies || [];
  var fundName = data.fund_name || data.fund_code || '';
  var fundType = data.fund_type || '';
  var latestNav = data.latest_nav || '--';
  var latestNavDate = data.latest_nav_date || '';
  var entryPrice = data.entry_price;
  var entryDate = data.entry_date;
  var returnRate = data.return_rate;

  var sigMap = {
    '清仓': 'badge-sell',
    '减仓': 'badge-wait',
    '持有': 'badge-hold',
    '观望': 'badge-wait'
  };

  // 基金信息头
  var fundInfoHtml = '<div class="exit-fund-info">' +
    '<span class="exit-fund-name">' + fundName + '</span>' +
    '<span class="exit-fund-code">' + (data.fund_code || '') + '</span>' +
    '<span class="exit-fund-type">' + (fundType === 'gold' ? '🥇 黄金' : fundType === 'qdii' ? '🌍 QDII' : '📊 基金') + '</span>' +
    '<span class="exit-fund-nav">净值: ' + (typeof latestNav === 'number' ? latestNav.toFixed(4) : latestNav) +
      (latestNavDate ? ' <small>(' + latestNavDate.slice(5) + ')</small>' : '') + '</span>';
  if (returnRate !== null && returnRate !== undefined && returnRate !== '') {
    var pnl = parseFloat(returnRate);
    fundInfoHtml += '<span class="exit-fund-pnl ' + (pnl >= 0 ? 'pnl-up' : 'pnl-down') + '">' +
      '收益率: ' + (pnl >= 0 ? '+' : '') + pnl.toFixed(2) + '% <small>(手动输入)</small></span>';
  } else if (entryPrice && parseFloat(entryPrice) > 0) {
    var pnl = latestNav && entryPrice ? ((latestNav - entryPrice) / entryPrice * 100) : null;
    fundInfoHtml += '<span class="exit-fund-pnl ' + (pnl >= 0 ? 'pnl-up' : 'pnl-down') + '">' +
      '入场: ' + parseFloat(entryPrice).toFixed(4) + ' | ' + (pnl >= 0 ? '+' : '') + (pnl ? pnl.toFixed(2) : '--') + '%</span>';
  }
  fundInfoHtml += '</div>';

  var cardsHtml = list.map(function(s, i) {
    var sig = s.current_signal || {};
    var sc = sigMap[sig.signal] || 'badge-wait';
    var catColors = { '止盈': 'var(--green)', '止损': 'var(--red)', '混合': 'var(--blue)', '信号': 'var(--orange)', '黄金': '#c8943e' };
    var catColor = catColors[s.category] || 'var(--text-2)';

    // 操作建议渲染
    var actionsHtml = '';
    if (sig.actions && sig.actions.length) {
      actionsHtml = '<div class="exit-actions">' +
        sig.actions.map(function(a) {
          var pct = Math.round((1 - a.ratio) * 100);
          var barClass = pct >= 100 ? 'action-bar-full' : pct >= 50 ? 'action-bar-half' : 'action-bar-partial';
          return '<div class="exit-action">' +
            '<div class="action-label">' + a.name + '</div>' +
            '<div class="action-bar-wrap"><div class="action-bar ' + barClass + '" style="width:' + Math.min(pct, 100) + '%"></div></div>' +
            '<div class="action-detail">保留 ' + Math.round(a.ratio * 100) + '% · ' + (a.reason || '') + '</div>' +
            '</div>';
        }).join('') +
        '</div>';
    }

    // 条件明细
    var condsHtml = '';
    if (sig.conditions && sig.conditions.length) {
      condsHtml = '<div class="exit-conditions">' +
        sig.conditions.map(function(c) {
          var cls = c.met ? 'cond-met' : 'cond-unmet';
          var w = c.weight ? ' <small>(' + c.weight + '%)</small>' : '';
          return '<span class="exit-cond ' + cls + '">' +
            (c.met ? '✓ ' : '✗ ') + c.name + w +
            '<br><small>' + (c.current || '--') + ' vs ' + (c.threshold || '--') + '</small>' +
            '</span>';
        }).join('') +
        '</div>';
    }

    return '<div class="strat-card exit-card" id="ec-' + s.id + '" onclick="toggleExitCard(\'' + s.id + '\')">' +
      '<div class="strat-head">' +
        '<div>' +
          '<div class="strat-title">' + (i + 1) + '. ' + s.name +
            '<span class="exit-cat" style="color:' + catColor + ';border-color:' + catColor + '">' + s.category + '</span>' +
          '</div>' +
          '<div class="strat-sub">' + s.tagline + '</div>' +
        '</div>' +
        '<div class="strat-badges">' +
          '<span class="badge ' + sc + '">' + (sig.signal || '--') + '</span>' +
          '<span class="badge badge-risk">风险' + (s.risk_level || '--') + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="strat-body">' +
        md(s.description || '') +
        '<div class="strat-signal">' +
          '<div class="sig-head">📶 当前信号 · ' + (s.frequency || '') + ' · ' + s.category + '类</div>' +
          '<div class="sig-body">' +
            '<strong style="color:' + (sig.signal === '清仓' ? 'var(--red)' :
              sig.signal === '减仓' ? 'var(--orange)' : sig.signal === '持有' ? 'var(--green)' : 'var(--blue)') + '">' +
            '【' + (sig.signal || '--') + '】</strong>' +
            ' 置信度 ' + ((sig.confidence || 0) * 100).toFixed(0) + '%' +
            ' &nbsp;—&nbsp; ' + (sig.reasoning || '') +
          '</div>' +
        '</div>' +
        (sig.pnl_pct != null ? '<div class="exit-pnl-info">' +
          '💵 盈亏: <b class="' + (sig.pnl_pct >= 0 ? 'pnl-up' : 'pnl-down') + '">' +
          (sig.pnl_pct >= 0 ? '+' : '') + sig.pnl_pct.toFixed(2) + '%</b>' +
          (sig.days_held != null ? ' | 📅 持有: ' + sig.days_held + '天' : '') +
          (sig.redemption_fee != null && sig.redemption_fee > 0 ? ' | 💸 赎回费: ' + sig.redemption_fee + '%' : '') +
          (sig.next_fee_breakpoint != null ? ' | ⏰ 距断点: ' + sig.next_fee_breakpoint + '天' : '') +
          '</div>' : '') +
        actionsHtml +
        condsHtml +
      '</div>' +
    '</div>';
  }).join('');

  // ═══ 顶部汇总离场决策面板 ═══
  var summaryHtml = '';
  if (data.decision && data.decision.recommendation) {
    var dec = data.decision;
    var recColor = dec.recommendation === '建议清仓' ? 'var(--red)' :
                    dec.recommendation === '建议减仓' ? 'var(--orange)' : 'var(--green)';
    var recIcon = dec.recommendation === '建议清仓' ? '🚨' :
                   dec.recommendation === '建议减仓' ? '⚠️' : '✅';
    var verdictClass = dec.recommendation === '建议清仓' ? 'clear' :
                        dec.recommendation === '建议减仓' ? 'reduce' : 'hold';
    var totalStrats = dec.total_strategies || ((dec.breakdown ? ((dec.breakdown['清仓']||0)+(dec.breakdown['减仓']||0)+(dec.breakdown['持有']||0)+(dec.breakdown['观望']||0)) : '--'));

    // ── 徐小明立场横幅 ──
    var stanceBannerHtml = '';
    for (var si = 0; si < list.length; si++) {
      if (list[si].id === 'xuxiaoming-exit' && list[si].current_signal && list[si].current_signal.signal !== '观望') {
        var xsig = list[si].current_signal;
        var reasoning = xsig.reasoning || '';
        var parts = reasoning.split('|');
        var stanceLine = parts.length > 1 ? parts[1].trim() : '';
        var reasonLine = parts.length > 3 ? parts[3].trim() : '';
        var stanceBadge = xsig.signal === '清仓' ? '🔴' : xsig.signal === '减仓' ? '🟠' : '🟢';
        stanceBannerHtml = '<div class="exit-stance-banner" style="margin:12px 0;padding:10px 14px;' +
          'background:' + (xsig.signal === '清仓' ? '#fff5f5' : xsig.signal === '减仓' ? '#fff9f0' : '#f0f7f0') + ';' +
          'border-left:3px solid ' + recColor + ';border-radius:var(--radius-sm);font-size:.88rem;line-height:1.5;">' +
          stanceBadge + ' <strong>徐小明今日观点：</strong>' + escHtml(stanceLine) +
          (reasonLine && reasonLine.indexOf('核心观点') >= 0 ? '<br><small style="color:var(--text-2);">' + escHtml(reasonLine) + '</small>' : '') +
          (xsig.confidence ? '<br><small style="color:var(--text-3);">信号置信度: ' + Math.round(xsig.confidence * 100) + '% | 策略权重: 1.5 (最高)</small>' : '') +
          '</div>';
        break;
      }
    }

    // ── 贡献度条形图 ──
    var contribs = dec.contributions || [];
    var contribHtml = '';
    if (contribs.length > 0) {
      contribHtml = '<div class="exit-contributions">' +
        '<div class="contrib-title">📊 各策略对综合决策的影响度</div>';
      for (var ci = 0; ci < contribs.length; ci++) {
        var c = contribs[ci];
        if (c.contribution_pct < 3) continue; // 过滤噪音
        var barColor = c.signal === '清仓' ? 'var(--red)' :
                        c.signal === '减仓' ? 'var(--orange)' : 'var(--green)';
        var icon = c.strategy_id === 'xuxiaoming-exit' ? '📰 ' :
                    c.category === '止损' ? '🛑 ' :
                    c.category === '止盈' ? '💰 ' :
                    c.category === '信号' ? '📉 ' :
                    c.category === '黄金' ? '🥇 ' :
                    c.category === '混合' ? '🔀 ' : '📌 ';
        contribHtml += '<div class="contribution-bar">' +
          '<span class="contrib-name" style="min-width:130px;font-size:.82rem;">' + icon + c.strategy_name + '</span>' +
          '<span class="contrib-signal" style="min-width:36px;font-size:.78rem;font-weight:600;color:' + barColor + ';">' + c.signal + '</span>' +
          '<span class="bar-track">' +
            '<span class="bar-fill signal-' + (c.signal === '清仓' ? 'clear' : c.signal === '减仓' ? 'reduce' : 'hold') + '" style="width:' + c.contribution_pct + '%"></span>' +
          '</span>' +
          '<span class="contrib-pct" style="min-width:38px;font-size:.8rem;font-weight:600;text-align:right;">' + c.contribution_pct + '%</span>' +
          '</div>';
      }
      contribHtml += '</div>';
    }

    // ── 信号分布条 ──
    var bd = dec.breakdown || {};
    var totalSignals = (bd['清仓']||0) + (bd['减仓']||0) + (bd['持有']||0) + (bd['观望']||0) || 1;
    var barHtml = '<div class="dec-breakdown-bar">' +
      (bd['清仓'] ? '<span class="dec-bar dec-bar-clear" style="flex:' + bd['清仓'] + '">清仓×' + bd['清仓'] + '</span>' : '') +
      (bd['减仓'] ? '<span class="dec-bar dec-bar-reduce" style="flex:' + bd['减仓'] + '">减仓×' + bd['减仓'] + '</span>' : '') +
      (bd['持有'] ? '<span class="dec-bar dec-bar-hold" style="flex:' + bd['持有'] + '">持有×' + bd['持有'] + '</span>' : '') +
      (bd['观望'] ? '<span class="dec-bar dec-bar-wait" style="flex:' + bd['观望'] + '">观望×' + bd['观望'] + '</span>' : '') +
      '</div>';

    // ── 建议操作 ──
    var actionHtml = '';
    if (dec.suggested_action) {
      var sa = dec.suggested_action;
      actionHtml = '<div class="dec-action">' +
        '<strong>' + sa.action + '</strong>' +
        ' — ' + sa.detail +
        '</div>';
    }

    summaryHtml = '<div class="exit-summary">' +
      // 标题行
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">' +
        '<span style="font-size:1.1rem;font-weight:700;">📊 离场综合决策</span>' +
        '<span style="font-size:.85rem;color:var(--text-2);">得分: <strong>' + (dec.confidence || 0) + '</strong> / 100</span>' +
      '</div>' +
      // 大号结论徽章
      '<div class="exit-summary-verdict ' + verdictClass + '">' +
        '<span style="font-size:1.4rem;">' + recIcon + '</span> ' +
        '<span style="font-size:1.3rem;font-weight:700;">' + dec.recommendation + '</span>' +
        '<span style="font-size:.85rem;color:var(--text-2);margin-left:8px;">' +
          (dec.consensus || '--') + ' (' + (bd['清仓']||0) + '/' + (bd['减仓']||0) + '/' + (bd['持有']||0) + '/' + (bd['观望']||0) + ')</span>' +
      '</div>' +
      // 信号分布条
      '<div class="dec-signals" style="margin:8px 0;">' +
        '<span class="dec-signals-label" style="font-size:.82rem;">信号分布:</span>' + barHtml +
      '</div>' +
      // 徐小明观点横幅
      stanceBannerHtml +
      // 双维度风险指示器
      (renderRiskIndicators(data.decision)) +
      // 贡献度条形图
      contribHtml +
      // 建议操作
      actionHtml +
      '</div>';
  }

  $('exitsList').innerHTML =
    '<div class="exits-header">' + fundInfoHtml + '</div>' +
    summaryHtml +
    '<div class="strategies-list">' + cardsHtml + '</div>';
}

function toggleExitCard(id) {
  var card = document.getElementById('ec-' + id);
  if (!card) return;
  var was = card.classList.contains('open');
  document.querySelectorAll('.exit-card').forEach(function(c) { c.classList.remove('open'); });
  if (!was) {
    card.classList.add('open');
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}
