# Public-data download catalog

This catalog implements the scope from the email **“public data to find”**. The retained bundle is intended for
aggregate calibration and capability testing for synthetic data, not direct row-level enrichment. It covers industry,
employment, payroll, receipts, geography, business size and age, legal structure/status, fleet size, healthcare
taxonomy, public-company presence, household/person relationships, vehicle complaints, and food/nutrient relations.

All download links below point to official publishers. The large bundle is intentionally ignored by Git and is not
served from this repository: use a direct link or the reproducible downloader to create
`datasets/public-data/` locally. The default run uses 34 U.S.-aligned sources; the U.S. SSA national-name archive is a
documented opt-in source because its endpoint was not reproducibly accessible during validation.

The default catalog is intentionally U.S.-only. Every manifest row carries `geographic_scope=United States`; the
FMCSA and Colorado API queries filter records to country `US`, the Iowa transform retains only U.S. home offices,
and the quality audit rejects any retained country value outside `US`. The former Corporations Canada feeds and their
generated artifacts were retired.

| Browse by need | Section |
| --- | --- |
| Core business, employment, payroll, receipts, and geography | [Highest-value downloads](#highest-value-downloads) |
| NAICS, SIC, county, place, and ZCTA reference files | [Industry and geography reference data](#industry-and-geography-reference-data) |
| Registries, transportation, healthcare, public companies, and PPP | [Registry and sector-specific data](#registry-and-sector-specific-data) |
| Federal contractors and bankruptcy aggregates | [Official gap examples](#official-gap-examples) |
| Names, address components, business tokens, and text distributions | [Privacy-safe realism calibration](#privacy-safe-realism-calibration) |
| Linked household/person, vehicle-complaint, and food/nutrient structures | [Capability benchmark downloads](#capability-benchmark-downloads) |
| Full, subset, or individual-source commands | [Reproduce or refresh](#reproduce-or-refresh) |

<details>
<summary><strong>Complete 35-source index: keys, direct downloads, publisher pages, and handling</strong></summary>

| Source key | Dataset and vintage | Direct download | Publisher page | Handling |
| --- | --- | --- | --- | --- |
| `census_cbp_state_2023` | Census County Business Patterns — state (2023) | [download](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23st.zip) | [source page](https://www.census.gov/data/datasets/2023/econ/cbp/2023-cbp.html) | Default; official artifact retained |
| `census_cbp_county_2023` | Census County Business Patterns — county (2023) | [download](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip) | [source page](https://www.census.gov/data/datasets/2023/econ/cbp/2023-cbp.html) | Default; official artifact retained |
| `census_zbp_detail_2023` | Census ZIP Code Business Patterns — industry detail (2023) | [download](https://www2.census.gov/programs-surveys/cbp/datasets/2023/zbp23detail.zip) | [source page](https://www.census.gov/data/datasets/2023/econ/cbp/2023-cbp.html) | Default; official artifact retained |
| `census_nes_state_2022` | Census Nonemployer Statistics — state (2022) | [download](https://www2.census.gov/programs-surveys/nonemployer-statistics/datasets/2022/historical-datasets/nonemp22st.zip) | [source page](https://www.census.gov/data/datasets/2022/econ/nonemployer-statistics/2022-ns.html) | Default; official artifact retained |
| `census_nes_county_2022` | Census Nonemployer Statistics — county (2022) | [download](https://www2.census.gov/programs-surveys/nonemployer-statistics/datasets/2022/historical-datasets/nonemp22co.zip) | [source page](https://www.census.gov/data/datasets/2022/econ/nonemployer-statistics/2022-ns.html) | Default; official artifact retained |
| `census_abs_company_summary_2023` | Census Annual Business Survey company summary (2023) | [download](https://www2.census.gov/programs-surveys/abs/data/2023/AB2300CSA01.zip) | [source page](https://api.census.gov/data/2023/abscs.html) | Default; official artifact retained |
| `census_bds_state_firm_size_2023` | Census Business Dynamics Statistics — state by firm size (1978–2023) | [download](https://www2.census.gov/programs-surveys/bds/tables/time-series/2023/bds2023_st_fz.csv) | [source page](https://www.census.gov/data/datasets/time-series/econ/bds/bds-datasets.html) | Default; official artifact retained |
| `bls_qcew_annual_singlefile_2025` | BLS Quarterly Census of Employment and Wages — annual single file (2025) | [download](https://data.bls.gov/cew/data/files/2025/csv/2025_annual_singlefile.zip) | [source page](https://www.bls.gov/cew/downloadable-data-files.htm) | Default; official artifact retained |
| `census_naics_2022_descriptions` | Census 2022 NAICS descriptions (2022) | [download](https://www2.census.gov/programs-surveys/nonemployer-statistics/technical-documentation/code-lists/nes_naics22.txt) | [source page](https://www.census.gov/programs-surveys/nonemployer-statistics/technical-documentation/reference/naics-descriptions.html) | Default; official artifact retained |
| `census_sic_descriptions` | Census SIC descriptions (1987 SIC used in 1988–1997 SUSB) | [download](https://www2.census.gov/programs-surveys/susb/technical-documentation/sic_codes_1988_to_1997.txt) | [source page](https://www.census.gov/programs-surveys/susb/technical-documentation/reference-files/industry-reference-files.html) | Default; official artifact retained |
| `census_gazetteer_counties_2025` | Census Gazetteer — counties (2025) | [download](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_counties_national.zip) | [source page](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2025.html) | Default; official artifact retained |
| `census_gazetteer_places_2025` | Census Gazetteer — places (2025) | [download](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip) | [source page](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2025.html) | Default; official artifact retained |
| `census_gazetteer_zcta_2025` | Census Gazetteer — ZIP Code Tabulation Areas (2025) | [download](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_zcta_national.zip) | [source page](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.2025.html) | Default; official artifact retained |
| `fmcsa_company_census_distribution` | FMCSA Company Census U.S. privacy-minimized distribution (live snapshot) | [download](https://data.transportation.gov/resource/az4n-8mr2.csv?%24select=phy_country%2Cphy_state%2Cstatus_code%2Ccarrier_operation%2Cbusiness_org_desc%2Cfleetsize%2Ccount%28%2A%29+as+records&%24where=phy_country+%3D+%27US%27&%24group=phy_country%2Cphy_state%2Cstatus_code%2Ccarrier_operation%2Cbusiness_org_desc%2Cfleetsize&%24order=records+desc&%24limit=500000) | [source page](https://data.transportation.gov/Trucking-and-Motorcoaches/Company-Census-File/az4n-8mr2/about_data) | Default; U.S.-only official aggregate retained |
| `sec_company_tickers_exchange` | SEC EDGAR company, CIK, ticker, and exchange associations (continuously updated) | [download](https://www.sec.gov/files/company_tickers_exchange.json) | [source page](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) | Default; official artifact retained |
| `sba_ppp_data_dictionary` | SBA PPP data dictionary (2024-09-30 release) | [download](https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/ppp-data-dictionary.xlsx) | [source page](https://data.sba.gov/dataset/ppp-foia) | Default; official artifact retained |
| `census_surnames_2010` | Census frequently occurring surnames (2010) | [download](https://www2.census.gov/topics/genealogy/2010surnames/names.zip) | [source page](https://www.census.gov/data/developers/data-sets/surnames/2010.html) | Default; official artifact retained |
| `ssa_national_names` | SSA national given-name counts (1880–2025) | [download](https://www.ssa.gov/oact/babynames/names.zip) | [source page](https://www.ssa.gov/oact/babynames/limits.html) | Opt-in; endpoint returned HTTP 403 during validation |
| `nyc_popular_baby_names` | NYC DOHMH popular baby names (updated annually) | [download](https://data.cityofnewyork.us/resource/25th-nujf.csv?%24limit=50000) | [source page](https://data.cityofnewyork.us/Health/Popular-Baby-Names/25th-nujf/data) | Default; official artifact retained |
| `usps_publication_28_suffixes` | USPS Publication 28 street suffix standards (live page) | [download](https://pe.usps.com/text/pub28/28apc_002.htm) | [source page](https://pe.usps.com/text/pub28/28apc_002.htm) | Default; official artifact retained |
| `tiger_roads_los_angeles_2025` | Census TIGER/Line roads — Los Angeles County, CA (2025) | [download](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_06037_roads.zip) | [source page](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html) | Default; road components retained after geometry removal |
| `tiger_roads_cook_2025` | Census TIGER/Line roads — Cook County, IL (2025) | [download](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_17031_roads.zip) | [source page](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html) | Default; road components retained after geometry removal |
| `tiger_roads_suffolk_ma_2025` | Census TIGER/Line roads — Suffolk County, MA (2025) | [download](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_25025_roads.zip) | [source page](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html) | Default; road components retained after geometry removal |
| `tiger_roads_new_york_2025` | Census TIGER/Line roads — New York County, NY (2025) | [download](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_36061_roads.zip) | [source page](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html) | Default; road components retained after geometry removal |
| `tiger_roads_harris_2025` | Census TIGER/Line roads — Harris County, TX (2025) | [download](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_48201_roads.zip) | [source page](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html) | Default; road components retained after geometry removal |
| `tiger_roads_king_2025` | Census TIGER/Line roads — King County, WA (2025) | [download](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_53033_roads.zip) | [source page](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2025.html) | Default; road components retained after geometry removal |
| `cfpb_complaints` | CFPB Consumer Complaint Database (continuously updated) | [download](https://files.consumerfinance.gov/ccdb/complaints.csv.zip) | [source page](https://www.consumerfinance.gov/data-research/consumer-complaints/) | Default; staged, aggregated, and source rows removed |
| `iowa_active_business_entities` | Iowa active business entities (monthly) | [download](https://idh-be.iowa.gov/api/v1/datasets/554/rows.csv) | [source page](https://data.iowa.gov/catalog/dataset/554) | Default; staged, aggregated, and source rows removed |
| `colorado_business_entities_us_distribution` | Colorado business entities — U.S. principal-address distribution (live snapshot) | [download](https://data.colorado.gov/resource/4ykn-tg5h.csv?%24select=entitytype%2Centitystatus%2Cjurisdictonofformation%2Cprincipalstate%2Cprincipalcountry%2Cdate_extract_y%28entityformdate%29+as+formation_year%2Ccount%28%2A%29+as+records&%24where=principalcountry+%3D+%27US%27&%24group=entitytype%2Centitystatus%2Cjurisdictonofformation%2Cprincipalstate%2Cprincipalcountry%2Cdate_extract_y%28entityformdate%29&%24order=records+desc&%24limit=500000) | [source page](https://data.colorado.gov/Business/Business-Entities-in-Colorado/4ykn-tg5h/about_data) | Default; U.S.-only official aggregate retained |
| `cms_nppes_weekly_v2` | CMS NPPES weekly incremental V2 (2026-08-10 through 2026-08-16) | [download](https://download.cms.gov/nppes/NPPES_Data_Dissemination_081026_081626_Weekly_V2.zip) | [source page](https://download.cms.gov/nppes/NPI_Files.html) | Default; staged, aggregated, and source rows removed |
| `sba_ppp_150k_plus` | SBA PPP loans above $150,000 (2024-09-30 release) | [download](https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/public_150k_plus_240930.csv) | [source page](https://data.sba.gov/dataset/ppp-foia) | Default; staged, aggregated, and source rows removed |
| `acs_pums_nc_person_2024` | Census ACS PUMS North Carolina person records (2024 1-year) | [download](https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_pnc.zip) | [source page](https://www.census.gov/programs-surveys/acs/microdata/access.html) | Default; staged, cell-suppressed, and source rows removed |
| `acs_pums_nc_housing_2024` | Census ACS PUMS North Carolina housing records (2024 1-year) | [download](https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_hnc.zip) | [source page](https://www.census.gov/programs-surveys/acs/microdata/access.html) | Default; staged, cell-suppressed, and source rows removed |
| `nhtsa_complaints_2020_2024` | NHTSA vehicle complaints received 2020–2024 | [download](https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2020-2024.zip) | [source page](https://www.nhtsa.gov/nhtsa-datasets-and-apis) | Default; staged, cell-suppressed, and source rows removed |
| `usda_fooddata_foundation_2026_04` | USDA FoodData Central Foundation Foods (2026-04-30) | [download](https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_csv_2026-04-30.zip) | [source page](https://fdc.nal.usda.gov/download-datasets/) | Default; non-person relational archive retained |

</details>

Snapshot date: **2026-08-27**. The complete machine-readable inventory, SHA-256 checksums, byte sizes, source URLs,
and transformation notes are in `datasets/public-data/manifest.csv`. The record-level evidence is in
`datasets/public-data/coverage-report.csv`, `coverage-report.json`, and `coverage-report.md`. See
[Public-data examples](public-data-examples.md) for a verified example from every requested category and every local
manifest artifact, including the privacy-safe realism and capability-benchmark families.

## Verified 10-million-record gate

The local bundle passes the requested threshold without counting FMCSA's server-side underlying rows:

- **10,933,879 locally materialized or locally processed core source records**.
- **10 distinct local core source families**: CBP/ZBP, NES, ABS, BDS, QCEW, Iowa Active Business Entities,
  Colorado Business Entities, CMS NPPES Type-2 Organizations, SBA PPP FOIA, and SEC EDGAR associations.
- **15,329,657 verified core source records across 11 families** when the 4,395,778 U.S. FMCSA entities represented by
  the downloaded server-side aggregate are included.
- The count uses source rows or published aggregate rows, not unique or deduplicated businesses. Supporting
  NAICS/SIC and Gazetteer reference rows are deliberately excluded from the 10-million threshold.

## Highest-value downloads

| Dataset | What it supplies | Direct download | Downloaded artifact |
| --- | --- | --- | --- |
| Census County Business Patterns 2023 — state | NAICS, establishments, employees, payroll, legal form, and employment-size classes by state | [ZIP](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23st.zip) | `datasets/public-data/raw/census_cbp_state_2023.zip` |
| Census County Business Patterns 2023 — county | NAICS, establishments, employees, and payroll by county | [ZIP](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip) | `datasets/public-data/raw/census_cbp_county_2023.zip` |
| Census ZIP Code Business Patterns 2023 — industry detail | ZIP Code × NAICS establishment counts and employment-size distributions | [ZIP](https://www2.census.gov/programs-surveys/cbp/datasets/2023/zbp23detail.zip) | `datasets/public-data/raw/census_zbp_industry_detail_2023.zip` |
| Census Annual Business Survey 2023 — company summary | Employer-firm characteristics by industry and geography | [ZIP](https://www2.census.gov/programs-surveys/abs/data/2023/AB2300CSA01.zip) | `datasets/public-data/raw/census_abs_company_summary_2023.zip` |
| Census Nonemployer Statistics 2022 — state | Nonemployer establishments and receipts by NAICS/state | [ZIP](https://www2.census.gov/programs-surveys/nonemployer-statistics/datasets/2022/historical-datasets/nonemp22st.zip) | `datasets/public-data/raw/census_nes_state_2022.zip` |
| Census Nonemployer Statistics 2022 — county | Nonemployer establishments and receipts by NAICS/county | [ZIP](https://www2.census.gov/programs-surveys/nonemployer-statistics/datasets/2022/historical-datasets/nonemp22co.zip) | `datasets/public-data/raw/census_nes_county_2022.zip` |
| Census Business Dynamics Statistics 2023 | Firm births/deaths and job creation/destruction by state and firm size, 1978–2023 | [CSV](https://www2.census.gov/programs-surveys/bds/tables/time-series/2023/bds2023_st_fz.csv) | `datasets/public-data/raw/census_bds_state_by_firm_size_2023.csv` |
| BLS QCEW annual 2025 | Employment, establishments, payroll, and wages by NAICS, ownership, and geography | [ZIP](https://data.bls.gov/cew/data/files/2025/csv/2025_annual_singlefile.zip) | `datasets/public-data/raw/bls_qcew_annual_singlefile_2025.zip` |

## Industry and geography reference data

| Dataset | What it supplies | Direct download | Downloaded artifact |
| --- | --- | --- | --- |
| Census 2022 NAICS descriptions | Valid NAICS codes and official labels | [TXT](https://www2.census.gov/programs-surveys/nonemployer-statistics/technical-documentation/code-lists/nes_naics22.txt) | `datasets/public-data/raw/census_naics_2022_descriptions.txt` |
| Census SIC descriptions | Valid 1987 SIC hierarchy and labels used by 1988–1997 SUSB | [TXT](https://www2.census.gov/programs-surveys/susb/technical-documentation/sic_codes_1988_to_1997.txt) | `datasets/public-data/raw/census_sic_descriptions_1988_1997.txt` |
| Census 2025 Gazetteer — counties | County names, FIPS, area, latitude, and longitude | [ZIP](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_counties_national.zip) | `datasets/public-data/raw/census_gazetteer_counties_2025.zip` |
| Census 2025 Gazetteer — places | Valid place/state combinations and coordinates | [ZIP](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip) | `datasets/public-data/raw/census_gazetteer_places_2025.zip` |
| Census 2025 Gazetteer — ZCTAs | ZIP Code Tabulation Areas and coordinates | [ZIP](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_zcta_national.zip) | `datasets/public-data/raw/census_gazetteer_zcta_2025.zip` |

## Registry and sector-specific data

The direct source links below are public, but several contain row-level identifiers or contact fields. The local
artifacts listed here are privacy-minimized distributions; the source rows were deleted after successful processing.

| Dataset | What it supplies | Direct source download | Privacy-minimized local artifact |
| --- | --- | --- | --- |
| Iowa active business entities | Entity type, effective year, state/country, and legal-designator patterns | [ZIP/CSV](https://idh-be.iowa.gov/api/v1/datasets/554/rows.csv) | `derived/iowa_business_registry_distribution.csv`; `derived/iowa_legal_name_pattern_distribution.csv` |
| Colorado business entities | Entity type, status, formation year, jurisdiction, and principal state for U.S.-principal-address entities | [U.S.-only aggregate CSV query](https://data.colorado.gov/resource/4ykn-tg5h.csv?%24select=entitytype%2Centitystatus%2Cjurisdictonofformation%2Cprincipalstate%2Cprincipalcountry%2Cdate_extract_y%28entityformdate%29+as+formation_year%2Ccount%28%2A%29+as+records&%24where=principalcountry+%3D+%27US%27&%24group=entitytype%2Centitystatus%2Cjurisdictonofformation%2Cprincipalstate%2Cprincipalcountry%2Cdate_extract_y%28entityformdate%29&%24order=records+desc&%24limit=500000) | `raw/colorado_business_entities_us_distribution.csv` |
| FMCSA Company Census | U.S. carrier state, status, operation, organization type, and fleet-size distributions | [U.S.-only aggregate CSV query](https://data.transportation.gov/resource/az4n-8mr2.csv?%24select=phy_country%2Cphy_state%2Cstatus_code%2Ccarrier_operation%2Cbusiness_org_desc%2Cfleetsize%2Ccount%28%2A%29+as+records&%24where=phy_country+%3D+%27US%27&%24group=phy_country%2Cphy_state%2Cstatus_code%2Ccarrier_operation%2Cbusiness_org_desc%2Cfleetsize&%24order=records+desc&%24limit=500000) | `raw/fmcsa_company_census_distribution.csv` |
| CMS NPPES weekly V2, 2026-08-10–2026-08-16 | Partial weekly Type-2 organization distribution by taxonomy, state, and year | [ZIP](https://download.cms.gov/nppes/NPPES_Data_Dissemination_081026_081626_Weekly_V2.zip) | `derived/cms_nppes_type2_weekly_distribution.csv` |
| SEC EDGAR company/ticker/exchange associations | Partial public-company legal-name, CIK, ticker, and exchange coverage | [JSON](https://www.sec.gov/files/company_tickers_exchange.json) | `raw/sec_company_tickers_exchange.json` |
| SBA PPP loans above $150,000 | Biased historical relationships among state, NAICS, jobs, business type/age, rural/urban, and loan size | [CSV](https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/public_150k_plus_240930.csv) | `derived/sba_ppp_by_state_naics_distribution.csv`; `derived/sba_ppp_business_profile_distribution.csv` |
| SBA PPP data dictionary | Definitions for the PPP aggregate tables | [XLSX](https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/ppp-data-dictionary.xlsx) | `raw/sba_ppp_data_dictionary.xlsx` |

## Capability benchmark downloads

These additions target generation capabilities that marginal business tables do not exercise well: cross-table
relationships, conditional distributions, mixed numeric/categorical/text inputs, and multi-table joins. The Census
and NHTSA source archives are public-use data, but they are still treated as sensitive staging inputs.

| Dataset | Capability supplied | Direct download | Retained local artifact |
| --- | --- | --- | --- |
| ACS PUMS North Carolina person records, 2024 1-year | Weighted age, education, employment, disability, insurance, income, and relationship conditionals | [person ZIP](https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_pnc.zip) | `derived/acs_pums_nc_person_distribution.csv`; `derived/acs_pums_nc_relationship_distribution.csv` |
| ACS PUMS North Carolina housing records, 2024 1-year | Weighted household size, tenure, bedrooms, vehicles, income, internet access, and food-stamp conditionals | [housing ZIP](https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_hnc.zip) | `derived/acs_pums_nc_household_distribution.csv`; `derived/acs_pums_nc_relationship_distribution.csv` |
| NHTSA complaints received 2020–2024 | Vehicle/component relationships, incident profiles, high-frequency language, and narrative lengths | [complaint ZIP](https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2020-2024.zip) | Four CSVs prefixed `derived/nhtsa_` |
| USDA FoodData Central Foundation Foods, 2026-04-30 | Foods, nutrients, portions, samples, and analytical-method relations | [Foundation Foods CSV ZIP](https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_csv_2026-04-30.zip) | `raw/usda_fooddata_foundation_2026-04.zip`; `derived/usda_fooddata_foundation_nutrient_statistics.csv` |

ACS processing keeps only occupied ordinary housing units, converts values to coarse categories, joins person and
household rows in memory, suppresses cells with fewer than 20 sample records, and removes serial numbers, PUMAs,
replicate weights, allocation flags, and both source archives. Use the [ACS PUMS documentation](https://www.census.gov/programs-surveys/acs/microdata/documentation.html)
and comply with the Census [no-reidentification terms](https://www.census.gov/data/developers/about/terms-of-service.html)
when refreshing or extending this source.

The NHTSA parser follows the official [complaint field layout](https://static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt). It
never selects city/state, VIN, dealer, or vehicle-operator fields; it suppresses structured cells below 20 records,
keeps only unigrams present in at least 500 distinct complaints and 50-word length bands, then deletes IDs, text,
token order, and the source archive.

FoodData Central is non-person reference data, so its official relational ZIP is retained. The audit verifies required
tables, CRCs, and foreign keys. The 2026-04-30 publisher archive has 33 unresolved nutrient references (0.019%) and 273
portion-to-food references (2.493%); both remain explicit quality warnings below the 5% hard-failure threshold. The
derived nutrient table uses valid inner joins and category/nutrient cells with at least five observations.

## Official gap examples

| Requested category | Official source | Generated privacy-safe example |
| --- | --- | --- |
| Federal contractors | [USAspending award-search API](https://api.usaspending.gov/api/v2/search/spending_by_award/); [SAM.gov Public Entity Extract](https://sam.gov/data-services/Entity%20Management/Public%20Extract) | `examples/usaspending_contract_awards_fy2025.csv` |
| Public records | [U.S. Courts Table F-2 XLSX](https://www.uscourts.gov/sites/default/files/document/stfj_f2_630.2026.xlsx) | `examples/uscourts_bankruptcy_f2_2026_06.csv` |

## Privacy-safe realism calibration

These sources improve component-level realism without retaining person/address pairs or narrative rows:

| Dataset | Calibration use | Direct download | Retained artifact |
| --- | --- | --- | --- |
| Census 2010 surnames | Weighted surnames | [ZIP](https://www2.census.gov/topics/genealogy/2010surnames/names.zip) | `derived/census_surname_distribution.csv` |
| NYC DOHMH Popular Baby Names | Weighted given names with explicit NYC bias | [CSV API](https://data.cityofnewyork.us/resource/25th-nujf.csv?%24limit=50000) | `derived/nyc_given_name_distribution.csv` |
| USPS Publication 28 Appendix C1 | Valid standardized street suffixes | [HTML](https://pe.usps.com/text/pub28/28apc_002.htm) | `derived/usps_street_suffix_reference.csv` |
| Census TIGER/Line 2025 roads, six-county sample | Independent road-name and suffix frequencies | [Directory](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/) | `derived/tiger_street_name_distribution.csv`; `derived/tiger_street_suffix_distribution.csv` |
| SEC company/ticker associations | High-frequency business-name tokens | [JSON](https://www.sec.gov/files/company_tickers_exchange.json) | `derived/sec_business_name_token_distribution.csv` |
| CFPB Consumer Complaint Database | High-document-frequency unigram and narrative-length distributions | [CSV ZIP](https://files.consumerfinance.gov/ccdb/complaints.csv.zip) | `derived/cfpb_narrative_token_distribution.csv`; `derived/cfpb_narrative_length_distribution.csv` |

The CFPB publisher releases a narrative only after the consumer opts in and the Bureau removes personal information.
The local transform adds another minimization layer: it retains only unigrams seen in at least 100 narratives and
coarse length bands, then deletes the complaint archive. It never retains text, phrases, token order, complaint IDs,
companies, or locations.

TIGER road geometry and road-name/suffix pairings are discarded. Synthetic addresses independently recombine a road
base and suffix with a valid ZIP/city/state row. Synthetic person names independently recombine given and surname
frequencies. Such recombinations can still coincidentally equal real-world values, so outputs must stay labeled
synthetic and must not be used for contact or identity resolution.

SSA's broader [national names ZIP](https://www.ssa.gov/oact/babynames/limits.html) was also evaluated: SSA suppresses
geographic cells below five occurrences. The official file remains an optional source because its Akamai endpoint
returned HTTP 403 to the reproducible downloader on this workstation; the pipeline does not silently substitute an
unofficial mirror.

Paths in these tables are relative to `datasets/public-data/` when they begin with `raw/` or `derived/`.

## Coverage and use notes

- Use CBP, ABS, NES, BDS, and QCEW first. Together they support realistic conditional relationships such as
  `industry → employee band → payroll/receipts → geography → business size`.
- Use NAICS/SIC files as validation dictionaries, not only as labels.
- Gazetteer files validate city/state/county/ZCTA combinations and supply representative coordinates. They are not
  street-address datasets.
- Iowa and Colorado outputs contain only grouped U.S. statistics. Registered-agent names, tax/business numbers,
  streets, and postal codes are not retained. The Colorado query is aggregated by the publisher API before download.
- The NPPES output includes only Type-2 organizations and is a one-week incremental sample, not a complete healthcare
  population. NPIs, personal/provider names, addresses, phones, and endpoints are not retained.
- The PPP output includes only loans above $150,000. It is a historically and programmatically selected sample, not a
  representative current business register. Borrower/lender names, addresses, IDs, and demographic fields are not
  retained.
- SEC ticker associations are explicitly partial. The complete nightly EDGAR submissions archive is available as
  [`submissions.zip`](https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip), but was not included
  because it is about 1.56 GB compressed and the compact file already supplies the requested partial coverage.
- SAM.gov Public Entity Extract is available through the
  [SAM.gov Data Services page](https://sam.gov/data-services/Entity%20Management/Public%20Extract), but it is not a
  stable anonymous direct download and was therefore not added to the full bundle. A small reproducible USAspending
  contract-award example covers contractor-name/NAICS/geography relationships without UEI, DUNS, street, award ID,
  or contact fields.
- U.S. Courts Table F-2 supplies aggregate bankruptcy counts. It does not cover state-specific liens, judgments, or
  UCC filings and intentionally retains no case-level records.
- ACS PUMS is a North Carolina public-use sample, not a national population file. Use its person/household weights and
  preserve the documented geographic and sampling limitation when calibrating synthetic relationships.
- NHTSA complaints are self-reported safety records and do not represent all vehicles or incidents. Component and
  narrative distributions must not be interpreted as defect prevalence or causal evidence.
- Foundation Foods is a curated food-composition reference, not a representative sample of consumption or products.
  Publisher-side orphan relationships remain recorded by the quality audit.

## Explicit exclusions

Do not use public sources to imitate SBFE trade histories, payment performance, delinquencies, credit limits,
balances, PayNet IDs, member/account identifiers, SSNs, tax IDs, owners, guarantors, personal emails, or phone
numbers. Use approved internal aggregates, de-identified statistics, or controlled simulation for those fields.

## Reproduce or refresh

List all 35 source keys together with their official download and publisher pages, download the default 34-source
bundle, or fetch only one source:

```powershell
uv run python tools/download_public_data.py --list
uv run python tools/download_public_data.py --workers 4
uv run python tools/download_public_data.py --only census_cbp_state_2023
uv run python tools/download_public_data.py --only realism --workers 6
uv run python tools/download_public_data.py --only capability --workers 4
uv run python tools/build_realism_profile.py
uv run python tools/benchmark_realism_quality.py
uv run python tools/audit_public_data_coverage.py
uv run python tools/audit_public_data_quality.py
uv run python tools/generate_public_data_examples.py
uv run python tools/generate_public_data_examples.py --check
```

The downloader validates archive integrity, JSON/CSV readability, minimum sizes, and SHA-256 hashes. It keeps failed
or incomplete transfers as `.part` files for resumption. Privacy-sensitive sources remain in `.staging` if a
transformation fails and are removed only after every derived output succeeds.

## Validation snapshot

- 27 official aggregate/reference downloads validated.
- 21 privacy-minimized distributions retained.
- 48 manifest entries and 207.24 MiB (217,302,198 bytes) retained locally, all declaring United States scope.
- The full value audit scanned 10,787,077 rows with zero hard failures. It retained three publisher-quality warnings:
  FMCSA organization-type missingness, NYC duplicate name dimensions, and the documented FoodData relationship gaps.
- 10,933,879 local core source records across 10 source families; the coverage audit gate passed.
- 15,329,657 core source records across 11 families when U.S.-only FMCSA server-side source coverage is included.
- Aggregate input coverage: 330,340 Iowa entities with U.S. home offices; 85,185 Colorado aggregate groups
  representing 2,998,731 entities with U.S. principal addresses; 6,275 NPPES Type-2 weekly records; and 968,524 PPP
  loans above $150,000.
- No privacy-sensitive staging directory remained after successful processing.
- Example coverage: 13/13 categories, 48/48 local manifest artifacts, 2 official gap examples, 50 CSV files, 250
  rows, and zero forbidden identifier/contact columns.
