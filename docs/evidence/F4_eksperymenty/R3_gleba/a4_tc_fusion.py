import warnings; warnings.filterwarnings("ignore")
import os
import pandas as pd, numpy as np
from common import DRIVE, insitu, ismn_rz, zclim, s7, era5, COMMON, r_ci, swi_regular, rootzone, paired_diff_ci, dekad_end

o = pd.read_csv(os.path.join(DRIVE, "gwl_observations.csv"))
o = o[(o.site_id == "SMOSMANIA_Condom") & (o["product"] == "S1_CD_A") & (o.variable == "sm_s1")]
o["time"] = pd.to_datetime(o["time_utc"]).dt.tz_localize(None)
sm = o.set_index("time")["value"].sort_index()

e = era5(); e_c = e.loc[COMMON[0]:COMMON[1]]
rz = ismn_rz(); z_ins = zclim(rz)
z_rz = zclim(rootzone(e_c)); z_028 = zclim((7 * e_c.sm_l1 + 21 * e_c.sm_l2) / 28)

def swi_s1(T):
    sw = swi_regular(sm, T)
    return sw.groupby(sw.index.floor("D")).last().asfreq("D").ffill(limit=6)
z_s1 = zclim(swi_s1(10))

def etc(x, y, z):
    """Extended TC (McColl 2014): correlation of each with unknown truth; and pytesmo error std."""
    d = pd.concat([x, y, z], axis=1).dropna().to_numpy()
    Q = np.cov(d.T)
    R2 = [Q[0,1]*Q[0,2]/(Q[0,0]*Q[1,2]), Q[0,1]*Q[1,2]/(Q[1,1]*Q[0,2]), Q[0,2]*Q[1,2]/(Q[2,2]*Q[0,1])]
    import pytesmo.metrics as pm
    snr, err, beta = pm.tcol_metrics(d[:,0], d[:,1], d[:,2], ref_ind=2)
    return np.sqrt(np.clip(R2, 0, None)), snr, err, len(d)

def etc_boot(x, y, z, nb=500, block=30, seed=1):
    d = pd.concat([x, y, z], axis=1).dropna()
    t = pd.Series(d.index); blk = ((t - t.min()) / pd.Timedelta(days=block)).astype(int).to_numpy()
    u = np.unique(blk); ib = {k: np.flatnonzero(blk == k) for k in u}
    rng = np.random.default_rng(seed); A = d.to_numpy(); out = []
    for _ in range(nb):
        idx = np.concatenate([ib[k] for k in rng.choice(u, len(u))])
        Q = np.cov(A[idx].T)
        out.append([Q[0,1]*Q[0,2]/(Q[0,0]*Q[1,2]), Q[0,1]*Q[1,2]/(Q[1,1]*Q[0,2]), Q[0,2]*Q[1,2]/(Q[2,2]*Q[0,1])])
    out = np.sqrt(np.clip(np.array(out), 0, 1))
    return np.percentile(out, 2.5, axis=0).round(2), np.percentile(out, 97.5, axis=0).round(2)

for lab, x in (("ERA5 RZ", z_rz), ("ERA5 0-28", z_028)):
    R, snr, err, n = etc(x, z_s1, z_ins)
    lo, hi = etc_boot(x, z_s1, z_ins)
    print(f"ETC [{lab}, SWI(S1)T10, ISMN20-30] n={n}: R_truth = {R.round(3)}  CI lo {lo} hi {hi}  SNR(dB)={np.round(snr,1)}")

# 35-day anomaly version (short-term)
a = lambda s: s7._moving_anomaly(s, 35, 15)
R, snr, err, n = etc(a(rootzone(e_c)), a(swi_s1(10)), a(rz))
print("ETC 35d [ERA5 RZ, SWI S1, ISMN]:", R.round(3), n)

