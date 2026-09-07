# Free web data — research inventory (D3.1)

Internal, builders-facing. Researched 2026-09-07 for the Barnboard Data
Platform arc. Every source below is free; verification status and license are
recorded per source — anything we could not fetch directly is marked
**(unverified)**. The fetcher (D3.2) stores selected datasets under
`data/reference/` with sha256 checksums so training and inference never depend
on a website staying up.

Use-case key: **1** milk-yield prediction / lactation curves · **2**
breeding/calving outcomes & heat timing · **3** mastitis / health-event risk ·
**4** milk-price forecasting · **5** breed benchmarking.

## Source table

| # | Name | URL | Publisher | License/Terms | Format | Use-cases | How used |
|---|------|-----|-----------|---------------|--------|-----------|----------|
| 1 | USDA NASS Quick Stats API | https://quickstats.nass.usda.gov/api | USDA National Agricultural Statistics Service | Free; requires free API key + attribution; 50k records/request | REST API (JSON/XML/CSV) | 4, 5 | Training + inference-time lookup of monthly milk prices and milk-per-cow series |
| 2 | USDA ERS Dairy Data | https://www.ers.usda.gov/data-products/dairy-data | USDA Economic Research Service | Free, US public domain | XLSX + CSV | 4 | Training data: monthly milk prices, production, supply back to 1960 |
| 3 | EU Milk Market Observatory | https://agriculture.ec.europa.eu/data-and-analysis/markets/price-data/price-monitoring-sector/milk-and-dairy-products_en | European Commission DG AGRI | Free, EU Commission reuse policy | PDF weekly; historical series on data.europa.eu | 4 | Training/benchmark: EU raw-milk farm-gate prices |
| 4 | AHDB UK farmgate milk prices | https://ahdb.org.uk/dairy/uk-farmgate-milk-prices | AHDB (UK levy board) | Free download | Excel (monthly) | 4 | Training data: monthly UK farmgate price series |
| 5 | FAOSTAT | https://www.fao.org/faostat/en/ | UN FAO | CC BY 4.0 + FAO caveat (no commercial-promotion use) | CSV/XLSX/API, bulk ZIPs | 4, 5 | Benchmark: country-level milk production, yield/animal, producer prices 1961– (covers India) |
| 6 | ICAR Milk Yearly Surveys | https://www.icar.org/publications/milk-yearly-surveys/ | ICAR | Free download | PDF (biennial) | 5 | Benchmark: recorded-population yields by breed and country |
| 7 | CDCB DHI Lactation Averages by Breed | https://queries.uscdcb.com/publish/dhi/current/laall.shtml | Council on Dairy Cattle Breeding (US) | Free public report | HTML tables | 5, 1 | Inference-time lookup: 305-day milk/fat/protein by breed; lactation-curve priors |
| 8 | NZ Dairy Statistics (annual) | https://www.dairynz.co.nz/media/oglesqfm/nz-dairy-statistics-24-25.pdf | DairyNZ + LIC | Free PDFs (site blocks bot fetch) (unverified fetch) | PDF + XLSX tables | 5, 2 | Benchmark: breed production and reproduction stats |
| 9 | Mountain-pastured Braunvieh cows 2000–2015 | https://datadryad.org/dataset/doi:10.5061/dryad.z612jm68g | Dryad (Braunvieh-CH) | Dryad open reuse (CC0-style) | CSV, 1.4 MB | 1, 3 | Training: per-cow repeated milk records + lactation number, calving date, heat/cold stress |
| 10 | UK Holstein age-at-first-calving | https://datadryad.org/dataset/doi:10.5061/dryad.85fm181 | Dryad (RVC London) | Dryad open reuse | CSV, 156 MB | 2, 3, 5, 1 | Training: 396,534 cows — AFC, 305-d yields, calving interval, SCC |
| 11 | Superior dairy sires / daughter yield (Indonesia) | https://data.mendeley.com/datasets/2sm93h8t7y/2 | Mendeley Data (BRIN) | CC BY 4.0 | Tabular | 1, 2 | Training: HF lactation records across 4 parities incl. THI |
| 12 | Clinical Mastitis via IoT udder parameters | https://data.mendeley.com/datasets/kbvcdw5b4m/1 | Mendeley Data | CC BY 4.0 | CSV | 3 | Training: labeled mastitis classifier (cow, breed, days-in-milk, sensors, 0/1 label) |
| 13 | Ketosis risk in German dairy cows | https://zenodo.org/records/18020925 | Zenodo (BMEL study) | CC BY 4.0 | XLSX, 13 MB | 3 | Feature reference: health-risk predictors from routine milk records |
| 14 | Japanese Black cattle accelerometer behaviors | https://zenodo.org/records/5849025 | Zenodo | CC BY-NC-ND 4.0 (restrictive) | CSV | 2 | Reference only (license blocks commercial training): activity-based heat detection |
| 15 | Monthly milk production (plotly classic) | https://raw.githubusercontent.com/plotly/datasets/master/monthly-milk-production-pounds.csv | plotly/datasets | Public sample data | CSV, 168 rows | 1, 4 | Toy series for validating the forecasting pipeline |
| 16 | Kaggle dairy datasets (various) | https://www.kaggle.com/datasets/hardikk011/milk-yield | Kaggle community | Varies; behind login (unverified) | CSV | 1, 4 | Possible demo data — verify columns and license per dataset before use |

Also noted: Statistics Canada monthly milk production/utilization CSV under the
Open Government Licence (https://open.canada.ca/data/en/dataset/bf14a478-7557-431b-b4ad-40f6ed76462b).

## Top pick per use-case

1. **Yield prediction / lactation curves** — Dryad Braunvieh (#9): the only
   verified, freely licensed per-cow repeated milk-record CSV found, with the
   calving dates and lactation numbers needed to fit Wood/Wilmink curves; seed
   priors from CDCB breed averages (#7).
2. **Breeding/calving outcomes** — Dryad UK Holstein AFC (#10): 396k cows with
   calving intervals and subsequent-lactation outcomes; matches barnboard's
   breedings schema at scale.
3. **Mastitis / health risk** — Mendeley IoT mastitis (#12): the only verified
   CC BY dataset with an explicit per-cow mastitis label; pair with #10's SCC
   field for yield-drop threshold calibration.
4. **Milk-price forecasting** — USDA NASS Quick Stats API (#1): decades of
   monthly prices behind a free keyed API, refreshable at inference time.
5. **Breed benchmarking** — CDCB lactation averages (#7) for exotic/crossbred
   references, with ICAR (#6) and FAOSTAT (#5) covering desi breeds and India
   country-level yields.

## Honest gaps

- **Desi-breed per-cow data**: no open per-cow dataset for Gir, Sahiwal, Red
  Sindhi, or Murrah buffalo was found; benchmarks come from ICAR/FAOSTAT
  aggregates and published literature rather than raw records. D3.3's
  benchmark table cites its sources per row.
- **Heat-detection events**: genuinely open estrus-event datasets are scarce;
  the plan uses a rules model (21-day cycle + deviation signals) validated
  against literature (e.g. the open-source BovHEAT tool) instead of training
  on the restrictively-licensed accelerometer set (#14).
- **India milk prices**: FAOSTAT producer prices cover India annually;
  higher-frequency Indian farm-gate series exist (e.g. state dairy federations)
  but were not verified as openly downloadable — revisit if price forecasting
  for INR becomes a priority (barnboard's own sales table is the primary
  signal meanwhile).
