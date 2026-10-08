"""A4: what the vegetation layer does to the dekadal ALERT (v1.0 build_status logic), per variant.

alert = ERA5-Land RZ SMA <= -1 (warning) AND last vegetation anomaly (<= 30 d old) <= -1.
Reference: ISMN 20-30 cm dekadal mean z <= -1 (as validate_anomalies, section 4). In-season dekads 2016-2024.
Question: does the vegetation confirmation raise the precision of 'warning' (P(ISMN dry | flag))?
"""
import logging
import warnings

import numpy as np
import pandas as pd

from common import OUT, DATA, era5, ins_z, s4

logging.basicConfig(level=logging.WARNING)
warnings.filterwarnings("ignore")

CFG = {"CLIM_REF": ("1991-01-01", "2020-12-31"), "CLIM_HALF_WINDOW_DAYS": 15, "SPI_DAYS": (30, 90),
       "S2_MONTHS": (4, 10), "VEG_MAX_AGE_DAYS": 30, "THR_SPI1": -2.0, "THR_SPI3": -1.0, "THR_SMA": -1.0,
       "THR_VEG": -1.0}
e = era5().reset_index(drop=True)
an = s4.era5_anomalies(e, CFG)

y = ins_z("rz")
tmp = pd.DataFrame({"z": y.to_numpy(), "dk": s4.dekad_end(pd.Series(y.index)).to_numpy()})
ins_dk = tmp.groupby("dk")["z"].mean()

ser = pd.read_csv(f"{OUT}/a2_variant_series.csv", index_col=0, parse_dates=True)
VARS = ["B0_ndvi_scene", "V1b_ndvi_whittaker_RT", "V1c_ndvi_trailing30d", "V3a_ndmi_scene",
        "V3d_meanz_ndvi_ndmi_crswir", "V6_harmonic_loyo"]


def status_for(zs: pd.Series, months=(4, 10)):
    v = pd.DataFrame({"site_id": "VINEYARD_06", "time": zs.dropna().index + pd.Timedelta(hours=11),
                      "z": zs.dropna().to_numpy(), "product": zs.name})
    st = s4.build_status(an, v, "VINEYARD_06", dict(CFG, S2_MONTHS=months), "2016-01-01")
    st["date"] = pd.to_datetime(st["date"])
    return st.set_index("date")


def skill(flag, obs):
    h, fa, m = int((flag & obs).sum()), int((flag & ~obs).sum()), int((~flag & obs).sum())
    cn = int((~flag & ~obs).sum())
    n = h + fa + m + cn
    exp = ((h + m) * (h + fa) + (cn + m) * (cn + fa)) / n
    return dict(n_flag=h + fa, hits=h, precision=h / (h + fa) if h + fa else np.nan,
                pod=h / (h + m) if h + m else np.nan, hss=(h + cn - exp) / (n - exp) if n != exp else np.nan)


def year_boot_prec_diff(j, col_a, col_b, n_boot=2000, seed=42):
    """Year-block bootstrap CI of precision(alert) - precision(warning)."""
    rng = np.random.default_rng(seed)
    yrs = j.index.year.to_numpy()
    uy = np.unique(yrs)
    out = []
    for _ in range(n_boot):
        idx = np.concatenate([np.flatnonzero(yrs == k) for k in rng.choice(uy, len(uy))])
        q = j.iloc[idx]
        pa = q.loc[q[col_a], "obs"].mean() if q[col_a].any() else np.nan
        pb = q.loc[q[col_b], "obs"].mean() if q[col_b].any() else np.nan
        out.append(pa - pb)
    out = np.asarray(out)
    out = out[np.isfinite(out)]
    return np.percentile(out, 2.5), np.percentile(out, 97.5)


rows = []
# sanity: v1.0 status from registry (VINEYARD_06) vs recomputed B0 status
reg = pd.read_csv(f"{DATA}/gwl_status.csv")
reg = reg[reg.site_id == "VINEYARD_06"].copy()
reg["date"] = pd.to_datetime(reg["date"])
reg = reg.set_index("date")
for var in VARS:
    for months, tag in (((4, 10), "IV-X"), ((6, 9), "VI-IX")):
        st = status_for(ser[var].rename(var), months)
        if var == "B0_ndvi_scene" and tag == "IV-X":
            jj = st.join(reg["cdi_level"].rename("reg"), how="inner")
            jj = jj[jj.index <= "2024-12-31"]
            print("status agreement recomputed B0 vs registry (2016-2024):",
                  round(float((jj["cdi_level"] == jj["reg"]).mean()), 3), "n", len(jj),
                  "alerts reg/recomp:", int((jj["reg"] == 3).sum()), int((jj["cdi_level"] == 3).sum()))
        j = st.join(ins_dk.rename("ins"), how="inner").dropna(subset=["ins", "sma_rz"])
        j = j[(j.index <= "2024-12-31") & j.index.month.isin(range(4, 11))]   # in-season dekads (IV-X)
        j["obs"] = j["ins"] <= -1
        j["warn"] = j["cdi_level"] >= 2
        j["alert"] = j["cdi_level"] == 3
        sw, sa = skill(j["warn"], j["obs"]), skill(j["alert"], j["obs"])
        lo, hi = year_boot_prec_diff(j, "alert", "warn")
        alert_years = j[j["alert"]].groupby(j[j["alert"]].index.year).size().to_dict()
        rows.append(dict(variant=var, veg_months=tag, n_dekads=len(j), n_obs_dry=int(j["obs"].sum()),
                         warn_n=sw["n_flag"], warn_precision=sw["precision"], warn_pod=sw["pod"],
                         alert_n=sa["n_flag"], alert_hits=sa["hits"], alert_precision=sa["precision"],
                         alert_pod=sa["pod"], alert_hss=sa["hss"], dprec_alert_minus_warn=sa["precision"] - sw["precision"],
                         dprec_lo=lo, dprec_hi=hi, alert_years=str(alert_years)))
out = pd.DataFrame(rows)
out.to_csv(f"{OUT}/a4_alert_eval.csv", index=False)
pd.set_option("display.width", 250, "display.max_colwidth", 80)
print(out.round(3).to_string(index=False))
