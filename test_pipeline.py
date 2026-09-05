"""
================================================================================
TEST AUTOMATYCZNY POTOKU AgriScreen DSS v2.5
================================================================================
Skrypt weryfikujący poprawność działania interfejsów funkcyjnych, typowania statycznego,
spójności georeferencyjnej siatek 10 m i 2.5 m oraz odporności numerycznej.
================================================================================
"""

import os
import sys
import numpy as np
from affine import Affine
import rasterio

from step_02_align_and_scale import align_and_scale_lst
from step_03_super_resolve import super_resolve_bands
from step_04_metrics_alert import compute_metrics_and_alerts
from step_05_colab_run import write_cog_geotiff, generate_validation_report

def run_integration_test():
    print("================================================================================")
    print("ROZPOCZĘCIE TESTU INTEGRACYJNEGO POTOKU...")
    print("================================================================================")

    # 1. Symulacja danych wyjściowych z Kroku 1 (10m grid)
    h_10m, w_10m = 80, 80
    bands_10m = ["B02", "B03", "B04", "B08"]
    bands_20m = ["B05", "B06", "B07", "B8A", "B11", "B12"]

    s2_bands = {}
    for b in bands_10m:
        s2_bands[b] = np.random.uniform(0.04, 0.40, (h_10m, w_10m)).astype(np.float32)
    for b in bands_20m:
        s2_bands[b] = np.random.uniform(0.05, 0.35, (h_10m // 2, w_10m // 2)).astype(np.float32)

    dem = np.random.uniform(110.0, 190.0, (h_10m, w_10m)).astype(np.float32)
    s3_lst_raw = np.random.uniform(23.0, 31.0, (8, 8)).astype(np.float32)
    profile_10m = {
        'driver': 'GTiff',
        'width': w_10m,
        'height': h_10m,
        'count': 1,
        'dtype': 'float32',
        'crs': 'EPSG:32631',
        'transform': Affine(10.0, 0.0, 440000.0, 0.0, -10.0, 4870000.0)
    }

    baseline_stats = {
        "tcari_osavi_mean": np.random.uniform(0.10, 0.25, (h_10m, w_10m)).astype(np.float32),
        "tcari_osavi_std": np.random.uniform(0.02, 0.08, (h_10m, w_10m)).astype(np.float32),
        "tvdi_mean": np.random.uniform(0.40, 0.60, (h_10m, w_10m)).astype(np.float32),
        "tvdi_std": np.random.uniform(0.10, 0.20, (h_10m, w_10m)).astype(np.float32)
    }

    # Krok 2: Korejestracja i downscaling
    print("\n--- Test Kroku 2: align_and_scale_lst ---")
    lst_10m = align_and_scale_lst(s2_bands, s3_lst_raw, dem, profile_10m)
    assert lst_10m.shape == (h_10m, w_10m), f"Błędny wymiar LST 10m: {lst_10m.shape}"
    assert not np.isnan(lst_10m).all(), "LST 10m zawiera same wartości NaN!"
    print(" Krok 2 ZDANY. Wymiary LST 10m:", lst_10m.shape)

    # Krok 3: Super-Rozdzielczość SEN2SR i Fuzja ATPRK
    print("\n--- Test Kroku 3: super_resolve_bands ---")
    bands_25m, profile_25m = super_resolve_bands(s2_bands, lst_10m, profile_10m)
    assert profile_25m['transform'].a == 2.5, "Transformacja afiniczna nie ma rozdzielczości 2.5m!"
    assert bands_25m['B04'].shape == (h_10m * 4, w_10m * 4), "B04 nie ma wymiarów 2.5m!"
    assert bands_25m['B05'].shape == (h_10m * 4, w_10m * 4), "B05 nie ma wymiarów 2.5m!"
    assert bands_25m['LST_2.5m'].shape == (h_10m * 4, w_10m * 4), "LST 2.5m nie ma wymiarów 2.5m!"
    print(" Krok 3 ZDANY. Wymiary siatki 2.5m:", bands_25m['B04'].shape)

    # Krok 4: Wskaźniki, Alerty i Test Walda
    print("\n--- Test Kroku 4: compute_metrics_and_alerts ---")
    products, metrics = compute_metrics_and_alerts(bands_25m, lst_10m, baseline_stats, profile_25m)
    assert 'tcari_osavi_25m' in products, "Brak wskaźnika TCARI/OSAVI w wynikach!"
    assert 'alert_mask_25m' in products, "Brak alert_mask w wynikach!"
    assert products['alert_mask_25m'].dtype == np.uint8, "alert_mask nie jest typu uint8!"
    assert 'rmse' in metrics and 'sam_degrees' in metrics and 'ssim' in metrics, "Brak metryk Walda!"
    print(f" Krok 4 ZDANY. Metryki Walda: RMSE={metrics['rmse']:.4f}, SAM={metrics['sam_degrees']:.2f}°, SSIM={metrics['ssim']:.4f}")

    # Krok 5: Test Zapisu COG i Raportu
    print("\n--- Test Kroku 5: Zapis COG i Raport ---")
    test_out = "data/05_Final_Outputs"
    os.makedirs(test_out, exist_ok=True)
    write_cog_geotiff(lst_10m, profile_10m, f"{test_out}/test_LST_10m.tif")
    write_cog_geotiff(products['alert_mask_25m'], profile_25m, f"{test_out}/test_Alert_2.5m.tif")

    report = generate_validation_report(
        config={"LAT": 43.97, "LON": 0.33, "TARGET_DATE": "2023-07-15", "BASELINE_YEARS": (2018, 2025)},
        runtimes={"step_01": 1.2, "step_02": 0.8, "step_03": 1.5, "step_04": 0.9, "step_05": 0.4},
        wald_metrics=metrics,
        alert_mask=products['alert_mask_25m'],
        output_dir=test_out
    )
    assert os.path.exists(report), "Raport Markdown nie został utworzony!"
    print(" Krok 5 ZDANY. Utworzono pliki COG i raport walidacyjny.")

    print("\n================================================================================")
    print("WSZYSTKIE TESTY JEDNOSTKOWE I INTEGRACYJNE ZAKOŃCZYŁY SIĘ PEŁNYM SUKCESEM!")
    print("================================================================================")

if __name__ == "__main__":
    run_integration_test()
