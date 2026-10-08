"""R1 - run all DA variants. Every tuning step uses 2016-2020 only; ISMN is used for exactly two training-year
choices (SWI T for V4, and the explicitly 'truth-tuned' sensitivity V1*), both logged in out/settings_log.csv.

Variants (root-zone product = ensemble-mean theta2, 10-100 cm):
  V0   open loop ensemble (same noise draws, same alpha as the matched DA run)
  V1   EnKF, S-1 CD SSM (seasonal mean/std rescaled to model theta1) -> theta1, cross-covariance -> theta2
  V2   V1 + augmented theta_fc2 (random walk), priors 0.30 / 0.36 / 0.42 (convergence test)
  V3   EnKF, ERA5-Land layer 1 on the S-1 analysis days -> theta1 (NOT independent of the forcing)
  V4   EnKF, S-1 SWI (exponential filter, T chosen on 2016-2020) rescaled to theta2 -> theta2
Sensitivities: V1cdf (whole-year CDF matching), V3d (ERA5 L1 every day), V1* (alpha x R grid chosen on
training-year R vs ISMN).
Innovation-based tuning (no ISMN): for each alpha in ALPHA_GRID, R is iterated with Desroziers (2005) on
2016-2020; alpha is the one whose ensemble HPbH' best matches the Desroziers HBH' estimate.
"""
import json
import time

import numpy as np
import pandas as pd

import common as K
import config as C
import model as M

t0 = time.time()
LOG = []          # every configuration run: what it was, whether ISMN was looked at to choose it


def log(name, kind, uses_ismn, **kw):
    LOG.append(dict(name=name, kind=kind, uses_ismn_for_choice=uses_ismn, **kw))


frc_all = K.forcing()
det = M.run_deterministic(frc_all, C.SOIL["theta_fc1"], C.SOIL["theta_fc2"])
det.to_csv(f"{K.OUT}/det_openloop_1991_2024.csv")
frc = frc_all.loc[C.ENS_START:C.END]
init = tuple(det.loc[pd.Timestamp(C.ENS_START) - pd.Timedelta(days=1)])
N = C.ENS["n_members"]
noise = M.draw_noise(len(frc), N, C.ENS["seed"])
TRAIN_END = f"{C.TRAIN_YEARS[-1]}-12-31"
frc_tr = frc.loc[:TRAIN_END]

# ------------------------------------------------------------------ observations
s1 = K.s1_raw()
y_s1 = K.s1_daily(s1).loc[C.DA_START:C.END]
print(f"S-1 after QC: {len(s1)} acquisitions -> {len(y_s1)} analysis days "
      f"({y_s1.groupby(y_s1.index.year).size().to_dict()})")
obs = {}
obs["S1_seasonal"] = M.rescale_seasonal_meanstd(y_s1, det["th1"], C.TRAIN_YEARS, C.RESCALE_WINDOW_DAYS)
obs["S1_cdf"] = M.rescale_cdf(y_s1, det["th1"], C.TRAIN_YEARS, C.CDF_PERCENTILES)
e5 = K.era5()["sm_l1"]
obs["E5L1_s1days"] = M.rescale_seasonal_meanstd(e5.reindex(y_s1.index), det["th1"], C.TRAIN_YEARS,
                                                C.RESCALE_WINDOW_DAYS)
e5d = e5.loc[C.DA_START:C.END]
obs["E5L1_daily"] = M.rescale_seasonal_meanstd(e5d, det["th1"], C.TRAIN_YEARS, C.RESCALE_WINDOW_DAYS)

