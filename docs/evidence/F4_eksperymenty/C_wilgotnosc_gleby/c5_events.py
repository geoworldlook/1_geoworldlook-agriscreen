"""C5 - dry-dekad event skill: threshold sensitivity, persistence, EDO hysteresis, base period, layer.

Observed event (fixed, v1.0 definition): dekadal mean of ISMN 20-30 cm z (DOY clim 2016-2024) <= -1.
Product trigger: dekadal mean of daily product z <= thr.
Rules (physical motivation):
  thr -0.5 / -1 / -1.5     sensitivity of the warning trigger;
  persist2                 drought is a persistent anomaly; one-dekad dips (single dry spell) are often noise
                           -> event only if the trigger holds in 2 consecutive dekads (costs 10 days of lead time);
  hysteresis(-1, -0.5)     EDO CDI v4 table 2a: warning starts at <= -1 and is kept while <= -0.5 (state memory);
Base period: ERA5 operational z is vs 1991-2020, the ISMN reference can only be vs 2016-2024; 2016-2024 is more
variable, so the 1991-2020 base flags more dekads. We show both bases (2016-2024 base computed leave-one-year-out).
Threshold selection itself is validated LOYO (choose thr maximising CSI on 8 years, score on held-out year).
Scores: POD, FAR, CSI, frequency bias, ETS; 95% CI from bootstrap over whole years (9 blocks).
Outputs: out/c5_events.csv, out/c5_events_by_year.csv, out/c5_loyo_threshold.csv
"""
import numpy as np
import pandas as pd

from common import (CLIM_REF, COMMON, OUT, YEARS, contingency, contingency_ci, era5_full, era5_layers, hysteresis,
                    ismn_ref, persist2, to_dekad, zclim)

e_full = era5_full()
lay_full = era5_layers(e_full)
z_ins = zclim(ismn_ref())
obs_dk = to_dekad(z_ins)
cv = pd.read_csv(f"{OUT}/c4_cv_series.csv", index_col=0, parse_dates=True)   # LOYO z (2016-2024 base)

prod = {
    "RZ_op1991": to_dekad(zclim(lay_full["RZ_0_100"], ref=CLIM_REF, min_n=30).loc["2016-01-01":COMMON[1]]),
    "L2_op1991": to_dekad(zclim(lay_full["L2_7_28"], ref=CLIM_REF, min_n=30).loc["2016-01-01":COMMON[1]]),
    "RZ_cv2016": to_dekad(cv["E_RZ"]),
    "L2_cv2016": to_dekad(cv["E_L2"]),
    "EQ_RZ_S1_cv2016": to_dekad(cv["EQ_RZ_S"]),
}
zop = zclim(lay_full["RZ_0_100"], ref=CLIM_REF, min_n=30).loc[COMMON[0]:COMMON[1]]
print(f"ERA5 RZ z (1991-2020 base) over 2016-2024: mean {zop.mean():.3f}, sd {zop.std():.3f}, share<=-1 {(zop<=-1).mean():.3f}")

RULES = {
    "thr-0.5": lambda z: z <= -0.5,
    "thr-1.0": lambda z: z <= -1.0,
    "thr-1.5": lambda z: z <= -1.5,
    "persist2@-1.0": lambda z: persist2(z <= -1.0),
    "persist2@-0.5": lambda z: persist2(z <= -0.5),
    "hyst(-1,-0.5)": lambda z: hysteresis(z, -1.0, -0.5),
}

rows, yrows = [], []
for pn, pz in prod.items():
    j = pd.concat([pz.rename("p"), obs_dk.rename("o")], axis=1).dropna()
    obs = j["o"] <= -1.0
    for rn, rule in RULES.items():
        flag = rule(j["p"])
        for season in ("all", "IV-X"):
            m = np.ones(len(j), bool) if season == "all" else j.index.month.isin(range(4, 11))
            c = contingency(obs.to_numpy()[m], flag.to_numpy()[m])
            ci = contingency_ci(obs[m], flag[m], by="year")
            rows.append({"product": pn, "rule": rn, "season": season, **c,
                         **{f"{k}_lo": v[0] for k, v in ci.items()}, **{f"{k}_hi": v[1] for k, v in ci.items()}})
        for y, g in j.groupby(j.index.year):
            c = contingency((g["o"] <= -1).to_numpy(), rule(j["p"]).loc[g.index].to_numpy())
            yrows.append({"product": pn, "rule": rn, "year": y, "hits": c["hits"], "misses": c["misses"],
                          "false_alarms": c["false_alarms"]})
res = pd.DataFrame(rows)
res.to_csv(f"{OUT}/c5_events.csv", index=False)
pd.set_option("display.width", 250)
cols = ["product", "rule", "season", "n", "hits", "misses", "false_alarms", "pod", "pod_lo", "pod_hi", "far", "far_lo",
        "far_hi", "csi", "csi_lo", "csi_hi", "freq_bias", "ets"]
print(res[cols].round(3).to_string(index=False))
yr = pd.DataFrame(yrows)
yr.to_csv(f"{OUT}/c5_events_by_year.csv", index=False)

# LOYO threshold selection (CSI on training years) per product, persistence rules included as candidates
cand = {"thr-0.5": RULES["thr-0.5"], "thr-1.0": RULES["thr-1.0"], "thr-1.5": RULES["thr-1.5"],
        "persist2@-0.5": RULES["persist2@-0.5"], "persist2@-1.0": RULES["persist2@-1.0"],
        "hyst(-1,-0.5)": RULES["hyst(-1,-0.5)"]}
lrows = []
for pn, pz in prod.items():
    j = pd.concat([pz.rename("p"), obs_dk.rename("o")], axis=1).dropna()
    obs = (j["o"] <= -1.0).to_numpy()
    flags = {rn: f(j["p"]).to_numpy() for rn, f in cand.items()}
    yrs = j.index.year.to_numpy()
    O, P, picks = [], [], []
    for yv in YEARS:
        tr, te = yrs != yv, yrs == yv
        best = max(cand, key=lambda rn: contingency(obs[tr], flags[rn][tr])["csi"])
        picks.append(best)
        O.append(obs[te]); P.append(flags[best][te])
    c = contingency(np.concatenate(O), np.concatenate(P))
    lrows.append({"product": pn, **c, "picked": ";".join(picks)})
lo = pd.DataFrame(lrows)
lo.to_csv(f"{OUT}/c5_loyo_threshold.csv", index=False)
print("\nLOYO-selected rule (max CSI on training years):\n", lo.round(3).to_string(index=False))
