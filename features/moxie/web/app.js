/* 小学生默写助手 · 前端
   三个页面：首页（拍照/图片/手输）→ 清单（核对 + 节奏/语速）→ 播放（逐条念）。
   播放规则由服务端给（/api/plan），这里只负责按顺序播、按节奏停。 */

const $ = (s) => document.querySelector(s);

const state = {
  items: [],
  name: '',
  mode: 'manual',
  speed: 'normal',
  subject: 'zh',
  plan: null,
  idx: 0,
  paused: false,
  running: false,
  token: 0,
  lastImage: null,
  paceFast: 10,
  paceSlow: 20,
  editing: -1,
  sessionId: null,
  lastSessionId: null,
  playStartedAt: 0,
  pausedMs: 0,
  pauseStartedAt: 0,
};

const player = $('#player');
const SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';

/* ---------- 基础工具 ---------- */

async function api(path, options = {}) {
  const res = await fetch(path, options);
  let data = {};
  try { data = await res.json(); } catch (e) { /* 忽略非 JSON */ }
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `请求失败（${res.status}）`);
  }
  return data;
}

function show(id) {
  document.querySelectorAll('.screen').forEach((el) => el.classList.remove('is-active'));
  const el = document.getElementById('screen-' + id);
  if (el) el.classList.add('is-active');
  document.body.classList.toggle('is-playing', id === 'play');
  document.documentElement.classList.toggle('is-playing', id === 'play');
  window.scrollTo(0, 0);
}

function overlay(title, note) {
  $('#overlay-title').textContent = title;
  $('#overlay-note').textContent = note || '';
  $('#overlay').hidden = false;
}

function hideOverlay() { $('#overlay').hidden = true; }

function toast(msg) {
  window.alert(msg);
}

function unlockAudio() {
  try {
    player.src = SILENT;
    player.play().catch(() => {});
  } catch (e) { /* 忽略 */ }
}

/* ---------- 图片处理：压到 1600px 以内再传 ---------- */

function compress(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const max = 1600;
      let { width, height } = img;
      const scale = Math.min(1, max / Math.max(width, height));
      width = Math.round(width * scale);
      height = Math.round(height * scale);
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);
      canvas.toBlob((blob) => {
        if (blob) resolve(blob); else reject(new Error('图片处理失败'));
      }, 'image/jpeg', 0.88);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('这张图片读不出来，换一张试试')); };
    img.src = url;
  });
}

async function handleFile(file) {
  if (!file) return;
  state.lastImage = file;
  overlay('正在认字…', state.subject === 'en' ? '英文内容大概 2 秒' : '先用手写识别，大概 2 秒');
  try {
    const blob = await compress(file);
    const data = await api('/api/recognize?lang=' + encodeURIComponent(state.subject), {
      method: 'POST',
      headers: { 'Content-Type': 'image/jpeg' },
      body: blob,
    });
    hideOverlay();
    if (!data.items.length) { toast('没认出内容，换成更清晰的照片，或手动输入。'); return; }
    state.items = data.items;
    state.name = new Date().toLocaleDateString('zh-CN');
    renderItems();
    show('list');
    prepare();
  } catch (err) {
    hideOverlay();
    overlay('没认出来', err.message);
    setTimeout(() => { hideOverlay(); }, 2600);
  }
}

/* ---------- 清单 ---------- */

function kindLabel(it) {
  const en = it && it.lang === 'en';
  if (it && it.kind === 'sentence') return '句子';
  return en ? '单词' : '词语';
}

