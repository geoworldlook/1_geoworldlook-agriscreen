> **STATUS: `Superseded` (2026-09-26)** — zastąpiony przez `Plan_wdrozenia_pipeline.md`. Użytkownik zdecydował: obecna struktura plików `step_01…06` zostaje; restrukturyzacja do pakietu wycofana.

# F0 — Plan poprawy jakości kodu

> **Status:** `PROPOSED` (2026-09-26) — wymaga `ZATWIERDZAM` przed rozpoczęciem F0.1
> **Etap:** F0 — Stabilizacja i uczciwość kodu (2026-10-01 → 2026-10-31)
> **Budżet:** ~40 h (4 tygodnie × 10 h)
> **Podstawa:** `Plan_pracy/1_Plan_pracy_v2_SR_LST.md`, `Plan_pracy/2_AgriWatch_Evidence_Lab_Master.md` (zadania F0.1–F0.6)
> **Środowisko:** kod na GitHub → klon na Dysku Google → obliczenia w Colab; wszystkie dane odtwarzalne z notatnika

---

## 1. Cel

Po F0 każdy wynik potoku musi spełniać trzy warunki:

1. **Prawdziwy** — pochodzi z danych, które deklaruje (żadnych cichych zastępstw).
2. **Sprawdzalny** — ma testy, metadane pochodzenia i da się go odtworzyć jednym poleceniem.
3. **Czytelny dla rekrutera z FR/IT** — pakiet Python z CI, README po angielsku, jasne ograniczenia.

F0 **nie poprawia metod naukowych** (downscaling, wskaźnik stresu). To robi F1. F0 buduje fundament, na którym uczciwe porównanie metod w F1 jest w ogóle możliwe.

---

## 2. Diagnoza: trzy przyczyny źródłowe

Problemy K-01…K-12 (rejestr: `Plan_pracy/3_AgriWatch Research Notebook.md`, sekcja 5.2) sprowadzają się do trzech przyczyn:

| Przyczyna | Objaw w kodzie (stan `6f41034`) | Problemy |
|---|---|---|
| **A. Brak kontraktu danych z georeferencją** | Moduły wymieniają `Dict[str, np.ndarray]` + osobny `profile`. Rozmiary wyrównywane „na siłę”: 20× `align_raster_shape`, 13× `scipy.ndimage.zoom`. Agregacja 10 m → 1 km robiona interpolacją, nie średnią powierzchniową | K-02, K-04, K-10 |
| **B. Ciche degradacje** | 32× `except Exception` zwykle kończy się podstawieniem wartości; 16× `np.full` ze stałymi; 9× `nan_to_num`; 6× globalne `warnings.filterwarnings("ignore")`. Potok zawsze kończy się „SUKCESEM” | K-03, K-05, K-06, K-07, K-09, K-11 |
| **C. Brak weryfikowalności** | Test integracyjny sprawdza tylko kształty i istnienie plików; brak testów wartości; brak metadanych pochodzenia w GeoTIFF; README niezgodny z kodem | K-01, K-08, K-12 |

### Nowe problemy znalezione przy tym przeglądzie

| ID | Problem | Plik |
|---|---|---|
| K-09 | **SR najpewniej nigdy nie używa SEN2SR.** `mlstac.load("model/SEN2SRLite_RGBN")` wymaga wcześniejszego `mlstac.download(...)`, którego nie ma. Błąd jest łapany i logowany jako `INFO`, a potok przechodzi na bikubikę z wyostrzeniem. Wyniki opisane jako „SEN2SR 2.5 m” to w praktyce interpolacja. Do tego ładowany jest wariant `SEN2SRLite`, a dokumentacja mówi o `NonReference_RGBN_x4` | `step_03_super_resolve.py:106` |
| K-10 | ATPRK i „konserwacja energii” używają interpolacji (`order=1`) zamiast średniej blokowej. Pasma 20 m przychodzą z GEE już na siatce 10 m (`scale=10`), a ATPRK zakłada skalę z wymiarów tablicy | `step_03_super_resolve.py:201` |
| K-11 | AROSICS dopasowuje LST 1 km powiększone do 10 m względem (1 − NDVI) z oknem 64 px i max. przesunięciem 100 m, co przy 1 km jest bez sensu fizycznego. Wynik i tak jest **odrzucany**, gdy LST ma rozdzielczość coarse (zawsze) | `step_02_align_and_scale.py:50, 415` |
| K-12 | Bloki `if __name__ == "__main__"` z `np.random` w modułach produkcyjnych; test integracyjny bez ustalonego ziarna losowania | `step_02…04`, `test_pipeline.py` |

---

## 3. Decyzje do zatwierdzenia przed startem

