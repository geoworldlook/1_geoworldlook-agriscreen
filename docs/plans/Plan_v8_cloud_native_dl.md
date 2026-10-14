# Plan v8 — cloud-native i deep learning w warstwie winnicy (AgriWatch v2.0)

Status: PROPOSED, 2026-10-14 (zatwierdzona kolejność modułów i start od A4: 2026-10-14). Nie zastępuje Planu v7:
etapy A–D zostają. v8 dodaje trzy etapy: **E** (uruchamianie poza Colab, cloud-native), **F** (deep learning na
ortofotomapie, rozwinięcie C3) i **G** (publikacja), ułożone w trzy moduły realizowane po kolei (§0). Zakres metody
v1.0/v1.1 bez zmian; zmieniamy sposób uruchamiania i dokładamy warstwę struktury winnicy.

## 0. Zasada modułowa (D-057)

Pracujemy w jednym obszarze naraz. Moduł jest skończony, gdy:
liczby w nim pochodzą z potoku (nie z obliczeń poza nim), testy przechodzą w CI, README po angielsku opisuje moduł
i jest tag w gicie. Do tego czasu nie dokładamy nowych warstw, wskaźników ani obszarów (ET0, przymrozki, choroby,
kolejne działki, zmiany SR). Obszar poszerzamy dopiero po skończonym module.

| Moduł | Zakres | Kiedy | Dni pracy | Luki z ogłoszeń, które zamyka |
|---|---|---|---|---|
| **1. Monitoring suszy gleby: zwalidowany i uruchamialny poza Colab** | v7 A4, A5 + etap E (E1–E6) | XI 2026 – III 2027 | ~13 | cal/val, Git/CI, Docker, xarray/STAC, uruchamianie poza Colab |
| **2. Struktura winnicy z ortofotomapy** | F0–F4 | IV – VIII 2027 | ~17 | deep learning / computer vision, walidacja przestrzenna, przetwarzanie wstępne |
| **3. Rozplątanie sygnału winnicy i test pre-rejestrowany** | F5, F6, G | IX 2027 | ~4 | rzetelna ewaluacja, publikacja |

Po module 3: v7 B, C, D albo nowe obszary — każdy jako osobny moduł.

## 1. Dlaczego

### 1.1. Ustalenia z v7 i F7, na których stoi ten plan

| # | Ustalenie | Źródło |
|---|---|---|
| 1 | NDVI winnicy jest sterowane przez międzyrzędzie (majowe koszenie, sierpniowe zasychanie, jesienny odrost); trend NDVI w kwietniu 0,30 (2016) → 0,62 (2024) | v7 ustalenie 2; F4 `R1` |
| 2 | Żaden z 15 wariantów roślinności nie bije NDVI; zgodność NDVI/NDRE/NDMI nie poprawia warstwy | v7 ustalenie 5; F7 §1 |
| 3 | Warstwa roślinności tego samego dnia nie ma umiejętności wobec ISMN z ≤ −1 (FAR NDVI 0,97). Alarm 2018–2024: w F7 (migawka rejestru `277d162`) 9 dekad, 0 trafień; w przebiegu potoku 2026-10-09 jest 11 dekad alarmu (2022: 10, 2023: 1), trafień potok jeszcze nie liczy — przeliczy je krok A5 | F7 §1; `run_summary.md` 2026-10-09 |
| 4 | SR 2,5 m nie rozdziela rzędów rozstawionych co 2,2–3 m (brak sygnału powyżej częstotliwości Nyquista S-2) | v7 §4 |
| 5 | SR 2,5 m jest równoważny 10 m dla sygnału (ΔR +0,004) | v7 ustalenie 14 |
| 6 | C3 (atrybuty działek z IGN BD ORTHO 20 cm IRC) jest zaplanowane, ale nie ma metody | v7 etap C |

Wniosek: problemem nie jest wskaźnik ani model szeregu czasowego, tylko **mieszany piksel** (winorośl + międzyrzędzie).
Rozdzielenie składowych wymaga informacji o strukturze działki, której S-2 nie zawiera, a ortofotomapa 20 cm tak.

### 1.2. Wymagania rynku, które projekt ma pokrywać

Przegląd 8 ogłoszeń EO z pełnym opisem wymagań (X 2026; firmy EO w Polsce, Francji i Włoszech).

