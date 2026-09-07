# Katalog: 06_Landsat_Validation

W tym katalogu gromadzone są referencyjne dane termiczne Landsat 8/9 L2 ST_B10 (30 m) pobierane z Google Earth Engine, mapy reszt przestrzennych (różnice temperatur) oraz raporty walidacyjne dokładności downscalingu termicznego.

## Zawartość katalogu:
- `Landsat_ST_30m_YYYY-MM-DD.tif` – pobrane referencyjne zobrazowanie Landsat ST w rozdzielczości 30 m (°C).
- `Residual_LST_Landsat_YYYY-MM-DD.tif` – mapa błędów przestrzennych (LST_10m_upscaled - LST_Landsat_30m).
- `landsat_validation_report.md` – zbiorczy raport walidacyjny z metrykami statystycznymi (RMSE, MAE, Bias, Pearson r, SSIM).