| ID | Propozycja | Rekomendacja | Uzasadnienie |
|---|---|---|---|
| Q-1 | Kontrakt danych: `rioxarray` (DataArray z CRS, transform, nodata, atrybutami) zamiast `dict` numpy + `profile` | **TAK** | Usuwa przyczynę A; resampling przez `rio.reproject(..., Resampling.average)` daje poprawną agregację; standard branżowy, dobrze wygląda w CV |
| Q-2 | ATPRK (pasma 20 m → 2,5 m, LST → 2,5 m, PPI → 2,5 m) wyłączone z głównego potoku do `experimental/` | **TAK** | Plan v2 (sekcja 3.1): alerty w natywnej rozdzielczości, SR tylko jako podgląd. ATPRK nie służy produktowi, a jest źródłem K-10 |
| Q-3 | AROSICS usunięty z potoku LST | **TAK** | K-11: metoda nieadekwatna dla 1 km, wynik i tak nieużywany |
| Q-4 | Kod, docstringi, logi, README i CHANGELOG po **angielsku**; dokumenty planu zostają po polsku | **TAK** | Droga B (praca FR/IT/UE): rekruter czyta repozytorium. Tłumaczenie przy okazji przenoszenia kodu, bez osobnego etapu |
| Q-5 | Brak GPU albo modelu SR = etap SR **pomijany z jawnym statusem** (`sr_status: skipped_no_model`). Bikubika dostępna tylko przez `superres.method: bicubic` w YAML, z etykietą na wyjściu | **TAK** | Zasada v2: zero cichych zastępstw |

Q-1…Q-5 nie zmieniają dokumentów nr 1 i nr 2. Są decyzjami wykonawczymi w ramach F0 i trafią do rejestru jako D-008…D-012.

---

## 4. Docelowa struktura repozytorium

```text
1_geoworldlook-agriscreen/
├── pyproject.toml                 # pakiet agriwatch; extras: [gee], [sr], [validation], [dev]
├── README.md                      # EN, zgodny z kodem
├── CHANGELOG.md
├── configs/
│   ├── condom.yaml                # site, daty, źródła, progi, parametry metod
│   └── profiles/
│       ├── colab.yaml             # data_dir=/content/drive/MyDrive/…, cache_dir=/content/cache
│       └── local.yaml             # data_dir=./data
├── src/agriwatch/
│   ├── config.py                  # pydantic: walidacja YAML, hash konfiguracji
│   ├── grid.py                    # siatki UTM, aggregate(average), refine, reproject (rioxarray)
│   ├── provenance.py              # tagi GeoTIFF + run_manifest.json (git sha, config hash, źródła)
│   ├── qa.py                      # reason_codes, flagi jakości, typy wyników
│   ├── io/
│   │   ├── gee.py                 # R&D: S-2, DEM, baseline (≡ step_01)
│   │   ├── cdse.py                # SWI, HR-VPP (≡ step_01); w F1: S-3 SLSTR
│   │   ├── ismn.py                # odczyt ISMN (≡ step_06)
│   │   └── storage.py             # ścieżki Dysk/lokalne, kopia do cache, zapis COG
│   ├── thermal/downscale.py       # DMS/TsHARP (≡ step_02, bez AROSICS)
│   ├── superres/sen2sr.py         # jawne pobranie i załadowanie modelu, tiling (≡ step_03 cz. 1)
│   ├── indices/{spectral,tvdi}.py # OSAVI, TCARI, NDVI, TVDI (≡ step_04)
│   ├── alerts/{baseline,anomaly,status}.py
│   ├── validation/{wald,station}.py
│   ├── reporting/report.py        # raport generowany z metryk (szablon)
│   ├── pipeline.py                # orkiestracja kroków + manifest (≡ step_05)
│   └── cli.py                     # agriwatch run / agriwatch sr-download / agriwatch validate
├── experimental/atprk.py          # poza potokiem (Q-2)
├── tests/
│   ├── unit/                      # wzory, siatki, reguły alertów
│   ├── property/                  # zachowanie średniej, CRS/transform, brak wartości zastępczych
│   ├── integration/               # potok na małym wycinku (fixture)
│   ├── fixtures/                  # mały GeoTIFF testowy (< 200 kB), deterministyczny
│   └── network/                   # testy GEE/CDSE/ISMN — tylko ręcznie (marker `network`)
├── notebooks/AgriWatch_Colab.ipynb  # cienki: mount → pull → pip install -e → agriwatch run
└── .github/workflows/ci.yml       # ruff + pytest (bez sieci i GPU)
```

Stare pliki `step_0x.py` znikają dopiero po przejściu testu regresji (F0.1). Do tego czasu zostają obok.

---

## 5. Zasady jakości (obowiązują od F0 do końca projektu)

