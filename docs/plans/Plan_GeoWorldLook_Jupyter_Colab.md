# GeoWorldLook — sterowanie z notatnika lokalnego, obliczenia w Colab: plan

> **Status:** `PROPOSED` (2026-09-29) — do zatwierdzenia (decyzje D-016…D-019, sekcja 8)
> **Cel:** moduły sterowane z notatnika Jupyter w VS Code (lokalnie, w repozytorium), liczone w Google Colab (GPU/GEE), z wynikami publikowanymi w GeoWorldLook (Supabase + strona na Vercel).
> **Zakres:** warstwa operacyjna. Nauka (metody, walidacja) — bez zmian względem `Plan_wdrozenia_pipeline.md`.

---

## 1. Co już jest (stan na 2026-09-29)

| Element | Stan |
|---|---|
| Moduły `step_01…06` | Działają w notatniku Colab w przeglądarce; kod klonowany **na Dysk** (git na Dysku — wolny i ryzykowny) |
| `step_07_station_pipeline.py` | Działa offline (selftest); przyjmuje konfigurację słownikiem, cache, manifest — **wzorzec dla pozostałych modułów** |
| Notatnik | Jeden, generowany (`build_colab_master.py`), w przeglądarce |
| VS Code 1.139 | Zainstalowany lokalnie; brak lokalnego Jupytera — VS Code ma go wbudowanego przez rozszerzenie |
| Poprzedni moduł VOWA-20m (`1_geoworldlook-vowa20m.zip`) | Orkiestrator etapów z manifestami, **rejestr CSV na Dysku o kolumnach przyszłych tabel Supabase** (`validation_summary`, `zones`), walidacja wielopoziomowa (SWI → ISMN → zdarzenia suszy EDO) |
| GeoWorldLook (strona) | Vercel + Supabase — **repozytorium i schemat bazy nieznane w tej sesji** |

---

## 2. Architektura docelowa

```text
 LOKALNIE (VS Code)                     GITHUB              GOOGLE COLAB (runtime)                 DYSK GOOGLE                         GEOWORLDLOOK
 ─────────────────────                  ──────              ───────────────────────                ───────────                         ────────────
 repo 2_geoworldlook                    main  ──pull──►     /content/code  (kod, efemeryczny)
  ├─ step_0x.py  (edycja, selftest) ──push──►                  │  import step_0x
  └─ notebooks/GWL_Control.ipynb ════ kernel Colab ══════►     │  run_task(...)  ──── zapis ────►  1_geoworldlook-agriscreen/data/
       (sterowanie, podgląd wyników                            │  GEE / CDSE / SEN2SR (T4)          ├─ cache, surowe dane, COG
        inline: wykresy, raporty)                              │                                    ├─ 08_Station_Validation/…
                                                               └─ publish() ──────────────────────► └─ registry/  (tabele CSV)  ──►  Supabase (tabele gwl_*)
                                                                                                                                      └─► strona Vercel
 Dysk Google for desktop (G:\) ◄─────────────── synchronizacja ───────────────────────────── (podgląd w QGIS, analiza przez Claude)
```

### Zasady

1. **Kod w git, dane na Dysku, wyniki w rejestrze.** Runtime Colab klonuje kod do `/content/code` (szybko, bez gita na Dysku). Na Dysku są tylko dane, cache i wyniki.
2. **Notatnik steruje, moduły liczą.** Komórka notatnika to kilka linii: ustaw → uruchom → pokaż. Zero logiki naukowej w notatniku.
3. **Każde uruchomienie zostawia ślad:** `run_id`, commit gita, hash konfiguracji, czas, status, ścieżki wyników — w manifeście i w rejestrze `runs`.
4. **Jeden kontrakt danych dla wszystkich modułów GeoWorldLook** (AgriWatch i VOWA-20m): tabele rejestru mają dokładnie kolumny tabel Supabase (wzorzec z VOWA `stage9_rejestr_drive.py`).
5. **Ten sam notatnik działa na trzech środowiskach:** Colab przez VS Code (główne), Colab w przeglądarce (zapas), lokalny kernel (lekkie zadania i testy).

