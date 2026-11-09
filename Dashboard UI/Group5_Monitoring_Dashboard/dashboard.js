/*
 * Yield Curve Monitoring Dashboard — renders a monitor_snapshot.json.
 *
 * CURRENT (local prototype). The snapshot is loaded from, in order:
 *   1. ./monitor_snapshot.json via fetch (works when this folder is served over http,
 *      e.g. `python -m http.server`; browsers block fetch for pages opened via file://)
 *   2. the embedded PLACEHOLDER_SNAPSHOT below (fallback when opened straight from disk)
 *   3. any file picked with the "Load JSON" button (replaces whatever is shown)
 *
 * FUTURE IMPLEMENTATION (Cloudflare). monitor_snapshot.json will be produced from our
 * Decision log + TVFI's Profitability workbook and served by a Cloudflare Worker.
 * Only CONFIG.snapshotUrl needs to change; the schema and rendering stay the same.
 *
 * The dashboard derives display metrics (mean shift, largest move, 2s10s twist) from the
 * curves using the same delta as the pipeline trigger: implied − pricing (bp).
 * Canada-par current − pricing is kept as labeled market context only.
 * Trigger statuses are taken as-is from the snapshot — rule evaluation lives upstream
 * in the Trigger / Decision log step, not here.
 */
'use strict';

const CONFIG = {
  // FUTURE (Cloudflare): replace with the Worker endpoint, e.g.
  //   'https://<worker-name>.<account>.workers.dev/monitor_snapshot.json'
  snapshotUrl: 'monitor_snapshot.json',
};

// Keep in sync with monitor_snapshot.json. Placeholder values only — no real TVFI data.
const PLACEHOLDER_SNAPSHOT = {
  schema_version: '1.0',
  snapshot_id: 'DEMO-20261027-01',
  is_illustrative: true,
  meta: {
    observation_date: '2026-10-27',
    latest_market_date: '2026-10-26',
    market_session: 'close',
    pricing_basis_date: '2026-09-30',
    source: 'BoC / Fiera reference',
    source_label: 'Illustrative',
    last_successful_update: '2026-10-27T07:05:00-04:00',
    timezone_label: 'ET',
    data_availability: 'CURRENT',
    currency: 'CAD',
    yield_type: 'nominal',
  },
  maturities: [0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30],
  curves: {
    pricing_basis: {
      label: 'Pricing Basis Curve',
      as_of: '2026-09-30',
      yields: [3.00, 2.90, 2.85, 2.90, 3.05, 3.20, 3.35, 3.50, 3.55, 3.60],
    },
    current_basis: {
      label: 'Current Basis Curve',
      as_of: '2026-10-26',
      yields: [2.96, 2.88, 2.86, 2.93, 3.11, 3.28, 3.45, 3.62, 3.69, 3.76],
    },
    implied: {
      label: 'Updated / Implied Curve',
      as_of: '2026-10-26',
      construction: 'Updated / implied = current + 0.05%',
      construction_note: 'A constant +5 bp uplift is a display-only assumption, not the planned production methodology. Fiera use and implied-curve calculations require separate validation.',
      yields: [3.01, 2.93, 2.91, 2.98, 3.16, 3.33, 3.50, 3.67, 3.74, 3.81],
    },
  },
  assessment: {
    overall_status: 'UNASSESSED',
    detail: 'Pending calibration',
    note: 'Thresholds not established. No rules evaluated.',
    outcome: 'No trigger conclusion. All observations are synthetic and every threshold is "To be calibrated". Data availability alone does not establish a market trigger or a pass.',
  },
  triggers: [
    { id: 'parallel', label: 'Parallel movement', metric: 'abs_mean_change_bp', threshold_bp: null, status: 'NOT_EVALUATED' },
    { id: 'maturity', label: 'Maturity-level movement', metric: 'max_abs_change_bp', threshold_bp: null, status: 'NOT_EVALUATED' },
    { id: 'twist', label: 'Curve shape / twist', metric: 'abs_twist_2s10s_bp', threshold_bp: null, status: 'NOT_EVALUATED' },
  ],
  history: [
    { date: '2026-10-14', mean_shift_bp: -3.1, flagged: false },
    { date: '2026-10-15', mean_shift_bp: 0.8, flagged: false },
    { date: '2026-10-16', mean_shift_bp: 2.6, flagged: false },
    { date: '2026-10-19', mean_shift_bp: 14.2, flagged: true, note: 'upward level movement' },
    { date: '2026-10-20', mean_shift_bp: 3.4, flagged: false },
    { date: '2026-10-21', mean_shift_bp: 1.2, flagged: false },
    { date: '2026-10-22', mean_shift_bp: -10.8, flagged: true, note: 'downward level movement' },
    { date: '2026-10-23', mean_shift_bp: -1.4, flagged: false },
    { date: '2026-10-26', mean_shift_bp: 4.1, flagged: false },
    { date: '2026-10-27', mean_shift_bp: 6.4, flagged: false },
  ],
  data_quality: {
    reference_basis: 'Fiera 26 Oct · pricing snapshot 30 Sep',
    last_pipeline_run: '2026-10-27T07:05:00-04:00',
    pipeline_run_simulated: true,
  },
  pipeline_runs: [],
  notes: {
    chart_reading: 'Reading the curves: short-end yields are lower; the long end is higher. The implied curve uses a synthetic +5 bp uplift to current yields, solely to demonstrate the comparison.',
  },
};

