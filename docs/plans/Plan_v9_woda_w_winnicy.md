# Plan v9 — „Woda w winnicy”: użyteczna informacja z tego, co AgriScreen już liczy (prototyp w Colab)

Status: PROPOSED, 2026-10-14 (kierunek i forma prototypu zatwierdzone 2026-10-14; specyfikacja W1 do akceptacji).
Przedefiniowuje moduł 1 Planu v8 (D-064). Moduły 2 i 3 Planu v8 (U-Net na ortofotomapie, rozplątanie sygnału)
zostają jako kolejne moduły. Etapy v7 B–D bez zmian.

**Forma:** prototyp w obecnym układzie — notatnik Colab, Dysk Google, `dashboard.html` (D-068). Publikacja na
GeoWorldLook i automatyczna aktualizacja dopiero po prototypie.

## 1. Cel

Winiarz z działkami w okolicy Condom raz w tygodniu dostaje odpowiedź na cztery pytania:
1. **Jak sucho jest teraz** w porównaniu z normą tej pory roku — słowami, w milimetrach i na tle lat, które pamięta.
2. **Co dalej** — najbliższe 7 dni i perspektywa miesiąca.
3. **Co to znaczy teraz** — w której fazie jest winorośl i czego dotyczy niedobór wody w tej fazie.
4. **Na ile temu ufać** — błąd każdej liczby.

## 2. Diagnoza (stan v1.2)

| # | Problem | Skutek |
|---|---|---|
| 1 | Informacja jako z-score i klasy EDO | nieczytelna dla winiarza (myśli w mm, latach, fazach) |
| 2 | Tylko przeszłość (dekada, ERA5 z opóźnieniem ~5 dni); prognoza 7 dni (opad, ET0) pokazana, ale niepołączona ze stanem gleby | brak odpowiedzi „co dalej” |
| 3 | Brak kontekstu rośliny | ten sam komunikat w maju i w sierpniu |
| 4 | Najmocniej wyeksponowany alarm z NDVI (0 trafień), najlepiej zwalidowane warstwy (opad, pogoda) niżej | odwrócone priorytety |
| 5 | Gleba z oczka ERA5 ~9 km | to informacja o okolicy — trzeba to mówić wprost |
| 6 | Referencja ISMN 20/30 cm częściowo niewiarygodna | podany błąd do rewizji (A4) |

## 3. Kroki (prototyp w Colab)

| Krok | Co | Jak | Jedno sprawdzenie (D-067), potem do produktu | Sesje |
|---|---|---|---|---|
| **W1** | Karta „Woda w winnicy” na górze dashboardu; alarm z NDVI do sekcji informacyjnej; logika EDO do „Szczegółów” | przeliczenie istniejącej wilgotności ERA5-Land 0–100 cm i opadu (specyfikacja w §5) | testy jednostkowe przeliczeń i zgodność percentyla z `clim_anomaly` | 2 |
| **W2** | A4: QC czujników ISMN i ponowne oszacowanie ρ | reguły z `docs/evidence/A4_QC_czujnikow_ISMN.md` (D-060–D-063, do akceptacji) | raport dni oznaczonych i nowe błędy na karcie | 2 |
| **W4** | Najbliższe 7 dni | prosty bilans wody od ostatniego stanu ERA5: opad − parowanie z prognozy, którą dashboard już pobiera (Open-Meteo, ET0 FAO) | test wsteczny 2016–2025 z rzeczywistą pogodą ERA5 zamiast prognozy: błąd zmiany niedoboru w mm; trafność samej prognozy opisana jako niesprawdzona | 1–2 |
| **W5** | Perspektywa 30 dni z lat podobnych | lata 1991–2025 o najbardziej podobnym przebiegu wilgotności w ostatnich 60 dniach i co działo się w nich dalej | test z pominięciem roku (1991–2025): Brier dla „susza za 30 dni” wobec klimatologii; tylko ERA5, bez zależności od ISMN | 2 |
| **W6** | Faza winorośli i znaczenie niedoboru w tej fazie | model sumy temperatur z literatury; najpierw notatka: źródła, parametry dla odmian z Gers, co mówi literatura o niedoborze w każdej fazie | porównanie z publicznymi datami faz, jeśli są dostępne; inaczej opis „orientacyjnie” | 1–2 |

