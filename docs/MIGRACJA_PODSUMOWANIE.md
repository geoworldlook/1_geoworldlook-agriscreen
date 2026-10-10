# AgriWatch — podsumowanie projektu do migracji (stan na 2026-10-10)

Dokument dla nowego konta (człowieka lub asystenta AI), które przejmuje projekt. Zawiera cel, stan prac, sposób
uruchomienia, audyt wyników i listę otwartych spraw. Czytaj go razem z `docs/plans/Plan_v7_precyzja.md` (decyzje D-040…D-051)
i `docs/evidence/` (dowody do każdej liczby).

---

## 1. Cel

**Cel zawodowy:** gotowy, uczciwie zwalidowany produkt obserwacji Ziemi do portfolio — wejście do pracy w EO.
Priorytetem jest **zamknięcie i opisanie**, nie kolejne rozszerzenia (projekt trwa ok. 2 lata i kilka razy utknął w
„jeszcze jednym ulepszeniu”).

**Cel produktowy:** „skaut” dla rolnika — monitoring działki, który mówi *co się dzieje, gdzie, od kiedy i z jaką pewnością*,
bez doradzania. Obecnie: **anomalia suszy** dla jednej winnicy.

**Obiekt:** winnica VINEYARD_06 (2,92 ha), Condom (Gers, Francja). Walidacja: stacja ISMN SMOSMANIA Condom (136 m od winnicy,
pod trawą, czujniki 5/10/20/30 cm) oraz stacje Météo-France (Condom 0,2 km, Beaucaire 15 km, Réaup 18 km).

**Twarde zasady (decyzje użytkownika):**
- Dane satelitarne **wyłącznie Copernicus** (Sentinel-1/2/3, CLMS, CEMS). Bez Landsat/MODIS/VIIRS (D-048).
  Dane niesatelitarne zostają: ERA5-Land (C3S), ISMN, Météo-France, prognoza Open-Meteo.
- Każda liczba na dashboardzie ma podany błąd walidacji; czego nie zwalidowano — piszemy wprost.
- Nowa warstwa wchodzi do statusu tylko, gdy na ISMN dodaje informację ponad obecne (D-050); wybór metody nigdy nie
  korzysta z danych testowych; klimatologie bez lat przyszłych.
- Zmiany kodu wypychane na `main` **i** na gałąź roboczą; użytkownik komunikuje się po polsku.

---

## 2. Architektura i uruchomienie

**Repozytorium:** `geoworldlook/1_geoworldlook-agriscreen` (GitHub). Kod Python, komentarze i UI po polsku.

| Plik | Rola |
|---|---|
| `step_01_ingest.py` | Sentinel-2 (GEE, przyrostowo), ERA5-Land punktowo (GEE `ECMWF/ERA5_LAND/DAILY_AGGR`, cache roczny) |
| `step_03_super_resolve.py` | SEN2SR 2,5 m z kontrolą jakości qc4 (tylko do map; sygnał ≈ 10 m) |
| `step_04_metrics_alert.py` | indeksy, anomalie (klimatologia przyczynowa, ten sam tor orbity, z predykcyjne), status CDI, biuletyn |
| `step_05_colab_run.py` | konfiguracja `MONITOR_CONFIG`, rejestr CSV, zadania `task_*`, selftest |
| `step_06_dashboard.py` | dashboard HTML |
| `step_07_station_pipeline.py` | ISMN: odczyt, QC, walidacja anomalii (`validate_anomalies`) |
| `step_08_weather.py` | Météo-France: przymrozki/upały, walidacja Tmin/Tmax/opadu/SPI |
| `step_09_panels.py` | panele v1.2: kondycja winnicy, krzywa sezonu, matryca sygnałów |
| `build_colab_master.py` → `notebooks/AgriWatch_Monitor.ipynb` | generator notatnika (nie edytować .ipynb ręcznie) |

