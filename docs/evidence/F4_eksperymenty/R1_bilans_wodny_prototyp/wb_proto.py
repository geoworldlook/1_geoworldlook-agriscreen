"""
Prototype: FAO-56 dual-Kc soil water balance driven by ERA5-Land + Sentinel-2 NDVI,
validated against ISMN SMOSMANIA Condom with the same harness as
step_07.validate_anomalies (common-period DOY climatology, block-bootstrap CI).

Read-only use of the AgriWatch repo (imports QC + anomaly functions).
Run: PYTHONDONTWRITEBYTECODE=1 python3 -I wb_proto.py
"""
import sys
import json
import numpy as np
import pandas as pd

REPO = "/home/user/1_geoworldlook-agriscreen"
DATA = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/drive_data"
sys.path.insert(0, REPO)
import logging
logging.disable(logging.CRITICAL)
from step_04_metrics_alert import clim_anomaly, rootzone, dekad_end  # noqa: E402
from step_07_station_pipeline import insitu_daily_depth, build_config, _r_with_ci  # noqa: E402

LAT = 43.9744
OVR = {"PROJECT_DIR": REPO}
CFG7 = build_config(OVR)
COMMON = ("2016-01-01", "2024-12-31")
CLIM_REF = ("1991-01-01", "2020-12-31")
HW = 15


# ----------------------------------------------------------------------------- forcing
def load_era5():
    e = pd.read_csv(f"{DATA}/era5_land_daily.csv", parse_dates=["time"]).set_index("time").sort_index()
    e = e[~e.index.duplicated(keep="last")].asfreq("D")
    return e