Razem ok. 8–10 sesji. Kolejność jak w tabeli.

**Stan 2026-10-14:** W1 wdrożone w kodzie (`step_09.water_card`, karta na górze dashboardu, sekcja w biuletynie,
`water_card` w `agriwatch_latest.json`, sekcja w `run_summary.md`; selftest przechodzi). Czeka na pierwszy przebieg w Colab
na prawdziwych danych. W1 nie zmienia trafności — te same liczby inaczej podane (§3a).

**Po prototypie (osobna decyzja):** W3 — publikacja karty na GeoWorldLook (Supabase, mapa); W7 — automatyczna
cotygodniowa aktualizacja (GitHub Actions, ERA5-Land z Copernicus Climate Data Store). To część etapu E Planu v8.

## 3a. Karta wyników: co się poprawiło (D-070)

Stała tabela metryk mierzonych na starcie (v1.2) i po każdym kroku. **„Przed” i „po” zawsze na tej samej referencji
i w tym samym okresie** — porównanie starych liczb (referencja z artefaktami) z nowymi (po A4) byłoby nieuczciwe.
Wynik „brak poprawy” też wpisujemy. Tabela żyje w `docs/evidence/karta_wynikow.md` od kroku W2.

| Krok | Czy zmienia trafność | Co porównujemy |
|---|---|---|
| W1 karta | nie — te same liczby inaczej podane | nic; zapisujemy wprost, że to zmiana prezentacji |
| W2 A4 | zmienia referencję, nie produkt | stara i nowa reguła statusu policzone na tej samej, poprawionej referencji: POD/FAR suchych dekad, Brier prawdopodobieństwa (W1/W2/W3 z notatki A4) |
| W4 7 dni | nowy element | błąd zmiany niedoboru wobec punktu odniesienia „bez zmian przez 7 dni” |
| W5 30 dni | nowy element | Brier wobec klimatologii i wobec „susza dziś = susza za 30 dni”; poprawa tylko, gdy lepszy od obu |
| Moduł 3 (Plan v8) | rozplątanie | FAR i opóźnienie składowej winorośli wobec NDVI całego piksela (H-F6, zahashowana przed testem) |

## 4. Czego w tym module nie robimy

- Nie mówimy „winorośl jest w stresie”: bez pojemności wodnej działki (Plan v7 C, D) nie da się tego uczciwie powiedzieć (D-066).
- Bez nowych danych satelitarnych, upraw, chorób i deep learningu.
- Bez zaleceń zabiegów: karta opisuje stan i jego znaczenie, decyzja należy do winiarza.

## 5. Specyfikacja W1 — karta „Woda w winnicy” (do akceptacji przed kodem)

Wszystkie wielkości z danych, które potok już ma: dzienna ERA5-Land w punkcie winnicy (`era5_land_daily.csv`),
status dekadowy (`status_dekads.csv`), zagrożenia pogodowe (`hazard_summary.csv`). Okres normy: 1991–2020,
okno ±15 dni roku (jak w statusie).

| Element karty | Definicja | Przykład tekstu |
|---|---|---|
| **Kategoria** (nagłówek, kolor) | percentyl wilgotności 0–100 cm wobec normy dla tego dnia roku (empiryczny, jak `clim_anomaly`); kategorie wg percentyli US Drought Monitor (D-069): ≤ 2 wyjątkowa susza, ≤ 5 skrajna, ≤ 10 silna, ≤ 20 umiarkowana, ≤ 30 nienormalnie sucho, 30–70 w normie, ≥ 70 wilgotniej niż zwykle | „Silna susza w glebie — sucho jak w 1 roku na 10 o tej porze” |
| **Niedobór w mm** | (mediana normy − stan) × 1000 mm dla warstwy 0–100 cm; zaokrąglony do 5 mm; pokazywany, gdy > 0 | „Brakuje ok. 60 mm wody w glebie względem typowego stanu na koniec września” |
| **Na tle lat** | miejsce bieżącego stanu wśród tego samego dnia roku 1991 – bieżący rok | „Trzeci najsuchszy stan na 30 IX od 1991 r. (po 2003 i 2022)” |
| **Od kiedy** | początek obecnego ciągu dekad ze średnim percentylem ≤ 20 | „Susza w glebie od 1 VII (9 dekad)” |
| **Opad** | suma 30 i 90 dni z ERA5-Land w mm i jako % mediany sum z tego samego okna w normie | „Ostatnie 90 dni: 62 mm, 45% normy” |
| **Prawdopodobieństwo** | istniejące `p_soil_drought` | „Szansa, że czujnik w gruncie też pokazuje suszę: 49%” + dopisek „liczba w rewizji (QC czujników, A4)” do czasu W2 |
| **Przymrozki i upały** | bez zmian (`hazard_summary`) | jak dziś |
| **Skala i opóźnienie** | stała stopka karty | „Okolica (~9 km, model ERA5-Land), nie pomiar w działce. Stan na <ostatni dzień ERA5> — dane dochodzą z ok. 5-dniowym opóźnieniem.” |

