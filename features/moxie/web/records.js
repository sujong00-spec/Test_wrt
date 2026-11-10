/* 默写档案：记录列表、上传批改与复核、错题本、能力评估。
   依赖 app.js 暴露的 window.MOXIE（state/api/show/...）。 */

(function () {
  const M = window.MOXIE;
  const $ = (s) => document.querySelector(s);

  const R = {
    records: [],
    filter: '',          // '' | 'zh' | 'en'
    detail: null,
    patches: {},         // gradingId -> {verdict, written}
    wrong: [],
    wrongFilter: '',
    days: 14,
  };

  const VERDICT_TEXT = { correct: '对', wrong: '错', missing: '没写', unknown: '待定' };
  const CYCLE = { correct: 'wrong', wrong: 'missing', missing: 'correct', unknown: 'correct' };

  /* ---------- 工具 ---------- */

  function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso.replace(' ', 'T'));
    const wd = '日一二三四五六'[d.getDay()];
    return `${d.getMonth() + 1}月${d.getDate()}日 周${wd} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  function fmtDuration(sec) {
    sec = Number(sec || 0);
    if (!sec) return '—';
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m ? `${m}分${s ? s + '秒' : ''}` : `${s}秒`;
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function summaryPills(sum) {
    const box = el('div', 'sum-row');
    if (!sum || !sum.graded) {
      box.appendChild(el('span', 'sum-pill', '还没批改'));
      return box;
    }
    box.appendChild(el('span', 'sum-pill correct', `对 ${sum.correct}`));
    box.appendChild(el('span', 'sum-pill wrong', `错 ${sum.wrong}`));
    box.appendChild(el('span', 'sum-pill missing', `没写 ${sum.missing}`));
    if (sum.accuracy !== null && sum.accuracy !== undefined) {
      box.appendChild(el('span', 'sum-pill acc', `正确率 ${sum.accuracy}%`));
    }
    return box;
  }

  /* ---------- 记录列表 ---------- */

  async function openRecords() {
    M.show('records');
    await loadRecords();
  }

  async function loadRecords() {
    const box = $('#records-list');
    box.innerHTML = '';
    box.appendChild(el('p', 'rec-sub', '读取中…'));
    try {
      const q = R.filter ? '?subject=' + R.filter : '';
      const data = await M.api('/api/records' + q);
      R.records = data.records || [];
    } catch (e) {
      box.innerHTML = '';
      box.appendChild(el('p', 'rec-sub', '读不到记录：' + e.message));
      return;
    }
    box.innerHTML = '';
    if (!R.records.length) {
      box.appendChild(el('p', 'rec-sub', '还没有默写记录。默写一轮之后这里就有了。'));
      return;
    }
    R.records.forEach((rec) => {
      const row = el('div', 'rec');
      const main = el('div', 'rec-main');
      const badge = el('span', 'rec-badge' + (rec.subject === 'en' ? ' is-en' : ''), rec.subject === 'en' ? '英文' : '中文');
      const date = el('div', 'rec-date', fmtDate(rec.started_at));
      const sub = el('div', 'rec-sub',
        `${rec.item_count} 条 · ${rec.char_count} 字${rec.word_count ? ' / ' + rec.word_count + ' 词' : ''} · ${fmtDuration(rec.duration_sec)}`
        + (rec.completed ? '' : ' · 未念完'));
      main.append(date, sub);
      row.append(badge, main);
      const sum = rec.summary;
      if (sum && sum.graded) {
        const acc = el('div', 'rec-acc', `${sum.accuracy}%`);
        acc.style.color = sum.accuracy >= 80 ? '#0f9c72' : (sum.accuracy >= 60 ? '#ef8a1f' : '#c0392b');
        row.appendChild(acc);
      } else {
        row.appendChild(el('span', 'rec-badge is-pending', '待批改'));
      }
      row.onclick = () => openRecord(rec.id);
      box.appendChild(row);
    });
  }

  /* ---------- 记录详情 / 批改 ---------- */

  async function openRecord(id, autoUpload) {
    R.patches = {};
    M.show('record');
    const box = $('#record-items');
    const sumBox = $('#record-summary');
    const tip = $('#record-tip');
    box.innerHTML = '';
    sumBox.textContent = '读取中…';
    tip.textContent = '';
    $('#btn-grade-vision').hidden = true;
    try {
      const data = await M.api('/api/record?id=' + id);
      R.detail = data;
    } catch (e) {
      sumBox.textContent = '读不到这一轮：' + e.message;
      return;
    }
    renderRecord();
    if (autoUpload) {
      setTimeout(() => $('#file-answer').click(), 400);
    }
  }

  function renderRecord() {
    const d = R.detail;
    const box = $('#record-items');
    const sumBox = $('#record-summary');
    const tip = $('#record-tip');
    if (!d || !d.session) return;
    const s = d.session;
    $('#record-title').textContent = (s.subject === 'en' ? '英文默写' : '中文默写') + ' · ' + fmtDate(s.started_at);
    sumBox.innerHTML = '';
    sumBox.appendChild(el('div', 'panel-title',
      `${s.item_count} 条 · ${s.char_count} 字 · ${fmtDuration(s.duration_sec)}`));
    sumBox.appendChild(summaryPills(d.summary));
    const has = d.gradings && d.gradings.length;
    $('#btn-grade-vision').hidden = !has;

    box.innerHTML = '';
    if (!has) {
      (d.items || []).forEach((it, i) => {
        const row = el('li', 'g-item');
        const main = el('div', 'g-main');
        main.appendChild(el('div', 'g-expected', `${i + 1}. ${it.text}`));
        main.appendChild(el('div', 'g-written', '还没上传批改'));
        row.appendChild(main);
        box.appendChild(row);
      });
      tip.textContent = '写完的纸拍一张上传，就能自动逐条判对错；判完你可以逐条改。';
      return;
    }

    const labels = d.labels || VERDICT_TEXT;
    d.gradings.forEach((g, i) => {
      const row = el('li', 'g-item');
      const main = el('div', 'g-main');
      main.appendChild(el('div', 'g-expected', `${i + 1}. ${g.expected}`));
      const written = el('div', 'g-written', g.written ? `写的：${g.written}` : '（没写）');
      main.appendChild(written);
      if (g.hint) main.appendChild(el('div', 'g-hint', g.hint));
      const chip = el('button', 'g-chip ' + (g.verdict || 'unknown'),
        labels[g.verdict] || VERDICT_TEXT[g.verdict] || '待定');
      chip.onclick = () => {
        const cur = currentVerdict(g);
        const next = CYCLE[cur] || 'correct';
        R.patches[g.id] = { verdict: next, written: currentWritten(g) };
        g.verdict = next;
        chip.className = 'g-chip ' + next;
        chip.textContent = labels[next] || VERDICT_TEXT[next];
        updateLiveSummary();
      };
      const edit = el('button', 'g-chip g-edit unknown', '✎');
      edit.onclick = () => {
        M.openSheet('孩子写的是什么？', currentWritten(g), (t) => {
          const text = t === null ? '' : t;
          R.patches[g.id] = { written: text, verdict: text.trim() ? currentVerdict(g) : 'missing' };
          written.textContent = text.trim() ? '写的：' + text : '（没写）';
          if (!text.trim()) {
            g.verdict = 'missing';
            chip.className = 'g-chip missing';
            chip.textContent = labels.missing || '没写';
          }
        }, false, '留空表示没写');
      };
      row.append(main, chip, edit);
      box.appendChild(row);
    });
    tip.textContent = d.result && d.result.scan_method !== 'vision'
      ? `批改方式：${(d.result.method === 'vision') ? '视觉模型精批' : '手写识别'}　点右边的小圆点可以改判定，改完点「保存复核」。`
      : '点右边的小圆点可以改判定，改完点「保存复核」。';
  }

  function currentVerdict(g) {
    const p = R.patches[g.id];
    return (p && p.verdict) || g.verdict || 'unknown';
  }

  function currentWritten(g) {
    const p = R.patches[g.id];
    return (p && p.written !== undefined) ? p.written : (g.written || '');
  }

  function updateLiveSummary() {
    const d = R.detail;
    if (!d || !d.gradings) return;
    const counts = { correct: 0, wrong: 0, missing: 0, unknown: 0 };
    d.gradings.forEach((g) => {
      const v = currentVerdict(g);
      counts[v] = (counts[v] || 0) + 1;
    });
    const graded = counts.correct + counts.wrong + counts.missing;
    const acc = graded ? Math.round((counts.correct / graded) * 1000) / 10 : null;
    const box = $('#record-summary');
    box.innerHTML = '';
    const s = d.session;
    box.appendChild(el('div', 'panel-title',
      `${s.item_count} 条 · ${s.char_count} 字 · ${fmtDuration(s.duration_sec)}`));
    const pills = el('div', 'sum-row');
    pills.appendChild(el('span', 'sum-pill correct', `对 ${counts.correct}`));
    pills.appendChild(el('span', 'sum-pill wrong', `错 ${counts.wrong}`));
    pills.appendChild(el('span', 'sum-pill missing', `没写 ${counts.missing}`));
    if (acc !== null) pills.appendChild(el('span', 'sum-pill acc', `正确率 ${acc}%`));
    box.appendChild(pills);
  }

  async function uploadAnswer(file) {
    if (!file || !R.detail) return;
    M.overlay('正在认孩子写的字…', '用手写识别，大概几秒');
    try {
      const blob = await M.compress(file);
      const res = await fetch('/api/result?session=' + R.detail.session.id, {
        method: 'POST',
        headers: { 'Content-Type': 'image/jpeg' },
        body: blob,
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || '批改失败');
      M.hideOverlay();
      R.patches = {};
      R.detail = data;
      renderRecord();
      M.toast('批改好了，看一眼有没有认错的，改完点「保存复核」。');
    } catch (e) {
      M.hideOverlay();
      M.toast(e.message);
    }
  }

  async function saveReflect() {
    if (!R.detail || !R.detail.result) { M.toast('还没有批改结果'); return; }
    const patches = R.patches;
    if (!Object.keys(patches).length) { M.toast('没有改动'); return; }
    try {
      const data = await M.api('/api/gradings/reflect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resultId: R.detail.result.id, session: R.detail.session.id, patches }),
      });
      R.patches = {};
      R.detail = data;
      renderRecord();
      M.toast('已保存复核结果');
    } catch (e) {
      M.toast(e.message);
    }
  }

  async function visionGrade() {
    if (!R.detail || !R.detail.result) { M.toast('先上传孩子写的照片'); return; }
    M.overlay('视觉模型逐条精批中…', '慢一点，大概半分钟');
    try {
      const data = await M.api('/api/result/vision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session: R.detail.session.id, resultId: R.detail.result.id }),
      });
      R.patches = {};
      R.detail = data;
      renderRecord();
      M.hideOverlay();
      M.toast('精批完成');
    } catch (e) {
      M.hideOverlay();
      M.toast(e.message);
    }
  }

  /* ---------- 错题本 ---------- */

  async function openWrongbook() {
    M.show('wrongbook');
    await loadWrongbook();
  }

  async function loadWrongbook() {
    const box = $('#wrong-list');
    box.innerHTML = '';
    box.appendChild(el('p', 'rec-sub', '读取中…'));
    try {
      const q = R.wrongFilter ? '?subject=' + R.wrongFilter : '';
      const data = await M.api('/api/wrongbook' + q);
      R.wrong = data.items || [];
    } catch (e) {
      box.innerHTML = '';
      box.appendChild(el('p', 'rec-sub', '读不到错题：' + e.message));
      return;
    }
    box.innerHTML = '';
    if (!R.wrong.length) {
      box.appendChild(el('p', 'rec-sub', '错题本是空的：最近的默写要么全对，要么还没批改。'));
      return;
    }
    R.wrong.forEach((w) => {
      const row = el('div', 'wrong-item');
      const top = el('div', 'wrong-top');
      top.appendChild(el('div', 'wrong-text', w.expected));
      top.appendChild(el('div', 'wrong-times', `错 ${w.times} 次`));
      row.appendChild(top);
      const meta = [];
      meta.push(w.subject === 'en' ? '英文' : '中文');
      if (w.last_written) meta.push('上次写成「' + w.last_written + '」');
      if (w.last_at) meta.push(fmtDate(w.last_at).slice(0, 12));
      row.appendChild(el('div', 'wrong-meta', meta.join(' · ')));
      box.appendChild(row);
    });
  }

  async function retryWrong() {
    try {
      const data = await M.api('/api/wrongbook/retry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: R.wrongFilter || M.state.subject, limit: 10 }),
      });
      if (!data.items.length) { M.toast('错题本是空的，先默一轮并批改。'); return; }
      M.state.items = data.items;
      M.state.subject = data.items[0].lang || 'zh';
      M.state.name = '错题复习';
      M.renderItems();
      M.show('list');
      M.prepare();
      M.toast(`已把 ${data.items.length} 道错题放进清单`);
    } catch (e) {
      M.toast(e.message);
    }
  }

  /* ---------- 能力评估 ---------- */

  async function openStats() {
    M.show('stats');
    await loadStats();
  }

  function bars(series, key, color, unit) {
    const max = Math.max(1, ...series.map((d) => d[key] || 0));
    const wrap = el('div');
    series.forEach((d) => {
      const row = el('div', 'bar-row');
      row.appendChild(el('div', 'bar-name', d.date.slice(5)));
      const track = el('div', 'bar-track');
      const fill = el('div', 'bar-fill');
      fill.style.width = Math.round(((d[key] || 0) / max) * 100) + '%';
      fill.style.background = color;
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el('div', 'bar-val', String(d[key] || 0) + (unit || '')));
      wrap.appendChild(row);
    });
    return wrap;
  }

  function lineChart(series) {
    const pts = series.filter((d) => d.accuracy !== null && d.accuracy !== undefined);
    const w = 320, h = 140, pad = 24;
    if (!pts.length) return el('p', 'rec-sub', '还没有批改数据，上传一次默写结果就有曲线了。');
    const step = pts.length > 1 ? (w - pad * 2) / (pts.length - 1) : 0;
    const xy = pts.map((d, i) => {
      const x = pad + step * i;
      const y = h - pad - (Math.max(0, Math.min(100, d.accuracy)) / 100) * (h - pad * 2);
      return [x, y, d];
    });
    const path = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
    const dots = xy.map(([x, y, d]) =>
      `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.5" fill="#f0761f"></circle>`).join('');
    const svg = `<svg class="chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#e2eaf8" stroke-width="1"></line>
      <line x1="${pad}" y1="${pad}" x2="${w - pad}" y2="${pad}" stroke="#eef2fb" stroke-width="1" stroke-dasharray="4 4"></line>
      <path d="${path}" fill="none" stroke="#f0761f" stroke-width="2.5" stroke-linejoin="round"></path>
      ${dots}
    </svg>`;
    const box = el('div');
    box.innerHTML = svg;
    const legend = el('div', 'chart-legend');
    legend.appendChild(el('span', null, `${pts.length} 次批改 · 最近 ${pts[pts.length - 1].accuracy}%`));
    box.appendChild(legend);
    return box;
  }

  async function loadStats() {
    const box = $('#stats-body');
    box.innerHTML = '';
    box.appendChild(el('p', 'rec-sub', '统计中…'));
    let s;
    try {
      s = await M.api('/api/stats?days=' + R.days);
    } catch (e) {
      box.innerHTML = '';
      box.appendChild(el('p', 'rec-sub', '读不到统计：' + e.message));
      return;
    }
    box.innerHTML = '';
    const t = s.totals;

    const grid = el('div', 'stat-grid');
    const cells = [
      [t.sessions, '默写轮次'],
      [t.chars + (t.words ? `字 / ${t.words}词` : '字'), '累计默写量'],
      [t.accuracy === null ? '—' : t.accuracy + '%', '平均正确率'],
      [t.streak + ' 天', '连续打卡'],
    ];
    cells.forEach(([num, label]) => {
      const cell = el('div', 'stat-cell');
      cell.appendChild(el('div', 'stat-num', String(num)));
      cell.appendChild(el('div', 'stat-label', label));
      grid.appendChild(cell);
    });
    box.appendChild(grid);

    const p1 = el('div', 'panel');
    p1.appendChild(el('div', 'panel-title', `最近 ${R.days} 天默写量（字）`));
    p1.appendChild(bars(s.daily, 'chars', '#f0761f', ''));
    p1.appendChild(el('div', 'chart-legend', `共 ${s.daily.reduce((a, d) => a + d.sessions, 0)} 轮 · ${s.daily.reduce((a, d) => a + d.chars, 0)} 字`));
    box.appendChild(p1);

    const p2 = el('div', 'panel');
    p2.appendChild(el('div', 'panel-title', '正确率趋势'));
    p2.appendChild(lineChart(s.daily));
    box.appendChild(p2);

    const p3 = el('div', 'panel');
    p3.appendChild(el('div', 'panel-title', '中文 / 英文 对比'));
    [['zh', '中文'], ['en', '英文']].forEach(([key, name]) => {
      const b = s.by_subject[key];
      const row = el('div', 'bar-row');
      row.appendChild(el('div', 'bar-name', name));
      const track = el('div', 'bar-track');
      const fill = el('div', 'bar-fill');
      fill.style.width = (b.accuracy === null ? 0 : b.accuracy) + '%';
      fill.style.background = key === 'en' ? '#7c5cff' : '#3e8bff';
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el('div', 'bar-val', (b.accuracy === null ? '—' : b.accuracy + '%')));
      p3.appendChild(row);
      p3.appendChild(el('div', 'rec-sub',
        `${b.sessions} 轮 · ${b.items} 条 · ${b.chars} 字 · 共 ${b.minutes} 分钟`));
    });
    box.appendChild(p3);

    const p4 = el('div', 'panel');
    p4.appendChild(el('div', 'panel-title', '最常错的内容'));
    if (!s.wrong_top.length) {
      p4.appendChild(el('p', 'rec-sub', '暂时没有错题记录。'));
    } else {
      const max = Math.max(...s.wrong_top.map((w) => w.times));
      s.wrong_top.forEach((w) => {
        const row = el('div', 'bar-row');
        row.appendChild(el('div', 'bar-name', w.expected));
        const track = el('div', 'bar-track');
        const fill = el('div', 'bar-fill');
        fill.style.width = Math.round((w.times / max) * 100) + '%';
        fill.style.background = '#e05a4e';
        track.appendChild(fill);
        row.appendChild(track);
        row.appendChild(el('div', 'bar-val', `${w.times} 次`));
        p4.appendChild(row);
      });
    }
    box.appendChild(p4);
  }

  /* ---------- 绑定 ---------- */

  function bindRecords() {
    const rec = $('#btn-records');
    const wrong = $('#btn-wrongbook');
    const stats = $('#btn-stats');
    if (rec) rec.onclick = openRecords;
    if (wrong) wrong.onclick = openWrongbook;
    if (stats) stats.onclick = openStats;

    $('#btn-grade-upload').onclick = () => $('#file-answer').click();
    $('#file-answer').onchange = (e) => uploadAnswer(e.target.files[0]);
    $('#btn-grade-save').onclick = saveReflect;
    $('#btn-grade-vision').onclick = visionGrade;
    $('#btn-wrong-refresh').onclick = loadWrongbook;
    $('#btn-wrong-retry').onclick = retryWrong;

    $('#records-filter').onclick = () => {
      R.filter = R.filter === '' ? 'zh' : (R.filter === 'zh' ? 'en' : '');
      $('#records-filter').textContent = R.filter === '' ? '全' : (R.filter === 'zh' ? '中' : '英');
      loadRecords();
    };
    $('#wrong-filter').onclick = () => {
      R.wrongFilter = R.wrongFilter === '' ? 'zh' : (R.wrongFilter === 'zh' ? 'en' : '');
      $('#wrong-filter').textContent = R.wrongFilter === '' ? '全' : (R.wrongFilter === 'zh' ? '中' : '英');
      loadWrongbook();
    };
    $('#stats-range').onclick = () => {
      R.days = R.days === 14 ? 30 : 14;
      $('#stats-range').textContent = R.days + '天';
      loadStats();
    };

    document.querySelectorAll('[data-go="records"]').forEach((b) => {
      b.onclick = () => openRecords();
    });
  }

  async function refreshHomeNotes() {
    try {
      const data = await M.api('/api/stats?days=14');
      const t = data.totals;
      const note = $('#records-note');
      if (note) note.textContent = t.sessions ? `${t.sessions} 轮 · ${t.chars} 字` : '每轮都在这里';
      const wn = $('#wrong-note');
      if (wn) {
        const w = M.api('/api/wrongbook').then((d) => {
          const n = (d.items || []).length;
          if (wn) wn.textContent = n ? `${n} 个错过的字词` : '错过的字词';
        }).catch(() => {});
      }
    } catch (e) { /* 忽略 */ }
  }

  window.MOXIE_RECORDS = {
    openRecord,
    openRecords,
    openWrongbook,
    openStats,
    refreshHomeNotes,
  };

  bindRecords();
  refreshHomeNotes();
})();