function renderItems() {
  const ul = $('#items');
  ul.innerHTML = '';
  $('#list-empty').hidden = state.items.length > 0;
  $('#list-count').textContent = state.items.length
    ? `共 ${state.items.length} 条 · ${state.subject === 'en' ? '英文' : '中文'}`
    : '';

  state.items.forEach((it, i) => {
    const li = document.createElement('li');
    li.className = 'item' + (it.kind === 'sentence' ? ' is-sentence' : '')
      + (it.lang === 'en' ? ' is-en' : '');

    const num = document.createElement('div');
    num.className = 'item-num';
    num.textContent = String(i + 1);

    const text = document.createElement('div');
    text.className = 'item-text';
    text.textContent = it.text;
    text.title = '点一下改这条';
    text.onclick = () => openEdit(i);
    const kd = document.createElement('div');
    kd.className = 'item-kind';
    kd.textContent = kindLabel(it);
    text.appendChild(kd);

    const btns = document.createElement('div');
    btns.className = 'item-btns';

    const playBtn = document.createElement('button');
    playBtn.className = 'mini-btn';
    playBtn.textContent = '🔊';
    playBtn.title = '试听';
    playBtn.setAttribute('aria-label', '试听这一条');
    playBtn.onclick = () => previewItem(i, playBtn);

    const editBtn = document.createElement('button');
    editBtn.className = 'mini-btn';
    editBtn.textContent = '✎';
    editBtn.title = '编辑';
    editBtn.setAttribute('aria-label', '编辑这一条');
    editBtn.onclick = () => openEdit(i);

    const delBtn = document.createElement('button');
    delBtn.className = 'mini-btn mini-btn-del';
    delBtn.textContent = '🗑';
    delBtn.title = '删除';
    delBtn.setAttribute('aria-label', '删除这一条');
    delBtn.onclick = () => {
      if (!window.confirm(`删掉「${state.items[i].text}」？`)) return;
      state.items.splice(i, 1);
      renderItems();
      saveList();
    };

    btns.append(playBtn, editBtn, delBtn);
    li.append(num, text, btns);
    ul.appendChild(li);
  });
}

async function previewItem(i, btn) {
  const it = state.items[i];
  if (!it) return;
  const data = await api('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: [it], speed: state.speed, mode: state.mode }),
  });
  const steps = data.items[0].steps;
  unlockAudio();
  if (btn) { btn.classList.add('is-playing'); btn.textContent = '⏸'; }
  try {
    for (const s of steps) {
      await waitForAudio(s.key, 90);
      await playUrl(s.url);
      await wait(s.gapAfterMs || 0);
    }
  } catch (err) {
    toast(err.message);
  } finally {
    if (btn) { btn.classList.remove('is-playing'); btn.textContent = '🔊'; }
  }
}

function saveList() {
  return api('/api/list', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: state.name, items: state.items }),
  }).catch(() => {});
}

/* ---------- 手动输入 / 编辑弹层 ---------- */

function openSheet(title, value, onOk, showTools, placeholder) {
  $('#sheet-manual').hidden = false;
  $('#sheet-manual').querySelector('.sheet-title').textContent = title;
  const ta = $('#manual-text');
  ta.value = value || '';
  ta.rows = showTools ? 3 : 8;
  ta.placeholder = placeholder || '一行一条，例如：\n春天\n花朵\n小鸟在树上唱歌。';
  $('#manual-tools').hidden = !showTools;
  const ok = $('#manual-ok');
  ok.onclick = async () => {
    const text = $('#manual-text').value;
    $('#sheet-manual').hidden = true;
    await onOk(text);
  };
}

function closeSheet() { $('#sheet-manual').hidden = true; state.editing = -1; }

function openEdit(i) {
  state.editing = i;
  const it = state.items[i];
  if (!it) return;
  openSheet('改一条', it.text, async (text) => {
    const t = text.trim();
    if (!t) return;
    try {
      const data = await api('/api/recognize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: t, lang: state.subject }),
      });
      state.items[i] = data.items[0] || state.items[i];
    } catch (err) { state.items[i].text = t; }
    renderItems();
    saveList();
    prepare();
  }, true);
}

/* ---------- 默写档案：一轮的开始与结束 ---------- */

async function sessionStart() {
  try {
    const data = await api('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: state.subject, items: state.items,
                             mode: state.mode, speed: state.speed }),
    });
    state.sessionId = data.session.id;
  } catch (e) {
    state.sessionId = null;
  }
  state.playStartedAt = Date.now();
  state.pausedMs = 0;
  state.pauseStartedAt = 0;
}

function sessionSeconds() {
  if (!state.playStartedAt) return 0;
  let ms = Date.now() - state.playStartedAt - state.pausedMs;
  if (state.pauseStartedAt) ms -= Date.now() - state.pauseStartedAt;
  return Math.max(1, Math.round(ms / 1000));
}

