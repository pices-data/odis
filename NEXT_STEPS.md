# Next steps for pices-data

Status on 26 October 2026. The PICES Data Catalogue is published as an ODIS
node at its persistent address <https://w3id.org/pices/odis/>, which
redirects to the GitHub Pages copy at <https://pices-data.github.io/odis/>.
The sitemap at <https://w3id.org/pices/odis/sitemap.xml> lists 3,958 entries
(3,956 record files plus the catalogue and organisation nodes), and every
`@id` is a w3id address. The weekly refresh runs on Mondays, builds with the
w3id base URL and commits on its own. ODIS has not harvested anything yet,
because the source is not registered in ODISCat, which is now the next step.
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
  `catalog.jsonld`), MIT for the code (`LICENSE`). The published files have
  carried `sdLicense` since the refresh of 26 October 2026 (`07350bd`).
- [x] Open the w3id.org pull request (25 October 2026):
  <https://github.com/perma-id/w3id.org/pull/6976>. w3id.org now keeps
  identifiers under `ids/`, so the files are `ids/pices/README.md`,
  `ids/pices/odis/.htaccess` and `ids/pices/odis/README.md` (copies in
  `w3id/ids/pices/`). They pass the w3id checker and a local run of the
  w3id test server.
- [x] w3id.org merged the pull request (26 October 2026, 17:59 UTC).
  `https://w3id.org/pices/odis/sitemap.xml` returns `302` to
  `https://pices-data.github.io/odis/sitemap.xml`, and the folder and file
  addresses redirect the same way.
- [x] Correct the sitemap namespace to `http://www.sitemaps.org/schemas/sitemap/0.9`
  (26 October 2026). The build had written an `https://` variant, which is a
  different XML namespace, so strict sitemap parsers would have found no URLs.
- [x] Merge the two open pull requests (26 October 2026): #2, which names the
  original dataset's DOI as `about` on link records so that ODIS can join them
  (no published record changes yet, because the 21 current links are plain
  portal URLs), and #3, which corrects the sitemap namespace.
- [x] Switch the base URL to w3id (26 October 2026). The repository variable
  `PICES_ODIS_BASE_URL` is `https://w3id.org/pices/odis/`, and refresh run
  40415309368 passed the gate and committed `e23f773`. The sitemap, the
  catalogue and every record now use w3id `@id`s, and a record's w3id address
  returns `302` to GitHub Pages and then `200` as `application/ld+json`.
- [x] Name the second contact (Brett, 25 October 2026): the PICES Secretariat,
  secretariat@pices.org. It is in the w3id files and the ODISCat text.
- [x] Check the OceanExpert entries (24 October 2026): PICES is institution
  11286 (<https://oceanexpert.org/institution/11286>). Brett's profile does
  not show in the public search; ODISCat shows its ID after the login.
- [x] Check ODISCat for existing PICES sources: none is set up for harvesting,
  but entries 3253 and 2154 describe the old TCODE catalogue, which no longer
  exists.

## To do, in order

1. **Register the source in ODISCat.** Log in at
   <https://catalogue.odis.org/> with the OceanExpert account, choose "add",
   and fill the three tabs with the values in the README, section (c). The
   start point is `https://w3id.org/pices/odis/sitemap.xml`, type Sitemap;
   the institution is OceanExpert 11286. Note the ODISCat record ID.
   Then ask the ODIS team (info@odis.org) to retire entries 3253 and 2154, or
   point them to the new entry.
   Consider waiting until TCODE decides which migrated legacy records stay in
   the PICES community, because if the source is registered first, ODIS also
   harvests the roughly 500 legacy records that duplicate other ones.
2. **Confirm the harvest.** The day after registration, check that the
   ODISCat entry is online, then check the ODIS dashboard
   (<http://dashboard.odis.org/>) for about as many harvested resources as
   the sitemap lists (3,958 on 26 October 2026).
3. **Tell PICES users.** Add the ODIS paragraph from the README, section (d),
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
