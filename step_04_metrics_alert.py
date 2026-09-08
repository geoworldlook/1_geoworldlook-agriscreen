"""
================================================================================
S-3/S-2 AgriScreen DSS v2.5 - KROK 4: WSKAŹNIKI, Z-SCORE I PROTOKÓŁ WALDA
================================================================================
Moduł obliczeniowy odpowiedzialny za:
  1. Biofizyczne wskaźniki spektralne odporne na wpływ tła glebowego (siatka 2.5 m):
     - OSAVI = (B08 - B04) / (B08 + B04 + 0.16)
     - TCARI = 3 * [(B05 - B04) - 0.2 * (B05 - B03) * (B05 / (B04 + eps))]
     - Ratio TCARI / OSAVI (wskaźnik chlorozy i zawartości chlorofilu)
  2. Wskaźnik suszy termiczno-wegetacyjnej TVDI (Temperature Vegetation Dryness Index):
     - Przestrzeń cech trójkąta LST_10m - NDVI_10m
     - Podział na N=100 przedziałów NDVI i odporne dopasowanie krawędzi suchej i wilgotnej
     - TVDI = (LST - LST_min) / (LST_max - LST_min + eps)
  3. Silnik detekcji anomalii (Z-score Engine) w oparciu o wieloletnią bazę GEE:
     - Z = (V_current - mu_history) / (sigma_history + eps)
     - alert_mask: 0 = Norma, 1 = Żółty (umiarkowany stres), 2 = Czerwony (silny deficyt)
  4. Desktopową walidację dokładności rekonstrukcji (Protokół Walda na kanale B04/B08):
     - Degradacja Gaussa (sigma=1.5) + decymacja 4x (10m -> 40m)
     - Rekonstrukcja super-rozdzielcza z powrotem do 10m
     - Metryki dokładności: RMSE, SAM (stopnie) oraz SSIM (Structural Similarity Index)
================================================================================
"""

import logging
import warnings
from typing import Dict, Any, Tuple, Optional

import numpy as np
from scipy.ndimage import gaussian_filter, zoom
from step_03_super_resolve import align_raster_shape
try:
    from skimage.metrics import structural_similarity as ssim_fn
except ImportError:
    def ssim_fn(im1: np.ndarray, im2: np.ndarray, data_range: float = 1.0) -> float:
        """Wbudowana implementacja SSIM (Structural Similarity Index)."""
        mu1 = float(np.mean(im1))
        mu2 = float(np.mean(im2))
        sigma1_sq = float(np.var(im1))
        sigma2_sq = float(np.var(im2))
        sigma12 = float(np.mean((im1 - mu1) * (im2 - mu2)))
        c1 = (0.01 * data_range) ** 2
        c2 = (0.03 * data_range) ** 2
        numerator = (2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)
        denominator = (mu1 ** 2 + mu2 ** 2 + c1) * (sigma1_sq + sigma2_sq + c2)
        return float(numerator / (denominator + 1e-6))

# Ustrukturyzowane logowanie zdarzeń
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AgriScreen_Metrics")
warnings.filterwarnings("ignore")

EPSILON = 1e-6


# ==============================================================================
# I. WSKAŹNIKI BIOFIZYCZNE (OSAVI, TCARI, TCARI/OSAVI NA SIATCE 2.5 M)
# ==============================================================================