def extraterrestrial_radiation_mm(doy, lat_deg):
    """FAO-56 eq. 21, returned as mm/day equivalent (x 0.408)."""
    phi = np.deg2rad(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    return 0.408 * ra


def et0_hargreaves(e):
    """Hargreaves-Samani (FAO-56 eq. 52). Tmax not in the local file: Tmax ~ 2*Tmean - Tmin (approximation)."""
    tmean, tmin = e["t2m_c"], e["t2m_min_c"]
    tmax = 2 * tmean - tmin
    ra = extraterrestrial_radiation_mm(e.index.dayofyear.to_numpy(), LAT)
    return 0.0023 * ra * (tmean + 17.8) * np.sqrt(np.clip(tmax - tmin, 0, None))


# ----------------------------------------------------------------------------- S-2 -> fc -> Kcb
def load_ndvi(site, product, min_clear=0.9):
    o = pd.read_csv(f"{DATA}/gwl_observations.csv")
    o = o[(o.site_id == site) & (o["product"] == product)]
    p = o.pivot_table(index="time_utc", columns="variable", values="value")
    p.index = pd.to_datetime(p.index).tz_localize(None).floor("D")
    if "clear_frac" in p:
        p = p[p["clear_frac"] >= min_clear]
    s = p["ndvi"].dropna()
    return s.groupby(level=0).mean().sort_index()


def daily_ndvi(obs, idx, max_gap=45):
    """Despike (3-obs rolling median), linear daily interpolation, gaps > max_gap and
    pre-S2 years filled with the DOY climatology of the observations (circular +-15 d)."""
    s = obs.rolling(3, center=True, min_periods=1).median()
    doy = s.index.dayofyear.to_numpy()
    clim = pd.Series(
        [np.nanmean(s.to_numpy()[np.minimum(np.abs(doy - d), 366 - np.abs(doy - d)) <= 15]) for d in range(1, 367)],
        index=range(1, 367)).interpolate(limit_direction="both")
    d = s.reindex(idx.union(s.index)).interpolate(method="time", limit_area="inside").reindex(idx)
    # mask interpolated values inside long gaps
    t_obs = pd.Series(s.index, index=s.index)
    prev = t_obs.reindex(idx, method="ffill")
    nxt = t_obs.reindex(idx, method="bfill")
    gap = (nxt - prev).dt.days
    d[(gap > max_gap) | prev.isna() | nxt.isna()] = np.nan
    clim_d = pd.Series(clim.reindex(idx.dayofyear).to_numpy(), index=idx)
    return d.fillna(clim_d), clim_d


def kcb_allen_pereira(ndvi, h, kcb_full, ml, ndvi_soil=0.15, ndvi_max=0.85, kc_min=0.15):
    """fc from NDVI (linear scaling), density coefficient Kd (Allen & Pereira 2009):
    Kd = min(1, ML*fc, fc**(1/(1+h)));  Kcb = Kc_min + Kd*(Kcb_full - Kc_min)."""
    fc = np.clip((ndvi - ndvi_soil) / (ndvi_max - ndvi_soil), 0.0, 0.99)
    kd = np.minimum.reduce([np.ones_like(fc), ml * fc, fc ** (1.0 / (1.0 + h))])
    return kc_min + kd * (kcb_full - kc_min), fc


# ----------------------------------------------------------------------------- FAO-56 dual Kc bucket
def saxton_rawls(sand, clay, om_pct):
    """Saxton & Rawls 2006 PTF: theta_33kPa (FC) and theta_1500kPa (WP), fractions."""
    S, C, OM = sand, clay, om_pct
    t1500t = -0.024 * S + 0.487 * C + 0.006 * OM + 0.005 * S * OM - 0.013 * C * OM + 0.068 * S * C + 0.031
    t1500 = t1500t + (0.14 * t1500t - 0.02)
    t33t = -0.251 * S + 0.195 * C + 0.011 * OM + 0.006 * S * OM - 0.027 * C * OM + 0.452 * S * C + 0.299
    t33 = t33t + (1.283 * t33t ** 2 - 0.374 * t33t - 0.015)
    return t33, t1500


def fao56_dual(P, ET0, Kcb, fc, thFC, thWP, Zr, p_tab, Ze=0.10, REW=9.0, kcmax_base=1.2, spinup_dr=0.0):
    """Daily FAO-56 dual crop coefficient water balance (Allen et al. 1998, ch. 7-8), rain only (fw = 1).
    Returns DataFrame with Dr, Ks, Ke, T (=Ks*Kcb*ET0), E, ETa, FTSW, theta_rz."""
    n = len(P)
    TAW = 1000 * (thFC - thWP) * Zr
    TEW = 1000 * (thFC - 0.5 * thWP) * Ze
    P, ET0, Kcb, fc = (np.asarray(a, float) for a in (P, ET0, Kcb, fc))
    Dr, De = spinup_dr, TEW * 0.5
    out = np.full((n, 7), np.nan)
    for i in range(n):
        p_i = 0.0 if np.isnan(P[i]) else P[i]
        et0 = 0.0 if np.isnan(ET0[i]) else ET0[i]
        kcb = Kcb[i]
        kcmax = max(kcmax_base, kcb + 0.05)
        few = max(1.0 - fc[i], 0.01)
        # evaporation layer
        De = max(De - p_i, 0.0)
        Kr = 1.0 if De <= REW else max((TEW - De) / (TEW - REW), 0.0)
        Ke = min(Kr * (kcmax - kcb), few * kcmax)
        E = Ke * et0
        De = min(De + E / few, TEW)
        # root zone
        p_adj = np.clip(p_tab + 0.04 * (5.0 - kcb * et0), 0.1, 0.8)
        RAW = p_adj * TAW
        # FAO-56 eq. 84: Ks from depletion at the start of the day; eq. 85-88: Dr update, DP = excess over FC
        Ks = 1.0 if Dr <= RAW else max((TAW - Dr) / ((1 - p_adj) * TAW), 0.0)
        T = Ks * kcb * et0
        ETa = T + E
        Dr = min(max(Dr - p_i + ETa, 0.0), TAW)
        out[i] = (Dr, Ks, Ke, T, E, ETa, 1 - Dr / TAW)
    df = pd.DataFrame(out, columns=["Dr", "Ks", "Ke", "T", "E", "ETa", "FTSW"])
    df["theta_rz"] = thFC - df["Dr"] / (1000 * Zr)
    return df, TAW, TEW


# ----------------------------------------------------------------------------- validation helpers
def r_ci(x, y):
    p = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    r, lo, hi = _r_with_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(), CFG7)
    rho = p["x"].rank().corr(p["y"].rank())
    return dict(r=round(r, 3), lo=round(lo, 3), hi=round(hi, 3), rho=round(rho, 3), n=len(p))


def z_common(s):
    return clim_anomaly(s.loc[COMMON[0]:COMMON[1]], COMMON, HW, min_n=20)["z"]


def z_ref(s):
    return clim_anomaly(s, CLIM_REF, HW)["z"]


def dekad_mean(z):
    tmp = pd.DataFrame({"z": z.to_numpy(), "dk": dekad_end(pd.Series(z.index)).to_numpy()})
    return tmp.groupby("dk")["z"].mean()


def pod_far(obs_dk, prd_dk, thr=-1.0):
    j = pd.concat([obs_dk.rename("o"), prd_dk.rename("p")], axis=1, join="inner").dropna()
    o, p = j["o"] <= thr, j["p"] <= thr
    h, m, f = int((o & p).sum()), int((o & ~p).sum()), int((~o & p).sum())
    return dict(pod=round(h / (h + m), 3) if h + m else np.nan, far=round(f / (h + f), 3) if h + f else np.nan,
                csi=round(h / (h + m + f), 3) if h + m + f else np.nan, n=len(j), hits=h, misses=m, fa=f)
