-- Mart: the production-weighted catalog footprint by material × vintage — the
-- basis the v1→v2 decomposition consumes (count = mass_kg, fact = factor). The
-- factor is constant within a material × vintage, so MIN pins it deterministically.
CREATE OR REPLACE TABLE mart_footprint_by_material AS
SELECT
    vintage,
    material,
    SUM(mass_kg)          AS mass_kg,
    MIN(factor)           AS factor,
    SUM(footprint_kgco2e) AS footprint_kgco2e
FROM core_footprint_lines
GROUP BY vintage, material
ORDER BY vintage, material;