# V4: SWI T chosen on training years only (ISMN, training-year days, training-year climatology of the SWI)
z_ins = K.z_common(K.ismn_ref())
swi_rows = []
for T in C.SWI_T_GRID:
    sw = M.swi_filter(y_s1, T)
    swd = sw.asfreq("D").ffill(limit=6)               # daily value for the choice only (as exp_sm C3)
    tr = swd[swd.index.year.isin(C.TRAIN_YEARS)]
    zt = K.s4.clim_anomaly(tr, (C.DA_START, TRAIN_END), C.HW, min_n=20)["z"]
    p = K.pair(zt, z_ins, names=["x", "y"])
    swi_rows.append(dict(T=T, R_train=p["x"].corr(p["y"]), n=len(p)))
    log(f"SWI_T{T}", "V4 T choice", True, R_train=swi_rows[-1]["R_train"])
swi_tab = pd.DataFrame(swi_rows)
T_best = float(swi_tab.loc[swi_tab["R_train"].idxmax(), "T"])
print("SWI T grid (training years):", swi_tab.round(3).to_dict("records"), "-> T =", T_best)
obs["SWI"] = M.rescale_seasonal_meanstd(M.swi_filter(y_s1, T_best), det["th2"], C.TRAIN_YEARS,
                                        C.RESCALE_WINDOW_DAYS)
for k, v in obs.items():
    assert v.notna().all(), k
pd.DataFrame(obs).to_csv(f"{K.OUT}/obs_rescaled.csv")


# ------------------------------------------------------------------ innovation-based tuning (training only)
def tune(name: str, y: pd.Series, h_row: int, R0: float) -> dict:
    rows = []
    for alpha in C.ALPHA_GRID:
        R = R0
        for it in range(C.DESROZIERS_ITER):
            r = M.run_ensemble(frc_tr, init, noise, alpha, y, h_row, R, None, obs_seed=7, da_end=TRAIN_END)
            d = M.desroziers(r["innov"], R)
            rows.append(dict(obs=name, alpha=alpha, iter=it, R_used=R, **d))
            log(f"{name}_a{alpha}_it{it}", "innovation tuning (train)", False, alpha=alpha, R_used=R)
            assert d["R"] > 0, f"Desroziers R <= 0 for {name} alpha={alpha}"
            R = d["R"]
    tab = pd.DataFrame(rows)
    last = tab[tab["iter"] == C.DESROZIERS_ITER - 1].copy()
    ok = last["HBH"] > 0
    if not ok.all():
        print(f"WARNING {name}: Desroziers HBH' <= 0 for alpha", last.loc[~ok, "alpha"].tolist())
    last["log_ratio"] = np.where(ok, np.log(last["HPbH"].clip(lower=1e-12) / last["HBH"].where(ok, 1.0)), np.inf)
    best = last.loc[last["log_ratio"].abs().idxmin()]
    print(f"[{name}] tuning (train 2016-2020):\n"
          + last[["alpha", "R_used", "R", "HBH", "HPbH", "NIS", "mean_d", "n"]].to_string(
              index=False, float_format=lambda x: f"{x:.3g}")
          + f"\n -> alpha={best['alpha']}, R={best['R_used']:.3g} (sd {np.sqrt(best['R_used']):.4f})")
    return dict(alpha=float(best["alpha"]), R=float(best["R_used"]), table=tab)


tuned = {}
for name, h, r0 in (("S1_seasonal", 0, C.R0["S1"]), ("S1_cdf", 0, C.R0["S1"]),
                    ("E5L1_s1days", 0, C.R0["ERA5L1"]), ("E5L1_daily", 0, C.R0["ERA5L1"]),
                    ("SWI", 1, C.R0["SWI"])):
    tuned[name] = tune(name, obs[name], h, r0)
pd.concat([v["table"] for v in tuned.values()]).to_csv(f"{K.OUT}/tuning_desroziers.csv", index=False)
print(f"tuning done in {time.time() - t0:.0f} s")


# ------------------------------------------------------------------ final runs (2015-2024)
def save(name, r, meta):
    np.savez_compressed(f"{K.OUT}/run_{name}.npz", th1=r["th1"].astype(np.float32), th2=r["th2"].astype(np.float32),
                        fc2=r["fc2"].astype(np.float32), index=r["index"].to_numpy().astype("datetime64[D]"))
    r["innov"].to_csv(f"{K.OUT}/innov_{name}.csv")
    meta_all[name] = meta


