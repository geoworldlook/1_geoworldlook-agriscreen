# AgriWatch v6: platforma informacji o anomalii wilgotności dla winnic — na wzór ESA WineEO

> **Status:** `PROPOSED` (2026-10-07). Wymaga zatwierdzenia (`ZATWIERDZAM v6`).
> **Wzorzec:** projekt ESA WineEO (TerraNIS + CESBIO, usługa Wago) — [artykuł ESA](https://eo4society.esa.int/2021/10/06/irrigation-scheduling-for-viticulture-using-sentinel-2/), [CESBIO](https://www.cesbio.cnrs.fr/irrigation-scheduling-for-viticulture-using-sentinel-2-wineeo/).
> **Różnica wobec wzorca:** WineEO mówi rolnikowi, **kiedy i ile nawadniać**. AgriWatch mówi, **czy winnica jest sucha w porównaniu ze swoją normą** i czy warto ją sprawdzić. Bez dawki nawadniania; winnice w Gers są w większości nienawadniane.
> **Stan wyjściowy (już w kodzie, 2026-10-07):** status dekadowy wg EDO CDI dla jednej winnicy; SEN2SR 2,5 m jako rozdzielczość detekcji (commity `fcf8c64`, `7bf9f0f`); walidacja na ISMN Condom; rejestr `gwl_*` na Dysku. Opis: `docs/ARCHITEKTURA.md`.
> **Relacja do innych planów:** v3 (`APPROVED`) — przegląd literatury i wzorzec EDO zostają. v5 (`PROPOSED`, bilans wodny FAO-56) — nie wchodzi do v6; zostaje opcjonalnym modułem na później (sekcja 2, wiersz „Model”).
> **Zasoby:** 1 osoba, około 10 h tygodniowo, darmowe narzędzia; architektura GitHub → Colab → Dysk Google → strona `geoworldlook.vercel.app`.

> **Ograniczenie źródeł:** proxy sieciowe tej sesji blokowało pełne teksty (eo4society, cesbio, terranis, mdpi i inne). Informacje o WineEO i innych platformach pochodzą ze streszczeń wyników wyszukiwania (poziom `snippet`). Liczby z tych źródeł trzeba sprawdzić w oryginale przed publikacją.
> **Przegląd literatury z pełnych tekstów** (factsheet EDO CDI v4.1.1, Pantaleoni Reluy 2022, Laroche-Pinel 2021, Núñez-Ibarra 2025) i propozycje zmian Z1–Z8: `docs/evidence/F3_przeglad_literatury_platforma.md`.

---

## 1. Pomysł w trzech zdaniach

1. **Platforma jak WineEO/Wago, tylko z inną informacją:** rejestrujesz działkę, a system dla każdej winnicy pokazuje kartę z jednym statusem, przyczynami, mapą 2,5 m, trendem i pewnością. Gdy status się zmieni, wysyła powiadomienie.
2. **Informacja = anomalia, nie zalecenie:** opad (SPI), wilgotność strefy korzeni (ERA5-Land) i roślinność winnicy (NDVI 2,5 m) wobec własnej normy. Status znaczy „sprawdź winnicę”, a nie „winorośl cierpi”. Umiarkowany niedobór wody bywa w winnicy pożądany dla jakości owoców (źródło A18).
3. **Uczciwie o rozdzielczości:** wszystkie 15 winnic leży w jednym oczku ERA5-Land (~9 km). Opad i wilgotność gleby są więc dla nich identyczne. Różnicę między działkami daje tylko Sentinel-2. To dlatego mapa 2,5 m i NDVI działki są rdzeniem platformy.

---

## 2. Wzorzec WineEO — co bierzemy, czym się różnimy

| Element | WineEO / Wago (źródło) | AgriWatch v6 |
|---|---|---|
| Rejestracja działki | Użytkownik rysuje działkę, podaje uprawę, glebę i datę siewu (W4) | Działka z GeoJSON (dziś 15 winnic z `1_AOI_GBOV_CONDOM.geojson`) + atrybuty: zarządzanie międzyrzędziem (zadarnione / częściowo / uprawiane), nawadnianie (tak/nie), rozstaw rzędów |
| Mapy roślinności | Mapa pokrycia roślinnością (fCover) dla każdej sceny Sentinel-2, pokazuje niejednorodność działki (W5) | Dla każdej sceny: NDVI 2,5 m działki, odchylenie piksela od mediany działki (niejednorodność) i anomalia działki wobec innych lat |
| Wskaźnik wody | Woda dostępna w glebie z bilansu wodnego (W4, W6) | Anomalia wilgotności strefy korzeni 0–100 cm (ERA5-Land, z-score i percentyl wobec 1991–2020) + SPI-1, SPI-3 |
| Model | Sat'Irr (CESBIO): bilans FAO-56 z podwójnym Kc; Kcb i pokrycie z NDVI (W6, W7, W8) | Logika EDO CDI (kaskada opad → gleba → roślinność). Bilans FAO-56 z v5 to opcjonalny moduł później, nie warunek v6 |
| Rozdzielczość | Własna sieć SISR: Sentinel-2 do 2,5 m w zakresie widzialnym i NIR; motywacja: niejednorodność działki, drogie zobrazowania VHR (W5). Architektura, dane uczące i walidacja SR nie są publiczne (W14) | SEN2SR (ESA OpenSR, CC0) do 2,5 m; do detekcji wchodzą tylko pasma 10 m, które przechodzą kontrolę spójności (sekcja 6) |
| Rzędy winorośli | Brak dowodu, że SR rozdziela rzędy; TerraNIS do rzędów używa Pléiades Neo 30 cm (W11) | Nie twierdzimy, że 2,5 m rozdziela rzędy (rozstaw ~1,5–2,5 m). Sygnał międzyrzędzia traktujemy jako znane źródło błędu (sekcja 9) |
| Wynik dla użytkownika | Zalecenie: kiedy, gdzie i ile wody; krzywe bilansu; prognoza 7 dni; SMS/e-mail przy ryzyku stresu (W4, W9) | Status (4 klasy + powrót), przyczyny w liczbach, mapa, trend, pewność; e-mail tylko przy **zmianie** klasy; bez dawki |
| Kanał | Platforma WWW + aplikacja mobilna (W4) | Strona statyczna `geoworldlook.vercel.app` czytająca JSON; biuletyn Markdown |
| Walidacja | Brak opublikowanej ilościowej walidacji WineEO na winoroślach (W14). Najbliższa praca TerraNIS: potencjał wodny łodygi z pasm S-2, R² = 0,40 na 36 działkach (W12) | Liczby z walidacji na karcie produktu: ISMN Condom (dziś), sieć SMOSMANIA (22 stacje w repozytorium), test porównawczy SR vs 10 m |
| Model biznesowy | ESA Open Call 2020–2021, ~150 tys. €; dziś Wago w Pixagri Irrigation (B2B, kukurydza, pszenica, bawełna; winorośli nie widać na listach) (W2, W10) | Otwarty, odtwarzalny projekt; pilotaż 2027 z grupą GIEE przy Cave de Condom (A20) |

**Wnioski z przeglądu innych platform (A1–A20), które przejmujemy:**
- **Jedno zdanie znaczenia dla każdej klasy** (EDO Drought News, A3) i przyczyny obok klasy (GEOGLAM, A19).
- **Percentyl i „najsuchsza od X lat” obok z-score** (US Drought Monitor D0–D4, A5; UFZ, A7; Météo-France SSWI, A10).
- **Trend:** zmiana wobec poprzedniej dekady i sprzed 3 dekad (mapy zmian USDM, A6).
- **Powiadomienie tylko przy zmianie klasy** (drought.gov, VigiEau, Weenat; A6, A11, A16).
- **Ostatnia dekada oznaczona jako wstępna.** ERA5-Land-T ma opóźnienie ~5 dni i jest zastępowany wersją finalną po 2–3 miesiącach (A17).
- **Wartość bezwzględna obok anomalii:** wilgotność objętościowa strefy korzeni w m³/m³ (InterSucho, A8).
- **Neutralne nazwy klas po francusku.** „Alerte” i „crise” to oficjalne poziomy ograniczeń w użyciu wody (VigiEau, A11).
- **Żadna z przejrzanych platform operacyjnych nie podawała, że wykrywa na obrazach po SR.** FruitLook pracuje w 20 m, IrriWatch w 10 m (A12, A13). Wyjątkiem jest projekt badawczy SMAIL (2,5 m, A14). Dlatego SR jako rozdzielczość detekcji wymaga jawnego testu (sekcja 6).

---

## 3. Produkt dla użytkownika: karta winnicy

Jedna karta na winnicę, odświeżana co tydzień. Status liczony jest na koniec dekady (10., 20., ostatni dzień miesiąca), jak w EDO. Mapa powstaje dla każdej nowej sceny Sentinel-2.

| Pole | Opis | Źródło w kodzie |
|---|---|---|
| `status` | `normal` / `watch` / `warning` / `alert` / `recovery` (kody stałe); etykiety PL/EN/FR w tabeli niżej | `step_04.build_status` |
| `meaning` | Jedno zdanie, co status znaczy i co zrobić | nowe (słownik etykiet) |
| `drivers` | SPI-1, SPI-3, anomalia strefy korzeni (z, percentyl, „najsuchsza od X lat”), NDVI 2,5 m (z, wiek sceny) | `gwl_status`, `gwl_anomalies.percentile` |
| `trend` | Klasa i z-score teraz vs dekada temu vs 3 dekady temu | nowe |
| `map` | PNG: NDVI 2,5 m działki, odchylenie piksela od mediany działki, obrys | nowe (z `step_03`, `site_stats`) |
| `absolute` | Wilgotność 0–100 cm w m³/m³ i norma dla tej pory roku | `gwl_anomalies.value`, `clim_mean` |
| `confidence` | high / medium / low + powody: wiek sceny, udział czystych pikseli, pokrycie SR, dekada wstępna | `build_status` + `sr_coverage` |
| `expected_error` | Liczba z walidacji, np. „R anomalii z czujnikiem 20–30 cm = 0,58 [0,50; 0,67]” | `gwl_validation_metrics` |
| `provisional` | Czy dane ERA5 dla dekady są wstępne (< 3 mies.) | nowe |
| `site` | Nazwa, powierzchnia, międzyrzędzie, nawadnianie | `gwl_sites` + nowe atrybuty |

**Etykiety (decyzja D-031):**

| Kod | PL | EN | FR (bez „alerte”) | Znaczenie (PL) |
|---|---|---|---|---|
| `normal` | norma | normal | normal | Opad i wilgotność gleby w normie dla tej pory roku |
| `watch` | obserwuj | watch | à surveiller | Mniej opadu niż zwykle; gleba jeszcze w normie |
| `warning` | sucho | dry | sec | Gleba wyraźnie suchsza niż zwykle (rzadziej niż raz na ~6 lat w tym okresie) |
| `alert` | sprawdź winnicę | check vineyard | à vérifier | Gleba sucha **i** roślinność tej winnicy słabsza niż w innych latach |
| `recovery` | powrót do normy | recovery | retour à la normale | Po suszy; anomalie jeszcze ujemne |

**Przykład (dane z uruchomienia 2026-10-07, VINEYARD_06):**
> **Sprawdź winnicę** (od połowy czerwca, 11 dekad). Opad: SPI-1 = −2,4, SPI-3 = −2,8. Gleba 0–100 cm: z = −1,7. NDVI 2,5 m: z = −1,5 (scena sprzed 9 dni). Pewność: wysoka. Błąd: R anomalii gleby z czujnikiem 20–30 cm = 0,58.

---

## 4. Łańcuch przetwarzania

```text
DANE                                   PRZETWARZANIE                                  PLATFORMA
ERA5-Land (GEE), punkt oczka ─────► SPI-1, SPI-3, anomalia 0–100 cm ──────┐
  (jedno oczko dla 15 winnic)        (klimatologia 1991–2020, percentyl)  │
Sentinel-2 L2A (GEE, AOI) ─► SEN2SR 2,5 m ─► kontrola H-SR0/H-SR1 ──┐     ├─► status dekadowy ─► karta winnicy (JSON)
  (jedna scena = wszystkie   (raz na scenę,   (odrzucona = poza     │     │   per winnica        ├─► mapa PNG per scena
   działki AOI)               nie na działkę)  detekcją)            ▼     │                      ├─► biuletyn tygodniowy
                                               NDVI 2,5 m per działka ───┘                      ├─► e-mail przy zmianie klasy
                                               (anomalia vs inne lata,                          └─► strona geoworldlook.vercel.app
                                                rastry przycięte do działek)
WALIDACJA: ISMN Condom 5–30 cm · SMOSMANIA (22 stacje) · porównanie SR vs 10 m na tych samych dniach
```

**Koszt SR nie rośnie z liczbą winnic.** Jedna scena SEN2SR obejmuje całe AOI (~407 × 443 px przy 10 m). Przejście z 1 na 15 winnic nie dokłada obliczeń GPU, tylko statystyki działek.

---

## 5. Architektura platformy

**Moduły (struktura repozytorium bez zmian):**

| Plik | Zmiana w v6 |
|---|---|
| `step_01_ingest.py` | Bez zmian |
| `step_03_super_resolve.py` | Zapis NDVI 2,5 m przyciętego do działek (int16, skala 10 000) |
| `step_04_metrics_alert.py` | Status dla wszystkich winnic; percentyl i „najsuchsza od X lat”; trend; słownik etykiet PL/EN/FR; mapa działki; karta JSON |
| `step_05_colab_run.py` | `VINEYARDS` = 15 winnic; nowe zadania `task_maps`, `task_publish`, `task_notify` |
| `step_07_station_pipeline.py` | Walidacja anomalii ERA5 na stacjach SMOSMANIA (nie tylko Condom) |
| `build_colab_master.py` | Komórki nowych zadań |

**Rejestr:**
- `gwl_sites` dostaje kolumny `inter_row`, `irrigated`, `row_spacing_m` (decyzja D-033). Przy pustej wartości wpisujemy `unknown`.
- `gwl_status` bez zmian schematu; wiersze dla 15 winnic.
- Nowa tabela `gwl_notifications` (`site_id`, `date`, `old_status`, `new_status`, `sent_at`, `channel`) zapobiega podwójnej wysyłce.

**Dane na Dysku:**
- NDVI 2,5 m przycięty do 15 winnic: ~53 tys. pikseli, czyli **~0,11 MB na scenę** (int16).
- Przy ~500–600 scenach od 2016 r. to ~60 MB. Liczbę scen trzeba potwierdzić w `gwl_observations`.
- Pełne rastry 2,5 m AOI zapisujemy tylko dla scen pokazowych.

**Kontrakt danych strony (decyzja D-032):**

```text
public/agriwatch/index.json            lista winnic: site_id, nazwa, obrys (GeoJSON), status, data, pewność
public/agriwatch/sites/<site_id>.json  karta (sekcja 3) + szereg dekad (36 ostatnich) + walidacja
public/agriwatch/maps/<site_id>_<data>.png
public/agriwatch/bulletin.md
```

Publikacja tak jak w v5. Notatnik wysyła pliki do repozytorium strony tokenem GitHub z Colab Secrets (token ustawiasz sam, nie trafia do kodu). Vercel sam publikuje nową wersję.

**Powiadomienia (decyzja D-034):**
- E-mail tylko przy zmianie klasy statusu dla winnicy, wysyłany przez SMTP z hasłem aplikacji w Colab Secrets.
- Lista odbiorców w pliku CSV na Dysku, nie w repozytorium.

---

## 6. SR 2,5 m jako rozdzielczość detekcji

**Co jest już zrobione (2026-10-07):**
- `VEG_PRODUCT = "S2SR_2.5m"`: do statusu wchodzi tylko NDVI ze scen po SEN2SR, które przeszły kontrolę pasm 10 m. Nie ma zastępstwa danymi 10 m.
- Kontrola jest liczona w natywnej rozdzielczości pasma: H-SR0 sprawdza szczegół wobec interpolacji bikubicznej, H-SR1 spójność radiometryczną.
- Pasma 10 m przechodzą (RMSE 0,002–0,004). Pasma 20 m nie przechodzą (RMSE 0,014–0,019 > 0,01), więc NDMI i NDRE z 2,5 m nie są używane.
- Sceny idą od najnowszej. `sr_coverage` pokazuje postęp, a biuletyn podaje pokrycie SR.
- NDVI 10 m jest liczony dalej jako odniesienie.

**Czego oczekiwać (wniosek, nie wynik):**
- SEN2SR ma warstwę, która zachowuje niskie częstotliwości obrazu wejściowego (A15, W13). Średnie NDVI całej działki z 2,5 m powinno więc być bliskie średniemu z 10 m.
- Różnice powinny pochodzić głównie z pikseli brzegowych.
- Zysk z SR to przede wszystkim czytelna mapa niejednorodności (jak w WineEO) i czystszy rdzeń małych działek (0,7–4,1 ha).
- Nie należy oczekiwać wyraźnie wyższej korelacji anomalii z wilgotnością gleby.

**Test H-SR2 (zapisany przed wynikiem; segment `anomaly_clim_paired` jest już w kodzie):**

| Wariant | Opis |
|---|---|
| A | NDVI 10 m, rdzeń bez pasa 10 m (obecny) |
| B | NDVI 2,5 m, rdzeń bez pasa 2,5 m (obecny) |
| C | NDVI 2,5 m, rdzeń bez pasa 10 m — ten sam rdzeń metryczny co A |

- **Miara:** R anomalii NDVI z anomalią czujnika 20–30 cm, na tych samych dniach, po zakończeniu SR wszystkich scen.
- **Dlaczego wariant C:** pas 1 piksela przy 2,5 m to tylko 2,5 m od granicy. Przy rozmyciu SR brzeg (drogi, uwrocia) może wejść do średniej. C oddziela efekt rozdzielczości od efektu szerokości pasa.
- **Reguła decyzji:**
  - Jeśli R(B lub C) ≥ R(A) − 0,05, SR zostaje w detekcji.
  - Jeśli R(B i C) < R(A) − 0,05 przy rozłącznych 95% CI, wynik idzie do ciebie z rekomendacją: wariant C albo 10 m w detekcji, a SR tylko do map. Zmiana to jedna linia konfiguracji (`VEG_PRODUCT`).

---

## 7. Walidacja (progi zapisane przed testem)

| Poziom | Co | Dane | Metryki | Próg „działa” |
|---|---|---|---|---|
| V1 | Anomalia gleby ERA5-Land | ISMN Condom 20–30 cm (jest: R = 0,58 [0,50; 0,67]) + stacje SMOSMANIA z profilem ≥ 20 cm | R anomalii, 95% CI z bootstrapu blokowego | Mediana R ≥ 0,5 na stacjach; wynik per stacja na stronie |
| V2 | Wykrywanie suchych dekad | Jak V1, dekady z anomalią czujnika ≤ −1 | POD, FAR (jest Condom: 0,57 / 0,57) | Raportowane bez progu; FAR podany na karcie jako „jak często sygnał gleby się nie potwierdza” |
| V3 | NDVI winnicy vs wilgotność | ISMN Condom; winnica 136 m od stacji | R anomalii; H-SR2 (sekcja 6) | Reguła z sekcji 6 |
| V4 | Zdarzenie 2022 | Météo-France: rekordowo sucha gleba latem 2022 (A9, `snippet`) | Czy ≥ 12 z 15 winnic ma `warning` lub `alert` w VII–IX 2022 | ≥ 12 z 15 |
| V5 | Teren | Pilotaż 2027 (GIEE Cave de Condom, ApeX Vigne IFV — A20) | Zgodność statusu z obserwacją | Bez progu do pilotażu |

**Uczciwe granice (na karcie produktu):**
- Stacja ISMN stoi na polu obok winnicy, nie w niej.
- Anomalia gleby jest ta sama dla całego oczka ERA5.
- Status nie mierzy potencjału wodnego winorośli.

---

## 8. Etapy (od 12 X 2026, ~10 h tygodniowo)

| Tydz. | Daty | Praca | Artefakt |
|---|---|---|---|
| 1 | 12–18 X | `VINEYARDS` = 15 winnic; uzupełnienie SR wszystkich scen (GPU); odczyt H-SR2 (A/B); Z1 + Z2 + Z4 z F3 (test POD/FAR) | Tabela statusów 15 winnic 2016–2026 |
| 2 | 19–25 X | NDVI 2,5 m przycięty do działek; mapy (NDVI, odchylenie od mediany); wariant C testu H-SR2 | Mapy 15 winnic dla sezonu 2022; wynik H-SR2 |
| 3 | 26 X – 1 XI | Karta JSON (sekcja 3): percentyl, „najsuchsza od X lat”, trend, `provisional`, etykiety PL/EN/FR | `index.json` + `sites/*.json` |
| 4 | 2–8 XI | Strona: mapa winnic w kolorach statusu, karta, wykresy; automatyczna publikacja | **Działająca platforma online** |
| 5 | 9–15 XI | V1, V2 na stacjach SMOSMANIA; V4 (2022) | Karta „błąd i walidacja” |
| 6 | 16–22 XI | Atrybuty działek (`inter_row`, `irrigated`, `row_spacing_m`); dodanie nowej działki z GeoJSON + CSV; `gwl_notifications`; e-mail przy zmianie | Instrukcja „dodaj winnicę” |
| 7 | 23–29 XI | Biuletyn v2: znaczenie klas, przyczyny, trend, notka autora; studium suszy 2022 dla 15 winnic | Biuletyn + studium |
| 8 | 30 XI – 6 XII | Stabilizacja (4 tygodnie w `gwl_runs`), README EN, oferta pilotażu 2027 | Pokaz + oferta |

**Cięcia przy opóźnieniu (w tej kolejności):** powiadomienia e-mail → etykiety FR → V2 na wielu stacjach.
**Nie tniemy:** 15 winnic, karty JSON, strony, H-SR2.

**Sezon:** od listopada do marca winorośl nie ma liści. Warstwa roślinności jest wtedy wyłączona, a karta pokazuje tylko opad i glebę. Pokazem produktu jest sezon 2022 odtworzony dekada po dekadzie oraz bieżący stan.

---

## 9. Ryzyka

| Ryzyko | Obejście |
|---|---|
| SR na CPU: ~60 s na scenę (log z 2026-10-07: 25 kafelków × ~2,4 s) | Środowisko Colab z GPU; limit `SR_MAX_SCENES_PER_RUN`; od najnowszych; czas i urządzenie w `gwl_runs` |
| Klimatologia NDVI 2,5 m niepełna, dopóki SR nie obejmie wszystkich lat | Komunikat i pokrycie SR w biuletynie; status bez warstwy roślinności, gdy brak anomalii 2,5 m |
| Międzyrzędzie (trawa, koszenie, uprawa) dominuje sygnał S-2 w winnicy (A16, W15) | Atrybut `inter_row` na karcie; przy `inter_row = grassed` pewność warstwy roślinności o poziom niżej |
| Jedno oczko ERA5 dla wszystkich winnic | Powiedziane wprost na karcie; różnice między działkami tylko z S-2 |
| Wszystkie źródła zewnętrzne na poziomie `snippet` | Przeczytać oryginały (lista niżej) przed publikacją liczb |
| GEE: licencja niekomercyjna | Pilotaż bezpłatny; komercja wymaga przejścia na CDSE (jak w v5) |
| Użytkownik czyta „sucho” jako „szkoda” | Zdanie znaczenia klasy; umiarkowany niedobór bywa pożądany (A18) |
| Kolizja z językiem prawnym we Francji | Neutralne etykiety FR; dopisek, że status nie ma związku z arrêtés sécheresse |

---

## 10. Decyzje do zatwierdzenia

| ID | Decyzja |
|---|---|
| D-029 | Produkt: platforma informacji o anomalii wilgotności dla wszystkich 15 winnic, na wzór WineEO/Wago (karta, mapa, trend, pewność, powiadomienie), **bez** dawki nawadniania. Bilans FAO-56 z v5 = opcjonalny moduł po v6 |
| D-030 | SR 2,5 m pozostaje rozdzielczością detekcji (wdrożone 2026-10-07); test H-SR2 z regułą decyzji z sekcji 6; NDVI 2,5 m zapisywany przycięty do działek |
| D-031 | Etykiety statusu PL/EN/FR z sekcji 3 (kody w danych bez zmian) |
| D-032 | Kontrakt danych strony (`index.json`, `sites/*.json`, `maps/*.png`) i publikacja tokenem z Colab Secrets |
| D-033 | Nowe kolumny `gwl_sites`: `inter_row`, `irrigated`, `row_spacing_m`; nowa tabela `gwl_notifications` |
| D-034 | Powiadomienia e-mail tylko przy zmianie klasy |
| D-035 | Harmonogram 8 tygodni (12 X – 6 XII 2026), cięcia z sekcji 8 |
| D-036 | Zmiany metody z przeglądu F3 (sekcja 5): Z1 pełna logika EDO CDI v4.1.1, Z2 warstwa roślinności w statusie VI–IX (po teście POD/FAR zapisanym przed zmianą), Z4 wspólny pas brzegowy w metrach; następnie Z8, Z3, Z5, Z6 |

---

## Źródła

Poziom weryfikacji: `snippet` — tylko streszczenie wyniku wyszukiwania (pełny tekst zablokowany przez proxy); `repo` — sprawdzone w kodzie lub danych repozytorium.

**WineEO i TerraNIS (W):**

| ID | Źródło | Co mówi | Poziom |
|---|---|---|---|
| W1 | [ESA, projekt WineEO](https://eo4society.esa.int/projects/wine-eo/) | TerraNIS (prime) + Univ. Toulouse III/CESBIO; usługa Wago na bilansie Sat'Irr; S-2 + in situ + meteo; kiedy, gdzie, ile wody | snippet |
| W2 | [TerraNIS, WineEO](https://www.terranis.fr/en/project/wineeo/) | 2020–2021, ~150 tys. €; części naukowa, techniczna, eksperymentalna; piloty GR, IT, PT, ES, CL | snippet |
| W3 | [ESA, artykuł 2021-10-06](https://eo4society.esa.int/2021/10/06/irrigation-scheduling-for-viticulture-using-sentinel-2/) | 4 użytkowników końcowych: PT, IT, ES, CL (rozbieżność z W2) | snippet |
| W4 | jak W1 | Rejestracja: działka, uprawa, gleba, data siewu; wskaźniki roślinności, stresu wodnego, pogoda; WWW + aplikacja | snippet |
| W5 | jak W3 | fCover dla każdej sceny; rzadkie pokrycie winorośli; SISR do 2,5 m (VIS + NIR) | snippet |
| W6 | [CESBIO, Sat'Irr](https://www.cesbio.cnrs.fr/multitemp/sat-irr-satellite-for-irrigation-scheduling-2/) | Bilans FAO-56; NDVI→Kcb i NDVI→Fc na poziomie działki | snippet |
| W7 | [CESBIO, CHAAMS 2022](https://www.cesbio.cnrs.fr/chaams/wp-content/uploads/sites/4/2022/07/chaams-outils-satirr-et-medi-.pdf) | Podwójny Kc; interpolacja NDVI między scenami | snippet |
| W8 | [SAMIR](https://www.researchgate.net/publication/266471265_SAMIR_a_tool_for_irrigation_monitoring_using_remote_sensing_for_evapotranspiration_estimate) | Kcb = a·NDVI + b | snippet |
| W9 | [MyEasyFarm Wago](https://www.myeasyfarm.com/en/home/myeasyfarm-wago/) | Bilans w czasie rzeczywistym, alerty, prognoza 7 dni, dawka i data | snippet |
| W10 | [TerraNIS, Pixagri Irrigation](https://www.terranis.fr/en/pixagri-irrigation/) | Następca Wago: B2B; kukurydza, pszenica, bawełna | snippet |
| W11 | [Airbus, Pléiades Neo — rzędy winorośli](https://space-solutions.airbus.com/resources/case-studies/pleiades-neo/detection-of-vine-rows-using-pleiades-neo-imagery) | Rzędy wykrywane na obrazach 30 cm | snippet |
| W12 | [Laroche-Pinel i in. 2021, Remote Sens. 13(9):1837](https://www.mdpi.com/2072-4292/13/9/1837); pełny tekst pracy towarzyszącej: OENO One 55(4):115–127 | Potencjał wodny łodygi z **B4, B8, B6, B11**: R² = 0,40, RMSE = 0,26 (> 2500 pomiarów, 36 działek); pas wewnętrzny 5 m | pełny tekst (F3, 1.3) |
| W13 | [Aybar i in. 2025, SEN2SR, RSE](https://www.sciencedirect.com/science/article/pii/S0034425725006261) | Warstwa zachowująca niskie częstotliwości wejścia; prawie zerowe odchylenie reflektancji | snippet |
| W14 | brak źródła | Nie znaleziono publicznej architektury, danych uczących ani walidacji SR WineEO; brak ilościowej walidacji Wago na winoroślach | — |
| W15 | [ICV/TerraNIS, dobre praktyki](https://bonnespratiques-eau.fr/2022/03/15/evaluer-letat-hydrique-de-la-vigne-par-teledetection-spatiale/) | 10 m nie rozdziela rzędu i międzyrzędzia | snippet |

**Inne platformy i literatura (A):**

| ID | Źródło | Co bierzemy | Poziom |
|---|---|---|---|
| A1 | [EDO CDI, factsheet v4.1.1](https://drought.emergency.copernicus.eu/data/factsheets/factsheet_combinedDroughtIndicator_v4.pdf) | Progi CDI; pamięć stanu i klasy przejściowe (tab. 2a); alert = roślinność ≤ −1 przy deficycie opadu **albo** po dekadzie suszy, SMA nie jest konieczne; v4.1: roślinność pomijana przy SPI-1 > 1. Nasz alert (warning ∧ NDVI) jest uproszczeniem — F3, 1.1 i Z1 | pełny tekst |
| A2 | [Cammalleri i in. 2021, NHESS 21:481](https://nhess.copernicus.org/articles/21/481/2021/) | Reguła ciągłości CDI i klasy powrotu | snippet |
| A3 | [EDO/GDO Drought News 2022-08](https://drought.emergency.copernicus.eu/documents/news/GDO-EDODroughtNews202208_Europe.pdf) | Znaczenie klas prostym językiem | snippet |
| A4 | [GDO, SMA factsheet](https://drought.emergency.copernicus.eu/data/factsheets/factsheet_soilmoisture_gdo.pdf) | Ostatnia dekada jako „first guess” | snippet |
| A5 | [US Drought Monitor, kategorie](https://drought.unl.edu/Education/Tutorials/Usdm/section-five.aspx) | D0–D4 = percentyle 30/20/10/5/2 | snippet |
| A6 | [USDM change maps](https://drought.gov/data-maps-tools/usdm-change-maps); [drought.gov e-mail](https://www.drought.gov/news/nidis-drought-alert-emails-get-local-drought-conditions-your-inbox) | Mapy zmian; e-mail przy zmianie kategorii | snippet |
| A7 | [UFZ Dürremonitor](https://www.ufz.de/export/data/2/111650_Dürremonitor_Marx_etal_TdH_2016.pdf) | Klasy percentylowe wilgotności | snippet |
| A8 | [InterSucho](https://sdgs.un.org/partnerships/integrated-system-drought-monitoring-intersucho) | Wartość bezwzględna obok klasy; sieć obserwatorów | snippet |
| A9 | [Météo-France, BSH 2021–2022](https://meteofrance.fr/sites/default/files/files/editorial/bsh_eau_sol_annuel_2021-2022.pdf) | Rekordowo sucha gleba latem 2022 (test V4) | snippet |
| A10 | [Météo-France, SWI/CATNAT](https://donneespubliques.meteofrance.fr/client/document/doc_swi_catnat_277.pdf) | Definicja SWI; okresy powrotu | snippet |
| A11 | [VigiEau](https://www.connexionfrance.com/practical/what-is-frances-drought-website-vigieau/139347) | Prawne poziomy: vigilance, alerte, alerte renforcée, crise | snippet |
| A12 | [FruitLook (eLEAF)](https://greenagri.org.za/wp-content/uploads/1.-Case-Study-FruitLook-FINAL.pdf) | Karta działki, porównanie sezonów, 20 m, doradcy | snippet |
| A13 | [IrriWatch](https://www.aziendaagrariasperimentale.unict.it/sites/default/files/documenti/brochure%20IRRIWATCH.pdf) | Sygnalizacja trzema kolorami; 10 m | snippet |
| A14 | [VRVis, SMAIL](https://www.vrvis.at/en/news-events/news/super-resolution-reconstruction-artificial-intelligence-improves-satellite-data-to-address-ecological-challenges) | SR S-2 do 2,5 m dla małych działek (projekt badawczy) | snippet |
| A15 | jak W13 | — | snippet |
| A16 | [Abubakar i in. 2023, OENO One 57(4)](https://oeno-one.eu/article/view/7703) | Sygnał międzyrzędzia w szeregach S-2 winnic | snippet |
| A17 | [C3S, ERA5-Land-T](https://climate.copernicus.eu/c3s-launches-new-era5-land-t-service) | Opóźnienie ~5 dni; wersja finalna po 2–3 miesiącach | snippet |
| A18 | [Revue suisse Vitic. 2007](https://www.revuevitiarbohorti.ch/wp-content/uploads/2007_01_f_704.pdf) | Klasy potencjału przedświtowego; umiarkowany stres sprzyja dojrzewaniu | snippet |
| A19 | [GEOGLAM Crop Monitor](https://www.cropmonitor.org/global-classification-system) | Przyczyny pokazane obok klasy | snippet |
| A20 | [DRAAF Occitanie, GIEE Cave de Condom](https://draaf.occitanie.agriculture.gouv.fr/IMG/pdf/fi_cavecondom_cle824b18.pdf); [ApeX Vigne](https://www.vinetur.com/en/20260710104038/french-study-finds-crowdsourced-vineyard-data-can-track-water-stress-across-wine-regions.html) | Partner pilotażu; obserwacje terenowe stresu wodnego | snippet |

**Repozytorium:**
- 15 winnic (fid 6–18, 21, 22), 0,68–4,14 ha, razem 33,2 ha, wszystkie w jednym oczku ERA5-Land 0,1° — z `data/1_AOI_GBOV_CONDOM.geojson`.
- 22 stacje SMOSMANIA w `data/7_isismn_data/`.
- Wyniki walidacji Condom z uruchomienia 2026-10-07.
