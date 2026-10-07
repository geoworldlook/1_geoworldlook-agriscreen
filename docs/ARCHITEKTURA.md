# AgriWatch — architektura (stan kodu)

> Opis tego, co jest zaimplementowane w `step_01…07` (commit „vineyard drought-anomaly monitor (EDO CDI logic)” i późniejsze poprawki SR).
> Nie jest to plan ani zapis decyzji — plany są w `docs/plans/` (patrz „Dokumenty” na końcu).

## 1. Przepływ

```text
GitHub (kod) ──git pull──▶ Dysk Google: MyDrive/GeoWorldLook/agriwatch ◀──── Colab (GPU, GEE)
                                     │
notebooks/AgriWatch_Monitor.ipynb ──▶ step_05.setup_runtime ──▶ run_task(...) dla każdego zadania
                                                                   │
   ingest_s2 ─▶ ingest_era5 ─▶ scene_stats ─▶ anomalies ─▶ validate ─▶ bulletin
   (step_01)    (step_01)      (step_03/04)   (step_04)    (step_07)   (step_04)
                                                                   │
                                     data/registry/gwl_*.csv  +  data/05_Final_Outputs/agriwatch/
```

Każde zadanie jest wywoływane przez `run_task`, który zapisuje wiersz w `gwl_runs` (czas, status, commit gita
z flagą `+dirty`, parametry, liczba nowych wierszy). Błąd zadania jest zapisywany i nie zatrzymuje kolejnych.

## 2. Moduły

| Moduł | Odpowiedzialność | Główne funkcje |
|---|---|---|
| `step_01_ingest.py` | Pobieranie z Google Earth Engine | `initialize_earth_engine`, `load_aoi_geometry`, `add_cloud_and_shadow_mask`, `sync_sentinel2_time_series` (10 pasm L2A [0–1] + `cloudmask` + SCL, manifest `data/00_Metadata/ingest_manifest.json`, filtr miesięcy), `sync_era5_land_point` (ERA5-Land DAILY_AGGR w punkcie, cache CSV w fragmentach 12-miesięcznych, ponowne pobieranie ostatnich 120 dni), `read_geotiff_to_numpy`, `write_geotiff` |
| `step_03_super_resolve.py` | SEN2SRLite „main” 10 m → 2,5 m | `load_sen2sr`, `super_resolve` (dopełnienie do kwadratu ≥ 128 px — obejście błędów `predict_large` w sen2sr 0.8.5), `sr_checks` (H-SR0, H-SR1), `plot_sr_comparison` |
| `step_04_metrics_alert.py` | Indeksy, anomalie, status, biuletyn | `compute_indices` (NDVI, NDMI, NDRE), `site_stats`, `clim_anomaly`, `spi`, `era5_anomalies`, `scene_anomaly`, `build_status`, `build_bulletin` |
| `step_05_colab_run.py` | Sterowanie i rejestr | `setup_runtime`, `run_task`, `registry_read/upsert`, `MONITOR_CONFIG`, `monitor_config`, zadania `task_*`, `run_monitoring`, `--selftest` |
| `step_07_station_pipeline.py` | Stacja ISMN (samodzielny potok) i walidacja anomalii | `qc_insitu`, `extract_satellite` (S-1, S-2, ERA5 z cache), `s1_change_detection`, `evaluate` (metryki z CI z bootstrapu blokowego), `run_station_pipeline`, `validate_anomalies` |
| `build_colab_master.py` | Generator `notebooks/AgriWatch_Monitor.ipynb` | `create_monitor_notebook` |

Zależności między modułami: `step_05` importuje `step_01/03/04/07` leniwie (wewnątrz zadań);
`step_07` używa z `step_01` tylko GEE, maski chmur i ERA5, a z `step_04` funkcji `clim_anomaly` i `rootzone`.

## 3. Zadania monitoringu (`step_05`)