1. **Brak danych = `NaN` + `reason_code`**, nigdy liczba. Fallback tylko wtedy, gdy włączony w YAML, i zawsze oznaczony na wyjściu.
2. **Wyjątki konkretne.** `except Exception` wyłącznie na granicy CLI (zapis błędu do manifestu). W CI działa check, który blokuje nowe wystąpienia w `src/`.
3. **Żadnej konfiguracji logowania ani tłumienia ostrzeżeń w modułach.** Logowanie konfiguruje tylko `cli.py`.
4. **Żadnych liczb magicznych** w logice: progi, parametry metod i zakresy fizyczne siedzą w YAML.
5. **Jednostki jawne** w nazwach i atrybutach (`lst_celsius`, `reflectance` 0–1).
6. **Operacje na siatkach tylko przez `grid.py`.** Agregacja = średnia powierzchniowa; zakaz `zoom` do zmiany rozdzielczości w `src/`.
7. **Pochodzenie danych:** każdy GeoTIFF ma tagi `agriwatch_version`, `git_sha`, `config_hash`, `source` (np. `MODIS_MOD11A1`), `source_ids`, `created_utc`, `status`. Każde uruchomienie zapisuje `run_manifest.json`.
8. **Deterministyczność:** ustalone ziarna losowania (RF, testy), zapisane w manifeście.

---

## 6. Kolejność prac i budżet czasu

Kolejność wynika z bezpieczeństwa zmian. Najpierw test, który zamraża obecne zachowanie, potem przenoszenie kodu. Poprawki merytoryczne przychodzą dopiero potem, każda z opisem „przed/po” w CHANGELOG.

### Tydzień 1 — F0.1 Pakiet, konfiguracja, kontrakt (12 h)

| # | Krok | h | Wynik |
|---|---|---:|---|
| 1 | **Test charakteryzujący:** zamrożenie wyników obecnego potoku kroków 2–5 na danych syntetycznych z ustalonym ziarnem (`tests/integration/test_characterization.py`, wyniki `.npz`) | 2 | Siatka bezpieczeństwa dla refaktoru |
| 2 | `pyproject.toml`, układ `src/agriwatch/`, extras, `ruff` | 2 | `pip install -e .` działa lokalnie i w Colab |
| 3 | `config.py` (pydantic) + `configs/condom.yaml` + profile `colab`/`local`; `CONFIG` ze `step_05` i ścieżki z notatnika przenoszone do YAML | 2 | Jedno źródło parametrów |
| 4 | Przeniesienie modułów 1:1 (bez zmian logiki, tłumaczenie docstringów na EN — Q-4) | 3 | Test charakteryzujący zielony |
| 5 | `cli.py`: `agriwatch run --config … --profile colab` | 1 | Uruchomienie jednym poleceniem |
| 6 | Cienki notatnik Colab: mount → `git pull` → `pip install -e` → `agriwatch run`; `build_colab_master.py` generuje ten notatnik; usunięcie `generate_notebook.py` i duplikatu `.ipynb` | 2 | Przepływ GitHub → Dysk → Colab bez zmian dla użytkownika |

Kontrakt `rioxarray` (Q-1) wchodzi w tym tygodniu tylko w `io/` i `pipeline.py`, jako opakowanie. Wnętrza metod dostają na razie tablice numpy, żeby test charakteryzujący nadal przechodził.

### Tydzień 2 — F0.2 Uczciwość danych (8 h)

| # | Krok | h |
|---|---|---:|
| 1 | Inwentaryzacja 32 `except Exception`, 16 `np.full`, 9 `nan_to_num`: tabela „miejsce → usunąć / jawny tryb” w `docs/decisions/F0.2_fallbacks.md` | 1,5 |
| 2 | `qa.py`: typ wyniku kroku (`data`, `status`, `reason_codes`, `source`) + słownik kodów | 1,5 |
| 3 | Usunięcie wartości zastępczych (baseline 0,15/0,05, SWI 50, PPI 0,45, 28 °C, clipping 5–60 °C bez flagi). Źródło LST (S3/MODIS/ERA5) zapisane na wyjściu | 2 |
| 4 | **SR uczciwie (K-09, Q-5):** `agriwatch sr-download` pobiera wagi na Dysk (`data/models/`); brak modelu = etap pominięty ze statusem; bikubika tylko jawnie | 1,5 |
| 5 | Usunięcie AROSICS (Q-3) i przeniesienie ATPRK do `experimental/` (Q-2) | 0,5 |
| 6 | `provenance.py`: tagi GeoTIFF + `run_manifest.json` | 1 |

**Oczekiwana zmiana wyników:** test charakteryzujący przestanie przechodzić (wynik zależy od usuniętych zastępstw). Aktualizujemy go świadomie, z wpisem w CHANGELOG.

### Tydzień 3 — F0.3 Alerty + F0.4 Wald na SEN2SR (11 h)

