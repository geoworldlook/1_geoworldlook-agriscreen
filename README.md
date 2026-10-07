# AgriWatch — monitoring suszy dla winnicy (Condom, Gers)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/geoworldlook/1_geoworldlook-agriscreen/blob/main/notebooks/AgriWatch_Monitor.ipynb)

Monitoring anomalii suszy dla jednej winnicy (`VINEYARD_06`, 2,9 ha, 136 m od stacji ISMN SMOSMANIA Condom)
z otwartych danych: ERA5-Land i Sentinel-2 po super-resolution SEN2SR do 2,5 m (rozdzielczość detekcji).
Status dekadowy wzorowany na Combined Drought Indicator (CDI) Europejskiego Obserwatorium Suszy (EDO):

| Status | Warunek | Akcja |
|---|---|---|
| `watch` | SPI-1 ≤ −2 lub SPI-3 ≤ −1 (deficyt opadu) | watch |
| `warning` | anomalia wilgotności strefy korzeni (ERA5-Land 0–100 cm) ≤ −1 | watch |
| `alert` | `warning` oraz anomalia NDVI winnicy ≤ −1 | inspect |
| `recovery` | po `warning`/`alert` spadek poniżej progów, anomalie nadal ujemne | normal |

Błąd anomalii jest walidowany na profilu glebowym stacji ISMN Condom (5–30 cm).

**Architektura:** kod na GitHub → obliczenia w Google Colab (GPU, Google Earth Engine) → Dysk Google jako baza danych
(`MyDrive/GeoWorldLook/agriwatch`, tabele CSV `data/registry/gwl_*`). Szczegóły: [`docs/ARCHITEKTURA.md`](docs/ARCHITEKTURA.md).

## Struktura repozytorium

```text
├── step_01_ingest.py            # GEE: Sentinel-2 L2A (przyrostowo, manifest) + maska chmur, ERA5-Land w punkcie, GeoTIFF I/O
├── step_03_super_resolve.py     # SEN2SRLite 10 m -> 2,5 m z kontrolą H-SR0/H-SR1 (bez zastępstwa interpolacją)
├── step_04_metrics_alert.py     # indeksy obiektów, anomalie klimatologiczne, SPI, status dekadowy, biuletyn
├── step_05_colab_run.py         # sterowanie z notatnika: setup_runtime, run_task, rejestr gwl_*, zadania monitoringu
├── step_06_dashboard.py         # dashboard winnicy (wzór: panel Wago, ESA WineEO): mapa NDVI, status, ryzyko, pogoda
├── step_07_station_pipeline.py  # stacja ISMN Condom: QC in situ, S-1 change detection, walidacja z CI
├── build_colab_master.py        # generator notatnika
├── notebooks/AgriWatch_Monitor.ipynb
├── data/
│   ├── 1_AOI_GBOV_CONDOM.geojson         # działki (winnice, sady, poligon stacji)
│   ├── 1_AOI_GBOV_CONDOM_ZASIEG.geojson  # zasięg pobierania
│   └── 7_isismn_data/                    # pomiary ISMN SMOSMANIA 2016–2024
├── docs/                        # architektura, plany, analizy (evidence)
└── legacy/                      # poprzednia wersja (AgriScreen v2.5): LST, ATPRK, TCARI/OSAVI, TVDI — nieużywana
```

Numeracja kroków nie jest ciągła: kroki 2 i 6 z v2.5 są w `legacy/`.

## Uruchomienie

1. Otwórz `notebooks/AgriWatch_Monitor.ipynb` w Colab (Plik → Otwórz → GitHub), środowisko z GPU.
2. `Uruchom wszystko`. Notatnik montuje Dysk, klonuje lub aktualizuje repozytorium w `MyDrive/GeoWorldLook/agriwatch`,
   instaluje pakiety, inicjalizuje GEE (projekt `ee-geoworldlook`) i wykonuje zadania:
   `ingest_s2 → ingest_era5 → scene_stats → anomalies → validate → bulletin → dashboard`.
3. Wyniki: `data/05_Final_Outputs/agriwatch/` (**`dashboard.html`**, biuletyn, wykresy, `agriwatch_latest.json`)
   i tabele `data/registry/gwl_*.csv`. Dashboard wyświetla się w notatniku (sekcja 6).

## Zakres wersji 1.0 (zamrożony 2026-10-07)

Jedna winnica (`VINEYARD_06`), status EDO z SPI, wilgotności gleby ERA5-Land i NDVI 2,5 m, dashboard w Colab.
Do wydania zmieniamy tylko błędy, nie metodę. NDMI, NDRE i CRSWIR liczą się w tle do walidacji.
Propozycje rozwoju (Z1–Z15, 15 winnic, strona WWW, powiadomienia) czekają na wersję 1.1:
`docs/plans/Plan_v6_platforma_anomalii_wilgotnosci.md`, `docs/evidence/F3_przeglad_literatury_platforma.md`.

Testy offline (bez GEE i GPU; prawdziwe dane ISMN i działki, syntetyczne dane satelitarne):

```bash
python step_05_colab_run.py --selftest
python step_07_station_pipeline.py --selftest
```

## Zależności

`earthengine-api geemap geedim rasterio geopandas numpy pandas scipy matplotlib pytesmo ismn`;
dla super-resolution dodatkowo `sen2sr mlstac torch` (wymagane do detekcji; środowisko Colab z GPU —
na CPU około 1 min na scenę). Bez SR status liczy się bez warstwy roślinności.