| Umiejętność | Ogłoszenia (z 8) | Stan repozytorium | Etap, który zamyka lukę |
|---|---|---|---|
| Python | 7 | jest | — |
| Deep learning, computer vision | 5 | brak (SEN2SR tylko jako gotowy model) | F (moduł 2) |
| Przetwarzanie wstępne, cal/val | 4 | częściowo (kontrola SR H-SR0/H-SR1, walidacja ISMN) | A4–A5 (moduł 1), F1 |
| Git, CI/CD | 3 | Git jest, CI brak | E5 (moduł 1) |
| Docker | 2 | brak | E4 (moduł 1) |
| Chmura (S3, AWS) | 2 | brak (Colab + Dysk Google) | E2–E4 (moduł 1) |
| xarray, STAC | 2 | brak | E2 (moduł 1) |
| SAR | 2 | S-1 w `step_07` (stacja) | poza v8 |

## 2. Moduł 1 — v7 A4, A5 i etap E (uruchamianie poza Colab; ok. 13 dni)

| Krok | Co | Kryterium akceptacji |
|---|---|---|
| A4 | QC czujników ISMN: utrata kontaktu i „dno skali” 20/30 cm (QC-4 z `docs/evidence/Condom_QC.md`), 5 cm poza walidacją klimatologiczną. Najpierw notatka metodyczna (`docs/evidence/A4_QC_czujnikow_ISMN.md`), potem kod | raport walidacji podaje dni oznaczone przez QC i wpływ na metryki |
| A5 | Protokół walidacji v1.1 w `validate_anomalies` (Plan v7 A5); w pierwszej kolejności Brier, diagram niezawodności i skill wobec klimatologii dla `p_soil_drought` oraz trafność alarmu wobec suchych dekad ISMN | Brier i liczba dekad alarmu z trafieniami pochodzą z `task_validate`, nie z obliczeń offline |
| E1 | Pakiet `src/agriwatch/` z `pyproject.toml` i przypiętymi wersjami; `step_*` jako moduły; notatnik Colab zostaje jako klient. Selftest `step_05` skrócony do CI (dziś ~6 min, z czego ~5 min to synteza scen) | `pip install -e .` działa; `--selftest` z `step_05` i `step_07` uruchamiane jako `pytest` |
| E2 | Sentinel-2 L2A z katalogu STAC Copernicus Data Space (odc-stac lub stackstac) obok GEE; `xarray` jako format pośredni. Zgodne z D-048 (tylko Copernicus). Testowane w Colab lub lokalnie (kontener asystenta nie ma dostępu do CDSE) | średni NDVI działki z GEE i STAC różni się o ≤ 0,01 na 10 scenach (próg do potwierdzenia po pierwszym porównaniu) |
| E3 | Rejestr `gwl_*` i katalog danych niezależne od Dysku Google: ścieżka w `MONITOR_CONFIG` (lokalnie lub magazyn zgodny z S3) | pełny przebieg monitoringu bez Colab i bez Dysku |
| E4 | Dwa obrazy Dockera: CPU (bez SR) i GPU (z SR) | `docker run … --site VINEYARD_06 --until <data>` odtwarza biuletyn; tabele `gwl_*` zgodne z przebiegiem Colab dla zamrożonego okresu (porównanie haszy) |
| E5 | GitHub Actions: ruff, pytest (testy offline), budowa obrazu CPU | zielony status na `main` |
| E6 | README po angielsku: problem, metoda ze źródłami, schemat przepływu, walidacja z liczbami, `docker run`; tag modułu 1 | README pozwala uruchomić projekt bez notatnika |

GEE zostaje jako zapasowe źródło do czasu, aż E2 przejdzie kryterium.

## 3. Moduły 2 i 3 — struktura winnicy z ortofotomapy (deep learning; rozwinięcie C3; ok. 21 dni)