---

## 3. Zmiany w kodzie — minimalne

| Plik | Zmiana | Po co |
|---|---|---|
| `step_05_colab_run.py` | **+ `setup_runtime(data_dir=None)`**: wykrywa środowisko (Colab web / Colab przez VS Code / lokalne), sprawdza montowanie Dysku, ustawia `CODE_DIR` i `DATA_DIR`, inicjalizuje GEE (konto serwisowe z Dysku lub `auth_mode="notebook"`), wczytuje klucze z `.env` na Dysku. **+ `sync_code()`**: `git pull` na runtime + przeładowanie modułów. **+ `run_task(name, overrides)`**: rejestr zadań, manifest, wpis do `registry/runs.csv`, adapter wyników do tabel rejestru. **+ `show_result(res)`**, **`run_history()`** | Jedno API sterowania dla wszystkich modułów; `run_pipeline` zostaje bez zmian |
| `step_07_station_pipeline.py` | Rozdzielenie `DATA_DIR` (Dysk) od katalogu kodu; maska chmur S-2: **Cloud Score+** (`GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`, jak w VOWA) zamiast s2cloudless + projekcji cieni — lżejsze obliczeniowo w GEE i mniej ryzyka przekroczenia czasu | Działa tak samo lokalnie i w Colab |
| **`step_08_publish.py` (nowy)** | Publikacja tabel rejestru do Supabase (upsert po kluczach) i wykresów do Supabase Storage; tryb `dry_run` (pokazuje, co zostanie wysłane) | Wyniki trafiają na stronę GeoWorldLook |
| **`notebooks/GWL_Control.ipynb` (nowy, ręcznie utrzymywany)** | Panel sterowania: 0 — bootstrap; 1 — stacja Condom; 2 — mapy SR (M2); 3 — publikacja; 4 — historia uruchomień | Jeden notatnik do codziennej pracy |
| **`requirements-colab.txt` (nowy)** | Wersje pakietów instalowanych na runtime | Powtarzalne środowisko |
| `build_colab_master.py` | Bez zmian — notatnik przeglądarkowy jako zapas | — |
| `step_06_station_api.py` | Status **legacy** (walidacja przeniesiona do `step_07`); plik zostaje, notatnik sterujący go nie używa | Koniec podwójnej, błędnej walidacji (K-13, K-15) |
| `step_01…04` | Bez zmian w tym planie; naprawy naukowe wg `Plan_wdrozenia_pipeline.md` (M2); podpięte do `run_task` przez istniejące funkcje | — |

### Kontrakt modułu (warunek podpięcia do `run_task`)

Każdy moduł, który podpinamy, musi:
1. przyjmować konfigurację jako słownik z wartościami domyślnymi w module;
2. nie mieć efektów ubocznych przy imporcie (brak `logging.basicConfig`, `warnings.filterwarnings` na poziomie modułu);
3. rozróżniać `CODE_DIR` i `DATA_DIR`;
4. być idempotentny (cache, ponowne uruchomienie nie duplikuje pracy);
5. zwracać słownik wyników i zapisywać `run_manifest.json`;
6. mieć test offline (`--selftest`).

| Moduł | Zgodność dziś |
|---|---|
| `step_07` | 1, 4, 5, 6 ✔; 3 — do zrobienia; 2 ✔ |
| `step_01` | 4 ✔; 1, 5 częściowo; 2 ✘ (basicConfig, warnings); 3 ✘ |
| `step_02…04` | 2 ✘; 3 ✘; 6 częściowo — naprawy w M2 |
| `step_06` | legacy |

---

## 4. Kontrakt danych GeoWorldLook v1 (tabele rejestru = tabele Supabase)

Na Dysku jako CSV w `data/registry/` (edytowalne, czytelne w Excelu/QGIS); w Supabase jako tabele z prefiksem `gwl_`.