| # | Krok | h |
|---|---|---:|
| 1 | Evidence Check F0.3: kierunek anomalii TCARI/OSAVI; rozdzielczość TCARI (B05 natywnie 20 m) | 1 |
| 2 | Baseline liczony z tego samego wskaźnika i na tej samej siatce co wartość bieżąca (K-01, K-02); kierunkowy, odporny Z (mediana/MAD) | 3 |
| 3 | `status.py`: `normal/watch/inspect` + `reason_codes` + `model_version`; progi w YAML; testy „anomalia w stronę stresu → inspect / w stronę wigoru → normal” | 2 |
| 4 | Evidence Check F0.4: protokół Walda dla SR Sentinel-2 | 1 |
| 5 | `validation/wald.py`: degradacja → **SEN2SR** vs bikubika; RMSE, SSIM, SAM, ERGAS per pasmo; uruchomienie w Colab (GPU) na jednej scenie Condom | 4 |

### Tydzień 4 — F0.5 Walidacja stacyjna + F0.6 Porządek (9 h)

| # | Krok | h |
|---|---|---:|
| 1 | `validation/station.py`: usunięcie ścieżek „ERA5 jako satelita” i „czujnik vs czujnik” (K-07); brak danych = brak metryk | 2 |
| 2 | `reporting/report.py`: raport z szablonu, wnioski warunkowe na podstawie liczb (bez zdań zakodowanych na sztywno) | 1,5 |
| 3 | Testy: unit (wzory OSAVI/TCARI/NDVI na znanych wartościach, reguły alertów, `grid.aggregate` zachowuje średnią), property, integracja na fixture; oznaczenie testów sieciowych | 2 |
| 4 | GitHub Actions: `ruff` + `pytest -m "not network"` + check zakazanych wzorców (`filterwarnings`, `basicConfig` i `zoom` w `src/`) | 1 |
| 5 | README (EN) zgodny z kodem, `docs/limitations.md`, `CHANGELOG.md` | 1,5 |
| 6 | **Uruchomienie odbiorcze:** `agriwatch run --config configs/condom.yaml --profile colab` dla 2023-07-15 w Colab; wyniki na Dysku z manifestem | 1 |

**Bufor:** brak. Jeśli F0 się przedłuża, w pierwszej kolejności przesuwamy krok 5 z tygodnia 4 (dokumentację) na pierwszy tydzień listopada. Nie przesuwamy testów ani CI.

---

## 7. Kryteria ukończenia F0 (bramka wyjścia)

- [ ] `pip install -e .` + `agriwatch run` działa w Colab na klonie z Dysku
- [ ] CI zielone na `main`: `ruff`, `pytest` (bez sieci i GPU) w < 5 min
- [ ] 0 wystąpień `warnings.filterwarnings("ignore")`, `logging.basicConfig` i `scipy.ndimage.zoom` w `src/` (sprawdzane w CI)
- [ ] 0 wartości zastępczych bez `reason_code` (tabela F0.2 zamknięta)
- [ ] Każdy GeoTIFF ma tagi pochodzenia; każde uruchomienie ma `run_manifest.json`
- [ ] SR: model faktycznie ładowany albo etap jawnie pominięty; Wald porównuje SEN2SR z bikubiką
- [ ] Alerty: ten sam wskaźnik i siatka dla baseline'u i wartości bieżącej, kierunkowy Z, progi w YAML
- [ ] Walidacja stacyjna porównuje wyłącznie produkt satelitarny z referencją
- [ ] README (EN) i CHANGELOG zgodne z kodem
- [ ] Rejestr (dokument nr 3) zaktualizowany; K-01…K-12 mają status

## 8. Czego F0 celowo nie robi

- Nie zmienia źródła LST na S-3 z CDSE (F1.2).
- Nie poprawia metody downscalingu ani zachowania średniej w DMS (F1.3); w F0 dostaje tylko testy, które pokażą skalę problemu.
- Nie wybiera wskaźnika stresu (ΔT/CWSI/TVDI) — to Evidence Brief F1.
- Nie buduje Dockera, bazy danych ani frontendu (F2).
- Nie usuwa GEE (R&D zostaje na GEE do F2).

## 9. Ryzyka

| Ryzyko | Działanie |
|---|---|
| `pip install -e` z Dysku Google jest wolny albo niestabilny | Awaryjnie: `pip install git+https://github.com/...@main` w Colab; dane nadal z Dysku |
| Wagi SEN2SR nie pobierają się albo licencja nie pozwala na użycie komercyjne (R-006) | Etap SR pominięty z jawnym statusem; sprawdzenie licencji w tygodniu 2 |
| Refaktor przekracza 12 h | Tniemy tłumaczenie docstringów (zostaje na później), nie test charakteryzujący |
| Wynik bez zastępstw pokaże, że potok dla Condom w wielu dniach nie ma danych | To oczekiwany i wartościowy wynik; zapisujemy go jako eksperyment E-002 |
