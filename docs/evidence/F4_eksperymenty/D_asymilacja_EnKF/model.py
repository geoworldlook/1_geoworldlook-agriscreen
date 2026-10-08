"""2-layer soil water bucket (0-10 cm surface, 10-100 cm root zone), ensemble integration and stochastic EnKF.

Units: theta in m3/m3, storages and fluxes in mm (per day), layer thickness in mm.
Daily step (all members vectorised), in this order:
  1. infiltration of P into layer 1; water above saturation bypasses to layer 2 (crack flow, clay);
  2. gravity drainage 1 -> 2: D1 = k1 * max(S1 - FC1, 0); layer-2 water above saturation -> runoff;
  3. deep drainage: D2 = k2 * max(S2 - FC2, 0);
  4. ET = Kc * ET0 split by root fraction f1 / (1 - f1), each reduced by a FAO-56-type linear stress factor
     beta = clip((theta - theta_low) / ((1 - p)(theta_fc - theta_low)), 0, 1); theta_low = theta_res (layer 1,
     evaporation + uptake down to air-dry) or theta_wp (layer 2);
  5. diffusive exchange F = kx * (theta1 - theta2), integrated exactly (relaxation of the theta difference),
     mass-conserving;
  6. (ensemble only) additive Gaussian process noise, then clipping to [theta_res, theta_sat].
EnKF: Evensen (1994) with perturbed observations (Burgers et al. 1998), scalar observation per analysis time,
state = [theta1, theta2] (+ theta_fc2 for joint state-parameter estimation).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import config as C


def step(th1: np.ndarray, th2: np.ndarray, fc2: np.ndarray, P: np.ndarray, ET0: np.ndarray) -> tuple:
    """One daily step. All inputs are arrays of shape (N,). Returns th1, th2 and a flux dict (mm)."""
    s, f, v = C.SOIL, C.FLUX, C.VEG
    d1, d2 = s["d1_mm"], s["d2_mm"]
    S1, S2 = th1 * d1, th2 * d2
    # 1. infiltration and saturation bypass
    S1 = S1 + P
    over1 = np.maximum(S1 - s["theta_sat"] * d1, 0.0)
    S1 = S1 - over1
    S2 = S2 + over1
    # 2. gravity drainage 1 -> 2
    D1 = f["k1_per_day"] * np.maximum(S1 - s["theta_fc1"] * d1, 0.0)
    S1 = S1 - D1
    S2 = S2 + D1
    RO = np.maximum(S2 - s["theta_sat"] * d2, 0.0)
    S2 = S2 - RO
    # 3. deep drainage
    D2 = f["k2_per_day"] * np.maximum(S2 - fc2 * d2, 0.0)
    S2 = S2 - D2
    # 4. evapotranspiration
    etc = v["kc"] * ET0
    q = 1.0 - v["p_depl"]
    b1 = np.clip((S1 / d1 - s["theta_res"]) / (q * (s["theta_fc1"] - s["theta_res"])), 0.0, 1.0)
    b2 = np.clip((S2 / d2 - s["theta_wp"]) / (q * (fc2 - s["theta_wp"])), 0.0, 1.0)
    E1 = np.minimum(v["f1_root"] * etc * b1, np.maximum(S1 - s["theta_res"] * d1, 0.0))
    E2 = np.minimum((1.0 - v["f1_root"]) * etc * b2, np.maximum(S2 - s["theta_wp"] * d2, 0.0))
    S1 = S1 - E1
    S2 = S2 - E2
    # 5. diffusive exchange (exact relaxation of theta1 - theta2 at rate lam = kx (1/d1 + 1/d2))
    inv = 1.0 / d1 + 1.0 / d2
    delta = S1 / d1 - S2 / d2
    F = delta * (1.0 - np.exp(-f["kx_mm_per_day"] * inv)) / inv
    S1 = S1 - F
    S2 = S2 + F
    return S1 / d1, S2 / d2, dict(RO=RO, D2=D2, E1=E1, E2=E2, D1=D1, F=F, over1=over1)


def run_deterministic(frc: pd.DataFrame, th1_0: float, th2_0: float) -> pd.DataFrame:
    """Unperturbed open loop (N = 1), with the a-priori theta_fc2."""
    n = len(frc)
    out = np.empty((n, 2))
    a1, a2 = np.array([th1_0]), np.array([th2_0])
    fc2 = np.array([C.SOIL["theta_fc2"]])
    P, E = frc["precip_mm"].to_numpy(), frc["et0_mm"].to_numpy()
    for i in range(n):
        a1, a2, _ = step(a1, a2, fc2, P[i:i + 1], E[i:i + 1])
        out[i] = a1[0], a2[0]
    return pd.DataFrame(out, index=frc.index, columns=["th1", "th2"])


@dataclass
class Noise:
    """Pre-drawn perturbations (n_days x N), identical for every variant (common random numbers)."""
    p_mult: np.ndarray
    e_mult: np.ndarray
    w1: np.ndarray
    w2: np.ndarray
    wp: np.ndarray
    init: np.ndarray


def draw_noise(n_days: int, N: int, seed: int) -> Noise:
    rng = np.random.default_rng(seed)
    e = C.ENS
    sp = e["precip_ln_sigma"]
    p_mult = np.exp(sp * rng.standard_normal((n_days, N)) - 0.5 * sp ** 2)
    se, rho = e["et0_ln_sigma"], e["et0_ar1"]
    z = np.empty((n_days, N))
    z[0] = rng.standard_normal(N)
    innov = rng.standard_normal((n_days, N)) * np.sqrt(1 - rho ** 2)
    for i in range(1, n_days):
        z[i] = rho * z[i - 1] + innov[i]
    e_mult = np.exp(se * z - 0.5 * se ** 2)
    w1 = rng.standard_normal((n_days, N))
    w2 = rng.standard_normal((n_days, N))
    wp = rng.standard_normal((n_days, N))
    init = rng.standard_normal((3, N))
    return Noise(p_mult, e_mult, w1, w2, wp, init)


def enkf_update(X: np.ndarray, h_row: int, y: float, R: float, rng: np.random.Generator) -> np.ndarray:
    """Stochastic EnKF analysis for one scalar observation of state row `h_row`. X: (n_state, N)."""
    N = X.shape[1]
    hx = X[h_row]
    A = X - X.mean(axis=1, keepdims=True)
    hA = hx - hx.mean()
    pxy = A @ hA / (N - 1)
    pyy = hA @ hA / (N - 1) + R
    K = pxy / pyy
    yp = y + rng.normal(0.0, np.sqrt(R), N)
    return X + K[:, None] * (yp - hx)[None, :]


def run_ensemble(frc: pd.DataFrame, init_state: tuple, noise: Noise, alpha: float, obs: pd.Series | None,
                 h_row: int | None, R: float | None, param: dict | None, obs_seed: int,
                 da_start: str = C.DA_START, da_end: str | None = None) -> dict:
    """Ensemble open loop / EnKF.

    frc: daily forcing from ENS_START. init_state: (theta1, theta2) deterministic state at the start.
    obs: rescaled observations indexed by analysis day (end of that model day), or None (open loop).
    h_row: 0 -> obs of theta1, 1 -> obs of theta2.  param: None, or dict(mean=..) to augment theta_fc2.
    da_end: last day on which observations are assimilated (None = all).
    Returns daily member arrays th1, th2, fc2 (n_days x N) and an innovation table.
    """
    n, N = len(frc), noise.p_mult.shape[1]
    assert noise.p_mult.shape[0] >= n
    e, s = C.ENS, C.SOIL
    rng_obs = np.random.default_rng(obs_seed)
    th1 = np.clip(init_state[0] + e["init_sd1"] * noise.init[0], s["theta_res"], s["theta_sat"])
    th2 = np.clip(init_state[1] + e["init_sd2"] * noise.init[1], s["theta_res"], s["theta_sat"])
    if param is None:
        fc2 = np.full(N, s["theta_fc2"])
    else:
        fc2 = np.clip(param["mean"] + C.PARAM["prior_sd"] * noise.init[2], C.PARAM["lo"], C.PARAM["hi"])
    P = frc["precip_mm"].to_numpy()
    E = frc["et0_mm"].to_numpy()
    days = frc.index
    obs_on = {}
    if obs is not None:
        o = obs.loc[da_start:da_end] if da_end else obs.loc[da_start:]
        obs_on = {days.get_loc(t): float(v) for t, v in o.items() if t in days}
    out1, out2, outp = np.empty((n, N)), np.empty((n, N)), np.empty((n, N))
    inn = []
    q1, q2 = alpha * e["q1"], alpha * e["q2"]
    for i in range(n):
        th1, th2, _ = step(th1, th2, fc2, P[i] * noise.p_mult[i], E[i] * noise.e_mult[i])
        th1 = np.clip(th1 + q1 * noise.w1[i], s["theta_res"], s["theta_sat"])
        th2 = np.clip(th2 + q2 * noise.w2[i], s["theta_res"], s["theta_sat"])
        if param is not None:
            fc2 = np.clip(fc2 + C.PARAM["rw_sd_per_day"] * noise.wp[i], C.PARAM["lo"], C.PARAM["hi"])
        if i in obs_on:
            y = obs_on[i]
            X = np.vstack([th1, th2, fc2]) if param is not None else np.vstack([th1, th2])
            hb = X[h_row].copy()
            Xa = enkf_update(X, h_row, y, R, rng_obs)
            th1 = np.clip(Xa[0], s["theta_res"], s["theta_sat"])
            th2 = np.clip(Xa[1], s["theta_res"], s["theta_sat"])
            if param is not None:
                fc2 = np.clip(Xa[2], C.PARAM["lo"], C.PARAM["hi"])
            ha = (th1, th2)[h_row]
            inn.append((days[i], y, hb.mean(), hb.var(ddof=1), ha.mean(), ha.var(ddof=1)))
        out1[i], out2[i], outp[i] = th1, th2, fc2
    innov = pd.DataFrame(inn, columns=["day", "y", "hxb", "hpbh", "hxa", "hpah"]).set_index("day")
    return dict(index=days, th1=out1, th2=out2, fc2=outp, innov=innov)


# ============================================================================ observation rescaling
def rescale_seasonal_meanstd(y: pd.Series, ref: pd.Series, train_years: list, window: int) -> pd.Series:
    """y' = mu_ref(doy) + (y - mu_y(doy)) * sd_ref(doy) / sd_y(doy); moments from TRAINING-year days on which
    y exists, pooled within +-window DOY. ref is sampled on the same days as y (same sampling)."""
    j = pd.concat([y.rename("y"), ref.rename("m")], axis=1, join="inner").dropna()
    tr = j[j.index.year.isin(train_years)]
    td = tr.index.dayofyear.to_numpy()
    out = pd.Series(np.nan, index=y.index)
    doy = y.index.dayofyear.to_numpy()
    for d in np.unique(doy):
        dist = np.abs(td - d)
        sel = np.minimum(dist, 366 - dist) <= window
        assert sel.sum() >= 30, f"too few training pairs for DOY {d}: {sel.sum()}"
        a, b = tr["y"].to_numpy()[sel], tr["m"].to_numpy()[sel]
        assert a.std(ddof=1) > 0
        m = doy == d
        out[m] = b.mean() + (y.to_numpy()[m] - a.mean()) * b.std(ddof=1) / a.std(ddof=1)
    return out


def rescale_cdf(y: pd.Series, ref: pd.Series, train_years: list, pct: list) -> pd.Series:
    """Whole-year piecewise-linear CDF matching (Reichle & Koster 2004) fitted on TRAINING-year pairs.
    Ties in the obs percentiles (S-1 CD is clipped at 0 and 0.5) are merged by averaging the matching model
    percentiles; values outside the training range are linearly extrapolated with the edge slopes."""
    j = pd.concat([y.rename("y"), ref.rename("m")], axis=1, join="inner").dropna()
    tr = j[j.index.year.isin(train_years)]
    py = np.percentile(tr["y"], pct)
    pm = np.percentile(tr["m"], pct)
    u, inv = np.unique(py, return_inverse=True)
    pm_u = np.array([pm[inv == k].mean() for k in range(len(u))])
    assert np.all(np.diff(u) > 0) and len(u) >= 5
    x = y.to_numpy()
    out = np.interp(x, u, pm_u)
    lo_s = (pm_u[1] - pm_u[0]) / (u[1] - u[0])
    hi_s = (pm_u[-1] - pm_u[-2]) / (u[-1] - u[-2])
    out = np.where(x < u[0], pm_u[0] + (x - u[0]) * lo_s, out)
    out = np.where(x > u[-1], pm_u[-1] + (x - u[-1]) * hi_s, out)
    return pd.Series(out, index=y.index)


def swi_filter(y: pd.Series, T: float) -> pd.Series:
    """Recursive exponential filter (Albergel et al. 2008, eqs. 3-4) evaluated at the observation times."""
    y = y.dropna().sort_index()
    t = ((y.index - y.index[0]) / pd.Timedelta(days=1)).to_numpy(float)
    v = y.to_numpy(float)
    out = np.empty(len(v))
    K, sw = 1.0, v[0]
    out[0] = sw
    for i in range(1, len(v)):
        K = K / (K + np.exp(-(t[i] - t[i - 1]) / T))
        sw = sw + K * (v[i] - sw)
        out[i] = sw
    return pd.Series(out, index=y.index)


def desroziers(innov: pd.DataFrame, R_used: float) -> dict:
    """Desroziers et al. (2005): R ~ E[d_oa d_ob], HBH' ~ E[d_ab d_ob] (ensemble means).
    NIS = mean(d_ob^2 / (HPbH' + R_used)): 1 for a filter whose stated uncertainty matches its innovations."""
    d_ob = innov["y"] - innov["hxb"]
    d_oa = innov["y"] - innov["hxa"]
    d_ab = innov["hxa"] - innov["hxb"]
    return dict(R=float((d_oa * d_ob).mean()), HBH=float((d_ab * d_ob).mean()), HPbH=float(innov["hpbh"].mean()),
                mean_d=float(d_ob.mean()), var_d=float(d_ob.var(ddof=1)),
                NIS=float((d_ob ** 2 / (innov["hpbh"] + R_used)).mean()), n=len(innov))