async function sessionFinish(completed) {
  if (!state.sessionId) return;
  const id = state.sessionId;
  state.sessionId = null;
  try {
    await api('/api/session/finish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, durationSec: sessionSeconds(), completed: completed ? 1 : 0 }),
    });
  } catch (e) { /* 记录不上就算了，别影响孩子做题 */ }
  state.playStartedAt = 0;
  state.pausedMs = 0;
  state.pauseStartedAt = 0;
}

/* ---------- 播放 ---------- */

function wait(ms) { return new Promise((r) => setTimeout(r, ms)); }

function playUrl(url) {
  return new Promise((resolve, reject) => {
    let done = false;
    let timer = null;
    const finish = () => {
      if (done) return;
      done = true;
      if (timer) clearTimeout(timer);
      player.onended = null;
      player.onerror = null;
      resolve();
    };
    const arm = (ms) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(finish, ms);      // 兜底：音频被打断时也不会卡住
    };
    player.onended = finish;
    player.onerror = () => { done = true; if (timer) clearTimeout(timer); reject(new Error('这条语音没播出来，点「再念一遍」试试')); };
    player.onloadedmetadata = () => arm((player.duration || 20) * 1000 + 3000);
    player.src = url;
    arm(35000);
    player.play().catch((err) => { if (!done) { done = true; clearTimeout(timer); reject(err); } });
  });
}

async function waitForAudio(key, seconds = 120) {
  const step = 700;
  for (let waited = 0; waited < seconds * 1000; waited += step) {
    const data = await fetch('/api/audio/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts: state.plan.texts, speed: state.speed }),
    }).then((r) => r.json()).catch(() => null);
    if (data && data.status && data.status[key] === 'ready') return true;
    if (data && data.status && data.status[key] === 'failed') {
      throw new Error(data.error || '语音合成失败了，检查一下网络再重试');
    }
    setStage('正在准备语音…', '第一次念新内容需要一点点时间', 'speaking');
    await wait(step);
  }
  throw new Error('语音准备超时了，检查一下网络再重试');
}

function setStage(state, sub, cls) {
  $('#stage-state').textContent = state;
  $('#stage-sub').textContent = sub || '';
  const card = $('#stage-card');
  card.classList.remove('is-speaking', 'is-writing', 'is-done');
  if (cls) card.classList.add(cls);
}

function renderDots() {
  const box = $('#play-dots');
  box.innerHTML = '';
  state.items.forEach((_, i) => {
    const d = document.createElement('span');
    d.className = 'dot' + (i < state.idx ? ' is-done' : i === state.idx ? ' is-now' : '');
    box.appendChild(d);
  });
  $('#play-progress').textContent = `第 ${Math.min(state.idx + 1, state.items.length)} / ${state.items.length} 条`;
}

function countdown(seconds) {
  return new Promise((resolve) => {
    const ring = $('#ring');
    const fg = $('#ring-fg');
    const num = $('#ring-num');
    ring.hidden = false;
    let left = seconds;
    num.textContent = left;
    fg.style.strokeDashoffset = 0;
    const timer = setInterval(() => {
      left -= 1;
      num.textContent = Math.max(left, 0);
      const total = seconds || 1;
      fg.style.strokeDashoffset = String(327 * (1 - Math.max(left, 0) / total));
      if (left <= 0) {
        clearInterval(timer);
        ring.hidden = true;
        resolve();
      }
    }, 1000);
    state.cancelCountdown = () => { clearInterval(timer); ring.hidden = true; resolve(); };
  });
}

async function playItem(i, myToken) {
  state.idx = i;
  renderDots();
  const item = state.plan.items[i];
  if (!item || !item.steps.length) return;

  for (let si = 0; si < item.steps.length; si += 1) {
    const s = item.steps[si];
    if (myToken !== state.token) return;
    setStage('正在念…', si === 0 ? '第一遍' : '第二遍', 'speaking');
    await waitForAudio(s.key, 120);
    if (myToken !== state.token) return;
    await playUrl(s.url);
    if (s.gapAfterMs) await wait(s.gapAfterMs);
  }
  if (myToken !== state.token) return;

  if (i >= state.items.length - 1) {
    await finish(myToken);
    return;
  }
  if (state.mode === 'manual') {
    setStage('写好了吗', '写完点「下一个」，或者等我念下一条', 'writing');
    return;
  }
  const secs = state.mode === 'autoSlow' ? state.paceSlow : state.paceFast;
  setStage('写吧', `${secs} 秒后念下一条`, 'writing');
  await countdown(secs);
  if (myToken !== state.token) return;
  await playItem(i + 1, myToken);
}

