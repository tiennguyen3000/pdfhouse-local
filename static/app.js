const $ = (sel) => document.querySelector(sel);

const state = {
  groups: [],
  tools: [],
  tool: null,
  token: null,
  accept: null,
  files: [],       // [{id,name,pages,size,thumb}]
  imageId: null,
};

const els = {
  home: $('#homeSection'),
  work: $('#workSection'),
  toolGroups: $('#toolGroups'),
  workIcon: $('#workIcon'),
  workTitle: $('#workTitle'),
  workDesc: $('#workDesc'),
  dropzone: $('#dropzone'),
  fileInput: $('#fileInput'),
  browseBtn: $('#browseBtn'),
  dzTitle: $('#dzTitle'),
  dzHint: $('#dzHint'),
  fileList: $('#fileList'),
  imageSlot: $('#imageSlot'),
  imageInput: $('#imageInput'),
  imageBtn: $('#imageBtn'),
  imageName: $('#imageName'),
  optionsBox: $('#optionsBox'),
  runBtn: $('#runBtn'),
  status: $('#status'),
  result: $('#resultSection'),
  resultName: $('#resultName'),
  resultMeta: $('#resultMeta'),
  downloadLink: $('#downloadLink'),
  backBtn: $('#backBtn'),
  homeLink: $('#homeLink'),
};

const ACCEPT_LABEL = {
  pdf: { title: 'Thả file PDF vào đây', input: 'application/pdf,.pdf', hint: 'Tối đa 30 file · 100 MB/file · 400 MB tổng' },
  image: { title: 'Thả ảnh JPG/PNG vào đây', input: 'image/*', hint: 'Mỗi ảnh thành một trang PDF' },
  office: { title: 'Thả file Word / Excel / PowerPoint', input: '.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.rtf,.txt,.csv', hint: 'Chuyển bằng LibreOffice trên máy' },
};

/* ------------------------------------------------------------------ tools */
async function loadTools() {
  const res = await fetch('/api/tools');
  const data = await res.json();
  state.groups = data.groups;
  state.tools = data.tools;
  renderTools();
}

function renderTools() {
  els.toolGroups.innerHTML = '';
  for (const group of state.groups) {
    const tools = state.tools.filter((t) => t.group === group.id);
    if (!tools.length) continue;

    const wrap = document.createElement('div');
    wrap.className = 'group';
    wrap.innerHTML = `<div class="group-head"><h2>${group.name}</h2><span>${group.desc}</span></div>`;
    const grid = document.createElement('div');
    grid.className = 'grid';

    for (const tool of tools) {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'tool-card';
      card.innerHTML = `
        <span class="ti">${tool.icon || '▤'}</span>
        <span>
          <strong>${escapeHtml(tool.name)}</strong>
          <p>${escapeHtml(tool.desc)}</p>
        </span>`;
      card.addEventListener('click', () => openTool(tool));
      grid.appendChild(card);
    }

    wrap.appendChild(grid);
    els.toolGroups.appendChild(wrap);
  }
}

function openTool(tool) {
  state.tool = tool;
  if (state.accept !== tool.accept) resetSession(tool.accept);
  state.imageId = null;
  els.imageName.textContent = 'chưa có ảnh';

  els.home.classList.add('hidden');
  els.work.classList.remove('hidden');
  els.workIcon.textContent = tool.icon || '▤';
  els.workTitle.textContent = tool.name;
  els.workDesc.textContent = tool.desc;

  const accept = ACCEPT_LABEL[tool.accept] || ACCEPT_LABEL.pdf;
  els.dzTitle.textContent = accept.title;
  els.dzHint.textContent = accept.hint;
  els.fileInput.accept = accept.input;
  els.fileInput.multiple = Boolean(tool.multi);

  els.imageSlot.hidden = !tool.needs_image;
  els.dropzone.classList.toggle('hidden', Boolean(tool.needs_image && tool.accept === 'pdf' && false));

  renderFields();
  renderFiles();
  els.result.classList.add('hidden');
  setStatus('');
  const isEditor = Boolean(tool.editor);
  els.optionsBox.classList.toggle('hidden', isEditor);
  document.querySelector('.actions').classList.toggle('hidden', isEditor);
  editorEls.panel.classList.toggle('hidden', !isEditor || !state.files.length);
  if (isEditor && state.files.length) startEditor();
  window.scrollTo({ top: 0 });
}

