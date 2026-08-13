/**
 * 观澜 v6 — 每日解读
 * 布局: 近3篇文章原文(上) + AI 解读(中) + 历史记录折叠(下)
 * ES5 兼容语法，确保微信/桌面浏览器均可运行
 */

var RECENT_COUNT = 3;  // AI 深度解读的文章数，其余放入历史记录

function loadIns(date) {
  var path = date ? '/insights?date=' + date : '/insights';
  get(path).then(function(data) {
    if (!data) {
      _insightsError('解读数据加载失败');
      return;
    }
    APP.ins = data;
    try {
      renderInsights(data);
    } catch(e) {
      _insightsError('渲染异常: ' + e.message);
    }
  }).catch(function(e) {
    _insightsError('API请求异常: ' + e.message);
  });
}

function _insightsError(msg) {
  var contentEl = $('articlesContent') || $('insightsBody');
  var divEl = $('insightsDivider');
  var llmEl = $('llmInterpretation');
  var histEl = $('articlesHistory');
  if (contentEl) {
    contentEl.innerHTML = '<p style="color:var(--red);text-align:center;padding:40px;">❌ ' + msg + '</p>';
  }
  if (divEl) divEl.style.display = 'none';
  if (llmEl) llmEl.style.display = 'none';
  if (histEl) histEl.style.display = 'none';
}

