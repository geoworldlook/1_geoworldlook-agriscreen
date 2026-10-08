"""T0 - validation of the building blocks against reality / analytic results (no ISMN involved).

1. mass balance of the bucket: dS1 + dS2 = P - RO - D2 - E1 - E2 for every day of a 1991-2024 run;
2. limiting cases: no rain + no ET -> exchange conserves water and equalises theta; no rain -> theta never
   below theta_res / ET stops at the floors;
3. EnKF on a linear-Gaussian 2-state problem reproduces the exact Kalman analysis mean / covariance;
4. rescaling: seasonal mean/std and CDF matching are the identity when obs == model.
"""
import numpy as np
import pandas as pd

import common as K
import config as C
import model as M

frc = K.forcing()
# --- 1. mass balance on the real forcing (deterministic)
s = C.SOIL
th1, th2, fc2 = np.array([0.30]), np.array([0.30]), np.array([s["theta_fc2"]])
P, E = frc["precip_mm"].to_numpy(), frc["et0_mm"].to_numpy()
err = 0.0
for i in range(len(frc)):
    S0 = th1[0] * s["d1_mm"] + th2[0] * s["d2_mm"]
    th1, th2, f = M.step(th1, th2, fc2, P[i:i + 1], E[i:i + 1])
    S1 = th1[0] * s["d1_mm"] + th2[0] * s["d2_mm"]
    resid = (S1 - S0) - (P[i] - f["RO"][0] - f["D2"][0] - f["E1"][0] - f["E2"][0])
    err = max(err, abs(resid))
    assert s["theta_res"] - 1e-12 <= th1[0] <= s["theta_sat"] + 1e-12
    assert s["theta_res"] - 1e-12 <= th2[0] <= s["theta_sat"] + 1e-12
print(f"1. max daily mass-balance residual over {len(frc)} days: {err:.2e} mm")
assert err < 1e-9

# --- 2. limiting cases
a1, a2 = np.array([0.30]), np.array([0.25])
tot0 = a1 * s["d1_mm"] + a2 * s["d2_mm"]
for _ in range(400):
    a1, a2, _f = M.step(a1, a2, fc2, np.zeros(1), np.zeros(1))
tot1 = a1 * s["d1_mm"] + a2 * s["d2_mm"]
print(f"2a. no P, no ET, below FC: total water change {float((tot1 - tot0)[0]):.2e} mm, theta1-theta2 = {float((a1 - a2)[0]):.2e}")
assert abs(float((tot1 - tot0)[0])) < 1e-9 and abs(float((a1 - a2)[0])) < 1e-6
a1, a2 = np.array([0.40]), np.array([0.40])
for _ in range(2000):
    a1, a2, _f = M.step(a1, a2, fc2, np.zeros(1), np.full(1, 6.0))
print(f"2b. 2000 dry days at ET0=6: theta1={a1[0]:.4f} theta2={a2[0]:.4f} (floors res={s['theta_res']}, wp={s['theta_wp']})")
assert a1[0] >= s["theta_res"] - 1e-12 and a2[0] >= s["theta_res"] - 1e-12

# --- 3. EnKF vs exact Kalman (linear Gaussian)
rng = np.random.default_rng(1)
mu = np.array([0.3, 0.25])
B = np.array([[0.004, 0.0015], [0.0015, 0.001]])
R, y, N = 0.002, 0.36, 200000
X = rng.multivariate_normal(mu, B, N).T
Xa = M.enkf_update(X, 0, y, R, rng)
Kx = B[:, 0] / (B[0, 0] + R)
ma = mu + Kx * (y - mu[0])
Pa = B - np.outer(Kx, B[0, :])
print("3. EnKF mean", Xa.mean(1).round(5), "exact", ma.round(5), "| cov", np.cov(Xa).round(6).ravel(),
      "exact", Pa.round(6).ravel())
assert np.allclose(Xa.mean(1), ma, atol=5e-4) and np.allclose(np.cov(Xa), Pa, atol=3e-5)

# --- 4. rescaling identity
idx = pd.date_range("2016-01-01", "2024-12-31", freq="3D")
m = pd.Series(0.3 + 0.08 * np.sin(2 * np.pi * idx.dayofyear / 365) + rng.normal(0, 0.03, len(idx)), index=idx)
r1 = M.rescale_seasonal_meanstd(m, m, C.TRAIN_YEARS, C.RESCALE_WINDOW_DAYS)
r2 = M.rescale_cdf(m, m, C.TRAIN_YEARS, C.CDF_PERCENTILES)
print(f"4. identity: seasonal max|d|={np.abs(r1 - m).max():.2e}, cdf max|d| (train range)="
      f"{np.abs(r2 - m)[m.between(m[m.index.year < 2021].min(), m[m.index.year < 2021].max())].max():.2e}")
assert np.abs(r1 - m).max() < 1e-12 and np.abs(r2 - m).max() < 1e-12
print("all tests passed")