function resetSession(accept) {
  state.token = null;
  state.files = [];
  state.accept = accept;
  state.imageId = null;
  els.result.classList.add('hidden');
}

/* ---------------------------------------------------------------- uploads */
async function uploadFiles(fileList) {
  const files = [...fileList];
  if (!files.length) return;

  const form = new FormData();
  files.forEach((f) => form.append('files', f));
  form.append('accept', state.tool.accept);
  form.append('slot', 'source');
  if (state.token) form.append('token', state.token);

  setStatus(`Đang tải ${files.length} file…`);
  els.runBtn.disabled = true;

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Tải file thất bại');
    state.token = data.token;
    state.files.push(...data.files.map((f) => ({ ...f })));
    if (!state.tool.multi && state.files.length > 1) state.files = state.files.slice(-1);
    renderFiles();
    if (state.tool.editor) startEditor();
    setStatus('');
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    els.runBtn.disabled = false;
  }
}

async function uploadImage(file) {
  if (!state.token) return setStatus('Hãy tải file PDF trước.', true);

  const form = new FormData();
  form.append('files', file);
  form.append('accept', 'image');
  form.append('slot', 'image');
  form.append('token', state.token);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Tải ảnh thất bại');
    state.imageId = data.files[0].id;
    els.imageName.textContent = data.files[0].name;
    setStatus('');
  } catch (err) {
    setStatus(err.message, true);
  }
}

/* ----------------------------------------------------------------- render */
function renderFiles() {
  els.fileList.innerHTML = '';
  const multi = Boolean(state.tool?.multi);
  if (state.tool?.editor) els.dropzone.classList.toggle('hidden', state.files.length > 0);

  state.files.forEach((file, idx) => {
    const card = document.createElement('div');
    card.className = 'file-card' + (multi ? '' : ' no-drag');
    card.draggable = multi;

    const thumb = file.thumb
      ? `<img class="thumb" src="${file.thumb}" alt="" />`
      : `<div class="thumb placeholder">▤</div>`;

    card.innerHTML = `
      ${multi ? '<div class="grip" title="Kéo để đổi thứ tự">⠿</div>' : ''}
      ${thumb}
      <div>
        <div class="fname">${escapeHtml(file.name)}</div>
        <div class="fmeta">${file.pages ? file.pages + ' trang · ' : ''}${file.size}</div>
      </div>
      <div class="fcontrols">
        ${multi ? `<button class="icon-btn up" title="Lên" ${idx === 0 ? 'disabled' : ''}>↑</button>
        <button class="icon-btn down" title="Xuống" ${idx === state.files.length - 1 ? 'disabled' : ''}>↓</button>` : ''}
        <button class="icon-btn del" title="Bỏ file">✕</button>
      </div>`;

    if (multi) {
      card.querySelector('.up').addEventListener('click', () => move(idx, idx - 1));
      card.querySelector('.down').addEventListener('click', () => move(idx, idx + 1));
      card.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', String(idx));
        e.dataTransfer.effectAllowed = 'move';
        card.classList.add('dragging');
      });
      card.addEventListener('dragend', () => card.classList.remove('dragging'));
      card.addEventListener('dragover', (e) => { e.preventDefault(); card.classList.add('drop-target'); });
      card.addEventListener('dragleave', () => card.classList.remove('drop-target'));
      card.addEventListener('drop', (e) => {
        e.preventDefault();
        card.classList.remove('drop-target');
        const from = Number(e.dataTransfer.getData('text/plain'));
        if (!Number.isNaN(from) && from !== idx) move(from, idx);
      });
    }

    card.querySelector('.del').addEventListener('click', () => {
      state.files.splice(idx, 1);
      renderFiles();
    });

    els.fileList.appendChild(card);
  });
}

