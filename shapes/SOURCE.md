# Vendored ODIS SHACL shapes

These shapes were copied unchanged on 2026-10-23 from the ODIS architecture
repository, directory `validation/SHACL/` on the `master` branch:

| File | Source | Role here |
| --- | --- | --- |
| `oih_search.ttl` | https://github.com/iodepo/odis-arch/blob/master/validation/SHACL/oih_search.ttl | **Gate.** The shape the ODIS validation workflow (`workflows/actions/validation/`) runs over each node's graph: every CreativeWork/Dataset/Organization/Person… must have an IRI `@id`, a `url` (exactly one) and a `description`; a `name` is suggested (warning). |
| `oih_dataset.ttl` | https://github.com/iodepo/odis-arch/blob/master/validation/SHACL/oih_dataset.ttl | Advisory. Dataset-specific: name, url, description, identifier, keywords; every `PropertyValue` must carry `propertyID`, `url` and `value`. |
| `oih_spatial0.ttl` | https://github.com/iodepo/odis-arch/blob/master/validation/SHACL/oih_spatial0.ttl | Advisory (warnings). A Dataset should have `spatialCoverage`; a `Place` should have `geo`. |

The repository also holds `oih_searchv2.ttl` (adds a `headline` suggestion),
`oih_spatial1.ttl`, `oih_checkDownload.ttl`, `googleRequired.ttl`,
`googleRecommended.ttl` and `typesAreUIRI.ttl`. They were not vendored: they
duplicate the above, are development variants, or encode Google rich-result
preferences rather than ODIS requirements. Drop any of them into this folder
and `pices-odis validate` will run it too (every `*.ttl` here is run; only
`oih_search.ttl` decides the gate).

Known tension: `oih_dataset.ttl` requires `schema:identifier` to be a literal,
while the ODIS book's own CreativeWork/Dataset examples (and this project)
use a `PropertyValue` node for the DOI. Its results are therefore reported but
do not gate.

Licence of the shapes: see the odis-arch repository.
