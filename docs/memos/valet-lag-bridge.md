# Memo: Valet lag bridge (BoC zeros + live benchmark shift)

**To:** TVFI / Group 5 project file  
**From:** STATS 4960 Group 5  
**Date:** 2026-11-20  
**Status:** **Production default during lag** for `--rebuilt` (disable with `--no-lag-bridge`)  
**Code:** `pipeline/valet_intake.py`, `pipeline/lag_bridge.py`

---

## 1. Problem

BoC zero-coupon CSV is the locked **primary** RF (construction-ready, dense 0.25–30y grid) but carries a **~2-week publication lag**. TVFI wants a **live figure during the lag** for the monitoring / col-J path.

Bootstrapping Fiera Canada par does **not** solve this — that input is monthly and recovers construction col E, not a fresher daily curve.

---

## 2. Decision

| Layer | Role |
|-------|------|
| **Primary** | Hold last published **BoC zeros** (`rf_asof`) — keep official shape |
| **Lag bridge** | Shift annual RF spots by **Valet benchmark Δ** since `rf_asof` |
| **Not** | Replacing BoC with a sparse Valet-only curve, or inventing zeros from Fiera monthlies |

Valet group (free, keyless, business-daily ~09:30–10:00 ET):

```text
GET .../valet/observations/group/bond_yields_benchmark/json?recent=N
```

Series used: 2y / 3y / 5y / 7y / 10y / Long (→ mapped to **30y**). RRB ignored.

---

## 3. Method (`valet_keyed_shift_v1`)

1. Load BoC snapshot → annual-effective zeros 1…30.  
2. Pull Valet history; take **base** = observation on/before `rf_asof`, **live** = latest.  
3. If `publish_lag_days >= 1` and Valet live date `> rf_asof`:  
   - Δ(t) = live_yield(t) − base_yield(t) at anchors 2,3,5,7,10,30  
   - Interpolate Δ piecewise-linear across years 1…30 (flat outside anchors)  
   - `z'_y = z_y + Δ_y` (additive on annual-effective spots)  
4. Feed `z'` into `curve_builder` with held H + static θ → col J.  
5. Soft-fail: if Valet missing, keep unshifted BoC (bridge `applied=false`).

This preserves BoC shape and only moves the curve by observed market drift at liquid benchmarks.

---

## 4. Defaults / knobs

| Command | Behavior |
|---------|----------|
| `python3 -m pipeline.build_monitor_snapshot --rebuilt` | Bridge **ON** when lagged |
| `--no-lag-bridge` | Hold BoC only (old behavior) |
| `--no-fetch-valet` | Use cached `data/risk_free/valet/benchmarks_latest.json` |
| `python3 -m pipeline.valet_intake` | Refresh Valet cache |
| `python3 -m pipeline.lag_bridge` | Diagnose shift without rebuilding J |

Snapshot / construction record carry `meta.lag_bridge` (`applied`, anchor Δ bp, Valet dates).

---

## 5. Relation to other decisions

- **One primary RF** (Sam): still BoC zeros. Valet is the lag **overlay**, not a second primary shop.  
- **IoA par bootstrap** (`pipeline/bootstrap.py`): pedagogy / Fiera col-E check — **not** the lag fill.  
- **Partner review:** confirm this bridge is ops-acceptable for live monitoring during lag.

---

## 6. Caveats

- Sparse anchors → interpolated shifts between 10y and 30y are coarse.  
- Valet pars ≠ BoC continuous zeros; we shift the zero curve by **par benchmark Δ**, which is an approximation.  
- Long benchmark → 30y mapping is a modeling choice.  
- Re-evaluate if BoC ever publishes zeros with shorter lag.
