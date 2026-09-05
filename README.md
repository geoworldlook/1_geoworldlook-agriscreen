# S-3/S-2 AgriScreen DSS v2.5
### System Wczesnego Wykrywania Anomalii Wilgotnościowych i Fizjologicznych w Uprawach Wieloletnich

[![GitHub Repo](https://img.shields.io/badge/GitHub-geoworldlook%2F1__geoworldlook--agriscreen-blue?logo=github)](https://github.com/geoworldlook/1_geoworldlook-agriscreen)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/geoworldlook/1_geoworldlook-agriscreen/blob/main/AgriScreen_Colab_Master.ipynb)

Potok przetwarzania teledetekcyjnego w języku **Python 3.10+**, zoptymalizowany pod środowisko **Google Colab (GPU T4, 12 GB RAM)** oraz chmurowy silnik **Google Earth Engine (GEE)**.
Dane i gotowe produkty GeoTIFF przechowywane są trwale na **Dysku Google** (`/content/drive/MyDrive/1_geoworldlook-agriscreen`).

System analizuje rzeczywiste dane satelitarne dla upraw wieloletnich (sady owocowe, winnice) w rejonie poligonu badawczego **GBOV Condom (Gers, Francja)** zdefiniowanego w pliku [`data/1_AOI_GBOV_CONDOM.geojson`](file:///c:/Users/dawids/OneDrive%20-%20opegieka.pl/Pulpit/OneDrive%20-%20opegieka.pl/Pulpit/DAWID/GEOWORLDLOOK/2_geoworldlook/data/1_AOI_GBOV_CONDOM.geojson).

---

## Architektura Modułowa i Struktura Projektu

Struktura katalogów została zaprojektowana zgodnie z wymogiem płaskiej struktury Colab (`/content/`) oraz dedykowanej hierarchii danych:

```text
2_geoworldlook/
│
├── data/
│   ├── 1_AOI_GBOV_CONDOM.geojson      # Granice 23 działek testowych (sady, winnice, gleba)
│   ├── 00_Metadata/                   # Manifest pobranych scen (ingest_manifest.json)
│   ├── 01_Raw_Sentinel2/              # Pobrane sceny S2 L2A (10 pasm + maska chmur)
│   ├── 02_Raw_Thermal_LST/            # Dane termalne LST 1km (S3 SLSTR / Copernicus Thermal)
│   ├── 03_Copernicus_Auxiliary/       # Copernicus DEM GLO-30 oraz Copernicus Land Cover
│   ├── 04_Processed_Intermediates/    # Dane pośrednie
│   └── 05_Final_Outputs/              # Gotowe COG GeoTIFF i raporty walidacyjne
│
├── step_01_ingest.py                  # Moduł 1: Ingestia GEE, S2 L2A, S3 LST, DEM i bazy 2018-2025
├── step_02_align_and_scale.py         # Moduł 2: Korejestracja AROSICS i deagregacja pyDMS (1km -> 10m)
├── step_03_super_resolve.py           # Moduł 3: SEN2SR 2.5m (RGBN) i fuzja geostatystyczna ATPRK (20m, LST)
├── step_04_metrics_alert.py           # Moduł 4: Wskaźniki TCARI/OSAVI, TVDI, Z-score i Protokół Walda
├── step_05_colab_run.py               # Moduł 5: Master Orchestrator potoku
│
├── test_pipeline.py                   # Skrypt testowy integracji modułów i odporności numerycznej
├── notebooks/
│   └── AgriScreen_Colab_Pipeline.ipynb # Interaktywny Jupyter Notebook dla Google Colab
└── README.md                          # Dokumentacja techniczna
```

---

## Wymagania i Zależności

W środowisku Google Colab instalacja pakietów odbywa się poleceniem:
```bash
pip install -q earthengine-api geemap geedim rasterio geopandas scikit-image scikit-learn scipy affine mlstac sen2sr arosics pydms
```

---

## Specyfikacja Algorytmiczna

### 1. Ingestia i Baza Historyczna GEE (`step_01_ingest.py`)
- **Sentinel-2 L2A BOA:** Pasma `B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12`.
- **Maskowanie chmur i cieni:** Połączenie prawdopodobieństwa `COPERNICUS/S2_CLOUD_PROBABILITY` (< 15%), filtracji warstwy `SCL` oraz geometrycznej projekcji cieni na bazie kąta azymutu słońca.
- **Skalowanie:** Rygorystyczny podział surowych wartości DN przez $10000.0$ do zakresu $[0.0, 1.0]$.
- **Sentinel-3 SLSTR / Copernicus Thermal LST:** Dopasowanie czasowe $\pm 24\text{ h}$ względem S2.
- **Copernicus DEM GLO-30:** Numeryczny model terenu 30 m resamplowany do siatki 10 m.
- **Agregacja wieloletnia (2018–2025):** Pikselowa średnia i odchylenie standardowe wskaźników TCARI/OSAVI oraz NDVI/TVDI liczone bezpośrednio w silniku GEE.
- **Przyrostowa synchronizacja (Incremental Sync):** Automatyczna detekcja istniejących scen w manifeście `ingest_manifest.json` – pobieranie tylko nowo opublikowanych zobrazowań.

### 2. Korejestracja i Downscaling Termiczny (`step_02_align_and_scale.py`)
- **AROSICS:** Subpikselowa korekta przesunięć geometrycznych LST względem kanału referencyjnego B08 (10 m) metodą korelacji fazowej.
- **Poprawka adiabatyczna (Lapse Rate):**
  $$\text{LST}_{\text{norm}} = \text{LST}_{\text{raw}} + 0.006 \cdot \text{DEM}$$
- **Deagregacja pyDMS:** Bagging drzew decyzyjnych (`BaggingRegressor` z `DecisionTreeRegressor`) z cechami przewodzącymi NDVI 10 m i DEM 10 m.
- **Konserwacja energii (Gaussian Residual Compensation):** Rozproszenie reszt filtrem Gaussa dla zachowania bilansu radiometrycznego.
- **Przywrócenie temperatury:**
  $$\text{LST}_{10\text{m}} = \text{LST}_{\text{norm\_10m}} - 0.006 \cdot \text{DEM}_{10\text{m}}$$

### 3. Super-Rozdzielczość SEN2SR i Fuzja ATPRK (`step_03_super_resolve.py`)
- **SEN2SR (Deep Learning):** Model `NonReference_RGBN_x4` (`tacofoundation/sen2sr`) podnoszący pasma 10 m do 2.5 m/px. Zarządzanie VRAM: `torch.cuda.empty_cache()` i przetwarzanie kafelkowe.
- **ATPRK (Area-To-Point Regression Kriging):**
  - Pasma 20 m (`B05, B06, B07, B8A, B11, B12`) oraz `LST_10m` fuzjowane do siatki 2.5 m.
  - Regresja wielozmienna + dyspersja reszt z uwzględnieniem PSF (Point Spread Function) sensora.
  - Bezwzględna konserwacja energii radiometrycznej (uśrednienie blokowe 2.5 m równe wartości wyjściowego piksela coarse).
- **Profil Affine:** Nowy rozmiar piksela $2.5\text{ m} \times 2.5\text{ m}$.

### 4. Wskaźniki, Detekcja Anomalii i Walidacja (`step_04_metrics_alert.py`)
- **OSAVI (2.5 m):**
  $$\text{OSAVI} = \frac{\text{B08} - \text{B04}}{\text{B08} + \text{B04} + 0.16}$$
- **TCARI (2.5 m):**
  $$\text{TCARI} = 3 \cdot \left[ (\text{B05} - \text{B04}) - 0.2 \cdot (\text{B05} - \text{B03}) \cdot \frac{\text{B05}}{\text{B04} + 1e-6} \right]$$
- **Ratio (2.5 m):** $\text{TCARI} / (\text{OSAVI} + 1e-6)$.
- **TVDI (10 m):** Przestrzeń trójkąta LST-NDVI (100 przedziałów), odporne dopasowanie krawędzi suchej i wilgotnej.
- **Silnik Z-score i Alerty (2.5 m):**
  $$Z = \frac{V_{\text{current}} - \mu_{\text{history}}}{\sigma_{\text{history}} + 1e-6}$$
  - `0`: Norma ($Z \le 1.5$)
  - `1`: Alert Żółty ($1.5 < Z \le 2.0$) – podwyższony stres ewapotranspiracyjny / umiarkowana chloroza
  - `2`: Alert Czerwony ($Z > 2.0$) – silny deficyt wody / ostra chloroza
- **Protokół Walda:** Degradacja Gaussa ($\sigma=1.5$, decymacja $\times 4$), super-rozdzielcza rekonstrukcja i metryki RMSE, SAM (stopnie), SSIM.

### 5. Orkiestracja i Produkty Końcowe (`step_05_colab_run.py`)
- Zapis w standardzie **Cloud-Optimized GeoTIFF (COG)** z kompresją LZW i kafelkowaniem $256 \times 256$:
  - `LST_10m_sharpened.tif`
  - `TCARI_OSAVI_2.5m.tif`
  - `TVDI_10m.tif`
  - `Alert_Matrix_2.5m.tif`
- Automatyczne wygenerowanie raportu Markdown [`validation_report.md`](file:///c:/Users/dawids/OneDrive%20-%20opegieka.pl/Pulpit/OneDrive%20-%20opegieka.pl/Pulpit/DAWID/GEOWORLDLOOK/2_geoworldlook/data/05_Final_Outputs/validation_report.md).

---

## Uruchomienie w Google Colab

1. Umieść folder projektu w środowisku Colab lub na Dysku Google.
2. Otwórz notatnik [`notebooks/AgriScreen_Colab_Pipeline.ipynb`](file:///c:/Users/dawids/OneDrive%20-%20opegieka.pl/Pulpit/OneDrive%20-%20opegieka.pl/Pulpit/DAWID/GEOWORLDLOOK/2_geoworldlook/notebooks/AgriScreen_Colab_Pipeline.ipynb).
3. Wybierz środowisko wykonawcze z akceleratorem **GPU (T4)**.
4. Uruchamiaj komórki sekwencyjnie.
