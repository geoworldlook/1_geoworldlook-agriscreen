"""E1 - evaluate every run against ISMN 20-30 cm (v1.0 definitions) and write tables + figures.

Deterministic product = ensemble-mean theta2 (10-100 cm), anomaly z = step_04.clim_anomaly over 2016-2024
(+-15 d, min_n 20; identical to the ERA5/ISMN validation definition).  Probabilistic product = fraction of members
whose dekadal-mean z <= -1, member z w.r.t. the POOLED-member DOY climatology 2016-2024 (members are treated as
equally likely truths).  Periods: ALL = 2016-2024 (no ISMN used for V0-V3 / V1cdf / V3d), TEST = 2021-2024.
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as K  # noqa: E402
import config as C  # noqa: E402
import model as M  # noqa: E402

pd.set_option("display.width", 250)
meta = json.load(open(f"{K.OUT}/runs_meta.json"))["meta"]
e = K.era5()
ec = e.loc[C.COMMON[0]:C.COMMON[1]]
z_ins = K.z_common(K.ismn_ref())
ins_dk = K.to_dekad(z_ins)
z_era = K.z_common(K.s4.rootzone(ec))
z_era_l2 = K.z_common(ec["sm_l2"])
z_era_oper = K.z_oper(K.s4.rootzone(e)).loc["2016-01-01":]
det = pd.read_csv(f"{K.OUT}/det_openloop_1991_2024.csv", index_col=0, parse_dates=True)
TEST = lambda s: s[s.index.year.isin(C.TEST_YEARS)]  # noqa: E731
TRAIN = lambda s: s[s.index.year.isin(C.TRAIN_YEARS)]  # noqa: E731
base_rate_train = float((TRAIN(ins_dk) <= C.THR).mean())


def load(name):
    d = np.load(f"{K.OUT}/run_{name}.npz")
    idx = pd.DatetimeIndex(d["index"].astype("datetime64[ns]"))
    keep = (idx >= C.COMMON[0]) & (idx <= C.COMMON[1])
    return dict(index=idx[keep], th1=d["th1"][keep].astype(float), th2=d["th2"][keep].astype(float),
                fc2=d["fc2"].astype(float), fc2_index=idx)


def probabilistic(run):
    mu, sd = K.pooled_member_clim(run["th2"], run["index"], C.COMMON)
    zm = (run["th2"] - mu[:, None]) / sd[:, None]
    dk = K.dekad_frame(zm, run["index"])
    p = (dk <= C.THR).mean(axis=1)
    zmean = pd.Series(zm.mean(axis=1), index=run["index"])
    zsd = pd.Series(zm.std(axis=1, ddof=1), index=run["index"])
    return p, zmean, zsd, zm


def event_scores(z_daily, p_dk=None, sub=None):
    dk = K.to_dekad(z_daily)
    j = K.pair(dk, ins_dk, names=["p", "o"])
    if sub is not None:
        j = sub(j)
    o = (j["o"] <= C.THR).to_numpy()
    pf = K.pod_far((j["p"] <= C.THR).to_numpy(), o)
    out = dict(POD=pf["pod"], FAR=pf["far"], hits=pf["hits"], misses=pf["misses"], fa=pf["false_alarms"],
               n_dk=pf["n"], BS_det=K.brier((j["p"] <= C.THR).to_numpy().astype(float), o),
               BS_clim=K.brier(np.full(len(o), base_rate_train), o))
    if p_dk is not None:
        jj = K.pair(p_dk, ins_dk, names=["p", "o"])
        if sub is not None:
            jj = sub(jj)
        oo = (jj["o"] <= C.THR).to_numpy()
        out["BS_ens"] = K.brier(jj["p"].to_numpy(), oo)
        out["BSS_ens_vs_clim"] = 1 - out["BS_ens"] / K.brier(np.full(len(oo), base_rate_train), oo)
        out["frac_p_0_or_1"] = float(((jj["p"] == 0) | (jj["p"] == 1)).mean())
    return out


rows, rel_tabs, probs, zs = [], {}, {}, {}
names = ["V0", "V1", "V2_p0.36", "V3", "V4", "V1cdf", "V3d", "V1star", "V2_p0.30", "V2_p0.42"]
v0_of = {n: meta[n]["matched_V0"] for n in names if n != "V0"}
v0_of["V0"] = v0_of["V1"]                      # table row "V0" = open loop matched to V1 (same alpha / noise)
runs = {}
for n in names:
    runs[n] = load(v0_of["V0"] if n == "V0" else n)
for a_name in set(v0_of.values()):
    runs[a_name] = load(a_name)

# ------------------------------------------------------------------ baselines
z_det = K.z_common(det["th2"])
for lab, z in (("ERA5_0_100 (v1.0)", z_era), ("ERA5_7_28", z_era_l2), ("det_openloop_bucket", z_det)):
    ra, rt = K.r_ci(z, z_ins), K.r_ci(TEST(z), z_ins)
    ev, evt = event_scores(z), event_scores(z, sub=TEST)
    rows.append(dict(variant=lab, R=ra["r"], lo=ra["lo"], hi=ra["hi"], n=ra["n"], R_test=rt["r"],
                     lo_test=rt["lo"], hi_test=rt["hi"], **{k: ev[k] for k in ("POD", "FAR", "BS_det", "BS_clim")},
                     POD_test=evt["POD"], FAR_test=evt["FAR"]))
ev_oper = event_scores(z_era_oper)
ev_det_oper = event_scores(K.z_oper(det["th2"]).loc["2016-01-01":])
print(f"ERA5 operational (1991-2020 clim) events: POD={ev_oper['POD']:.3f} FAR={ev_oper['FAR']:.3f} n={ev_oper['n_dk']}"
      f" | bucket open loop (1991-2020 clim): POD={ev_det_oper['POD']:.3f} FAR={ev_det_oper['FAR']:.3f}")

# ------------------------------------------------------------------ variants
for n in names:
    r = runs[n]
    prod = pd.Series(r["th2"].mean(axis=1), index=r["index"])
    z = K.z_common(prod)
    zs[n] = z
    p_dk, zmean, zsd, zm = probabilistic(r)
    probs[n] = (p_dk, zmean, zsd)
    ra, rt, rtr = K.r_ci(z, z_ins), K.r_ci(TEST(z), z_ins), K.r_ci(TRAIN(z), z_ins)
    v0 = runs[v0_of[n]]
    z0 = K.z_common(pd.Series(v0["th2"].mean(axis=1), index=v0["index"]))
    d0, d0t = K.paired_delta_r(z, z0, z_ins), K.paired_delta_r(TEST(z), TEST(z0), z_ins)
    de, det_ = K.paired_delta_r(z, z_era, z_ins), K.paired_delta_r(TEST(z), TEST(z_era), z_ins)
    dl2 = K.paired_delta_r(z, z_era_l2, z_ins)
    ev, evt = event_scores(z, p_dk), event_scores(z, p_dk, sub=TEST)
    # spread vs error in z units (pooled-member climatology), all days with ISMN
    j = K.pair(zmean, zsd, z_ins, names=["m", "s", "o"])
    rmse = float(np.sqrt(((j["m"] - j["o"]) ** 2).mean()))
    spread = float(np.sqrt((j["s"] ** 2).mean()))
    zmf = pd.DataFrame(zm, index=r["index"]).reindex(j.index).to_numpy()
    below = float((j["o"].to_numpy()[:, None] < zmf).all(axis=1).mean())
    above = float((j["o"].to_numpy()[:, None] > zmf).all(axis=1).mean())
    rows.append(dict(variant=n, R=ra["r"], lo=ra["lo"], hi=ra["hi"], n=ra["n"], R_train=rtr["r"], R_test=rt["r"],
                     lo_test=rt["lo"], hi_test=rt["hi"],
                     dR_V0=d0["delta"], dR_V0_lo=d0["lo"], dR_V0_hi=d0["hi"],
                     dR_V0_test=d0t["delta"], dR_V0_test_lo=d0t["lo"], dR_V0_test_hi=d0t["hi"],
                     dR_ERA5=de["delta"], dR_ERA5_lo=de["lo"], dR_ERA5_hi=de["hi"],
                     dR_ERA5_test=det_["delta"], dR_ERA5_test_lo=det_["lo"], dR_ERA5_test_hi=det_["hi"],
                     dR_ERA5_7_28=dl2["delta"], dR_ERA5_7_28_lo=dl2["lo"], dR_ERA5_7_28_hi=dl2["hi"],
                     **{k: ev[k] for k in ("POD", "FAR", "BS_det", "BS_ens", "BSS_ens_vs_clim", "BS_clim",
                                           "frac_p_0_or_1", "hits", "misses", "fa", "n_dk")},
                     POD_test=evt["POD"], FAR_test=evt["FAR"], BS_ens_test=evt["BS_ens"],
                     BSS_ens_test=evt["BSS_ens_vs_clim"],
                     spread_z=spread, rmse_z=rmse, spread_over_rmse=spread / rmse,
                     ismn_below_all_members=below, ismn_above_all_members=above, alpha=meta.get(n, {}).get(
                         "alpha", meta[v0_of["V0"]]["alpha"]), R_obs=meta.get(n, {}).get("R", np.nan)))
    jj = K.pair(p_dk, ins_dk, names=["p", "o"])
    rel_tabs[n] = K.reliability(jj["p"].to_numpy(), (jj["o"] <= C.THR).to_numpy(), C.REL_BINS)
    rel_tabs[n]["variant"] = n

tab = pd.DataFrame(rows)
tab.to_csv(f"{K.OUT}/results_table.csv", index=False)
pd.concat(rel_tabs.values()).to_csv(f"{K.OUT}/reliability.csv", index=False)
show = ["variant", "R", "lo", "hi", "R_train", "R_test", "dR_V0", "dR_V0_lo", "dR_V0_hi", "dR_V0_test",
        "dR_ERA5", "dR_ERA5_lo", "dR_ERA5_hi", "dR_ERA5_test", "dR_ERA5_test_lo", "dR_ERA5_test_hi",
        "POD", "FAR", "BS_det", "BS_ens", "BSS_ens_vs_clim", "BS_ens_test", "spread_over_rmse"]
print(tab[show].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
print(tab[["variant", "dR_ERA5_7_28", "dR_ERA5_7_28_lo", "dR_ERA5_7_28_hi", "POD_test", "FAR_test", "BS_clim",
           "frac_p_0_or_1", "spread_z", "rmse_z", "ismn_below_all_members", "ismn_above_all_members",
           "alpha", "R_obs"]].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
for n in ("V0", "V1", "V3"):
    print(f"reliability {n}:\n", rel_tabs[n].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    jj = K.pair(probs[n][0], ins_dk, names=["p", "o"])
    print("  Brier decomposition:", {k: round(v, 4) for k, v in K.brier_decomposition(
        jj["p"].to_numpy(), (jj["o"] <= C.THR).to_numpy(), C.REL_BINS).items()})

# ------------------------------------------------------------------ surface innovation consistency (train / test)
inn_rows = []
for n in ("V1", "V1cdf", "V3", "V3d", "V4", "V2_p0.36"):
    inn = pd.read_csv(f"{K.OUT}/innov_{n}.csv", index_col=0, parse_dates=True)
    R = meta[n]["R"]
    for per, yrs in (("train", C.TRAIN_YEARS), ("test", C.TEST_YEARS)):
        d = M.desroziers(inn[inn.index.year.isin(yrs)], R)
        mon = inn[inn.index.year.isin(yrs)]
        bias_mjj = float((mon["y"] - mon["hxb"])[mon.index.month.isin([5, 6, 7])].mean())
        bias_djf = float((mon["y"] - mon["hxb"])[mon.index.month.isin([12, 1, 2])].mean())
        inn_rows.append(dict(variant=n, period=per, R_used=R, R_desroziers=d["R"], HBH_desroziers=d["HBH"],
                             HPbH_ens=d["HPbH"], NIS=d["NIS"], mean_innov=d["mean_d"], innov_MJJ=bias_mjj,
                             innov_DJF=bias_djf, n=d["n"],
                             mean_gain=float((mon["hpbh"] / (mon["hpbh"] + R)).mean())))
inn_tab = pd.DataFrame(inn_rows)
inn_tab.to_csv(f"{K.OUT}/innovation_stats.csv", index=False)
print(inn_tab.to_string(index=False, float_format=lambda x: f"{x:.4g}"))

# root-zone increment and cross-layer coupling of V1
inn = pd.read_csv(f"{K.OUT}/innov_V1.csv", index_col=0, parse_dates=True)
d1 = runs["V1"]["th2"].mean(axis=1) - runs[v0_of["V1"]]["th2"].mean(axis=1)
dd = pd.Series(d1, index=runs["V1"]["index"])
print(f"V1 - V0 root-zone theta2 difference: mean {dd.mean():.4f}, sd {dd.std():.4f} m3/m3; "
      f"V0 root-zone temporal sd {runs[v0_of['V1']]['th2'].mean(axis=1).std():.4f}")

# ------------------------------------------------------------------ V2 parameter convergence
par = {}
for pm in C.PARAM["prior_means"]:
    r = runs[f"V2_p{pm:.2f}"]
    f = pd.DataFrame(r["fc2"], index=r["fc2_index"])
    par[pm] = pd.DataFrame({"mean": f.mean(axis=1), "sd": f.std(axis=1, ddof=1)})
pt = pd.concat({f"prior_{k:.2f}": v.resample("YE").last() for k, v in par.items()}, axis=1)
pt.index = pt.index.year
pt.to_csv(f"{K.OUT}/v2_param_by_year.csv")
print("V2 theta_fc2 (end-of-year ensemble mean / sd):\n", pt.round(4).to_string())
gap = {y: float(max(par[k]["mean"].loc[str(y)].iloc[-1] for k in par) - min(par[k]["mean"].loc[str(y)].iloc[-1]
                                                                          for k in par)) for y in range(2016, 2025)}
print("spread of posterior means across the three priors at year end:", {k: round(v, 4) for k, v in gap.items()})

json.dump(dict(base_rate_train=base_rate_train, ev_oper_era5=ev_oper, ev_oper_bucket=ev_det_oper,
               v1_minus_v0_th2=dict(mean=float(dd.mean()), sd=float(dd.std())), v2_prior_gap=gap),
          open(f"{K.OUT}/eval_extra.json", "w"), indent=1, default=float)

# ------------------------------------------------------------------ figures
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
COL = {"ERA5": "#8a8985", "V0": "#2a78d6", "V1": "#eb6834", "V3": "#1baf7a"}
plt.rcParams.update({"font.size": 8.5, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 1.4})
obs_s1 = pd.read_csv(f"{K.OUT}/obs_rescaled.csv", index_col=0, parse_dates=True)["S1_seasonal"]
fig, ax = plt.subplots(3, 2, figsize=(13, 8.2), sharex="col", gridspec_kw=dict(height_ratios=[1, 1.2, 0.7]))
for c, yr in enumerate((2017, 2022)):
    sl = slice(f"{yr}-04-01", f"{yr}-10-31")
    r1, r0 = runs["V1"], runs[v0_of["V1"]]
    idx = r1["index"]
    m = (idx >= sl.start) & (idx <= sl.stop)
    a = ax[0, c]
    q = np.percentile(r1["th1"][m], [5, 95], axis=1)
    a.fill_between(idx[m], q[0], q[1], color=COL["V1"], alpha=0.18, lw=0, label="V1 5-95 % members")
    a.plot(idx[m], r0["th1"][m].mean(axis=1), color=COL["V0"], label="V0 open loop")
    a.plot(idx[m], r1["th1"][m].mean(axis=1), color=COL["V1"], label="V1 analysis (S-1)")
    o = obs_s1.loc[sl]
    a.plot(o.index, o.values, "o", ms=3.2, color=INK, mfc="white", mew=0.8, label="S-1 (rescaled)")
    a.set_ylabel("theta1 0-10 cm (m3/m3)")
    a.set_title(f"{yr} Apr-Oct: surface layer", loc="left", color=INK)
    a = ax[1, c]
    zm_, zsd_ = probs["V1"][1], probs["V1"][2]
    a.fill_between(idx[m], (zm_ - 1.645 * zsd_)[m], (zm_ + 1.645 * zsd_)[m], color=COL["V1"], alpha=0.18, lw=0,
                   label="V1 90 % ensemble range")
    for lab, s_, col, ls in (("ERA5-L 0-100 cm", z_era, COL["ERA5"], "-"), ("V0", zs["V0"], COL["V0"], "-"),
                             ("V1", zs["V1"], COL["V1"], "-"), ("V3 (ERA5 L1 obs)", zs["V3"], COL["V3"], "--")):
        a.plot(s_.loc[sl].index, s_.loc[sl].values, color=col, ls=ls, label=lab)
    zi = z_ins.loc[sl]
    a.plot(zi.index, zi.values, color=INK, lw=2.0, label="ISMN 20-30 cm")
    a.axhline(C.THR, color=INK2, lw=0.8, ls=":")
    a.set_ylabel("root-zone anomaly z")
    a.set_title("root zone (10-100 cm) vs ISMN 20-30 cm", loc="left", color=INK)
    a = ax[2, c]
    for k, (lab, col, off) in enumerate((("V0", COL["V0"], -2.2), ("V1", COL["V1"], 2.2))):
        p = probs[lab][0].loc[sl]
        a.bar(p.index + pd.Timedelta(days=off), p.values, width=4.2, color=col, label=f"P(z<=-1) {lab}")
    ev_ = ins_dk.loc[sl]
    ev_ = ev_[ev_ <= C.THR]
    a.plot(ev_.index, np.full(len(ev_), 1.06), "v", color=INK, ms=6, label="ISMN dekad z<=-1")
    a.set_ylim(0, 1.15)
    a.set_ylabel("probability")
    a.set_title("dekadal P(root-zone z <= -1)", loc="left", color=INK)
for a in ax.ravel():
    a.tick_params(labelsize=7.5)
for r_ in range(3):
    ax[r_, 1].legend(fontsize=7.5, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))
fig.suptitle("Condom: EnKF assimilation of Sentinel-1 into a 2-layer bucket (dry summer 2017 vs 2022)",
             x=0.01, ha="left", color=INK, fontsize=10)
fig.tight_layout()
fig.subplots_adjust(right=0.84)
fig.savefig(f"{K.OUT}/fig_summers_2017_2022.png", dpi=150)

fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
for k, (pm, col) in enumerate(zip(C.PARAM["prior_means"], ("#2a78d6", "#eb6834", "#1baf7a"))):
    v = par[pm]
    ax[0].fill_between(v.index, v["mean"] - v["sd"], v["mean"] + v["sd"], color=col, alpha=0.15, lw=0)
    ax[0].plot(v.index, v["mean"], color=col, label=f"prior mean {pm:.2f}")
ax[0].axvline(pd.Timestamp(C.DA_START), color=INK2, lw=0.8, ls=":")
ax[0].set_ylabel("theta_fc2 (m3/m3)")
ax[0].set_title("V2: augmented root-zone field capacity (mean +- 1 sd)", loc="left", color=INK)
ax[0].legend(frameon=False, fontsize=7.5)
for n, col in (("V0", COL["V0"]), ("V1", COL["V1"]), ("V3", COL["V3"])):
    rt = rel_tabs[n].dropna()
    ax[1].plot(rt["p_mean"], rt["obs_freq"], "o-", color=col, label=n, ms=5)
ax[1].plot([0, 1], [0, 1], color=INK2, lw=0.8, ls=":")
ax[1].set_xlabel("forecast P(z<=-1), dekadal")
ax[1].set_ylabel("observed frequency (ISMN)")
ax[1].set_title("reliability 2016-2024 (bins: 0, .1-.3, ..., .9-1)", loc="left", color=INK)
ax[1].legend(frameon=False, fontsize=7.5)
fig.tight_layout()
fig.savefig(f"{K.OUT}/fig_param_reliability.png", dpi=150)
print("figures written")
