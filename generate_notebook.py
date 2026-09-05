"""
Generator notatnika Google Colab dla potoku AgriScreen DSS v2.5.
"""
import json

nb = {
    'cells': [],
    'metadata': {
        'colab': {'name': 'AgriScreen_Colab_Pipeline.ipynb', 'provenance': []},
        'accelerator': 'GPU',
        'gpuClass': 'standard',
        'language_info': {'name': 'python', 'version': '3.10.12'}
    },
    'nbformat': 4,
    'nbformat_minor': 0
}

def add_md(source):
    nb['cells'].append({
        'cell_type': 'markdown',
        'metadata': {},
        'source': [line + '\n' for line in source.strip().split('\n')]
    })

def add_code(source):
    nb['cells'].append({
        'cell_type': 'code',
        'execution_count': None,
        'metadata': {},
        'outputs': [],
        'source': [line + '\n' for line in source.strip().split('\n')]
    })

add_md("""# 🛰️ S-3/S-2 AgriScreen DSS v2.5
### System Wczesnego Wykrywania Anomalii Wilgotnościowych i Fizjologicznych w Uprawach Wieloletnich
**Środowisko:** Google Colab (GPU T4, 12 GB RAM) | Google Earth Engine (GEE)  
**Dane wejściowe:** Rzeczywiste dane satelitarne Sentinel-2, Sentinel-3 / LST 1km, Copernicus DEM GLO-30, CLMS  
**Obszar testowy:** GBOV Condom (`data/1_AOI_GBOV_CONDOM.geojson`)""")

add_md("## 📦 Krok 0: Instalacja Wymaganych Zależności w Google Colab")

add_code("""# Instalacja pakietów geoprzestrzennych i uczenia maszynowego
!pip install -q earthengine-api geemap geedim rasterio geopandas scikit-image scikit-learn scipy affine
# Opcjonalne zaawansowane biblioteki super-rozdzielczości i korejestracji
!pip install -q mlstac sen2sr arosics pydms || true

import torch
print(f'PyTorch: {torch.__version__} | Akcelerator CUDA: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)} (VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB)')
""")

add_md("## 📁 Krok 0.1: Montowanie Dysku Google (Opcjonalne)")

add_code("""import os
# Jeśli pracujesz na Google Colab, możesz zamontować Dysk Google
try:
    from google.colab import drive
    drive.mount('/content/drive')
    BASE_DIR = '/content/drive/MyDrive/AgriScreen_Project'
    print(f'✅ Zamontowano Google Drive: {BASE_DIR}')
except Exception:
    BASE_DIR = os.getcwd()
    print(f'ℹ️ Uruchomienie lokalne/Colab bez montowania dysku: {BASE_DIR}')
""")

add_md("## 🔑 Krok 0.2: Autoryzacja i Inicjalizacja Google Earth Engine (GEE)")

add_code("""import ee
import geemap

print('Inicjalizacja połączenia z Google Earth Engine...')
try:
    ee.Initialize()
    print('✅ Pomyślnie zainicjalizowano GEE!')
except Exception:
    print('Wymagana autoryzacja GEE. Postępuj zgodnie z instrukcjami na ekranie...')
    ee.Authenticate()
    ee.Initialize() # Jeśli posiadasz projekt, podaj: ee.Initialize(project='twoj-projekt')
    print('✅ Pomyślnie uwierzytelniono GEE!')
""")

add_md("## 🗺️ Krok 0.3: Konfiguracja Parametrów i Wizualizacja Poligonu AOI")

add_code("""import json
import geopandas as gpd

CONFIG = {
    'LAT': 43.9752,
    'LON': 0.3376,
    'TARGET_DATE': '2023-07-15',
    'BUFFER_M': 2000,
    'BASELINE_YEARS': (2018, 2025),
    'GEOJSON_PATH': 'data/1_AOI_GBOV_CONDOM.geojson',
    'OUTPUT_DIR': 'data/05_Final_Outputs',
    'DOWNLOAD_HISTORICAL': False
}

# Wczytanie i podgląd wektora działek
gdf = gpd.read_file(CONFIG['GEOJSON_PATH'])
print(f'Wczytano AOI: {len(gdf)} działek referencyjnych.')
display(gdf.head(3))

# Interaktywna mapa podglądowa
m = geemap.Map(center=[CONFIG['LAT'], CONFIG['LON']], zoom=14)
m.add_geojson(CONFIG['GEOJSON_PATH'], layer_name='Działki GBOV Condom')
m
""")

add_md("## 🛰️ MODUŁ 1: Ingestia Danych Satelitarnych GEE i Bazy Referencyjnej (`step_01_ingest.py`)")

add_code("""from step_01_ingest import ingest_satellite_data

# Pobranie zobrazowań rzeczywistych z GEE i Copernicus:
# 1. Sentinel-2 L2A (10 pasm BOA) z maskowaniem chmur s2cloudless i cieni
# 2. Sentinel-3 / 1km LST zbieżne czasowo (+/- 24h)
# 3. Copernicus DEM GLO-30 (30m)
# 4. Maska Upraw Trwałych HRL Croplands (10m: sady, winnice) -> M_crop
# 5. Regionalny Indeks Wilgotności CGLS Soil Water Index (SWI T=5, 1km, strefa korzeniowa)
# 6. Trajektoria Sezonowa HR-VPP ST (10m, wskaźnik PPI - bezszumny, gap-filled)
# 7. Wieloletnia agregacja bazy referencyjnej GEE (2018-2025)
s2_bands, profile_10m, baseline_stats = ingest_satellite_data(
    lat=CONFIG['LAT'],
    lon=CONFIG['LON'],
    target_date=CONFIG['TARGET_DATE'],
    buffer_m=CONFIG['BUFFER_M'],
    baseline_years=CONFIG['BASELINE_YEARS'],
    geojson_path=CONFIG['GEOJSON_PATH'],
    download_historical_series=CONFIG['DOWNLOAD_HISTORICAL']
)

print('✅ Pomyślnie pobrano dane wejściowe!')
print(f' - Pasm S2: {list(s2_bands.keys())}')
print(f' - Maska HRL M_crop: {s2_bands[\"crop_mask\"].shape}')
print(f' - Regionalny SWI T=5: {s2_bands[\"swi_1km\"].shape}')
print(f' - Fenologia HR-VPP PPI: {s2_bands[\"ppi_10m\"].shape}')
print(f' - Profil CRS: {profile_10m[\"crs\"]}')
""")

