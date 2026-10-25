# pices-odis: the PICES Data Catalogue as an ODIS node

This repository turns the public records of the **PICES Data Catalogue**
(the `pices` community on Zenodo, about 3,900 metadata records migrated from
the former PICES FGDC catalogue) into a PICES-controlled directory of
[schema.org](https://schema.org/) JSON-LD files plus a `sitemap.xml`, so that
the IOC **Ocean Data and Information System (ODIS / Ocean InfoHub)** can
harvest it.

It follows the recipe Pier Luigi Buttigieg (ODIS lead) gave PICES in April
2025: extract the metadata from Zenodo, transform it to rich PICES-specific
JSON-LD, host the files on a PICES-controlled resource (GitHub Pages behind a
w3id.org redirect), expose a sitemap, and register that sitemap in ODISCat.
The JSON-LD points at the Zenodo content through `identifier`, `url`,
`sameAs` and `distribution`. Zenodo keeps hosting the records and their DOIs;
PICES controls what ODIS sees.

Status on 2026-10-25: the directory is published on GitHub Pages at
<https://pices-data.github.io/odis/>, with the sitemap at
<https://pices-data.github.io/odis/sitemap.xml> (3,922 entries), and the
weekly refresh workflow has run and committed on its own. The published
JSON-LD is licensed CC BY 4.0 and the code MIT (see [Licence](#licence)).
Still to do: the w3id redirect, the switch of the base URL to it, and the
ODISCat registration. `NEXT_STEPS.md` tracks them; the human steps at the end
of this document hold the exact text. Nothing is written to Zenodo.

## What the pipeline produces

```
Zenodo REST API  --fetch-->  data/snapshot/        raw API pages, byte for byte (not committed)
                                   |
                                 build
                                   v
                             docs/                  the publishable directory (GitHub Pages serves it)
                             +-- records/zenodo-<concept id>.jsonld   one file per record (3,920)
                             +-- catalog.jsonld      schema:DataCatalog node for the catalogue
                             +-- organization.jsonld schema:Organization node for PICES
                             +-- sitemap.xml         every file above, with <lastmod> from Zenodo
                             +-- index.html          minimal landing page (embeds the DataCatalog JSON-LD)
                             +-- .nojekyll
                                   |
                               validate
                                   v
                             reports/validation-report.json, reports/build-summary.json
```

Run of 2026-10-23 on the production community (3,920 public records):

| Step | Result | Time |
| --- | --- | --- |
| `fetch` | 157 pages, 3,920 hits, 159 requests, no errors | 461 s (paced at 2.5 s per request) |
| `build` | 3,920 files: 2,001 `Dataset`, 1,919 `Report`+`CreativeWork`; 0 skipped | 3 s |
| `sitemap` | 3,922 URLs (records + catalogue + organisation) in one `sitemap.xml` | < 1 s |
| `validate` | 3,922 files well-formed, 0 `@id` mismatches, 297,580 triples; ODIS gate passed | 16 to 38 s |

A full refresh therefore takes about 8 to 9 minutes, almost all of it waiting
politely for Zenodo.

Sample output: `docs/records/zenodo-23606271.jsonld` (a dataset with a
bounding box, collected dates and free-text rights) and
`docs/records/zenodo-23201172.jsonld` (a PICES Scientific Report whose
bounding box crosses the date line).

## Quick start

Python 3.12 is required (pinned dependencies: PyLD, rdflib, pyshacl, pytest).

```bash
cd pices-odis
uv venv --python 3.12 .venv            # or: python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

.venv/bin/pices-odis fetch             # read-only, no token; reuses cached pages, --refresh refetches
.venv/bin/pices-odis build             # writes docs/ (records, catalogue nodes, sitemap, index)
.venv/bin/pices-odis validate          # well-formedness + ODIS SHACL; exit 1 if the gate fails
.venv/bin/pices-odis all --refresh     # the four steps in one go (what CI runs)

.venv/bin/python -m pytest             # offline tests on fixtures from the snapshot
```

Every command accepts `--base-url` and `--root`; `--limit N` on `build` and
`validate` is handy for smoke tests (`--limit 10`).

### The one setting that matters: the base URL

All public URLs (`@id`, sitemap `<loc>`, cross-references) derive from a
single value, `Settings.base_url` (`src/pices_odis/config.py`):

| Phase | Base URL | How to select it |
| --- | --- | --- |
| Now (hosting decided, no redirect yet) | `https://pices-data.github.io/odis/` | default |
| After the w3id redirect is live | `https://w3id.org/pices/odis/` | `export PICES_ODIS_BASE_URL=https://w3id.org/pices/odis/` locally; repository variable `PICES_ODIS_BASE_URL` in GitHub Actions; then rebuild |

Switching the base URL changes every `@id` once. ODIS identifies resources
by `@id`, so the switch is best made **before** the sitemap is registered in
ODISCat; if it happens later, ODIS will see 3,922 "new" resources once and
drop the old ones when they leave the sitemap.

## Hosting layout

Decision (Brett, 2026-10-23): public repository **`pices-data/odis`**
(GitHub organisation `pices-data`), served by GitHub Pages at
`https://pices-data.github.io/odis/`, later fronted by
`https://w3id.org/pices/odis/`.

Pages source: **"Deploy from a branch", branch `main`, folder `/docs`**. The
Actions workflow commits the refreshed `docs/` to `main`; Pages redeploys from
that commit. The alternative (an Actions-built Pages artifact) was not chosen
because committing `docs/` keeps the published state identical to the
reviewed git state, gives a readable diff of what changed on Zenodo at every
refresh, needs only `contents: write`, and lets the raw files also be served
from `raw.githubusercontent.com` in an emergency, like the TechOceanS example
ODIS pointed to. The `.nojekyll` file stops Pages from running Jekyll over the
directory. GitHub Pages is expected to serve `.jsonld` files as
`application/ld+json`; verify after the first deploy with
`curl -I https://pices-data.github.io/odis/catalog.jsonld` (ODIS harvesters
parse the body either way, as the TechOceanS example served from
`raw.githubusercontent.com` as `text/plain` shows).

## What is committed and why

* `docs/` **is committed** (about 12 MB of JSON-LD in 3,920 small files; Git
  compresses it to a few MB). Output is deterministic, so a weekly refresh only
  changes the files whose Zenodo record changed, plus `sitemap.xml`,
  `catalog.jsonld` (its `dateModified`) and `index.html` (its refresh date).
* `data/snapshot/` **is not committed** (`.gitignore`): 46 MB of raw API
  pages whose per-record `stats` (views, downloads) change on every fetch, so
  committing it would rewrite all 157 pages weekly. It stays on the machine
  that ran `fetch`.
* `tests/fixtures/` is the committed, offline subset of the snapshot (nine
  records chosen to exercise every mapping branch, plus the community
  metadata). `scripts/extract_fixtures.py` regenerates it from a snapshot.
* `reports/` is committed so each refresh records its validation outcome.

## Licence

Decision (Brett, 2026-10-24):

* The files PICES publishes from `docs/` (the JSON-LD descriptions,
  `catalog.jsonld`, `organization.jsonld`, `sitemap.xml` and `index.html`) are
  licensed under **CC BY 4.0** (`LICENSE-DATA`). Every record file and
  `catalog.jsonld` also state it with `schema:sdLicense`, so the licence
  travels with the descriptions into ODIS. It covers PICES's descriptions
  only: each described record keeps the licence or use constraints given in
  its own `license` or `usageInfo`.
* The pipeline code is **MIT** licensed (`LICENSE`).
* `shapes/` holds the ODIS SHACL shapes, vendored unchanged from
  `iodepo/odis-arch`; neither licence covers them (see `shapes/SOURCE.md`).

## Mapping: Zenodo record to JSON-LD

Source serialization: `application/vnd.inveniordm.v1+json` (it carries the
GeoJSON locations, the rights text, EDTF dates and the publisher field that
the legacy serialization lacks). The context is
`{"@vocab": "https://schema.org/", "geosparql": "http://www.opengis.net/ont/geosparql#"}`
(inline, so no processor needs the network).

| JSON-LD | From | Notes |
| --- | --- | --- |
| `@id` | `parent.id` (concept id) | `<base>records/zenodo-<concept id>.jsonld`; stable across new versions; equals the URL the file is served at (ODIS: "@id should point to the JSON-LD file itself") |
| `@type` | `metadata.resource_type.id` | `dataset` to `Dataset`; `publication-report` to `["Report", "CreativeWork"]`; table in `mapping.py` for other types. The plain `CreativeWork` is kept beside the subtype so ODIS tooling that targets `CreativeWork` without the schema.org class hierarchy still sees the node |
| `name`, `alternateName` | `title`, `additional_titles` | |
| `description` | `description` + `additional_descriptions` of type `notes`/`other` | HTML converted to plain text, paragraphs kept. `technical-info` (catalogue-provenance boilerplate) is left out; its FGDC identifier is carried as an identifier instead |
| `abstract`, `measurementTechnique` | `additional_descriptions` of type `abstract`, `methods` | `methods` becomes `measurementTechnique` for datasets, extra description text otherwise |
| `url` | `links.self_html` | the Zenodo landing page; single value (ODIS shape: exactly one `url`) |
| `sameAs` | DOI | `https://doi.org/<doi>`; single value, as the ODIS book advises |
| `identifier` | `pids.doi`, `parent.pids.doi`, deposited file names | `PropertyValue` nodes: version DOI first (`propertyID` `https://registry.identifiers.org/registry/doi`, `value` = bare DOI, `url` = doi.org URL, `@id` = doi.org URL, as in the ODIS examples), then the concept DOI, then one `PICES-FGDC` identifier per deposited `FGDC-<n>.xml` (value `FGDC-<n>`, url = the file) |
| `keywords` | `subjects[].subject` | text keywords (array) |
| `creator`, `contributor` | `creators`, `contributors` | `Person` (name as Zenodo gives it, plus `givenName`/`familyName`, `affiliation`, ORCID as `@id`/`url`/`identifier`) or `Organization`. No e-mail addresses (Zenodo exposes none). Contributor roles (contact person, distributor) are not carried |
| `datePublished`, `dateModified`, `version` | `publication_date`, record `updated`, `version` | |
| `publisher`, `provider`, `sdPublisher` | fixed | PICES (`@id` = the PICES Organization node under the base URL, `sameAs` ROR `https://ror.org/0205jhq31`, name, url, description). Zenodo's own publisher field says "Zenodo"; that fact is stated in the catalogue description and Zenodo appears as `provider` of every deposited file |
| `sdLicense` | fixed | CC BY 4.0 (`https://creativecommons.org/licenses/by/4.0/` plus the SPDX URL), also on `catalog.jsonld`: the licence of the JSON-LD description itself. It says nothing about the described record, whose licence or constraints stay in `license`/`usageInfo` |
| `includedInDataCatalog` (datasets) / `isPartOf` (other works) | fixed | the PICES `DataCatalog` node (`catalog.jsonld`), whose `url` is the Zenodo community |
| `spatialCoverage` | `locations.features` | see below |
| `temporalCoverage` | `dates` of type `collected` | ISO 8601 `start/end`; several collected dates are enveloped into one interval; a single date stays a single date |
| `license` | `rights[]` with an `id` | URL(s): the licence URL Zenodo gives plus the SPDX URL (6 records) |
| `usageInfo` | `rights[]` without an `id` | `CreativeWork` with `name` and `text` (the FGDC use/access constraints; 3,914 records). No `license` is asserted, because none is granted |
| `distribution` (datasets) / `subjectOf` (other works) | `files.entries` | `DataDownload` / `MediaObject` with `contentUrl` (`.../api/records/<id>/files/<key>/content`), `encodingFormat`, `contentSize`, `name`, Zenodo as `provider`, and for FGDC files a description saying the deposit is descriptive metadata only. Omitted when files are restricted (1 record) |
| related identifiers | `related_identifiers` | `describes` becomes a `DataDownload`/`MediaObject` with the URL (21 records, NEAR-GOOS portal); `cites`/`references` become `citation`; `isPartOf` stays `isPartOf`; `isDescribedBy` becomes `subjectOf`; anything else (3 x `isSupplementTo`) becomes `citation` with a typed target node |
| `citation`, `funding`, `inLanguage` | `references`, `funding`, `languages` | |

### Spatial coverage

ODIS recommends OGC GeoSPARQL WKT and also accepts the classic schema.org
`Place`/`geo` shapes (its validation shapes look for `spatialCoverage/geo`).
Each record therefore gets one `Place` carrying both:

* `geo`: `GeoShape.box` ("south west north east", latitude first, as the
  ODIS dataset template says) for axis-aligned rectangles, `GeoShape.polygon`
  ("lat lon,lat lon,...", the ODIS template format) otherwise, `GeoCoordinates`
  for points; plus the ODIS template's `additionalProperty` naming WGS 84.
* `geosparql:hasGeometry` with `geosparql:asWKT` (CRS84, longitude first) and
  `geosparql:crs`.

Date line: the source pipeline split any FGDC bounding box that crosses the
date line into a part west of the line and a part east of it (two GeoJSON
polygons; 944 records). These stay one `Place` with two `GeoShape` boxes (each
labelled "part west/east of the date line") and one WKT `MULTIPOLYGON`.
Nothing is re-merged across the line, so no box ever spans the whole globe.
176 records have no location and get no `spatialCoverage`; a location that
Zenodo carries only as text would become a `Place` with a description and no
`geo` (never parsed back into coordinates).

## Validation

`pices-odis validate` checks every file three ways and writes
`reports/validation-report.json`:

1. Well-formedness: parse as JSON, expand with PyLD, load into rdflib; at
   least one triple.
2. `@id` equals the URL the file is served at under the base URL.
3. SHACL, with the shapes ODIS publishes in
   `iodepo/odis-arch/validation/SHACL/` (vendored unchanged under `shapes/`,
   provenance in `shapes/SOURCE.md`), run with pyshacl over the combined
   graph of all files, as the ODIS validation workflow does for a node:
   * `oih_search.ttl` (the shape that workflow uses) **gates**: every
     record, the catalogue and the organisation must have an IRI `@id`, one
     `url` and a `description`.
   * `oih_dataset.ttl` and `oih_spatial0.ttl` are advisory.

Result on the full build: gate passed, 0 record-level violations. The report
also lists 44,785 `oih_search.ttl` violations on *embedded* nodes: authors
and affiliations (`Person`/`Organization` without their own IRI, `url` or
`description`) and the `usageInfo` rights statements. Zenodo does not hold
that information and inventing IRIs for people would be worse than reporting
the gap, so these are reported, not fixed. `oih_dataset.ttl` flags every
dataset's identifiers (6,002 results) because it wants `schema:identifier` to
be a literal while the ODIS book's own examples (and this project) use a
`PropertyValue` node; `oih_spatial0.ttl` warns about the 98 datasets without
a location and the catalogue's `Place` without geometry.

## Automated refresh (GitHub Actions)

`.github/workflows/refresh.yml` runs every Monday at 06:17 UTC and on manual
dispatch: fetch (`--refresh`), build, validate, upload `reports/` as an
artifact, and, only if the gate passed, commit `docs/` and `reports/` to
`main`, from where Pages redeploys. A failed gate leaves the published state
untouched. `.github/workflows/tests.yml` runs the offline tests on every push
and pull request. The first manual refresh ran on 2026-10-24 and pushed
`c452e08`: the workflow's own `permissions: contents: write` is enough, so the
repository default for workflow permissions stays read-only.

## Remaining human steps

Each step that writes to GitHub, ODISCat or a PICES page needs Brett's
approval; the exact text to use is given.

### (a) GitHub repository, Pages and refresh (done)

Done on 2026-10-23 and 2026-10-24: the public repository `pices-data/odis`
exists, owned by the PICES organisation `pices-data` (a PICES-owned home keeps
the "PICES-controlled" promise and survives staff changes); Pages serves
`main:/docs`; and the first manual run of "Refresh ODIS directory" committed
to `main` (`c452e08`).

Still open in this group:

1. When the w3id redirect works (step (b)), add the repository variable
   `PICES_ODIS_BASE_URL` = `https://w3id.org/pices/odis/` (Settings, Secrets
   and variables, Actions, Variables) and run the refresh once:

   ```bash
   gh variable set PICES_ODIS_BASE_URL --body https://w3id.org/pices/odis/ -R pices-data/odis
   gh workflow run refresh.yml -R pices-data/odis
   ```

2. Optional: set the repository Website to `https://w3id.org/pices/odis/`
   and the topics `odis`, `ocean-infohub`, `schema-org`, `json-ld`, `zenodo`,
   `pices`, `metadata`.

### (b) w3id.org pull request

w3id.org now keeps every identifier under `ids/` and checks each pull request
against its rule catalogue (<https://w3id.org/docs/rules/>). The three files
are in `w3id/ids/pices/` here, identical to commit `2fd7fad2` on the branch
`pices-odis-redirect` (local clone `/Users/brettjohnson/code/w3id-pices-odis`,
fork `Br-Johnson/w3id.org`):

* `ids/pices/README.md`: the parent namespace and its maintainers, Brett
  and the PICES Secretariat (the w3id maintainers asked for such a file when
  `/psc/` was added).
* `ids/pices/odis/.htaccess`: a 302 of every path to the same path under
  `https://pices-data.github.io/odis/`, with the contact in its comments.
* `ids/pices/odis/README.md`: what the identifier is and who maintains it.

Checked on 2026-10-24: `node tools/check/bin/w3id-check.js` reports no
problems, and the repository's test server answers 302 to the same path under
the Pages site for `/pices/odis/`, `sitemap.xml`, `catalog.jsonld`,
`organization.jsonld` and a record file, with query strings kept. On macOS the
test server runs on the system Apache with
`W3ID_ALLOW_SYSTEM_HTTPD=1 W3ID_MODDIR=/usr/libexec/apache2 W3ID_MIMETYPES=/private/etc/apache2/mime.types tools/server/bin/run-server start`.

Title:

```
pices: add /pices/odis/ redirect to the PICES ODIS JSON-LD directory
```

Body:

```
## Brief description

This adds `https://w3id.org/pices/` for the North Pacific Marine Science Organization (PICES, https://ror.org/0205jhq31), with one identifier under it for now, `https://w3id.org/pices/odis/`. I'm on the PICES Technical Committee on Data Exchange and I'm setting this up on PICES's behalf.

`/pices/odis/` redirects (302) every path to the same path under https://pices-data.github.io/odis/, which is the GitHub Pages site of pices-data/odis, a public repository in the PICES GitHub organisation. That site holds a schema.org JSON-LD description of each record in the PICES Data Catalogue (the `pices` community on Zenodo, about 3,900 records), along with the sitemap that the IOC Ocean Data and Information System (ODIS) harvests. Once the redirect is live we'll switch the files to use the w3id IRIs as their `@id`, so PICES can move the hosting later without changing the identifiers that ODIS has indexed. I've also added `ids/pices/README.md` naming the maintainers of the PICES namespace as a whole, the same way we did for `/psc/` in #6474. The PICES Secretariat (secretariat@pices.org) is the second contact in all three files, and I'll add a GitHub username for the Secretariat in a follow-up once it has an account.

I ran `node tools/check/bin/w3id-check.js`, which found no problems, and served the rules from the repository's test server (`tools/server/bin/run-server` on Apache 2.4.66). The identifier root, `sitemap.xml`, `catalog.jsonld`, `organization.jsonld` and a record file such as `records/zenodo-23606271.jsonld` all come back as a 302 to the same path on the Pages site with the query string kept, and `resolve-identifier pices/odis` ends at a 200 after one hop. The targets themselves return 200, with the sitemap served as `application/xml` and the `.jsonld` files as `application/ld+json`.
```

After the merge, verify that `curl -sI https://w3id.org/pices/odis/sitemap.xml`
returns `302` with `location: https://pices-data.github.io/odis/sitemap.xml`.
The PICES Secretariat (secretariat@pices.org) is the second contact (Brett,
2026-10-25). It has no GitHub account yet; once it has one, add the username
to both README files and the `.htaccess` contact block in a follow-up pull
request, and make the account an owner of the `pices-data` organisation.

### (c) ODISCat registration

Prerequisites, checked on 2026-10-24:

* PICES is in OceanExpert as institution 11286, "North Pacific Marine Science
  Organization", Sidney, Canada (<https://oceanexpert.org/institution/11286>).
* Brett's own OceanExpert profile does not appear in OceanExpert's public
  search. ODISCat logs in with the OceanExpert user name and password, and its
  "Submitter info" tab then shows the OceanExpert ID. If the login fails, the
  profile may still wait for OceanExpert's validation.
* ODISCat has no PICES source set up for harvesting: none of the 65 entries in
  <https://catalogue.odis.org/odis-arch-records> mentions PICES or Zenodo. It
  does hold two entries for the old TCODE catalogue, which no longer exists:
  3253 (`tcode.tinro.ru`, registered by Igor Shevchenko in 2023 and still
  marked online) and 2154 (`82.162.170.226`, offline). After registering, ask
  the ODIS team (info@odis.org) to retire them or point them to the new entry.

Register after step (a) 1, so that ODIS indexes the w3id `@id`s from the
first harvest. Log in at <https://catalogue.odis.org/>, choose "add", and fill
the three tabs. Field names follow the ODISCat help page
(<https://catalogue.odis.org/help>); "pick" marks a pick list, where the
closest offered value is the right one.

| Tab | Field | Value |
| --- | --- | --- |
| Submitter info | Role of the submitter | pick the option for an intergovernmental organisation |
| Basic description | URL | `https://zenodo.org/communities/pices/` |
| | URL of the parent project | blank |
| | Startpoint URL for ODIS-Arch | `https://w3id.org/pices/odis/sitemap.xml` |
| | Type of startpoint | Sitemap |
| | End date of the (parent) project | blank (no end date) |
| | English name | PICES Data Catalogue |
| | Original name | blank |
| | Acronym | blank (PICES uses no acronym for the catalogue) |
| | Abstract | the abstract below |
| | Citation | North Pacific Marine Science Organization (PICES). PICES Data Catalogue. Zenodo community, https://zenodo.org/communities/pices/. schema.org JSON-LD descriptions: https://w3id.org/pices/odis/ (CC BY 4.0). |
| | Email of source's technical contact | johnson@psc.org |
| | Languages of the source's interface | English |
| | Countries owning the source | the six PICES members: Canada, China, Japan, Republic of Korea, Russian Federation, United States of America |
| Detailed description | Institution | North Pacific Marine Science Organization (OceanExpert 11286) |
| | Technical notes | the notes below |
| | Countries contributing to the source | REGIONAL and the six member countries |
| | Spatial coverage | the temperate and sub-Arctic North Pacific and adjacent seas, mainly north of 30°N (the PICES Convention area) |
| | Sea regions | pick North Pacific Ocean, Bering Sea, Gulf of Alaska, Sea of Okhotsk, Sea of Japan/East Sea, Yellow Sea, East China Sea where offered |
| | Data access policy | pick the open option (each record states its own constraints) |
| | Metadata standard | Other: schema.org JSON-LD for ODIS; records migrated from FGDC CSDGM |
| | Keywords | marine ecosystems, fisheries oceanography, physical oceanography, plankton, marine birds and mammals, climate variability, North Pacific Ocean |
| | Themes | pick the ones for ecosystems, fisheries, physical oceanography and climate |
| | DOIs | blank (each record has its own Zenodo DOI) |
| | Types | pick metadata catalogue or data catalogue |
| | Machine to machine interaction technologies | Sitemap; schema.org JSON-LD; Zenodo REST API |
| | Contributing to | ODIS (Ocean InfoHub), if offered |
| | Obtained from | Zenodo, if offered |

Abstract:

```
The data catalogue of the North Pacific Marine Science Organization (PICES): about 3,900 descriptive metadata records for datasets and reports produced by PICES expert groups and their member-country partners (Canada, China, Japan, Korea, Russia, USA), migrated from the former PICES FGDC metadata catalogue. The records are hosted as a Zenodo community and carry DOIs. PICES publishes a schema.org JSON-LD description of every record for ODIS, regenerated weekly and licensed CC BY 4.0.
```

Technical notes:

```
Metadata-only catalogue: the records describe datasets and reports held elsewhere, and most carry the use and access constraints of the original FGDC record. The JSON-LD directory and its sitemap are generated every week from the Zenodo REST API by GitHub Actions in https://github.com/pices-data/odis and served from GitHub Pages behind https://w3id.org/pices/odis/. Contacts: Brett Johnson, PICES Technical Committee on Data Exchange (johnson@psc.org), and the PICES Secretariat (secretariat@pices.org).
```

ODISCat lets only the account that created an entry edit it, so the entry
stays tied to Brett's OceanExpert login; ask the ODIS team (info@odis.org)
how the Secretariat can share it once it has an OceanExpert profile.

After saving, note the record ID that ODISCat shows. The next day, check that
the entry is online, then check the ODIS dashboard
(<http://dashboard.odis.org/>) for the harvested count (expected: about 3,922
resources).

### (d) Note for the PICES Zenodo manual

```
## ODIS (Ocean Data and Information System)

The PICES Data Catalogue is connected to the IOC Ocean Data and Information System (ODIS, https://odis.org). PICES publishes a machine-readable description of every public record of the Zenodo community as schema.org JSON-LD at https://w3id.org/pices/odis/, with a sitemap that ODIS harvests. These descriptions are licensed CC BY 4.0; each record keeps its own licence or use constraints. The files are regenerated automatically every week from the Zenodo REST API, so nothing extra has to be done for a record to reach ODIS: publish it in the PICES community and it appears after the next weekly refresh and ODIS harvest. Keep titles, descriptions, keywords, locations and collected dates complete, because that is what ODIS searches. Questions: PICES Secretariat (secretariat@pices.org) or TCODE (johnson@psc.org).
```

### (e) Item for the TCODE 2027 work plan

Use after the first harvest is confirmed; fill in the month.

```
ODIS connection of the PICES Data Catalogue. Since [month] 2026 the PICES Data Catalogue (Zenodo community "pices", about 3,900 records) is a source of the IOC Ocean Data and Information System (ODIS). A repository in the PICES GitHub organisation (pices-data/odis) regenerates a schema.org JSON-LD description of every record each week and publishes them, with a sitemap, at https://w3id.org/pices/odis/ under CC BY 4.0; the source is registered in the ODIS Catalogue of Sources as "PICES Data Catalogue". Work for 2027: (1) set up a Secretariat GitHub account as co-owner of the repository and the w3id namespace, and share the ODISCat entry with the Secretariat; (2) compare the ODIS harvest count with the catalogue after each quarter; (3) add ORCID and ROR identifiers for authors and affiliations where Zenodo holds them; (4) find out which member-country data centres already contribute to ODIS.
```

## Decisions

Made:

1. Repository owner: `pices-data/odis` (2026-10-23).
2. Licence: CC BY 4.0 for the published JSON-LD, MIT for the code
   (2026-10-24; see [Licence](#licence)).
3. Base URL: switch to `https://w3id.org/pices/odis/` before the ODISCat
   registration, the order `NEXT_STEPS.md` follows.
4. OceanExpert: PICES is institution 11286; Brett reports that he has a
   profile, which ODISCat uses for the login (2026-10-24).
5. Second contact: the PICES Secretariat, secretariat@pices.org (2026-10-25).
   It becomes an owner of `pices-data` once it has a GitHub account.

Open:

6. Whether to keep contributor roles out of the JSON-LD (current) or add
   schema.org `Role` wrappers, and whether `technical-info` provenance text
   should also be published (currently left out).

## Repository layout

```
src/pices_odis/        config, zenodo (fetch), text, spatial, mapping, catalog, build, sitemap, pages, validate, cli
shapes/                vendored ODIS SHACL shapes + SOURCE.md
tests/                 pytest suite; tests/fixtures/ = offline snapshot subset
scripts/extract_fixtures.py
docs/                  the published directory (generated; committed)
reports/               build-summary.json, validation-report.json (generated; committed)
w3id/ids/pices/        the files of the perma-id/w3id.org pull request (README, .htaccess)
.github/workflows/     refresh.yml (weekly), tests.yml
data/snapshot/         raw Zenodo pages (generated; not committed)
```

Zenodo access is read-only and credential-free throughout; every request
sends `User-Agent: pices-odis/0.1 (+mailto:johnson@psc.org)` and requests
are at least 2.5 s apart (Zenodo's anonymous limit is 30 per minute).
