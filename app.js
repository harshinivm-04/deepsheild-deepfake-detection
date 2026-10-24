const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const COL = { real: '#34d3a5', fake: '#ff6b5e', amber: '#f5b83d', line: '#263c58', muted: '#8aa0b8' };

let history = [], charts = {}, chosen = null, filt = 'all', openScan = null;

const fmtDate = d => new Date(d.replace(' ', 'T') + 'Z').toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
const esc = s => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function toast(msg, ok = false) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'toast show' + (ok ? ' ok' : '');
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('show'), 3500);
}

async function api(url, opts) {
  const r = await fetch(url, opts);
  if (r.status === 401) { location.href = '/login'; throw new Error('Signed out'); }
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || 'Something went wrong');
  return data;
}

/* ---------- navigation ---------- */
function show(view) {
  $$('.view').forEach(v => v.classList.toggle('hide', v.id !== 'view-' + view));
  $$('.nav').forEach(n => n.classList.toggle('on', n.dataset.view === view));
  location.hash = view;
  if (view === 'overview') drawCharts();
  if (view === 'history') renderHistory();
}
$$('.nav').forEach(n => n.onclick = () => show(n.dataset.view));
$$('[data-go]').forEach(b => b.onclick = () => show(b.dataset.go));

/* ---------- overview ---------- */
function countUp(el, to, suffix = '') {
  const start = performance.now(), from = 0;
  const step = t => {
    const k = Math.min((t - start) / 700, 1);
    el.textContent = (Number.isInteger(to) ? Math.round(from + (to - from) * k) : (from + (to - from) * k).toFixed(1)) + suffix;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function drawCharts() {
  const total = history.length, real = history.filter(h => h.verdict === 'Real').length, fake = total - real;
  const avg = total ? history.reduce((a, h) => a + h.confidence, 0) / total : 0;
  countUp($('#s-total'), total); countUp($('#s-real'), real); countUp($('#s-fake'), fake);
  countUp($('#s-conf'), +avg.toFixed(1), '%');
  $('#hist-count').textContent = total;

  // last 14 days
  const days = [...Array(14)].map((_, i) => { const d = new Date(); d.setDate(d.getDate() - 13 + i); return d; });
  const key = d => d.toLocaleDateString('en-CA');
  const rc = {}, fc = {};
  history.forEach(h => {
    const k = key(new Date(h.created.replace(' ', 'T') + 'Z'));
    (h.verdict === 'Real' ? rc : fc)[k] = ((h.verdict === 'Real' ? rc : fc)[k] || 0) + 1;
  });

  Chart.defaults.color = COL.muted; Chart.defaults.font.family = 'Manrope';
  charts.donut?.destroy(); charts.line?.destroy();
  charts.donut = new Chart($('#c-donut'), {
    type: 'doughnut',
    data: { labels: ['Real', 'Fake'], datasets: [{ data: total ? [real, fake] : [1, 0], backgroundColor: total ? [COL.real, COL.fake] : [COL.line], borderWidth: 0 }] },
    options: { maintainAspectRatio: false, cutout: '68%', plugins: { legend: { position: 'bottom' }, tooltip: { enabled: !!total } },
      onClick: (_, els) => { if (els.length) { filt = ['Real', 'Fake'][els[0].index]; setChip(); show('history'); } } }
  });
  charts.line = new Chart($('#c-line'), {
    type: 'line',
    data: {
      labels: days.map(d => d.toLocaleDateString([], { day: 'numeric', month: 'short' })),
      datasets: [
        { label: 'Real', data: days.map(d => rc[key(d)] || 0), borderColor: COL.real, backgroundColor: COL.real + '33', fill: true, tension: .35 },
        { label: 'Fake', data: days.map(d => fc[key(d)] || 0), borderColor: COL.fake, backgroundColor: COL.fake + '33', fill: true, tension: .35 }]
    },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: COL.line } }, x: { grid: { display: false } } } }
  });

  const rec = $('#recent');
  rec.innerHTML = history.slice(0, 5).map(h => `
    <div class="recent-item" data-id="${h.id}">
      <img src="${h.thumb_url}" alt="">
      <div class="grow"><b>${esc(h.filename)}</b><span class="muted">${fmtDate(h.created)}</span></div>
      <span class="muted">${h.confidence}%</span><span class="badge ${h.verdict}">${h.verdict}</span>
    </div>`).join('') || '<p class="muted">No scans yet. Start with <b>New scan</b>.</p>';
  $$('.recent-item', rec).forEach(el => el.onclick = () => openModal(+el.dataset.id));
}