add_md("## 🌡️ MODUŁ 2: Korejestracja AROSICS i Downscaling Termiczny pyDMS (`step_02_align_and_scale.py`)")

add_code("""from step_02_align_and_scale import align_and_scale_lst
import matplotlib.pyplot as plt

# Wykonanie subpikselowej korejestracji, korekty adiabatycznej i deagregacji termicznej 1 km -> 10 m
lst_10m = align_and_scale_lst(
    s2_bands=s2_bands,
    s3_lst_raw=s2_bands['s3_lst_raw'],
    dem=s2_bands['dem'],
    profile_10m=profile_10m
)

# Wizualizacja wyników deagregacji termicznej
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
im0 = axes[0].imshow(s2_bands['s3_lst_raw'], cmap='inferno')
axes[0].set_title('Surowe LST Coarse (1 km)')
plt.colorbar(im0, ax=axes[0], label='Temperatura [°C]')

im1 = axes[1].imshow(lst_10m, cmap='inferno')
axes[1].set_title('Zaostrzone LST pyDMS (10 m)')
plt.colorbar(im1, ax=axes[1], label='Temperatura [°C]')
plt.tight_layout()
plt.show()
""")

add_md("## 🔍 MODUŁ 3: Super-Rozdzielczość SEN2SR i Fuzja ATPRK do Siatki 2.5 m (`step_03_super_resolve.py`)")

add_code("""from step_03_super_resolve import super_resolve_bands

# Podniesienie rozdzielczości pasm RGBN do 2.5 m (SEN2SR) oraz kanałów 20m i LST (ATPRK)
bands_25m, profile_25m = super_resolve_bands(
    s2_bands=s2_bands,
    lst_10m=lst_10m,
    profile_10m=profile_10m
)

print('✅ Fuzja ATPRK zakończona!')
print(f' - Nowa siatka afiniczna: piksel {profile_25m[\"transform\"].a} m')
print(f' - Rozmiar siatki 2.5m: {bands_25m[\"B04\"].shape}')
""")

add_md("## 📊 MODUŁ 4: Wskaźniki Biofizyczne, TVDI, Alerty Z-score i Protokół Walda (`step_04_metrics_alert.py`)")

add_code("""from step_04_metrics_alert import compute_metrics_and_alerts

# Obliczenie OSAVI, TCARI, TCARI/OSAVI, TVDI, Z-score anomalii oraz walidacja Walda
products, wald_metrics = compute_metrics_and_alerts(
    bands_25m=bands_25m,
    lst_10m=lst_10m,
    baseline_stats=baseline_stats,
    profile_25m=profile_25m
)

print('✅ Metryki Protokołu Walda:')
for k, v in wald_metrics.items():
    print(f'  - {k.upper()}: {v:.4f}')

# Wizualizacja wskaźników i macierzy alertów
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
im0 = axes[0].imshow(products['tcari_osavi_25m'], cmap='RdYlGn_r', vmin=-0.5, vmax=1.5)
axes[0].set_title('TCARI / OSAVI (2.5 m)')
plt.colorbar(im0, ax=axes[0], label='Wskaźnik chlorozy')

im1 = axes[1].imshow(products['tvdi_10m'], cmap='YlOrRd', vmin=0, vmax=1)
axes[1].set_title('TVDI (10 m) - Stres Wodny')
plt.colorbar(im1, ax=axes[1], label='Indeks TVDI [0-1]')

cmap_alert = plt.matplotlib.colors.ListedColormap(['#2ecc71', '#f1c40f', '#e74c3c'])
im2 = axes[2].imshow(products['alert_mask_25m'], cmap=cmap_alert, vmin=0, vmax=2)
axes[2].set_title('Macierz Alertów (2.5 m): 0=Norma, 1=Żółty, 2=Czerwony')
plt.colorbar(im2, ax=axes[2], ticks=[0, 1, 2])
plt.tight_layout()
plt.show()
""")

add_md("## 🚀 MODUŁ 5: Master Orchestrator i Eksport Cloud-Optimized GeoTIFF (`step_05_colab_run.py`)")

add_code("""from step_05_colab_run import run_pipeline

# Pełne automatyczne uruchomienie potoku i eksport COG GeoTIFF wraz z raportem Markdown
run_pipeline(CONFIG)

# Wyświetlenie wygenerowanego raportu
with open('data/05_Final_Outputs/validation_report.md', 'r', encoding='utf-8') as f:
    print(f.read())
""")

with open('notebooks/AgriScreen_Colab_Pipeline.ipynb', 'w', encoding='utf-8') as out:
    json.dump(nb, out, indent=2, ensure_ascii=False)

print('Notebook successfully generated at: notebooks/AgriScreen_Colab_Pipeline.ipynb')