**Logika statusu (uproszczony EDO CDI, per dekada):** obserwuj = SPI-1 ≤ −2 lub SPI-3 ≤ −1; sucho = anomalia wilgotności
ERA5-Land 0–100 cm ≤ −1; sprawdź winnicę = sucho ORAZ anomalia NDVI winnicy ≤ −1. Do tego prawdopodobieństwo suszy gleby
p = Φ((−1 − ρz)/√(1−ρ²)), ρ = 0,58.

**Uruchomienie:** Colab z linku GitHub
`https://colab.research.google.com/github/geoworldlook/1_geoworldlook-agriscreen/blob/main/notebooks/AgriWatch_Monitor.ipynb`
→ „Uruchom wszystko”. Pierwsza komórka montuje Dysk i robi `git pull` kopii na Dysku. GPU tylko przy nowych scenach (SR).
Wyniki: `MyDrive/GeoWorldLook/agriwatch/data/05_Final_Outputs/agriwatch/` (`dashboard.html`, `run_summary.md`, `bulletin.md`,
CSV), rejestr: `data/registry/gwl_*.csv`. **Po każdym przebiegu czytać `run_summary.md`.**

**Testy offline:** `python3 step_05_colab_run.py --selftest --out <katalog>` (~4–6 min) i `python3 step_08_weather.py`;
`python3 -m pyflakes step_0*.py step_09_panels.py` (znane: 2× `undefined name 'pd'` w step_01 — adnotacje).

---

## 3. Migracja — lista kontrolna

1. **GitHub:** dostęp (zapis) do repo albo fork; gałąź robocza poprzedniego konta: `claude/charming-franklin-c4i0k3`
   (zsynchronizowana z `main`).
2. **Google Drive:** folder `MyDrive/GeoWorldLook/agriwatch` (klon repo + `data/`: sceny S-2 414 szt., SR, cache ERA5,
   ISMN, Météo-France, rejestr, wyniki). Udostępnić lub skopiować na nowe konto; ścieżka `PROJECT_DIR` w 1. komórce notatnika.
3. **Google Earth Engine:** projekt `ee-geoworldlook` (parametr `gee_project` w `setup_runtime`). Nowe konto potrzebuje
   dostępu do tego projektu albo własnego projektu GEE (zmienić parametr w `build_colab_master.py` i przegenerować notatnik).
4. **Sekrety:** obecnie żadne. Na przyszłość (termika S-3): konto Copernicus Data Space + klient OAuth Sentinel Hub w Colab
   Secrets (`CDSE_SH_CLIENT_ID`, `CDSE_SH_CLIENT_SECRET`). ISMN: konto na ismn.earth (pobieranie ręczne).
5. **Pułapki operacyjne:**
   - Notatnik otwierać **z GitHuba**, nie z kopii na Dysku (lokalne zmiany blokowały `git pull`; dopisek `+dirty` w raporcie).
   - Colab zapisuje notatnik z wynikami do `main` („Utworzono za pomocą Colab”) — przed własnym pushem zawsze `git pull`.
   - Dodanie pasma do `ERA5_LAND_BANDS` wymusza jednorazowe pobranie całego cache (36 lat) — kilka minut.
   - Z kontenera AI nie było dostępu do serwerów Météo-France, CDSE i GEE — te części testuje się dopiero w Colab.

---

## 4. Stan prac

