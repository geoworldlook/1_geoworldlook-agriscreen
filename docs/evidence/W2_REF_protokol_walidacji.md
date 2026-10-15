# W2 + REF — protokół walidacji warstwy wody (pre-rejestracja)

> **Status:** `REGISTERED` 2026-10-15 — zapisany **przed** pobraniem danych ERA5 i SWI w punktach stacji ICOS i przed
> policzeniem jakiejkolwiek metryki. Skrót SHA-256 tego pliku (sekcje 1–7) jest w Planie v9 (D-083). Zmiana po
> rejestracji = nowa wersja protokołu z nowym skrótem i opisem, co i dlaczego zmieniono.
> Plan v9, kroki W2 (A4) i REF (D-082). Reguły A4: `docs/evidence/A4_QC_czujnikow_ISMN.md` §3–4 (D-060–D-063).

## 1. Miejsca i warstwy referencyjne

| Miejsce | Sieć, dane | Okres walidacji | Warstwa referencyjna | Głębokości czujników (źródło) | Profile |
|---|---|---|---|---|---|
| **Condom** (obszar główny) | ISMN SMOSMANIA, pliki `.stm` na Dysku | 2016-01-01 – 2024-12-31 | średnia 0,20 i 0,30 m | nagłówki `.stm` | 1 |
| **FR-Aur** Auradé (Gers, 78 km) | ICOS ETC L2 Meteo | 2019-01-01 – 2025-12-31 | 0,30 m | `VARINFO_METEO_L2`: 0,05 / 0,10 / 0,30 / 0,50 / 1,00 m | 4 (czwarty od 2020) |
| **FR-Lus** Lusignan (272 km) | ICOS ETC L2 Meteo (interim) + NRT Meteo | 2023-01-01 – ostatni dzień danych | średnia 0,20 i 0,30 m | `VARINFO_METEO_INTERIM_L2`: 0,05 / 0,10 / 0,20 / 0,30 / 0,60 / 1,00 m | 4 |

Głębokości odczytane 2026-10-15 z plików VARINFO w archiwach ICOS (`ETC L2 ARCHIVE`). Na FR-Aur nie ma czujnika
0,20 m, więc warstwą jest 0,30 m.

**Wrażliwość (raportowana, nie główna):** warstwa 0–1 m — średnia poziomów ważona grubością warstw, którą każdy
poziom reprezentuje (bliżej ERA5-Land 0–100 cm).

## 2. Kontrola jakości referencji

- **Condom:** reguły A4 dokładnie jak w notatce A4 §3–4 (`LOW_IMPLAUSIBLE` θ_dno = 0,10, `FAST_DROP` > 0,05 m³/m³
  w ≤ 6 h; wariant główny W1 — cenzurowanie, W2 i W3 obok; wrażliwość θ_dno = 0,5·WP i 0,15). Dotychczasowe reguły
  (flaga `G`, zakres, wartość stała ≥ 7 dni, okres wymiany czujnika) bez zmian.
- **ICOS:** dane L2 po kontroli ETC; poziom = średnia profili z pliku METEO (`SWC_n`, % → m³/m³). Dodatkowo, na każdym
  poziomie: zakres 0–0,60 m³/m³; `FAST_DROP` (> 0,05 m³/m³ w ≤ 6 h → cały dzień usunięty; uzasadnienie fizyczne
  z A4, niezależne od gleby); dzień = średnia z co najmniej 24 z 48 półgodzin. `LOW_IMPLAUSIBLE` **nie** stosujemy:
  próg 0,10 wynika z gleby Condom (punkt więdnięcia ≈ 0,27), a gleb FR-Aur i FR-Lus nie znamy.
- **Dane bieżące (FR-Lus, NRT po końcu L2):** te same reguły; dni z NRT raportowane osobno jako „wstępne”.
- Liczbę dni oznaczonych raportujemy dla każdej stacji, poziomu i reguły.

## 3. Produkty

- **ERA5-Land 0–100 cm** w punkcie stacji (ta sama funkcja strefy korzeni co karta, `step_04.rootzone`).
- **SWI 0,1° v4, T = 15** w punkcie stacji; T = 10 i T = 40 jako wrażliwość.
- Niczego nie dostrajamy pod stacje (ani T, ani progów, ani okien).

## 4. Metryki (każda para produkt × miejsce)

1. **R Pearsona i ρ Spearmana anomalii klimatologicznych:** z wobec wspólnego okresu z tabeli 1 dla obu serii,
   okno ±15 dni roku, co najmniej 20 wartości w puli (jak `step_07.validate_anomalies`).
2. **R Pearsona i ρ Spearmana anomalii 35-dniowych:** wartość minus wyśrodkowana średnia ruchoma 35 dni
   (min. 15 dni w oknie).
3. **Zgodność klas** (sucho ≤ 30. percentyla, norma, wilgotno ≥ 70. percentyla wobec wspólnego okresu): odsetek dni
   z tą samą klasą i kappa Cohena.
4. **Suche dekady** (średnia dekadowa z ≤ −1): POD i FAR.
5. **Przedziały ufności:** R i ρ — bootstrap blokowy, bloki 30 dni, 1000 powtórzeń, ziarno 42 (jak dotąd);
   zgodność klas i kappa — bootstrap po latach (jak D-080).

**Miara główna:** Condom i FR-Aur — R anomalii klimatologicznych warstwy referencyjnej; FR-Lus — R anomalii
35-dniowych (historia czujników od 2023: anomalie klimatologiczne, klasy i dekady tylko orientacyjnie).

## 5. Jak czytamy wynik (zapisane przed liczeniem)

- Nie ma progu „zaliczone”. Raportujemy wartość z CI i liczbą dni. Opis słowny R na karcie: < 0,3 słaba,
  0,3–0,5 umiarkowana, 0,5–0,7 dobra, > 0,7 bardzo dobra zgodność.
- **Przenośność metody („dowolne pole”):** porównujemy R głównej miary między miejscami. Jeśli przedziały ufności
  Condom i stacji ICOS są rozłączne, piszemy to wprost jako ograniczenie przenośności.
- **A4:** wynik W1 (główny) obok W2 i W3, bez wybierania wariantu po wyniku.
- Po walidacji „Na ile ufać” na karcie podaje liczby ze wszystkich trzech miejsc (albo informację o braku danych).

## 6. Dane bieżące (monitoring, nie walidacja)

Na FR-Lus co tydzień: klasa ERA5 i SWI wobec znaku anomalii 35-dniowej czujnika w ostatnim dniu z danymi. Raport
w `run_summary.md` jako „kontrola bieżąca”. Nie wchodzi do metryk z §4.

## 7. Ograniczenia znane przed liczeniem

- Łąka (FR-Lus) i pole uprawne (FR-Aur) to nie winnica: sprawdzamy warstwę wody i metodę anomalii, nie reakcję winorośli.
- FR-Lus: pełne lata dopiero od 2023 — krótka własna norma czujników.
- FR-Aur: w metadanych zmiana modelu czujnika 2020-10-19 (`SWC-FDR` → `MULTI-Meteo`); wrażliwość: okres od
  2020-10-19. Rok 2022 ma ok. 50% dni.
- ERA5-Land i SWI mają skalę ~9–12 km; stacja to punkt. Część różnic to różnica skali, nie błąd produktu.
- Condom: referencja do czasu powrotu ISMN z danymi do 2024 r. (pliki na Dysku).
