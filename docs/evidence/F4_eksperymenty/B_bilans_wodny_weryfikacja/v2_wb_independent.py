"""Independent re-run of the FAO-56 water-balance variants with pyfao56 (not the author's numpy loop).

- ET0 Hargreaves recomputed here (own Ra), compared with inputs_forcing.csv.
- Kcb rebuilt from gwl_observations: (a) author-like (centred 3-scene median + linear interpolation,
  i.e. uses the NEXT scene = not available in real time), (b) CAUSAL (trailing 3-scene median,
  last observation carried forward <= 30 d) = what an operational Colab run could do.
  Kcb climatology for gaps: (c) leave-one-year-out (LOYO) DOY climatology, to remove the use of the
  evaluation year in the gap-filling climatology.
- pyfao56 v1.4.3 model runs 1991-2026, RSW = 1 - Dr/TAW, anomalies vs ISMN 20-30 cm.
"""
import json
import logging
import sys

import numpy as np
import pandas as pd

REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
OUT = f"{SCR}/exp_wb_verify"
sys.path.insert(0, REPO)
sys.path.insert(0, f"{SCR}/pkgs/pyfao56_lib")
sys.path.insert(0, OUT)
logging.disable(logging.CRITICAL)
import pyfao56 as fao  # noqa: E402
import step_07_station_pipeline as s7  # noqa: E402
from v1_helpers import own_anom, boot_dr, boot_r  # noqa: E402

COMMON = ("2016-01-01", "2024-12-31")
LAT = 43.9744

e = pd.read_csv(f"{SCR}/drive_data/era5_land_daily.csv", parse_dates=["time"]).set_index("time").sort_index()
e = e[~e.index.duplicated(keep="last")]
days = e.index

# ---- ET0 Hargreaves (own)
J = days.dayofyear.to_numpy()
phi = np.deg2rad(LAT)
dr = 1 + 0.033 * np.cos(2 * np.pi / 365 * J)
dec = 0.409 * np.sin(2 * np.pi / 365 * J - 1.39)
ws = np.arccos(-np.tan(phi) * np.tan(dec))
Ra = 24 * 60 / np.pi * 0.082 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
tmax = 2 * e.t2m_c - e.t2m_min_c
et0 = (0.0023 * 0.408 * Ra * (e.t2m_c + 17.8) * np.sqrt((tmax - e.t2m_min_c).clip(lower=0))).clip(lower=0)
fin = pd.read_csv(f"{SCR}/exp_wb/inputs_forcing.csv", index_col="date", parse_dates=True)
out = {"maxabs_et0_vs_author": float((et0 - fin["et0"]).abs().max()),
       "mean_DTR_reconstructed_C": float((tmax - e.t2m_min_c).mean()),
       "et0_annual_mean_1991_2020": float(et0.loc["1991":"2020"].resample("YE").sum().mean()),
       "P_annual_mean_1991_2020": float(e.precip_mm.loc["1991":"2020"].resample("YE").sum().mean())}

# ---- NDVI scenes
obs = pd.read_csv(f"{SCR}/drive_data/gwl_observations.csv")


def scenes(site, prod, min_clear, months):
    o = obs[(obs.site_id == site) & (obs["product"] == prod)]
    w = o.pivot_table(index="time_utc", columns="variable", values="value")
    w.index = pd.to_datetime(w.index).tz_localize(None).floor("D")
    if min_clear is not None:
        w = w[w["clear_frac"] >= min_clear]
    s = w["ndvi"].dropna().groupby(level=0).mean().sort_index()
    if months:
        s = s[(s.index.month >= months[0]) & (s.index.month <= months[1])]
    return s


def doy_clim(kobs: pd.Series, exclude_year=None):
    k = kobs.dropna()
    if exclude_year is not None:
        k = k[k.index.year != exclude_year]
    d0, v0 = k.index.dayofyear.to_numpy(), k.to_numpy()
    c = np.full(366, np.nan)
    for d in range(1, 367):
        dist = np.abs(d0 - d)
        dist = np.minimum(dist, 366 - dist)
        if (dist <= 15).sum() >= 30:
            c[d - 1] = v0[dist <= 15].mean()
    x = np.arange(1, 367)
    g = np.isfinite(c)
    return np.interp(x, np.concatenate([x[g] - 366, x[g], x[g] + 366]), np.tile(c[g], 3))


