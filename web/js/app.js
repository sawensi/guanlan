/**
 * 观澜 v2 — 主应用
 * 路由优先、骨架屏、独立加载、不阻塞
 */

const API  = '/guanlan/api';
const APP  = { page: 'dashboard', dash: null, ins: null, strats: [], holdings: false };
const $    = id => document.getElementById(id);

// HTML 转义（防 XSS）
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── API ─────────────────────────────────────────

async function get(path) {
  try {
    const r = await fetch(API + path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn(`GET ${path}:`, e.message);
    return null;
  }
}

async function post(path, body) {
  try {
    const opts = { method: 'POST' };
    if (body !== undefined && body !== null) {
      opts.headers = { 'Content-Type': 'application/json' };
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(API + path, opts);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn(`POST ${path}:`, e.message);
    return null;
  }
}

// ── Router ──────────────────────────────────────

function go(page) {
  APP.page = page;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const el = $('page-' + page);
  if (el) el.classList.add('active');

  document.querySelectorAll('.nav-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.page === page);
  });

  // 懒加载：切到某页才第一次请求数据
  if (page === 'dashboard' && !APP.dash) loadDash();
  if (page === 'insights'   && !APP.ins)  loadIns();
  if (page === 'strategies' && !APP.strats.length) loadStrats();
  if (page === 'rankings'  && !APP.rankings) loadRankings();
  if (page === 'holdings'  && !APP.holdings) loadHoldings();
}

// ── Simple Markdown ─────────────────────────────

// 行内渲染（表格单元格 + md() 复用）：先转义 &<>，再处理 **粗体** *斜体* `代码`
function mdInline(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,'<em>$1</em>')
    .replace(/`([^`]+)`/g,'<code>$1</code>');
}

// ── Markdown 表格解析 ───────────────────────────

// 去掉首尾外层管道，按 | 拆列并去空白
function splitTableRow(line) {
  var s = String(line).replace(/^\s*\|/,'').replace(/\|\s*$/,'');
  return s.split('|').map(function(c){ return c.trim(); });
}

// 是否表格数据行（以 | 开头结尾且至少 2 个管道）
function isTableRow(line) {
  var t = String(line).trim();
  return t.charAt(0) === '|' && t.charAt(t.length - 1) === '|' &&
         (t.match(/\|/g) || []).length >= 2;
}

// 是否表格分隔行（|---|:---:|---|）
function isTableSep(line) {
  return /^\s*\|[\s:\-|]*\|\s*$/.test(String(line));
}

// 组装表格 HTML（单元格内容经 mdInline 转义一次）
function renderMdTable(header, rows) {
  var h = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
  header.forEach(function(c){ h += '<th>' + mdInline(c) + '</th>'; });
  h += '</tr></thead><tbody>';
  rows.forEach(function(r){
    h += '<tr>';
    r.forEach(function(c){ h += '<td>' + mdInline(c) + '</td>'; });
    h += '</tr>';
  });
  return h + '</tbody></table></div>';
}

// 在转义前抽取连续的 |…| 表格块，替换为占位符，避免单元格内容被双重转义
function extractTables(text) {
  var lines = String(text).split('\n');
  var tables = [];
  var i = 0;
  while (i + 1 < lines.length) {
    if (isTableRow(lines[i]) && isTableSep(lines[i + 1])) {
      var header = splitTableRow(lines[i]);
      var rows = [];
      var j = i + 2;
      while (j < lines.length && isTableRow(lines[j])) {
        rows.push(splitTableRow(lines[j]));
        j++;
      }
      tables.push(renderMdTable(header, rows));
      lines.splice(i, j - i, '\u0001MDT' + (tables.length - 1) + '\u0001');
      i++;
    } else {
      i++;
    }
  }
  return { text: lines.join('\n'), tables: tables };
}

function md(text) {
  if (!text) return '';

  // 1. 抽出表格 → 占位符（单元格在 renderMdTable 里只转义一次）
  var tbl = extractTables(text);
  var h = mdInline(tbl.text)
    .replace(/^#### (.+)$/gm,'<h4>$1</h4>')
    .replace(/^### (.+)$/gm,'<h3>$1</h3>')
    .replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^# (.+)$/gm,'<h1>$1</h1>')
    .replace(/^&gt; (.+)$/gm,'<blockquote>$1</blockquote>')
    .replace(/^---$/gm,'<hr>')
    .replace(/^- (.+)$/gm,'<li>$1</li>');

  // Wrap consecutive <li> in <ul>
  h = h.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // Wrap non-tag lines in <p>
  var lines = h.split('\n');
  var out = [];
  for (var i = 0; i < lines.length; i++) {
    var L = lines[i];
    if (!L.trim()) { out.push(''); continue; }
    // 表格占位符行：不包 <p>，也不被续行 <br> 合并
    if (L.indexOf('\u0001MDT') === 0 && L.charCodeAt(L.length - 1) === 1) {
      out.push(L); continue;
    }
    if (L.match(/^<(h[1-4]|ul|ol|li|\/ul|\/ol|blockquote|hr|p|div)/)) { out.push(L); continue; }
    var prev = out[out.length-1] || '';
    if (prev.startsWith('<p>') && !prev.endsWith('</p>')) {
      out[out.length-1] += '<br>' + L;
    } else {
      out.push('<p>' + L);
    }
  }
  var final = out.map(function(r){
    return (r.startsWith('<p>') && !r.endsWith('</p>')) ? r+'</p>' : r;
  }).join('\n');

  // 3. 替换回真实表格 HTML
  tbl.tables.forEach(function(t, k){
    final = final.replace('\u0001MDT' + k + '\u0001', t);
  });
  return final;
}

// ── Init ────────────────────────────────────────

function boot() {
  // 导航：立即绑定，不等待任何数据
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => go(btn.dataset.page));
  });
  // 等所有 defer 脚本加载完毕后再触发首屏
  setTimeout(() => go('dashboard'), 10);
}

// ── 手动刷新解读 (供 insights 页按钮调用) ────────

async function refreshInsightsNow() {
  const btn = $('btnRefreshInsights');
  if (btn) {
    btn.textContent = '⏳ 刷新中...';
    btn.classList.add('loading');
  }
  const result = await post('/refresh/insights');
  if (btn) {
    btn.textContent = '🔄 刷新';
    btn.classList.remove('loading');
  }
  if (result?.success) {
    APP.ins = null;
    await loadIns();
  } else {
    alert('刷新失败: ' + (result?.message || '未知错误'));
  }
}

// 关键：DOMContentLoaded 不再被外部 CDN 阻塞
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();  // defer 脚本执行时 DOM 已经 ready
}