const SERIES = [
  { key: 'pricing_basis', label: 'Pricing Basis Curve', cls: 's-pricing' },
  { key: 'current_basis', label: 'Current Basis Curve', cls: 's-current' },
  { key: 'implied', label: 'Updated / Implied Curve', cls: 's-implied' },
];

// Metrics a trigger can reference via its `metric` key.
const METRICS = {
  abs_mean_change_bp: {
    label: '|mean Δ|',
    text: (d) => (isNum(d.mean) ? `${Math.abs(d.mean).toFixed(1)} bp` : '—'),
  },
  max_abs_change_bp: {
    label: 'max |Δ|',
    text: (d, s) => (d.maxIdx < 0 ? '—' : `${Math.abs(d.change[d.maxIdx]).toFixed(0)} bp · ${tenor(s.maturities[d.maxIdx])}`),
  },
  abs_twist_2s10s_bp: {
    label: '|Δ 2s10s|',
    text: (d) => (isNum(d.twist) ? `${Math.abs(d.twist).toFixed(1)} bp` : '—'),
  },
};

const OVERALL = {
  UNASSESSED: { label: 'UNASSESSED', cls: 'neutral', box: '' },
  NO_TRIGGER: { label: 'NO TRIGGER', cls: 'ok', box: 'clear' },
  TRIGGERED: { label: 'TRIGGERED', cls: 'warn', box: 'triggered' },
};
const TRIGGER_STATUS = {
  NOT_EVALUATED: { label: 'Not evaluated', cls: '' },
  PASS: { label: 'Within threshold', cls: 'pass' },
  BREACH: { label: 'Triggered', cls: 'breach' },
};

const state = {
  snap: null,
  d: null,          // derived metrics
  source: '',
  selected: null,   // selected maturity (years)
  hover: null,      // hovered maturity on the curve chart
  curve: 'all',
  range: [0, 30],
};

/* ---------- helpers ---------- */

const $ = (sel) => document.querySelector(sel);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function esc(str) {
  return String(str ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Dates are parsed from the ISO string directly so the local timezone never shifts the day.
function fmtDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}
function fmtShortDate(iso) {
  if (!iso) return '—';
  const [, m, d] = iso.slice(0, 10).split('-').map(Number);
  return `${d} ${MONTHS[m - 1]}`;
}
function fmtDateTime(iso, tz) {
  if (!iso) return '—';
  const time = iso.length > 15 ? ` · ${iso.slice(11, 16)} ${tz || ''}` : '';
  return fmtDate(iso) + time.trimEnd();
}

function fmtBp(v, dp = 0) {
  if (!isNum(v)) return '—';
  const s = Math.abs(v).toFixed(dp);
  if (Number(s) === 0) return s;
  return (v > 0 ? '+' : '−') + s;
}
const fmtPct = (v) => (isNum(v) ? `${v.toFixed(2)}%` : '—');
const tenor = (m) => `${m}y`;
const tenorLong = (m) => (m < 1 ? `${Math.round(m * 12)}-month` : `${m}-year`);
const round6 = (v) => Math.round(v * 1e6) / 1e6;

function niceStep(span, maxTicks = 5) {
  const steps = [1, 2, 2.5, 5, 10, 20, 25, 50, 100];
  return steps.find((s) => span / s <= maxTicks) || 100;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
function svgEl(tag, attrs = {}, parent) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(el);
  return el;
}
function svgText(parent, x, y, text, attrs = {}) {
  const t = svgEl('text', { x, y, ...attrs }, parent);
  t.textContent = text;
  return t;
}

function toast(msg, isError = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.toggle('error', isError);
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 4000);
}

