-- Core: the conformed per-line production grain the mart aggregates. Lines are
-- costed upstream; this is the modeled grain — one row per costed component line,
-- carrying its production mass and factor.
CREATE OR REPLACE TABLE core_footprint_lines AS
SELECT
    vintage,
    record_id,
    material,
    mass_kg,
    factor,
    footprint_kgco2e
FROM stg_footprint_lines
WHERE mass_kg >= 0;