/* ---------- upload ---------- */
const drop = $('#drop'), fileIn = $('#file');
drop.onclick = () => !chosen && fileIn.click();
drop.onkeydown = e => { if (e.key === 'Enter' && !chosen) fileIn.click(); };
['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));
drop.addEventListener('drop', e => setFile(e.dataTransfer.files[0]));
fileIn.onchange = () => setFile(fileIn.files[0]);

function setFile(f) {
  if (!f) return;
  if (!/^(image|video)\//.test(f.type)) return toast('Choose a photo or a video file.');
  if (f.size > 100 * 1024 * 1024) return toast('File is larger than 100 MB.');
  chosen = f;
  const url = URL.createObjectURL(f);
  $('#preview').innerHTML = f.type.startsWith('video') ? `<video src="${url}" controls muted></video>` : `<img src="${url}" alt="Preview">`;
  $('#preview').classList.remove('hide'); $('#drop-empty').classList.add('hide');
  $('#file-name').textContent = `${f.name} (${(f.size / 1048576).toFixed(1)} MB)`;
  $('#run').disabled = false; $('#clear').classList.remove('hide');
  resetResult();
}

function clearFile() {
  chosen = null; fileIn.value = '';
  $('#preview').innerHTML = ''; $('#preview').classList.add('hide'); $('#drop-empty').classList.remove('hide');
  $('#file-name').textContent = 'No file selected'; $('#run').disabled = true; $('#clear').classList.add('hide');
  $('#status').textContent = '';
}
$('#clear').onclick = () => { clearFile(); resetResult(); };

function resetResult() {
  $('#result').className = 'empty';
  $('#result').innerHTML = '<b>Your result will appear here</b><span class="muted">You\'ll get a verdict, a confidence score and, for photos, an error-level map showing edited regions.</span>';
}

$('#run').onclick = async () => {
  if (!chosen) return;
  const btn = $('#run'), fd = new FormData();
  fd.append('file', chosen);
  btn.disabled = true; btn.textContent = 'Analysing...';
  drop.classList.add('scanning'); $('#beam').classList.remove('hide');
  $('#status').textContent = chosen.type.startsWith('video')
    ? 'Sampling frames and checking each face. Videos take up to a minute on CPU.'
    : 'Finding the face and running the model.';
  try {
    const scan = await api('/api/analyze', { method: 'POST', body: fd });
    history.unshift(scan);
    $('#hist-count').textContent = history.length;
    $('#result').className = '';
    renderResult(scan, $('#result'), $('#preview video')?.src);
    toast(`Scan saved: ${scan.verdict} (${scan.confidence}%)`, true);
    $('#status').textContent = '';
  } catch (e) {
    toast(e.message); $('#status').textContent = e.message;
  } finally {
    btn.disabled = false; btn.textContent = 'Run analysis';
    drop.classList.remove('scanning'); $('#beam').classList.add('hide');
  }
};

/* ---------- result renderer (used by New scan + history modal) ---------- */
function renderResult(s, el, localVideo) {
  const isFake = s.verdict === 'Fake';
  const low = s.confidence < 70;
  const what = s.kind === 'video' ? 'video' : 'photo';
  el.innerHTML = `
    <div class="verdict ${s.verdict}">
      <div class="ring"><span>${s.confidence}%</span></div>
      <div>
        <h3>${isFake ? 'Likely deepfake' : 'Likely authentic'}</h3>
        <span class="muted">${esc(s.filename)}</span>
      </div>
    </div>
    <div class="meter-labels"><span>Real</span><span>Fake probability ${(s.fake_prob * 100).toFixed(1)}%</span><span>Fake</span></div>
    <div class="meter"><i style="left:0" data-to="${(s.fake_prob * 100).toFixed(1)}"></i></div>
    <p class="note ${low ? 'warn' : ''}">${low ? 'Low confidence. Treat this as inconclusive and check the source of the ' + what + '.' : 'The model is fairly sure about this ' + what + ', but no detector is perfect. Use it as evidence, not proof.'}</p>
    ${s.kind === 'image' ? `
      <div class="seg"><button class="on" data-m="orig">Original</button><button data-m="heat">Heatmap</button><button data-m="ela">Error-level map</button></div>
      <div class="media-view"><img src="${s.media_url}" alt="Scanned photo" id="mv-img"></div>
      <p class="note" id="mv-note"></p>`
    : `
      <div class="media-view"><video src="${localVideo || s.media_url}" controls muted id="mv-vid"></video></div>
      <div class="tl-box"><canvas id="tl"></canvas></div>
      <p class="note">Each point is one sampled frame. Click a point to jump to that moment in the video.</p>
      ${s.heat_url ? `<h3 style="margin-top:16px">Heatmap: most suspicious frame</h3><div class="media-view"><img src="${s.heat_url}" alt="Heatmap"></div><p class="note">Red and yellow areas are what pushed the model toward "fake".</p>` : ''}`}
    <div class="facts">
      <span>${s.kind === 'video' ? s.frames.length + ' frames checked' : 'Single image'}</span>
      <span>${s.face_found ? 'Face detected and cropped' : 'No face found: whole image scored (less reliable)'}</span>
    </div>`;

  requestAnimationFrame(() => requestAnimationFrame(() => {
    $('.ring', el).style.setProperty('--p', s.confidence);
    const m = $('.meter i', el); m.style.left = `calc(${m.dataset.to}% - 2px)`;
  }));

  if (s.kind === 'image') {
    const notes = {
      orig: 'The photo you uploaded.',
      heat: 'Heatmap: red and yellow areas are the regions that pushed the model toward "fake". A mostly blue map means no region stood out.',
      ela: 'Compression-error map: regions that glow brighter than their surroundings were saved differently and may have been edited or generated.' };
    const urls = { orig: s.media_url, heat: s.heat_url, ela: s.ela_url };
    const setMode = m => {
      $$('.seg button', el).forEach(x => x.classList.toggle('on', x.dataset.m === m));
      $('#mv-img', el).src = urls[m]; $('#mv-note', el).textContent = notes[m];
    };
    $$('.seg button', el).forEach(b => b.onclick = () => setMode(b.dataset.m));
    setMode(isFake && s.heat_url ? 'heat' : 'orig');
  } else {
    const c = $('#tl', el), vid = $('#mv-vid', el);
    charts['tl' + el.id]?.destroy();
    charts['tl' + el.id] = new Chart(c, {
      type: 'line',
      data: {
        labels: s.frames.map((_, i) => i + 1),
        datasets: [
          { label: 'Fake probability', data: s.frames.map(p => +(p * 100).toFixed(1)), borderColor: COL.amber, backgroundColor: COL.amber, tension: .3, pointRadius: 5, pointHoverRadius: 8,
            pointBackgroundColor: s.frames.map(p => p >= .5 ? COL.fake : COL.real) },
          { label: '50% line', data: s.frames.map(() => 50), borderColor: COL.muted, borderDash: [5, 5], pointRadius: 0 }]
      },
      options: { maintainAspectRatio: false, scales: { y: { min: 0, max: 100, grid: { color: COL.line }, title: { display: true, text: '% fake' } }, x: { title: { display: true, text: 'Frame' }, grid: { display: false } } },
        plugins: { legend: { display: false } },
        onClick: (_, els) => {
          if (!els.length || !vid.duration) return;
          vid.currentTime = els[0].index / Math.max(s.frames.length - 1, 1) * vid.duration; vid.play();
        } }
    });
  }
}

/* ---------- history ---------- */
function setChip() { $$('.chip').forEach(c => c.classList.toggle('on', c.dataset.f === filt)); }
$$('.chip').forEach(c => c.onclick = () => { filt = c.dataset.f; setChip(); renderHistory(); });
$('#search').oninput = renderHistory;

function renderHistory() {
  const q = $('#search').value.trim().toLowerCase();
  const rows = history.filter(h => (filt === 'all' || h.verdict === filt || h.kind === filt) && h.filename.toLowerCase().includes(q));
  $('#hist-grid').innerHTML = rows.map(h => `
    <div class="h-card" data-id="${h.id}" tabindex="0">
      <div class="th"><img src="${h.thumb_url}" alt=""><span class="kind">${h.kind === 'video' ? 'Video' : 'Photo'}</span></div>
      <div class="bd"><b>${esc(h.filename)}</b>
        <div class="row-between"><span class="badge ${h.verdict}">${h.verdict}</span><span class="muted">${h.confidence}%</span></div>
        <span class="muted" style="font-size:12px">${fmtDate(h.created)}</span></div>
    </div>`).join('') || `<div class="empty-hist">${history.length ? 'No scans match this filter.' : 'Nothing here yet. Run your first scan.'}</div>`;
  $$('.h-card').forEach(el => {
    el.onclick = () => openModal(+el.dataset.id);
    el.onkeydown = e => e.key === 'Enter' && openModal(+el.dataset.id);
  });
}

/* ---------- modal ---------- */
function openModal(id) {
  openScan = history.find(h => h.id === id);
  if (!openScan) return;
  renderResult(openScan, $('#modal-body'));
  $('#modal-date').textContent = 'Scanned ' + fmtDate(openScan.created);
  $('#modal').showModal();
}
$('#modal-x').onclick = () => $('#modal').close();
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') e.target.close(); });
$('#modal').addEventListener('close', () => $('#modal-body video')?.pause());
$('#modal-del').onclick = async () => {
  if (!openScan || !confirm('Delete this scan and its files?')) return;
  try {
    await api('/api/history/' + openScan.id, { method: 'DELETE' });
    history = history.filter(h => h.id !== openScan.id);
    $('#modal').close(); renderHistory(); drawCharts(); toast('Scan deleted', true);
  } catch (e) { toast(e.message); }
};

/* ---------- boot ---------- */
(async () => {
  try { history = await api('/api/history'); } catch (e) { toast(e.message); }
  const v = location.hash.slice(1);
  show(['overview', 'analyze', 'history'].includes(v) ? v : 'overview');
})();