"""Compact summary table of Experiment B (one row per variant) from the result files."""
import json

import pandas as pd

import common as C

r = pd.read_csv(f"{C.OUT}/results_daily_r.csv")
ev = pd.read_csv(f"{C.OUT}/results_events.csv")
d2 = json.load(open(f"{C.OUT}/results_diagnostics2.json"))
v11 = json.load(open(f"{C.OUT}/results_v11_psmd.json"))
evx = pd.read_csv(f"{C.OUT}/results_events_extra.csv")

rows = []
for v in ["B0_ERA5L_RZ", "V1_WB_vine_SR", "V2_WB_vine_10m", "V3_WB_vine_clim", "V4_WB_station", "V5_WB_vine_SR_cvZr",
          "V6_SPEI30_like", "V7_SPEI60_like", "V8_SPEI90_like", "V9_ERA5+WB_loyo"]:
    a = r[(r.variant == v) & (r.reference == "ISMN_20_30cm") & (r.subset == "all")].iloc[0]
    t = r[(r.variant == v) & (r.reference == "ISMN_10cm") & (r.subset == "all")].iloc[0]
    s1 = r[(r.variant == v) & (r.subset == "IV-X")].iloc[0]
    s2 = r[(r.variant == v) & (r.subset == "XI-III")].iloc[0]
    row = dict(variant=v, R_2030=a.r, lo=a.lo, hi=a.hi, n=a.n, base_same_dates=a.get("baseline_same_dates"),
               dR=a.get("delta_r"), dR_lo30d=a.get("delta_lo_30d"), dR_hi30d=a.get("delta_hi_30d"),
               dR_lo_year=a.get("delta_lo_year"), dR_hi_year=a.get("delta_hi_year"),
               R_10cm=t.r, R_10cm_base=t.get("baseline_same_dates"), dR_10cm_lo=t.get("delta_lo_30d"), dR_10cm_hi=t.get("delta_hi_30d"),
               R_IVX=s1.r, dR_IVX=s1.get("delta_r"), dR_IVX_lo=s1.get("delta_lo_30d"), dR_IVX_hi=s1.get("delta_hi_30d"),
               R_XIIII=s2.r, dR_XIIII=s2.get("delta_r"), dR_XIIII_lo=s2.get("delta_lo_30d"), dR_XIIII_hi=s2.get("delta_hi_30d"))
    e = ev[(ev.variant == v) & (ev.anomaly_ref == "operational_1991-2020")]
    if len(e):
        e = e.iloc[0]
        row.update(POD_oper=e.pod, FAR_oper=e.far, POD_lo=e.pod_lo, POD_hi=e.pod_hi, FAR_lo=e.far_lo, FAR_hi=e.far_hi)
    e = ev[(ev.variant == v) & (ev.anomaly_ref == "common_2016-2024")]
    if len(e):
        row.update(POD_common=e.iloc[0].pod, FAR_common=e.iloc[0].far)
    rows.append(row)
# post-hoc / diagnostic rows
p = d2["e_V10_ERA5+SPEI30_vs_ERA5_loyo_POSTHOC"]
rows.append(dict(variant="V10_ERA5+SPEI30_loyo (post-hoc; base = ERA5 LOYO)", R_2030=p["r_a"], lo=d2["e_V10_R_ci_POSTHOC"]["lo"], hi=d2["e_V10_R_ci_POSTHOC"]["hi"], n=p["n"], base_same_dates=p["r_b"],
                 dR=p["delta"], dR_lo30d=p["lo"], dR_hi30d=p["hi"],
                 dR_lo_year=d2["e_V10_ERA5+SPEI30_vs_ERA5_loyo_yearblocks_POSTHOC"]["lo"],
                 dR_hi_year=d2["e_V10_ERA5+SPEI30_vs_ERA5_loyo_yearblocks_POSTHOC"]["hi"]))
q = v11["V11a_PSMD_vine_SR"]
rows.append(dict(variant="V11_PSMD_unbounded (post-hoc, INVALID: drifts)", R_2030=q["R_all"]["r"], lo=q["R_all"]["lo"],
                 hi=q["R_all"]["hi"], n=q["R_all"]["n"], base_same_dates=q["dR_vs_ERA5_30d"]["r_b"],
                 dR=q["dR_vs_ERA5_30d"]["delta"], dR_lo30d=q["dR_vs_ERA5_30d"]["lo"], dR_hi30d=q["dR_vs_ERA5_30d"]["hi"]))
d = d2["d_R_ERA5_0-28cm_vs_ISMN2030"]
dd = d2["d_dR_ERA5_0-28_minus_0-100"]
ex = evx[(evx.variant == "D_ERA5L_0-28cm") & (evx.subset == "all")]
rows.append(dict(variant="D_ERA5L_0-28cm (diagnostic, not a WB variant)", R_2030=d["r"], lo=d["lo"], hi=d["hi"], n=d["n"],
                 base_same_dates=dd["r_b"], dR=dd["delta"], dR_lo30d=dd["lo"], dR_hi30d=dd["hi"],
                 POD_oper=ex[ex.anomaly_ref == "operational_1991-2020"].pod.iat[0],
                 FAR_oper=ex[ex.anomaly_ref == "operational_1991-2020"].far.iat[0],
                 POD_common=ex[ex.anomaly_ref == "common_2016-2024"].pod.iat[0],
                 FAR_common=ex[ex.anomaly_ref == "common_2016-2024"].far.iat[0]))
t = pd.DataFrame(rows)
t.to_csv(f"{C.OUT}/results_summary.csv", index=False)
pd.set_option("display.width", 300)
pd.set_option("display.max_columns", 40)
print(t.round(3).to_string(index=False))