meta_all = {}
alphas_needed = sorted({v["alpha"] for v in tuned.values()} | {1.0})
for a in alphas_needed:
    r = M.run_ensemble(frc, init, noise, a, None, None, None, None, obs_seed=7)
    save(f"V0_a{a}", r, dict(variant="V0", alpha=a))
    log(f"V0_a{a}", "final", False, alpha=a)

spec = {"V1": ("S1_seasonal", 0, None), "V3": ("E5L1_s1days", 0, None), "V4": ("SWI", 1, None),
        "V1cdf": ("S1_cdf", 0, None), "V3d": ("E5L1_daily", 0, None)}
for pm in C.PARAM["prior_means"]:
    spec[f"V2_p{pm:.2f}"] = ("S1_seasonal", 0, dict(mean=pm))
for name, (oname, h, param) in spec.items():
    a, R = tuned[oname]["alpha"], tuned[oname]["R"]
    r = M.run_ensemble(frc, init, noise, a, obs[oname], h, R, param, obs_seed=7)
    save(name, r, dict(variant=name, obs=oname, h_row=h, alpha=a, R=R, param=param, matched_V0=f"V0_a{a}"))
    log(name, "final", oname == "SWI", alpha=a, R=R)
    print(f"{name}: alpha={a} R_sd={np.sqrt(R):.4f} n_updates={len(r['innov'])} ({time.time() - t0:.0f} s)")

# ------------------------------------------------------------------ V1*: truth-tuned sensitivity (train-only choice)
z_ins_tr = z_ins[z_ins.index.year.isin(C.TRAIN_YEARS)]
grid, runs = [], {}
for a in C.ALPHA_GRID:
    for rsd in (0.02, 0.04, 0.08):
        r = M.run_ensemble(frc, init, noise, a, obs["S1_seasonal"], 0, rsd ** 2, None, obs_seed=7)
        prod = pd.Series(r["th2"].mean(axis=1), index=r["index"])
        p = K.pair(K.z_common(prod), z_ins_tr, names=["x", "y"])
        grid.append(dict(alpha=a, R_sd=rsd, R_train=p["x"].corr(p["y"])))
        runs[(a, rsd)] = r
        log(f"V1star_a{a}_r{rsd}", "ISMN-tuned grid (train choice)", True, alpha=a, R=rsd ** 2,
            R_train=grid[-1]["R_train"])
grid_df = pd.DataFrame(grid)
b = grid_df.loc[grid_df["R_train"].idxmax()]
best_r = runs[(b["alpha"], b["R_sd"])]
best_meta = dict(variant="V1star", alpha=float(b["alpha"]), R=float(b["R_sd"]) ** 2, obs="S1_seasonal",
                 matched_V0=f"V0_a{float(b['alpha'])}")
del runs
grid_df.to_csv(f"{K.OUT}/v1star_grid.csv", index=False)
print("V1* grid (training-year R vs ISMN):\n", grid_df.round(3).to_string(index=False))
if f"V0_a{best_meta['alpha']}" not in meta_all:
    r = M.run_ensemble(frc, init, noise, best_meta["alpha"], None, None, None, None, obs_seed=7)
    save(f"V0_a{best_meta['alpha']}", r, dict(variant="V0", alpha=best_meta["alpha"]))
save("V1star", best_r, best_meta)

json.dump(dict(meta=meta_all, T_swi=T_best, tuned={k: dict(alpha=v["alpha"], R=v["R"]) for k, v in tuned.items()},
               swi_grid=swi_rows), open(f"{K.OUT}/runs_meta.json", "w"), indent=1, default=float)
pd.DataFrame(LOG).to_csv(f"{K.OUT}/settings_log.csv", index=False)
print(f"settings run: {len(LOG)} (of which chosen with ISMN on training years: "
      f"{sum(x['uses_ismn_for_choice'] for x in LOG)}); total {time.time() - t0:.0f} s")