function download(filename, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/* ---------- snapshot loading ---------- */

function validateSnapshot(s) {
  const errs = [];
  if (!s || typeof s !== 'object') return ['Snapshot is not a JSON object.'];
  if (!s.meta) errs.push('"meta" is missing.');
  if (!Array.isArray(s.maturities) || !s.maturities.length) {
    errs.push('"maturities" must be a non-empty array.');
    return errs;
  }
  for (const se of SERIES) {
    const y = s.curves?.[se.key]?.yields;
    if (!Array.isArray(y)) errs.push(`"curves.${se.key}.yields" is missing.`);
    else if (y.length !== s.maturities.length) errs.push(`"curves.${se.key}.yields" length does not match "maturities".`);
  }
  return errs;
}

function derive(s) {
  const M = s.maturities;
  const [P, C, I] = SERIES.map((se) => s.curves[se.key].yields);
  const diff = (a, b, i) => (isNum(a[i]) && isNum(b[i]) ? round6((a[i] - b[i]) * 100) : null);

  // Trigger measure (matches pipeline/snapshot.py): implied − pricing.
  const change = M.map((_, i) => diff(I, P, i));
  // Market context only: Canada par current − pricing (not used for KPIs / triggers).
  const marketDelta = M.map((_, i) => diff(C, P, i));
  // Construction uplift: implied − current (display / formula card).
  const impliedDelta = M.map((_, i) => diff(I, C, i));
  const avg = (arr) => {
    const v = arr.filter(isNum);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };

  let maxIdx = -1;
  change.forEach((v, i) => {
    if (isNum(v) && (maxIdx < 0 || Math.abs(v) > Math.abs(change[maxIdx]))) maxIdx = i;
  });

  const i2 = M.indexOf(2);
  const i10 = M.indexOf(10);
  const slope = (Y) => (i2 >= 0 && i10 >= 0 && isNum(Y[i2]) && isNum(Y[i10]) ? round6((Y[i10] - Y[i2]) * 100) : null);
  const slopeP = slope(P);
  const slopeC = slope(C);
  const slopeI = slope(I);

  const complete = M.map((_, i) => SERIES.every((se) => isNum(s.curves[se.key].yields[i])));

  return {
    change,
    marketDelta,
    impliedDelta,
    mean: avg(change),
    meanMarket: avg(marketDelta),
    meanImplied: avg(impliedDelta),
    nValid: change.filter(isNum).length,
    maxIdx,
    slopeP,
    slopeC,
    slopeI,
    // Equivalent to (Δ10y − Δ2y) on implied − pricing, matching pipeline twist_2s10s_bp.
    twist: isNum(slopeP) && isNum(slopeI) ? round6(slopeI - slopeP) : null,
    complete,
    missing: M.filter((_, i) => !complete[i]),
    ordered: M.every((m, i) => i === 0 || m > M[i - 1]),
  };
}

function applySnapshot(snap, source) {
  const errs = validateSnapshot(snap);
  if (errs.length) {
    toast(`Snapshot rejected: ${errs[0]}`, true);
    return false;
  }
  state.snap = snap;
  state.d = derive(snap);
  state.source = source;
  state.hover = null;
  if (!snap.maturities.includes(state.selected)) {
    state.selected = snap.maturities.includes(10) ? 10 : snap.maturities[Math.max(state.d.maxIdx, 0)];
  }
  render();
  return true;
}

async function loadInitialSnapshot() {
  // FUTURE (Cloudflare): this fetch will hit the Worker URL instead of a local file.
  try {
    const res = await fetch(CONFIG.snapshotUrl, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (applySnapshot(await res.json(), CONFIG.snapshotUrl)) return;
  } catch (err) {
    // Expected when index.html is opened from disk (file://) — fall through to placeholder.
  }
  applySnapshot(PLACEHOLDER_SNAPSHOT, 'embedded placeholder (dashboard.js)');
}

function loadFromFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    let snap;
    try {
      snap = JSON.parse(reader.result);
    } catch (err) {
      toast(`Could not parse ${file.name}: ${err.message}`, true);
      return;
    }
    if (applySnapshot(snap, file.name)) toast(`Loaded ${file.name}`);
  };
  reader.readAsText(file);
}

/* ---------- view state ---------- */

function visibleIdx() {
  const [lo, hi] = state.range;
  return state.snap.maturities.map((m, i) => i).filter((i) => {
    const m = state.snap.maturities[i];
    return m >= lo && m <= hi;
  });
}

function selectMaturity(m) {
  state.selected = m;
  state.hover = null;
  renderCurveChart();
  renderBarChart();
  renderMaturity();
}

/* ---------- rendering ---------- */

function render() {
  renderHeader();
  renderKpis();
  renderCurveChart();
  renderBarChart();
  renderTriggers();
  renderQuality();
  renderHistory();
  renderMaturity();
}

function renderHeader() {
  const s = state.snap;
  const m = s.meta || {};
  const illus = !!s.is_illustrative;

  $('#illustrativeBanner').hidden = !illus;
  $('#bannerSnapshotId').textContent = s.snapshot_id || '';

  $('#mObs').textContent = fmtDate(m.observation_date);
  $('#mMarket').textContent = `${fmtDate(m.latest_market_date)}${m.market_session ? ` · ${m.market_session}` : ''}`;
  $('#mSourceLabel').textContent = m.source_label ? `Source · ${m.source_label}` : 'Source';
  $('#mSource').textContent = m.source || '—';
  $('#mUpdate').textContent = fmtDateTime(m.last_successful_update, m.timezone_label);

  const avail = m.data_availability || 'UNKNOWN';
  const availEl = $('#mAvail');
  availEl.className = `dot-status ${avail === 'CURRENT' ? 'ok' : 'warn'}`;
  availEl.textContent = `${avail}${illus ? ' · demo' : ''}`;

  $('#selObs').innerHTML = `<option>${esc(fmtDate(m.observation_date))}</option>`;
  $('#toolbarNote').textContent =
    `${m.currency || ''} ${m.yield_type || ''} yields · ${s.maturities.length} maturity nodes · 1 bp = 0.01%`.trim();

  const a = s.assessment || {};
  $('#tabsNote').textContent = a.overall_status === 'UNASSESSED' || !a.overall_status
    ? 'Assessment pending calibration · rules not evaluated'
    : `Assessment: ${(OVERALL[a.overall_status] || {}).label || a.overall_status}`;

  $('#loadedFrom').textContent = `${state.source} · schema v${s.schema_version || '?'}`;
}

