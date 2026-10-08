"""A2: evaluate pre-registered vegetation-signal variants vs ISMN Condom 20-30 cm anomaly (VINEYARD_06).

Pre-registered list (written before looking at variant results):
  B0   v1.0: NDVI SR 2.5 m scene anomaly (other years, +-15 d)
  V1a  Whittaker-smoothed NDVI (lambda=1000 from S-2-only LOO-CV), non-causal
  V1b  same, real-time (smoother fitted only on obs up to the scene day)
  V1c  causal trailing 30-day mean of scene z (F3 Z3)
  V3a  NDMI, V3b NDRE, V3c -CRSWIR (scene z, SR 2.5 m)
  V3d  mean z of NDVI, NDMI, -CRSWIR (equal weights)
  V3e  PC1 of NDVI, NDMI, NDRE, -CRSWIR z (loadings LOYO)
  V4   vineyard minus station-grass-plot NDVI anomaly (same scene)
  V6   phenology-relative: residual from 3-harmonic curve of other years / pooled residual SD (+-30 d)
  V7   within-season decline from running max since 1 June (smoothed), z vs other years
  V8a  Whittaker mean z of NDVI, NDMI, -CRSWIR (non-causal); V8b same real-time
Evaluation on the B0 scene days (paired with ISMN), R with 30-day block and year-block bootstrap CIs,
paired R difference vs B0 (same resamples), per-year wins, partial R | ERA5 RZ, event skill (z <= -1).
"""
import logging
import warnings

import numpy as np
import pandas as pd

from common import OUT, ins_z, era5_rz_z, r_ci, paired_diff_ci, per_year_r, events, pair, year_boot
import variants as V

logging.basicConfig(level=logging.WARNING)
warnings.filterwarnings("ignore")

y = ins_z("rz")
y10 = ins_z("10")
era = era5_rz_z()

S = {}
S["B0_ndvi_scene"] = V.b0()
S["V1a_ndvi_whittaker"] = V.whit()
S["V1b_ndvi_whittaker_RT"] = V.whit(realtime=True)
S["V1c_ndvi_trailing30d"] = V.trailing_mean(S["B0_ndvi_scene"], 30)
S["V3a_ndmi_scene"] = V.b0(idx="ndmi")
S["V3b_ndre_scene"] = V.b0(idx="ndre")
S["V3c_negcrswir_scene"] = V.b0(idx="crswir")
S["V3d_meanz_ndvi_ndmi_crswir"] = V.mean_z([S["B0_ndvi_scene"], S["V3a_ndmi_scene"], S["V3c_negcrswir_scene"]])
S["V3e_pc1_loyo"] = V.pc1_loyo({"ndvi": S["B0_ndvi_scene"], "ndmi": S["V3a_ndmi_scene"],
                                "ndre": S["V3b_ndre_scene"], "crswir": S["V3c_negcrswir_scene"]})
S["V4_vine_minus_grass"] = V.contrast()
S["V6_harmonic_loyo"] = V.harmonic_loyo()
S["V7_decline_since_june"] = V.decline()
w_nd, w_nm, w_cr = V.whit(idx="ndvi"), V.whit(idx="ndmi"), V.whit(idx="crswir")
S["V8a_whittaker_meanz"] = V.mean_z([w_nd, w_nm, w_cr])
S["V8b_whittaker_meanz_RT"] = V.mean_z([S["V1b_ndvi_whittaker_RT"], V.whit(idx="ndmi", realtime=True),
                                        V.whit(idx="crswir", realtime=True)])
pd.concat(S, axis=1).to_csv(f"{OUT}/a2_variant_series.csv")

base = S["B0_ndvi_scene"]
base_days = pair(base, y).index


def partial_r(x, yy, zc):
    p = pd.concat([x.rename("x"), yy.rename("y"), zc.rename("z")], axis=1, join="inner").dropna()
    def f(q):
        A = np.c_[np.ones(len(q)), q["z"]]
        rx = q["x"] - A @ np.linalg.lstsq(A, q["x"], rcond=None)[0]
        ry = q["y"] - A @ np.linalg.lstsq(A, q["y"], rcond=None)[0]
        return np.corrcoef(rx, ry)[0, 1]
    lo, hi = year_boot(p, f)
    return f(p), lo, hi, len(p)


rows = []
for name, s in S.items():
    s = s[s.index.isin(base_days)]                         # same dates as baseline
    a = r_ci(s, y)
    ay = r_ci(s, y, blocks="year")
    a10 = r_ci(s, y10)
    d = paired_diff_ci(s, base, y)
    py_v, py_b = per_year_r(s, y), per_year_r(base[base.index.isin(s.index)], y)
    wins = int(((py_v - py_b) > 0).sum())
    nyr = int((py_v - py_b).notna().sum())
    pr = partial_r(s, y, era)
    ev = events(s, y)
    jj = pair(s, y)
    m69 = jj.index.month.isin([6, 7, 8, 9])
    r69 = np.corrcoef(jj["x"][m69], jj["y"][m69])[0, 1]
    ev69 = events(s[s.index.month.isin([6, 7, 8, 9])], y)
    rows.append(dict(variant=name, n=a["n"], r=a["r"], ci30_lo=a["lo"], ci30_hi=a["hi"], ciY_lo=ay["lo"],
                     ciY_hi=ay["hi"], dR_vs_B0=d["d"], dR_lo=d["lo"], dR_hi=d["hi"], n_paired=d["n"],
                     B0_same_days=d["rb"], years_better=f"{wins}/{nyr}", partial_r_given_era5=pr[0],
                     pr_lo=pr[1], pr_hi=pr[2], r_10cm=a10["r"], n_10cm=a10["n"], r_VI_IX=r69,
                     n_VI_IX=int(m69.sum()), pod=ev["pod"], far=ev["far"], hss=ev["hss"],
                     n_flag=ev["hits"] + ev["fa"], pod_VI_IX=ev69["pod"], far_VI_IX=ev69["far"],
                     hss_VI_IX=ev69["hss"], n_flag_VI_IX=ev69["hits"] + ev69["fa"]))
res = pd.DataFrame(rows)
res.to_csv(f"{OUT}/a2_variants_eval.csv", index=False)
pd.set_option("display.width", 250)
cols1 = ["variant", "n", "r", "ci30_lo", "ci30_hi", "ciY_lo", "ciY_hi", "dR_vs_B0", "dR_lo", "dR_hi",
         "B0_same_days", "years_better", "partial_r_given_era5", "r_10cm", "n_10cm"]
cols2 = ["variant", "r_VI_IX", "n_VI_IX", "pod", "far", "hss", "n_flag", "pod_VI_IX", "far_VI_IX", "hss_VI_IX",
         "n_flag_VI_IX"]
print(res[cols1].round(3).to_string(index=False))
print(res[cols2].round(3).to_string(index=False))

# per-year R table
py = pd.DataFrame({k: per_year_r(v[v.index.isin(base_days)], y) for k, v in S.items()})
py.round(2).to_csv(f"{OUT}/a2_per_year_r.csv")
print(py.round(2).T.to_string())