| Tabela | Klucz | Kolumny | Źródło w AgriWatch |
|---|---|---|---|
| `gwl_sites` | `site_id` | `module, name, site_type (station/aoi/parcel), lat, lon, geom_wkt, land_cover, source, created_at` | stacja Condom, 22 działki |
| `gwl_observations` | `site_id, time, product, variable` | `value, unit, qc_flags, run_id` | in situ (dobowe), S-1 SM, ERA5-Land |
| `gwl_validation_metrics` | `site_id, product, reference, segment, period, subset, metric` | `value, ci_low, ci_high, n, run_id, computed_at` | `metrics.csv` ze `step_07` |
| `gwl_zones` | `id` | kolumny VOWA: `aoi_id, crop_type, geom_wkt, current_status, confidence, last_updated` + `module, anomaly_value` | status działek (M4) |
| `gwl_runs` | `run_id` | `module, task, git_commit, config_hash, runtime, started_at, finished_at, status, message, outputs_uri` | każdy `run_task` |
| `gwl_artifacts` | `run_id, kind` | `path, public_url` | wykresy, raporty, COG |

Format długi (`metric`, `value`) pozwala obu modułom (VOWA-20m i AgriWatch) pisać do tych samych tabel bez zmiany schematu. Strona czyta tylko te tabele.

---

## 5. Notatnik sterujący — szkic

```python
# [0] Bootstrap (Colab przez VS Code lub przeglądarkę). Wcześniej: VS Code → "Colab: Mount Google Drive to Server..."
import os, sys, subprocess
REPO, CODE = "https://github.com/geoworldlook/1_geoworldlook-agriscreen.git", "/content/code"
if not os.path.exists(CODE):
    subprocess.run(["git", "clone", "--depth", "1", REPO, CODE], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", f"{CODE}/requirements-colab.txt"], check=True)
sys.path.insert(0, CODE)
from step_05_colab_run import setup_runtime, sync_code, run_task, show_result, run_history
rt = setup_runtime(data_dir="/content/drive/MyDrive/1_geoworldlook-agriscreen/data")

# [1] Stacja Condom
res = run_task("station", {"STATION": "Condom"})
show_result(res)            # wykres + raport inline w VS Code

# [2] Po zmianie kodu lokalnie (commit + push):
sync_code()                 # git pull na runtime + przeładowanie modułów

# [3] Publikacja do GeoWorldLook
from step_08_publish import publish
publish(rt, dry_run=True)   # podgląd
publish(rt)                 # wysłanie

# [4] Historia
run_history().tail(10)
```

### Codzienny cykl pracy

1. Edycja modułu w VS Code → `python step_07_station_pipeline.py --selftest` (lokalnie, sekundy).
2. `git commit` + `git push`.
3. W `GWL_Control.ipynb` (kernel Colab): `sync_code()` → `run_task(...)` → wynik inline.
4. `publish()` → strona GeoWorldLook pokazuje nowe wyniki.
5. Wyniki na Dysku widoczne lokalnie (Dysk Google for desktop) — QGIS i analiza przez Claude.

Szybkie eksperymenty bez commita: w VS Code „Upload to Colab” na zmienionym pliku, potem `sync_code(pull=False)`. Uruchomienia bez commita są oznaczane w `gwl_runs` jako `dirty`.

---

## 6. Etapy wdrożenia (10 h/tydzień)