function renderKpis() {
  const s = state.snap;
  const d = state.d;
  const bpUnit = '<small>bp</small>';

  $('#kpiParallel').innerHTML = `${fmtBp(d.mean, 1)}${bpUnit}`;
  $('#kpiParallelFoot').textContent = `Implied − pricing across ${d.nValid} nodes; not a fitted parallel shift.`;

  if (d.maxIdx >= 0) {
    $('#kpiLargest').innerHTML = `${fmtBp(d.change[d.maxIdx])}${bpUnit}`;
    $('#kpiLargestLine').textContent = `${tenorLong(s.maturities[d.maxIdx])} maturity · largest |implied − pricing|`;
  } else {
    $('#kpiLargest').innerHTML = `—${bpUnit}`;
    $('#kpiLargestLine').textContent = 'No complete maturity nodes';
  }

  $('#kpiTwist').innerHTML = `${fmtBp(d.twist, 1)}${bpUnit}`;
  $('#kpiTwistLine').textContent = isNum(d.twist)
    ? `2s10s ${d.twist >= 0 ? 'steepening' : 'flattening'} · ${d.slopeP.toFixed(0)} → ${d.slopeI.toFixed(0)} bp`
    : '2y or 10y node unavailable';

  const a = s.assessment || {};
  const o = OVERALL[a.overall_status] || { label: a.overall_status || '—', cls: 'neutral' };
  $('#kpiStatus').textContent = o.label;
  const detail = $('#kpiStatusDetail');
  detail.className = `dot-status ${o.cls}`;
  detail.textContent = a.detail || '';
  $('#kpiStatusNote').textContent = a.note || '';
}

function renderLegend() {
  $('#curveLegend').innerHTML = SERIES.map((se) => {
    const off = state.curve !== 'all' && state.curve !== se.key ? ' off' : '';
    return `<span class="${off.trim()}"><i class="${se.cls}"></i>${esc(state.snap.curves[se.key].label || se.label)}</span>`;
  }).join('');
}

function renderCurveChart() {
  const s = state.snap;
  const host = $('#curveChart');
  const M = s.maturities;
  const idx = visibleIdx();
  const series = SERIES.filter((se) => state.curve === 'all' || state.curve === se.key);
  $('#curveDesc').textContent =
    `${s.is_illustrative ? 'Illustrative annual' : 'Annual'} yields ·${s.meta.currency || ''} · pricing basis ${fmtDate(s.meta.pricing_basis_date)} / market ${fmtDate(s.meta.latest_market_date)}`;
  renderLegend();
  host.innerHTML = '';

  const vals = series.flatMap((se) => idx.map((i) => s.curves[se.key].yields[i])).filter(isNum);
  if (idx.length < 2 || !vals.length) {
    host.innerHTML = '<p class="empty">Not enough maturity nodes in this range.</p>';
    return;
  }

  const W = 760, H = 300;
  const mg = { t: 12, r: 18, b: 44, l: 46 };
  const xMin = M[idx[0]], xMax = M[idx[idx.length - 1]];
  const yMin = Math.floor((Math.min(...vals) - 0.05) / 0.25) * 0.25;
  const yMax = Math.ceil((Math.max(...vals) + 0.05) / 0.25) * 0.25;
  const x = (v) => mg.l + ((v - xMin) / (xMax - xMin)) * (W - mg.l - mg.r);
  const y = (v) => H - mg.b - ((v - yMin) / (yMax - yMin)) * (H - mg.t - mg.b);

  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': 'Yield curve comparison chart' });

  for (let v = yMin; v <= yMax + 1e-9; v += 0.25) {
    svgEl('line', { x1: mg.l, x2: W - mg.r, y1: y(v), y2: y(v), class: 'grid' }, svg);
    svgText(svg, mg.l - 8, y(v) + 3, v.toFixed(2), { class: 'tick', 'text-anchor': 'end' });
  }

  // Full-curve view uses round tenor ticks; narrow ranges label every node.
  const ticks = xMax - xMin >= 20
    ? [xMin, ...[2, 5, 10, 15, 20, 25, 30].filter((t) => t > xMin + 1 && t <= xMax)]
    : idx.map((i) => M[i]);
  for (const t of ticks) {
    svgEl('line', { x1: x(t), x2: x(t), y1: mg.t, y2: H - mg.b, class: 'grid' }, svg);
    svgText(svg, x(t), H - mg.b + 16, String(t), { class: 'tick', 'text-anchor': 'middle' });
  }
  svgText(svg, (mg.l + W - mg.r) / 2, H - 6, 'Maturity (years) · linear scale', { class: 'axis-title' });

  const selVisible = idx.some((i) => M[i] === state.selected);
  if (selVisible) {
    svgEl('line', { x1: x(state.selected), x2: x(state.selected), y1: mg.t, y2: H - mg.b, class: 'sel-line' }, svg);
  }

  for (const se of series) {
    const Y = s.curves[se.key].yields;
    let path = '';
    let pen = false;
    for (const i of idx) {
      if (!isNum(Y[i])) { pen = false; continue; }
      path += `${pen ? 'L' : 'M'}${x(M[i]).toFixed(1)},${y(Y[i]).toFixed(1)}`;
      pen = true;
    }
    svgEl('path', { d: path, class: `line ${se.cls}` }, svg);
    for (const i of idx) {
      if (isNum(Y[i])) svgEl('circle', { cx: x(M[i]), cy: y(Y[i]), r: 2.4, class: `dot ${se.cls}` }, svg);
    }
  }

  const hoverG = svgEl('g', {}, svg);
  const hit = svgEl('rect', { x: mg.l, y: mg.t, width: W - mg.l - mg.r, height: H - mg.t - mg.b, class: 'hit' }, svg);
  const tip = document.createElement('div');
  tip.className = 'tooltip';

  const nearest = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    let best = idx[0];
    for (const i of idx) if (Math.abs(x(M[i]) - px) < Math.abs(x(M[best]) - px)) best = i;
    return M[best];
  };

  const drawFocus = () => {
    hoverG.innerHTML = '';
    const m = state.hover ?? state.selected;
    const i = M.indexOf(m);
    if (!idx.includes(i)) { tip.hidden = true; return; }

    if (state.hover != null && state.hover !== state.selected) {
      svgEl('line', { x1: x(m), x2: x(m), y1: mg.t, y2: H - mg.b, class: 'hover-line' }, hoverG);
    }
    for (const se of series) {
      const v = s.curves[se.key].yields[i];
      if (isNum(v)) svgEl('circle', { cx: x(m), cy: y(v), r: 4.5, class: `dot hl ${se.cls}` }, hoverG);
    }

    const row = (label, v) => `<div class="tt-row">${esc(label)}<b>${fmtPct(v)}</b></div>`;
    const isSel = m === state.selected;
    tip.innerHTML =
      `<div class="tt-head"><b>${tenorLong(m)} maturity</b><span>${isSel ? 'Selected' : 'Click to select'}</span></div>` +
      SERIES.map((se) => row(s.curves[se.key].label || se.label, s.curves[se.key].yields[i])).join('') +
      `<div class="tt-row total">Implied − pricing (trigger)<b>${fmtBp(state.d.change[i])} bp</b></div>` +
      `<div class="tt-row">Current − pricing (market)<b>${fmtBp(state.d.marketDelta[i])} bp</b></div>`;

    const anchor = s.curves.implied.yields[i];
    const xPct = (x(m) / W) * 100;
    tip.style.left = `${xPct}%`;
    tip.style.top = `${((isNum(anchor) ? y(anchor) : H / 2) / H) * 100}%`;
    tip.classList.toggle('flip', xPct > 60);
    tip.hidden = false;
  };

  hit.addEventListener('mousemove', (ev) => {
    const m = nearest(ev);
    if (m !== state.hover) { state.hover = m; drawFocus(); }
  });
  hit.addEventListener('mouseleave', () => { state.hover = null; drawFocus(); });
  hit.addEventListener('click', (ev) => selectMaturity(nearest(ev)));

  host.append(svg, tip);
  drawFocus();
}