def daily_kcb(nd, months, causal=False, loyo_clim=False):
    if causal:
        sm = nd.rolling(3, min_periods=1).median()  # trailing
    else:
        sm = nd.rolling(3, center=True, min_periods=1).median()
    k = (1.44 * sm - 0.10).clip(lower=0.15)
    t = k.index
    if causal:
        last_t = pd.Series(t, index=t).reindex(days, method="ffill")
        age = (days.to_series() - last_t).dt.days.to_numpy()
        val = k.reindex(days, method="ffill").to_numpy()
        ok = np.isfinite(val) & (age <= 30)
    else:
        val = k.reindex(days.union(t)).interpolate(method="time", limit_area="inside").reindex(days).to_numpy()
        prev = pd.Series(t, index=t).reindex(days, method="ffill")
        nxt = pd.Series(t, index=t).reindex(days, method="bfill")
        ok = np.isfinite(val) & ((nxt - prev).dt.days.to_numpy() <= 30)
    if months:
        ok &= (days.month >= months[0]) & (days.month <= months[1])
    kobs = pd.Series(np.where(ok, val, np.nan), index=days)
    if loyo_clim:
        cl = np.empty(len(days))
        for yr in np.unique(days.year):
            m = days.year == yr
            c = doy_clim(kobs, exclude_year=yr if 2016 <= yr <= 2024 else None)
            cl[m] = c[days.dayofyear.to_numpy()[m] - 1]
        kcl = pd.Series(cl, index=days)
    else:
        c = doy_clim(kobs)
        kcl = pd.Series(c[days.dayofyear.to_numpy() - 1], index=days)
    return kobs.where(kobs.notna(), kcl), kcl


nd_v = scenes("VINEYARD_06", "S2SR_2.5m", 0.9, (4, 10))
nd_s = scenes("SMOSMANIA_Condom", "S2_L2A", None, None)
kin = pd.read_csv(f"{SCR}/exp_wb/inputs_kcb.csv", index_col="date", parse_dates=True)
kv, kv_clim = daily_kcb(nd_v, (4, 10))
kv_c, _ = daily_kcb(nd_v, (4, 10), causal=True)
kv_cl, kv_cl_clim = daily_kcb(nd_v, (4, 10), causal=True, loyo_clim=True)
ks_, _ = daily_kcb(nd_s, None)
out["maxabs_kcb_vine_vs_author"] = float((kv - kin["vine_SR"]).abs().max())
out["maxabs_kcbclim_vine_vs_author"] = float((kv_clim - kin["vine_SR_clim"]).abs().max())
out["maxabs_kcb_station_vs_author"] = float((ks_ - kin["station_L2A"]).abs().max())
out["mean_abs_kcb_causal_minus_centred_obsdays"] = float((kv_c - kv).abs()[kv.index.month.isin(range(4, 11))].mean())


def run_pyfao(kcb: pd.Series, p_base, h, zr=1.0):
    par = fao.Parameters(Kcbini=0.15, Kcbmid=0.65, Kcbend=0.40, Lini=1, Ldev=1, Lmid=100000, Lend=1,
                         hini=h, hmax=h, thetaFC=0.36, thetaWP=0.22, theta0=0.36, Zrini=zr, Zrmax=zr,
                         pbase=p_base, Ze=0.10, REW=10.0)
    wth = fao.Weather()
    wth.wndht = 2.0
    wth.rfcrp = "S"
    keys = days.strftime("%Y-%j")
    wd = pd.DataFrame(np.nan, index=keys, columns=wth.cnames)
    wd["Rain"] = e.precip_mm.to_numpy()
    wd["ETref"] = et0.to_numpy()
    wd["Wndsp"] = 2.0
    wd["RHmin"] = 45.0
    wd["Tmax"] = tmax.to_numpy()
    wd["Tmin"] = e.t2m_min_c.to_numpy()
    wth.wdata = wd
    upd = fao.Update()
    upd.udata = pd.DataFrame({"Kcb": kcb.to_numpy(), "h": h, "fc": np.nan}, index=keys)
    m = fao.Model(keys[0], keys[-1], par, wth, upd=upd)
    m.run()
    o = m.odata
    o.index = days
    taw = 1000 * (0.36 - 0.22) * zr
    return 1 - o["Dr"].astype(float) / taw, o


