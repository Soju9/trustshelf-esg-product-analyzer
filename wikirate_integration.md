# WikiRate + Wikidata Company Enrichment

This document explains the optional company-level enrichment layer for the Ethical Product Analyzer.

The main product score still comes from product-level evidence: Open Food Facts, Open Beauty Facts, Open Products Facts, and the label-based scoring engine. WikiRate does not replace that scoring logic. It only provides optional company-level evidence for Social, Governance, and Ethics.

## Why This Layer Exists

Open*Facts usually provides product brands, not parent companies. For example, a product may list `Nutella`, while company-level ESG data is more likely to exist under `Ferrero SpA`.

WikiRate generally stores company profiles and company-level ESG metrics. Wikidata is used as a bridge from product brand to company:

```text
Open*Facts brand
-> clean brand
-> Wikidata brand/company lookup
-> parent or owner company via P127/P749
-> WikiRate company lookup
-> selected company-level ESG metrics
-> optional Social/Governance/Ethics adjustments
```

Low-confidence or ambiguous company resolution leads to no WikiRate adjustment.

## Product-Level vs Company-Level Evidence

`label_mapping.csv` should remain product-level. It maps product labels to product scoring effects.

WikiRate enrichment should remain separate because it describes company-level evidence. A company policy or controversy should not be mixed into the product label mapping table.

The enrichment can later be integrated by applying `company_adjustments` to base product scores, but for now it is returned separately for transparency.

## Missing and Failed Data

Missing company data does not change the score.

Failed API requests, including HTTP `429 Too Many Requests`, are not interpreted as missing evidence and are not scored. The affected metric is marked as failed:

```python
{
    "classification": "failed",
    "reason": "HTTP 429 rate limit",
    "adjustment": 0
}
```

## Company Enrichment Confidence

The enrichment returns a separate `company_enrichment_confidence` score. This is not the product-level confidence score and is not merged into the final product score.

It measures how much usable company-level ESG evidence was found in WikiRate:

- `0`: low-confidence company resolution or no WikiRate company found
- `20`: company found, but no usable metrics
- `40`: one usable metric
- `60`: two to three usable metrics
- `80`: four or more usable metrics
- `100`: four or more usable metrics plus at least one strong signal

Labels are:

- `0-20`: `low`
- `40-60`: `medium`
- `80-100`: `high`

## Metric Interpretation

Positive policy evidence gives only small bonuses. A positive policy metric means disclosure or policy evidence, not proof of perfect ethical behavior.

Examples of positive policy values:

- `Yes`
- `True`
- `Available`
- `Disclosed`
- `Policy exists`
- `Statement published`

Values such as `No`, `Unknown`, `Not available`, `No data`, metric not found, or failed request are neutral.

Negative adjustments are reserved for explicit controversy-style metrics, such as:

- child labour controversy
- forced labour / modern slavery controversy
- corruption / bribery case
- severe human rights allegation
- serious discrimination case
- greenwashing / misleading sustainability claim

A negative controversy metric is treated as a controversy signal, not a legal conclusion.

## Contradiction Rule

Actions and controversies override policy statements.

If a severe controversy exists for a pillar, positive policy bonuses in that same pillar are suppressed.

```text
Human rights policy exists: Ethics +5
Forced labour controversy exists: Ethics -10
Final Ethics adjustment: -10
```

## Caps

- Maximum positive company-level adjustment per pillar: `+10`
- Maximum negative company-level adjustment per pillar: `-15`
- Final preview scores are clamped between `0` and `100`

## Output

The enrichment returns a preview object for inspection:

```python
{
    "brand": "Milka",
    "base_scores": {
        "environmental": 70,
        "social": 55,
        "governance": 50,
        "ethics": 60
    },
    "company_resolution": {
        "clean_brand": "milka",
        "wikidata_qid": "...",
        "wikidata_label": "...",
        "parent_company_name": "Mondelez International",
        "parent_company_qid": "...",
        "resolution_confidence": "high",
        "resolution_method": "wikidata_p127_or_p749"
    },
    "wikirate": {
        "company_found": True,
        "company_name": "Mondelez International",
        "company_url": "...",
        "metrics": {}
    },
    "company_adjustments": {
        "social": 0,
        "governance": 5,
        "ethics": 0
    },
    "company_enrichment_confidence": 60,
    "company_enrichment_confidence_label": "medium",
    "updated_scores_preview": {
        "environmental": 70,
        "social": 55,
        "governance": 55,
        "ethics": 60
    },
    "warnings": []
}
```

The preview should be reviewed before any future integration into the main product scoring engine.
