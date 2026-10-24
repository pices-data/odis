"""pices_odis: build the PICES Data Catalogue node for IOC ODIS.

Purpose
    Turn the public records of the PICES community on Zenodo into one
    schema.org JSON-LD file per record, plus an Organization node, a
    DataCatalog node, a sitemap.xml and a validation report, so that ODIS
    (Ocean Data and Information System / Ocean InfoHub) can harvest a
    PICES-controlled description of the catalogue.

Invariants
    * The pipeline is read-only towards Zenodo and never uses credentials.
    * Every public URL in the output derives from one configurable base URL
      (``Settings.base_url``), because hosting is not decided yet.
    * Output files are deterministic for a given snapshot: no generation
      timestamps inside record files, so a refresh only changes what Zenodo
      changed.

Assumptions
    * Python 3.12; dependencies pinned in pyproject.toml / requirements.txt.
"""

__version__ = "0.1.0"
