"""C4 - fusion of ERA5-Land and Sentinel-1 SWI anomalies, evaluated leave-one-year-out against ISMN Condom 20-30 cm.

Why fusion could help: ERA5-Land (9 km model, ERA5 precipitation) and S-1 SWI (50 m radar at the station) have
physically different error sources (forcing/representativeness vs speckle/vegetation/roughness). If errors are
independent, a weighted mean has lower error variance than either input.

Weights
  * equal: mean of the two z-scores, re-standardised.
  * triple collocation (TC): needs a THIRD source whose errors are independent of both inputs AND that is not the
    evaluation target. ISMN Condom cannot be the third source: weights would then be fitted to the target
    (information leak; the 'skill' would be partly in-sample). We use the neighbouring SMOSMANIA station
    PeyrusseGrande (35 km, 20-30 cm; independent sensor, R=0.54 with Condom). Caveat: TC then defines 'truth' as
    the signal COMMON to the 9 km cell and a point 35 km away (regional signal); local (Condom-only) signal that
    S-1 sees is counted as S-1 error, so TC weights are conservative for S-1.
  * For each held-out year: SWI T chosen on the 8 training years (max R vs Condom, as in C3), predictor climatology
    and TC weights from training years only.
Also: ETC diagnostic with Condom as third member (NOT used for weights) -> correlation of each source with the
unknown truth, including the point sensor's own representativeness error.
Outputs: out/c4_fusion_loyo.csv, out/c4_tc_weights.csv, out/c4_etc_diagnostic.csv, out/c4_cv_series.csv
"""
import numpy as np
import pandas as pd

from common import (COMMON, OUT, YEARS, diff_r_ci, era5_full, era5_layers, ismn_ref, pair, r_ci, s1_obs, swi,
                    zclim, zclim_years)

e = era5_full().loc[COMMON[0]:COMMON[1]]
lay = era5_layers(e)
z_ins = zclim(ismn_ref())                      # evaluation target (fixed reference definition)
nb = ismn_ref("PeyrusseGrande")
s1 = s1_obs("sm_s1")
TS = [5, 10, 15, 20, 30, 40]
swis = {T: swi(s1, T).loc[COMMON[0]:COMMON[1]] for T in TS}


def tc(x, y, z):
    """Covariance-notation TC (McColl et al. 2014). Returns signal sensitivity a_i (var(T)=1), error var, SNR,
    and R with truth for x, y, z."""
    d = pair(x, y, z).to_numpy()
    Q = np.cov(d.T)
    a2 = np.array([Q[0, 1] * Q[0, 2] / Q[1, 2], Q[0, 1] * Q[1, 2] / Q[0, 2], Q[0, 2] * Q[1, 2] / Q[0, 1]])
    err = np.diag(Q) - a2
    return {"a": np.sqrt(np.clip(a2, 1e-9, None)), "err": err, "snr": a2 / np.clip(err, 1e-9, None),
            "R_truth": np.sqrt(np.clip(a2 / np.diag(Q), 0, 1)), "n": len(d)}


def held(series_by_year):
    return pd.concat(series_by_year).sort_index()


out = {k: [] for k in ("E_RZ", "E_L2", "S", "EQ_RZ_S", "TC_RZ_S", "EQ_L2_S", "TC_L2_S")}
wrows = []
for yv in YEARS:
    tr = [y for y in YEARS if y != yv]
    in_tr = lambda s: s[s.index.year.isin(tr)]  # noqa: E731
    in_te = lambda s: s[s.index.year == yv]     # noqa: E731
    # SWI T chosen on training years
    best = max(TS, key=lambda T: (lambda p: p.iloc[:, 0].corr(p.iloc[:, 1]))(in_tr(pair(zclim_years(swis[T], tr), z_ins))))
    zS = zclim_years(swis[best], tr)
    zE = {"RZ": zclim_years(lay["RZ_0_100"], tr), "L2": zclim_years(lay["L2_7_28"], tr)}
    zN = zclim_years(nb, tr)
    out["E_RZ"].append(in_te(zE["RZ"])); out["E_L2"].append(in_te(zE["L2"])); out["S"].append(in_te(zS))
    for k in ("RZ", "L2"):
        # equal weights: mean of z, re-standardised on training years
        f_eq = (zE[k] + zS.reindex(zE[k].index)).dropna() / 2.0
        out[f"EQ_{k}_S"].append(in_te(zclim_years(f_eq, tr)))
        # TC weights from training years (third source = neighbouring station)
        t = tc(in_tr(zE[k]), in_tr(zS), in_tr(zN))
        w = t["snr"][:2] / t["snr"][:2].sum()
        f_tc = (w[0] * zE[k] / t["a"][0] + w[1] * zS.reindex(zE[k].index) / t["a"][1]).dropna()
        out[f"TC_{k}_S"].append(in_te(zclim_years(f_tc, tr)))
        wrows.append({"held_out": yv, "era5": k, "T_swi": best, "w_era5": w[0], "w_s1": w[1],
                      "R_truth_era5": t["R_truth"][0], "R_truth_s1": t["R_truth"][1], "R_truth_neighbour": t["R_truth"][2],
                      "n_tc": t["n"]})
