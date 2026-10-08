"""All physical parameters of Experiment B in one place (literature values, fixed BEFORE validation).

Soil at Condom (static_variables.csv): in situ 5-30 cm clay 41-46 %, silt 40-44 %, sand 12-15 %
(silty clay / clay); HWSD 30-100 cm clay 42 %, sand 23 % (clay); in situ saturation 0.50-0.52.
FAO-56 Table 19 (clay): theta_FC 0.32-0.40, theta_WP 0.20-0.24, REW 8-12 mm, TEW(Ze=0.1) 22-29 mm.
  -> mid values theta_FC = 0.36, theta_WP = 0.22 (TAW per m = 140 mm), REW = 10 mm.
Root zone: grapevine ~80 % of active roots in the first 1.0 m (search snippet, see README);
  vineyard total transpirable soil water typically 100-250 mm (Lebon et al. 2003; Pellegrino et al. 2006,
  abstracts) -> Zr = 1.0 m gives TAW = 140 mm (inside that range) and matches ERA5-Land 0-100 cm.
Kcb(NDVI): Campos et al. 2010, Kcb = 1.44 NDVI - 0.10 (vineyard; abstract-level verification).
p: FAO-56 Table 22 depletion fraction for grapes 0.35-0.45 (from memory, not verified online);
   p only affects Ks (feedback on ET), not the definition of relative soil water.
"""

SOIL_BASE = dict(
    theta_fc=0.36, theta_wp=0.22,   # m3/m3, FAO-56 Table 19 clay (mid)
    zr_m=1.0,                       # m, vine root zone
    ze_m=0.10,                      # m, FAO-56 evaporation layer
    rew_mm=10.0,                    # mm, FAO-56 Table 19 clay (8-12)
    kc_min=0.15,                    # FAO-56 Kc_min for bare soil (eq. 76)
    kc_max_climate=1.2,             # FAO-56 eq. 72 with u2 = 2 m/s, RHmin = 45 % (no wind/RH in local data)
    dr0_mm=0.0,                     # start 1991-01-01 at field capacity (winter); spin-up years discarded
)
VINE = dict(p_base=0.45, h_m=1.5)    # VSP trellis height ~1.5 m
GRASS = dict(p_base=0.50, h_m=0.15)  # station plot (grass / fallow)

NDVI = dict(
    min_clear=0.9,        # VEG_MIN_CLEAR_FRAC of v1.0
    despike_window=3,     # running median over 3 scenes
    max_gap_days=30,      # longer gaps -> climatological Kcb
)

# TAW grid for the leave-one-year-out calibration (variant V5); TAW = 140 mm/m * Zr
ZR_GRID_M = [0.35, 0.5, 0.75, 1.0, 1.5]   # -> TAW 49, 70, 105, 140, 210 mm
SPEI_DAYS = [30, 60, 90]
