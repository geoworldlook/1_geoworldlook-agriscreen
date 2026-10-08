"""Experiment DA - every setting in one place, fixed BEFORE any comparison with ISMN.

Station: SMOSMANIA Condom (43.9744 N, 0.3361 E, 174 m), grass plot on a silty-clay / clay soil
(in situ 5-30 cm: clay 41-46 %, saturation 0.50-0.52 m3/m3; HWSD 0-30 cm clay 49 %).

Sources of a-priori values (none tuned on ISMN):
  - theta_fc 0.36 / theta_wp 0.22: FAO-56 Table 19, clay, mid of ranges (0.32-0.40 / 0.20-0.24) [from memory].
  - theta_sat 0.50: ISMN static_variables (in situ / HWSD saturation).
  - theta_res 0.11 = 0.5 * theta_wp: FAO-56 convention for the air-dry limit of the evaporation layer (TEW eq. 73).
  - Kc 0.95: FAO-56 Table 12, turf grass cool season, Kc_mid [from memory]; p 0.5 (FAO-56 Table 22 grass ~0.5-0.6).
  - f1_root 0.45: fraction of grassland roots in the top 10 cm, Jackson et al. 1996 (temperate grassland
    beta = 0.943 -> 1 - 0.943**10 = 0.44) [from memory].
  - drainage / exchange rates k1, k2, kx: plausible order of magnitude for a clay soil, NOT calibrated (stated as
    a limitation; V2 tests whether a root-zone parameter can be learned from the data instead).
Hargreaves ET0 needs Tmax, which the ERA5-Land file lacks: Tmax ~ 2*Tmean - Tmin (Tmean = 24-h mean is usually
a little below (Tmax+Tmin)/2, so the diurnal range and ET0 are biased low by a few %; anomalies much less affected).
"""

SITE = dict(lat_deg=43.9744, lon_deg=0.3361)

# ------------------------------------------------------------------ model physics (2-layer bucket, daily)
SOIL = dict(
    d1_mm=100.0,          # surface layer 0-10 cm
    d2_mm=900.0,          # root zone 10-100 cm
    theta_sat=0.50,
    theta_fc1=0.36,       # field capacity, surface layer
    theta_fc2=0.36,       # field capacity, root zone (augmented + estimated in V2)
    theta_wp=0.22,
    theta_res=0.11,
)
FLUX = dict(
    k1_per_day=0.5,       # gravity drainage of water above FC, layer 1 -> 2
    k2_per_day=0.1,       # deep drainage of water above FC out of layer 2
    kx_mm_per_day=10.0,   # diffusive exchange, F = kx * (theta1 - theta2) [mm/day], relaxation ~9 days
)
VEG = dict(kc=0.95, f1_root=0.45, p_depl=0.5)

# ------------------------------------------------------------------ periods
SPINUP_DET_START = "1991-01-01"   # deterministic open loop (also gives the 1991-2020 climatology)
ENS_START = "2015-01-01"          # ensemble initialised from the deterministic state, 1 yr of free spread
DA_START = "2016-01-01"
END = "2024-12-31"
COMMON = ("2016-01-01", "2024-12-31")   # v1.0 validation period (ISMN files end 2024-12-31)
CLIM_REF_OPER = ("1991-01-01", "2020-12-31")
TRAIN_YEARS = list(range(2016, 2021))   # rescaling, innovation tuning, any ISMN-based choice
TEST_YEARS = list(range(2021, 2025))    # never used for any choice
HW = 15                                 # +-15 d DOY window (v1.0)
THR = -1.0                              # event threshold z <= -1 (v1.0 THR_SMA)

# ------------------------------------------------------------------ ensemble / perturbations (a priori)
ENS = dict(
    n_members=100,
    seed=20160101,
    precip_ln_sigma=0.5,     # multiplicative log-normal precipitation error (mean 1), independent daily
    et0_ln_sigma=0.2,        # multiplicative log-normal ET0 error (mean 1) ...
    et0_ar1=0.9,             # ... AR(1)-correlated in time (Hargreaves errors are persistent)
    q1=0.005,                # additive process noise on theta1, sd per day (m3/m3); scaled by alpha
    q2=0.0015,               # additive process noise on theta2, sd per day (m3/m3); scaled by alpha
    init_sd1=0.02, init_sd2=0.01,
)

# ------------------------------------------------------------------ observations
S1 = dict(
    product="S1_CD_A", variable="sm_s1", site="SMOSMANIA_Condom",
    drop_flags=("POSSIBLE_FROZEN",),     # radar SM meaningless on frozen soil
    morning_to_previous_day=True,        # 06 UTC passes -> end of previous model day (6 h vs 18 h away)
)
# Rescaling (training years only).  Primary = seasonal mean/std matching (S-1 CD seasonal cycle is inverted
# in May-July w.r.t. surface soil moisture -> vegetation; a whole-year CDF match leaves a seasonal bias that
# the EnKF cannot handle).  Whole-year CDF matching is run as the literal alternative (counted setting).
RESCALE_PRIMARY = "seasonal_meanstd"
RESCALE_WINDOW_DAYS = 45                 # +-45 DOY window for the seasonal moments (S-1 is sparse)
CDF_PERCENTILES = list(range(0, 101, 5))

# Initial obs-error variances (then re-estimated by Desroziers et al. 2005 on training years)
R0 = {"S1": 0.05 ** 2, "ERA5L1": 0.03 ** 2, "SWI": 0.03 ** 2}
DESROZIERS_ITER = 4
ALPHA_GRID = [0.25, 0.5, 1.0, 2.0, 4.0]  # process-noise scale grid, chosen by innovation consistency (no ISMN)

# V2: augmented root-zone field capacity, slow random walk
PARAM = dict(name="theta_fc2", prior_sd=0.03, rw_sd_per_day=0.0005, lo=0.27, hi=0.46,
             prior_means=(0.30, 0.36, 0.42))
# V4: SWI exponential filter T chosen on training years only (grid), obs of the root zone
SWI_T_GRID = [5, 10, 15, 20, 30, 40]

# ------------------------------------------------------------------ evaluation
BOOT = {"BOOTSTRAP_N": 1000, "BOOTSTRAP_BLOCK_DAYS": 30, "RANDOM_SEED": 42, "MIN_N_METRICS": 10}
PAIRED_BOOT_N = 2000
REL_BINS = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0001]
