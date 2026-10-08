import os, sys, warnings, logging
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); logging.basicConfig(level=logging.WARNING)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from v0_base import load_obs, scene_z, R, VD, REPO, SCR, block_ci, year_ci, clim_z
import step_04_metrics_alert as s4
y = pd.read_csv(os.path.join(VD, "ismn_rz.csv"), index_col=0, parse_dates=True)["ismn_rz_z"]
w = load_obs()
g = w[(w.site_id == "VINEYARD_06") & (w["product"] == "S2SR_2.5m")]
b0 = scene_z(g, "ndvi")

# ---- decomposition (covariance share)
p = b0.to_frame("x").join(y.rename("y")).dropna()
xm = p.groupby(p.index.year).x.transform("mean"); ym = p.groupby(p.index.year).y.transform("mean")
xc, yc = p.x - p.x.mean(), p.y - p.y.mean()
cov_tot = (xc * yc).sum(); cov_b = ((xm - p.x.mean()) * (ym - p.y.mean())).sum(); cov_w = ((p.x - xm) * (p.y - ym)).sum()
print("cov share between-year = %.2f, within = %.2f" % (cov_b / cov_tot, cov_w / cov_tot))
print("var share between-year x = %.2f, y = %.2f" % (((xm - p.x.mean())**2).sum() / (xc**2).sum(), ((ym - p.y.mean())**2).sum() / (yc**2).sum()))
wx, wy = (p.x - xm).to_numpy(), (p.y - ym).to_numpy()
print("within-year R %.3f; 30d CI" % R(wx, wy), np.round(block_ci(p.index, wx, wy, R), 3))

# ---- partial R | ERA5 (2016-2024 clim) with both CI methods
e = pd.read_csv(os.path.join(SCR, "drive_data/era5_land_daily.csv"), parse_dates=["time"])
e = e.set_index(e.time.dt.floor("D")); e = e[~e.index.duplicated(keep="last")].sort_index()
ez = clim_z(s4.rootzone(e.loc["2016":"2024"]))
q = p.join(ez.rename("e")).dropna()
def pr(i):
    qq = q.iloc[i]; A = np.c_[np.ones(len(qq)), qq.e]
    rx = qq.x - A @ np.linalg.lstsq(A, qq.x, rcond=None)[0]; ry = qq.y - A @ np.linalg.lstsq(A, qq.y, rcond=None)[0]
    return R(rx, ry)
idx = np.arange(len(q))
print("ERA5 vs ISMN on scene days R=%.3f; veg vs ERA5 R=%.3f" % (R(q.e, q.y), R(q.x, q.e)))
print("partial R veg|ERA5 = %.3f; 30d-block CI" % pr(idx), np.round(block_ci(q.index, idx, idx, lambda a, b: pr(a)), 3),
      "year CI", np.round(year_ci(q.index, idx, idx, lambda a, b: pr(a)), 3))
# Does veg improve ERA5 regression for ISMN? LOYO CV R of y ~ e vs y ~ e + x
pred1, pred2 = [], []
for yv in sorted(set(q.index.year)):
    tr, te = q[q.index.year != yv], q[q.index.year == yv]
    b1 = np.linalg.lstsq(np.c_[np.ones(len(tr)), tr.e], tr.y, rcond=None)[0]
    b2 = np.linalg.lstsq(np.c_[np.ones(len(tr)), tr.e, tr.x], tr.y, rcond=None)[0]
    pred1.append(pd.Series(np.c_[np.ones(len(te)), te.e] @ b1, te.index)); pred2.append(pd.Series(np.c_[np.ones(len(te)), te.e, te.x] @ b2, te.index))
p1, p2 = pd.concat(pred1), pd.concat(pred2)
print("LOYO-CV R(ISMN, ERA5 only)=%.3f, R(ISMN, ERA5+veg)=%.3f, RMSE %.3f vs %.3f" % (R(p1, q.y.reindex(p1.index)), R(p2, q.y.reindex(p2.index)),
      np.sqrt(((p1 - q.y) ** 2).mean()), np.sqrt(((p2 - q.y) ** 2).mean())))

# ---- dekadal alert vs warning
CFG = {"CLIM_REF": ("1991-01-01", "2020-12-31"), "CLIM_HALF_WINDOW_DAYS": 15, "SPI_DAYS": (30, 90), "S2_MONTHS": (4, 10),
       "VEG_MAX_AGE_DAYS": 30, "THR_SPI1": -2.0, "THR_SPI3": -1.0, "THR_SMA": -1.0, "THR_VEG": -1.0}
an = s4.era5_anomalies(e.reset_index(drop=True), CFG)
veg = pd.DataFrame({"site_id": "VINEYARD_06", "time": b0.index + pd.Timedelta(hours=11), "z": b0.values, "product": "S2SR_2.5m"})
st = s4.build_status(an, veg, "VINEYARD_06", CFG, "2016-01-01"); st["date"] = pd.to_datetime(st["date"]); st = st.set_index("date")
reg = pd.read_csv(os.path.join(SCR, "drive_data/gwl_status.csv")); reg = reg[reg.site_id == "VINEYARD_06"]; reg["date"] = pd.to_datetime(reg["date"])
jj = st.join(reg.set_index("date")["cdi_level"].rename("reg"), how="inner"); jj = jj[jj.index <= "2024-12-31"]
print("agreement with registry status: %.3f n=%d alerts reg %d mine %d" % ((jj.cdi_level == jj.reg).mean(), len(jj), (jj.reg == 3).sum(), (jj.cdi_level == 3).sum()))
ins_dk = pd.DataFrame({"z": y.values, "dk": s4.dekad_end(pd.Series(y.index)).values}).groupby("dk").z.mean()
j = st.join(ins_dk.rename("ins"), how="inner").dropna(subset=["ins", "sma_rz"])
j = j[(j.index <= "2024-12-31") & j.index.month.isin(range(4, 11))]
obs = j.ins <= -1; warn = j.cdi_level >= 2; alert = j.cdi_level == 3
print("in-season dekads", len(j), "obs dry", obs.sum(), "| warn n", warn.sum(), "prec %.3f" % obs[warn].mean(), "| alert n", alert.sum(), "prec %.3f" % obs[alert].mean())
print("alert dekads:\n", j[alert][["sma_rz", "veg_z", "veg_age_days", "ins"]].round(2).to_string())
# precision of a random 16-of-44 subset of warnings (null distribution)
rng = np.random.default_rng(0); wi = np.flatnonzero(warn.to_numpy()); ob = obs.to_numpy()
sims = [ob[rng.choice(wi, alert.sum(), replace=False)].mean() for _ in range(20000)]
print("random subset of warnings precision: mean %.3f, P(<=0.25)=%.3f" % (np.mean(sims), np.mean(np.array(sims) <= obs[alert].mean())))
# All-dekad (not only in-season) ERA5 warning POD/FAR as in v1.0 report
jall = st.join(ins_dk.rename("ins"), how="inner").dropna(subset=["ins", "sma_rz"]); jall = jall[jall.index <= "2024-12-31"]
o2, p2_ = jall.ins <= -1, jall.sma_rz <= -1
print("all dekads n=%d POD=%.3f FAR=%.3f" % (len(jall), (o2 & p2_).sum() / o2.sum(), (~o2 & p2_).sum() / p2_.sum()))