| Krok | Co | Kryterium akceptacji |
|---|---|---|
| F0 | Kampanie IGN BD ORTHO IRC 20 cm dla Gers (licencja Etalab): lata, daty nalotów, wycinki dla 15 winnic AOI z buforem; sceny S-2 bez chmur w ±5 dni od nalotu | tabela kampanii i par (nalot, scena S-2) |
| F1 | **Walidacja SR ortofotomapą.** NDVI z SR 2,5 m vs NDVI z ortofotomapy uśrednionej do 2,5 m. Porównujemy strukturę, nie wartości (ortofotomapa nie jest reflektancją): korelacja składowej wysokoczęstotliwościowej (SR − bikubika vs orto − rozmyta orto), widmo orientacji wzoru | wynik raportowany niezależnie od kierunku; hipoteza H-F1 w §5 |
| F2 | Etykiety: 30–50 kafli 256 × 256 px (20 cm) w QGIS, klasy: okrywa winorośli, zielone międzyrzędzie, odkryta gleba, inne. Słabe etykiety z wykrywania rzędów przez FFT. Podział na zbiory **po działkach**, nie po kaflach. Kafle także z winnic Gers spoza 15 działek AOI (ortofotomapa pokrywa departament), żeby zbiór testowy miał więcej niż 3–5 działek | etykiety i podział w repozytorium (`data/labels/`) |
| F3 | Model: U-Net w PyTorch (segmentation_models_pytorch lub TorchGeo), enkoder pretrenowany, wejście NIR-R-G. Punkt odniesienia: Random Forest na tych samych kanałach | mIoU na działkach testowych wyższe niż RF, CI z bootstrapu po działkach; wyniki per klasa |
| F4 | Atrybuty działki z maski: udział winorośli, udział zielonego międzyrzędzia, rozstaw i azymut rzędów (FFT na masce) | rozstaw zgodny z pomiarem ręcznym na ortofotomapie dla 5 działek (tolerancja do ustalenia w F2) |
| F5 | **Rozplątanie sygnału** (D-058). Mieszanie liniowe dotyczy reflektancji, nie NDVI (iloraz): dla każdej daty S-2 rozplątujemy pasma czerwone i NIR piksela, ρ = f_w·ρ_w + f_m·ρ_m (+ gleba), regresją z ograniczeniami w oknie działki i sąsiadów, z udziałami z F4; NDVI składowych liczymy z rozplątanych reflektancji | składowa międzyrzędzia oddaje koszenie w maju i zasychanie w sierpniu; błąd rekonstrukcji reflektancji piksela raportowany |
| F6 | **Test pre-rejestrowany** (protokół zahashowany przed uruchomieniem, jak w F7): czy anomalia składowej winorośli ma niższy FAR i mniejsze opóźnienie niż NDVI całego piksela. Przed zahashowaniem: najmniejszy wykrywalny efekt przy dostępnej liczbie zdarzeń (D-059) | hipoteza H-F6 w §5; wynik negatywny też jest wynikiem |
| F7 | Udziały i typ międzyrzędzia jako parametry strukturalne bilansu dwuskładnikowego C2 (zgodnie z D-043) | parametry w `gwl_sites` |
| F8 | Eksperyment warunkowy: dostrajanie SR na parach S-2 – ortofotomapa | tylko jeśli F1 pokaże prawdziwy detal; inaczej nie robimy |

Moduł 2 = F0–F4, moduł 3 = F5, F6 i G (F7, F8 po module 3, jako osobne moduły).
To nie jest „uczenie maszynowe na jednej stacji” (v7 §4): F3 uczy się na pikselach ortofotomapy z wielu działek,
a stacja ISMN nie jest celem uczenia.

## 4. Etap G — publikacja (moduł 3)

- G1. Wpis na blogu GeoWorldLook (po angielsku) po module 1, po F1 i po F6.
- G2. README po angielsku (E6) i krótki raport techniczny z wynikami F1 i F6 w `docs/evidence/`.
- G3. Każdy wpis zawiera liczby z CI i to, co nie zadziałało.

## 5. Hipotezy (do zahashowania przed testem)

- **H-F1:** Na scenach S-2 w ±5 dni od nalotu składowa wysokoczęstotliwościowa NDVI z SR 2,5 m jest dodatnio skorelowana
  z odpowiadającą składową ortofotomapy (dolna granica CI z bootstrapu po działkach > 0), mocniej niż składowa bikubiki.
- **H-F6:** Na latach 2018–2024 anomalia składowej winorośli (F5) daje niższy FAR wobec suchych dekad niż NDVI całego piksela
  (sparowany bootstrap blokowy po sezonach, korekta Holma przy wielu wariantach).
