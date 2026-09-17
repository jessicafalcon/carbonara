# references

Versioned reference data the connector resolves against — material emission
factors (Ecobalyse / ADEME), PEFCR plausibility bands, unit and country
vocabularies. Each file is a small CSV with a **citation per row** and a version
in its name, so every referenced value stays auditable and reproducible.

`material_factors_<v>.csv` holds the climate-change emission factor (kgCO₂e/kg)
per material — a pinned in-repo snapshot so the footprint (§9) runs offline and
reproducibly. Textile fibres carry exact Ecobalyse figures: the climate-change
indicator (`cch`) for 1 kg of the fibre at its material life-cycle stage, fetched
by `scripts/fetch_factors.py` (a build-time script, token-gated behind an
Ecoinvent 3.9.1 license). Component hardware (`brass`, `metal`) is outside
Ecobalyse's textile library and carries a cited representative ADEME value. A
revision ships as a new version file (`_v2`), and the footprint records the
version it used; `_v2` here is a hypothetical polyester revision for the
version-diff demo.
