// TaskTodo - 学生智能任务管理
const API = 'http://localhost:8765/api/tasks';

let state = { tasks:[], schedule:[], tab:'today', editingId:null, loading:false };

// ====== 统一 API 调用（含精细报错）======

async function callApi(path, opts = {}) {
  const url = API + path;
  const method = opts.method || 'GET';
  const timeout = opts.timeout || 30000;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const resp = await fetch(url, {
      ...opts,
      signal: controller.signal,
      headers: opts.body instanceof FormData
        ? opts.headers
        : { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    });

    clearTimeout(timer);

    if (!resp.ok) {
      let detail = '';
      try { const errBody = await resp.json(); detail = errBody.detail || ''; } catch (_) {}
      const msg = detail ? '请求失败 (' + resp.status + '): ' + detail : '请求失败 (' + resp.status + ': ' + resp.statusText + ')';
      return { ok: false, error: msg, status: resp.status };
    }

    const data = await resp.json().catch(() => null);
    return { ok: true, data };
  } catch (e) {
    clearTimeout(timer);
    if (e.name === 'AbortError') return { ok: false, error: '请求超时，后端可能未响应' };
    if (e.message === 'Failed to fetch' || e.message.includes('NetworkError'))
      return { ok: false, error: '无法连接后端 (localhost:8765)\n请用 PowerShell 运行: .\\start.ps1' };
    return { ok: false, error: '网络异常: ' + e.message };
  }
}

// ====== 初始化 ======

async function init() {
  // 先探活
  let ping = { ok: false, error: '' }; try { const pr = await fetch('http://localhost:8765/health'); ping = { ok: pr.ok, data: await pr.json().catch(()=>null) }; } catch(e) { ping = { ok: false, error: '无法连接后端 (localhost:8765)\n请用 PowerShell 运行: .\\start.ps1' }; }
  if (!ping.ok && ping.error.includes('无法连接')) {
    document.getElementById('llmStatus').textContent = '后端未启动: 请在项目目录运行 .\\start.ps1';
    document.getElementById('llmStatus').style.color = 'var(--danger)';
  }

  await loadLLMStatus();
  await loadAll();
  document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', onTabSwitch));
  document.getElementById('btnExtract').addEventListener('click', onExtract);
  document.getElementById('btnAdd').addEventListener('click', () => openModal());
  document.getElementById('fileInput').addEventListener('change', onUploadImage);
  document.getElementById('btnConfig').addEventListener('click', openConfig);
  document.getElementById('configClose').addEventListener('click', closeConfig);
  document.getElementById('configCancel').addEventListener('click', closeConfig);
  document.getElementById('configSave').addEventListener('click', onSaveConfig);
  document.getElementById('configOverlay').addEventListener('click', e => { if (e.target.id==='configOverlay') closeConfig(); });
  document.getElementById('modalClose').addEventListener('click', closeModal);
  document.getElementById('modalCancel').addEventListener('click', closeModal);
  document.getElementById('modalConfirm').addEventListener('click', onSaveTask);
  document.getElementById('modalDelete').addEventListener('click', onDeleteTask);
  document.getElementById('modalOverlay').addEventListener('click', e => { if (e.target.id==='modalOverlay') closeModal(); });
  document.getElementById('inputText').addEventListener('keydown', e => { if (e.ctrlKey && e.key==='Enter') onExtract(); });
}

// ====== 数据加载 ======

async function loadAll() {
  const r1 = await callApi('');
  if (r1.ok) state.tasks = r1.data;
  else toast(r1.error);

  const r2 = await callApi('/schedule', { method:'POST' });
  if (r2.ok) state.schedule = r2.data.schedule || [];

  render();
}

async function loadLLMStatus() {
  try {
    const d = await fetch(API+'/llm-config').then(r=>r.json());
    updateLLMStatusUI(d.has_api_key);
    if (d.has_api_key) {
      document.getElementById('configApiBase').value = d.api_base;
      document.getElementById('configModel').value = d.model;
    }
  } catch(_) {}
}

function updateLLMStatusUI(hasKey) {
  const el = document.getElementById('llmStatus');
  el.style.color = '';
  el.textContent = hasKey
    ? 'AI 已连接，Key 已持久化保存'
    : '配置 API Key 后自动保存，无需重复输入';
}