Układ dashboardu po W1:
1. Karta „Woda w winnicy” (nowa) + krzywa sezonu (gleba na tle normy, już jest).
2. Przymrozki i upały, pogoda, prognoza (bez zmian).
3. „Roślinność działki (informacyjnie)”: mapa NDVI i kafelki NDVI/NDRE/NDMI (bez zmian treści).
4. „Szczegóły”: status EDO z przyczynami (z-score), matryca sygnałów, wiarygodność, tabela ostatnich lat.

Kod (do napisania po akceptacji; przy zmianach pokazujemy tylko zmienione fragmenty i changelog):
- `step_09_panels.py`: `water_card(era5, status, cfg)` → słownik z elementami tabeli powyżej, `water_card_caption`.
- `step_06_dashboard.py`: nowa karta na górze, przeniesienie sekcji, wskaźnik ryzyka z percentyla zamiast klasy EDO.
- `step_05_colab_run.py`: klucze `WATER_*` w `MONITOR_CONFIG` (kategorie, próg „od kiedy” = 20, zaokrąglenie 5 mm);
  testy karty w selfteście (kategorie, znak niedoboru, ranking, początek ciągu, zgodność percentyla).
- Biuletyn (EN) i `agriwatch_latest.json`: sekcja „Water in the soil” z tymi samymi wielkościami.

## 6. Decyzje

- **D-064:** moduł 1 = „Woda w winnicy” (W1, W2, W4, W5, W6); zmienia kolejność z Planu v8 (D-052).
- **D-065:** na górze karty stan wody i perspektywa; alarm z NDVI tylko informacyjnie; logika EDO w „Szczegółach”.
- **D-066:** niedobór względem normy w glebie modelu ERA5-Land, z dopiskiem „okolica, model”; żadnych twierdzeń o stresie winorośli.
- **D-067:** każdy nowy element ma jedno sprawdzenie na danych historycznych, zapisane przed policzeniem; potem trafia do produktu.
- **D-068:** prototyp w obecnym układzie Colab + Dysk + `dashboard.html`; publikacja (W3) i automatyzacja (W7) po prototypie.
- **D-070:** karta wyników (§3a): „przed” i „po” na tej samej referencji i w tym samym okresie, z punktami odniesienia.
- Specyfikacja W1 (§5) zaakceptowana 2026-10-14: próg „od kiedy” = percentyl ≤ 20, karta po polsku w prototypie.
- **D-069:** kategorie suszy w glebie wg percentyli US Drought Monitor (NDMC/NOAA; system opisany w Svoboda i in. 2002).

## 7. Źródła

- Kategorie D0–D4 US Drought Monitor z percentyli (D0 21–30, D1 11–20, D2 6–10, D3 3–5, D4 0–2): samouczek National
  Drought Mitigation Center, University of Nebraska–Lincoln, https://drought.unl.edu/Education/Tutorials/Usdm/Section-Five.aspx
  [F], zgodnie z opisem NOAA NCEI https://www.ncei.noaa.gov/node/9066 [F].
- Svoboda M. i in. 2002. The Drought Monitor. Bulletin of the American Meteorological Society 83(8): 1181–1190 —
  opis systemu USDM [W; progi percentyli potwierdzone w źródłach powyżej, nie w tym artykule].
- Plan v7, Plan v8, `docs/evidence/A4_QC_czujnikow_ISMN.md`, `docs/MIGRACJA_PODSUMOWANIE.md` (wyniki walidacji opadu,
  pogody i gleby).