| Zadanie | Wejście | Wyjście |
|---|---|---|
| `task_ingest_s2` | AOI + bufor 320 m, sezon IV–X, ≤ 40% chmur nad AOI | `data/01_Raw_Sentinel2/S2_L2A_*.tif` |
| `task_ingest_era5` | centroid winnicy, 1991 → dziś | `data/02_ERA5_Land/era5_land_daily.csv` |
| `task_scene_stats` | nowe sceny (brak w `gwl_observations`), od najnowszej | statystyki obiektów 10 m i 2,5 m (tylko indeksy, których pasma przeszły H-SR0/H-SR1); QC SR jako `product = SR_QC` z wersją kontroli w `calib_id`; limit `SR_MAX_SCENES_PER_RUN` na uruchomienie; pokrycie SR w komunikacie (`sr_coverage`); zapis co 25 scen (wznawianie po przerwanej sesji) |
| `task_anomalies` | ERA5, obserwacje roślinności | `gwl_anomalies`, `gwl_status`, CSV w `OUTPUT_DIR` |
| `task_validate` | anomalie i status | `gwl_validation_metrics` (R anomalii vs ISMN 5/20/30 cm, POD/FAR) |
| `task_bulletin` | status, anomalie, walidacja | `bulletin.md`, wykresy PNG, `agriwatch_latest.json` |

## 4. Metoda

- **Anomalie ERA5-Land** (`clim_anomaly`): z-score i percentyl względem klimatologii dnia roku 1991–2020 (okno ±15 dni).
  Wilgotność strefy korzeni = średnia warstw 0–7, 7–28, 28–100 cm ważona grubością.
- **SPI-1, SPI-3** (`spi`): sumy 30 i 90 dni, rozkład gamma dopasowany dla pory roku, z prawdopodobieństwem zera.
- **Anomalie roślinności** (`scene_anomaly`): dla sceny z roku Y odniesieniem są sceny z innych lat (±15 dni roku),
  min. 5 scen odniesienia, tylko sceny z ≥ 90% czystych pikseli.
- **Status** (`build_status`): na koniec każdej dekady; roślinność tylko w IV–X i nie starsza niż 30 dni;
  `confidence` = high / medium / low zależnie od dostępności i wieku sceny.
- **Rozdzielczość detekcji: SR 2,5 m** (`VEG_PRODUCT = "S2SR_2.5m"`, decyzja 2026-10-07). Każda scena wchodząca do
  detekcji jest po SEN2SR; scena, która nie przeszła kontroli pasm 10 m, nie wchodzi do detekcji (bez zastępstwa 10 m).
  NDVI 10 m jest liczony dalej jako odniesienie: walidacja `anomaly_clim_paired` porównuje oba produkty na tych samych dniach.
  Klimatologia anomalii 2,5 m jest pełna dopiero po przetworzeniu SR wszystkich scen; do tego czasu biuletyn podaje pokrycie SR.
- **Kontrola SR:** H-SR0 — `std(SR − bikubika) / std(SR) ≥ 0,02` (model faktycznie działał);
  H-SR1 — RMSE(SR uśredniony do natywnej rozdzielczości pasma, wejście) w reflektancji (spójność radiometryczna):
  pasma 10 m (B02, B03, B04, B08) w blokach 4×4, próg stały 0,01; pasma 20 m (B05–B07, B8A, B11, B12) w blokach 8×8
  względem pikseli 20 m (przesunięcie siatki wykrywane z powielonych pikseli), próg = specyfikacja dokładności L2A
  `SR_20M_SPEC_FACTOR · (0,05·ρ + 0,005)` (Vermote 2008), ρ = średnia reflektancja pasma w scenie.
  **Decyzja per wskaźnik** (`step_03.INDEX_BANDS`): NDVI (B04, B08), NDMI (B8A, B11), NDRE (B8A, B05) z 2,5 m tylko,
  gdy przeszły wszystkie ich pasma. Szacowany błąd wskaźnika z SR (`{idx}_sr_err`) zapisywany w `SR_QC` dla każdej sceny.
  Brak modelu = błąd zgłoszony, bez zastępstwa interpolacją. Wersja kontroli: `SR_QC_VERSION = "qc3"`.
