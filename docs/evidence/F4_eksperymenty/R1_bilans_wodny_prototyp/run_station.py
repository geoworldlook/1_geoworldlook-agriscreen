"""Station experiment: does an S-2-driven FAO-56 bucket beat ERA5-Land RZ anomalies vs ISMN Condom?
Parameters fixed from literature BEFORE looking at results (pre-registered in this header):
  grass plot: h=0.3 m, Kcb_full=1.0, ML=2.0, Zr=0.5 m, p=0.5 (FAO-56 T22 pasture 0.5-0.6), Ze=0.10, REW=9
  soil: Saxton & Rawls 2006 PTF with ISMN in-situ texture 0-30 cm (sand 13 %, clay 45 %, OC 1.2 % -> OM 2.1 %)
  ET0: Hargreaves-Samani with Tmax ~ 2*Tmean - Tmin.
Sensitivity runs are reported separately and are NOT used to choose the headline number.
"""
import sys
import json
import numpy as np
import pandas as pd
sys.path.insert(0, "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/wb")
from wb_proto import (load_era5, et0_hargreaves, load_ndvi, daily_ndvi, kcb_allen_pereira, saxton_rawls,
                      fao56_dual, r_ci, z_common, z_ref, dekad_mean, pod_far, insitu_daily_depth, OVR, rootzone,
                      DATA)

e = load_era5()
e["et0"] = et0_hargreaves(e)
idx = e.index

# ---------------- in situ
d = {z: insitu_daily_depth(z, OVR)["sm"] for z in (0.05, 0.10, 0.20, 0.30)}
rz2030 = pd.concat([d[0.20], d[0.30]], axis=1).dropna().mean(axis=1)
prof = pd.concat([d[0.05], d[0.10], d[0.20], d[0.30]], axis=1).dropna()
prof030 = (prof.iloc[:, 0] * 7.5 + prof.iloc[:, 1] * 7.5 + prof.iloc[:, 2] * 10 + prof.iloc[:, 3] * 5) / 30
print("in situ 20-30 cm: n=%d, p01=%.3f p50=%.3f p99=%.3f" % (len(rz2030), *rz2030.quantile([.01, .5, .99])))
ins_z = z_common(rz2030)
prof_z = z_common(prof030)

res = {}
# ---------------- baselines (ERA5-Land)
era_rz = rootzone(e)
era_028 = (7 * e["sm_l1"] + 21 * e["sm_l2"]) / 28
res["ERA5L_RZ_0-100"] = r_ci(z_common(era_rz), ins_z)
res["ERA5L_0-28"] = r_ci(z_common(era_028), ins_z)

# ---------------- S-2 at station (50 m buffer, all months)
nd_obs = load_ndvi("SMOSMANIA_Condom", "S2_L2A", min_clear=0)
nd, nd_clim = daily_ndvi(nd_obs, idx)
print("station NDVI obs:", len(nd_obs), nd_obs.index.min().date(), nd_obs.index.max().date())

thFC, thWP = saxton_rawls(0.13, 0.45, 1.2 * 1.724)
print("PTF theta_FC=%.3f theta_WP=%.3f" % (thFC, thWP))


def run(ndvi_series, Zr=0.5, p=0.5, h=0.3, kcb_full=1.0, ml=2.0, et0_scale=1.0, fc_=thFC, wp_=thWP):
    kcb, fc = kcb_allen_pereira(ndvi_series.to_numpy(), h, kcb_full, ml)
    out, taw, tew = fao56_dual(e["precip_mm"].to_numpy(), e["et0"].to_numpy() * et0_scale, kcb, fc, fc_, wp_, Zr, p)
    out.index = idx
    out["Kcb"] = kcb
    return out, taw


wb_s2, taw = run(nd)
wb_clim, _ = run(nd_clim)
print("TAW(Zr=0.5) = %.0f mm" % taw)
for name, wb in (("WB_S2Kcb", wb_s2), ("WB_climKcb", wb_clim)):
    res[name] = r_ci(z_common(wb["theta_rz"]), ins_z)
    res[name + "_vs_profile0-30"] = r_ci(z_common(wb["theta_rz"]), prof_z)