async function finish(myToken) {
  state.running = false;
  const end = state.plan.phrases.end;
  if (end) {
    await waitForAudio(end.key, 60).catch(() => false);
    if (myToken === state.token) await playUrl(end.url).catch(() => {});
  }
  const sid = state.sessionId || state.lastSessionId;
  if (state.sessionId) {
    state.lastSessionId = state.sessionId;
    await sessionFinish(1);
  }
  setStage('默写结束，你真棒！', '写完的纸拍一张，就能自动批改', 'done');
  $('#play-progress').textContent = `${state.items.length} / ${state.items.length} 条，全部完成`;
  const btn = $('#btn-pause');
  btn.dataset.action = 'grade';
  if (sid) btn.dataset.session = String(sid);
  btn.innerHTML = '<span>📷</span>拍照批改';
}

async function startPlay(from) {
  state.token += 1;
  const myToken = state.token;
  state.running = true;
  state.paused = false;
  $('#btn-pause').innerHTML = '<span>⏸</span>暂停';
  if (from !== undefined) state.idx = from;
  await playItem(state.idx, myToken);
}

async function prepare() {
  const data = await api('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: state.items, speed: state.speed, mode: state.mode }),
  });
  state.plan = data;
  state.paceFast = data.paceFast;
  state.paceSlow = data.paceSlow;
  return data;
}

async function prepareWithFeedback() {
  overlay('正在准备语音…', '第一次念的内容要先合成，稍等一下下');
  const delay = 900;
  const started = Date.now();
  try {
    await prepare();
    while (true) {
      const st = await api('/api/audio/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts: state.plan.texts, speed: state.speed }),
      });
      if (st.ready >= st.total) break;
      overlay('正在准备语音…', `正在准备 ${st.ready}/${st.total} 句`);
      if (Date.now() - started > 300000) throw new Error('语音准备超时，检查网络后再试');
      await wait(1500);
    }
    hideOverlay();
    return true;
  } catch (err) {
    hideOverlay();
    toast(err.message);
    return false;
  }
}

/* ---------- 设置 / 功能 ---------- */

function paintSubject() {
  document.querySelectorAll('#seg-subject button').forEach((b) => {
    b.classList.toggle('is-on', b.dataset.val === state.subject);
  });
  $('#home-sub').textContent = state.subject === 'en'
    ? '英文默写：拍下听写内容，一个词一个词念给你听。'
    : '中文默写：拍下作业本，一条一条念给你听。';
  $('#btn-photo').querySelector('.card-note').textContent = state.subject === 'en'
    ? '对着听写单拍一张，自动认出英文内容'
    : '对着作业本拍一张，自动认出手写内容';
}

function paintSegs() {
  document.querySelectorAll('#seg-mode button').forEach((b) => {
    b.classList.toggle('is-on', b.dataset.val === state.mode);
  });
  document.querySelectorAll('#seg-speed button').forEach((b) => {
    b.classList.toggle('is-on', b.dataset.val === state.speed);
  });
  $('#mode-note').textContent = state.mode === 'manual'
    ? '你点「下一个」才念下一条'
    : (state.mode === 'autoFast' ? `每条念完停 ${state.paceFast} 秒，自动念下一条` : `每条念完停 ${state.paceSlow} 秒，自动念下一条`);
}

async function loadSettings() {
  try {
    const data = await api('/api/settings');
    const s = data.settings || {};
    state.mode = s.mode || 'manual';
    state.subject = s.subject || 'zh';
    state.speed = s.speed || 'normal';
    state.paceFast = s.paceFast || 10;
    state.paceSlow = s.paceSlow || 20;
    $('#voice-tag').textContent = s.voiceName ? `音色：${s.voiceName}` : '';
    $('#set-voice').textContent = s.voiceName || '（未配置）';
    $('#set-recognize').textContent = s.recognizeProvider === 'vision' ? '视觉模型' : '手写识别 + 视觉模型兜底';
    $('#set-device').textContent = `${location.host} · 服务在本机电脑上运行`;
    if (!s.voiceReady) {
      $('#home-sub').textContent = '还没配语音通道：可以先用「手动输入」整理清单，配好 key 后就有朗读了（见 README）。';
    }
  } catch (e) { /* 忽略 */ }
  paintSegs();
  paintSubject();
}