function renderBarChart() {
  const s = state.snap;
  const d = state.d;
  const host = $('#barChart');
  const M = s.maturities;
  const idx = visibleIdx();

  $('#barDesc').textContent = `Implied − Pricing (trigger delta)${s.is_illustrative ? ' · illustrative' : ''}`;
  host.innerHTML = '';
  if (!idx.length) {
    host.innerHTML = '<p class="empty">No maturity nodes in this range.</p>';
    return;
  }

  const W = 760, H = 210;
  const mg = { t: 22, r: 10, b: 42, l: 40 };
  const vals = idx.map((i) => d.change[i]).filter(isNum);
  const lo = Math.min(0, ...vals);
  const hi = Math.max(0, ...vals);
  const step = niceStep(hi - lo || 1, 4);
  const yLo = Math.floor(lo / step) * step;
  const yHi = Math.max(Math.ceil(hi / step) * step, yLo + step);
  const y = (v) => H - mg.b - ((v - yLo) / (yHi - yLo)) * (H - mg.t - mg.b);
  const band = (W - mg.l - mg.r) / idx.length;
  const barW = Math.min(36, band * 0.5);

  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': 'Maturity-level change bar chart' });

  for (let v = yLo; v <= yHi + 1e-9; v += step) {
    svgEl('line', { x1: mg.l, x2: W - mg.r, y1: y(v), y2: y(v), class: v === 0 ? 'zero' : 'grid' }, svg);
    svgText(svg, mg.l - 8, y(v) + 3, fmtBp(v), { class: 'tick', 'text-anchor': 'end' });
  }

  idx.forEach((i, k) => {
    const m = M[i];
    const v = d.change[i];
    const cx = mg.l + band * k + band / 2;
    const sel = m === state.selected;
    const g = svgEl('g', {}, svg);

    if (isNum(v)) {
      const top = y(Math.max(v, 0));
      const h = Math.max(Math.abs(y(v) - y(0)), 1);
      svgEl('rect', { x: cx - barW / 2, y: top, width: barW, height: h, class: `bar ${sel ? 'sel' : v >= 0 ? 'pos' : 'neg'}` }, g);
      svgText(g, cx, v >= 0 ? top - 5 : top + h + 12, fmtBp(v), { class: `bar-label${sel ? ' sel' : ''}` });
    } else {
      svgText(g, cx, y(0) - 5, 'n/a', { class: 'bar-label' });
    }
    svgText(g, cx, H - mg.b + 16, tenor(m), { class: `tick${sel ? ' sel' : ''}`, 'text-anchor': 'middle' });

    const hitBand = svgEl('rect', { x: cx - band / 2, y: mg.t - 16, width: band, height: H - mg.t - mg.b + 32, class: 'band' }, g);
    svgEl('title', {}, hitBand).textContent = `${tenor(m)}: ${fmtBp(v)} bp`;
    hitBand.addEventListener('click', () => selectMaturity(m));
  });
  svgText(svg, (mg.l + W - mg.r) / 2, H - 6, 'Maturity nodes (years) · discrete spacing', { class: 'axis-title' });

  host.appendChild(svg);
  $('#readingNote').textContent = s.notes?.chart_reading || '';
  $('#readingNote').hidden = !s.notes?.chart_reading;
}