// ====== AI 配置 ======

async function openConfig() {
  try {
    const d = await fetch(API+'/llm-config').then(r=>r.json());
    document.getElementById('configApiBase').value = d.api_base;
    document.getElementById('configModel').value = d.model;
  } catch(_) {}
  document.getElementById('configApiKey').value = '';
  document.getElementById('configOverlay').classList.add('show');
}
function closeConfig() { document.getElementById('configOverlay').classList.remove('show'); }

async function onSaveConfig() {
  const body = new FormData();
  body.append('api_key', document.getElementById('configApiKey').value);
  body.append('api_base', document.getElementById('configApiBase').value);
  body.append('model', document.getElementById('configModel').value);
  const r = await callApi('/llm-config', { method:'POST', body });
  if (r.ok) {
    updateLLMStatusUI(r.data.has_api_key);
    toast(r.data.has_api_key ? '已保存，下次自动加载' : '未提供 Key');
    closeConfig();
  } else { toast(r.error); }
}

// ====== AI 提取 ======

async function onExtract() {
  const text = document.getElementById('inputText').value.trim();
  if (!text) return toast('请先粘贴文本');
  setLoading(true, 'AI 提取中...');
  const body = new FormData(); body.append('text', text);
  const r = await callApi('/extract', { method:'POST', body, timeout:120000 });
  setLoading(false);
  if (r.ok) {
    document.getElementById('inputText').value = '';
    toast(r.data.extracted + ' 项已提取，新增 ' + r.data.new_tasks + ' 个任务');
    await loadAll();
  } else { toast(r.error); }
}

// ====== 截图上传 ======

async function onUploadImage(e) {
  const file = e.target.files[0];
  if (!file) return;
  setLoading(true, '识别中...');
  const body = new FormData(); body.append('file', file);
  const r = await callApi('/extract-image', { method:'POST', body, timeout:120000 });
  setLoading(false); e.target.value = '';
  if (r.ok) {
    toast(r.data.new_tasks ? '已识别 ' + r.data.extracted + ' 个任务' : '未识别到任务');
    await loadAll();
  } else { toast(r.error); }
}

function setLoading(loading, msg) {
  state.loading = loading; const btn = document.getElementById('btnExtract');
  btn.disabled = loading;
  btn.innerHTML = loading
    ? '<span class="spinner"></span>处理中...'
    : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> AI 提取并安排';
  if (loading) toast(msg);
}

// ====== 渲染 ======

function render() {
  updateStats();
  document.getElementById('taskCount').textContent = state.tasks.filter(t => t.status!=='done').length;
  if (state.tab === 'today') return renderToday();
  const tasks = state.tab === 'done' ? state.tasks.filter(t => t.status==='done') : state.tasks;
  const list = document.getElementById('taskList');
  document.getElementById('scheduleArea').innerHTML = '';
  if (!tasks.length) {
    list.innerHTML = '<div class="empty-state">' + (state.tab==='done'?'暂无已完成任务':'暂无任务') + '</div>';
    return;
  }
  list.innerHTML = tasks.map(taskItemHTML).join('');
  bindEvents(list);
}

// ====== 今日视图 ======