async function loadFeatures() {
  try {
    const data = await api('/api/features');
    const box = $('#feature-list');
    box.innerHTML = '';
    (data.features || []).forEach((f) => {
      const div = document.createElement('div');
      div.className = 'panel panel-feature';
      div.innerHTML = `<span class="card-emoji">${f.icon || '📘'}</span>
        <span class="card-body"><span class="card-title">${f.name}</span>
        <span class="card-note">${f.desc || ''}</span></span>`;
      div.onclick = () => { if (f.entry) window.location.href = f.entry; };
      box.appendChild(div);
    });
    const soon = document.createElement('div');
    soon.className = 'panel panel-feature is-soon';
    soon.innerHTML = '<span class="card-emoji">➕</span><span class="card-body">' +
      '<span class="card-title">再加一个学习功能</span>' +
      '<span class="card-note">照着默写这个功能的做法加一个文件夹就能挂上来</span></span>';
    box.appendChild(soon);
  } catch (e) { /* 忽略 */ }
}

/* ---------- 事件绑定 ---------- */

function bind() {
  $('#btn-photo').onclick = () => { state.lastImage = null; $('#file-camera').click(); };
  $('#btn-upload').onclick = () => { state.lastImage = null; $('#file-upload').click(); };
  $('#file-camera').onchange = (e) => handleFile(e.target.files[0]);
  $('#file-upload').onchange = (e) => handleFile(e.target.files[0]);

  $('#btn-manual').onclick = () => {
    openSheet('手动输入', '', async (text) => {
      if (!text.trim()) return;
      try {
        const data = await api('/api/recognize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, lang: state.subject }),
        });
        state.items = data.items;
        state.name = '手动输入';
        renderItems();
        show('list');
        prepare();
      } catch (err) { toast(err.message); }
    }, false);
  };

  $('#manual-cancel').onclick = closeSheet;

  $('#edit-up').onclick = () => {
    const i = state.editing;
    if (i > 0) {
      const tmp = state.items[i - 1];
      state.items[i - 1] = state.items[i];
      state.items[i] = tmp;
    }
    closeSheet();
    renderItems();
    saveList();
  };

  $('#edit-down').onclick = () => {
    const i = state.editing;
    if (i >= 0 && i < state.items.length - 1) {
      const tmp = state.items[i + 1];
      state.items[i + 1] = state.items[i];
      state.items[i] = tmp;
    }
    closeSheet();
    renderItems();
    saveList();
  };

  $('#edit-del').onclick = () => {
    const i = state.editing;
    if (i >= 0) state.items.splice(i, 1);
    closeSheet();
    renderItems();
    saveList();
  };

  $('#btn-last').onclick = async () => {
    try {
      const data = await api('/api/list');
      if (!data.list.items.length) { toast('还没有存过的清单'); return; }
      state.items = data.list.items;
      state.name = data.list.name || '';
      renderItems();
      show('list');
      prepare();
    } catch (err) { toast(err.message); }
  };

  $('#btn-add').onclick = () => {
    openSheet('加一条', '', async (text) => {
      const t = text.trim();
      if (!t) return;
      const data = await api('/api/recognize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: t, lang: state.subject }),
      });
      data.items.forEach((it) => state.items.push(it));
      renderItems();
      saveList();
    }, false);
  };

  $('#btn-reocr').onclick = () => {
    if (!state.lastImage) { toast('这次没有照片，可以点「＋」手动补一条。'); return; }
    if (!window.confirm('重新识别会用新结果替换现在的清单，继续吗？')) return;
    handleFile(state.lastImage);
  };

  $('#btn-start').onclick = async () => {
    if (!state.items.length) { toast('清单是空的，先加一条。'); return; }
    unlockAudio();
    saveList();
    const ok = await prepareWithFeedback();
    if (!ok) return;
    await sessionStart();
    show('play');
    requestWakeLock();
    state.idx = 0;
    startPlay(0);
  };

  document.querySelectorAll('#seg-subject button').forEach((b) => {
    b.onclick = () => {
      state.subject = b.dataset.val;
      paintSubject();
      api('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: state.subject }),
      }).catch(() => {});
    };
  });

  document.querySelectorAll('#seg-mode button, #seg-speed button').forEach((b) => {
    b.onclick = async () => {
      const kind = b.parentElement.id === 'seg-mode' ? 'mode' : 'speed';
      state[kind] = b.dataset.val;
      paintSegs();
      api('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: state.mode, speed: state.speed }),
      }).catch(() => {});
      if (kind === 'speed') prepare().catch(() => {});
    };
  });

  $('#btn-prev').onclick = () => {
    unpause();
    if (state.idx <= 0) {
      playPhrase('first').then(() => startPlay(0));
      return;
    }
    startPlay(state.idx - 1);
  };

  $('#btn-next').onclick = () => {
    unpause();
    if (state.idx >= state.items.length - 1) {
      playPhrase('last').then(() => finish(state.token));
      return;
    }
    startPlay(state.idx + 1);
  };

  $('#btn-repeat').onclick = () => { unpause(); startPlay(state.idx); };

  $('#btn-pause').onclick = () => {
    if ($('#btn-pause').dataset.action === 'grade') {
      const sid = $('#btn-pause').dataset.session;
      $('#btn-pause').dataset.action = '';
      if (sid && window.MOXIE_RECORDS) window.MOXIE_RECORDS.openRecord(Number(sid), true);
      return;
    }
    if (state.paused) { unpause(); return; }
    state.pauseStartedAt = Date.now();
    state.paused = true;
    state.token += 1;             // 停掉正在跑的流程
    cancelCountdown();
    player.pause();
    $('#btn-pause').innerHTML = '<span>▶</span>继续';
    setStage('先歇一会儿', '点「继续」接着念', 'writing');
  };

  $('#btn-quit').onclick = () => {
    sessionFinish(0);
    state.token += 1;
    state.running = false;
    cancelCountdown();
    player.pause();
    releaseWakeLock();
    show('list');
  };

  $('#btn-settings').onclick = () => { loadSettings(); show('settings'); };
  $('#btn-features').onclick = () => { loadFeatures(); show('features'); };
  document.querySelectorAll('[data-go]').forEach((b) => {
    b.onclick = () => {
      state.token += 1;
      cancelCountdown();
      player.pause();
      if (b.dataset.go === 'home') { updateLast(); show('home'); }
    };
  });
}