function move(from, to) {
  if (to < 0 || to >= state.files.length) return;
  const [item] = state.files.splice(from, 1);
  state.files.splice(to, 0, item);
  renderFiles();
}

function renderFields() {
  els.optionsBox.innerHTML = '';
  const fields = state.tool?.fields || [];

  for (const field of fields) {
    const wrap = document.createElement('div');
    wrap.className = field.type === 'checkbox' ? 'field check' : 'field';

    if (field.type === 'checkbox') {
      wrap.innerHTML = `<input type="checkbox" id="f-${field.key}" ${field.default ? 'checked' : ''} />
        <label for="f-${field.key}">${escapeHtml(field.label)}</label>`;
    } else if (field.type === 'select') {
      const opts = (field.options || [])
        .map((o) => `<option value="${escapeHtml(o.value)}" ${String(o.value) === String(field.default) ? 'selected' : ''}>${escapeHtml(o.label)}</option>`)
        .join('');
      wrap.innerHTML = `<label for="f-${field.key}">${escapeHtml(field.label)}</label>
        <select id="f-${field.key}">${opts}</select>`;
    } else {
      const step = field.step ? `step="${field.step}"` : '';
      const min = field.min !== undefined ? `min="${field.min}"` : '';
      const max = field.max !== undefined ? `max="${field.max}"` : '';
      const ph = field.placeholder ? `placeholder="${escapeHtml(field.placeholder)}"` : '';
      const val = field.default !== undefined && field.default !== null ? `value="${escapeHtml(String(field.default))}"` : '';
      wrap.innerHTML = `<label for="f-${field.key}">${escapeHtml(field.label)}</label>
        <input type="${field.type === 'number' ? 'number' : 'text'}" id="f-${field.key}" ${val} ${ph} ${step} ${min} ${max} />
        ${field.help ? `<span class="help">${escapeHtml(field.help)}</span>` : ''}`;
    }

    els.optionsBox.appendChild(wrap);
  }
}

function collectOptions() {
  const options = {};
  for (const field of state.tool?.fields || []) {
    const el = document.getElementById(`f-${field.key}`);
    if (!el) continue;
    if (field.type === 'checkbox') options[field.key] = el.checked;
    else if (field.type === 'number') options[field.key] = el.value === '' ? field.default : Number(el.value);
    else options[field.key] = el.value;
  }
  return options;
}

