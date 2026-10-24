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

Status on 2026-10-23: the directory is published on GitHub Pages at
<https://pices-data.github.io/odis/>, with the sitemap at
<https://pices-data.github.io/odis/sitemap.xml> (3,922 entries). Still to do:
the w3id pull request and the ODISCat registration (see the human steps at the
end of this document). Nothing is written to Zenodo.

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
and pull request. Neither workflow is active until the repository exists on
GitHub.

## Remaining human steps

Each step needs Brett's approval; the exact text to use is given.

### (a) Create the GitHub repository and enable Pages

Owner options: the new PICES organisation `pices-data` (chosen: a
PICES-owned home keeps the "PICES-controlled" promise and survives staff
changes) or Brett's account `Br-Johnson` (fallback; would need a later
transfer and a w3id change).

1. On GitHub, `pices-data`, New repository, name **`odis`**, Public, no
   template, no README/licence/.gitignore (the local repository has them).
   Description:

   ```
   PICES Data Catalogue as an ODIS node: schema.org JSON-LD records and sitemap generated weekly from the PICES community on Zenodo for the IOC Ocean Data and Information System (ODIS / Ocean InfoHub).
   ```

   Website: `https://pices-data.github.io/odis/`. Topics: `odis`,
   `ocean-infohub`, `schema-org`, `json-ld`, `zenodo`, `pices`, `metadata`.

2. Push the local repository (Brett runs this; the agent did not):

   ```bash
   cd /Users/brettjohnson/code/pices-odis
   git remote add origin git@github.com:pices-data/odis.git
   git push -u origin main
   ```

3. Settings, Pages, Build and deployment: Source **"Deploy from a
   branch"**, Branch **`main`**, Folder **`/docs`**, Save. Wait for
   `https://pices-data.github.io/odis/` and
   `https://pices-data.github.io/odis/sitemap.xml` to answer.

4. Settings, Actions, General, Workflow permissions: **"Read and write
   permissions"** (the refresh workflow commits to `main`). Then Actions,
   "Refresh ODIS directory", Run workflow once and check the commit it makes.

5. Later, when the w3id redirect exists: Settings, Secrets and variables,
   Actions, Variables, New repository variable
   `PICES_ODIS_BASE_URL` = `https://w3id.org/pices/odis/`, then run the
   workflow once.

6. Decide the licence for this repository's code and for the JSON-LD
   (suggestion: MIT for the code, CC0 for the generated JSON-LD, which is
   metadata about PICES records). `pyproject.toml` says `TBD` until then.

### (b) w3id.org pull request

Fork `perma-id/w3id.org`, add the three files from `w3id/` at the repository
root as `pices/README.md`, `pices/odis/.htaccess`, `pices/odis/README.md`,
and open a pull request:

Title:

```
Add pices/odis: PICES Data Catalogue ODIS JSON-LD directory
```

Body:

```
This adds the namespace https://w3id.org/pices/odis/ for the North Pacific Marine Science Organization (PICES, https://ror.org/0205jhq31).

It redirects (302) every path under /pices/odis/ to https://pices-data.github.io/odis/, the GitHub Pages site of the public repository pices-data/odis. That directory holds schema.org JSON-LD descriptions of the PICES Data Catalogue (a Zenodo community) and the sitemap that the IOC Ocean Data and Information System (ODIS) harvests. The persistent identifiers let PICES move the hosting later without changing the identifiers registered with ODIS.

Contact: Brett Johnson (@Br-Johnson), johnson@psc.org, PICES Technical Committee on Data Exchange. The repository is owned by the PICES GitHub organisation pices-data.
```

Before submitting, update the maintainer line in `w3id/pices/README.md` if
the PICES Secretariat names a second contact. After the merge, verify:
`curl -I https://w3id.org/pices/odis/sitemap.xml` returns `302` with
`Location: https://pices-data.github.io/odis/sitemap.xml`.

### (c) ODISCat registration

Prerequisites: an OceanExpert ID for Brett and an OceanExpert institution
entry for PICES (https://oceanexpert.org/; allow one business day after
creation). Then at https://catalogue.odis.org/ log in, create an entry, and
fill it as below (field labels follow the ODIS book; the live form may word
them slightly differently). Register the sitemap URL **after** Pages answers
and ideally after the base-URL decision in (a) step 5.