| Wersja / etap | Stan |
|---|---|
| v1.0 — status CDI, walidacja ISMN, dashboard | gotowe |
| v1.1 (etap A planu v7) — klimatologia przyczynowa, tor orbity, z predykcyjne, prawdopodobieństwo suszy gleby | gotowe (A4 QC czujników i A5 protokół walidacji w kodzie — **otwarte**) |
| Pogoda — przymrozki, upały, walidacja Météo-France | gotowe (progi ze stacji referencyjnej, D-049) |
| v1.2 — panel kondycji, krzywa sezonu, matryca sygnałów, NDRE | gotowe; selftest przechodzi. Ostatni przebieg Colab zapisany w repo (wyniki w notatniku) jest z commita `f668b6c` (2026-10-09 08:41 UTC, **przed** commitem v1.2 `a330ad1`) — przebieg po v1.2 potwierdzić nowym `run_summary.md` |
| Okres ISMN automatyczny (`END_DATE="auto"`) | gotowe; **czeka na nowe pliki ISMN 2025–2026** od użytkownika |
| ET0 z ERA5-Land + walidacja na ETP Météo-France | zaprojektowane (`docs/evidence/F7_v12/evap_v2.py`), niewdrożone |
| Mapa anomalii w działce | zaprojektowana; wymaga wycinków 10 m z nazwami z godziną |
| Termika Sentinel-3 SLSTR | zbadana, **odłożona na v1.3** (D-051) |
| README EN + opis do CV | **niezrobione — najwyższy priorytet** |

---

## 5. Audyt wyników

Wszystkie liczby z przebiegów w Colab (rejestr na Dysku) lub z eksperymentów offline powtórzonych niezależnie
(`docs/evidence/F4_eksperymenty`, `F7_v12`). Liczby z potoku sprawdzone 2026-10-10 z `run_summary.md` przebiegu
2026-10-09 08:41 UTC (zapisanego w wynikach notatnika, commit `f668b6c`): zgadzają się co do drugiego miejsca po przecinku. Ocena: **mocne** = solidna metoda i próba; **ograniczone** = poprawne, ale
z istotnym zastrzeżeniem; **słabe/niepotwierdzone** = nie wolno sprzedawać jako zwalidowane.

### 5.1 Tabela wyników

| Warstwa | Wynik | Odniesienie | Ocena |
|---|---|---|---|
| Gleba 0–100 cm (ERA5-Land) | R = 0,58 [0,50; 0,67], n = 2976 dni (2016–2024) | ISMN 20–30 cm | **mocne** — typowy poziom dla ERA5 vs punkt |
| Suche dekady (gleba z ≤ −1) | wykryte 57%, fałszywe 57% | ISMN 20–30 cm | **ograniczone** — to sufit dla R = 0,58 przy regule tak/nie |
| Prawdopodobieństwo suszy gleby | Brier 0,10 vs 0,17 (reguła) i 0,13 (klimatologia); niezawodne | ISMN | **mocne**, ale policzone offline przy wdrożeniu (commit `9f9c477`, skryptu nie zachowano) — nie ma go jeszcze w tabeli walidacji potoku (A5) |
| Gleba 0–7 cm | R = 0,47 [0,37; 0,57] (czujnik od 2019); 0,57 (2016–2019) | ISMN 5 cm | **ograniczone** — wymiana czujnika w 2019 |
| NDVI winnicy (SR 2,5 m) | R = 0,38 [0,16; 0,58], n = 200 dni | ISMN 20–30 cm (pośrednio) | **ograniczone** — pośrednie, z opóźnieniem roślinności |
| NDMI / NDRE | R = 0,40 / 0,29 | jw. | informacyjne; NDRE wyraźnie słabszy |
| Opad 30 dni / SPI-3 | R = 0,90 / 0,87; suche dekady SPI-3: wykryte 66%, fałszywe 30% | deszczomierz MF Condom | **mocne** |
| Tmin / Tmax dzienne | średni błąd 1,04 / 1,09 °C, przesunięcie −0,10 / +0,12 °C | MF Condom | **mocne** |
| Upały (Tmax ≥ 35,5 °C) | wykryte 68%, fałszywe 9%, n = 73 dni (lata testowe 2021+) | MF Condom | **mocne**; próg 35 °C dawał 78%/11% (kalibracja nie przeniosła się — opisane uczciwie) |
| Przymrozki wiosenne | 4 dni ze zdarzeniem w latach testowych | MF Condom | **niepotwierdzone** — za mało zdarzeń |
| Alarm „sprawdź winnicę” (gleba + NDVI) | F7 (migawka rejestru `277d162`): 9 dekad, 0 trafień wobec suchych dekad ISMN (2018–2024). Przebieg 2026-10-09: 11 dekad alarmu w 2018–2024 (2022: 10, 2023: 1); trafień potok nie liczy (A5) | ISMN | **niepotwierdzone** — roślinność reaguje 1–1,5 mies. później |
| SEN2SR 2,5 m | wynik jak 10 m | — | tylko kosmetyka map |

