# Next steps for pices-data

Status on 25 October 2026. The PICES Data Catalogue is published as an ODIS
node at <https://pices-data.github.io/odis/>, with its sitemap at
<https://pices-data.github.io/odis/sitemap.xml> (3,922 entries: 3,920 record
files plus the catalogue and organisation nodes). The weekly refresh has run
once by hand and committed on its own. ODIS has not harvested anything yet,
because the source is not registered in ODISCat; the registration waits for
the w3id redirect, so that ODIS indexes the persistent `@id`s from the start.
The README's "Remaining human steps" section holds the exact text for each
step below.

## Done

- [x] Create the `pices-data` GitHub organisation (Brett, 23 October 2026).
- [x] Create the public repository `pices-data/odis` and push the build.
- [x] Enable GitHub Pages from `main`, folder `/docs`.
- [x] Confirm that the live site, the sitemap and the JSON-LD files return
  HTTP 200, with `application/ld+json` for `.jsonld`.
- [x] Run the weekly refresh once by hand (24 October 2026, Actions run
  40141884876): 3,920 records fetched in 401 s, gate passed, commit `c452e08`
  pushed to `main`. The workflow's own `contents: write` permission was
  enough, so no repository setting changed. No record had changed on Zenodo
  since 23 October, so only the refresh date and the reports moved.
- [x] Choose a licence (Brett, 24 October 2026): CC BY 4.0 for the published
  JSON-LD (`LICENSE-DATA`, and `sdLicense` in every record and in
  `catalog.jsonld`), MIT for the code (`LICENSE`). The published files gain
  `sdLicense` at the next refresh after this change reaches `main`.
- [x] Open the w3id.org pull request (25 October 2026):
  <https://github.com/perma-id/w3id.org/pull/6976>. w3id.org now keeps
  identifiers under `ids/`, so the files are `ids/pices/README.md`,
  `ids/pices/odis/.htaccess` and `ids/pices/odis/README.md` (copies in
  `w3id/ids/pices/`). They pass the w3id checker and a local run of the
  w3id test server.
- [x] Name the second contact (Brett, 25 October 2026): the PICES Secretariat,
  secretariat@pices.org. It is in the w3id files and the ODISCat text.
- [x] Check the OceanExpert entries (24 October 2026): PICES is institution
  11286 (<https://oceanexpert.org/institution/11286>). Brett's profile does
  not show in the public search; ODISCat shows its ID after the login.
- [x] Check ODISCat for existing PICES sources: none is set up for harvesting,
  but entries 3253 and 2154 describe the old TCODE catalogue, which no longer
  exists.

## To do, in order

1. **Wait for the w3id merge, then check the redirect.**
   `curl -sI https://w3id.org/pices/odis/sitemap.xml` must return `302` with
   `location: https://pices-data.github.io/odis/sitemap.xml`. Answer any
   review comments on the pull request first.
2. **Switch the base URL to w3id.** Add the repository variable
   `PICES_ODIS_BASE_URL` = `https://w3id.org/pices/odis/` and run the
   refresh (commands in the README, step (a) 1). Then check that the records'
   `@id` values start with `https://w3id.org/pices/odis/`, that the gate
   passed, and that `https://w3id.org/pices/odis/sitemap.xml` lists w3id
   addresses.
3. **Register the source in ODISCat.** Log in at
   <https://catalogue.odis.org/> with the OceanExpert account, choose "add",
   and fill the three tabs with the values in the README, section (c). The
   start point is `https://w3id.org/pices/odis/sitemap.xml`, type Sitemap;
   the institution is OceanExpert 11286. Note the ODISCat record ID.
   Then ask the ODIS team (info@odis.org) to retire entries 3253 and 2154, or
   point them to the new entry.
4. **Confirm the harvest.** The day after registration, check that the
   ODISCat entry is online, then check the ODIS dashboard
   (<http://dashboard.odis.org/>) for about 3,922 harvested resources.
5. **Tell PICES users.** Add the ODIS paragraph from the README, section (d),
   to the PICES Zenodo Manual and ask the Secretariat to link it from the
   "Data" menu of the PICES website. Put the item in section (e) in the TCODE
   2027 work plan.

At any time, independent of the order above:

- **Give the Secretariat a GitHub account and ownership.** When the PICES
  Secretariat has a GitHub account, invite it as an owner of the `pices-data`
  organisation, so that the site never depends on one account, and add its
  username to the w3id files in a follow-up pull request. Ask the ODIS team
  how the Secretariat can share the ODISCat entry, which only its creator can
  edit.

## Optional improvements

- Reduce the advisory SHACL warnings: give author and affiliation nodes an
  ORCID or ROR identifier where Zenodo has one, and revisit how the DOI is
  expressed (`PropertyValue` versus a literal) with the ODIS team.
- Decide whether to publish contributor roles (`schema:Role`) and the
  `technical-info` provenance text, both left out for now.
- About 30 record descriptions contain e-mail addresses copied from the
  original FGDC records. They are already public on Zenodo, so nothing new is
  exposed, but they could be masked in a later build.