function renderInsights(d) {
  // 元信息
  var metaEl = $('insightsMeta');
  if (metaEl) {
    var genTime = '--';
    if (d.generated_at) {
      genTime = new Date(d.generated_at).toLocaleTimeString('zh-CN');
    }
    metaEl.innerHTML =
      '📅 ' + (d.date || '--') +
      ' · 📄 ' + (d.articles_count || 0) + ' 篇' +
      ' · 🕐 ' + genTime;
  }

  // ── 徐小明立场横幅 ──
  var stanceBannerEl = $('stanceBanner');
  if (stanceBannerEl && d.xu_xiaoming_stance && d.xu_xiaoming_stance.market_stance) {
    var s = d.xu_xiaoming_stance;
    var stanceEmoji = s.market_stance === '看多' ? '🟢' :
                       s.market_stance === '看空' ? '🔴' : '🟡';
    var stanceBg = s.market_stance === '看多' ? '#f0f7f0' :
                    s.market_stance === '看空' ? '#fff5f5' : '#fffef5';
    var stanceBorder = s.market_stance === '看多' ? 'var(--green)' :
                        s.market_stance === '看空' ? 'var(--red)' : '#e6a817';
    stanceBannerEl.style.display = 'block';
    stanceBannerEl.style.background = stanceBg;
    stanceBannerEl.style.borderLeft = '3px solid ' + stanceBorder;
    stanceBannerEl.innerHTML =
      '<span style="font-size:1.05rem;">' + stanceEmoji +
      ' <strong>徐小明今日观点：' + escHtml(s.market_stance) +
      '</strong> · 建议仓位：' + escHtml(s.position_recommendation) + '</span>' +
      (s.key_reason ? '<br><small style="color:var(--text-2);">' + escHtml(s.key_reason) + '</small>' : '') +
      '<br><small style="color:var(--text-3);">LLM 置信度: ' + Math.round(s.confidence * 100) + '% · ' +
      '分析 ' + s.articles_analyzed + ' 篇文章 · ' + (s.date || '') + '</small>';
  } else if (stanceBannerEl) {
    stanceBannerEl.style.display = 'none';
  }

  var articlesEl = $('articlesContent');
  var llmEl = $('llmInterpretation');
  var divEl = $('insightsDivider');
  var histEl = $('articlesHistory');

  // 旧版 HTML 回退 (浏览器缓存)
  if (!articlesEl && !llmEl) {
    var oldBody = $('insightsBody');
    if (oldBody) {
      oldBody.innerHTML =
        '<p style="color:var(--text-3);text-align:center;padding:20px;">' +
        '页面已更新，请<strong>强制刷新</strong>浏览器（Ctrl+Shift+R）</p>';
    }
    return;
  }

  // ── 拆分文章：近 N 篇 + 历史 ──
  var articles = d.articles || [];
  var recentArticles = articles.slice(0, RECENT_COUNT);
  var historyArticles = articles.slice(RECENT_COUNT);

  // ═══ 上半部分：近 N 篇文章原文 ═══
  var articlesHtml = '';

  if (recentArticles.length > 0) {
    // 区域标签
    articlesHtml += '<div class="articles-section-label">📌 近 ' + RECENT_COUNT + ' 次解读</div>';

    var sourceMap = {
      'wewe_rss': '微信读书',
      'sina_blog': '新浪博客',
      'sogou': '搜狗搜索',
      'baidu': '百度搜索'
    };

    for (var i = 0; i < recentArticles.length; i++) {
      var a = recentArticles[i];
      var title = a.title || '无标题';
      var content = a.content || a.summary || '';
      var sourceLabel = sourceMap[a.source] || a.source || '';

      articlesHtml += '<div class="article-card">';
      articlesHtml += '<div class="article-header">';
      articlesHtml += '<span class="article-num">#' + (i + 1) + '</span>';
      articlesHtml += '<span class="article-title">' + escHtml(title) + '</span>';
      if (sourceLabel) {
        articlesHtml += '<span class="article-source-tag">' + sourceLabel + '</span>';
      }
      articlesHtml += '</div>';

      // 正文
      if (content) {
        var displayContent = content;
        if (content.length > 5000) {
          displayContent = content.slice(0, 5000) + '\n\n...（内容过长，已截断，点击原文链接阅读全文）';
        }
        articlesHtml += '<div class="article-body"><p>' +
          escHtml(displayContent).replace(/\n/g, '<br>') + '</p></div>';
      } else {
        // 无内容时的降级展示
        articlesHtml += '<div class="article-body article-body-empty">';
        articlesHtml += '<p style="color:var(--text-3);text-align:center;padding:12px 0;">📭 正文内容暂未抓取成功</p>';
        if (a.url) {
          articlesHtml += '<p style="text-align:center;"><a href="' + a.url + '" target="_blank" rel="noopener" class="article-link" style="font-size:.82rem;">👉 点击查看原文</a></p>';
        }
        articlesHtml += '</div>';
      }

      // 底部
      articlesHtml += '<div class="article-footer">';
      if (a.url) {
        articlesHtml += '<a href="' + a.url + '" target="_blank" rel="noopener" class="article-link">📎 查看原文</a>';
      }
      if (a.publish_time) {
        articlesHtml += '<span class="article-time">' + a.publish_time + '</span>';
      }
      articlesHtml += '</div>';
      articlesHtml += '</div>';
    }
  } else {
    articlesHtml = '<p style="color:var(--text-3);text-align:center;padding:20px;">今日暂无新文章</p>';
  }

  if (articlesEl) articlesEl.innerHTML = articlesHtml;

  // ═══ 下半部分：AI 解读 ═══
  var hasInterpretation = d.full_interpretation &&
    d.full_interpretation.trim() &&
    d.full_interpretation.indexOf('暂无新文章') === -1;

  if (hasInterpretation) {
    if (llmEl) {
      llmEl.innerHTML = md(d.full_interpretation);
      llmEl.style.display = 'block';
    }
    if (divEl) divEl.style.display = 'flex';
  } else if (recentArticles.length > 0) {
    if (divEl) divEl.style.display = 'flex';
    if (llmEl) {
      llmEl.style.display = 'block';
      llmEl.innerHTML = '<p style="color:var(--text-3);text-align:center;padding:20px;">AI 解读正在生成中，请稍后刷新...</p>';
    }
  } else {
    if (divEl) divEl.style.display = 'none';
    if (llmEl) llmEl.style.display = 'none';
  }

  // ═══ 历史记录（第 N+1 篇起）═══
  if (historyArticles.length > 0 && histEl) {
    histEl.style.display = 'block';

    // 标题行
    var titleEl = $('historyTitle');
    if (titleEl) {
      titleEl.textContent = '📚 历史记录（' + historyArticles.length + ' 篇）';
    }

    // 生成卡片列表
    var histHtml = '';
    var sourceMap = {
      'wewe_rss': '微信读书',
      'sina_blog': '新浪博客',
      'sogou': '搜狗搜索',
      'baidu': '百度搜索'
    };

    for (var j = 0; j < historyArticles.length; j++) {
      var ha = historyArticles[j];
      var hTitle = ha.title || '无标题';
      var hContent = ha.content || ha.summary || '';
      var hSourceLabel = sourceMap[ha.source] || ha.source || '';
      var hTime = ha.publish_time || '';
      var globalIndex = RECENT_COUNT + j + 1;  // 延续编号

      histHtml += '<div class="history-card" id="histCard' + j + '">';
      histHtml += '<div class="history-card-header" onclick="toggleHistoryCard(' + j + ')">';
      histHtml += '<span class="history-card-num">#' + globalIndex + '</span>';
      histHtml += '<span class="history-card-title">' + escHtml(hTitle) + '</span>';
      if (hSourceLabel) {
        histHtml += '<span class="article-source-tag">' + hSourceLabel + '</span>';
      }
      if (hTime) {
        histHtml += '<span class="history-card-time">' + hTime + '</span>';
      }
      histHtml += '<span class="history-card-arrow" id="histArrow' + j + '">▸</span>';
      histHtml += '</div>';
      histHtml += '<div class="history-card-body" id="histBody' + j + '">';
      if (hContent) {
        var displayContent = hContent;
        if (hContent.length > 3000) {
          displayContent = hContent.slice(0, 3000) + '\n\n...（内容过长，已截断）';
        }
        histHtml += '<p>' + escHtml(displayContent).replace(/\n/g, '<br>') + '</p>';
      } else {
        histHtml += '<p style="color:var(--text-3);text-align:center;padding:8px 0;">📭 正文内容暂未抓取成功</p>';
      }
      if (ha.url) {
        histHtml += '<p style="text-align:center;margin-top:4px;"><a href="' + ha.url + '" target="_blank" rel="noopener" class="article-link" style="font-size:.8rem;">👉 点击查看原文</a></p>';
      }
      histHtml += '</div>';
      histHtml += '</div>';
    }

    var listEl = $('historyList');
    if (listEl) listEl.innerHTML = histHtml;

    // 重置展开状态
    _historyExpanded = false;
    _historyCardStates = {};
    var arrowEl = $('historyArrow');
    if (arrowEl) {
      arrowEl.textContent = '▶';
      arrowEl.classList.remove('open');
    }
    if (listEl) listEl.style.display = 'none';
  } else if (histEl) {
    histEl.style.display = 'none';
  }
}

