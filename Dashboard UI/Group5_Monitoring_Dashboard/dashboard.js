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
 * Summary KPIs prefer snapshot.metrics_computed / decision when present (Python owns
 * mean |Δ|, max |Δ|, twist). Per-maturity change arrays are still derived here for
 * charts. Canada-par current − pricing is market context only.
 * Trigger statuses are taken as-is from the snapshot — rule evaluation lives upstream
 * in the Trigger / Decision log step, not here.
 */
'use strict';

const CONFIG = {
  // Pipeline writes once to data/monitor/. Serve from the TVFI project root:
  //   cd /Users/mickle/Desktop/STATS4960/TVFI && python3 -m http.server 8000
  //   open http://127.0.0.1:8000/Dashboard%20UI/Group5_Monitoring_Dashboard/
  // FUTURE (Cloudflare): replace with the Worker endpoint, e.g.
  //   'https://<worker-name>.<account>.workers.dev/monitor_snapshot.json'
  snapshotUrl: '../../data/monitor/monitor_snapshot.json',
  // Optional experimental Ridge/PCA nowcast summary (from pipeline.lag_bridge_mlr).
  nowcastUrl: '../../data/curves/lag_bridge_mlr_levels_delta_results.json',
  // Predict → IoA bootstrap lag remedy (pipeline.lag_bridge_bootstrap).
  lagBootstrapSummaryUrl: '../../data/curves/lag_bootstrap/summary_2026-11-04_to_2026-11-19.json',
  lagBootstrapMethodUrl: (method, day) =>
    `../../data/curves/lag_bootstrap/${method}/${day}.json`,
  lagBootstrapLatestUrl: (method) =>
    `../../data/curves/lag_bootstrap/${method}/latest.json`,
  // Multi-sheet Excel of all predicted zeros + IoA bootstrap curves.
  lagBootstrapXlsxUrl: '../../data/curves/lag_bootstrap/lag_bootstrap_curves.xlsx',
  // Walk-forward per-maturity MoE (SE / RMSE / P90|e|) from pipeline.lag_error_report.
  lagErrorReportUrl: '../../data/curves/lag_error_report.json',
  // Official held BoC annual zeros (dated snaps) for the "current" curve cutoff.
  bocSnapshotsUrls: [
    '../../data/risk_free/2026-10-21.json',
    '../../data/risk_free/2026-10-28.json',
    '../../data/risk_free/2026-11-04.json',
  ],
  // Production keyed-shift RF (continues past rf_asof).
  productionShiftUrl: '../../data/curves/lag_bridge_2026-11-04_applied.json',
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
    { id: 'weighted', label: 'Weighted |Δ| T', metric: 'weighted_abs_change_bp', threshold_bp: null, status: 'NOT_EVALUATED' },
    { id: 'bucket', label: 'Largest bucket mean |Δ|', metric: 'max_bucket_abs_change_bp', threshold_bp: null, status: 'NOT_EVALUATED' },
    { id: 'twist', label: 'Curve shape / twist', metric: 'abs_twist_2s10s_bp', threshold_bp: null, status: 'NOT_EVALUATED' },
    { id: 'signed', label: 'Signed weighted Δ S', metric: 'weighted_signed_change_bp', threshold_bp: null, status: 'NOT_EVALUATED' },
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
  weighted_abs_change_bp: {
    label: 'weighted |Δ| T',
    text: (d) => (isNum(d.weightedAbs) ? `${fmtAbsBp(d.weightedAbs, 1)} bp` : '—'),
  },
  weighted_signed_change_bp: {
    label: 'signed weighted Δ S',
    text: (d) => (isNum(d.weightedSigned) ? `${d.weightedSigned.toFixed(1)} bp` : '—'),
  },
  max_bucket_abs_change_bp: {
    label: 'max bucket |Δ|',
    text: (d) => {
      if (!isNum(d.maxBucketAbs)) return '—';
      const label = d.maxBucketLabel ? ` · ${d.maxBucketLabel}` : '';
      return `${Math.abs(d.maxBucketAbs).toFixed(0)} bp${label}`;
    },
  },
  abs_mean_change_bp: {
    label: '|mean Δ|',
    text: (d) => (isNum(d.meanAbs) ? `${Math.abs(d.meanAbs).toFixed(1)} bp` : '—'),
  },
  max_abs_change_bp: {
    label: 'max |Δ|',
    text: (d, s) => {
      if (isNum(d.maxAbs)) {
        const node = d.maxIdx >= 0 ? ` · ${tenor(s.maturities[d.maxIdx])}` : '';
        return `${Math.abs(d.maxAbs).toFixed(0)} bp${node}`;
      }
      return d.maxIdx < 0 ? '—' : `${Math.abs(d.change[d.maxIdx]).toFixed(0)} bp · ${tenor(s.maturities[d.maxIdx])}`;
    },
  },
  abs_twist_2s10s_bp: {
    label: '|Δ 2s10s|',
    text: (d) => {
      const v = isNum(d.twistAbs) ? d.twistAbs : d.twist;
      return isNum(v) ? `${Math.abs(v).toFixed(1)} bp` : '—';
    },
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

const LAG_BOOT_METHODS = ['ridge', 'pca', 'pca_ridge'];

const LAG_BOOT_SERIES_META = {
  current: { label: 'Known BoC (held)', color: '#6f8696', dashed: false },
  production: { label: 'Production Valet shift', color: '#5b6b7c', dashed: true },
  ridge: { label: 'Ridge predicted', color: '#2c7a71', dashed: false },
  pca: { label: 'PCA predicted', color: '#b07a28', dashed: false },
  pca_ridge: { label: 'PCA+Ridge predicted', color: '#213851', dashed: false },
  ridge_fwd: { label: 'Ridge fwd', color: '#2c7a71', dashed: true },
  pca_fwd: { label: 'PCA fwd', color: '#b07a28', dashed: true },
  pca_ridge_fwd: { label: 'PCA+Ridge fwd', color: '#213851', dashed: true },
};

const state = {
  snap: null,
  d: null,          // derived metrics
  source: '',
  nowcast: null,    // optional lag_bridge_mlr results JSON
  lagBootstrap: null, // { summary, byMethod, selectedDay, dayCache, days }
  lagErrorReport: null, // lag_error_report.json (per-maturity SE / MoE)
  lagMoeMethod: 'ridge',
  bocHistory: [],   // [{ asof, zeros: {1..30} }] sorted
  productionShift: null, // lag_bridge applied JSON
  lagBootView: 'time',   // 'time' | 'maturity'
  lagBootTenor: 10,
  lagBootVisible: {
    current: true,
    production: true,
    ridge: true,
    pca: true,
    pca_ridge: true,
    ridge_fwd: false,
    pca_fwd: false,
    pca_ridge_fwd: false,
  },
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
/** Absolute bp (no sign) — for T, bucket mean |Δ|, and other unsigned measures. */
function fmtAbsBp(v, dp = 0) {
  if (!isNum(v)) return '—';
  return Math.abs(v).toFixed(dp);
}
/** Last-resort fallback for old placeholders that lack pipeline threshold/flagged. */
const HISTORY_PRIMARY_THR_BP_FALLBACK = 35;
const fmtPct = (v) => (isNum(v) ? `${v.toFixed(2)}%` : '—');

/** Pipeline is the sole write-side source for primary threshold (CALIBRATED.weighted). */
function primaryThresholdBp(snap) {
  const mc = (snap && snap.metrics_computed) || {};
  if (isNum(mc.primary_threshold_bp)) return mc.primary_threshold_bp;
  const primary = ((snap && snap.triggers) || []).find(
    (t) => t.role === 'primary' || t.id === 'weighted' || t.metric === 'weighted_abs_change_bp'
  );
  if (primary && isNum(primary.threshold_bp)) return primary.threshold_bp;
  return HISTORY_PRIMARY_THR_BP_FALLBACK;
}
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

  // Per-maturity deltas for charts (implied − pricing). Summary KPIs prefer metrics_computed.
  const change = M.map((_, i) => diff(I, P, i));
  // Market context only: Canada par current − pricing (not used for KPIs / triggers).
  const marketDelta = M.map((_, i) => diff(C, P, i));
  // Construction uplift: implied − current (display / formula card).
  const impliedDelta = M.map((_, i) => diff(I, C, i));
  const avg = (arr) => {
    const v = arr.filter(isNum);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  };
  const meanAbsLocal = (() => {
    const v = change.filter(isNum).map((x) => Math.abs(x));
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  })();

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
  const twistLocal = isNum(slopeP) && isNum(slopeI) ? round6(slopeI - slopeP) : null;

  const complete = M.map((_, i) => SERIES.every((se) => isNum(s.curves[se.key].yields[i])));

  // Prefer Python-owned summary metrics when the snapshot carries them.
  const mc = s.metrics_computed || {};
  const decision = s.decision || {};
  const weightedAbs = isNum(mc.weighted_abs_change_bp)
    ? mc.weighted_abs_change_bp
    : (isNum(decision.value_bp) && decision.measure === 'weighted_abs_change_bp'
      ? decision.value_bp
      : null);
  const weightedSigned = isNum(mc.weighted_signed_change_bp)
    ? mc.weighted_signed_change_bp
    : null;
  const maxBucketAbs = isNum(mc.max_bucket_abs_change_bp)
    ? mc.max_bucket_abs_change_bp
    : null;
  const maxBucketLabel = mc.max_bucket_label || null;
  const meanAbs = isNum(mc.abs_mean_change_bp)
    ? mc.abs_mean_change_bp
    : (isNum(decision.value_bp) && decision.measure === 'abs_mean_change_bp'
      ? decision.value_bp
      : meanAbsLocal);
  const maxAbs = isNum(mc.max_abs_change_bp)
    ? mc.max_abs_change_bp
    : (maxIdx >= 0 ? Math.abs(change[maxIdx]) : null);
  // Prefer pipeline max_maturity so abs + tenor stay aligned even if JS change[] drifts.
  const maxIdxPipeline = (() => {
    if (!isNum(mc.max_maturity)) return maxIdx;
    const i = M.indexOf(mc.max_maturity);
    return i >= 0 ? i : maxIdx;
  })();
  const twistAbs = isNum(mc.abs_twist_2s10s_bp)
    ? mc.abs_twist_2s10s_bp
    : (isNum(twistLocal) ? Math.abs(twistLocal) : null);

  return {
    change,
    marketDelta,
    impliedDelta,
    mean: avg(change), // signed mean (formula cards / market context)
    weightedAbs,       // primary trigger measure (weighted |Δ| T)
    weightedSigned,    // direction diagnostic S
    maxBucketAbs,
    maxBucketLabel,
    meanAbs,           // equal-weight display mean |Δ| (legacy / chart)
    meanMarket: avg(marketDelta),
    meanImplied: avg(impliedDelta),
    nValid: change.filter(isNum).length,
    maxIdx: maxIdxPipeline,
    maxAbs,
    slopeP,
    slopeC,
    slopeI,
    // Signed twist for steepening/flattening labels; abs from metrics_computed when present.
    twist: twistLocal,
    twistAbs,
    metricsFromPipeline: isNum(mc.weighted_abs_change_bp) || isNum(mc.abs_mean_change_bp),
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
  // Do not auto-select a maturity on load (avoids an open tooltip covering the legend).
  if (state.selected != null && !snap.maturities.includes(state.selected)) {
    state.selected = null;
  }
  render();
  return true;
}

async function loadNowcast() {
  try {
    const res = await fetch(CONFIG.nowcastUrl, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.nowcast = await res.json();
  } catch (err) {
    state.nowcast = null;
  }
}

async function fetchJsonQuiet(url) {
  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    return null;
  }
}

function lagBootstrapDaysFromSummary(summary) {
  const days = new Set();
  LAG_BOOT_METHODS.forEach((m) => {
    const block = (summary.methods || {})[m];
    (block && block.days ? block.days : []).forEach((d) => {
      if (d && d.valet_asof && !d.error) days.add(d.valet_asof);
    });
  });
  return Array.from(days).sort();
}

async function loadLagBootstrapDay(day) {
  if (!state.lagBootstrap) return null;
  if (!state.lagBootstrap.dayCache) state.lagBootstrap.dayCache = {};
  if (state.lagBootstrap.dayCache[day]) return state.lagBootstrap.dayCache[day];
  const byMethod = {};
  await Promise.all(
    LAG_BOOT_METHODS.map(async (method) => {
      const payload = await fetchJsonQuiet(CONFIG.lagBootstrapMethodUrl(method, day));
      if (payload) byMethod[method] = payload;
    })
  );
  state.lagBootstrap.dayCache[day] = byMethod;
  return byMethod;
}

async function loadBocHistory() {
  const rows = [];
  await Promise.all(
    (CONFIG.bocSnapshotsUrls || []).map(async (url) => {
      const snap = await fetchJsonQuiet(url);
      if (!snap || !Array.isArray(snap.annual_zeros_1_30)) return;
      const zeros = {};
      snap.annual_zeros_1_30.forEach((z, i) => {
        zeros[i + 1] = Number(z);
      });
      rows.push({
        asof: String(snap.rf_asof || ''),
        zeros,
        publish_lag_days: (snap.gaps && snap.gaps.publish_lag_days) || null,
      });
    })
  );
  rows.sort((a, b) => (a.asof < b.asof ? -1 : a.asof > b.asof ? 1 : 0));
  state.bocHistory = rows.filter((r) => r.asof);
}

async function loadProductionShift() {
  state.productionShift = await fetchJsonQuiet(CONFIG.productionShiftUrl);
}

async function loadLagBootstrap() {
  await Promise.all([loadBocHistory(), loadProductionShift()]);

  const summary = await fetchJsonQuiet(CONFIG.lagBootstrapSummaryUrl);
  if (!summary) {
    // Fall back to latest.json per method if summary missing
    const byMethod = {};
    await Promise.all(
      LAG_BOOT_METHODS.map(async (method) => {
        const payload = await fetchJsonQuiet(CONFIG.lagBootstrapLatestUrl(method));
        if (payload) byMethod[method] = payload;
      })
    );
    if (!Object.keys(byMethod).length) {
      state.lagBootstrap = null;
      return;
    }
    const day =
      (byMethod.ridge && byMethod.ridge.valet_asof) ||
      (byMethod.pca_ridge && byMethod.pca_ridge.valet_asof) ||
      (byMethod.pca && byMethod.pca.valet_asof) ||
      null;
    state.lagBootstrap = {
      summary: null,
      byMethod,
      selectedDay: day,
      dayCache: day ? { [day]: byMethod } : {},
      days: day ? [day] : [],
    };
    return;
  }

  const days = lagBootstrapDaysFromSummary(summary);
  const selectedDay = days.length ? days[days.length - 1] : null;
  state.lagBootstrap = {
    summary,
    byMethod: {},
    selectedDay,
    dayCache: {},
    days,
  };
  // Prefetch every Valet day so the time-series view has full history.
  await Promise.all(days.map((d) => loadLagBootstrapDay(d)));
  if (selectedDay) {
    state.lagBootstrap.byMethod =
      state.lagBootstrap.dayCache[selectedDay] ||
      (await loadLagBootstrapDay(selectedDay));
  }
}

async function loadLagErrorReport() {
  state.lagErrorReport = await fetchJsonQuiet(CONFIG.lagErrorReportUrl);
}

async function loadInitialSnapshot() {
  // FUTURE (Cloudflare): this fetch will hit the Worker URL instead of a local file.
  await loadNowcast();
  await loadLagBootstrap();
  await loadLagErrorReport();
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
  renderFeeds();
  renderLagBootstrap();
  renderCurveChart();
  renderBarChart();
  renderTriggers();
  renderQuality();
  renderHistory();
  renderMaturity();
}

function kvHtml(rows) {
  return rows
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v == null || v === '' ? '—' : v}</dd>`)
    .join('');
}

function renderFeeds() {
  const s = state.snap;
  const m = s.meta || {};
  const bridge = m.lag_bridge || {};
  const mc = s.metrics_computed || {};
  const decision = s.decision || {};
  const profit = s.profitability || {};
  const thrPrimary = isNum(mc.primary_threshold_bp)
    ? mc.primary_threshold_bp
    : (isNum(decision.threshold_bp) ? decision.threshold_bp : 25);
  const thrBucket = (() => {
    const t = (s.triggers || []).find((x) => x.id === 'bucket');
    return t && isNum(t.threshold_bp) ? t.threshold_bp : 40;
  })();

  // --- Data feeds ---
  const rfChip = $('#feedRfChip');
  const rfSrc = m.rf_source || '—';
  rfChip.textContent = String(rfSrc).includes('valet') ? 'BoC + Valet' : (String(rfSrc).startsWith('boc') ? 'BoC RF' : 'RF');
  $('#feedRfList').innerHTML = kvHtml([
    ['RF source', esc(rfSrc)],
    ['RF as-of', esc(fmtDate(m.rf_as_of) || '—')],
    [
      'Publish lag',
      isNum(m.rf_publish_lag_days) ? `${m.rf_publish_lag_days}d (calendar vs rf_asof)` : '—',
    ],
    [
      'Obs − RF gap',
      isNum(m.obs_rf_calendar_gap_days) ? `${m.obs_rf_calendar_gap_days}d` : '—',
    ],
    ['Effective RF', esc(m.rf_effective_as_of || m.rf_as_of || '—')],
    ['Col H policy', esc(m.premium_policy || '—')],
    ['H / premium as-of', esc(fmtDate(m.premium_as_of) || '—')],
    ['Curve mode', esc(m.curve_mode || '—')],
  ]);

  // --- Lag bridge ---
  const applied = !!bridge.applied;
  const bChip = $('#feedBridgeChip');
  bChip.textContent = applied ? 'ON' : (bridge.enabled === false ? 'OFF' : 'SKIPPED');
  bChip.className = `chip ${applied ? 'on' : 'off'}`;
  const anchorBp = bridge.anchor_delta_bp || {};
  const anchorKeys = Object.keys(anchorBp).sort((a, b) => Number(a) - Number(b));
  $('#feedBridgeList').innerHTML = kvHtml([
    ['Method', esc(bridge.method || '—')],
    ['Reason', esc(bridge.reason || '—')],
    ['Valet base → live', applied
      ? `${esc(fmtDate(bridge.valet_base_asof))} → ${esc(fmtDate(bridge.valet_live_asof))}`
      : '—'],
    [
      'Max |Δ|',
      applied && isNum(bridge.max_abs_shift_bp) ? `${Number(bridge.max_abs_shift_bp).toFixed(1)} bp` : '—',
    ],
    [
      'Mean |Δ|',
      applied && isNum(bridge.mean_abs_shift_bp) ? `${Number(bridge.mean_abs_shift_bp).toFixed(1)} bp` : '—',
    ],
  ]);
  const anchorsEl = $('#feedBridgeAnchors');
  if (applied && anchorKeys.length) {
    anchorsEl.hidden = false;
    anchorsEl.innerHTML = anchorKeys.map((k) => {
      const v = Number(anchorBp[k]);
      const cls = v >= 0 ? 'pos' : 'neg';
      const sign = v >= 0 ? '+' : '';
      return `<span class="anchor-pill ${cls}">${esc(k)}y ${sign}${v.toFixed(1)} bp</span>`;
    }).join('');
  } else {
    anchorsEl.hidden = true;
    anchorsEl.innerHTML = '';
  }

  // --- Trigger & profitability ---
  $('#feedTrigChip').textContent = `T≥${thrPrimary} · bucket ${thrBucket}`;
  const tVal = isNum(decision.value_bp)
    ? decision.value_bp
    : (isNum(mc.weighted_abs_change_bp) ? mc.weighted_abs_change_bp : null);
  $('#feedTrigList').innerHTML = kvHtml([
    ['Primary rule', `weighted |Δ| T ≥ ${thrPrimary} bp`],
    ['Bucket diagnostic', `max bucket mean |Δ| ≥ ${thrBucket} bp (does not fire alone)`],
    ['Decision', esc(decision.status || (s.assessment || {}).overall_status || '—')],
    ['T (live)', isNum(tVal) ? `${Number(tVal).toFixed(2)} bp` : '—'],
    [
      'Bucket (live)',
      isNum(mc.max_bucket_abs_change_bp)
        ? `${Number(mc.max_bucket_abs_change_bp).toFixed(2)} bp${mc.max_bucket_label ? ` · ${esc(mc.max_bucket_label)}` : ''}`
        : '—',
    ],
    ['Profitability', esc(profit.status || 'not_run')],
    [
      'Export',
      profit.summary && profit.summary.export_path
        ? `<span class="mono">${esc(profit.summary.export_path)}</span>`
        : '—',
    ],
  ]);

  // --- Ridge / PCA nowcast (optional companion JSON) ---
  renderNowcast(state.nowcast);
}

function renderNowcast(nowcast) {
  const list = $('#feedNowcastList');
  const chip = $('#feedNowcastChip');
  const note = $('#feedNowcastNote');
  if (!nowcast || !nowcast.methods) {
    chip.textContent = 'EXPERIMENTAL';
    chip.className = 'chip';
    list.innerHTML = kvHtml([
      ['Status', 'No nowcast results loaded'],
      ['How to refresh', '<span class="mono">python3 -m pipeline.lag_bridge_mlr --train --backtest --predict</span>'],
    ]);
    note.textContent = 'Walk-forward Valet → BoC zeros (not the --rebuilt default). Serve from project root to load results JSON.';
    return;
  }
  const ridge = (nowcast.methods.ridge || {}).backtest_summary || {};
  const pca = (nowcast.methods.pca || {}).backtest_summary || {};
  const ridgeLive = ((nowcast.methods.ridge || {}).live_predict || {}).meta || {};
  chip.textContent = 'LOADED';
  chip.className = 'chip on';
  list.innerHTML = kvHtml([
    ['Feature mode', esc(nowcast.feature_mode || '—')],
    [
      'Ridge walk-forward',
      isNum(ridge.mean_rmse_bp)
        ? `mean RMSE ${Number(ridge.mean_rmse_bp).toFixed(2)} bp (n=${ridge.n || '—'})`
        : '—',
    ],
    [
      'PCA walk-forward',
      isNum(pca.mean_rmse_bp)
        ? `mean RMSE ${Number(pca.mean_rmse_bp).toFixed(2)} bp (n=${pca.n || '—'})`
        : '—',
    ],
    [
      'Hold baseline',
      isNum(ridge.hold_mean_rmse_bp)
        ? `mean RMSE ${Number(ridge.hold_mean_rmse_bp).toFixed(2)} bp`
        : (isNum(pca.hold_mean_rmse_bp) ? `mean RMSE ${Number(pca.hold_mean_rmse_bp).toFixed(2)} bp` : '—'),
    ],
    [
      'Live Valet',
      ridgeLive.valet_live_asof
        ? `${esc(fmtDate(ridgeLive.boc_rf_asof))} RF ← Valet ${esc(fmtDate(ridgeLive.valet_live_asof))}`
        : '—',
    ],
  ]);
  note.textContent = 'Experimental horse-race vs keyed Valet shift. Hold Fiera H unchanged; RF-only nowcast.';
}

const LAG_BOOT_UI = [
  { key: 'ridge', label: 'Ridge', chip: '#lagBootRidgeChip', list: '#lagBootRidgeList', cls: 'lg-ridge', color: '#2c7a71' },
  { key: 'pca', label: 'PCA curve', chip: '#lagBootPcaChip', list: '#lagBootPcaList', cls: 'lg-pca', color: '#b07a28' },
  { key: 'pca_ridge', label: 'PCA+Ridge', chip: '#lagBootPcaRidgeChip', list: '#lagBootPcaRidgeList', cls: 'lg-pca-ridge', color: '#213851' },
];

function lagBootSpotPct(payload, year) {
  if (!payload) return null;
  const rows = payload.predicted_zeros_annual_effective || [];
  const hit = rows.find((r) => Number(r.year) === year);
  if (hit && isNum(hit.zero)) return Number(hit.zero) * 100;
  const boot = (payload.bootstrap || []).find((r) => Number(r.year) === year);
  if (boot && isNum(boot.zero_annual_effective)) return Number(boot.zero_annual_effective) * 100;
  return null;
}

function lagBootFwdPct(payload, year) {
  if (!payload) return null;
  const boot = (payload.bootstrap || []).find((r) => Number(r.year) === year);
  if (boot && isNum(boot.forward_1y)) return Number(boot.forward_1y) * 100;
  return null;
}

function bocHistorySpotPct(snap, year) {
  if (!snap) return null;
  // loadBocHistory stores { asof, zeros: {1..30} }; raw BoC JSON uses annual_zeros_1_30[].
  if (snap.zeros && isNum(snap.zeros[year])) {
    return Number(snap.zeros[year]) * 100;
  }
  const arr = snap.annual_zeros_1_30 || [];
  const idx = year - 1;
  if (idx < 0 || idx >= arr.length) return null;
  const v = arr[idx];
  return isNum(v) ? Number(v) * 100 : null;
}

function bocHistoryAsof(snap) {
  if (!snap) return null;
  return snap.asof || snap.rf_asof || null;
}

function productionShiftSpotPct(year) {
  const ps = state.productionShift;
  if (!ps || !Array.isArray(ps.annual_zeros_1_30)) return null;
  const idx = year - 1;
  if (idx < 0 || idx >= ps.annual_zeros_1_30.length) return null;
  const v = ps.annual_zeros_1_30[idx];
  return isNum(v) ? Number(v) * 100 : null;
}

function lagBootRfAsOf() {
  const lb = state.lagBootstrap;
  const summary = (lb && lb.summary) || {};
  const byMethod = (lb && lb.byMethod) || {};
  const sample = byMethod.ridge || byMethod.pca_ridge || byMethod.pca || {};
  return (
    summary.boc_rf_asof ||
    sample.boc_rf_asof ||
    (state.productionShift && state.productionShift.bridge && state.productionShift.bridge.rf_asof) ||
    (state.snap && state.snap.meta && state.snap.meta.rf_as_of) ||
    null
  );
}

function lagMoeStatsFor(method) {
  const rep = state.lagErrorReport;
  if (!rep || !rep.methods || !rep.methods[method]) return null;
  return rep.methods[method];
}

function lagMoeRow(method, year) {
  const block = lagMoeStatsFor(method);
  if (!block || !Array.isArray(block.by_maturity_boot)) return null;
  return block.by_maturity_boot.find((r) => Number(r.year) === Number(year)) || null;
}

function fillLagBootMethodCard(ui, payload) {
  const chip = $(ui.chip);
  const list = $(ui.list);
  if (!payload) {
    chip.textContent = '—';
    chip.className = 'chip off';
    list.innerHTML = kvHtml([['Status', 'No artifact for this day']]);
    return;
  }
  chip.textContent = 'LOADED';
  chip.className = 'chip on';
  const z1 = lagBootSpotPct(payload, 1);
  const z10 = lagBootSpotPct(payload, 10);
  const z30 = lagBootSpotPct(payload, 30);
  const f10 = lagBootFwdPct(payload, 10);
  const moe = lagMoeStatsFor(ui.key);
  const r1 = lagMoeRow(ui.key, 1);
  const r10 = lagMoeRow(ui.key, 10);
  const r30 = lagMoeRow(ui.key, 30);
  const rows = [
    ['Method', esc(payload.method || ui.key)],
    ['Valet as-of', esc(fmtDate(payload.valet_asof) || '—')],
    ['BoC rf_asof', esc(fmtDate(payload.boc_rf_asof) || '—')],
    ['Spot y1 / y10 / y30', [
      isNum(z1) ? z1.toFixed(3) : '—',
      isNum(z10) ? z10.toFixed(3) : '—',
      isNum(z30) ? z30.toFixed(3) : '—',
    ].join(' / ') + ' %'],
    ['Fwd y10 (boot)', isNum(f10) ? `${f10.toFixed(3)} %` : '—'],
  ];
  if (moe) {
    rows.push([
      'MoE (WF)',
      `RMSE ${Number(moe.curve_rmse_bp).toFixed(2)} bp · mean SE ${Number(moe.mean_tenor_se_bp).toFixed(3)} bp · P90|e| ${Number(moe.p90_abs_curve_bp).toFixed(2)} bp`,
    ]);
    rows.push([
      'SE y1 / y10 / y30',
      [
        r1 && isNum(r1.se_bp) ? Number(r1.se_bp).toFixed(3) : '—',
        r10 && isNum(r10.se_bp) ? Number(r10.se_bp).toFixed(3) : '—',
        r30 && isNum(r30.se_bp) ? Number(r30.se_bp).toFixed(3) : '—',
      ].join(' / ') + ' bp',
    ]);
  }
  list.innerHTML = kvHtml(rows);
}

function renderLagMoePanel() {
  const chip = $('#lagMoeChip');
  const summary = $('#lagMoeSummary');
  const body = $('#lagMoeBody');
  const desc = $('#lagMoeDesc');
  if (!chip || !summary || !body) return;

  const method = state.lagMoeMethod || 'ridge';
  const moeSel = $('#selLagMoeMethod');
  if (moeSel) moeSel.value = method;

  const block = lagMoeStatsFor(method);
  const rep = state.lagErrorReport;
  if (!block || !Array.isArray(block.by_maturity_boot)) {
    chip.textContent = 'MoE';
    chip.className = 'chip off';
    summary.innerHTML = kvHtml([
      ['Status', 'No lag_error_report.json loaded'],
      ['Refresh', '<span class="mono">python3 -m pipeline.lag_error_report --methods ridge,pca_ridge</span>'],
    ]);
    body.innerHTML = '<tr><td colspan="6">Serve from TVFI root so ../../data/curves/lag_error_report.json resolves.</td></tr>';
    if (desc) {
      desc.textContent =
        'SE = sd(residuals)/√n at each tenor vs later BoC. Daily lag-bridge MoE — not clock-hourly.';
    }
    return;
  }

  chip.textContent = 'LOADED';
  chip.className = 'chip on';
  if (desc) {
    desc.textContent =
      `Walk-forward n=${block.n_days} (${fmtDate(rep.date_from) || '—'} → ${fmtDate(rep.date_to) || '—'}). ` +
      'SE = sd/√n per tenor; P90|e| ≈ 90% MoE band. Valet business-daily — not clock-hourly.';
  }
  summary.innerHTML = kvHtml([
    ['Method', esc(method)],
    ['Curve RMSE', `${Number(block.curve_rmse_bp).toFixed(2)} bp`],
    ['Mean tenor SE', `${Number(block.mean_tenor_se_bp).toFixed(3)} bp`],
    ['Pooled P90|e|', `${Number(block.p90_abs_curve_bp).toFixed(2)} bp`],
    ['Freshness', 'Valet-timed daily (not clock-hourly)'],
  ]);

  const keyYears = new Set([1, 2, 3, 5, 7, 10, 15, 20, 25, 30]);
  body.innerHTML = block.by_maturity_boot
    .filter((r) => keyYears.has(Number(r.year)))
    .map((r) => `
      <tr>
        <td>${esc(r.year)}y</td>
        <td>${Number(r.bias_bp).toFixed(2)}</td>
        <td>${Number(r.sd_bp).toFixed(2)}</td>
        <td>${Number(r.se_bp).toFixed(3)}</td>
        <td>${Number(r.rmse_bp).toFixed(2)}</td>
        <td>${Number(r.p90_abs_bp).toFixed(2)}</td>
      </tr>`)
    .join('');
}

function setLagBootTip(html, clientX, clientY) {
  const tip = $('#lagBootTip');
  const host = $('#lagBootChart');
  if (!tip || !host) return;
  if (!html) {
    tip.hidden = true;
    tip.innerHTML = '';
    return;
  }
  tip.hidden = false;
  tip.innerHTML = html;
  const rect = host.getBoundingClientRect();
  let left = clientX - rect.left + 12;
  let top = clientY - rect.top + 12;
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
  const tipRect = tip.getBoundingClientRect();
  if (tipRect.right > rect.right - 4) {
    left = Math.max(8, clientX - rect.left - tipRect.width - 12);
    tip.style.left = `${left}px`;
  }
  if (tipRect.bottom > rect.bottom - 4) {
    top = Math.max(8, clientY - rect.top - tipRect.height - 12);
    tip.style.top = `${top}px`;
  }
}

function renderLagBootstrapLegend() {
  const legend = $('#lagBootLegend');
  if (!legend) return;
  const vis = state.lagBootVisible || {};
  legend.innerHTML = Object.entries(LAG_BOOT_SERIES_META)
    .map(([key, se]) => {
      const on = vis[key] !== false;
      return (
        `<button type="button" data-key="${esc(key)}" class="${on ? '' : 'off'}" ` +
        `aria-pressed="${on ? 'true' : 'false'}" title="Toggle ${esc(se.label)}">` +
        `<span class="swatch${se.dashed ? ' dashed' : ''}" style="${se.dashed ? `border-top-color:${se.color}` : `background:${se.color}`}"></span>` +
        `${esc(se.label)}</button>`
      );
    })
    .join('');
  legend.querySelectorAll('button[data-key]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.key;
      if (!key) return;
      state.lagBootVisible[key] = !(state.lagBootVisible[key] !== false);
      renderLagBootstrapLegend();
      renderLagBootstrapChart(
        (state.lagBootstrap && state.lagBootstrap.byMethod) || {},
        state.lagBootstrap && state.lagBootstrap.selectedDay
      );
    });
  });
}

function renderLagBootstrap() {
  const panel = $('#lagBootPanel');
  if (!panel) return;

  const lb = state.lagBootstrap;
  const chip = $('#lagBootChip');
  const sel = $('#selLagBootDay');
  const desc = $('#lagBootDesc');
  const viewSel = $('#selLagBootView');
  const tenorSel = $('#selLagBootTenor');

  if (viewSel) viewSel.value = state.lagBootView || 'time';
  if (tenorSel) {
    tenorSel.value = String(state.lagBootTenor || 10);
    tenorSel.disabled = (state.lagBootView || 'time') === 'maturity';
  }

  if (!lb || (!lb.byMethod && !(lb.days && lb.days.length))) {
    chip.textContent = 'EXPERIMENTAL';
    chip.className = 'chip';
    if (sel) sel.innerHTML = '';
    LAG_BOOT_UI.forEach((ui) => fillLagBootMethodCard(ui, null));
    $('#lagBootMetaList').innerHTML = kvHtml([
      ['Status', 'No lag_bootstrap artifacts loaded'],
      ['Refresh', '<span class="mono">python3 -m pipeline.lag_bridge_bootstrap --from … --to …</span>'],
    ]);
    $('#lagBootMetaNote').textContent =
      'Serve from project root so data/curves/lag_bootstrap/ resolves.';
    $('#lagBootChart').innerHTML =
      '<p class="empty">No predicted curves loaded. Run lag_bridge_bootstrap and serve from the TVFI root.</p>';
    $('#lagBootLegend').innerHTML = '';
    $('#lagBootChartDesc').textContent =
      'Held BoC RF cuts off at rf_asof; predicted tracks continue through the lag. Hover a curve to name it; click the legend to toggle.';
    setLagBootTip('');
    return;
  }

  chip.textContent = 'LOADED';
  chip.className = 'chip on';

  const days = lb.days && lb.days.length
    ? lb.days
    : (lb.selectedDay ? [lb.selectedDay] : []);
  if (sel) {
    const cur = lb.selectedDay || (days.length ? days[days.length - 1] : '');
    sel.innerHTML = days
      .map((d) => `<option value="${esc(d)}"${d === cur ? ' selected' : ''}>${esc(fmtDate(d) || d)}</option>`)
      .join('');
  }

  const byMethod = lb.byMethod || {};
  LAG_BOOT_UI.forEach((ui) => fillLagBootMethodCard(ui, byMethod[ui.key] || null));

  const summary = lb.summary || {};
  const interval = summary.interval || {};
  const sample = byMethod.ridge || byMethod.pca_ridge || byMethod.pca || {};
  const sampleInterval = sample.interval || interval;
  const rfAsOf = lagBootRfAsOf();
  const nBoc = (state.bocHistory || []).length;
  const hasShift = !!(state.productionShift && state.productionShift.annual_zeros_1_30);
  $('#lagBootMetaList').innerHTML = kvHtml([
    [
      'Interval',
      sampleInterval.from && sampleInterval.to
        ? `${esc(fmtDate(sampleInterval.from))} → ${esc(fmtDate(sampleInterval.to))}`
        : '—',
    ],
    ['BoC rf_asof (cutoff)', esc(fmtDate(rfAsOf) || '—')],
    ['Valet day', esc(fmtDate(lb.selectedDay) || '—')],
    ['Feature mode', esc(summary.feature_mode || '—')],
    [
      'Days in run',
      isNum(summary.n_valet_days) ? String(summary.n_valet_days) : String(days.length || '—'),
    ],
    [
      'Tracks loaded',
      LAG_BOOT_METHODS.filter((m) => byMethod[m]).join(', ') || '—',
    ],
    ['Held BoC history', nBoc ? `${nBoc} dated snap(s)` : '—'],
    ['Production shift', hasShift ? 'loaded' : '—'],
  ]);
  $('#lagBootMetaNote').textContent =
    'Held BoC (current) stops at rf_asof. Predicted Ridge / PCA / PCA+Ridge continue through the lag. Keyed Valet shift remains the --rebuilt default.';
  desc.textContent =
    `Held BoC cutoff ${fmtDate(rfAsOf) || '—'} · predictions through Valet ${fmtDate(lb.selectedDay) || '—'} (experimental).`;

  renderLagMoePanel();
  renderLagBootstrapLegend();
  renderLagBootstrapChart(byMethod, lb.selectedDay);
}

function buildLagBootTimeSeries(byMethod, tenor) {
  const series = [];
  const vis = state.lagBootVisible || {};
  const rfAsOf = lagBootRfAsOf();
  const hist = (state.bocHistory || [])
    .map((h) => ({
      date: bocHistoryAsof(h),
      pct: bocHistorySpotPct(h, tenor),
    }))
    .filter((p) => p.date && isNum(p.pct))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  // Keep the last few known BoC prints on the plot (through rf_asof), then stop.
  let lastKnown = null;
  if (vis.current !== false && hist.length) {
    const cut = hist.filter((p) => !rfAsOf || p.date <= rfAsOf);
    if (cut.length) {
      lastKnown = cut[cut.length - 1];
      series.push({
        key: 'current',
        label: 'Known BoC (held)',
        color: '#6f8696',
        dashed: false,
        cutoff: true,
        points: cut.map((p) => ({ t: p.date, pct: p.pct })),
      });
    }
  }

  // Anchor every prediction at the last known BoC point so tracks fan out past the cutoff.
  const anchorPt = lastKnown
    ? { t: lastKnown.date, pct: lastKnown.pct }
    : (rfAsOf
      ? (() => {
          const snap = (state.bocHistory || []).find((h) => bocHistoryAsof(h) === rfAsOf);
          const pct = snap ? bocHistorySpotPct(snap, tenor) : null;
          return isNum(pct) ? { t: rfAsOf, pct } : null;
        })()
      : null);

  if (vis.production !== false && state.productionShift && isNum(productionShiftSpotPct(tenor))) {
    const bridge = state.productionShift.bridge || {};
    const live = bridge.valet_live_asof || null;
    const base = bridge.rf_asof || rfAsOf;
    const pts = [];
    if (anchorPt) {
      pts.push({ t: anchorPt.t, pct: anchorPt.pct });
    } else if (base) {
      const baseSnap = (state.bocHistory || []).find((h) => bocHistoryAsof(h) === base);
      const basePct = baseSnap ? bocHistorySpotPct(baseSnap, tenor) : null;
      if (isNum(basePct)) pts.push({ t: base, pct: basePct });
    }
    if (live) pts.push({ t: live, pct: productionShiftSpotPct(tenor) });
    if (pts.length) {
      series.push({
        key: 'production',
        label: 'Production Valet shift',
        color: '#5b6b7c',
        dashed: true,
        cutoff: false,
        points: pts,
      });
    }
  }

  const lb = state.lagBootstrap;
  const days = (lb && lb.days) || [];
  const cache = (lb && lb.dayCache) || {};
  LAG_BOOT_UI.forEach((ui) => {
    if (vis[ui.key] === false) return;
    const pts = [];
    // Start at last known BoC so the prediction visually continues past the cutoff.
    if (anchorPt) pts.push({ t: anchorPt.t, pct: anchorPt.pct });
    days.forEach((day) => {
      // Skip days on/before the known cutoff — those are covered by the held BoC series.
      if (rfAsOf && day <= rfAsOf) return;
      const payload = (cache[day] && cache[day][ui.key]) || (day === (lb && lb.selectedDay) ? byMethod[ui.key] : null);
      const pct = lagBootSpotPct(payload, tenor);
      if (isNum(pct)) pts.push({ t: day, pct });
    });
    // Ensure selected day from byMethod is present even if cache race
    if (pts.length <= (anchorPt ? 1 : 0) && byMethod[ui.key]) {
      const pct = lagBootSpotPct(byMethod[ui.key], tenor);
      const day = byMethod[ui.key].valet_asof || (lb && lb.selectedDay);
      if (day && isNum(pct) && !(rfAsOf && day <= rfAsOf)) pts.push({ t: day, pct });
    }
    if (pts.length > (anchorPt ? 1 : 0)) {
      series.push({
        key: ui.key,
        label: `${ui.label} predicted`,
        color: ui.color,
        dashed: false,
        cutoff: false,
        points: pts.sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0)),
      });
    }
  });

  return { series, rfAsOf, axis: 'time' };
}

function buildLagBootMaturitySeries(byMethod, day) {
  const series = [];
  const vis = state.lagBootVisible || {};
  const rfAsOf = lagBootRfAsOf();
  const years = Array.from({ length: 30 }, (_, i) => i + 1);

  if (vis.current !== false) {
    const snap =
      (state.bocHistory || []).find((h) => bocHistoryAsof(h) === rfAsOf) ||
      (state.bocHistory || [])[(state.bocHistory || []).length - 1] ||
      null;
    const pts = years
      .map((y) => ({ year: y, pct: bocHistorySpotPct(snap, y) }))
      .filter((p) => isNum(p.pct));
    if (pts.length) {
      series.push({
        key: 'current',
        label: `Known BoC${rfAsOf ? ` (${fmtDate(rfAsOf)})` : ''}`,
        color: '#6f8696',
        dashed: false,
        cutoff: true,
        points: pts,
      });
    }
  }

  if (vis.production !== false) {
    const pts = years
      .map((y) => ({ year: y, pct: productionShiftSpotPct(y) }))
      .filter((p) => isNum(p.pct));
    if (pts.length) {
      series.push({
        key: 'production',
        label: 'Production Valet shift',
        color: '#5b6b7c',
        dashed: true,
        cutoff: false,
        points: pts,
      });
    }
  }

  LAG_BOOT_UI.forEach((ui) => {
    if (vis[ui.key] === false) return;
    const payload = byMethod[ui.key];
    if (!payload) return;
    const zeros = (payload.predicted_zeros_annual_effective || [])
      .map((r) => ({
        year: Number(r.year),
        pct: isNum(r.zero) ? Number(r.zero) * 100 : null,
      }))
      .filter((r) => isNum(r.year) && isNum(r.pct));
    if (zeros.length) {
      series.push({
        key: ui.key,
        label: `${ui.label} predicted spot`,
        color: ui.color,
        dashed: false,
        cutoff: false,
        points: zeros,
      });
    }
    if (vis[`${ui.key}_fwd`] !== false) {
      const fwds = (payload.bootstrap || [])
        .map((r) => ({
          year: Number(r.year),
          pct: isNum(r.forward_1y) ? Number(r.forward_1y) * 100 : null,
        }))
        .filter((r) => isNum(r.year) && isNum(r.pct));
      if (fwds.length) {
        series.push({
          key: `${ui.key}_fwd`,
          label: `${ui.label} boot fwd`,
          color: ui.color,
          dashed: true,
          cutoff: false,
          points: fwds,
        });
      }
    }
  });

  return { series, rfAsOf, axis: 'maturity', day };
}

function renderLagBootstrapChart(byMethod, day) {
  const host = $('#lagBootChart');
  const chartDesc = $('#lagBootChartDesc');
  if (!host) return;
  setLagBootTip('');

  const view = state.lagBootView || 'time';
  const tenor = state.lagBootTenor || 10;
  const built =
    view === 'maturity'
      ? buildLagBootMaturitySeries(byMethod || {}, day)
      : buildLagBootTimeSeries(byMethod || {}, tenor);
  const series = built.series || [];
  const rfAsOf = built.rfAsOf;

  if (!series.length) {
    chartDesc.textContent =
      'Held BoC cuts off at rf_asof; predicted tracks continue. Hover to name a curve; click legend to toggle.';
    host.innerHTML =
      '<p class="empty">No curve points for the current view / toggles. Load lag_bootstrap artifacts and BoC snaps from the project root.</p>';
    return;
  }

  const moeMethod = state.lagMoeMethod || 'ridge';
  const moeBlock = lagMoeStatsFor(moeMethod);
  if (view === 'maturity') {
    chartDesc.textContent =
      `Maturity view · BoC @ ${fmtDate(rfAsOf) || '—'} vs predictions for Valet ${fmtDate(day) || '—'} · ±P90 MoE band on ${moeMethod}` +
      (moeBlock ? ` (P90|e|≈${Number(moeBlock.p90_abs_curve_bp).toFixed(2)} bp pooled)` : '') +
      ' · hover for SE';
  } else {
    const moeTenor = lagMoeRow(moeMethod, tenor);
    chartDesc.textContent =
      `Time view · ${tenor}y · BoC through ${fmtDate(rfAsOf) || '—'}; predictions fan out` +
      (moeTenor
        ? ` · ${moeMethod} ${tenor}y SE ${Number(moeTenor.se_bp).toFixed(3)} bp · P90|e| ${Number(moeTenor.p90_abs_bp).toFixed(2)} bp`
        : '') +
      ' · hover for SE';
  }

  const allVals = series.flatMap((se) => se.points.map((p) => p.pct)).filter(isNum);
  // Include MoE band extents so y-scale fits
  if (view === 'maturity' && moeBlock) {
    const moeSe = series.find((s) => s.key === moeMethod);
    if (moeSe) {
      moeSe.points.forEach((p) => {
        const row = lagMoeRow(moeMethod, p.year);
        if (row && isNum(row.p90_abs_bp) && isNum(p.pct)) {
          const half = Number(row.p90_abs_bp) / 100; // bp → %
          allVals.push(p.pct + half, p.pct - half);
        }
      });
    }
  }
  if (!allVals.length) {
    host.innerHTML = '<p class="empty">No numeric points to chart.</p>';
    return;
  }

  const W = 760, H = 300;
  const mg = { t: 18, r: 18, b: 48, l: 48 };
  let xMin;
  let xMax;
  let xPos;
  let xTicks;

  if (view === 'maturity') {
    const years = Array.from(
      new Set(series.flatMap((se) => se.points.map((p) => p.year)))
    ).sort((a, b) => a - b);
    if (years.length < 2) {
      host.innerHTML = '<p class="empty">Not enough maturity nodes to chart.</p>';
      return;
    }
    xMin = years[0];
    xMax = years[years.length - 1];
    xPos = (v) => mg.l + ((v - xMin) / (xMax - xMin || 1)) * (W - mg.l - mg.r);
    xTicks = [1, 2, 5, 10, 15, 20, 25, 30].filter((t) => t >= xMin && t <= xMax);
  } else {
    const dates = Array.from(
      new Set(series.flatMap((se) => se.points.map((p) => p.t)))
    ).sort();
    if (dates.length < 1) {
      host.innerHTML = '<p class="empty">Not enough dates to chart.</p>';
      return;
    }
    // Map dates (+ optional rfAsOf) onto a linear index axis
    const axisDates = Array.from(new Set([...dates, rfAsOf].filter(Boolean))).sort();
    const idxOf = (d) => {
      const i = axisDates.indexOf(d);
      return i < 0 ? 0 : i;
    };
    xMin = 0;
    xMax = Math.max(1, axisDates.length - 1);
    xPos = (d) => mg.l + (idxOf(d) / (xMax || 1)) * (W - mg.l - mg.r);
    xTicks = axisDates;
  }

  const yMin = Math.floor((Math.min(...allVals) - 0.05) / 0.25) * 0.25;
  const yMax = Math.ceil((Math.max(...allVals) + 0.05) / 0.25) * 0.25;
  const yPos = (v) => H - mg.b - ((v - yMin) / (yMax - yMin || 1)) * (H - mg.t - mg.b);

  host.innerHTML = '';
  // Keep tip element inside chart wrap
  let tip = $('#lagBootTip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'lagBootTip';
    tip.className = 'tip';
    tip.hidden = true;
    host.appendChild(tip);
  }

  const svg = svgEl('svg', {
    viewBox: `0 0 ${W} ${H}`,
    class: 'chart',
    role: 'img',
    'aria-label': 'Lag-remedy held BoC and predicted curves',
  });
  host.appendChild(svg);

  for (let v = yMin; v <= yMax + 1e-9; v += 0.25) {
    svgEl('line', { x1: mg.l, x2: W - mg.r, y1: yPos(v), y2: yPos(v), class: 'grid' }, svg);
    svgText(svg, mg.l - 8, yPos(v) + 3, v.toFixed(2), { class: 'tick', 'text-anchor': 'end' });
  }

  if (view === 'maturity') {
    for (const t of xTicks) {
      svgEl('line', { x1: xPos(t), x2: xPos(t), y1: mg.t, y2: H - mg.b, class: 'grid' }, svg);
      svgText(svg, xPos(t), H - mg.b + 16, String(t), { class: 'tick', 'text-anchor': 'middle' });
    }
    svgText(svg, (mg.l + W - mg.r) / 2, H - 8, 'Maturity (years)', { class: 'axis-title' });
  } else {
    const axisDates = Array.from(
      new Set(series.flatMap((se) => se.points.map((p) => p.t)).concat(rfAsOf ? [rfAsOf] : []))
    ).sort();
    const labelEvery = Math.max(1, Math.ceil(axisDates.length / 6));
    axisDates.forEach((d, i) => {
      if (i % labelEvery !== 0 && i !== axisDates.length - 1) return;
      svgEl('line', { x1: xPos(d), x2: xPos(d), y1: mg.t, y2: H - mg.b, class: 'grid' }, svg);
      svgText(svg, xPos(d), H - mg.b + 16, fmtDate(d) || d, {
        class: 'tick',
        'text-anchor': 'middle',
      });
    });
    svgText(svg, (mg.l + W - mg.r) / 2, H - 8, 'Valet / BoC date', { class: 'axis-title' });
  }

  // Cutoff marker at rf_asof (time view) or annotation (maturity view)
  if (rfAsOf) {
    if (view === 'time') {
      const cx = xPos(rfAsOf);
      svgEl('line', {
        x1: cx, x2: cx, y1: mg.t, y2: H - mg.b, class: 'cutoff',
      }, svg);
      svgText(svg, cx + 4, mg.t + 10, `BoC data ends ${fmtDate(rfAsOf)}`, {
        class: 'cutoff-label',
      });
    } else {
      svgText(svg, mg.l + 4, mg.t + 10, `Held BoC as-of ${fmtDate(rfAsOf)} (no official points beyond this date in time view)`, {
        class: 'cutoff-label',
      });
    }
  }

  // ±P90|e| MoE band around selected method (maturity view)
  if (view === 'maturity' && moeBlock) {
    const moeSe = series.find((s) => s.key === moeMethod);
    if (moeSe && moeSe.points.length >= 2) {
      const upper = [];
      const lower = [];
      for (const p of moeSe.points) {
        const row = lagMoeRow(moeMethod, p.year);
        if (!row || !isNum(row.p90_abs_bp) || !isNum(p.pct)) continue;
        const half = Number(row.p90_abs_bp) / 100; // bp → %
        const px = xPos(p.year);
        upper.push([px, yPos(p.pct + half)]);
        lower.push([px, yPos(p.pct - half)]);
      }
      if (upper.length >= 2) {
        let d = `M${upper[0][0].toFixed(1)},${upper[0][1].toFixed(1)}`;
        for (let i = 1; i < upper.length; i++) {
          d += `L${upper[i][0].toFixed(1)},${upper[i][1].toFixed(1)}`;
        }
        for (let i = lower.length - 1; i >= 0; i--) {
          d += `L${lower[i][0].toFixed(1)},${lower[i][1].toFixed(1)}`;
        }
        d += 'Z';
        svgEl('path', { d, class: 'moe-band', 'aria-hidden': 'true' }, svg);
      }
    }
  }

  const hitTargets = []; // {x,y,r, series, point}

  for (const se of series) {
    let path = '';
    let pen = false;
    for (const p of se.points) {
      const px = view === 'maturity' ? xPos(p.year) : xPos(p.t);
      const py = yPos(p.pct);
      path += `${pen ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)}`;
      pen = true;
      hitTargets.push({
        x: px,
        y: py,
        r: 10,
        seriesKey: se.key,
        seriesLabel: se.label,
        color: se.color,
        point: p,
        view,
      });
    }
    const attrs = {
      d: path,
      fill: 'none',
      stroke: se.color,
      'stroke-width': se.dashed ? 1.5 : (se.key === 'current' ? 2.6 : 2),
      'stroke-linejoin': 'round',
      'stroke-linecap': 'round',
      class: `line lb-${se.key.replace(/_/g, '-')}`,
      'data-series': se.key,
      'data-label': se.label,
    };
    if (se.dashed) attrs['stroke-dasharray'] = '5 4';
    // Wider invisible stroke for easier hover
    svgEl('path', {
      d: path,
      fill: 'none',
      stroke: 'transparent',
      'stroke-width': 12,
      'stroke-linejoin': 'round',
      'stroke-linecap': 'round',
      class: 'hit',
      'data-series': se.key,
      'data-label': se.label,
    }, svg);
    svgEl('path', attrs, svg);

    const markerPts =
      view === 'maturity'
        ? se.points.filter((pt) => [1, 2, 5, 10, 20, 30].includes(pt.year))
        : se.points;
    for (const p of markerPts) {
      const px = view === 'maturity' ? xPos(p.year) : xPos(p.t);
      const py = yPos(p.pct);
      svgEl('circle', {
        cx: px,
        cy: py,
        r: se.key === 'current' ? 3 : 2.4,
        fill: se.dashed ? '#fff' : se.color,
        stroke: se.color,
        'stroke-width': 1.2,
        class: `dot lb-${se.key.replace(/_/g, '-')}`,
        'data-series': se.key,
        'data-label': se.label,
      }, svg);
    }
  }

  function tipForTarget(t) {
    const when =
      view === 'maturity'
        ? `${t.point.year}y`
        : (fmtDate(t.point.t) || t.point.t);
    const extra =
      view === 'time'
        ? `${tenor}y tenor`
        : (t.seriesKey === 'current' ? 'held BoC (cuts off after rf_asof in time view)' : 'predicted');
    let moeLine = '';
    const moeYear = view === 'maturity' ? t.point.year : tenor;
    const moeKey = t.seriesKey === 'current' ? moeMethod : t.seriesKey;
    const row = lagMoeRow(moeKey, moeYear);
    if (row && isNum(row.se_bp) && t.seriesKey !== 'current') {
      moeLine =
        `<div class="tip-meta">SE ${Number(row.se_bp).toFixed(3)} bp · P90|e| ${Number(row.p90_abs_bp).toFixed(2)} bp` +
        (isNum(row.rmse_bp) ? ` · RMSE ${Number(row.rmse_bp).toFixed(2)} bp` : '') +
        `</div>`;
    } else if (view === 'time' && row && isNum(row.se_bp) && t.seriesKey === moeMethod) {
      moeLine =
        `<div class="tip-meta">MoE ${moeMethod}: SE ${Number(row.se_bp).toFixed(3)} bp · P90|e| ${Number(row.p90_abs_bp).toFixed(2)} bp</div>`;
    }
    return (
      `<div class="tip-name" style="color:${t.color}">${esc(t.seriesLabel)}</div>` +
      `<div class="tip-meta">${esc(when)} · ${Number(t.point.pct).toFixed(3)}%` +
      (extra ? ` · ${esc(extra)}` : '') +
      `</div>` +
      moeLine
    );
  }

  function nearestTarget(clientX, clientY) {
    const rect = svg.getBoundingClientRect();
    const sx = ((clientX - rect.left) / rect.width) * W;
    const sy = ((clientY - rect.top) / rect.height) * H;
    let best = null;
    let bestDist = Infinity;
    for (const t of hitTargets) {
      const d = (t.x - sx) ** 2 + (t.y - sy) ** 2;
      if (d < bestDist && d <= t.r * t.r * 4) {
        bestDist = d;
        best = t;
      }
    }
    return best;
  }

  svg.addEventListener('mousemove', (ev) => {
    // Prefer series from hit path / dot under cursor
    const el = document.elementFromPoint(ev.clientX, ev.clientY);
    let label = el && el.getAttribute && el.getAttribute('data-label');
    let key = el && el.getAttribute && el.getAttribute('data-series');
    const near = nearestTarget(ev.clientX, ev.clientY);
    if (near) {
      setLagBootTip(tipForTarget(near), ev.clientX, ev.clientY);
      return;
    }
    if (label) {
      const se = series.find((s) => s.key === key) || { label, color: '#15263a' };
      setLagBootTip(
        `<div class="tip-name" style="color:${se.color || '#15263a'}">${esc(label)}</div>` +
          `<div class="tip-meta">Hover a point for date / tenor detail</div>`,
        ev.clientX,
        ev.clientY
      );
      return;
    }
    setLagBootTip('');
  });
  svg.addEventListener('mouseleave', () => setLagBootTip(''));
}

function renderHeader() {
  const s = state.snap;
  const m = s.meta || {};
  const illus = !!s.is_illustrative;
  const bridge = m.lag_bridge || {};

  $('#illustrativeBanner').hidden = !illus;
  $('#bannerSnapshotId').textContent = s.snapshot_id || '';

  $('#mObs').textContent = fmtDate(m.observation_date);
  $('#mMarket').textContent = `${fmtDate(m.latest_market_date)}${m.market_session ? ` · ${m.market_session}` : ''}`;
  $('#mSourceLabel').textContent = m.source_label ? `Source · ${m.source_label}` : 'Source';
  $('#mSource').textContent = m.source || '—';

  const rfEl = $('#mRf');
  if (rfEl) {
    const lagPart = isNum(m.rf_publish_lag_days) ? ` · lag ${m.rf_publish_lag_days}d` : '';
    const bridgePart = bridge.applied ? ' · Valet bridge ON' : '';
    rfEl.textContent = m.rf_as_of
      ? `${fmtDate(m.rf_as_of)}${lagPart}${bridgePart}`
      : '—';
    rfEl.className = bridge.applied ? 'dot-status ok' : '';
  }
  const premEl = $('#mPremium');
  if (premEl) {
    premEl.textContent = m.premium_policy
      ? `${m.premium_policy}${m.premium_as_of ? ` · ${fmtDate(m.premium_as_of)}` : ''}`
      : '—';
  }

  $('#mUpdate').textContent = fmtDateTime(m.last_successful_update, m.timezone_label);

  const avail = m.data_availability || 'UNKNOWN';
  const availEl = $('#mAvail');
  availEl.className = `dot-status ${avail === 'CURRENT' ? 'ok' : 'warn'}`;
  let availTxt = avail;
  if (avail === 'LAGGED' && m.rf_as_of) {
    // Prefer obs−RF gap (product age). Never present rf_publish_lag_days as that gap.
    const gap = m.obs_rf_calendar_gap_days;
    const gapPart = isNum(gap) ? ` · obs−RF ${gap}d` : '';
    availTxt = `LAGGED · RF ${fmtDate(m.rf_as_of)}${gapPart}`;
  }
  availEl.textContent = `${availTxt}${illus ? ' · demo' : ''}`;

  $('#selObs').innerHTML = `<option>${esc(fmtDate(m.observation_date))}</option>`;
  const thr = (s.metrics_computed || {}).primary_threshold_bp;
  const thrNote = isNum(thr) ? ` · trigger T ≥ ${thr} bp` : ' · trigger T ≥ 25 bp';
  $('#toolbarNote').textContent =
    `${m.currency || ''} ${m.yield_type || ''} yields · ${s.maturities.length} display nodes (T uses years 1–30) · 1 bp = 0.01%${thrNote}`.trim();

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

  // Prefer weighted T (primary) when pipeline provides it; else equal-weight mean.
  const parallelShow = isNum(d.weightedAbs) ? d.weightedAbs : d.meanAbs;
  $('#kpiParallel').innerHTML = `${fmtAbsBp(parallelShow, 1)}${bpUnit}`;
  if (isNum(d.weightedAbs)) {
    const sPart = isNum(d.weightedSigned) ? ` · S ${fmtBp(d.weightedSigned, 1)} bp` : '';
    $('#kpiParallelFoot').textContent =
      `Primary measure · years 1–30${sPart}`;
  } else {
    $('#kpiParallelFoot').textContent = d.metricsFromPipeline
      ? `Mean |implied − pricing| from metrics_computed · ${d.nValid} nodes`
      : `Mean |implied − pricing| across ${d.nValid} nodes; not a fitted parallel shift.`;
  }

  if (isNum(d.maxBucketAbs)) {
    $('#kpiLargest').innerHTML = `${fmtAbsBp(d.maxBucketAbs)}${bpUnit}`;
    $('#kpiLargestLine').textContent = d.maxBucketLabel
      ? `Largest bucket mean |Δ| · ${d.maxBucketLabel}y`
      : 'Largest bucket mean |Δ| (from metrics_computed)';
  } else if (isNum(d.maxAbs) && d.maxIdx >= 0) {
    $('#kpiLargest').innerHTML = `${fmtAbsBp(d.maxAbs)}${bpUnit}`;
    $('#kpiLargestLine').textContent = `${tenorLong(s.maturities[d.maxIdx])} maturity · largest |implied − pricing|`;
  } else if (isNum(d.maxAbs)) {
    $('#kpiLargest').innerHTML = `${fmtAbsBp(d.maxAbs)}${bpUnit}`;
    $('#kpiLargestLine').textContent = 'Largest |implied − pricing| (from metrics_computed)';
  } else {
    $('#kpiLargest').innerHTML = `—${bpUnit}`;
    $('#kpiLargestLine').textContent = 'No complete maturity nodes';
  }

  // Show signed twist for direction; magnitude prefers metrics_computed abs when present.
  const twistShow = isNum(d.twist) ? d.twist : d.twistAbs;
  $('#kpiTwist').innerHTML = `${fmtBp(twistShow, 1)}${bpUnit}`;
  $('#kpiTwistLine').textContent = isNum(d.twist)
    ? `2s10s ${d.twist >= 0 ? 'steepening' : 'flattening'} · ${d.slopeP.toFixed(0)} → ${d.slopeI.toFixed(0)} bp`
    : (isNum(d.twistAbs) ? `|2s10s| from metrics_computed` : '2y or 10y node unavailable');

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

    // Tooltip only while hovering or after an explicit selection click.
    if (state.hover == null && state.selected == null) {
      tip.hidden = true;
      return;
    }
    const row = (label, v) => `<div class="tt-row">${esc(label)}<b>${fmtPct(v)}</b></div>`;
    const isSel = m === state.selected;
    tip.innerHTML =
      `<div class="tt-head"><b>${tenorLong(m)} maturity</b><span>${isSel ? 'Selected' : 'Click to select'}</span></div>` +
      SERIES.map((se) => row(s.curves[se.key].label || se.label, s.curves[se.key].yields[i])).join('') +
      `<div class="tt-row total">Implied − pricing (display)<b>${fmtBp(state.d.change[i])} bp</b></div>` +
      `<div class="tt-row">Canada par − col J (basis gap)<b>${fmtBp(state.d.marketDelta[i])} bp</b></div>`;

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

  $('#barDesc').textContent = `Implied − Pricing (display nodes)${s.is_illustrative ? ' · illustrative' : ''}`;
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
    const isSigned = t.id === 'signed' || t.metric === 'weighted_signed_change_bp';
    const st = isSigned
      ? { label: 'Direction only', cls: '' }
      : (TRIGGER_STATUS[t.status] || { label: t.status || '—', cls: '' });
    const threshold = isSigned
      ? 'No threshold'
      : (isNum(t.threshold_bp) ? `${t.threshold_bp} bp` : 'To be calibrated');
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

/** Prefer weighted T for history chart; fall back to signed equal-weight mean. */
function historyValue(p) {
  if (isNum(p.weighted_abs_bp)) return p.weighted_abs_bp;
  if (isNum(p.mean_shift_bp)) return p.mean_shift_bp;
  return null;
}

/**
 * Trust pipeline ``flagged`` first (single ownership with snapshot_history).
 * Recompute from T only for legacy placeholders that lack ``flagged``.
 */
function historyMarked(p, thr) {
  if (typeof p.flagged === 'boolean') return p.flagged;
  if (isNum(p.weighted_abs_bp) && isNum(thr)) return p.weighted_abs_bp >= thr;
  return false;
}

function renderHistory() {
  const s = state.snap;
  const h = s.history || [];
  const host = $('#historyChart');
  host.innerHTML = '';

  if (s.is_illustrative) {
    $('#historyDescSuffix').textContent = ' · all history is synthetic';
  } else if (s.meta && s.meta.curve_mode === 'rebuilt') {
    $('#historyDescSuffix').textContent =
      ' · archive Fiera MoM (live KPI T uses rebuilt implied — may differ)';
  } else if (s.notes && s.notes.history_reading) {
    $('#historyDescSuffix').textContent = ' · archived Fiera only';
  } else if (s.data_quality && s.data_quality.history_basis === 'archive_consecutive_column_j') {
    $('#historyDescSuffix').textContent = ' · archived Fiera only';
  } else {
    $('#historyDescSuffix').textContent = '';
  }
  $('#historyPeriod').textContent = h.length
    ? `${fmtShortDate(h[0].date)}–${fmtDate(h[h.length - 1].date)} · ${h.length} ${s.is_illustrative ? 'illustrative ' : ''}observations`
    : '';

  const thr = primaryThresholdBp(s);
  const marked = h.filter((p) => historyMarked(p, thr));
  $('#eventsCount').textContent = `${marked.length} / ${h.length}`;
  $('#eventsList').innerHTML = marked
    .map((p) => {
      const v = historyValue(p);
      // Prefer pipeline note (already says "archive marker…"); avoid duplicating the phrase.
      return `<li>${esc(fmtShortDate(p.date))}: ${esc(fmtAbsBp(v, 1))} bp${p.note ? ` · ${esc(p.note)}` : ''}</li>`;
    })
    .join('');

  const pts = h.filter((p) => isNum(historyValue(p)));
  if (!pts.length) {
    host.innerHTML = '<p class="empty">No historical observations in this snapshot.</p>';
    return;
  }

  const W = 900, H = 250;
  const mg = { t: 22, r: 28, b: 34, l: 48 };
  const vals = pts.map(historyValue);
  const ext = Math.max(...vals.map((v) => Math.abs(v)), thr, 1);
  const step = niceStep(ext, 3);
  // T is absolute → plot from 0 upward (plus room for threshold line).
  const yMax = Math.ceil(Math.max(ext, thr) / step) * step;
  const x = (k) => (pts.length === 1 ? (mg.l + W - mg.r) / 2 : mg.l + (k / (pts.length - 1)) * (W - mg.l - mg.r));
  const y = (v) => mg.t + ((yMax - v) / yMax) * (H - mg.t - mg.b);

  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img', 'aria-label': 'Historical weighted T chart' });

  for (let v = 0; v <= yMax + 1e-9; v += step) {
    svgEl('line', { x1: mg.l, x2: W - mg.r, y1: y(v), y2: y(v), class: v === 0 ? 'zero' : 'grid' }, svg);
    svgText(svg, mg.l - 8, y(v) + 3, fmtAbsBp(v), { class: 'tick', 'text-anchor': 'end' });
  }

  // Threshold line from pipeline metrics_computed.primary_threshold_bp.
  svgEl('line', {
    x1: mg.l, x2: W - mg.r, y1: y(thr), y2: y(thr),
    class: 'zero', 'stroke-dasharray': '4 3',
  }, svg);
  svgText(svg, W - mg.r, y(thr) - 6, `T = ${thr}`, { class: 'tick', 'text-anchor': 'end' });

  svgEl('path', {
    d: pts.map((p, k) => `${k ? 'L' : 'M'}${x(k).toFixed(1)},${y(historyValue(p)).toFixed(1)}`).join(''),
    class: 'h-line',
  }, svg);

  pts.forEach((p, k) => {
    const v = historyValue(p);
    const flag = historyMarked(p, thr);
    const last = k === pts.length - 1;
    const dot = svgEl('circle', { cx: x(k), cy: y(v), r: flag ? 5 : 3, class: `h-dot${flag ? ' flag' : ''}` }, svg);
    svgEl('title', {}, dot).textContent = `${fmtDate(p.date)}: T ${fmtAbsBp(v, 1)} bp${p.note ? ` · ${p.note}` : ''}`;
    if (flag || last) {
      svgText(svg, x(k), y(v) - 10, fmtAbsBp(v, 1), { class: `h-label${flag ? ' flag' : ''}` });
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

  const matTrigger = (s.triggers || []).find(
    (t) => t.metric === 'max_bucket_abs_change_bp' || t.metric === 'max_abs_change_bp'
  );
  const matNote = !matTrigger || matTrigger.status === 'NOT_EVALUATED'
    ? 'No bucket diagnostic has been evaluated.'
    : `Bucket diagnostic: ${(TRIGGER_STATUS[matTrigger.status] || {}).label || matTrigger.status}`;
  $('#selStrip').innerHTML = `
    <div><span class="k">Selected maturity</span><div class="big">${si >= 0 ? `${M[si]} years` : 'Click a node'}</div></div>
    <div><span class="k">${esc(s.curves.implied.label || 'Updated / Implied Curve')}</span><div class="big mono">${si >= 0 ? fmtPct(I[si]) : '—'}</div></div>
    <div><span class="k">Implied − pricing (display)</span><div class="big mono teal">${si >= 0 ? `${fmtBp(d.change[si])} bp` : '—'}</div></div>
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

  const maxTxt = isNum(d.maxAbs)
    ? `max |implied − pricing| ${Math.abs(d.maxAbs).toFixed(0)} bp${d.maxIdx >= 0 ? ` at ${tenor(M[d.maxIdx])}` : ''}`
    : 'max |Δ| —';
  const meanAbsTxt = isNum(d.meanAbs) ? `${fmtAbsBp(d.meanAbs, 1)} bp` : '—';
  const tTxt = isNum(d.weightedAbs) ? ` · primary T ${fmtAbsBp(d.weightedAbs, 1)} bp (years 1–30)` : '';
  $('#matFoot').textContent =
    `${M.length} display nodes · ${d.missing.length} missing · mean |implied − pricing| ${meanAbsTxt} · ${maxTxt}${tTxt}`;
  $('#matFine').textContent = s.is_illustrative
    ? 'ILLUSTRATIVE DATA · Not actual TVFI results. Completeness and finite-value checks describe only this placeholder dataset; they are not production validation. All maturities remain unassessed until rules are calibrated and validated.'
    : 'T uses annual years 1–30; this table shows the 9 display nodes.';

  // Formula cards — show the arithmetic with this snapshot's numbers.
  const i2 = M.indexOf(2), i10 = M.indexOf(10);
  $('#fParallel').textContent = isNum(d.weightedAbs)
    ? `T = Σ w_t · |Δr_t| (years 1–30) = ${fmtAbsBp(d.weightedAbs, 1)} bp · display mean |Δ| = ${fmtAbsBp(d.meanAbs, 1)} bp`
    : `Σ|implied − pricing| / ${d.nValid} = ${fmtAbsBp(d.meanAbs, 1)} bp`;
  $('#fTwist').textContent = isNum(d.twist)
    ? `[(${I[i10].toFixed(2)} − ${I[i2].toFixed(2)}) − (${P[i10].toFixed(2)} − ${P[i2].toFixed(2)})] × 100 = ${fmtBp(d.twist, 1)} bp`
    : '[(I10 − I2) − (P10 − P2)] × 100 = —';
  $('#fTwistDesc').textContent = isNum(d.twist)
    ? `The 2s10s slope ${d.twist >= 0 ? 'increases' : 'decreases'} from ${d.slopeP.toFixed(0)} to ${d.slopeI.toFixed(0)} bp (implied vs pricing). A ${d.twist >= 0 ? 'positive' : 'negative'} slope change describes ${d.twist >= 0 ? 'steepening' : 'flattening'}, not a validated trigger outcome.`
    : 'Requires both 2-year and 10-year nodes.';
  $('#fImplied').textContent = s.curves.implied.construction || `Mean implied − current = ${fmtBp(d.meanImplied, 1)} bp`;
  $('#fImpliedDesc').textContent = s.curves.implied.construction_note
    || `Canada par − column J mean gap = ${fmtBp(d.meanMarket, 1)} bp · basis difference, not a market move.`;
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

async function exportLagBootstrapXlsx() {
  const url = CONFIG.lagBootstrapXlsxUrl;
  try {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const a = document.createElement('a');
    const obj = URL.createObjectURL(blob);
    a.href = obj;
    a.download = 'lag_bootstrap_curves.xlsx';
    a.click();
    setTimeout(() => URL.revokeObjectURL(obj), 0);
    toast('Downloaded lag_bootstrap_curves.xlsx');
  } catch (err) {
    toast(
      'Excel export missing — run: python3 -m pipeline.lag_bridge_bootstrap --xlsx-only',
      true
    );
  }
}

function openHistory() {
  const s = state.snap;
  const thr = primaryThresholdBp(s);
  $('#historyBody').innerHTML = (s.history || []).map((p) => `
    <tr>
      <td>${esc(fmtDate(p.date))}</td>
      <td>${esc(fmtAbsBp(historyValue(p), 1))}</td>
      <td>${historyMarked(p, thr) ? 'Yes' : '—'}</td>
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
  const btnLagXlsx = $('#btnLagBootXlsx');
  if (btnLagXlsx) btnLagXlsx.addEventListener('click', exportLagBootstrapXlsx);
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

  const lagDaySel = $('#selLagBootDay');
  if (lagDaySel) {
    lagDaySel.addEventListener('change', async (e) => {
      const day = e.target.value;
      if (!day || !state.lagBootstrap) return;
      state.lagBootstrap.selectedDay = day;
      const byMethod = await loadLagBootstrapDay(day);
      if (byMethod) state.lagBootstrap.byMethod = byMethod;
      renderLagBootstrap();
    });
  }

  const lagMoeSel = $('#selLagMoeMethod');
  if (lagMoeSel) {
    lagMoeSel.addEventListener('change', (e) => {
      state.lagMoeMethod = e.target.value === 'pca_ridge' ? 'pca_ridge' : 'ridge';
      renderLagMoePanel();
      renderLagBootstrapChart(
        (state.lagBootstrap && state.lagBootstrap.byMethod) || {},
        state.lagBootstrap && state.lagBootstrap.selectedDay
      );
    });
  }

  const lagViewSel = $('#selLagBootView');
  if (lagViewSel) {
    lagViewSel.addEventListener('change', (e) => {
      state.lagBootView = e.target.value === 'maturity' ? 'maturity' : 'time';
      const tenorWrap = $('#lagBootTenorWrap');
      if (tenorWrap) tenorWrap.hidden = state.lagBootView !== 'time';
      renderLagBootstrapChart(
        (state.lagBootstrap && state.lagBootstrap.byMethod) || {},
        state.lagBootstrap && state.lagBootstrap.selectedDay
      );
    });
  }

  const lagTenorSel = $('#selLagBootTenor');
  if (lagTenorSel) {
    lagTenorSel.addEventListener('change', (e) => {
      const y = Number(e.target.value);
      state.lagBootTenor = Number.isFinite(y) ? y : 10;
      if (state.lagBootView === 'time') {
        renderLagBootstrapChart(
          (state.lagBootstrap && state.lagBootstrap.byMethod) || {},
          state.lagBootstrap && state.lagBootstrap.selectedDay
        );
      }
    });
  }

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
