"""Event skill of L2 vs RZ by season (paired year-block bootstrap), operational 1991-2020 base and 2016-2024 base.
Uses repo dekad_end and the repo ISMN QC (same as baseline)."""
import sys
import numpy as np
import pandas as pd
sys.dont_write_bytecode = True
REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
sys.path.insert(0, REPO); sys.path.insert(0, f"{SCR}/exp_sm_verify")
import warnings; warnings.filterwarnings("ignore")  # noqa
from step_04_metrics_alert import dekad_end, clim_anomaly  # noqa
from v0_core import zclim  # noqa
import step_07_station_pipeline as s7  # noqa

e = pd.read_csv(f"{SCR}/drive_data/era5_land_daily.csv", parse_dates=["time"]).set_index("time").sort_index()
e = e[~e.index.duplicated(keep="last")]
rz = (7 * e.sm_l1 + 21 * e.sm_l2 + 72 * e.sm_l3) / 100
ov = {"PROJECT_DIR": REPO}
ref = pd.concat([s7.insitu_daily_depth(0.2, ov)["sm"], s7.insitu_daily_depth(0.3, ov)["sm"]], axis=1).dropna().mean(axis=1)


def dk(z):
    z = z.dropna()
    return pd.Series(z.to_numpy(), index=pd.DatetimeIndex(dekad_end(pd.Series(z.index)).to_numpy())).groupby(level=0).mean()


obs = dk(zclim(ref))
P = {}
for lab, s in (("RZ", rz), ("L2", e.sm_l2)):
    zop = clim_anomaly(s, ("1991-01-01", "2020-12-31"), 15, min_n=30)["z"].loc["2016-01-01":"2024-12-31"]
    P[f"{lab}_op"] = dk(zop)
    P[f"{lab}_val"] = dk(zclim(s.loc["2016":"2024"]))
    print(f"{lab}: share daily z<=-1 2016-2024: op base {(zop<=-1).mean():.3f}, own base {(zclim(s.loc['2016':'2024'])<=-1).mean():.3f}")
J = pd.DataFrame(P).join(obs.rename("obs"), how="inner").dropna()
print("n dekads", len(J), " obs events", int((J.obs <= -1).sum()))


def sc(o, f):
    h = (o & f).sum(); m = (o & ~f).sum(); fa = (~o & f).sum()
    return np.array([h / (h + m) if h + m else np.nan, fa / (h + fa) if h + fa else np.nan,
                     h / (h + m + fa) if h + m + fa else np.nan, h, m, fa])


rng = np.random.default_rng(0)
yrs = J.index.year.to_numpy(); Y = np.unique(yrs)
draws = [rng.choice(Y, len(Y)) for _ in range(3000)]
seas = {"all": range(1, 13), "IV-X": range(4, 11), "VII-X": range(7, 11), "XI-III": [11, 12, 1, 2, 3]}
rows = []
for base in ("op", "val"):
    for sn, ms in seas.items():
        S = J[J.index.month.isin(list(ms))]
        O = (S.obs <= -1).to_numpy(); yy = S.index.year.to_numpy()
        fa_, fb_ = (S[f"L2_{base}"] <= -1).to_numpy(), (S[f"RZ_{base}"] <= -1).to_numpy()
        a, b = sc(O, fa_), sc(O, fb_)
        ds = []
        for d in draws:
            ii = np.concatenate([np.flatnonzero(yy == y) for y in d])
            ds.append(sc(O[ii], fa_[ii])[:3] - sc(O[ii], fb_[ii])[:3])
        ds = np.array(ds)
        lo, hi = np.nanpercentile(ds, 2.5, axis=0), np.nanpercentile(ds, 97.5, axis=0)
        rows.append({"base": base, "season": sn, "n": len(S), "obs_ev": int(O.sum()),
                     "L2_hit/miss/fa": f"{int(a[3])}/{int(a[4])}/{int(a[5])}", "RZ_hit/miss/fa": f"{int(b[3])}/{int(b[4])}/{int(b[5])}",
                     "L2_csi": a[2], "RZ_csi": b[2], "dCSI": a[2] - b[2], "dCSI_lo": lo[2], "dCSI_hi": hi[2],
                     "dPOD": a[0] - b[0], "dPOD_lo": lo[0], "dPOD_hi": hi[0]})
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).round(3).to_string(index=False))

# 2017 dekads
print("\n2017 dekadal z (obs vs op-base RZ/L2), months IV-X:")
k = J.loc["2017-04":"2017-10", ["obs", "RZ_op", "L2_op"]]
print(k.round(2).T.to_string())