- **Moc testu (D-059):** przed zahashowaniem H-F1 i H-F6 liczymy najmniejszy wykrywalny efekt przy dostępnej liczbie
  działek, scen i zdarzeń (dla H-F6: 34 zdarzenia ISMN z ≤ −1 na dniach ze sceną 2018–2024). Jeśli jest większy niż
  realistyczny efekt, piszemy to w protokole przed testem.
- **Ograniczenie walidacji:** ISMN mierzy glebę pod trawą stacji, więc nie jest prawdą o winorośli. Do czasu etapu D (δ13C, ApeX)
  H-F6 sprawdzamy także na terminie wejścia w suszę z bilansu dwuskładnikowego (v7 ustalenie 12, hipoteza) i na latach 2019 oraz 2022.
  W raporcie piszemy to wprost.

## 6. Kolejność i nakład

Założenie: 4–6 h tygodniowo, czyli około 0,7 dnia pracy tygodniowo.

| Moduł | Etap | Dni pracy | Kiedy | Zależy od | Wynik dla CV |
|---|---|---|---|---|---|
| 1 | v7 A4, A5 | ~3 | XI 2026 | — | protokół walidacji v1.1 w potoku |
| 1 | E | ~10 | XI 2026 – III 2027 | A5 | pipeline cloud-native: STAC, xarray, Docker, CI |
| 2 | F0–F1 | ~4 | IV 2027 | moduł 1 | niezależna walidacja super-rozdzielczości |
| 2 | F2–F4 | ~13 | V – VIII 2027 | F0 | U-Net na ortofotomapie, atrybuty działek |
| 3 | F5, F6, G | ~6 | IX 2027 | F4 | rozplątanie sygnału winnicy, test pre-rejestrowany i publikacja |
| — | v7 B, C, D | wg v7 | po module 3 | — | wg v7 |

## 7. Czego nie robimy (i dlaczego)

- Nowych obszarów (ET0, przymrozki, choroby, kolejne działki) przed końcem bieżącego modułu (D-057).
- Modeli głębokich na szeregach czasowych jednej winnicy (245 scen): ogranicza mieszany piksel i opóźnienie, nie pojemność modelu.
- SR jako źródła rzędów: fizycznie niemożliwe (v7 §4).
- Jednorazowej migracji z GEE: GEE zostaje jako zapas do czasu przejścia E2.
- Dostrajania SR bez wyniku F1.
- Rozplątywania samego NDVI (iloraz nie miesza się liniowo, D-058).

## 8. Decyzje

- D-052: Etap E (cloud-native) wchodzi przed C; najpierw kończymy A4 i A5.
- D-053: C3 realizujemy jako etap F (U-Net na IGN BD ORTHO IRC 20 cm + rozplątanie sygnału).
- D-054: Walidacja SR ortofotomapą (F1) przed jakąkolwiek zmianą roli SR w produkcie.
- D-055: H-F1 i H-F6 hashujemy przed uruchomieniem testów; wyniki publikujemy niezależnie od kierunku.
- D-056: Podział danych do uczenia wyłącznie po działkach.
- D-057 (zatwierdzona 2026-10-14): rozbudowa modułowa — jeden obszar naraz, moduły 1 → 2 → 3 (§0); obszar poszerzamy
  dopiero po skończonym module.
- D-058: Rozplątanie w F5 na reflektancji (czerwień, NIR), NDVI składowych liczone z rozplątanych pasm.
- D-059: Przed zahashowaniem hipotez liczymy najmniejszy wykrywalny efekt i zapisujemy go w protokole.

## 9. Źródła

- Plan v7 (`docs/plans/Plan_v7_precyzja.md`), dowody F4 i F7 (`docs/evidence/`).
- IGN BD ORTHO IRC 20 cm, licencja Etalab, np. https://data.gouv.fr/en/datasets/fr-200052264-ignf-orthohr-irc-lamb93-d67-2021-7 (dla Gers sprawdzić w F0).
- SEN2SR: https://github.com/ESAOpenSR/sen2sr
- Ma i in. 2026, „Harvesting AlphaEarth” (arXiv 2601.00857): modele bazowe EO słabo przenoszą się przestrzennie i słabo reagują na czas; walidacja przestrzenna jest konieczna.