function renderToday() {
  document.getElementById('taskList').innerHTML = '';
  const todayStr = new Date().toISOString().slice(0,10);
  const todayPlan = state.schedule.find(d => d.date === todayStr);
  const now = new Date();
  const overdue = state.tasks.filter(t => t.status==='todo' && t.deadline && new Date(t.deadline) < now);
  let html = '';
  if (overdue.length) {
    html += '<div class="day-plan overdue-section">';
    html += '<div class="day-plan-header"><span class="day-plan-date overdue-label">已逾期 (' + overdue.length + ')</span></div>';
    html += overdue.map(t => dayItemHTML(t, 'overdue')).join('');
    html += '</div>';
  }
  if (todayPlan && todayPlan.tasks.length) {
    const doneToday = todayPlan.tasks.filter(t => t.status==='done').length;
    html += '<div class="day-plan">';
    html += '<div class="day-plan-header">';
    html += '<span class="day-plan-date">今日 <span class="highlight">' + todayStr + '</span> · ' + todayPlan.day_name + '</span>';
    html += '<span class="day-plan-meta">' + doneToday + '/' + todayPlan.tasks.length + ' 完成 · ' + todayPlan.total_hours.toFixed(1) + 'h/' + todayPlan.capacity + 'h</span>';
    html += '</div>';
    html += todayPlan.tasks.map(t => dayItemHTML(t)).join('');
    html += '</div>';
  }
  const future = state.schedule.filter(d => d.date > todayStr);
  if (future.length) {
    html += future.map(day => {
      const done = day.tasks.filter(t => t.status==='done').length;
      return '<div class="day-plan" style="opacity:0.85">' +
        '<div class="day-plan-header">' +
        '<span class="day-plan-date">' + day.date + ' · ' + day.day_name + '</span>' +
        '<span class="day-plan-meta">' + done + '/' + day.tasks.length + ' · ' + day.total_hours.toFixed(1) + 'h</span>' +
        '</div>' +
        day.tasks.map(t => dayItemHTML(t)).join('') +
        '</div>';
    }).join('');
  }
  if (!html) html = '<div class="empty-state">暂无任务，粘贴文本点击「AI 提取并安排」</div>';
  document.getElementById('scheduleArea').innerHTML = html;
  document.getElementById('scheduleArea').querySelectorAll('.day-item-check').forEach(el => {
    el.addEventListener('click', e => {
      e.stopPropagation();
      const task = state.tasks.find(t => t.id === el.dataset.toggle);
      if (task) toggleDone(task);
    });
  });
  document.getElementById('scheduleArea').querySelectorAll('.day-item-body').forEach(el => {
    el.addEventListener('click', () => {
      const task = state.tasks.find(t => t.id === el.dataset.edit);
      if (task) openModal(task);
    });
  });
}

function dayItemHTML(t, urgencyType) {
  const ddl = t.deadline ? new Date(t.deadline).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '';
  const urgency = urgencyType || getUrgency(t);
  const dotClass = {'overdue':'urgency-overdue','today':'urgency-today','soon':'urgency-soon'}[urgency] || 'urgency-normal';
  return '<div class="day-item">' +
    '<div class="day-item-check" data-toggle="' + t.id + '">' + (t.status==='done'?'\u2713':'') + '</div>' +
    '<div class="day-item-body" data-edit="' + t.id + '">' +
    '<div class="day-item-title">' + esc(t.title) + '</div>' +
    '<div class="day-item-meta">' +
    '<span class="urgency-dot ' + dotClass + '"></span>' +
    '<span>' + t.estimated_hours + 'h</span>' +
    (ddl ? '<span>' + ddl + '</span>' : '') +
    '<span class="task-tag ' + (t.priority==='urgent'?'tag-urgent':t.priority==='high'?'tag-high':t.priority==='low'?'tag-low':'tag-medium') + '">' + priorityLabel(t.priority) + '</span>' +
    (t.source==='ai'?'<span class="task-tag tag-ai">AI</span>':'<span class="task-tag tag-source">手动</span>') +
    '</div>' +
    (t.ai_reason ? '<div class="ai-reason">' + esc(t.ai_reason) + '</div>' : '') +
    '</div>' +
    '</div>';
}

function getUrgency(t) {
  if (!t.deadline) return 'normal';
  const now = new Date(); const ddl = new Date(t.deadline);
  if (ddl < now) return 'overdue';
  const days = (ddl - now) / 86400000;
  if (days <= 1) return 'today';
  if (days <= 3) return 'soon';
  return 'normal';
}

function taskItemHTML(t) {
  const ddlText = t.deadline ? new Date(t.deadline).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '';
  const isOverdue = t.deadline && new Date(t.deadline) < new Date() && t.status!=='done';
  return '<div class="task-item ' + (t.status==='done'?'done':'') + '" data-id="' + t.id + '">' +
    '<div class="task-check ' + (t.status==='done'?'done':'') + '" data-toggle="' + t.id + '">' + (t.status==='done'?'\u2713':'') + '</div>' +
    '<div class="task-body" data-edit="' + t.id + '">' +
    '<div class="task-title">' + esc(t.title) + '</div>' +
    '<div class="task-meta">' +
    '<span class="task-tag ' + (t.priority==='urgent'?'tag-urgent':t.priority==='high'?'tag-high':t.priority==='low'?'tag-low':'tag-medium') + '">' + priorityLabel(t.priority) + '</span>' +
    (t.source==='ai'?'<span class="task-tag tag-ai">AI</span>':'<span class="task-tag tag-source">手动</span>') +
    (ddlText ? '<span class="task-ddl' + (isOverdue?' overdue':'') + '">' + (isOverdue?'逾期 ':'') + ddlText + '</span>' : '') +
    '</div>' +
    (t.ai_reason ? '<div class="ai-reason">' + esc(t.ai_reason) + '</div>' : '') +
    '</div>' +
    '</div>';
}