res["ERA5L_RZ_vs_profile0-30"] = r_ci(z_common(era_rz), prof_z)
res["ERA5L_0-28_vs_profile0-30"] = r_ci(z_common(era_028), prof_z)

# split periods (no tuning, just stability)
for per in (("2016", "2020"), ("2021", "2024")):
    for name, s in (("ERA5L_RZ_0-100", z_common(era_rz)), ("WB_S2Kcb", z_common(wb_s2["theta_rz"])),
                    ("ERA5L_0-28", z_common(era_028))):
        res[f"{name}_{per[0]}-{per[1]}"] = r_ci(s.loc[per[0]:per[1]], ins_z.loc[per[0]:per[1]])

# growing season only (IV-X), where a vine stress product matters
gs = lambda s: s[s.index.month.isin(range(4, 11))]
for name, s in (("ERA5L_RZ_0-100", z_common(era_rz)), ("WB_S2Kcb", z_common(wb_s2["theta_rz"])),
                ("WB_climKcb", z_common(wb_clim["theta_rz"])), ("ERA5L_0-28", z_common(era_028))):
    res[f"{name}_IV-X"] = r_ci(gs(s), gs(ins_z))

# ---------------- dekadal events with operational 1991-2020 climatology
st = pd.read_csv(f"{DATA}/gwl_status.csv", parse_dates=["date"]).drop_duplicates("date").set_index("date")
obs_dk = dekad_mean(ins_z)
ev = {"ERA5L_RZ (gwl_status sma_rz, replication)": pod_far(obs_dk, st["sma_rz"]),
      "ERA5L_RZ recomputed": pod_far(obs_dk, z_ref(era_rz).groupby(level=0).first().reindex(st.index)),
      "ERA5L_0-28 (dekad-end)": pod_far(obs_dk, z_ref(era_028).reindex(st.index)),
      "WB_S2Kcb (dekad-end)": pod_far(obs_dk, z_ref(wb_s2["theta_rz"]).reindex(st.index)),
      "WB_climKcb (dekad-end)": pod_far(obs_dk, z_ref(wb_clim["theta_rz"]).reindex(st.index))}

# ---------------- sensitivity (reported, not used for selection)
sens = {}
for Zr in (0.3, 0.5, 0.8, 1.2):
    w, t = run(nd, Zr=Zr)
    sens[f"Zr={Zr} (TAW={t:.0f} mm)"] = r_ci(z_common(w["theta_rz"]), ins_z)["r"]
for sc in (0.85, 1.15):
    w, _ = run(nd, et0_scale=sc)
    sens[f"ET0 x{sc}"] = r_ci(z_common(w["theta_rz"]), ins_z)["r"]
for ml in (1.5, 2.5):
    w, _ = run(nd, ml=ml)
    sens[f"ML={ml}"] = r_ci(z_common(w["theta_rz"]), ins_z)["r"]
w, _ = run(nd, p=0.35)
sens["p=0.35"] = r_ci(z_common(w["theta_rz"]), ins_z)["r"]
# data-derived limits (diagnostic only): FC = p95 of Dec-Feb 20-30 cm, WP = p01 of the series
fc_d = rz2030[rz2030.index.month.isin([12, 1, 2])].quantile(0.95)
wp_d = rz2030.quantile(0.01)
w, t = run(nd, fc_=fc_d, wp_=wp_d)
sens[f"in-situ limits FC={fc_d:.3f} WP={wp_d:.3f} (TAW={t:.0f} mm)"] = r_ci(z_common(w["theta_rz"]), ins_z)["r"]

print(json.dumps({"validation_vs_ISMN_20-30cm_anomaly": res, "dekad_events_z<=-1": ev, "sensitivity_R": sens},
                 indent=1, default=str))
wb_s2.to_csv("/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/wb/station_wb_s2.csv")
