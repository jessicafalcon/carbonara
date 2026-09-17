-- Staging: type and select the raw per-line footprints the connector produced.
-- Reads the raw source table loaded by analytics.vintages.load_raw_footprint_lines.
CREATE OR REPLACE TABLE stg_footprint_lines AS
SELECT
    vintage,
    record_id,
    material,
    CAST(quantity AS BIGINT)         AS quantity,
    CAST(weight_kg AS DOUBLE)        AS weight_kg,
    CAST(factor AS DOUBLE)           AS factor,
    CAST(mass_kg AS DOUBLE)          AS mass_kg,
    CAST(footprint_kgco2e AS DOUBLE) AS footprint_kgco2e
FROM raw_footprint_lines;