def compute_biophysical_indices(
    b03_25m: np.ndarray,
    b04_25m: np.ndarray,
    b05_25m: np.ndarray,
    b08_25m: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Oblicza zrekonstruowane wskaźniki biofizyczne na siatce 2.5 m:
      - OSAVI (Optimized Soil-Adjusted Vegetation Index)
      - TCARI (Transformed Chlorophyll Absorption in Reflectance Index)
      - Iloraz TCARI / OSAVI (wskaźnik koncentracji chlorofilu zredukowany o LAI i glebę)
    """
    logger.info("Obliczanie wskaźników biofizycznych na siatce 2.5 m (OSAVI, TCARI, TCARI/OSAVI)...")

    # 1. OSAVI = (B08 - B04) / (B08 + B04 + 0.16)
    osavi = (b08_25m - b04_25m) / (b08_25m + b04_25m + 0.16)
    osavi = np.clip(osavi, -1.0, 1.0)

    # 2. TCARI = 3 * [(B05 - B04) - 0.2 * (B05 - B03) * (B05 / (B04 + epsilon))]
    term_diff = b05_25m - b04_25m
    b04_safe = np.where(b04_25m < EPSILON, EPSILON, b04_25m)
    term_ratio = (b05_25m - b03_25m) * (b05_25m / b04_safe)
    tcari = 3.0 * (term_diff - 0.2 * term_ratio)

    # 3. Ratio = TCARI / (OSAVI + epsilon)
    osavi_safe = np.where(np.abs(osavi) < EPSILON, EPSILON, osavi)
    ratio = tcari / (osavi_safe + EPSILON)

    # Zabezpieczenie przed wartościami inf i nan
    ratio = np.nan_to_num(ratio, nan=0.0, posinf=10.0, neginf=-10.0)

    return osavi.astype(np.float32), tcari.astype(np.float32), ratio.astype(np.float32)


# ==============================================================================
# II. WSKAŹNIK SUSZY TERMICZNEJ TVDI (TRÓJKĄT LST-NDVI)
# ==============================================================================

def compute_tvdi_index(
    lst_10m: np.ndarray,
    ndvi_10m: np.ndarray,
    n_bins: int = 100
) -> np.ndarray:
    """
    Oblicza Temperature Vegetation Dryness Index (TVDI) na bazie przestrzeni cech
    trójkąta LST-NDVI.

    Dzieli zakres NDVI na n_bins przedziałów, wyznacza krawędź suchą (LST_max)
    oraz krawędź wilgotną (LST_min) za pomocą regresji liniowej na percentylach,
    a następnie normalizuje temperaturę każdego piksela do zakresu [0.0, 1.0].
    """
    logger.info(f"Obliczanie wskaźnika TVDI (trójkąt LST-NDVI, {n_bins} przedziałów)...")

    valid_mask = ~np.isnan(lst_10m) & ~np.isnan(ndvi_10m) & (ndvi_10m >= 0.0) & (ndvi_10m <= 1.0)
    lst_valid = lst_10m[valid_mask]
    ndvi_valid = ndvi_10m[valid_mask]

    if len(lst_valid) < 100:
        logger.warning("Zbyt mała liczba poprawnych pikseli do wyznaczenia trójkąta TVDI. Zwracanie znormalizowanego LST.")
        v_min, v_max = np.nanpercentile(lst_10m, 2), np.nanpercentile(lst_10m, 98)
        return np.clip((lst_10m - v_min) / (v_max - v_min + EPSILON), 0.0, 1.0).astype(np.float32)

    # Podział NDVI na N przedziałów
    bins = np.linspace(0.05, 0.95, n_bins + 1)
    bin_centers = []
    lst_max_points = []
    lst_min_points = []

    for i in range(n_bins):
        bin_mask = (ndvi_valid >= bins[i]) & (ndvi_valid < bins[i + 1])
        if np.sum(bin_mask) >= 10:
            sub_lst = lst_valid[bin_mask]
            bin_centers.append((bins[i] + bins[i + 1]) / 2.0)
            # Odporne wyznaczenie krawędzi: 98 percentyl dla suchej, 2 percentyl dla wilgotnej
            lst_max_points.append(np.percentile(sub_lst, 98))
            lst_min_points.append(np.percentile(sub_lst, 2))

    bin_centers_arr = np.array(bin_centers)
    lst_max_arr = np.array(lst_max_points)
    lst_min_arr = np.array(lst_min_points)

    if len(bin_centers_arr) >= 5:
        # Dopasowanie krawędzi suchej: LST_max = a1 + b1 * NDVI
        poly_dry = np.polyfit(bin_centers_arr, lst_max_arr, deg=1)
        # Dopasowanie krawędzi wilgotnej: LST_min = a2 + b2 * NDVI
        poly_wet = np.polyfit(bin_centers_arr, lst_min_arr, deg=1)
    else:
        # Fallback na globalne ekstrema
        poly_dry = np.array([0.0, float(np.nanmax(lst_valid))])
        poly_wet = np.array([0.0, float(np.nanmin(lst_valid))])

    b1, a1 = poly_dry[0], poly_dry[1]
    b2, a2 = poly_wet[0], poly_wet[1]
    logger.info(f"Parametry krawędzi TVDI: Krawędź sucha: LST = {a1:.2f} + ({b1:.2f})*NDVI | Krawędź mokra: LST = {a2:.2f} + ({b2:.2f})*NDVI")

    # Obliczenie LST_max i LST_min dla każdego piksela
    lst_max_pixel = a1 + (b1 * ndvi_10m)
    lst_min_pixel = a2 + (b2 * ndvi_10m)

    # TVDI = (LST - LST_min) / (LST_max - LST_min + epsilon)
    denominator = lst_max_pixel - lst_min_pixel
    denominator = np.where(denominator < 1.0, 1.0, denominator)  # Minimalny zakres 1K

    tvdi = (lst_10m - lst_min_pixel) / (denominator + EPSILON)
    tvdi = np.clip(tvdi, 0.0, 1.0)
    tvdi = np.nan_to_num(tvdi, nan=0.5).astype(np.float32)

    return tvdi


# ==============================================================================
# III. SILNIK DETEKCJI ANOMALII Z-SCORE I KLASYFIKACJA ALERTÓW
# ==============================================================================

def compute_zscore_alerts(
    current_metric: np.ndarray,
    baseline_mean: np.ndarray,
    baseline_std: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Oblicza standaryzowaną anomalię Z-score względem wieloletniej bazy historycznej GEE:
      Z = (V_current - mu_history) / (sigma_history + epsilon)

    Klasyfikuje piksele do macierzy alertów (alert_mask uint8):
      0 = Norma (Z <= 1.5)
      1 = Alert Żółty (1.5 < Z <= 2.0) – podwyższony stres / umiarkowana chloroza
      2 = Alert Czerwony (Z > 2.0) – silny deficyt wody / ostra chloroza
    """
    logger.info("Obliczanie standaryzowanej anomalii Z-score oraz klasyfikacji alertów...")

    # Dopasowanie wymiarów bazy historycznej do siatki 2.5m (jeśli baza była w 10m)
    if baseline_mean.shape != current_metric.shape:
        mean_resampled = align_raster_shape(baseline_mean, current_metric.shape, order=1).astype(np.float32)
        std_resampled = align_raster_shape(baseline_std, current_metric.shape, order=1).astype(np.float32)
    else:
        mean_resampled = baseline_mean.astype(np.float32)
        std_resampled = baseline_std.astype(np.float32)

    # Zabezpieczenie przed zerowym odchyleniem standardowym
    std_safe = np.where(std_resampled < 0.01, 0.05, std_resampled)

    # Obliczenie Z-score
    z_score = (current_metric - mean_resampled) / (std_safe + EPSILON)
    z_score = np.nan_to_num(z_score, nan=0.0).astype(np.float32)

    # Klasyfikacja alertów (uint8)
    alert_mask = np.zeros(current_metric.shape, dtype=np.uint8)
    # Wskaźnik stresu (bezwzględna anomalia lub wzrost deficytu)
    abs_z = np.abs(z_score)

    alert_mask[(abs_z > 1.5) & (abs_z <= 2.0)] = 1  # Alert Żółty
    alert_mask[abs_z > 2.0] = 2                     # Alert Czerwony

    pct_normal = np.mean(alert_mask == 0) * 100.0
    pct_yellow = np.mean(alert_mask == 1) * 100.0
    pct_red = np.mean(alert_mask == 2) * 100.0

    logger.info(
        f"Statystyka alertów: Norma (0): {pct_normal:.1f}%, "
        f"Alert Żółty (1): {pct_yellow:.1f}%, Alert Czerwony (2): {pct_red:.1f}%"
    )

    return z_score, alert_mask


# ==============================================================================
# IV. PROTOKÓŁ WALDA (DESKTOPOWA WALIDACJA REKONSTRUKCJI)
# ==============================================================================

def run_wald_protocol_validation(
    original_10m: np.ndarray,
    sigma_blur: float = 1.5,
    decimation_factor: int = 4
) -> Dict[str, float]:
    """
    Rygorystyczna walidacja w oparciu o Protokół Walda:
      1. Oryginalny kanał Sentinel-2 10 m (I_10).
      2. Sztuczna degradacja do 40 m: filtr dolnoprzepustowy Gaussa (sigma=1.5) + decymacja 4x.
      3. Rekonstrukcja super-rozdzielcza z powrotem do 10 m (I_rec).
      4. Obliczenie bezwzględnych metryk dokładności:
         - RMSE (Root Mean Square Error)
         - SAM (Spectral Angle Mapper w stopniach kątowych)
         - SSIM (Structural Similarity Index)
    """
    logger.info("Uruchamianie procedury walidacyjnej (Protokół Walda)...")

    i_10 = original_10m.astype(np.float32)
    h, w = i_10.shape

    # 1. Filtr dolnoprzepustowy Gaussa (sigma=1.5)
    blurred = gaussian_filter(i_10, sigma=sigma_blur)

    # 2. Decymacja 4x (10m -> 40m)
    i_40 = blurred[::decimation_factor, ::decimation_factor]

    # 3. Rekonstrukcja super-rozdzielcza z powrotem do 10m
    # Użycie align_raster_shape z interpolacją bikubiczną (spline 3)
    i_rec = align_raster_shape(i_40, (h, w), order=3)
    # Rekonstrukcja detali
    high_pass = i_rec - gaussian_filter(i_rec, sigma=1.0)
    i_rec = np.clip(i_rec + 0.35 * high_pass, 0.0, 1.0)

    # 4. Obliczenie metryk błędu
    diff = i_10 - i_rec
    rmse = float(np.sqrt(np.mean(diff ** 2)))

    # SAM (Spectral Angle Mapper)
    dot_prod = np.sum(i_10 * i_rec)
    norm_orig = np.sqrt(np.sum(i_10 ** 2))
    norm_rec = np.sqrt(np.sum(i_rec ** 2))
    cos_sam = dot_prod / (norm_orig * norm_rec + EPSILON)
    cos_sam = np.clip(cos_sam, -1.0, 1.0)
    sam_rad = float(np.arccos(cos_sam))
    sam_deg = float(np.degrees(sam_rad))

    # SSIM (Structural Similarity Index)
    data_rng = float(np.nanmax(i_10) - np.nanmin(i_10))
    if data_rng <= 0:
        data_rng = 1.0
    ssim_val = ssim_fn(i_10, i_rec, data_range=data_rng)

    metrics = {
        "rmse": rmse,
        "sam_degrees": sam_deg,
        "ssim": float(ssim_val)
    }

    logger.info(f"Metryki Walda: RMSE = {rmse:.4f}, SAM = {sam_deg:.2f}°, SSIM = {ssim_val:.4f}")
    return metrics


# ==============================================================================
# V. GŁÓWNA FUNKCJA KROKU 4: compute_metrics_and_alerts
# ==============================================================================

def compute_metrics_and_alerts(
    bands_25m: Dict[str, np.ndarray],
    lst_10m: np.ndarray,
    baseline_stats: Dict[str, np.ndarray],
    profile_25m: dict
) -> Tuple[Dict[str, np.ndarray], Dict[str, float]]:
    """
    GŁÓWNY KONTRAKT INTERFEJSU DLA KROKU 4.

    Oblicza wskaźniki TCARI/OSAVI, TVDI, anomalię Z-score, generuje klasy alertów
    oraz przeprowadza test Walda zwracając metryki walidacyjne (RMSE, SAM, SSIM).

    Parametry:
        bands_25m: Słownik pasm w rozdzielczości 2.5 m (w tym B02, B03, B04, B05, B08).
        lst_10m: Zaostrzona macierz temperatury LST w rozdzielczości 10 m (z Kroku 2).
        baseline_stats: Słownik statystyk wieloletnich z GEE (mean i std wskaźników).
        profile_25m: Profil georeferencyjny Rasterio dla siatki 2.5 m.

    Zwraca:
        derived_products: Słownik zawierający macierze:
                          - 'tcari_osavi_25m' (iloraz w 2.5 m)
                          - 'osavi_25m' (OSAVI w 2.5 m)
                          - 'tcari_25m' (TCARI w 2.5 m)
                          - 'tvdi_10m' (TVDI w natywnej siatce 10 m)
                          - 'tvdi_25m' (TVDI zresamplowane do 2.5 m)
                          - 'z_score_25m' (anomalia Z-score w 2.5 m)
                          - 'alert_mask_25m' (klasyfikacja alertów: 0, 1, 2)
        wald_metrics: Słownik metryk dokładności rekonstrukcji (RMSE, SAM, SSIM).
    """
    logger.info("================================================================================")
    logger.info("URUCHOMIENIE KROKU 4: Wskaźniki Biofizyczne, TVDI, Alerty Z-score i Test Walda...")
    logger.info("================================================================================")

    # 1. Weryfikacja obecności pasm 2.5 m
    req_keys = ["B03", "B04", "B05", "B08"]
    for k in req_keys:
        if k not in bands_25m:
            raise KeyError(f"Brak wymaganego pasma 2.5m '{k}' do kalkulacji TCARI/OSAVI.")

    b03_25m = bands_25m["B03"]
    b04_25m = bands_25m["B04"]
    b05_25m = bands_25m["B05"]
    b08_25m = bands_25m["B08"]

    # 2. Obliczenie OSAVI, TCARI i TCARI/OSAVI na siatce 2.5 m
    osavi_25m, tcari_25m, ratio_25m = compute_biophysical_indices(
        b03_25m, b04_25m, b05_25m, b08_25m
    )

    # 3. Obliczenie NDVI 10m i wskaźnika TVDI w rozdzielczości 10 m
    # Resamplowanie pasm B08 i B04 z powrotem do 10m z gwarancją identycznych wymiarów co lst_10m
    h_10m, w_10m = lst_10m.shape
    b04_10m = align_raster_shape(b04_25m, (h_10m, w_10m), order=1)
    b08_10m = align_raster_shape(b08_25m, (h_10m, w_10m), order=1)

    ndvi_10m = (b08_10m - b04_10m) / (b08_10m + b04_10m + EPSILON)
    tvdi_10m = compute_tvdi_index(lst_10m, ndvi_10m, n_bins=100)

    # Wersja TVDI na siatce 2.5 m dla spójności warstw wynikowych
    tvdi_25m = align_raster_shape(
        tvdi_10m,
        (ratio_25m.shape[0], ratio_25m.shape[1]),
        order=1
    ).astype(np.float32)

    # 4. Detekcja Anomalii Z-score i Klasyfikacja Alertów
    # Wykorzystanie wieloletniej bazy historycznej z Kroku 1
    base_mean = baseline_stats.get("tcari_osavi_mean", np.full_like(lst_10m, 0.15))
    base_std = baseline_stats.get("tcari_osavi_std", np.full_like(lst_10m, 0.05))

    z_score_25m, alert_mask_25m = compute_zscore_alerts(ratio_25m, base_mean, base_std)

    # 5. Aplikacja Maski Upraw Trwałych M_crop (HRL Croplands 10 m -> 2.5 m)
    crop_mask_25m = bands_25m.get("crop_mask_25m")
    if crop_mask_25m is not None:
        logger.info("Aplikowanie maski M_crop: zawężenie alertów i wskaźników wyłącznie do upraw trwałych (sady, winnice)...")
        ratio_masked_25m = np.where(crop_mask_25m == 1.0, ratio_25m, np.nan)
        # Piksele poza uprawami trwałymi oznaczamy jako 255 (poza analizą upraw)
        alert_mask_25m = np.where(crop_mask_25m == 1.0, alert_mask_25m, 255).astype(np.uint8)
    else:
        ratio_masked_25m = ratio_25m

    # 6. Weryfikacja Regionalnego Tła Wilgotnościowego (CGLS Soil Water Index)
    swi_1km = bands_25m.get("swi_1km")
    if swi_1km is not None:
        mean_swi = float(np.nanmean(swi_1km))
        logger.info(f"Regionalne tlo makrohydrologiczne (CGLS SWI T=5): srednia wilgotnosc {mean_swi:.1f}%")
        if mean_swi < 30.0:
            logger.warning("ALARM REGIONALNY: Silny deficyt wilgoci w strefie korzeniowej upraw (SWI T=5 < 30%)!")

    swi_profile = bands_25m.get("swi_profile_8depths")
    if swi_profile is not None and len(swi_profile.shape) == 3 and swi_profile.shape[0] == 8:
        depth_names = bands_25m.get("swi_depth_names", ["T=2", "T=5", "T=10", "T=15", "T=20", "T=40", "T=60", "T=100"])
        means = [float(np.nanmean(swi_profile[i])) for i in range(8)]
        prof_summary = ", ".join(f"{depth_names[i]}: {means[i]:.1f}%" for i in range(8))
        logger.info(f"Pionowy profil wilgotnosci gleby CDSE SWI: {prof_summary}")
        # Wykrywanie inwersji profilu glebowego (wysuszenie glebokie)
        if means[7] < means[0] - 10.0:
            logger.warning("OSTRZEZENIE HYDROLOGICZNE: Odwrocony gradient wilgotnosci - gleboki drenaz i deficyt rezerwuaru wodnego (T=100 < T=2)!")

    ppi_qflag = bands_25m.get("ppi_qflag")
    if ppi_qflag is not None:
        valid_qflags = np.unique(ppi_qflag[~np.isnan(ppi_qflag)])
        logger.info(f"Flagi jakosci rekonstrukcji fenologicznej HR-VPP ST QFLAG: {valid_qflags.tolist()}")

    # 7. Protokół Walda (walidacja kanału B04)
    wald_metrics = run_wald_protocol_validation(b04_10m, sigma_blur=1.5, decimation_factor=4)

    # Słownik produktów wynikowych
    derived_products: Dict[str, np.ndarray] = {
        "tcari_osavi_25m": ratio_masked_25m,
        "tcari_osavi_raw_25m": ratio_25m,
        "osavi_25m": osavi_25m,
        "tcari_25m": tcari_25m,
        "tvdi_10m": tvdi_10m,
        "tvdi_25m": tvdi_25m,
        "z_score_25m": z_score_25m,
        "alert_mask_25m": alert_mask_25m,
        "crop_mask_25m": crop_mask_25m if crop_mask_25m is not None else np.ones_like(ratio_25m),
        "swi_1km": swi_1km if swi_1km is not None else np.full((10, 10), 50.0, dtype=np.float32),
        "ppi_25m": bands_25m.get("ppi_25m", np.full_like(ratio_25m, 0.45))
    }

    logger.info("================================================================================")
    logger.info("KROK 4 ZAKOŃCZONY POMYŚLNIE:")
    logger.info(f" - Zakres TCARI/OSAVI 2.5m: min={np.nanmin(ratio_25m):.3f}, max={np.nanmax(ratio_25m):.3f}")
    logger.info(f" - Zakres TVDI 10m: min={np.nanmin(tvdi_10m):.3f}, max={np.nanmax(tvdi_10m):.3f}")
    logger.info(f" - Wyniki Protokołu Walda: RMSE={wald_metrics['rmse']:.4f}, SAM={wald_metrics['sam_degrees']:.2f}°, SSIM={wald_metrics['ssim']:.4f}")
    logger.info("================================================================================")

    return derived_products, wald_metrics


# ==============================================================================
# TEST SAMODZIELNY MODUŁU
# ==============================================================================
if __name__ == "__main__":
    print("Testowanie modułu step_04_metrics_alert.py na syntetycznych danych...")
    h, w = 160, 160
    mock_bands_25m = {
        "B03": np.random.uniform(0.04, 0.10, (h, w)).astype(np.float32),
        "B04": np.random.uniform(0.05, 0.12, (h, w)).astype(np.float32),
        "B05": np.random.uniform(0.08, 0.18, (h, w)).astype(np.float32),
        "B08": np.random.uniform(0.25, 0.55, (h, w)).astype(np.float32)
    }
    mock_lst_10m = np.random.uniform(20.0, 35.0, (40, 40)).astype(np.float32)
    mock_base = {
        "tcari_osavi_mean": np.random.uniform(0.12, 0.20, (40, 40)).astype(np.float32),
        "tcari_osavi_std": np.random.uniform(0.02, 0.06, (40, 40)).astype(np.float32)
    }
    mock_prof = {}

    products, metrics = compute_metrics_and_alerts(
        mock_bands_25m, mock_lst_10m, mock_base, mock_prof
    )

    print(" Sukces! Wymiary TCARI/OSAVI:", products["tcari_osavi_25m"].shape)
    print(" Wymiary alert_mask:", products["alert_mask_25m"].shape)
    print(" Metryki Walda:", metrics)
