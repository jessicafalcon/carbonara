# references

Versioned reference data the connector resolves against — material emission
factors (Ecobalyse / ADEME), PEFCR plausibility bands, unit and country
vocabularies. Each file is a small CSV with a **citation per row** and a version
in its name, so every referenced value stays auditable and reproducible.

`material_factors_<v>.csv` holds the climate-change emission factor (kgCO₂e/kg)
per material — a pinned in-repo snapshot of the Ecobalyse / ADEME Base Empreinte
material library, so the footprint (§9) runs offline and reproducibly. The values
are a labeled assumption set, not a precise claim (§15); a revision ships as a new
version file (`_v2`), and the footprint records the version it used.
