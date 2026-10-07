# AgriWatch v5: stres wodny winnic z otwartych danych — od bilansu wodnego do informacji dla rolnika

> **Status:** `PROPOSED` (2026-10-06). Wymaga zatwierdzenia (`ZATWIERDZAM v5`).
> **Zastępuje:** propozycję `Plan_v4_cel_zawodowy.md` (niezatwierdzoną) i harmonogram E0–E6 z `Plan_v3_monitoring_winnic_SR.md`. Przegląd literatury z v3 i wyniki diagnostyki z v4 (sekcja 2) zostają jako podstawa.
> **Wzorzec:** projekt ESA WineEO (TerraNIS + CESBIO, model Sat'Irr): bilans wodny winnicy zasilany Sentinel-2 z super-resolution do 2,5 m, zalecenia nawadniania w aplikacji Wago — [opis ESA](https://eo4society.esa.int/2021/10/06/irrigation-scheduling-for-viticulture-using-sentinel-2/), [projekt](https://eo4society.esa.int/projects/wine-eo/).
> **Zasoby:** 1 osoba, około 10 h tygodniowo; architektura GitHub → Colab → Dysk Google bez zmian.

---

## 1. Pomysł w trzech zdaniach

1. **Odtwarzamy sprawdzony w przemyśle łańcuch WineEO wyłącznie z otwartych danych i gotowych bibliotek:** pogoda (ERA5-Land, prognoza ECMWF), Sentinel-2 (pokrycie roślinnością → współczynnik uprawy), gleba (SoilGrids) → **dzienny bilans wodny FAO-56 dla każdej winnicy** (biblioteka `pyfao56`).
2. **Wynik to informacja, na której rolnik może działać:**
   - ile wody dostępnej dla winorośli zostało w glebie (FTSW, %),
   - czy winorośl jest w stresie według progów z literatury,
   - za ile dni stres się zacznie przy prognozie na 10 dni,
   - ile wody brakuje (mm).
3. **Każda część ma błąd zwalidowany na otwartych pomiarach terenowych:** wilgotność profilu glebowego na stacjach ISMN (Condom + sieć SMOSMANIA) i ewapotranspiracja na wieżach ICOS. Super-resolution (SEN2SR 2,5 m) jest testowane jako ulepszenie pokrycia roślinnością w małych winnicach, z ablacją.

**Dlaczego to jest lepsze niż poprzednie podejście:**
- Diagnostyka z 6 X pokazała, że w Condom satelity nie poprawiają **przebiegu w czasie** ponad ERA5-Land (R 0,81 dla strefy korzeni).
- Bilans wodny używa ERA5 tam, gdzie jest dobre (pogoda, czas), a Sentinel-2 tam, gdzie ERA5 jest ślepe (stan konkretnej winnicy, czyli jej roślinność i parowanie).
- Wynik jest wyrażony w jednostkach, które rozumie rolnik: mm wody i dni do stresu, a nie m³/m³.

---

## 2. Podstawa w literaturze

Kolumna „Weryfikacja” mówi, jak dokładnie sprawdzono źródło. Prace oznaczone `abstrakt` trzeba przeczytać w całości przed przejęciem parametrów.

| ID | Źródło | Co bierzemy | Weryfikacja |
|---|---|---|---|
| L01 | ESA WineEO / TerraNIS Sat'Irr — [ESA](https://eo4society.esa.int/projects/wine-eo/), [TerraNIS](https://www.terranis.fr/en/project/wineeo/) | Architektura: bilans wodny + fCover z S-2 + SR 2,5 m + zalecenia dzienne; podwójny bilans: rząd i międzyrzędzie | strona projektu |
| L02 | Allen i in. 1998, *FAO Irrigation and Drainage Paper 56* | Metoda: ET0 Penman-Monteith, podwójny współczynnik uprawy (Kcb + Ke), bilans strefy korzeni, współczynnik stresu Ks | standard |
| L03 | Thorp 2022, *pyfao56: FAO-56 evapotranspiration in Python*, SoftwareX 19:101208 — [GitHub](https://github.com/kthorp/pyfao56) | **Gotowa implementacja** FAO-56 (ET0 ASCE, podwójny Kc, bilans, nawadnianie) | README + abstrakt |
| L04 | Campos i in. 2010, *Assessing satellite-based basal crop coefficients for irrigated grapes*, Agric. Water Manag. 98(1):45–54 | Zależność **Kcb–NDVI dla winorośli** | abstrakt |
| L05 | Pôças i in. 2020, przegląd: współczynniki uprawy z indeksów roślinności, Agric. Water Manag. 233:106081 | Dobre praktyki Kc z teledetekcji | tytuł + streszczenie |
| L06 | *Improving the Accuracy of Seasonal Crop Coefficients in Grapevine from Sentinel-2 Data*, Remote Sensing 17(19):3365 (2025) — [DOI](https://doi.org/10.3390/rs17193365) | Kc winorośli z S-2 (aktualny stan wiedzy) | tytuł |
| L07 | Lebon i in. 2003, model bilansu wodnego winnicy (Functional Plant Biology) | **FTSW** (udział wody dostępnej do transpiracji) jako zmienna stresu winorośli | abstrakt |
| L08 | Pellegrino i in. 2006, *A model-based diagnosis tool to evaluate the water stress experienced by grapevine in field sites*, Eur. J. Agron. — [RG](https://www.researchgate.net/publication/222891530) | Związek FTSW ↔ potencjał wodny przedświtowy; **próg stresu FTSW ≈ 0,4** (zamykanie aparatów szparkowych) | abstrakt |
| L09 | *Monitoring vineyard water status using Sentinel-2 images: qualitative survey on five wine estates in the south of France*, OENO One — [link](https://oeno-one.eu/article/view/4752) | Czego chcą winiarze: stan wody, **prognoza pogody**, wigor, wiarygodność wieloletnia | abstrakt |
| L10 | Laroche-Pinel i in. 2021, Remote Sensing 13(9):1837 | Sam S-2 wyjaśnia ~40% zmienności stanu wody winorośli → potrzebny model bilansu, nie tylko indeks | abstrakt |
| L11 | *Sensitivity of Grapevine Soil–Water Balance to Rainfall Spatial Variability at Local Scale Level* — [RG](https://www.researchgate.net/publication/343419583) | **Opad jest głównym źródłem błędu bilansu** → kontrola opadu ERA5 stacjami Météo-France | tytuł |
| L12 | Aybar i in. 2025 (SEN2SR, RSE) + opensr-test (S16, S27 z v3) | SR 10 → 2,5 m z kontrolą spójności i halucynacji | abstrakt + README |
| L13 | Poggio i in. 2021, *SoilGrids 2.0*, SOIL 7:217–240 | Tekstura i retencja gleby (250 m) → pojemność wodna strefy korzeni (TAW) | znana praca |
| L14 | Albergel i in. 2008 (S04); Dorigo i in. 2021 (S34); Calvet i in. 2007 (S33) | Walidacja na profilu SMOSMANIA 5–30 cm; flagi ISMN | znane prace |
| L15 | Muñoz-Sabater i in. 2021, ERA5-Land (S31) | Wymuszenie meteorologiczne (T, Td, promieniowanie, wiatr, opad) | znana praca |
| L16 | Sieć ICOS, stacje ekosystemowe FR-Aur (Auradé) i FR-Lam (Lamasquère) koło Tuluzy | **Pomiar ewapotranspiracji** (eddy covariance) do walidacji ET modelu | do sprawdzenia dostępności danych w ICOS Carbon Portal |

**Co jest nowe w naszym projekcie (wyróżnik dla rekrutera):**
- Otwarta, odtwarzalna wersja łańcucha WineEO.
- Walidacja wieloźródłowa: profil glebowy na wielu stacjach ISMN, ewapotranspiracja ICOS, benchmark ERA5-Land.
- Prognoza „dni do stresu”.
- Uczciwa ablacja SR (10 m wobec 2,5 m) dla małych winnic.

---

## 3. Łańcuch przetwarzania

```text
OTWARTE DANE                         GOTOWE NARZĘDZIA                 INFORMACJA DLA ROLNIKA
ERA5-Land (GEE): T, Td, Rs, wiatr ──► ET0 (pyfao56, ASCE) ──┐
ERA5-Land / Météo-France: opad ─────────────────────────────┤
Prognoza 10 dni (Open-Meteo, ECMWF) ─► ET0 i opad prognoza ─┤
Sentinel-2 + Cloud Score+ (GEE) ─► NDVI per działka ───────►│ Kcb (Campos 2010)   ┌─► FTSW dziś (%) i status stresu
      └─► SEN2SR 2,5 m (rdzeń działki, eksperyment) ───────►│                     ├─► dni do stresu (prognoza)
SoilGrids: tekstura → TAW strefy korzeni ───────────────────┤                     ├─► niedobór wody (mm)
                                                            └► BILANS FAO-56 ─────┼─► trend roślinności vs historia działki
                                                               (pyfao56, dzienny) └─► mapa + tabela + wykresy (strona)
WALIDACJA: ISMN 5–30 cm (Condom + SMOSMANIA) · ICOS ET (FR-Aur, FR-Lam) · benchmark ERA5-Land
```

### Wynik dla każdej winnicy (codziennie; raport i strona co tydzień)

| Pole | Opis | Przykład |
|---|---|---|
| `ftsw` | Woda dostępna dla winorośli w strefie korzeni | 34% |
| `stress_class` | Bez stresu (> 0,4) / umiarkowany (0,2–0,4) / silny (< 0,2); progi wg L08, do potwierdzenia w L07 | umiarkowany |
| `days_to_stress` | Za ile dni FTSW spadnie poniżej 0,4 przy prognozie 10 dni | 4 dni |
| `deficit_mm` | Ile mm brakuje do progu bez stresu | 18 mm |
| `ndvi_vs_history` | Roślinność działki wobec jej średniej z lat 2016–2025 | −12% |
| `confidence` | Niższa przy starej scenie S-2, niepewnym opadzie, małej działce | średnia |
| `expected_error` | Błąd z walidacji (sekcja 4) | ±0,08 FTSW |

**Ramy prawne:** w Gers winnice są głównie nienawadniane. Produkt to wtedy monitoring i prognoza stresu: planowanie prac, ocena ryzyka dla plonu i jakości. Zalecenie nawadniania w mm jest opcją dla regionów, które nawadniają (Langwedocja, Hiszpania, Włochy) — tak jak w WineEO.

---

## 4. Walidacja: błąd na otwartych pomiarach terenowych

| Poziom | Co walidujemy | Dane referencyjne | Metryki | Próg „działa” (zapisany przed testem) |
|---|---|---|---|---|
| **V1. Woda w glebie** | Zapas wody 0–30 cm z modelu (względny) | ISMN Condom 5/10/20/30 cm + 4–6 stacji SMOSMANIA (Gers, Langwedocja) | R, ubRMSD, R anomalii, 95% CI; benchmark: ERA5-Land warstwy 1–2 | R ≥ 0,7 i nie gorzej niż ERA5 o więcej niż 0,05 |
| **V2. Ewapotranspiracja** | ET rzeczywista z modelu | ICOS FR-Aur, FR-Lam (dziennie) | R, RMSE [mm/d], bias | RMSE ≤ 1,0 mm/d |
| **V3. Epizody suszy** | Czy FTSW < 0,4 pokrywa się z suszą w profilu | ISMN 20–30 cm (spadek poniżej 20. percentyla) | POD, FAR | POD ≥ 0,7, FAR ≤ 0,3 |
| **V4. Winorośl** | FTSW → stres winorośli | Literatura (L07, L08); w pilotażu 2027: pomiar potencjału wodnego u rolnika | R z potencjałem wodnym | Raportowane, bez progu do czasu pilotażu |

**Uczciwe granice:**
- Stacje ISMN i ICOS stoją na polach uprawnych i łąkach, nie w winnicach. Walidujemy więc **bilans i dane wejściowe**, a część „winorośl” (próg FTSW 0,4) opiera się na literaturze.
- Mówimy to wprost w raporcie i na stronie.
- Pilotaż 2027 z pomiarem potencjału wodnego u rolnika zamyka tę lukę.

**Wybór parametrów bez przecieku danych:**
- TAW i Kcb ustalamy z literatury i SoilGrids przed walidacją.
- Jeśli kalibrujemy, to tylko na latach 2016–2021; test na 2022–2025.
- Stacje bliskie sobie (Pézenas, Pézenas-old, Prades-le-Lez) liczymy jako jedną grupę w testach przenośności.

---

## 5. Super-resolution: gdzie ma sens

| Hipoteza | Test | Dlaczego może pomóc |
|---|---|---|
| H-SR0 | SR ≠ interpolacja (automatycznie przy każdej scenie) | Stary potok podawał interpolację jako SR |
| H-SR1 | Spójność radiometryczna (opensr-test) | Warunek użycia |
| H-SR2 | NDVI działki z SR 2,5 m (rdzeń 92% powierzchni) stabilniejsze niż z 10 m (rdzeń 70%) | Mniej zanieczyszczenia brzegiem w winnicach < 2 ha |
| H-SR3 | Bilans z Kcb z SR wobec Kcb z 10 m: zmiana błędu V1 i V2 | Czy lepsze Kcb przekłada się na lepszą wodę i ET |

**Eksperyment dodatkowy:** czasowe rozdzielenie NDVI na winorośl i międzyrzędzie.
- Zimą winorośl nie ma liści, więc NDVI pochodzi z okrywy międzyrzędzi.
- Wiosną i latem przyrost NDVI pochodzi z winorośli.
- To proste przybliżenie podwójnego bilansu WineEO. Wymaga sprawdzenia; w literaturze jeszcze go nie zweryfikowaliśmy.

---

## 6. Moduły (struktura bez zmian, jeden nowy plik)

| Plik | Rola | Zmiana |
|---|---|---|
| `step_01_ingest.py` | GEE, maska chmur | + Cloud Score+ jako maska S-2 |
| `step_03_super_resolve.py` | SEN2SR | Naprawa K-09, K-17; testy H-SR0 i H-SR1; NDVI 2,5 m per działka |
| `step_05_colab_run.py` | Sterowanie, rejestr `gwl_*` | + tabela `gwl_status` (status działki na dzień) |
| `step_07_station_pipeline.py` | ISMN + QC + walidacja z CI | Używany do V1 i V3: walidacja dowolnego produktu (np. `WB_SW030`) na stacjach; S-1 zostaje jako dodatek |
| **`step_08_water_balance.py`** (nowy) | Wymuszenie (ERA5-Land, prognoza), Kcb z NDVI, TAW z SoilGrids, bilans `pyfao56`, FTSW, status, dni do stresu, eksport JSON dla strony | Jedyny nowy moduł |
| `notebooks/AgriWatch_Monitor.ipynb` | Co tydzień „Uruchom wszystko” | Zadania: dane → bilans → walidacja → prognoza → publikacja |
| Strona `geoworldlook.vercel.app` | Prezentacja | Czyta `agriwatch_latest.json` + mapy PNG z repozytorium strony |

**Publikacja na stronie bez ręcznej pracy:**
- Notatnik zapisuje `public/agriwatch/*.json` i `*.png`, a następnie wysyła je do repozytorium strony tokenem GitHub z Colab Secrets. Token ustawiasz sam; nie trafia do kodu.
- Vercel sam publikuje nową wersję.

---

## 7. Harmonogram (10 tygodni, do 13 XII 2026)

| Tydz. | Daty | Projekt (~7 h) | Kariera (~3 h) | Artefakt |
|---|---|---|---|---|
| **1** | 6–11 X | `step_08`: wymuszenie ERA5-Land (dziennie) dla 15 winnic i stacji; ET0 w `pyfao56`; NDVI S-2 per działka (Cloud Score+), interpolacja dzienna; Kcb wg Campos 2010 | Lista 20 firm (w tym TerraNIS — robi dokładnie to) | Wykres: NDVI, Kcb, ET0 dla winnic 2016 → dziś |
| **2** | 12–18 X | TAW z SoilGrids; bilans `pyfao56`; FTSW i status dla każdej winnicy; sezon 2022 | CV po angielsku | **Studium przypadku: susza 2022 w 15 winnicach** |
| **3** | 19–25 X | Walidacja V1 i V3: Condom + stacje SMOSMANIA (`step_07`); benchmark ERA5 | LinkedIn; 3 aplikacje | Raport walidacji z CI |
| **4** | 26 X – 1 XI | Walidacja V2 (ICOS ET); kontrola opadu ERA5 stacją Météo-France (otwarte dane) | 3 aplikacje | Tabela błędów ET i opadu |
| **5** | 2–8 XI | Prognoza 10 dni (Open-Meteo/ECMWF) → `days_to_stress`; tabela `gwl_status`; raport tygodniowy | 3 aplikacje | **Biuletyn tygodniowy dla rolnika** (wersja 1) |
| **6** | 9–15 XI | SEN2SR: naprawa, H-SR0, H-SR1; NDVI 2,5 m dla scen sezonów 2022–2025 | Rozmowy z 3 doradcami lub spółdzielniami | Porównanie 10 m / 2,5 m |
| **7** | 16–22 XI | H-SR2, H-SR3 (ablacja w bilansie); rozdzielenie winorośl / międzyrzędzie (eksperyment) | 3 aplikacje | Tabela ablacji SR |
| **8** | 23–29 XI | **Strona produktu na geoworldlook.vercel.app**: mapa winnic, status, wykres FTSW z prognozą, karta „błąd i walidacja”; automatyczna publikacja | 3 aplikacje | **Działający produkt online** |
| **9** | 30 XI – 6 XII | README EN, opis metody (2 strony), test automatyczny na GitHub, przeniesienie repozytorium poza firmowy OneDrive | Przygotowanie do rozmów | Repozytorium publiczne |
| **10** | 7–13 XII | Film 5 min; 4 tygodnie stabilnej pracy (`gwl_runs`); oferta pilotażu 2027 | Podsumowanie: ≥ 15 aplikacji | Film + oferta pilotażu |

**Uwaga o sezonie:** październik–marzec to spoczynek winorośli. Bieżący biuletyn pokaże „brak stresu, uzupełnianie zapasu wody”. Dlatego pokazem produktu jest **sezon 2022 (susza) odtworzony dzień po dniu** + bieżący stan. Pierwszy prawdziwy sezon dla rolnika to kwiecień–wrzesień 2027.

**Cięcia przy opóźnieniu (w tej kolejności):** rozdzielenie winorośl / międzyrzędzie → V2 ICOS → H-SR3.
**Nie tniemy:** tygodni 1–3, 5 i 8, czyli działającego bilansu, walidacji, biuletynu i strony.

---

## 8. Kariera i produkt

- **Dopasowanie do rynku:** dokładnie taki łańcuch sprzedaje TerraNIS (Tuluza) w ramach WineEO / Wago. Projekt pokazuje, że umiesz go zbudować sam z otwartych danych i uczciwie zwalidować.
- **Gdzie jeszcze takie umiejętności są potrzebne:** firmy agri-EO, instytuty (CESBIO, Eurac, TU Wien), ubezpieczenia rolne.
- **Aplikacje od tygodnia 3:** raport walidacji i studium suszy 2022 wystarczą, żeby zacząć rozmowy.
- **Produkt:**
  - pokaz dla doradców w Gers i Langwedocji (tydz. 6),
  - oferta bezpłatnego pilotażu w sezonie 2027 w zamian za pomiary potencjału wodnego (walidacja V4),
  - użycie komercyjne wymaga przejścia z GEE na CDSE (lista „później”).

---

## 9. Ryzyka

| Ryzyko | Obejście |
|---|---|
| TAW (pojemność wodna) winnic nieznana; korzenie winorośli sięgają głęboko | Wartość z SoilGrids + pasmo niepewności ±30%; parametr do nadpisania przez rolnika (CSV); status podawany z `confidence` |
| Błąd opadu ERA5 | Kontrola stacją Météo-France (V4 tydz. 4); w raporcie suma opadu do weryfikacji przez rolnika |
| Dane ICOS niedostępne lub niekompletne | V2 opcjonalna; V1 i V3 wystarczą do raportu |
| SEN2SR nie działa w Colab | Produkt działa na 10 m; SR zostaje eksperymentem |
| Brak czasu | Cięcia z sekcji 7 |

---

## 10. Decyzje do zatwierdzenia

| ID | Decyzja |
|---|---|
| D-024 | Rdzeń produktu: **dzienny bilans wodny FAO-56 per winnica** (`pyfao56`) z Kcb z Sentinel-2, wymuszeniem ERA5-Land, TAW z SoilGrids i prognozą 10 dni. Zastępuje D-020 i propozycję v4. S-1 jako dodatek |
| D-025 | Walidacja V1–V3 na otwartych danych (ISMN, ICOS) z progami z sekcji 4; V4 w pilotażu 2027 |
| D-026 | SR jako ulepszenie Kcb w małych winnicach, testy H-SR0…H-SR3 |
| D-027 | Jeden nowy moduł `step_08_water_balance.py`; publikacja JSON/PNG na geoworldlook.vercel.app |
| D-028 | Harmonogram 10 tygodni (do 13 XII 2026); pokaz: sezon suszy 2022 + bieżący stan |