ov = {"PROJECT_DIR": REPO}
ins = pd.concat([s7.insitu_daily_depth(0.20, ov)["sm"], s7.insitu_daily_depth(0.30, ov)["sm"]], axis=1).dropna().mean(axis=1)
y = own_anom(ins.loc[COMMON[0]:COMMON[1]], COMMON)
rz = (7 * e.sm_l1 + 21 * e.sm_l2 + 72 * e.sm_l3) / 100
zb = own_anom(rz.loc[COMMON[0]:COMMON[1]], COMMON)
ser = pd.read_csv(f"{SCR}/exp_wb/series_daily_z.csv", index_col="date", parse_dates=True)

runs = {"V1": (kv, 0.45, 1.5), "V3": (kv_clim, 0.45, 1.5), "V4": (ks_, 0.5, 0.15),
        "V1_causal": (kv_c, 0.45, 1.5), "V1_causal_loyoclim": (kv_cl, 0.45, 1.5), "V3_loyoclim": (kv_cl_clim, 0.45, 1.5)}
zz = {}
ivx = lambda s: s[(s.index.month >= 4) & (s.index.month <= 10)]
for name, (k, pb, h) in runs.items():
    rsw, o = run_pyfao(k, pb, h)
    z = own_anom(rsw.loc[COMMON[0]:COMMON[1]], COMMON)
    zz[name] = z
    r = boot_r(z, y, 30)
    res = {"R": r, "dR_vs_ERA5_30": boot_dr(z, zb, y, 30), "dR_vs_ERA5_year": boot_dr(z, zb, y, "year"),
           "dR_vs_ERA5_IVX_30": boot_dr(ivx(z), ivx(zb), ivx(y), 30),
           "dR_vs_ERA5_IVX_year": boot_dr(ivx(z), ivx(zb), ivx(y), "year"),
           "mean_RSW_Aug_2016_2024": float(rsw.loc["2016":"2024"][rsw.loc["2016":"2024"].index.month == 8].mean()),
           "ETa_annual_2016_2024": float(o["ETa"].astype(float).loc["2016":"2024"].resample("YE").sum().mean())}
    col = {"V1": "z_V1_WB_vine_SR", "V3": "z_V3_WB_vine_clim", "V4": "z_V4_WB_station"}.get(name)
    if col:
        res["maxabs_z_vs_author"] = float((z - ser[col]).abs().max())
    out[name] = res
out["dR_V1_minus_V3_30"] = boot_dr(zz["V1"], zz["V3"], y, 30)
out["dR_V1causal_minus_V1"] = boot_dr(zz["V1_causal"], zz["V1"], y, 30)
out["dR_V1causalloyo_minus_V3loyo"] = boot_dr(zz["V1_causal_loyoclim"], zz["V3_loyoclim"], y, 30)
out["r_z_V1_vs_V3"] = float(pd.concat([zz["V1"], zz["V3"]], axis=1).dropna().corr().iloc[0, 1])
c = (zz["V1"] - zz["V3"])
out["S2comp_std_IVX"] = float(ivx(c).std())
out["S2comp_q01_q99_IVX"] = [float(ivx(c).quantile(0.01)), float(ivx(c).quantile(0.99))]
print(json.dumps(out, indent=1, default=str))
json.dump(out, open(f"{OUT}/v2_wb_independent.json", "w"), indent=1, default=str)