function renderTriggers() {
  const s = state.snap;
  const a = s.assessment || {};
  const o = OVERALL[a.overall_status] || { label: a.overall_status || '—', box: '' };

  const box = $('#triggerStatusBox');
  box.className = `status-box ${o.box}`;
  box.innerHTML = `<b class="dot-status ${o.cls || ''}">${esc(o.label)}</b><small>${esc(a.detail || '')}${a.overall_status === 'UNASSESSED' ? ' · rules not evaluated' : ''}</small>`;

  $('#triggerList').innerHTML = (s.triggers || []).map((t) => {
    const metric = METRICS[t.metric];
    const st = TRIGGER_STATUS[t.status] || { label: t.status || '—', cls: '' };
    const threshold = isNum(t.threshold_bp) ? `${t.threshold_bp} bp` : 'To be calibrated';
    return `
      <div class="trigger">
        <div class="trigger-head"><span>${esc(t.label)}</span><span class="pill ${st.cls}">${esc(st.label)}</span></div>
        <div class="trigger-body">
          <div><span class="k">Observed metric · ${esc(metric ? metric.label : t.metric)}</span>
               <span class="v">${metric ? esc(metric.text(state.d, s)) : '—'}</span></div>
          <div><span class="k">Threshold</span><span class="v plain">${esc(threshold)}</span></div>
        </div>
      </div>`;
  }).join('') || '<p class="desc">No trigger rules in this snapshot.</p>';

  $('#triggerOutcome').textContent = a.outcome ? `Outcome: ${a.outcome}` : '';
}

function renderQuality() {
  const s = state.snap;
  const d = state.d;
  const m = s.meta || {};
  const dq = s.data_quality || {};
  const n = s.maturities.length;
  const nComplete = d.complete.filter(Boolean).length;

  const rows = [
    ['Source / market date', `${m.source || '—'} / ${fmtDate(m.latest_market_date)}`],
    ['Reference basis', dq.reference_basis || '—'],
    ['Version / identifier', `${s.snapshot_id || '—'} · schema v${s.schema_version || '?'}`],
    ['Validation', `${nComplete}/${n} nodes · ${nComplete === n ? 'finite values' : 'gaps present'} · ${d.ordered ? 'ordered tenors' : 'tenors out of order'}`],
    ['Missing maturities', d.missing.length ? d.missing.map(tenor).join(', ') : `None${s.is_illustrative ? ' in illustrative dataset' : ''}`],
    ['Last pipeline run', `${fmtDateTime(dq.last_pipeline_run, m.timezone_label)}${dq.pipeline_run_simulated ? ' (simulated)' : ''}`],
  ];
  $('#dqList').innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');

  $('#dqChip').hidden = !s.is_illustrative;
  $('#provenance').hidden = !s.is_illustrative;
  const runs = s.pipeline_runs || [];
  $('#pipelineSub').textContent = runs.length ? `${runs.length} run${runs.length === 1 ? '' : 's'} recorded` : 'Available after pipeline integration';
}