# Surface triplet: ERA5 L1, S1 raw daily, ISMN 5 cm  (35-d anomalies; drift-robust)
d05 = insitu(0.05)["sm"]
smd = sm.groupby(sm.index.floor("D")).mean()
R, snr, err, n = etc(a(e_c.sm_l1).reindex(smd.index), s7._moving_anomaly(smd, 35, 3), a(d05))
lo, hi = etc_boot(a(e_c.sm_l1).reindex(smd.index), s7._moving_anomaly(smd, 35, 3), a(d05))
print(f"ETC surface 35d [ERA5 L1, S1 CD, ISMN5] n={n}: R_truth={R.round(3)} lo {lo} hi {hi}")

# Fusion
res = []
def add(name, x):
    r, lo, hi, n = r_ci(x, z_ins); res.append((name, round(r,3), round(lo,3), round(hi,3), n))
add("ERA5 RZ (baseline)", z_rz)
add("ERA5 0-28", z_028)
add("SWI(S1) T10", z_s1)
f_eq = ((z_rz + z_s1) / 2); add("mean(ERA5 RZ, SWI S1)", f_eq)
f_eq2 = ((z_028 + z_s1) / 2); add("mean(ERA5 0-28, SWI S1)", f_eq2)
# TC/SNR-based weights from ETC R: w ~ R^2/(1-R^2)  (optimal for standardized series w/ independent errors)
R, *_ = etc(z_028, z_s1, z_ins)
w = R[:2]**2 / (1 - R[:2]**2); w = w / w.sum()
print("TC weights (ERA5 0-28, S1):", w.round(2))
add("TC-weighted(ERA5 0-28, SWI S1)", w[0] * z_028 + w[1] * z_s1)
# leave-one-year-out TC weights (honest)
zz = pd.concat([z_028.rename("e"), z_s1.rename("s"), z_ins.rename("y")], axis=1).dropna()
pred = pd.Series(index=zz.index, dtype=float)
for yr in sorted(zz.index.year.unique()):
    tr = zz[zz.index.year != yr]
    Rt, *_ = etc(tr.e, tr.s, tr.y)
    wt = Rt[:2]**2 / (1 - Rt[:2]**2); wt = wt / wt.sum()
    te = zz[zz.index.year == yr]
    pred.loc[te.index] = wt[0] * te.e + wt[1] * te.s
add("TC-weighted LOYO(ERA5 0-28, SWI S1)", pred)
f3 = (z_rz + z_028 + z_s1) / 3
print(pd.DataFrame(res, columns=["series", "R", "lo", "hi", "n"]).to_string(index=False))
print("paired diff mean(0-28,S1) - ERA5 RZ:", np.round(paired_diff_ci(f_eq2, z_rz, z_ins)[:3], 3))
print("paired diff mean(0-28,S1) - ERA5 0-28:", np.round(paired_diff_ci(f_eq2, z_028, z_ins)[:3], 3))
print("paired diff mean(RZ,S1) - ERA5 RZ:", np.round(paired_diff_ci(f_eq, z_rz, z_ins)[:3], 3))

# Dekadal drought-event skill (z<=-1 both) for candidates
def events(x, thr=-1.0):
    dk = pd.DataFrame({"x": x, "y": z_ins}).dropna()
    dk["dk"] = dekad_end(pd.Series(dk.index)).to_numpy()
    g = dk.groupby("dk").mean()
    ob, pr = g.y <= thr, g.x <= thr
    h, m, f = (ob & pr).sum(), (ob & ~pr).sum(), (~ob & pr).sum()
    cn = (~ob & ~pr).sum()
    pod, far = h / (h + m), f / (h + f)
    hss = 2 * (h * cn - f * m) / ((h + m) * (m + cn) + (h + f) * (f + cn))
    return round(pod, 3), round(far, 3), round(hss, 3), len(g), int(ob.sum())
for name, x in (("ERA5 RZ", z_rz), ("ERA5 0-28", z_028), ("SWI S1", z_s1), ("mean(0-28,S1)", f_eq2), ("mean(RZ,S1)", f_eq)):
    print("events", name, "POD, FAR, HSS, n_dekads, n_obs_events =", events(x))
