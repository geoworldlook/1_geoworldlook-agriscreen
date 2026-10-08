"""Independent re-check of the core claim: ERA5-Land L2 vs 0-100 cm anomaly R vs ISMN Condom 20-30 cm.

Own ISMN parser (flag G only, daily mean with >=12 h), own DOY climatology z, plus repo-based reference for exact match.
Adds: seasonal / monthly breakdown, block-length sensitivity, Bonferroni for 52 variants.
"""
import glob
import sys

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
sys.path.insert(0, REPO)
import warnings; warnings.filterwarnings("ignore")  # noqa

ISMN = f"{REPO}/data/7_isismn_data/SMOSMANIA"


def read_stm(path):
    rows = []
    with open(path) as f:
        hdr = f.readline().split()
        for line in f:
            p = line.split()
            rows.append((p[0] + " " + p[1], float(p[2]), p[3]))
    d = pd.DataFrame(rows, columns=["t", "v", "flag"])
    d["t"] = pd.to_datetime(d["t"], format="%Y/%m/%d %H:%M")
    return d, hdr


def daily(station, depth):
    fs = glob.glob(f"{ISMN}/{station}/*_sm_{depth:.6f}_{depth:.6f}_*.stm")
    out = []
    for f in fs:
        d, _ = read_stm(f)
        d = d[d.flag == "G"]
        g = d.set_index("t")["v"].resample("D")
        m, c = g.mean(), g.count()
        out.append(m[c >= 12])
    return pd.concat(out).sort_index().groupby(level=0).mean()


def zclim(s, ref=("2016-01-01", "2024-12-31"), hw=15, min_n=20):
    s = s.dropna().sort_index()
    r = s.loc[ref[0]:ref[1]]
    rd, rv = r.index.dayofyear.to_numpy(), r.to_numpy(float)
    doy = s.index.dayofyear.to_numpy()
    z = np.full(len(s), np.nan)
    for d in np.unique(doy):
        dd = np.abs(rd - d); dd = np.minimum(dd, 366 - dd)
        pool = rv[dd <= hw]
        if len(pool) < min_n:
            continue
        sel = doy == d
        z[sel] = (s.to_numpy()[sel] - pool.mean()) / pool.std(ddof=1)
    return pd.Series(z, index=s.index)


def blocks(idx, L):
    t = pd.Series(idx)
    b = ((t - t.min()) / pd.Timedelta(days=L)).astype(int).to_numpy()
    u = np.unique(b)
    return u, {k: np.flatnonzero(b == k) for k in u}


def dr_boot(A, B, Y, idx, L, n=4000, seed=1, qs=(2.5, 97.5)):
    u, ib = blocks(idx, L)
    rng = np.random.default_rng(seed)
    ds = np.empty(n)
    for i in range(n):
        ii = np.concatenate([ib[k] for k in rng.choice(u, len(u))])
        ds[i] = np.corrcoef(A[ii], Y[ii])[0, 1] - np.corrcoef(B[ii], Y[ii])[0, 1]
    return np.percentile(ds, qs), len(u)


if __name__ == "__main__":
    e = pd.read_csv(f"{SCR}/drive_data/era5_land_daily.csv", parse_dates=["time"]).set_index("time").sort_index()
    e = e[~e.index.duplicated(keep="last")].loc["2016-01-01":"2024-12-31"]
    rz = (7 * e.sm_l1 + 21 * e.sm_l2 + 72 * e.sm_l3) / 100
    l2 = e.sm_l2
    # independent ISMN
    d20, d30 = daily("Condom", 0.2), daily("Condom", 0.3)
    ref_ind = pd.concat([d20, d30], axis=1).dropna().mean(axis=1).loc["2016":"2024"]
    # repo ISMN (QC as v1.0)
    import step_07_station_pipeline as s7
    ov = {"PROJECT_DIR": REPO}
    r20 = s7.insitu_daily_depth(0.2, ov)["sm"]; r30 = s7.insitu_daily_depth(0.3, ov)["sm"]
    ref_repo = pd.concat([r20, r30], axis=1).dropna().mean(axis=1)
    print("n days independent ISMN:", len(ref_ind), " repo QC:", len(ref_repo))
    for lab, ref in (("indep", ref_ind), ("repo", ref_repo)):
        zi = zclim(ref)
        D = pd.concat([zclim(rz).rename("rz"), zclim(l2).rename("l2"), zi.rename("y")], axis=1).dropna()
        print(f"[{lab}] n={len(D)} R_rz={D.rz.corr(D.y):.3f} R_l2={D.l2.corr(D.y):.3f} dR={D.l2.corr(D.y)-D.rz.corr(D.y):.3f}")
    zi = zclim(ref_repo)
    D = pd.concat([zclim(rz).rename("rz"), zclim(l2).rename("l2"), zclim(e.sm_l3).rename("l3"), zi.rename("y")], axis=1).dropna()
    D.to_csv(f"{SCR}/exp_sm_verify/D_daily.csv")
    A, B, Y = D.l2.to_numpy(), D.rz.to_numpy(), D.y.to_numpy()
    print("\nBlock-length sensitivity of dR(L2-RZ) 95% CI:")
    for L in (30, 90, 180, 365):
        (lo, hi), nb = dr_boot(A, B, Y, D.index, L)
        print(f"  block {L:3d} d (n blocks {nb:3d}): [{lo:.3f},{hi:.3f}]")
    # 52-test Bonferroni: two-sided alpha/52
    q = 100 * 0.05 / 52 / 2
    for L in (90, 180):
        (lo, hi), nb = dr_boot(A, B, Y, D.index, L, n=20000, seed=3, qs=(q, 100 - q))
        print(f"  Bonferroni(52) {100-2*q:.3f}% CI, block {L}: [{lo:.3f},{hi:.3f}]")
    # lag-1 autocorrelation of z and of the per-day difference in squared errors (memory)
    for c in ("rz", "l2", "y"):
        s = D[c].asfreq("D")
        print(f"  ACF {c}: lag30={s.autocorr(30):.2f} lag90={s.autocorr(90):.2f}")
    print("\nSeasonal R (2016-2024 base clim z):")
    seas = {"DJF": [12, 1, 2], "MAM": [3, 4, 5], "JJA": [6, 7, 8], "SON": [9, 10, 11], "IV-X": list(range(4, 11)),
            "VII-X": [7, 8, 9, 10], "XI-III": [11, 12, 1, 2, 3]}
    rows = []
    for k, ms in seas.items():
        S = D[D.index.month.isin(ms)]
        (lo, hi), nb = dr_boot(S.l2.to_numpy(), S.rz.to_numpy(), S.y.to_numpy(), S.index, 30, n=2000)
        (lo9, hi9), _ = dr_boot(S.l2.to_numpy(), S.rz.to_numpy(), S.y.to_numpy(), S.index, 90, n=2000)
        rows.append({"season": k, "n": len(S), "R_rz": S.rz.corr(S.y), "R_l2": S.l2.corr(S.y), "R_l3": S.l3.corr(S.y),
                     "dR": S.l2.corr(S.y) - S.rz.corr(S.y), "lo30": lo, "hi30": hi, "lo90": lo9, "hi90": hi9})
    print(pd.DataFrame(rows).round(3).to_string(index=False))
    print("\nMonthly R:")
    m = D.groupby(D.index.month).apply(lambda g: pd.Series({"R_rz": g.rz.corr(g.y), "R_l2": g.l2.corr(g.y),
                                                              "R_l3": g.l3.corr(g.y), "n": len(g)}))
    print(m.round(3).to_string())