function renderHistory() {
  const s = state.snap;
  const h = s.history || [];
  const host = $('#historyChart');
  host.innerHTML = '';

  $('#historyDescSuffix').textContent = s.is_illustrative ? ' · all history is synthetic' : '';
  $('#historyPeriod').textContent = h.length
    ? `${fmtShortDate(h[0].date)}–${fmtDate(h[h.length - 1].date)} · ${h.length} ${s.is_illustrative ? 'illustrative ' : ''}observations`
    : '';

  const flagged = h.filter((p) => p.flagged);
  $('#eventsCount').textContent = `${flagged.length} / ${h.length}`;
  $('#eventsList').innerHTML = flagged
    .map((p) => `<li>${esc(fmtShortDate(p.date))}: ${esc(fmtBp(p.mean_shift_bp, 1))} bp${p.note ? ` · ${esc(p.note)}` : ''}</li>`)
    .join('');

  const pts = h.filter((p) => isNum(p.mean_shift_bp));
  if (!pts.length) {
    host.innerHTML = '<p class="empty">No historical observations in this snapshot.</p>';
    return;
  }

  const W = 900, H = 250;
  const mg = { t: 22, r: 28, b: 34, l: 40 };
  const ext = Math.max(...pts.map((p) => Math.abs(p.mean_shift_bp)), 1);
  const step = niceStep(ext, 2);
  const yMax = Math.ceil(ext / step) * step;
  const x = (k) => (pts.length === 1 ? (mg.l + W - mg.r) / 2 : mg.l + (k / (pts.length - 1)) * (W - mg.l - mg.r));
  const y = (v) => mg.t + ((yMax - v) / (2 * yMax)) * (H - mg.t - mg.b);

  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': 'Historical mean shift chart' });

  for (let v = -yMax; v <= yMax + 1e-9; v += step) {
    svgEl('line', { x1: mg.l, x2: W - mg.r, y1: y(v), y2: y(v), class: v === 0 ? 'zero' : 'grid' }, svg);
    svgText(svg, mg.l - 8, y(v) + 3, fmtBp(v), { class: 'tick', 'text-anchor': 'end' });
  }

  svgEl('path', {
    d: pts.map((p, k) => `${k ? 'L' : 'M'}${x(k).toFixed(1)},${y(p.mean_shift_bp).toFixed(1)}`).join(''),
    class: 'h-line',
  }, svg);

  pts.forEach((p, k) => {
    const v = p.mean_shift_bp;
    const last = k === pts.length - 1;
    const dot = svgEl('circle', { cx: x(k), cy: y(v), r: p.flagged ? 5 : 3, class: `h-dot${p.flagged ? ' flag' : ''}` }, svg);
    svgEl('title', {}, dot).textContent = `${fmtDate(p.date)}: ${fmtBp(v, 1)} bp${p.note ? ` · ${p.note}` : ''}`;
    if (p.flagged || last) {
      svgText(svg, x(k), v >= 0 ? y(v) - 10 : y(v) + 18, fmtBp(v, 1), { class: `h-label${p.flagged ? ' flag' : ''}` });
    }
    svgText(svg, x(k), H - mg.b + 18, fmtShortDate(p.date), { class: 'tick', 'text-anchor': 'middle' });
  });

  host.appendChild(svg);
}

function renderMaturity() {
  const s = state.snap;
  const d = state.d;
  const M = s.maturities;
  const idx = visibleIdx();
  const [P, C, I] = SERIES.map((se) => s.curves[se.key].yields);
  const a = s.assessment || {};
  const o = OVERALL[a.overall_status] || { label: a.overall_status || '—' };
  const si = M.indexOf(state.selected);

  $('#matIllus').textContent = s.is_illustrative ? 'illustrative ' : '';
  $('#matCount').textContent = `${idx.length} of ${M.length} maturities`;
  $('#thPricing').innerHTML = `${esc(s.curves.pricing_basis.label || 'Pricing Basis Curve')}<br>${esc(fmtDate(s.curves.pricing_basis.as_of))} · %`;
  $('#thCurrent').innerHTML = `${esc(s.curves.current_basis.label || 'Current Basis Curve')}<br>${esc(fmtDate(s.curves.current_basis.as_of))} · %`;
  $('#thImplied').innerHTML = `${esc(s.curves.implied.label || 'Updated / Implied Curve')}<br>${esc(fmtDate(s.curves.implied.as_of))} · %`;

  const matTrigger = (s.triggers || []).find((t) => t.metric === 'max_abs_change_bp');
  const matNote = !matTrigger || matTrigger.status === 'NOT_EVALUATED'
    ? 'No maturity-level trigger rule has been evaluated.'
    : `Maturity-level rule: ${(TRIGGER_STATUS[matTrigger.status] || {}).label || matTrigger.status}`;
  $('#selStrip').innerHTML = `
    <div><span class="k">Selected maturity</span><div class="big">${si >= 0 ? `${M[si]} years` : '—'}</div></div>
    <div><span class="k">${esc(s.curves.implied.label || 'Updated / Implied Curve')}</span><div class="big mono">${fmtPct(I[si])}</div></div>
    <div><span class="k">Implied − pricing (trigger)</span><div class="big mono teal">${fmtBp(d.change[si])} bp</div></div>
    <div class="right"><b>${esc(o.label)}${a.detail ? ` · ${esc(a.detail)}` : ''}</b><small>${esc(matNote)}</small></div>`;

  const sign = (v) => (isNum(v) ? (v > 0 ? 'pos' : v < 0 ? 'neg' : '') : '');
  const body = $('#matBody');
  body.innerHTML = idx.map((i) => `
    <tr data-m="${M[i]}" class="${M[i] === state.selected ? 'sel' : ''}">
      <td>${tenor(M[i])}</td>
      <td>${fmtPct(P[i])}</td>
      <td>${fmtPct(C[i])}</td>
      <td>${fmtPct(I[i])}</td>
      <td class="${sign(d.marketDelta[i])}">${fmtBp(d.marketDelta[i])}</td>
      <td class="${sign(d.change[i])}">${fmtBp(d.change[i])}</td>
      <td class="${d.complete[i] ? '' : 'bad'}">${d.complete[i] ? 'Complete · finite' : 'Missing value'}</td>
    </tr>`).join('');
  body.querySelectorAll('tr').forEach((tr) => tr.addEventListener('click', () => selectMaturity(Number(tr.dataset.m))));

  const maxTxt = d.maxIdx >= 0 ? `max |implied − pricing| ${Math.abs(d.change[d.maxIdx]).toFixed(0)} bp at ${tenor(M[d.maxIdx])}` : 'max |Δ| —';
  $('#matFoot').textContent = `${M.length} nodes · ${d.missing.length} missing · mean implied − pricing ${fmtBp(d.mean, 1)} bp · ${maxTxt}`;
  $('#matFine').textContent = s.is_illustrative
    ? 'ILLUSTRATIVE DATA · Not actual TVFI results. Completeness and finite-value checks describe only this placeholder dataset; they are not production validation. All maturities remain unassessed until rules are calibrated and validated.'
    : '';

  // Formula cards — show the arithmetic with this snapshot's numbers.
  const i2 = M.indexOf(2), i10 = M.indexOf(10);
  $('#fParallel').textContent = `Σ(implied − pricing) × 100 / ${d.nValid} = ${fmtBp(d.mean, 1)} bp`;
  $('#fTwist').textContent = isNum(d.twist)
    ? `[(${I[i10].toFixed(2)} − ${I[i2].toFixed(2)}) − (${P[i10].toFixed(2)} − ${P[i2].toFixed(2)})] × 100 = ${fmtBp(d.twist, 1)} bp`
    : '[(I10 − I2) − (P10 − P2)] × 100 = —';
  $('#fTwistDesc').textContent = isNum(d.twist)
    ? `The 2s10s slope ${d.twist >= 0 ? 'increases' : 'decreases'} from ${d.slopeP.toFixed(0)} to ${d.slopeI.toFixed(0)} bp (implied vs pricing). A ${d.twist >= 0 ? 'positive' : 'negative'} slope change describes ${d.twist >= 0 ? 'steepening' : 'flattening'}, not a validated trigger outcome.`
    : 'Requires both 2-year and 10-year nodes.';
  $('#fImplied').textContent = s.curves.implied.construction || `Mean implied − current = ${fmtBp(d.meanImplied, 1)} bp`;
  $('#fImpliedDesc').textContent = s.curves.implied.construction_note
    || `Canada-par current − pricing (market context) mean = ${fmtBp(d.meanMarket, 1)} bp · not the trigger delta.`;
}