/* -------------------------------------------------------------------- run */
async function run() {
  if (!state.token || !state.files.length) return setStatus('Hãy tải file lên trước.', true);
  if (state.tool.needs_image && !state.imageId) return setStatus('Hãy chọn ảnh (chữ ký/logo) trước.', true);

  els.runBtn.disabled = true;
  els.result.classList.add('hidden');
  setStatus('Đang xử lý…');

  try {
    const res = await fetch(`/api/run/${state.tool.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        token: state.token,
        fileIds: state.files.map((f) => f.id),
        options: collectOptions(),
        imageId: state.imageId,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Xử lý thất bại');

    els.downloadLink.href = data.url;
    els.downloadLink.download = data.filename;
    els.resultName.textContent = data.filename;
    const parts = [data.size];
    if (data.count > 1) parts.push(`${data.count} file trong zip`);
    if (data.elapsed) parts.push(`${data.elapsed}s`);
    if (data.meta) parts.push(data.meta);
    els.resultMeta.textContent = parts.join(' · ');

    els.result.classList.remove('hidden');
    els.downloadLink.click();
    setStatus('Xong.');
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    els.runBtn.disabled = false;
  }
}

/* ------------------------------------------------------------------ utils */
function setStatus(msg, isError = false) {
  els.status.textContent = msg;
  els.status.classList.toggle('error', Boolean(isError));
}

function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* ----------------------------------------------------------------- events */
els.dropzone.addEventListener('click', () => els.fileInput.click());
els.dropzone.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') els.fileInput.click();
});
els.browseBtn.addEventListener('click', (e) => { e.stopPropagation(); els.fileInput.click(); });
els.fileInput.addEventListener('change', (e) => { uploadFiles(e.target.files); e.target.value = ''; });

['dragenter', 'dragover'].forEach((evt) =>
  els.dropzone.addEventListener(evt, (e) => { e.preventDefault(); els.dropzone.classList.add('dragover'); })
);
['dragleave', 'drop'].forEach((evt) =>
  els.dropzone.addEventListener(evt, (e) => { e.preventDefault(); els.dropzone.classList.remove('dragover'); })
);
els.dropzone.addEventListener('drop', (e) => {
  if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
});

els.imageBtn.addEventListener('click', () => els.imageInput.click());
els.imageInput.addEventListener('change', (e) => {
  if (e.target.files[0]) uploadImage(e.target.files[0]);
  e.target.value = '';
});

els.runBtn.addEventListener('click', run);
els.backBtn.addEventListener('click', () => {
  state.tool = null;
  els.work.classList.add('hidden');
  els.home.classList.remove('hidden');
  els.result.classList.add('hidden');
});
els.homeLink.addEventListener('click', (e) => {
  e.preventDefault();
  els.backBtn.click();
});

/* ================================================================ editor = */
const editorEls = {
  panel: $('#editorPanel'),
  modes: $('#edModes'),
  textOpts: $('#edTextOpts'),
  text: $('#edText'),
  size: $('#edSize'),
  color: $('#edColor'),
  align: $('#edAlign'),
  undo: $('#edUndo'),
  clear: $('#edClear'),
  imageRow: $('#edImageRow'),
  imageInput: $('#edImageInput'),
  imageBtn: $('#edImageBtn'),
  imageName: $('#edImageName'),
  canvas: $('#edCanvas'),
  img: $('#edPageImg'),
  overlay: $('#edOverlay'),
  rubber: $('#edRubber'),
  prev: $('#edPrev'),
  next: $('#edNext'),
  pageInfo: $('#edPageInfo'),
  hint: $('#edHint'),
  apply: $('#edApply'),
  status: $('#edStatus'),
};

const ed = { mode: 'text', page: 1, pages: 1, ops: [], imageId: null, drag: null, fileId: null };
let editorBound = false;

const ED_HINTS = {
  text: 'Kéo một vùng trên trang để đặt chữ',
  image: 'Chọn ảnh, rồi kéo vùng để chèn',
  highlight: 'Kéo vùng cần highlight',
  rect: 'Kéo để vẽ khung',
  arrow: 'Kéo từ điểm bắt đầu đến điểm kết thúc',
  redact: 'Kéo vùng cần xoá nội dung (xoá vĩnh viễn chữ/ảnh dưới vùng đó)',
};

function edStatus(msg, isError = false) {
  editorEls.status.textContent = msg;
  editorEls.status.classList.toggle('error', Boolean(isError));
}

function bindEditor() {
  if (editorBound) return;
  editorBound = true;

  editorEls.modes.addEventListener('click', (e) => {
    const btn = e.target.closest('.mode');
    if (btn) setEditorMode(btn.dataset.mode);
  });

  editorEls.prev.addEventListener('click', () => edGo(-1));
  editorEls.next.addEventListener('click', () => edGo(1));

  editorEls.undo.addEventListener('click', () => {
    if (!ed.ops.length) return;
    ed.ops.pop();
    renderOps();
    edStatus('');
  });
  editorEls.clear.addEventListener('click', () => {
    ed.ops = [];
    renderOps();
    edStatus('');
  });

  editorEls.imageBtn.addEventListener('click', () => editorEls.imageInput.click());
  editorEls.imageInput.addEventListener('change', (e) => {
    if (e.target.files[0]) editorImage(e.target.files[0]);
    e.target.value = '';
  });

  editorEls.overlay.addEventListener('mousedown', edDown);
  window.addEventListener('mousemove', edMove);
  window.addEventListener('mouseup', edUp);
  editorEls.apply.addEventListener('click', applyEdits);
}

function startEditor() {
  bindEditor();
  const file = state.files[0];
  if (!file) return;

  if (ed.fileId !== file.id) {
    ed.fileId = file.id;
    ed.ops = [];
    ed.page = 1;
    ed.imageId = null;
    editorEls.imageName.textContent = 'chưa có ảnh';
  }
  ed.pages = file.pages || 1;
  editorEls.panel.classList.remove('hidden');
  setEditorMode(ed.mode);
  loadEditorPage();
}

function setEditorMode(mode) {
  ed.mode = mode;
  [...editorEls.modes.querySelectorAll('.mode')].forEach((b) =>
    b.classList.toggle('active', b.dataset.mode === mode)
  );
  editorEls.textOpts.classList.toggle('hidden', mode !== 'text' && mode !== 'rect' && mode !== 'arrow');
  editorEls.imageRow.classList.toggle('hidden', mode !== 'image');
  editorEls.hint.textContent = ED_HINTS[mode] || '';
}

function loadEditorPage() {
  const file = state.files[0];
  if (!file) return;
  editorEls.img.src = `/api/page-image/${state.token}/${file.id}/${ed.page}?dpi=130&t=${Date.now()}`;
  editorEls.pageInfo.textContent = `Trang ${ed.page}/${ed.pages}`;
  editorEls.prev.disabled = ed.page <= 1;
  editorEls.next.disabled = ed.page >= ed.pages;
  editorEls.img.onload = renderOps;
  editorEls.img.onerror = () => edStatus('Không tải được trang. Phiên có thể đã hết hạn.', true);
}

function edGo(delta) {
  const next = ed.page + delta;
  if (next < 1 || next > ed.pages) return;
  ed.page = next;
  loadEditorPage();
}

function edDown(e) {
  if (!state.token || e.target.closest('.ed-op')) return;
  const box = editorEls.canvas.getBoundingClientRect();
  ed.drag = { box, x0: e.clientX - box.left, y0: e.clientY - box.top };
  rubberBand(ed.drag.x0, ed.drag.y0, ed.drag.x0, ed.drag.y0);
  e.preventDefault();
}

function edMove(e) {
  if (!ed.drag) return;
  const { box } = ed.drag;
  const x = clampNum(e.clientX - box.left, 0, box.width);
  const y = clampNum(e.clientY - box.top, 0, box.height);
  rubberBand(ed.drag.x0, ed.drag.y0, x, y);
}

function edUp(e) {
  if (!ed.drag) return;
  const { box, x0, y0 } = ed.drag;
  const x = clampNum(e.clientX - box.left, 0, box.width);
  const y = clampNum(e.clientY - box.top, 0, box.height);
  ed.drag = null;
  editorEls.rubber.classList.add('hidden');

  const left = Math.min(x0, x);
  const top = Math.min(y0, y);
  const w = Math.abs(x - x0);
  const h = Math.abs(y - y0);
  if (w < 14 || h < 12) return;

  createOp({
    x: round1((left / box.width) * 100),
    y: round1((top / box.height) * 100),
    w: round1((w / box.width) * 100),
    h: round1((h / box.height) * 100),
  });
}

function createOp(rect) {
  const mode = ed.mode;
  const op = { type: mode, page: ed.page, rect };

  if (mode === 'text') {
    const text = editorEls.text.value.trim();
    if (!text) return edStatus('Nhập nội dung chữ trước khi kéo vùng.', true);
    op.text = text;
    op.size = Number(editorEls.size.value) || 14;
    op.color = editorEls.color.value;
    op.align = editorEls.align.value;
  } else if (mode === 'image') {
    if (!ed.imageId) return edStatus('Chọn ảnh trước khi kéo vùng.', true);
    op.imageId = ed.imageId;
  } else if (mode === 'highlight') {
    op.color = '#ffe066';
    op.opacity = 0.45;
  } else if (mode === 'redact') {
    op.fill = '#ffffff';
  } else {
    op.color = editorEls.color.value;
    op.width = 2;
  }

  ed.ops.push(op);
  renderOps();
  edStatus(`${ed.ops.length} thao tác`);
}

function renderOps() {
  editorEls.overlay.innerHTML = '';
  for (const [idx, op] of ed.ops.entries()) {
    if (op.page !== ed.page) continue;
    const div = document.createElement('div');
    div.className = `ed-op ${op.type}`;
    div.style.left = `${op.rect.x}%`;
    div.style.top = `${op.rect.y}%`;
    div.style.width = `${op.rect.w}%`;
    div.style.height = `${op.rect.h}%`;
    div.title = 'Bấm đúp để xoá thao tác này';

    if (op.type === 'text') {
      div.style.color = op.color || '#111';
      const nat = editorEls.img.naturalWidth || 0;
      const canvasW = editorEls.canvas.clientWidth || 1;
      const pxPerPt = nat ? canvasW / ((nat * 72) / 130) : 1;
      const sizePx = Math.max(9, Math.min(48, (op.size || 12) * pxPerPt));
      div.innerHTML = `<span style="font-size:${sizePx.toFixed(1)}px">${escapeHtml(op.text)}</span>`;
    }
    if (op.type === 'rect' || op.type === 'arrow') div.style.color = op.color || '#e11d48';

    div.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      ed.ops.splice(idx, 1);
      renderOps();
      edStatus(`${ed.ops.length} thao tác`);
    });

    editorEls.overlay.appendChild(div);
  }
}

function rubberBand(x0, y0, x1, y1) {
  const left = Math.min(x0, x1);
  const top = Math.min(y0, y1);
  const style = editorEls.rubber.style;
  style.left = `${left}px`;
  style.top = `${top}px`;
  style.width = `${Math.abs(x1 - x0)}px`;
  style.height = `${Math.abs(y1 - y0)}px`;
  editorEls.rubber.classList.remove('hidden');
}

async function editorImage(file) {
  if (!state.token) return edStatus('Tải PDF trước đã.', true);
  const form = new FormData();
  form.append('files', file);
  form.append('accept', 'image');
  form.append('slot', 'image');
  form.append('token', state.token);
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Tải ảnh thất bại');
    ed.imageId = data.files[0].id;
    editorEls.imageName.textContent = data.files[0].name;
    edStatus('Đã có ảnh, kéo vùng trên trang để chèn.');
  } catch (err) {
    edStatus(err.message, true);
  }
}

async function applyEdits() {
  if (!ed.ops.length) return edStatus('Chưa có thao tác nào để áp dụng.', true);
  editorEls.apply.disabled = true;
  edStatus('Đang áp dụng…');
  try {
    const res = await fetch('/api/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: state.token, fileId: state.files[0].id, ops: ed.ops }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Áp dụng thất bại');

    els.downloadLink.href = data.url;
    els.downloadLink.download = data.filename;
    els.resultName.textContent = data.filename;
    els.resultMeta.textContent = [data.size, data.meta, data.elapsed ? `${data.elapsed}s` : ''].filter(Boolean).join(' · ');
    els.result.classList.remove('hidden');
    els.downloadLink.click();
    edStatus('Xong.');
  } catch (err) {
    edStatus(err.message, true);
  } finally {
    editorEls.apply.disabled = false;
  }
}

function round1(n) {
  return Math.round(n * 10) / 10;
}

function clampNum(v, low, high) {
  return Math.max(low, Math.min(high, v));
}

loadTools();