cv = pd.DataFrame({k: held(v) for k, v in out.items()})
cv.to_csv(f"{OUT}/c4_cv_series.csv")
W = pd.DataFrame(wrows)
W.to_csv(f"{OUT}/c4_tc_weights.csv", index=False)
print(W.round(3).to_string(index=False))

rows = []
common_days = pair(*[cv[c] for c in cv.columns], z_ins).index
for k in cv.columns:
    x = cv[k].reindex(common_days)
    r, lo, hi, n = r_ci(x, z_ins)
    ref = "E_L2" if "L2" in k else "E_RZ"
    d = diff_r_ci(x, cv[ref].reindex(common_days), z_ins) if k != ref else (0, 0, 0, n, np.nan)
    p = pair(x, cv[ref].reindex(common_days), z_ins, names=["x", "b", "y"])
    yr = p.groupby(p.index.year).apply(lambda g: g["x"].corr(g["y"]) - g["b"].corr(g["y"]))
    rows.append({"variant": k, "R": r, "ci_lo": lo, "ci_hi": hi, "n": n, "vs": ref, "dR": d[0], "dR_lo": d[1],
                 "dR_hi": d[2], "years_better": int((yr > 0).sum()), "years": int(yr.notna().sum())})
res = pd.DataFrame(rows)
res.to_csv(f"{OUT}/c4_fusion_loyo.csv", index=False)
print(res.round(3).to_string(index=False))

# ETC diagnostic (in-sample, full period): Condom as third member, NOT used for weights
diag = []
for lab, x in (("ERA5_RZ", zclim(lay["RZ_0_100"])), ("ERA5_L2", zclim(lay["L2_7_28"]))):
    for third_lab, third in (("Condom_20_30", z_ins), ("PeyrusseGrande_20_30", zclim(nb))):
        t = tc(x, zclim(swis[10]), third)
        # block bootstrap (30-day) of R_truth
        p = pair(x, zclim(swis[10]), third)
        tt = pd.Series(p.index); blk = ((tt - tt.min()) / pd.Timedelta(days=30)).astype(int).to_numpy()
        u = np.unique(blk); ib = {b: np.flatnonzero(blk == b) for b in u}
        rng = np.random.default_rng(42); A = p.to_numpy(); bs = []
        for _ in range(500):
            ii = np.concatenate([ib[b] for b in rng.choice(u, len(u))])
            Q = np.cov(A[ii].T)
            a2 = np.array([Q[0, 1] * Q[0, 2] / Q[1, 2], Q[0, 1] * Q[1, 2] / Q[0, 2], Q[0, 2] * Q[1, 2] / Q[0, 1]])
            bs.append(np.sqrt(np.clip(a2 / np.diag(Q), 0, 1)))
        bs = np.array(bs)
        for i, nm in enumerate([lab, "S1_SWI_T10", third_lab]):
            diag.append({"triplet": f"{lab}+S1_SWI_T10+{third_lab}", "member": nm, "R_truth": t["R_truth"][i],
                         "ci_lo": np.percentile(bs[:, i], 2.5), "ci_hi": np.percentile(bs[:, i], 97.5), "n": t["n"]})
diag = pd.DataFrame(diag)
diag.to_csv(f"{OUT}/c4_etc_diagnostic.csv", index=False)
print("\nETC diagnostic (correlation with unknown truth):\n", diag.round(3).to_string(index=False))