| ODISCat field | Value |
| --- | --- |
| Name | PICES Data Catalogue |
| Acronym | PICES-DC |
| Organisation (OceanExpert institution) | North Pacific Marine Science Organization (PICES) |
| URL | https://zenodo.org/communities/pices/ |
| Description | The data catalogue of the North Pacific Marine Science Organization (PICES): about 3,900 descriptive metadata records for datasets and reports produced by PICES expert groups and their member-country partners (Canada, China, Japan, Korea, Russia, USA), migrated from the former PICES FGDC metadata catalogue. The records are hosted as a Zenodo community and carry DOIs; PICES publishes schema.org JSON-LD descriptions of every record for ODIS. |
| Type of source | Metadata catalogue (data catalogue) |
| Thematic areas / keywords | marine ecosystems, fisheries oceanography, physical oceanography, plankton, marine birds and mammals, climate variability, North Pacific Ocean, Bering Sea, Gulf of Alaska, Sea of Okhotsk, Sea of Japan/East Sea |
| Geographic coverage | North Pacific Ocean and adjacent seas (regional) |
| Languages | English |
| Access / licence | Metadata records openly accessible; each record carries the use and access constraints of the original FGDC record (no blanket licence); the JSON-LD descriptions are published by PICES |
| Contact person (OceanExpert) | Brett Johnson, PICES TCODE / WG-52 |
| Startpoint URL for ODIS-Arch | `https://pices-data.github.io/odis/sitemap.xml` now; `https://w3id.org/pices/odis/sitemap.xml` once the redirect is live |
| Type of ODIS-Arch URL | Sitemap |
| Update frequency | weekly (sitemap `changefreq` says monthly per record) |
| Relationship to other sources | Hosted by Zenodo (CERN); records minted with Zenodo DOIs |

After saving, check the entry's online status the next day, then the ODIS
dashboard (http://dashboard.odis.org/) for the harvested record count
(expected: 3,922 resources).

### (d) Note for the PICES Zenodo manual

```
## ODIS (Ocean Data and Information System)

The PICES Data Catalogue is connected to the IOC Ocean Data and Information System (ODIS, https://odis.org). PICES publishes a machine-readable description of every public record of the Zenodo community as schema.org JSON-LD at https://pices-data.github.io/odis/ (persistent address https://w3id.org/pices/odis/), with a sitemap that ODIS harvests. The files are regenerated automatically every week from the Zenodo REST API, so nothing extra has to be done for a record to reach ODIS: publish it in the PICES community and it appears in the next weekly refresh. Keep titles, descriptions, keywords, locations and collected dates complete, because that is what ODIS searches. Questions: PICES TCODE (johnson@psc.org).
```

## Decisions Brett must make

1. Confirm the repository owner (`pices-data/odis`) and run steps (a) 1 to 4.
2. Licence for the code and for the generated JSON-LD (step (a) 6).
3. When to switch the base URL to `https://w3id.org/pices/odis/`: before
   ODISCat registration (cleanest) or after (one-time re-index).
4. Who else is named as w3id and ODISCat contact for PICES (Secretariat).
5. Whether to keep contributor roles out of the JSON-LD (current) or add
   schema.org `Role` wrappers, and whether `technical-info` provenance text
   should also be published (currently left out).
6. Whether OceanExpert entries for PICES and Brett already exist.

## Repository layout

```
src/pices_odis/        config, zenodo (fetch), text, spatial, mapping, catalog, build, sitemap, pages, validate, cli
shapes/                vendored ODIS SHACL shapes + SOURCE.md
tests/                 pytest suite; tests/fixtures/ = offline snapshot subset
scripts/extract_fixtures.py
docs/                  the published directory (generated; committed)
reports/               build-summary.json, validation-report.json (generated; committed)
w3id/                  draft files for the perma-id/w3id.org pull request
.github/workflows/     refresh.yml (weekly), tests.yml
data/snapshot/         raw Zenodo pages (generated; not committed)
```

Zenodo access is read-only and credential-free throughout; every request
sends `User-Agent: pices-odis/0.1 (+mailto:johnson@psc.org)` and requests
are at least 2.5 s apart (Zenodo's anonymous limit is 30 per minute).
