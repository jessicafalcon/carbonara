"""Build-time fetch of exact Ecobalyse climate-change factors into a pinned CSV.

Lives outside ``carbonara/`` on purpose: it reads a secret token and hits the
network, which the connector package forbids. It writes
``references/material_factors_v1.csv`` — a frozen, in-repo snapshot the connector
then reads offline and reproducibly.

Ecobalyse's public data exposes only the aggregated eco-score; the climate-change
indicator (``cch``, kgCO₂e) requires an API token (an Ecoinvent 3.9.1 license
click-through). To get a *per-kg fibre* factor from the product simulator, we run
a 1 kg, single-material query with every life-cycle step disabled except the
material stage — the returned ``cch`` is the fibre production climate change per
kg, at Ecobalyse's default origin for that material.

The token is read from ``ECOBALYSE_TOKEN`` (environment or a gitignored ``.env``
at the repo root); it is used only as a request header, never printed or written.

Run ``python scripts/fetch_factors.py``. Textile fibres get exact Ecobalyse
figures; component hardware (``brass``, ``metal``) is not in Ecobalyse's textile
library and keeps a cited representative ADEME value.
"""

from __future__ import annotations

import csv
import json
import os
import pathlib
import urllib.error
import urllib.request

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_OUT = _ROOT / "references" / "material_factors_v1.csv"
_BASE = "https://ecobalyse.beta.gouv.fr"
_MATERIALS_URL = f"{_BASE}/data/textile/materials.json"
_SIM_URL = f"{_BASE}/api/textile/simulator/cch"
_SOURCE = "Ecobalyse / ADEME Base Empreinte"
_SOURCE_VERSION = "ecoinvent-3.9.1 via Ecobalyse"
#: Isolate the material (fibre) stage: disable every other life-cycle step.
_NON_MATERIAL_STEPS = ["spinning", "fabric", "ennobling", "making", "distribution", "use", "end-of-life"]

#: our canonical material -> Ecobalyse material alias (textile fibres only).
_FIBRES = {
    "cotton": "ei-coton",
    "organic cotton": "ei-coton-organic",
    "polyester": "ei-pet",
    "nylon": "ei-pa",
    "viscose": "ei-viscose",
    "elastane": "elasthane",
}
#: hardware Ecobalyse's textile library does not cover — cited representative values.
_HARDWARE = {
    "brass": 4.2,
    "metal": 3.5,
}
_ADEME = "ADEME Base Empreinte"
_ADEME_VERSION = "base-empreinte-2024"
_ADEME_REF = "metal component hardware (representative) — https://base-empreinte.ademe.fr/"
_OUTPUT_ORDER = ("cotton", "organic cotton", "polyester", "nylon", "viscose", "elastane", "brass", "metal")


def _token() -> str:
    """Read the Ecobalyse token from the env or a gitignored .env — never logged."""
    token = os.environ.get("ECOBALYSE_TOKEN", "").strip()
    if not token and (env := _ROOT / ".env").exists():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "ECOBALYSE_TOKEN":
                token = value.strip().strip('"').strip("'")
    if not token:
        raise SystemExit("ECOBALYSE_TOKEN not set — put it in .env or the environment (see the module docstring).")
    return token


def _post(url: str, body: dict, token: str) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "token": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (fixed https host)
        return json.load(response)


def _get(url: str, token: str) -> object:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "token": token})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (fixed https host)
        return json.load(response)


def _fibre_cch(material_id: str, token: str) -> float:
    """The material-stage climate change for 1 kg of one fibre (kgCO₂e/kg)."""
    body = {
        "mass": 1.0,
        "product": "tshirt",
        "materials": [{"id": material_id, "share": 1.0}],
        "disabledSteps": _NON_MATERIAL_STEPS,
    }
    return float(_post(_SIM_URL, body, token)["impacts"]["cch"])


def main() -> None:
    token = _token()
    print("fetching Ecobalyse material list …")
    materials = _get(_MATERIALS_URL, token)
    assert isinstance(materials, list)
    material_id = {m["alias"]: m["id"] for m in materials}
    name_of = {m["alias"]: m["name"] for m in materials}

    rows: dict[str, tuple[float, str, str, str]] = {}
    for material, alias in _FIBRES.items():
        try:
            cch = _fibre_cch(material_id[alias], token)
        except urllib.error.HTTPError as error:
            raise SystemExit(f"{material}: HTTP {error.code} — {error.read().decode()[:200]}") from error
        ref = f"{name_of[alias]} — climate change (cch), material stage, 1 kg, default origin — {_BASE}/"
        rows[material] = (round(cch, 4), _SOURCE, _SOURCE_VERSION, ref)
        print(f"  {material:15s} {cch:8.4f} kgCO₂e/kg  ({name_of[alias]})")

    for material, value in _HARDWARE.items():
        rows[material] = (value, _ADEME, _ADEME_VERSION, _ADEME_REF)

    with _OUT.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["material", "factor_kgco2e_per_kg", "source", "source_version", "source_ref"])
        for material in _OUTPUT_ORDER:
            writer.writerow([material, *rows[material]])
    print(f"wrote {_OUT}")


if __name__ == "__main__":
    main()
