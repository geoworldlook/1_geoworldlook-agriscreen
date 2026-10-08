"""POST-HOC variant V11 (added after seeing that the bounded FAO-56 bucket empties every summer, mean August
RSW ~0.09, which removes interannual contrast in IV-X).

Potential soil moisture deficit (PSMD; Penman 1948 idea, used e.g. in UK MORECS): unbounded below,
D_t = max(0, D_{t-1} + Kcb*ET0 + E - P), with E = soil evaporation from the FAO-56 dual-Kc run (does not
depend on Ks). Without the Ks feedback the S-2 Kcb deviations accumulate fully, so this is also the most
favourable test for a parcel-specific S-2 contribution.
  V11a: Kcb from vineyard S-2 SR   V11b: climatological Kcb (ablation)
Anomaly variable = -D (dry = negative), same anomaly definitions as all other variants.
"""
import json

import numpy as np
import pandas as pd

import common as C
import config as K
import wb_model as W

f = pd.read_csv(f"{C.OUT}/inputs_forcing.csv", index_col="date", parse_dates=True)
kc = pd.read_csv(f"{C.OUT}/inputs_kcb.csv", index_col="date", parse_dates=True)
VINE = dict(K.SOIL_BASE, **K.VINE)


def psmd(kcb: pd.Series) -> pd.Series:
    r = W.run_wb(f, kcb, VINE)
    demand = (r["kcb"] * f["et0"] + r["E"]).to_numpy()
    p = f["precip_mm"].to_numpy()
    d = np.empty(len(p))
    acc = 0.0
    for i in range(len(p)):
        acc = max(0.0, acc + demand[i] - p[i])
        d[i] = acc
    return pd.Series(-d, index=f.index)


y = C.ins_z("rz")
base = C.anom_common(C.s4.rootzone(C.era5()))
ser = pd.read_csv(f"{C.OUT}/series_daily_z.csv", index_col="date", parse_dates=True)
out = {}
zs = {}
for name, k in (("V11a_PSMD_vine_SR", kc["vine_SR"]), ("V11b_PSMD_vine_clim", kc["vine_SR_clim"])):
    s = psmd(k)
    z = C.anom_common(s)
    zs[name] = z
    zo = C.anom_oper(s)
    res = {"R_all": C.r_ci(z, y), "dR_vs_ERA5_30d": C.paired_delta_r(z, base, y, "30d"),
           "dR_vs_ERA5_year": C.paired_delta_r(z, base, y, "year"),
           "dR_vs_V1_30d": C.paired_delta_r(z, ser["z_V1_WB_vine_SR"], y, "30d"),
           "max_deficit_mm_by_year": (-s.loc["2016":"2024"]).groupby(s.loc["2016":"2024"].index.year).max().round(0).to_dict()}
    for sub, months in (("IV-X", (4, 10)),):
        m = lambda q: q[(q.index.month >= months[0]) & (q.index.month <= months[1])]
        res[f"R_{sub}"] = C.r_ci(m(z), m(y))
        res[f"dR_vs_ERA5_{sub}"] = C.paired_delta_r(m(z), m(base), m(y), "30d")
    ins_dk = C.dekad_mean(y)
    res["events_oper"] = C.pod_far_ci(C.dekad_mean(zo.loc["2016":]), ins_dk)
    res["events_common"] = C.pod_far_ci(C.dekad_mean(z), ins_dk)
    out[name] = res
out["dR_V11a_minus_V11b_30d"] = C.paired_delta_r(zs["V11a_PSMD_vine_SR"], zs["V11b_PSMD_vine_clim"], y, "30d")
comp = (zs["V11a_PSMD_vine_SR"] - zs["V11b_PSMD_vine_clim"])
out["std_S2component_z_IV-X"] = float(comp[(comp.index.month >= 4) & (comp.index.month <= 10)].std())
with open(f"{C.OUT}/results_v11_psmd.json", "w") as fh:
    json.dump(out, fh, indent=1, default=float)
print(json.dumps(out, indent=1, default=float))