function bindEvents(list) {
  list.querySelectorAll('[data-toggle]').forEach(el => {
    el.addEventListener('click', e => {
      e.stopPropagation();
      const task = state.tasks.find(t => t.id === el.dataset.toggle);
      if (task) toggleDone(task);
    });
  });
  list.querySelectorAll('[data-edit]').forEach(el => {
    el.addEventListener('click', () => {
      const task = state.tasks.find(t => t.id === el.dataset.edit);
      if (task) openModal(task);
    });
  });
}

function updateStats() {
  const t = state.tasks; const now = new Date();
  document.getElementById('statUrgent').textContent = t.filter(x => x.status!=='done' && x.deadline && new Date(x.deadline) < now).length;
  document.getElementById('statToday').textContent = t.filter(x => x.status!=='done' && x.ai_schedule === now.toISOString().slice(0,10)).length;
  document.getElementById('statTodo').textContent = t.filter(x => x.status==='todo').length;
  document.getElementById('statDone').textContent = t.filter(x => x.status==='done').length;
}

// ====== Tab ======

function onTabSwitch(e) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  e.target.classList.add('active');
  state.tab = e.target.dataset.tab;
  if (state.tab === 'today') document.getElementById('inputArea').style.display = 'none';
  else document.getElementById('inputArea').style.display = '';
  render();
}

// ====== Modal ======

function openModal(task) {
  state.editingId = task ? task.id : null;
  document.getElementById('modalTitle').textContent = task ? '编辑任务' : '添加任务';
  document.getElementById('inputTitle').value = task ? task.title : '';
  document.getElementById('inputDesc').value = task ? task.description : '';
  document.getElementById('inputPriority').value = task ? task.priority : 'medium';
  document.getElementById('inputHours').value = task ? task.estimated_hours : 2;
  document.getElementById('inputDeadline').value = task && task.deadline ? new Date(task.deadline).toISOString().slice(0,16) : '';
  document.getElementById('modalDelete').style.display = task ? '' : 'none';
  document.getElementById('modalOverlay').classList.add('show');
}
function closeModal() { document.getElementById('modalOverlay').classList.remove('show'); state.editingId = null; }

async function onSaveTask() {
  const title = document.getElementById('inputTitle').value.trim();
  if (!title) return toast('请输入标题');
  const body = {
    title, description: document.getElementById('inputDesc').value,
    priority: document.getElementById('inputPriority').value,
    deadline: document.getElementById('inputDeadline').value || null,
    estimated_hours: parseFloat(document.getElementById('inputHours').value) || 2,
  };
  let r;
  if (state.editingId) {
    r = await callApi('/' + state.editingId, { method:'PUT', body: JSON.stringify(body) });
  } else {
    r = await callApi('', { method:'POST', body: JSON.stringify(body) });
  }
  if (r.ok) {
    toast(state.editingId ? '已更新' : '已添加');
    closeModal();
    await loadAll();
  } else { toast(r.error); }
}

async function onDeleteTask() {
  if (!state.editingId) return;
  const r = await callApi('/' + state.editingId, { method:'DELETE' });
  if (r.ok) { toast('已删除'); closeModal(); await loadAll(); }
  else toast(r.error);
}

async function toggleDone(task) {
  const status = task.status === 'done' ? 'todo' : 'done';
  const r = await callApi('/' + task.id, { method:'PUT', body: JSON.stringify({status}) });
  if (!r.ok) toast(r.error);
  await loadAll();
}

function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3500);
}
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function priorityLabel(p) { return {urgent:'紧急',high:'高',medium:'中',low:'低'}[p]||p; }

init();

