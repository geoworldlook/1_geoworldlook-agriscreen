"""Independent re-check of the baseline and the ERA5 depth diagnostic (Experiment B review).

Independent pieces: ERA5 loading, root-zone weighting, DOY anomaly (own implementation, cross-checked
against step_04.clim_anomaly), block bootstrap (own, several block lengths incl. moving blocks).
Shared piece (unavoidable): ISMN reading/QC via step_07.insitu_daily_depth (repo, read-only).
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
logging.disable(logging.CRITICAL)
import step_04_metrics_alert as s4  # noqa: E402
import step_07_station_pipeline as s7  # noqa: E402

COMMON = ("2016-01-01", "2024-12-31")


def own_anom(s, ref, hw=15, min_n=20):
    s = s.dropna().sort_index()
    r = s.loc[ref[0]:ref[1]]
    rd, rv = r.index.dayofyear.to_numpy(), r.to_numpy(float)
    doy = s.index.dayofyear.to_numpy()
    z = np.full(len(s), np.nan)
    for d in np.unique(doy):
        dist = np.abs(rd - d)
        dist = np.minimum(dist, 366 - dist)
        pool = rv[dist <= hw]
        if len(pool) < min_n:
            continue
        sel = doy == d
        z[sel] = (s.to_numpy(float)[sel] - pool.mean()) / pool.std(ddof=1)
    return pd.Series(z, index=s.index)


def boot_r(x, y, block_days, n=1000, seed=7, moving=False, fn=None):
    p = pd.concat([x.rename("x"), y.rename("y")], axis=1, join="inner").dropna()
    t = p.index
    xv, yv = p["x"].to_numpy(), p["y"].to_numpy()
    rng = np.random.default_rng(seed)
    if not moving:
        blk = ((t - t.min()) / pd.Timedelta(days=block_days)).astype(int).to_numpy()
        ub = np.unique(blk)
        by = {b: np.flatnonzero(blk == b) for b in ub}
        st = []
        for _ in range(n):
            idx = np.concatenate([by[b] for b in rng.choice(ub, len(ub))])
            st.append(np.corrcoef(xv[idx], yv[idx])[0, 1])
    else:  # moving block bootstrap on the row index (days with data)
        L = block_days
        N = len(xv)
        k = int(np.ceil(N / L))
        st = []
        for _ in range(n):
            starts = rng.integers(0, N - L + 1, k)
            idx = np.concatenate([np.arange(s0, s0 + L) for s0 in starts])[:N]
            st.append(np.corrcoef(xv[idx], yv[idx])[0, 1])
    return float(np.corrcoef(xv, yv)[0, 1]), float(np.percentile(st, 2.5)), float(np.percentile(st, 97.5)), len(p)


def boot_dr(xa, xb, y, block_days, n=2000, seed=11):
    p = pd.concat([xa.rename("a"), xb.rename("b"), y.rename("y")], axis=1, join="inner").dropna()
    t = p.index
    a, b, yy = p["a"].to_numpy(), p["b"].to_numpy(), p["y"].to_numpy()
    if block_days == "year":
        blk = t.year.to_numpy()
    else:
        blk = ((t - t.min()) / pd.Timedelta(days=block_days)).astype(int).to_numpy()
    ub = np.unique(blk)
    by = {k: np.flatnonzero(blk == k) for k in ub}
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n):
        idx = np.concatenate([by[k] for k in rng.choice(ub, len(ub))])
        d.append(np.corrcoef(a[idx], yy[idx])[0, 1] - np.corrcoef(b[idx], yy[idx])[0, 1])
    ra, rb = np.corrcoef(a, yy)[0, 1], np.corrcoef(b, yy)[0, 1]
    return dict(ra=round(ra, 4), rb=round(rb, 4), d=round(ra - rb, 4), lo=round(float(np.percentile(d, 2.5)), 4),
                hi=round(float(np.percentile(d, 97.5)), 4), n=len(p))


e = pd.read_csv(f"{SCR}/drive_data/era5_land_daily.csv", parse_dates=["time"]).set_index("time").sort_index()
e = e[~e.index.duplicated(keep="last")]
rz = (7 * e.sm_l1 + 21 * e.sm_l2 + 72 * e.sm_l3) / 100
e28 = (7 * e.sm_l1 + 21 * e.sm_l2) / 28
l2 = e.sm_l2
l3 = e.sm_l3

ov = {"PROJECT_DIR": REPO}
d20 = s7.insitu_daily_depth(0.20, ov)["sm"]
d30 = s7.insitu_daily_depth(0.30, ov)["sm"]
d10 = s7.insitu_daily_depth(0.10, ov)["sm"]
ins = pd.concat([d20, d30], axis=1).dropna().mean(axis=1)

y = own_anom(ins.loc[COMMON[0]:COMMON[1]], COMMON)
y10 = own_anom(d10.loc[COMMON[0]:COMMON[1]], COMMON)
zs = {k: own_anom(v.loc[COMMON[0]:COMMON[1]], COMMON) for k, v in
      {"rz": rz, "e28": e28, "l1": e.sm_l1, "l2": l2, "l3": l3}.items()}

# cross-check own anomaly vs repo
zr_repo = s4.clim_anomaly(rz.loc[COMMON[0]:COMMON[1]], COMMON, 15, min_n=20)["z"]
out = {"maxabs_own_vs_repo_anom": float((zs["rz"] - zr_repo).abs().max())}
out["ismn_days"] = int(ins.loc[COMMON[0]:COMMON[1]].shape[0])
for k, z in zs.items():
    res = {}
    for bl, mv in ((30, False), (90, False), (365, False), (60, True), (180, True)):
        r, lo, hi, n = boot_r(z, y, bl, moving=mv)
        res[f"{'mbb' if mv else 'cal'}{bl}"] = (round(r, 4), round(lo, 4), round(hi, 4), n)
    out[f"R_{k}_vs_ismn2030"] = res
    out[f"R_{k}_vs_ismn10"] = boot_r(z, y10, 30)

season = {"IV-X": lambda s: s[(s.index.month >= 4) & (s.index.month <= 10)],
          "XI-III": lambda s: s[(s.index.month >= 11) | (s.index.month <= 3)],
          "VI-IX": lambda s: s[(s.index.month >= 6) & (s.index.month <= 9)]}
for k in ("e28", "l2", "l1"):
    for bl in (30, 90, "year"):
        out[f"dR_{k}_minus_rz_all_{bl}"] = boot_dr(zs[k], zs["rz"], y, bl)
    for sn, f in season.items():
        out[f"dR_{k}_minus_rz_{sn}_30"] = boot_dr(f(zs[k]), f(zs["rz"]), f(y), 30)
        out[f"dR_{k}_minus_rz_{sn}_year"] = boot_dr(f(zs[k]), f(zs["rz"]), f(y), "year")

# per-year
p = pd.concat([zs["rz"].rename("rz"), zs["e28"].rename("e28"), zs["l2"].rename("l2"), y.rename("y")], axis=1).dropna()
out["per_year"] = p.groupby(p.index.year).apply(
    lambda g: pd.Series({c: round(np.corrcoef(g[c], g["y"])[0, 1], 3) for c in ("rz", "e28", "l2")})).to_dict()

# autocorrelation of the residual (to judge block length)
res = (p["y"] - p["rz"] * np.polyfit(p["rz"], p["y"], 1)[0])
full = res.asfreq("D")
out["acf_lag30_ismn_z"] = float(y.asfreq("D").autocorr(30))
out["acf_lag90_ismn_z"] = float(y.asfreq("D").autocorr(90))
out["acf_lag30_resid"] = float(full.autocorr(30))
out["acf_lag60_resid"] = float(full.autocorr(60))

# events
def dk(z):
    z = z.dropna()
    k = s4.dekad_end(pd.Series(z.index)).to_numpy()
    return pd.Series(z.to_numpy(), index=k).groupby(level=0).mean()


def pf(p_, o_):
    j = pd.concat([p_.rename("p"), o_.rename("o")], axis=1, join="inner").dropna()
    ob, pr = j.o <= -1, j.p <= -1
    h, m, f_ = int((ob & pr).sum()), int((ob & ~pr).sum()), int((~ob & pr).sum())
    return dict(pod=round(h / (h + m), 3), far=round(f_ / (h + f_), 3), h=h, m=m, fa=f_, n=len(j), n_obs=int(ob.sum()),
                n_pred=int(pr.sum()))


ydk = dk(y)
REF = ("1991-01-01", "2020-12-31")
for k, v in {"rz": rz, "e28": e28, "l2": l2}.items():
    zo = own_anom(v, REF, 15, min_n=30).loc["2016":]
    out[f"events_{k}_oper"] = pf(dk(zo), ydk)
    out[f"events_{k}_common"] = pf(dk(zs[k]), ydk)
    ivx = lambda s: s[(s.index.month >= 4) & (s.index.month <= 10)]
    out[f"events_{k}_oper_IVX"] = pf(ivx(dk(zo)), ivx(ydk))
    # mean operational z over 2016-2024
    out[f"mean_oper_z_2016_2024_{k}"] = round(float(zo.loc["2016":"2024"].mean()), 3)
st = pd.read_csv(f"{SCR}/drive_data/gwl_status.csv")
print(st.columns.tolist(), st.site_id.unique())
st = st.drop_duplicates("date")
st["date"] = pd.to_datetime(st["date"])
out["events_registry"] = pf(st.set_index("date")["sma_rz"], ydk)
print(json.dumps(out, indent=1, default=str))
json.dump(out, open(f"{OUT}/v1_baseline_and_depth.json", "w"), indent=1, default=str)
