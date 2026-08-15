"""Demo for experimental WikiRate + Wikidata company ESG enrichment.

Run from the project root:

    python workbooks/demo_wikirate_lookup.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from wikirate_lookup import enrich_brand_with_company_esg  # noqa: E402


EXAMPLE_BRANDS = [
    "Nutella",
    "Milka",
    "Nivea",
    "Ben & Jerry's",
    "Apple",
    "Dove",
    "KitKat",
    "Weleda",
    "Alnatura",
    "Storck",
]


def main() -> None:
    for brand in EXAMPLE_BRANDS:
        print(f"\n=== {brand} ===")
        result = enrich_brand_with_company_esg(brand)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