### 5.2 Co wykazały testy negatywne (ważne dla CV — „umiem walidować”)
- Żaden inny indeks (NDMI, NDRE, CRSWIR, kompozyty) ani reguła zgodności kilku indeksów nie poprawia warstwy roślinności;
  indeksy są niemal redundantne (korelacja z 0,92–0,97). Powtórzone niezależnie dwa razy (F7).
- Bilans wodny FAO-56 nie bije ERA5 (F4 B). Asymilacja EnKF z Sentinel-1 nie poprawia (F5). Radar S-1 punktowo R ≈ 0,37.
- Wcześniejsza klimatologia NDVI używała lat przyszłych (wyciek) — usunięte w v1.1; uczciwe R spadło z 0,43 do 0,38.
- Progi z dalszych stacji MF zawyżały dni upału (30 → 16 w 2026) — naprawione (D-049).

### 5.3 Ryzyka i ograniczenia (stan na dziś)
1. **Jedna stacja referencyjna**, pod trawą, 136 m od winnicy, dane ISMN do 2024-12-31 → susza 2026 bez potwierdzenia naziemnego.
   Minimalny wykrywalny efekt dla nowych warstw ≈ częściowe r 0,15–0,30 → nowe warstwy prawie zawsze wyjdą „nie wykazano”.
2. **Czujniki ISMN** mają „dno skali” w suche lata i wymianę 5 cm w 2019 (QC A4 niewdrożone).
3. **Norma ERA5 1991–2020** zawiera lata 2016–2020 (konwencja WMO; nieprzyczynowe dla tych lat — wspólne dla wszystkich reguł).
4. **Jedna działka** — brak porównania z sąsiadami; produkt dla rolnika wymaga wielu działek.
5. Prognoza Open-Meteo — licencja tylko niekomercyjna.
6. Tor orbity S-2 rozpoznawany z godziny przelotu (Otsu); przesunięcie torów ≈ 0,03 NDVI uwzględnione w z, ale nie w paśmie krzywej sezonu (opisane w podpisie).

### 5.4 Werdykt audytu
Wyniki są **rzetelne i uczciwie opisane**: liczby pochodzą z przebiegów, kluczowe eksperymenty zreplikowano niezależnie,
wycieki danych wykryto i usunięto, a ograniczenia są na dashboardzie. Najsłabsze ogniwo to **walidacja alarmu na samej
winorośli** i **brak danych naziemnych po 2024 r.** — to nie są błędy kodu, tylko granice danych referencyjnych.

---

## 6. Następne kroki (w tej kolejności)

1. **Zamrozić v1.2** (tag git) i napisać **README po angielsku + opis projektu (case study) do CV** z wykresami i tabelą 5.1.
2. Wgrać nowe dane ISMN Condom (ismn.earth → Data Viewer → SMOSMANIA/Condom, Header+values; **zastąpić** stare `.stm`)
   i przeliczyć — walidacja wydłuży się automatycznie.
3. Domknąć etap A: QC czujników (A4) i protokół walidacji w kodzie z Brierem (A5).
4. v1.3: ET0 z walidacją na ETP Météo-France; inne działki użytkownika (uśrednianie, porównanie z sąsiadami);
   mapa anomalii w działce; ewentualnie termika S-3 (CLMS LST 3 km jako pomost) i SWI 1 km (CLMS).

**Nie zaczynać** nowych warstw przed punktem 1 — to była przyczyna wcześniejszych zastojów projektu.
