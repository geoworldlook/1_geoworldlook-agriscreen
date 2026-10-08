"""FAO-56 dual-Kc root-zone soil water balance driven by ERA5-Land + Sentinel-2 NDVI.

Physics = FAO-56 (Allen et al. 1998) chapters 7-8, implemented to mirror pyfao56 v1.4.3 Model._advance
(Thorp 2022; default homogeneous soil, no runoff, constant p adjusted by ETc, FAO-56 Ks) so that the
implementation can be regression-tested against pyfao56 (test_vs_pyfao56.py). Perennial crop: Zr constant.

Units: water depths in mm, theta in m3/m3, Zr/Ze in m, ET0 in mm/day, radiation in mm/day equivalent.
"""
import numpy as np
import pandas as pd

GSC = 0.0820          # solar constant, MJ m-2 min-1 (FAO-56 eq. 21)
MJ_TO_MM = 0.408      # MJ m-2 d-1 -> mm/day equivalent (1 / lambda, lambda = 2.45 MJ/kg)


# ----------------------------------------------------------------------------- reference ET
def extraterrestrial_radiation_mm(doy: np.ndarray, lat_deg: float) -> np.ndarray:
    """Ra, FAO-56 eqs. 21-25, returned in mm/day equivalent."""
    phi = np.deg2rad(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(-np.tan(phi) * np.tan(dec))          # |lat| < 66 deg: argument within [-1, 1]
    ra_mj = 24 * 60 / np.pi * GSC * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    return MJ_TO_MM * ra_mj


def et0_hargreaves(tmean_c: pd.Series, tmin_c: pd.Series, lat_deg: float) -> pd.DataFrame:
    """Hargreaves-Samani (1985), FAO-56 eq. 52: ET0 = 0.0023 Ra (Tmean + 17.8) sqrt(Tmax - Tmin).

    ERA5-Land file has no Tmax: approximated as Tmax = 2*Tmean - Tmin (i.e. Tmean = (Tmax+Tmin)/2).
    Because ERA5 Tmean is the mean of 24 hourly values (usually a bit below (Tmax+Tmin)/2), the
    reconstructed diurnal range is biased low -> ET0 biased low by a roughly constant factor; anomalies
    are much less affected. Stated as a limitation; add 'maximum_2m_air_temperature' in step_01 to remove it.
    """
    assert tmean_c.index.equals(tmin_c.index)
    tmax = 2 * tmean_c - tmin_c
    dtr = tmax - tmin_c
    assert (dtr >= -1e-9).all(), "Tmin > Tmean in input"
    ra = extraterrestrial_radiation_mm(tmean_c.index.dayofyear.to_numpy(), lat_deg)
    et0 = 0.0023 * ra * (tmean_c + 17.8) * np.sqrt(dtr.clip(lower=0))
    return pd.DataFrame({"et0": et0.clip(lower=0), "tmax_approx": tmax, "ra_mm": ra}, index=tmean_c.index)


# ----------------------------------------------------------------------------- NDVI -> Kcb
def kcb_campos2010(ndvi: pd.Series) -> pd.Series:
    """Campos et al. 2010 (Agric. Water Manag. 98:45-54), vineyards: Kcb = 1.44 NDVI - 0.10."""
    return 1.44 * ndvi - 0.10


def ndvi_scenes(obs: pd.DataFrame, site: str, product: str, min_clear: float | None) -> pd.Series:
    """Per-day NDVI of one site/product from gwl_observations (long format)."""
    o = obs[(obs["site_id"] == site) & (obs["product"] == product)]
    w = o.pivot_table(index="time_utc", columns="variable", values="value")
    w.index = pd.to_datetime(w.index).tz_localize(None).floor("D")
    if min_clear is not None:
        w = w[w["clear_frac"] >= min_clear]
    s = w["ndvi"].dropna()
    s = s.groupby(level=0).mean().sort_index()
    assert s.between(-1, 1).all()
    return s


def despike(s: pd.Series, window: int) -> pd.Series:
    """Running median over `window` consecutive scenes (removes single-scene cloud/shadow residuals)."""
    return s.rolling(window, center=True, min_periods=1).median()


def daily_kcb(scenes_ndvi: pd.Series, days: pd.DatetimeIndex, max_gap_days: int, months: tuple | None,
              kcb_min: float) -> pd.DataFrame:
    """Daily Kcb from scene NDVI.

    - Kcb per scene via Campos 2010, then linear interpolation in time between scenes;
    - a day uses observed Kcb only if its bracketing scenes are <= max_gap_days apart and (if `months`)
      the day lies in the observation season; otherwise the DOY climatology of the observed daily Kcb
      (circular +-15 d mean, gaps in DOY - e.g. winter for IV-X data - linearly interpolated across
      the year boundary). Climatology is also used for all days before the first scene (1991-2015).
    Returns columns: kcb (used), kcb_clim, kcb_obs (NaN where not observed), source ('obs'/'clim').
    """
    k = kcb_campos2010(scenes_ndvi).clip(lower=kcb_min)
    t = k.index
    full = k.reindex(days.union(t)).interpolate(method="time", limit_area="inside").reindex(days)
    prev = pd.Series(t, index=t).reindex(days, method="ffill")
    nxt = pd.Series(t, index=t).reindex(days, method="bfill")
    gap = (nxt - prev).dt.days.to_numpy()
    ok = np.isfinite(full.to_numpy()) & (gap <= max_gap_days)
    if months is not None:
        ok &= (days.month >= months[0]) & (days.month <= months[1])
    kobs = pd.Series(np.where(ok, full.to_numpy(), np.nan), index=days)

    doy_obs = kobs.dropna().index.dayofyear.to_numpy()
    val_obs = kobs.dropna().to_numpy()
    clim = np.full(366, np.nan)
    for d in range(1, 367):
        dist = np.abs(doy_obs - d)
        dist = np.minimum(dist, 366 - dist)
        sel = dist <= 15
        if sel.sum() >= 30:
            clim[d - 1] = val_obs[sel].mean()
    # circular linear interpolation across DOYs without observations (winter for IV-X products)
    x = np.arange(1, 367)
    good = np.isfinite(clim)
    clim = np.interp(x, np.concatenate([x[good] - 366, x[good], x[good] + 366]),
                     np.tile(clim[good], 3))
    kclim = pd.Series(clim[days.dayofyear.to_numpy() - 1], index=days)
    used = kobs.where(kobs.notna(), kclim)
    return pd.DataFrame({"kcb": used, "kcb_clim": kclim, "kcb_obs": kobs,
                         "source": np.where(kobs.notna(), "obs", "clim")}, index=days)


# ----------------------------------------------------------------------------- soil water balance
def fao56_dual(rain_mm: np.ndarray, et0_mm: np.ndarray, kcb: np.ndarray, *, theta_fc: float, theta_wp: float,
               zr_m: float, ze_m: float, rew_mm: float, p_base: float, h_m: float, kc_min: float,
               kc_max_climate: float, dr0_mm: float) -> dict:
    """Daily FAO-56 dual crop coefficient water balance (mirror of pyfao56 Model._advance, method 'D').

    kc_max_climate = 1.2 + [0.04(u2-2) - 0.004(RHmin-45)](h/3)^0.3 ; with u2 and RHmin unavailable
    (Hargreaves forcing) we use u2 = 2 m/s, RHmin = 45 % -> 1.2 (FAO-56 eq. 72 standard climate).
    Returns arrays: Dr (end of day), De, Ks, Ke, Kr, fc, E, T, ETa, DP, RSW = 1 - Dr/TAW.
    """
    n = len(rain_mm)
    assert len(et0_mm) == n and len(kcb) == n
    assert np.all(np.isfinite(rain_mm)) and np.all(np.isfinite(et0_mm)) and np.all(np.isfinite(kcb))
    assert theta_fc > theta_wp > 0
    taw = 1000.0 * (theta_fc - theta_wp) * zr_m                 # FAO-56 eq. 82
    tew = 1000.0 * (theta_fc - 0.5 * theta_wp) * ze_m           # FAO-56 eq. 73
    assert tew > rew_mm > 0
    dr, de, fw = float(dr0_mm), tew, 1.0                         # De starts dry (pyfao56 convention)
    out = {k: np.empty(n) for k in ("Dr", "De", "Ks", "Ke", "Kr", "fc", "E", "T", "ETa", "DP", "p")}
    for i in range(n):
        kb = kcb[i]
        kcmax = max(kc_max_climate, kb + 0.05)                   # eq. 72
        fc = min(max(((kb - kc_min) / (kcmax - kc_min)) ** (1.0 + 0.5 * h_m) if kb > kc_min else 0.0, 0.0), 0.99)  # eq. 76
        r = rain_mm[i]
        if r >= 3.0:
            fw = 1.0
        few = min(max(min(1.0 - fc, fw), 0.01), 1.0)              # eq. 75
        kr = min(max((tew - de) / (tew - rew_mm), 0.0), 1.0)     # eq. 74
        ke = min(kr * (kcmax - kb), few * kcmax)                 # eq. 71
        e = ke * et0_mm[i]
        dpe = max(r - de, 0.0)                                   # eq. 79
        de = min(max(de - r + e / few + dpe, 0.0), tew)          # eqs. 77-78
        etc = (ke + kb) * et0_mm[i]
        p = min(max(p_base + 0.04 * (5.0 - etc), 0.1), 0.8)      # FAO-56 p.162
        raw = p * taw
        ks = min(max((taw - dr) / (taw - raw), 0.0), 1.0)        # eq. 84 (Dr at start of day)
        t = ks * kb * et0_mm[i]
        eta = t + e                                              # eq. 80
        dp = max(r - eta - dr, 0.0)                              # eq. 88
        dr = min(max(dr - r + eta + dp, 0.0), taw)               # eqs. 85-86
        for k, v in (("Dr", dr), ("De", de), ("Ks", ks), ("Ke", ke), ("Kr", kr), ("fc", fc), ("E", e),
                     ("T", t), ("ETa", eta), ("DP", dp), ("p", p)):
            out[k][i] = v
    out["TAW"] = taw
    out["TEW"] = tew
    out["RSW"] = 1.0 - out["Dr"] / taw
    out["SEW"] = 1.0 - out["De"] / tew
    return out


def run_wb(forcing: pd.DataFrame, kcb: pd.Series, soil: dict) -> pd.DataFrame:
    """forcing: columns precip_mm, et0 (daily, continuous); kcb aligned on the same index."""
    assert forcing.index.equals(kcb.index)
    res = fao56_dual(forcing["precip_mm"].to_numpy(float), forcing["et0"].to_numpy(float),
                     kcb.to_numpy(float), **soil)
    cols = {k: v for k, v in res.items() if np.ndim(v) == 1}
    df = pd.DataFrame(cols, index=forcing.index)
    df["kcb"] = kcb.to_numpy()
    df.attrs["TAW"], df.attrs["TEW"] = res["TAW"], res["TEW"]
    return df