function unpause() {
  if (state.pauseStartedAt) {
    state.pausedMs += Date.now() - state.pauseStartedAt;
    state.pauseStartedAt = 0;
  }
  if (state.paused) {
    state.paused = false;
    $('#btn-pause').innerHTML = '<span>⏸</span>暂停';
  }
}

function cancelCountdown() { if (state.cancelCountdown) { state.cancelCountdown(); state.cancelCountdown = null; } }

async function playPhrase(name) {
  if (!state.plan || !state.plan.phrases[name]) return;
  const p = state.plan.phrases[name];
  await waitForAudio(p.key, 20).catch(() => false);
  await playUrl(p.url).catch(() => {});
}

/* 屏幕常亮（支持的浏览器才开） */
let wakeLock = null;
async function requestWakeLock() {
  try { if ('wakeLock' in navigator) wakeLock = await navigator.wakeLock.request('screen'); } catch (e) { /* 忽略 */ }
}
function releaseWakeLock() {
  try { if (wakeLock) { wakeLock.release(); wakeLock = null; } } catch (e) { /* 忽略 */ }
}

function updateLast() {
  api('/api/list').then((data) => {
    const items = (data.list && data.list.items) || [];
    const btn = $('#btn-last');
    if (items.length) {
      btn.hidden = false;
      $('#last-note').textContent = `${items.length} 条 · ${data.list.name || '上次的清单'}`;
    } else {
      btn.hidden = true;
    }
  }).catch(() => {});
}

/* ---------- 启动 ---------- */

bind();
loadSettings();
updateLast();

/* 供 records.js 复用 */
window.MOXIE = {
  state, api, show, toast, overlay, hideOverlay, unlockAudio, compress,
  saveList, renderItems, prepare, prepareWithFeedback, updateLast, paintSubject, openSheet,
  subjectLabel: () => (state.subject === 'en' ? '英文' : '中文'),
};