- **Ryzyko przyjęte świadomie (2026-10-07):** pasma 20 m po SR mają błąd spójności 4–9% reflektancji (B8A ~0,019,
  B11 ~0,015, B05 ~0,008 na scenach z 2019), czyli 10–20 razy więcej niż pasma 10 m. Próg L2A dopuszcza błąd równy
  niepewności samych danych wejściowych. Skutek: NDMI i NDRE z 2,5 m mają błąd ~0,03–0,04 na piksel (propagacja z RMSE
  pasm), porównywalny z typową zmiennością międzyroczną. Średnia działki zmniejsza tylko losową część błędu.
  NDMI/NDRE z 2,5 m są na karcie i w walidacji (segment `anomaly_clim_paired`), **nie** w logice statusu, dopóki test
  paired nie pokaże, że nie są gorsze od 10/20 m. B12 nie spełnia specyfikacji, więc wskaźniki z B12 (NMDI, CRSWIR)
  liczymy z pasm natywnych.

## 5. Rejestr `gwl_*` (Dysk Google, `data/registry/`)

Pliki CSV o nazwach i kolumnach przyszłej bazy danych. `registry_upsert` dopisuje wiersze według klucza głównego:
nowy klucz → dopisany, zmieniona wartość → zastąpiony, bez zmian → zostaje stary wiersz. Zapis atomowy.

| Tabela | Klucz |
|---|---|
| `gwl_sites` | `site_id` |
| `gwl_observations` | `site_id, product, variable, time_utc, orbit` |
| `gwl_anomalies` | `site_id, product, date` |
| `gwl_validation_metrics` | `site_id, product, reference, segment, period, subset, metric` |
| `gwl_calibrations` | `calib_id, site_id, product, orbit, param` |
| `gwl_status` | `site_id, date` |
| `gwl_runs` | `run_id` |

Pełny schemat: `REGISTRY_SCHEMA` w `step_05_colab_run.py`.

## 6. Konfiguracja

Jedno miejsce: `MONITOR_CONFIG` w `step_05_colab_run.py` (ścieżki względne liczone od `PROJECT_DIR`).
Kolejna winnica = nowy wpis w `VINEYARDS` (`{"site_id": fid}` z `data/1_AOI_GBOV_CONDOM.geojson`).
Konfiguracja stacji: `STATION_CONFIG` w `step_07_station_pipeline.py`.

## 7. Dokumenty

| Dokument | Status |
|---|---|
| `docs/plans/Plan_v3_monitoring_winnic_SR.md` | `APPROVED` (2026-10-06); część A = przegląd literatury, z którego korzysta kod (EDO CDI, walidacja anomalii, SR) |
| `docs/plans/Plan_v6_platforma_anomalii_wilgotnosci.md` | `PROPOSED` (2026-10-07) — platforma na wzór WineEO dla 15 winnic; przegląd literatury i propozycje Z1–Z8 w `docs/evidence/F3_przeglad_literatury_platforma.md` |
| `docs/plans/Plan_v5_bilans_wodny_winnic.md` | `PROPOSED` (bilans wodny FAO-56) — niezatwierdzony, nie jest zaimplementowany |
| `docs/plans/Plan_v4_cel_zawodowy.md` | `SUPERSEDED` |
| `docs/plans/F0…`, `F1…`, `Plan_wdrozenia_pipeline.md`, `Plan_GeoWorldLook_Jupyter_Colab.md`, `Plan_6_tygodni.md` | historyczne; odwołują się do plików `step_02`, `step_06`, które są teraz w `legacy/` |
| `docs/evidence/F1_evidence_brief.md`, `docs/evidence/Condom_QC.md` | analizy źródłowe (QC stacji Condom wdrożone w `step_07.qc_insitu`) |

## 8. `legacy/`

Poprzedni potok AgriScreen v2.5 (LST z H-pyDMS, ATPRK, TCARI/OSAVI, TVDI, walidacja Landsat) i poprzednie wersje modułów
(`*_v1.py`). Nie jest uruchamiany i nie jest utrzymywany; zostaje jako archiwum.
