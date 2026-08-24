# Public-data examples by requested category

This catalog answers the follow-up request to find an example for every dataset category in the email
**“public data to find.”** The generated examples are deliberately small and privacy-safe: published aggregates and
reference rows are sampled directly, while registry, provider, carrier, loan, contract, and court data are reduced to
the minimum fields needed to demonstrate useful relationships.

Snapshot date: **2026-08-22**.

## Result

- **12/12 categories covered**, including privacy-safe realism calibration added after the original email scope.
- **40/40 artifacts in the downloaded source manifest covered**.
- **2 official gap examples added**: USAspending contract awards and U.S. Courts bankruptcy aggregates.
- **42 CSV example files with 210 total rows**.
- **0 forbidden identifier/contact columns** found by the verifier.

The generated, ignored local artifacts are:

- `datasets/public-data/examples/catalog.csv`: one row per example source, including official URL, local path,
  checksum, coverage note, and privacy transform.
- `datasets/public-data/examples/category-summary.csv`: one row per requested category.
- `datasets/public-data/examples/download-links.txt`: official download/query links paired with each local example.
- `datasets/public-data/examples/coverage-report.json` and `coverage-report.md`: machine-readable and readable
  verification evidence.

## Download links and local examples

| Requested category | Official download or query | Generated local examples | Coverage note |
| --- | --- | --- | --- |
| Business population and distributions | [Census CBP state ZIP](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23st.zip), [CBP county ZIP](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip), [ZBP ZIP](https://www2.census.gov/programs-surveys/cbp/datasets/2023/zbp23detail.zip), [ABS ZIP](https://www2.census.gov/programs-surveys/abs/data/2023/AB2300CSA01.zip), [NES state ZIP](https://www2.census.gov/programs-surveys/nonemployer-statistics/datasets/2022/historical-datasets/nonemp22st.zip), [NES county ZIP](https://www2.census.gov/programs-surveys/nonemployer-statistics/datasets/2022/historical-datasets/nonemp22co.zip), [BDS CSV](https://www2.census.gov/programs-surveys/bds/tables/time-series/2023/bds2023_st_fz.csv) | Seven CSVs prefixed `census_cbp_`, `census_zbp_`, `census_abs_`, `census_nes_`, and `census_bds_` | Direct aggregate examples for NAICS, firms/establishments, employees, receipts/payroll, size, births, deaths, and geography. |
| Employment and wages | [BLS QCEW 2025 ZIP](https://data.bls.gov/cew/data/files/2025/csv/2025_annual_singlefile.zip) | `bls_qcew_annual_singlefile_2025.csv` | Five unsuppressed private-sector six-digit-NAICS rows. |
| Industry validity | [NAICS TXT](https://www2.census.gov/programs-surveys/nonemployer-statistics/technical-documentation/code-lists/nes_naics22.txt), [SIC TXT](https://www2.census.gov/programs-surveys/susb/technical-documentation/sic_codes_1988_to_1997.txt) | `census_naics_2022_descriptions.csv`; `census_sic_descriptions.csv` | Official validation codes and descriptions; SIC is historical. |
| Addresses and geography | [County Gazetteer ZIP](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_counties_national.zip), [place ZIP](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip), [ZCTA ZIP](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_zcta_national.zip) | Three CSVs prefixed `census_gazetteer_` | Geography and representative coordinates only, not street addresses. |
| Business names and formation | [Iowa registry source](https://idh-be.iowa.gov/api/v1/datasets/554/rows.csv), [Corporations Canada active CSV](https://d4bf66bykfyaf.cloudfront.net/corporations-active-cbca-en.csv), [inactive/dissolved CSV](https://d4bf66bykfyaf.cloudfront.net/corporations-inactive-or-dissolved-cbca-en.csv) | Four aggregate CSVs prefixed `iowa_` and `canada_` | Entity type/status/year/geography and legal-suffix patterns; legal names, addresses, and identifiers removed. |
| Federal contractors | [USAspending award-search API](https://api.usaspending.gov/api/v2/search/spending_by_award/); [SAM.gov Public Entity Extract](https://sam.gov/data-services/Entity%20Management/Public%20Extract) | `usaspending_contract_awards_fy2025.csv` | Five public FY2025 contract-award relationships. Partial proxy for the complete SAM entity registry; no UEI, DUNS, award ID, street, or contact fields retained. |
| Public companies | [SEC ticker/exchange JSON](https://www.sec.gov/files/company_tickers_exchange.json) | `sec_company_tickers_exchange.csv` | Compact, partial company/ticker/exchange associations. |
| Historical small business | [SBA PPP data dictionary XLSX](https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/ppp-data-dictionary.xlsx), [PPP loans above $150K CSV](https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/public_150k_plus_240930.csv) | Three CSVs prefixed `sba_ppp_` | Aggregate state/NAICS/jobs and business-profile examples; historical and selection-biased. |
| Transportation | [FMCSA aggregate CSV query](https://data.transportation.gov/resource/az4n-8mr2.csv?%24select=phy_country%2Cphy_state%2Cstatus_code%2Ccarrier_operation%2Cbusiness_org_desc%2Cfleetsize%2Ccount%28%2A%29+as+records&%24group=phy_country%2Cphy_state%2Cstatus_code%2Ccarrier_operation%2Cbusiness_org_desc%2Cfleetsize&%24order=records+desc&%24limit=500000) | `fmcsa_company_census_distribution.csv` | Server-side aggregate carrier distribution without carrier identifiers. |
| Healthcare | [CMS NPPES weekly V2 ZIP](https://download.cms.gov/nppes/NPPES_Data_Dissemination_081026_081626_Weekly_V2.zip) | `cms_nppes_type2_weekly_distribution.csv` | Weekly incremental Type-2 organization aggregate; no NPI, name, address, endpoint, or phone. |
| Public records | [U.S. Courts Table F-2 XLSX](https://www.uscourts.gov/sites/default/files/document/stfj_f2_630.2026.xlsx) | `uscourts_bankruptcy_f2_2026_06.csv` | District-level business/nonbusiness bankruptcy counts only. Liens, judgments, and UCC records remain state-specific. |
| Realism calibration | [Census surnames ZIP](https://www2.census.gov/topics/genealogy/2010surnames/names.zip), [NYC baby-name API](https://data.cityofnewyork.us/resource/25th-nujf.csv?%24limit=50000), [USPS Publication 28 suffixes](https://pe.usps.com/text/pub28/28apc_002.htm), [Census TIGER/Line roads](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/), [CFPB complaints ZIP](https://files.consumerfinance.gov/ccdb/complaints.csv.zip) | Seventeen raw or aggregate examples for names, address components, business-name tokens, and narrative word/length distributions. | Independent, thresholded marginals only; road geometry, full names, exact addresses, complaint narratives, phrases, and record identifiers are discarded. |

The complete source inventory and caveats are in [Public business calibration datasets](public-data-sources.md).

## Regenerate and verify

After downloading the full bundle, generate fresh examples, including the two official network gap examples:

```powershell
uv run python tools/generate_public_data_examples.py
```

Verify the existing catalog without network access or rewriting example CSVs:

```powershell
uv run python tools/generate_public_data_examples.py --check
```

To regenerate local examples while reusing previously fetched USAspending and U.S. Courts examples:

```powershell
uv run python tools/generate_public_data_examples.py --offline
```

Generation fails closed if a source-manifest artifact lacks a sampler, a requested category has no example, a file
is empty, a checksum or row count differs, an example escapes the expected directory, or a forbidden identifier or
contact column appears.

## Privacy boundary

These examples are calibration evidence, not row-level enrichment material. Do not use public sources to imitate
SBFE trade histories, payment behavior, delinquencies, credit limits/balances, PayNet IDs, member/account IDs, SSNs,
tax IDs, owners, guarantors, personal emails, or phone numbers. Use approved internal aggregates, de-identified
statistics, or controlled simulation for those fields.