// ── 历史记录展开/收起 ──

var _historyExpanded = false;
var _historyCardStates = {};  // { cardIndex: true/false }

function toggleHistory() {
  var listEl = $('historyList');
  var arrowEl = $('historyArrow');
  if (!listEl || !arrowEl) return;

  _historyExpanded = !_historyExpanded;

  if (_historyExpanded) {
    listEl.style.display = 'block';
    arrowEl.textContent = '▼';
    arrowEl.classList.add('open');
  } else {
    listEl.style.display = 'none';
    arrowEl.textContent = '▶';
    arrowEl.classList.remove('open');
    // 收起所有单条
    _historyCardStates = {};
    var cards = document.querySelectorAll('.history-card');
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.remove('open');
    }
    var arrows = document.querySelectorAll('.history-card-arrow');
    for (var k = 0; k < arrows.length; k++) {
      arrows[k].textContent = '▸';
    }
  }
}

function toggleHistoryCard(index) {
  var cardEl = $('histCard' + index);
  var bodyEl = $('histBody' + index);
  var arrowEl = $('histArrow' + index);
  if (!cardEl || !bodyEl) return;

  var isOpen = cardEl.classList.contains('open');

  if (isOpen) {
    cardEl.classList.remove('open');
    bodyEl.style.display = 'none';
    if (arrowEl) arrowEl.textContent = '▸';
    _historyCardStates[index] = false;
  } else {
    cardEl.classList.add('open');
    bodyEl.style.display = 'block';
    if (arrowEl) arrowEl.textContent = '▾';
    _historyCardStates[index] = true;
  }
}

// HTML 转义
function escHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
