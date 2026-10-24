# Next steps for pices-data

Status on 24 October 2026. The PICES Data Catalogue is published as an ODIS
node at <https://pices-data.github.io/odis/>, with its sitemap at
<https://pices-data.github.io/odis/sitemap.xml> (3,922 entries: 3,920 record
files plus the catalogue and organisation nodes). The repository
`pices-data/odis` was created on 23 October 2026, Pages serves `main:/docs`,
and the Tests workflow passes. ODIS has not harvested anything yet, because
the source is not registered in ODISCat. The README's "Remaining human steps"
section holds the exact text for each step below.

## Done

- [x] Create the `pices-data` GitHub organisation (Brett, 23 October 2026).
- [x] Create the public repository `pices-data/odis` and push the build.
- [x] Enable GitHub Pages from `main`, folder `/docs`.
- [x] Confirm that the live site, the sitemap and the JSON-LD files return
  HTTP 200, with `application/ld+json` for `.jsonld`.

## To do, in order

1. **Run the weekly refresh once by hand.** In Actions, run "Refresh ODIS
   directory" and check the commit it makes to `main`. The workflow asks for
   `contents: write`; if the run cannot push, set Settings › Actions ›
   General › Workflow permissions to "Read and write permissions" and run it
   again. After that, it runs every Monday at 06:17 UTC.
2. **Choose a licence.** The repository has none yet and `pyproject.toml`
   says `TBD`. The suggestion is MIT for the code and CC0 for the generated
   JSON-LD, which is metadata about PICES records. This is a PICES decision.
3. **Name a second maintainer.** Add a PICES Secretariat or TCODE member as
   an owner of the `pices-data` organisation, so that the site never depends
   on one account. The same person should be the second contact in the w3id
   and ODISCat entries.
4. **Open the w3id.org pull request.** Fork `perma-id/w3id.org`, add the
   files in `w3id/pices/`, and open the pull request with the title and body
   in the README, section (b). After it is merged, check that
   `curl -I https://w3id.org/pices/odis/sitemap.xml` returns a 302 to
   `https://pices-data.github.io/odis/sitemap.xml`.
5. **Switch the base URL to w3id.** Once the redirect works, add the
   repository variable `PICES_ODIS_BASE_URL` = `https://w3id.org/pices/odis/`
   and run the refresh, so that every record's `@id` uses the persistent
   address. Doing this before step 6 avoids ODIS indexing the records twice.
6. **Register the source in ODISCat.** This needs an OceanExpert ID for the
   contact and an OceanExpert institution entry for PICES; allow a day for
   new entries. Then create the ODISCat entry at
   <https://catalogue.odis.org/> with the field values in the README,
   section (c). The start-point URL is the sitemap: the w3id address if
   step 5 is done, otherwise the GitHub Pages address.
7. **Confirm the harvest.** The day after registration, check that the
   ODISCat entry is online, then check the ODIS dashboard
   (<http://dashboard.odis.org/>) for about 3,922 harvested resources.
8. **Tell PICES users.** Add the ODIS paragraph from the README, section (d),
   to the PICES Zenodo Manual and the "Data" menu on the PICES website, and
   report the connection to TCODE as the 2027 workplan item on ODIS.

## Optional improvements

- Reduce the advisory SHACL warnings: give author and affiliation nodes an
  ORCID or ROR identifier where Zenodo has one, and revisit how the DOI is
  expressed (`PropertyValue` versus a literal) with the ODIS team.
- Decide whether to publish contributor roles (`schema:Role`) and the
  `technical-info` provenance text, both left out for now.
- About 30 record descriptions contain e-mail addresses copied from the
  original FGDC records. They are already public on Zenodo, so nothing new is
  exposed, but they could be masked in a later build.
