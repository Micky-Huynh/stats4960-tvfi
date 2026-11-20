# Memo: Ridge / PCA lag bridge (Valet → BoC zeros)

**To:** TVFI / Group 5 project file  
**From:** STATS 4960 Group 5  
**Date:** 2026-11-20  
**Status:** **Experimental statistical nowcast** — compare to keyed-shift bridge; not yet default  
**Code:** `pipeline/lag_bridge_mlr.py`

---

## 1. Why

Keyed Valet shift (`valet_keyed_shift_v1`) assumes ΔValet ≈ ΔBoC zero at each tenor (interpolated). A **learned** map can do better when loadings differ by maturity.

Project need: predict dense RF during BoC’s ~2-week publish lag using **live** Valet benchmarks.

---

## 2. Methods

| Method | Idea |
|--------|------|
| **Ridge MLR** | Multi-output Ridge: Valet (2/3/5/7/10/30) → BoC annual-effective zeros 1…30. Features = levels, or levels + Δ vs prior. |
| **PCA + Ridge** | PCA (k=3) on historical BoC curves (level/slope/curvature-like); Ridge maps Valet → PC scores; reconstruct zeros. |

Both train on overlapping history where a BoC observation date has a Valet print on/before that date. Walk-forward back-test vs **hold last BoC**.

---

## 3. Run

```bash
cd /Users/mickle/Desktop/STATS4960/TVFI
python3 -m pipeline.lag_bridge_mlr --train --backtest --predict
python3 -m pipeline.lag_bridge_mlr --method ridge --feature-mode levels_delta --predict
python3 -m pipeline.lag_bridge_mlr --method pca --n-components 3 --predict
```

Artifacts:

- Models: `data/models/lag_bridge_{ridge|pca}_{feature_mode}.pkl`
- Results: `data/curves/lag_bridge_mlr_*_results.json`

---

## 4. Relation to production path

| Layer | Role |
|-------|------|
| Primary RF | Still BoC zeros at `rf_asof` |
| Default lag bridge today | Keyed Valet **shift** (`--rebuilt`) |
| This module | Statistical alternative / horse-race |
| Fiera H | Still **hold** between pubs |

Wire into `--rebuilt` only after back-test beats hold + shift on TVFI history and Nathan signs off.

---

## 5. Caveats

- Valet pars ≠ BoC continuous zeros — model learns an empirical map, not an identity.  
- Short sample / regime change → re-train; report walk-forward RMSE in bp.  
- PCA with k=3 is a shape prior; if ridge already fits well, PCA is mainly interpretability.  
- Still does **not** invent Fiera monthly H / full illiquid col J — only the RF piece.