/* ---------- exports & history dialog ---------- */

function exportSnapshot() {
  const s = state.snap;
  download(`monitor_snapshot_${s.snapshot_id || 'export'}.json`, JSON.stringify(s, null, 2), 'application/json');
}

function exportCsv() {
  const s = state.snap;
  const d = state.d;
  const [P, C, I] = SERIES.map((se) => s.curves[se.key].yields);
  const lines = [['maturity_years', 'pricing_basis_pct', 'current_basis_pct', 'implied_pct', 'implied_minus_pricing_bp', 'current_minus_pricing_bp', 'complete'].join(',')];
  for (const i of visibleIdx()) {
    const cell = (v, dp) => (isNum(v) ? v.toFixed(dp) : '');
    lines.push([s.maturities[i], cell(P[i], 2), cell(C[i], 2), cell(I[i], 2), cell(d.change[i], 1), cell(d.marketDelta[i], 1), d.complete[i]].join(','));
  }
  download(`maturity_analysis_${s.snapshot_id || 'export'}.csv`, lines.join('\n'), 'text/csv');
}

function openHistory() {
  const s = state.snap;
  $('#historyBody').innerHTML = (s.history || []).map((p) => `
    <tr>
      <td>${esc(fmtDate(p.date))}</td>
      <td>${esc(fmtBp(p.mean_shift_bp, 1))}</td>
      <td>${p.flagged ? 'Yes' : '—'}</td>
      <td>${esc(p.note || '')}</td>
    </tr>`).join('') || '<tr><td colspan="4">No observations.</td></tr>';

  const runs = s.pipeline_runs || [];
  $('#pipelineRuns').innerHTML = runs.length
    ? `<ul class="events-list">${runs.map((r) => `<li>${esc(fmtDateTime(r.run_at, s.meta.timezone_label))} · ${esc(r.status || '')}${r.note ? ` · ${esc(r.note)}` : ''}</li>`).join('')}</ul>`
    : '<p class="desc">Available after pipeline integration. Runs will be appended to pipeline_runs in monitor_snapshot.json.</p>';

  $('#historyDialog').showModal();
}

/* ---------- controls ---------- */

function bindControls() {
  const fileInput = $('#fileInput');
  $('#btnLoad').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) loadFromFile(fileInput.files[0]);
    fileInput.value = '';
  });
  $('#btnExport').addEventListener('click', exportSnapshot);
  $('#btnCsv').addEventListener('click', exportCsv);
  $('#btnHistory').addEventListener('click', openHistory);
  $('#pipelineRow').addEventListener('click', openHistory);
  $('#btnCloseDialog').addEventListener('click', () => $('#historyDialog').close());

  $('#selCurve').addEventListener('change', (e) => {
    state.curve = e.target.value;
    renderCurveChart();
  });
  $('#selRange').addEventListener('change', (e) => {
    state.range = e.target.value.split('-').map(Number);
    renderCurveChart();
    renderBarChart();
    renderMaturity();
  });

  document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => showTab(tab.dataset.tab)));
  if (location.hash === '#maturity') showTab('maturity');
}

function showTab(name) {
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  $('#tab-overview').hidden = name !== 'overview';
  $('#tab-maturity').hidden = name !== 'maturity';
  history.replaceState(null, '', name === 'overview' ? location.pathname : `#${name}`);
}

bindControls();
loadInitialSnapshot();