| Etap | Termin | Zakres | Wynik do pokazania |
|---|---|---|---|
| **A — Sterowanie** | 30 IX → 6 X | Rozszerzenia VS Code (Jupyter, Colab); `requirements-colab.txt`; `setup_runtime`, `sync_code`, `run_task`, `show_result` w `step_05`; `DATA_DIR` w `step_07`; `GWL_Control.ipynb`; **pierwsze prawdziwe uruchomienie stacji Condom w Colab** | Raport i wykres Condom na prawdziwych danych S-1 |
| **B — Rejestr** | 7 → 13 X | Tabele `data/registry/*.csv` wg sekcji 4; adapter `station` w `run_task`; `run_history()`; Dysk Google for desktop lokalnie | Historia uruchomień i wyniki w tabelach gotowych do bazy |
| **C — Publikacja** | 14 → 27 X | Schemat Supabase (SQL w repo), `step_08_publish.py`, polityki RLS (odczyt publiczny tylko tabel demo); strona „AgriWatch Evidence — Condom” w repozytorium GeoWorldLook: wykres, tabela metryk z CI, mapa działek | **Wyniki Condom na stronie GeoWorldLook** |
| **D — Automatyzacja (opcja)** | XI | Konto serwisowe GEE; cotygodniowa aktualizacja stacji w GitHub Actions (zadanie CPU, bez Colab); mapy SR (GPU) nadal ręcznie w Colab | Strona aktualizuje się sama |

Etap A pokrywa się z M1 z `Plan_wdrozenia_pipeline.md`; etapy B–C to przygotowanie publikacji dla M2–M4.

---

## 7. Ograniczenia i ryzyka

| Ryzyko | Działanie |
|---|---|
| Darmowy Colab: brak pracy w tle, rozłączenie po ~90 min bezczynności, maks. 12 h, GPU niegwarantowane | Zadania przyrostowe z cache (przerwane wznawia się); automatyzacja zadań CPU poza Colab (etap D) |
| Rozszerzenie Colab dla VS Code: część funkcji eksperymentalna; nie ma przezroczystego dostępu do plików lokalnych | Kod przez git; dane przez Dysk; notatnik przeglądarkowy jako zapas |
| Logowanie do GEE na runtime przez VS Code (inne niż w przeglądarce) | `auth_mode="notebook"`; docelowo konto serwisowe GEE (klucz na Dysku, nigdy w repo) |
| Sekrety (CDSE, Supabase) w VS Code — brak potwierdzonej obsługi Colab Secrets | Plik `.env` na Dysku (obsługiwany już przez `step_01`); klucz `service_role` Supabase tylko na runtime, nigdy na stronie |
| Repozytorium w folderze **OneDrive pracodawcy** (`OneDrive - opegieka.pl`) | Przenieść repo do katalogu prywatnego przed publikacją i sprzedażą (zgodnie z zasadą NDA z planu i ryzykiem R-002) |
| GEE i Colab tylko do użytku niekomercyjnego | Strona demo/portfolio — w porządku; sprzedaż → ingestia z CDSE (plan v2, F2) |
| Nieznany schemat bazy i repozytorium strony GeoWorldLook | Potrzebny dostęp (sekcja 9) przed etapem C |
| Darmowy Supabase: limity bazy i plików `[VERIFY]` | Tylko wyniki zagregowane i wykresy; rastry COG na Dysku/R2 |

---

## 8. Decyzje do zatwierdzenia

| ID | Decyzja |
|---|---|
| D-016 | Sterowanie z notatnika w VS Code z kernelem Colab (oficjalne rozszerzenie); notatnik przeglądarkowy jako zapas |
| D-017 | Kod w git, klonowany na runtime do `/content/code`; Dysk tylko na dane, cache i wyniki |
| D-018 | Kontrakt danych GeoWorldLook v1 (sekcja 4) wspólny dla AgriWatch i VOWA-20m; publikacja przez `step_08_publish.py` |
| D-019 | `step_06_station_api.py` → legacy; walidacja stacyjna tylko w `step_07` |

---

## 9. Czego potrzebuję od użytkownika

1. Instalacja w VS Code: rozszerzenia **Jupyter** (Microsoft) i **Google Colab** (Google).
2. Czy repozytorium na GitHubie jest publiczne (klonowanie bez tokena)?
3. Dostęp do repozytorium strony GeoWorldLook i informacja o projekcie Supabase (istniejące tabele) — przed etapem C.
4. Opcjonalnie: Dysk Google for desktop zalogowany lokalnie (podgląd wyników i analiza przez Claude).
