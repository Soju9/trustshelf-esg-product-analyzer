"""Experimental WikiRate/Wikidata company-level ESG enrichment.

This module is intentionally separate from the product-label scoring engine.
It resolves product brands to companies, fetches selected WikiRate evidence, and
returns optional Social/Governance/Ethics adjustments with transparent evidence.
Missing, ambiguous, or low-confidence data produces no score change.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests


BASE_URL = "https://wikirate.org"
WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
DEFAULT_TIMEOUT = 20
MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATHS = (
    MODULE_DIR / ".env",
    MODULE_DIR / "workbooks" / ".env",
    Path(".env"),
    Path("workbooks/.env"),
)
DEFAULT_USER_AGENT = "ethical-product-analyzer/1.0"
DEFAULT_BASE_SCORES = {"environmental": 70, "social": 55, "governance": 50, "ethics": 60}
WIKIRATE_REQUEST_DELAY_SECONDS = 0.35
WIKIRATE_MAX_RETRIES = 3

PILLARS = ("social", "governance", "ethics")
ZERO_ADJUSTMENTS = {"social": 0, "governance": 0, "ethics": 0}
POSITIVE_CAP = 5
NEGATIVE_CAP = -20
SEVERE_CONTROVERSY_POSITIVE_CAP = 2


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    pillar_adjustments: dict[str, int]
    keywords: tuple[str, ...]
    preferred_metric_cards: tuple[str, ...]
    metric_kind: str = "positive_policy"
    severe: bool = False


METRIC_SPECS: tuple[MetricSpec, ...] = (
    # Positive policy metrics receive small bonuses because they indicate disclosure
    # or policy existence, not guaranteed ethical performance. Negative
    # controversy-style metrics receive stronger penalties because they represent
    # higher-risk company-level signals.
    MetricSpec(
        key="human_rights_policy",
        label="Human rights policy",
        pillar_adjustments={"ethics": 2},
        keywords=("Human Rights Policy", "Human Rights"),
        preferred_metric_cards=(
            "ShareAction+Human Rights Policy Commitment",
            "World Benchmarking Alliance+Assessing Human Rights Risks and Impacts Processes (Own Operations)",
        ),
    ),
    MetricSpec(
        key="modern_slavery_statement",
        label="Modern slavery statement",
        pillar_adjustments={"ethics": 1, "governance": 1},
        keywords=("Modern Slavery Statement",),
        preferred_metric_cards=(
            "Business & Human Rights Resource Centre+Modern Slavery Statement",
            "GreenDex+Modern Slavery Statement",
        ),
    ),
    MetricSpec(
        key="anti_corruption_policy",
        label="Anti-corruption policy",
        pillar_adjustments={"governance": 2},
        keywords=("Anti-Corruption Policy", "Anti-bribery and anti-corruption", "corruption"),
        preferred_metric_cards=(
            "World Benchmarking Alliance+CSI.17.A Anti-bribery and Anti-Corruption Policy",
            "World Benchmarking Alliance+Anti-bribery and anti-corruption fundamentals",
        ),
    ),
    MetricSpec(
        key="supply_chain_transparency",
        label="Supply chain transparency",
        pillar_adjustments={"governance": 2},
        keywords=("Supply Chain Transparency", "Traceability and Supply Chain Transparency", "Supply Chain"),
        preferred_metric_cards=(
            "KnowTheChain+2.1 Traceability and Supply Chain Transparency",
            "Walk Free+MSA supply chain disclosure",
            "World Benchmarking Alliance+Assessing Human Rights Risks and Impacts Processes (Supply Chain)",
        ),
    ),
    MetricSpec(
        key="worker_grievance_mechanism",
        label="Worker grievance mechanism",
        pillar_adjustments={"social": 2, "governance": 1},
        keywords=("Worker Grievance Mechanism", "Grievance Mechanism", "Grievance"),
        preferred_metric_cards=(
            "World Benchmarking Alliance+CSI.7.A Grievance Mechanisms for Workers",
            "World Benchmarking Alliance+Supply Chain Worker Grievance Mechanism Access",
            "KnowTheChain+5.3 Grievance Mechanism",
        ),
    ),
    MetricSpec(
        key="supplier_code_of_conduct",
        label="Supplier Code of Conduct",
        pillar_adjustments={"governance": 2, "ethics": 1},
        keywords=("Supplier Code of Conduct", "Supplier Code"),
        preferred_metric_cards=(
            "KnowTheChain+1.2 Supplier Code of Conduct",
            "World Benchmarking Alliance+Supplier Code of Conduct",
        ),
    ),
    MetricSpec(
        key="freedom_of_association_collective_bargaining",
        label="Freedom of association / collective bargaining",
        pillar_adjustments={"social": 2},
        keywords=("Freedom of Association", "Collective Bargaining"),
        preferred_metric_cards=(
            "World Benchmarking Alliance+Freedom of Association and Collective Bargaining",
            "KnowTheChain+Freedom of Association",
        ),
    ),
    MetricSpec(
        key="living_wage_commitment",
        label="Living wage commitment",
        pillar_adjustments={"social": 2, "ethics": 1},
        keywords=("Living Wage", "Living Wage Commitment"),
        preferred_metric_cards=(
            "World Benchmarking Alliance+Living Wage",
            "Platform Living Wage Financials+Living Wage",
        ),
    ),
    MetricSpec(
        key="whistleblower_protection",
        label="Whistleblower protection / grievance mechanism",
        pillar_adjustments={"governance": 2},
        keywords=("Whistleblower Protection", "Whistleblowing", "Whistleblower"),
        preferred_metric_cards=(
            "World Benchmarking Alliance+Whistleblower Protection",
            "Commons+Whistleblower Protection",
        ),
    ),
    MetricSpec(
        key="diversity_inclusion_policy",
        label="Diversity / inclusion policy",
        pillar_adjustments={"social": 1},
        keywords=("Diversity Inclusion Policy", "Diversity and Inclusion", "Inclusion Policy"),
        preferred_metric_cards=(
            "World Benchmarking Alliance+Diversity and Inclusion",
            "Commons+Diversity Policy",
        ),
    ),
    MetricSpec(
        key="child_labour_controversy",
        label="Child labour controversy",
        pillar_adjustments={"ethics": -15},
        keywords=("Child Labour Controversy", "Child Labor Controversy", "Child Labour"),
        preferred_metric_cards=("Commons+Child Labour Controversy",),
        metric_kind="negative_controversy",
        severe=True,
    ),
    MetricSpec(
        key="forced_labour_modern_slavery_controversy",
        label="Forced labour / modern slavery controversy",
        pillar_adjustments={"ethics": -20},
        keywords=("Forced Labour Controversy", "Forced Labor Controversy", "Modern Slavery Controversy"),
        preferred_metric_cards=("Commons+Forced Labour Controversy",),
        metric_kind="negative_controversy",
        severe=True,
    ),
    MetricSpec(
        key="corruption_bribery_case",
        label="Corruption / bribery case",
        pillar_adjustments={"governance": -15},
        keywords=("Corruption Case", "Bribery Case", "Anti-Corruption Controversy"),
        preferred_metric_cards=("Commons+Corruption Controversy",),
        metric_kind="negative_controversy",
        severe=True,
    ),
    MetricSpec(
        key="serious_discrimination_case",
        label="Serious discrimination case",
        pillar_adjustments={"social": -10, "ethics": -5},
        keywords=("Discrimination Case", "Discrimination Controversy"),
        preferred_metric_cards=("Commons+Discrimination Controversy",),
        metric_kind="negative_controversy",
        severe=True,
    ),
    MetricSpec(
        key="severe_human_rights_allegation",
        label="Severe human rights allegation",
        pillar_adjustments={"ethics": -15},
        keywords=("Human Rights Allegation", "Human Rights Controversy"),
        preferred_metric_cards=("Commons+Human Rights Controversy",),
        metric_kind="negative_controversy",
        severe=True,
    ),
    MetricSpec(
        key="greenwashing_misleading_claim",
        label="Greenwashing / misleading sustainability claim",
        pillar_adjustments={"governance": -8},
        keywords=("Greenwashing", "Misleading Sustainability Claim"),
        preferred_metric_cards=("Commons+Greenwashing Controversy",),
        metric_kind="negative_controversy",
        severe=False,
    ),
)

METRIC_SPEC_BY_KEY = {spec.key: spec for spec in METRIC_SPECS}


def clean_brand_name(brand: str | None) -> str:
    """Normalize a brand for matching and cache keys."""

    if not brand:
        return ""
    return re.sub(r"\s+", " ", str(brand).strip().lower())


def get_first_brand(brands_field: str | list[str] | None) -> str:
    """Use the first Open*Facts brand as the primary brand."""

    if not brands_field:
        return ""
    if isinstance(brands_field, list):
        return str(brands_field[0]).strip() if brands_field else ""
    return re.split(r"[,;|]", str(brands_field), maxsplit=1)[0].strip()


@lru_cache(maxsize=1024)
def search_wikidata_entity(brand: str) -> dict[str, Any]:
    """Search Wikidata for a brand/company entity and score likely matches."""

    clean_brand = clean_brand_name(brand)
    if not clean_brand:
        return {}

    try:
        response = requests.get(
            WIKIDATA_SEARCH_URL,
            params={
                "action": "wbsearchentities",
                "search": brand.strip(),
                "language": "en",
                "format": "json",
                "limit": 8,
            },
            headers={"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return {}

    ranked = sorted(
        data.get("search", []),
        key=lambda item: _wikidata_brand_score(clean_brand, item),
        reverse=True,
    )
    if not ranked:
        return {}

    score = _wikidata_brand_score(clean_brand, ranked[0])
    if score < 45:
        return {}

    item = ranked[0]
    return {
        "qid": item.get("id"),
        "label": item.get("label"),
        "description": item.get("description"),
        "url": item.get("concepturi"),
        "match_score": score,
    }


@lru_cache(maxsize=1024)
def get_parent_company_from_wikidata(qid: str) -> dict[str, Any]:
    """Resolve a Wikidata entity to owner/parent company using P127/P749."""

    qid = str(qid or "").strip()
    if not re.fullmatch(r"Q\d+", qid):
        return {}

    query = f"""
    SELECT ?company ?companyLabel ?property ?propertyLabel WHERE {{
      VALUES ?brand {{ wd:{qid} }}
      VALUES ?property {{ wdt:P127 wdt:P749 }}
      ?brand ?property ?company .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    LIMIT 10
    """

    try:
        response = requests.get(
            WIKIDATA_SPARQL_URL,
            params={"query": query, "format": "json"},
            headers={"Accept": "application/sparql-results+json", "User-Agent": DEFAULT_USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return {}

    bindings = data.get("results", {}).get("bindings", [])
    if not bindings:
        return {}

    owned_by = [item for item in bindings if item.get("property", {}).get("value", "").endswith("/P127")]
    selected = owned_by[0] if owned_by else bindings[0]
    company_uri = selected.get("company", {}).get("value", "")

    return {
        "parent_company_name": selected.get("companyLabel", {}).get("value"),
        "parent_company_qid": company_uri.rsplit("/", 1)[-1] if company_uri else None,
        "relationship_property": selected.get("property", {}).get("value", "").rsplit("/", 1)[-1],
        "relationship_label": selected.get("propertyLabel", {}).get("value"),
    }


@lru_cache(maxsize=1024)
def resolve_brand_to_company(brand: str) -> dict[str, Any]:
    """Resolve a product brand to a company with confidence metadata."""

    original_brand = get_first_brand(brand)
    clean_brand = clean_brand_name(original_brand)
    empty = {
        "original_brand": original_brand,
        "clean_brand": clean_brand,
        "wikidata_qid": None,
        "wikidata_label": None,
        "wikidata_description": None,
        "parent_company_name": None,
        "parent_company_qid": None,
        "resolution_confidence": "low",
        "resolution_method": "unresolved",
        "reason": "Missing brand." if not clean_brand else "Ambiguous or non-company Wikidata match.",
    }
    if not clean_brand:
        return empty

    entity = search_wikidata_entity(original_brand)
    if not entity:
        return empty

    result = {
        **empty,
        "wikidata_qid": entity.get("qid"),
        "wikidata_label": entity.get("label"),
        "wikidata_description": entity.get("description"),
        "wikidata_match_score": entity.get("match_score"),
    }

    if _wikidata_entity_is_company(entity):
        result.update(
            {
                "parent_company_name": entity.get("label"),
                "parent_company_qid": entity.get("qid"),
                "resolution_confidence": "high",
                "resolution_method": "wikidata_entity_is_company",
                "reason": None,
            }
        )
        return result

    parent = get_parent_company_from_wikidata(str(entity.get("qid") or ""))
    if parent.get("parent_company_name") and _valid_company_target(parent.get("parent_company_name", "")):
        result.update(
            {
                **parent,
                "resolution_confidence": "high",
                "resolution_method": "wikidata_p127_or_p749",
                "reason": None,
            }
        )
        return result

    if parent.get("parent_company_name"):
        result.update(
            {
                **parent,
                "resolution_confidence": "low",
                "resolution_method": "rejected_wikidata_parent",
                "reason": "Resolved parent/owner is not a suitable company enrichment target.",
            }
        )
        return result

    return result


@lru_cache(maxsize=512)
def lookup_wikirate_company(company_name: str) -> dict[str, Any]:
    """Find a WikiRate company card by name/alias."""

    api_key = _get_api_key()
    if not api_key or not company_name:
        return {"company_found": False, "reason": "Missing WikiRate API key or company name."}

    client = WikiRateClient(api_key=api_key)
    try:
        company = client.find_company(company_name)
    except requests.HTTPError as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        reason = f"WikiRate company lookup failed with HTTP {status}." if status else "WikiRate company lookup failed."
        return {"company_found": False, "reason": reason}
    except (requests.RequestException, ValueError):
        return {"company_found": False, "reason": "WikiRate company lookup failed."}

    if not company:
        return {"company_found": False, "reason": "Company not found on WikiRate."}

    return {
        "company_found": True,
        "company_name": company.get("name"),
        "company_url": _redact_api_key(str(company.get("url") or "")),
        "company_card": _company_card_slug(company),
        "raw_company": company,
    }


_COMPANY_METRICS_CACHE: dict[str, dict[str, Any]] = {}


def _fetch_wikirate_metrics_uncached(company_name: str, debug: bool = False) -> dict[str, Any]:
    """Fetch selected WikiRate company metrics and classify values."""

    company = lookup_wikirate_company(company_name)
    debug_log: list[dict[str, Any]] = []

    if not company.get("company_found"):
        return {
            **company,
            "metrics": {},
            "debug": debug_log,
            "reason": company.get("reason", "WikiRate company not found."),
        }

    api_key = _get_api_key()
    client = WikiRateClient(api_key=api_key, debug=debug)
    metrics: dict[str, dict[str, Any]] = {}
    company_card = company["company_card"]

    if debug:
        print(f"WikiRate company card URL: {company['company_url']}")

    for spec in METRIC_SPECS:
        if debug:
            print(f"\nSearched metric: {spec.key}")
            print(f"  keywords: {', '.join(spec.keywords)}")

        selected_answer = None
        selected_meta = None
        answers_seen = 0
        failed_requests: list[dict[str, Any]] = []

        for keyword in spec.keywords:
            endpoint = f"/{company_card}+Answers.json"
            try:
                data, meta = client.get_json_with_meta(
                    endpoint,
                    limit=20,
                    **{"filter[metric_keyword]": keyword},
                )
                answers = _extract_items(data)
            except (requests.RequestException, ValueError) as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                meta = {
                    "url": f"{BASE_URL}{endpoint}?filter[metric_keyword]={keyword}",
                    "status_code": status,
                    "error": type(error).__name__,
                }
                answers = []
                failed_requests.append(
                    {
                        "keyword": keyword,
                        "status_code": status,
                        "reason": "HTTP 429 rate limit" if status == 429 else type(error).__name__,
                        "api_url": _redact_api_key(str(meta["url"])),
                    }
                )

            log_entry = {
                "metric_key": spec.key,
                "keyword": keyword,
                "api_url": _redact_api_key(str(meta.get("url") or "")),
                "http_status": meta.get("status_code"),
                "answers_returned": len(answers),
                "failed": bool(meta.get("error")),
                "reason": "HTTP 429 rate limit" if meta.get("status_code") == 429 else meta.get("error"),
                "cached": meta.get("cached", False),
            }
            debug_log.append(log_entry)

            if debug:
                print(f"  URL: {log_entry['api_url']}")
                print(f"  HTTP status: {log_entry['http_status']}")
                print(f"  Answers returned: {log_entry['answers_returned']}")

            answers_seen += len(answers)
            candidate_answer = _best_answer_for_spec(spec, answers)
            if candidate_answer:
                selected_answer = candidate_answer
                selected_meta = log_entry
                break

        if not selected_answer:
            if failed_requests and any(item.get("status_code") == 429 for item in failed_requests):
                metrics[spec.key] = _failed_metric_record(spec, failed_requests)
            continue

        metric_name = _answer_metric_name(selected_answer) or spec.label
        value = _metric_value(selected_answer)
        classification = classify_metric_value(metric_name, value)
        if spec.metric_kind == "negative_controversy":
            classification = _classify_controversy_value(metric_name, value)

        if classification == "neutral":
            continue

        proposed_adjustments = (
            spec.pillar_adjustments.copy()
            if classification in {"positive", "negative"}
            else {}
        )

        evidence_type = (
            "performance_controversy"
            if spec.metric_kind == "negative_controversy"
            else "policy_disclosure"
        )

        metrics[spec.key] = {
            "metric_name": metric_name,
            "value": value,
            "year": selected_answer.get("year"),
            "classification": classification,
            "metric_kind": spec.metric_kind,
            "evidence_type": evidence_type,
            "pillar": _primary_pillar(spec.pillar_adjustments),
            "pillar_adjustments": proposed_adjustments,
            "adjustment": sum(proposed_adjustments.values()),
            "source_url": _source_url(selected_answer),
            "answer_url": _answer_url(selected_answer),
            "api_url": selected_meta.get("api_url") if selected_meta else None,
            "http_status": selected_meta.get("http_status") if selected_meta else None,
            "answers_returned": selected_meta.get("answers_returned") if selected_meta else answers_seen,
            "severe": spec.severe,
            "explanation": _metric_explanation(metric_name, proposed_adjustments),
        }

        if debug:
            print(f"  Selected metric card: {metric_name}")
            print(f"  Selected year/value/classification: {selected_answer.get('year')} / {value} / {classification}")

    result = {
        "company_found": True,
        "company_name": company.get("company_name"),
        "company_url": company.get("company_url"),
        "metrics": metrics,
        "debug": debug_log,
    }
    if not metrics:
        result["reason"] = "No usable metric found."
    return result


def fetch_wikirate_metrics(company_name: str, debug: bool = False) -> dict[str, Any]:
    """Return one complete WikiRate metric bundle per canonical company."""

    cache_key = clean_brand_name(company_name)
    if not cache_key:
        return {
            "company_found": False,
            "metrics": {},
            "debug": [],
            "reason": "Missing company name.",
        }

    if not debug and cache_key in _COMPANY_METRICS_CACHE:
        return deepcopy(_COMPANY_METRICS_CACHE[cache_key])

    result = _fetch_wikirate_metrics_uncached(company_name, debug=debug)
    if not debug:
        _COMPANY_METRICS_CACHE[cache_key] = deepcopy(result)
    return result


def classify_metric_value(metric_name: str, value: Any) -> str:
    """Classify WikiRate answer values as positive, negative, neutral, or unknown."""

    if value in (None, "", [], {}):
        return "unknown"

    text = clean_brand_name(str(value))
    metric = clean_brand_name(metric_name)
    missing_values = {
        "unknown",
        "not available",
        "n a",
        "na",
        "no data",
        "not disclosed",
        "not found",
        "missing",
    }
    if text in missing_values:
        return "unknown"

    if _is_controversy_metric(metric):
        return _classify_controversy_value(metric_name, value)

    negative_policy_values = {"no", "false", "0", "0.0", "none"}
    if text in negative_policy_values:
        return "neutral"

    positive_terms = (
        "yes",
        "true",
        "available",
        "disclosed",
        "disclosure",
        "policy exists",
        "statement published",
        "published",
        "uk modern slavery act",
        "california transparency",
        "commitment",
        "geographical",
        "full",
        "partial",
    )
    if any(term in text for term in positive_terms):
        return "positive"

    if isinstance(value, (int, float)):
        return "positive" if value > 0 else "neutral"
    if _looks_numeric(text):
        return "positive" if float(text) > 0 else "neutral"

    return "unknown"


def compute_company_adjustments(metrics: dict[str, dict[str, Any]], controversies: dict | None = None) -> dict[str, Any]:
    """Compute capped company-level adjustments and evidence explanations."""

    all_metrics = dict(metrics or {})
    if controversies:
        all_metrics.update(controversies)

    positives: dict[str, list[tuple[str, int]]] = defaultdict(list)
    negatives: dict[str, list[tuple[str, int, bool]]] = defaultdict(list)
    explanations: list[str] = []
    policy_evidence: list[str] = []
    performance_evidence: list[str] = []
    warnings: list[str] = []

    for key, metric in all_metrics.items():
        classification = metric.get("classification")
        adjustments = metric.get("pillar_adjustments") or {}
        if classification not in {"positive", "negative"}:
            continue

        for pillar, adjustment in adjustments.items():
            if pillar not in PILLARS or adjustment == 0:
                continue
            label = metric.get("metric_name") or key
            if adjustment > 0 and classification == "positive":
                positives[pillar].append((label, adjustment))
            elif adjustment < 0 and classification == "negative":
                negatives[pillar].append((label, adjustment, bool(metric.get("severe"))))

    final = ZERO_ADJUSTMENTS.copy()
    severe_controversy_exists = any(
        severe
        for entries in negatives.values()
        for _, _, severe in entries
    )
    positive_cap = (
        SEVERE_CONTROVERSY_POSITIVE_CAP
        if severe_controversy_exists
        else POSITIVE_CAP
    )
    suppressed_pillars = {
        pillar for pillar, entries in negatives.items() if any(severe for _, _, severe in entries)
    }

    if severe_controversy_exists and positives:
        warnings.append(
            "Company has positive policy/disclosure evidence, but severe controversy evidence was also found. "
            f"Positive company-level adjustments are limited to +{SEVERE_CONTROVERSY_POSITIVE_CAP} per pillar."
        )

    for pillar in PILLARS:
        negative_total = max(NEGATIVE_CAP, sum(value for _, value, _ in negatives.get(pillar, [])))
        raw_positive_total = sum(value for _, value in positives.get(pillar, []))
        positive_total = 0 if pillar in suppressed_pillars else min(positive_cap, raw_positive_total)
        final[pillar] = max(NEGATIVE_CAP, min(POSITIVE_CAP, negative_total + positive_total))

        if pillar in suppressed_pillars and positives.get(pillar):
            warnings.append(
                f"Positive {pillar} policy bonuses suppressed because severe negative controversy evidence exists."
            )
        elif raw_positive_total > positive_total:
            warnings.append(
                f"Positive {pillar} policy bonuses capped at +{positive_total}."
            )

        if negative_total <= -15:
            warnings.append(
                f"Severe company-level controversy significantly reduced the {pillar.title()} score "
                f"({negative_total} adjustment before any permitted positive evidence)."
            )

    for pillar, entries in positives.items():
        if pillar in suppressed_pillars:
            continue
        for label, adjustment in entries:
            message = f"Policy/disclosure evidence: {label} found on WikiRate; supports {pillar.title()}."
            explanations.append(message)
            policy_evidence.append(message)

    for pillar, entries in negatives.items():
        for label, adjustment, _severe in entries:
            message = (
                f"Performance/controversy evidence: {label} found on WikiRate; "
                f"{pillar.title()} signal {adjustment}."
            )
            explanations.append(message)
            performance_evidence.append(message)

    if positives and negatives:
        warnings.append(
            "Mixed company evidence found: policy/disclosure signals do not cancel out controversy signals."
        )

    return {
        "adjustments": final,
        "explanations": explanations,
        "policy_evidence": policy_evidence,
        "performance_evidence": performance_evidence,
        "warnings": warnings,
    }


def compute_company_enrichment_confidence(
    resolution_confidence: str | None,
    company_found: bool,
    metrics: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Score how well-supported the company-level enrichment is."""

    if resolution_confidence == "low" or not company_found:
        score = 0
    else:
        usable_count = _usable_metric_count(metrics or {})
        has_strong_signal = _has_strong_company_signal(metrics or {})

        if usable_count == 0:
            score = 20
        elif usable_count == 1:
            score = 40
        elif usable_count <= 3:
            score = 60
        elif usable_count >= 4 and has_strong_signal:
            score = 100
        else:
            score = 80

    return {
        "company_enrichment_confidence": score,
        "company_enrichment_confidence_label": _company_enrichment_confidence_label(score),
    }


def enrich_brand_with_company_esg(
    brand: str,
    debug: bool = False,
    base_scores: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    """Full enrichment pipeline for one Open*Facts brand field."""

    first = get_first_brand(brand)
    clean = clean_brand_name(first)
    score_base = dict(base_scores or DEFAULT_BASE_SCORES)
    resolution = resolve_brand_to_company(first)
    warnings: list[str] = []

    if resolution.get("resolution_confidence") not in {"high", "medium"}:
        warnings.append("Company could not be resolved confidently. No company-level adjustment applied.")
        confidence = compute_company_enrichment_confidence(
            resolution.get("resolution_confidence", "low"),
            False,
            {},
        )
        return {
            "brand": first,
            "clean_brand": clean,
            "base_scores": score_base,
            "company_resolution": {
                "clean_brand": clean,
                "wikidata_qid": resolution.get("wikidata_qid"),
                "wikidata_label": resolution.get("wikidata_label"),
                "parent_company_name": resolution.get("parent_company_name"),
                "parent_company_qid": resolution.get("parent_company_qid"),
                "resolution_confidence": resolution.get("resolution_confidence", "low"),
                "resolution_method": resolution.get("resolution_method"),
                "reason": resolution.get("reason", "Ambiguous or non-company Wikidata match."),
            },
            "wikirate": {"company_found": False, "metrics": {}},
            "wikirate_metrics": {},
            "company_adjustments": ZERO_ADJUSTMENTS.copy(),
            "adjustments": ZERO_ADJUSTMENTS.copy(),
            "updated_scores_preview": apply_company_adjustments(score_base, ZERO_ADJUSTMENTS),
            **confidence,
            "explanations": [],
            "policy_evidence": [],
            "performance_evidence": [],
            "warnings": warnings,
        }

    company_name = resolution.get("parent_company_name") or first
    wikirate = fetch_wikirate_metrics(company_name, debug=debug)
    metrics = wikirate.get("metrics") or {}

    if not wikirate.get("company_found"):
        reason = wikirate.get("reason") or "WikiRate company page was not found."
        warnings.append(f"{reason} No company-level adjustment applied.")
    if wikirate.get("company_found") and not metrics:
        warnings.append("No usable metric found. Missing company data does not affect the score.")
    if any(metric.get("classification") == "failed" for metric in metrics.values()):
        warnings.append("Some WikiRate metric requests failed. Failed metrics were not used for scoring.")

    computed = compute_company_adjustments(metrics)
    warnings.extend(computed["warnings"])
    company_adjustments = computed["adjustments"] if metrics else ZERO_ADJUSTMENTS.copy()
    confidence = compute_company_enrichment_confidence(
        resolution.get("resolution_confidence"),
        bool(wikirate.get("company_found")),
        metrics,
    )

    return {
        "brand": first,
        "clean_brand": clean,
        "base_scores": score_base,
        "company_resolution": {
            "clean_brand": clean,
            "wikidata_qid": resolution.get("wikidata_qid"),
            "wikidata_label": resolution.get("wikidata_label"),
            "wikidata_description": resolution.get("wikidata_description"),
            "parent_company_name": resolution.get("parent_company_name"),
            "parent_company_qid": resolution.get("parent_company_qid"),
            "resolution_confidence": resolution.get("resolution_confidence"),
            "resolution_method": resolution.get("resolution_method"),
            "reason": resolution.get("reason"),
        },
        "wikirate": {
            "company_found": bool(wikirate.get("company_found")),
            "company_name": wikirate.get("company_name"),
            "company_url": wikirate.get("company_url"),
            "metrics": metrics,
            "debug": wikirate.get("debug", []),
            "reason": wikirate.get("reason"),
        },
        "wikirate_metrics": metrics,
        "company_adjustments": company_adjustments,
        "adjustments": company_adjustments,
        "updated_scores_preview": apply_company_adjustments(score_base, company_adjustments),
        **confidence,
        "explanations": computed["explanations"] if metrics else [],
        "policy_evidence": computed["policy_evidence"] if metrics else [],
        "performance_evidence": computed["performance_evidence"] if metrics else [],
        "warnings": warnings,
    }


def enrich_company_with_wikirate(
    company_name: str,
    debug: bool = False,
    base_scores: dict[str, int | float] | None = None,
) -> dict[str, Any]:
    """Enrich an already-reviewed canonical company without Wikidata resolution."""

    company_name = str(company_name or "").strip()
    score_base = dict(base_scores or DEFAULT_BASE_SCORES)
    wikirate = fetch_wikirate_metrics(company_name, debug=debug)
    metrics = wikirate.get("metrics") or {}
    warnings: list[str] = []

    if not wikirate.get("company_found"):
        reason = wikirate.get("reason") or "WikiRate company page was not found."
        warnings.append(f"{reason} No company-level adjustment applied.")
    elif not metrics:
        warnings.append("No usable metric found. Missing company data does not affect the score.")

    if any(metric.get("classification") == "failed" for metric in metrics.values()):
        warnings.append("Some WikiRate metric requests failed. Failed metrics were not used for scoring.")

    computed = compute_company_adjustments(metrics)
    warnings.extend(computed["warnings"])
    adjustments = computed["adjustments"] if metrics else ZERO_ADJUSTMENTS.copy()
    confidence = compute_company_enrichment_confidence(
        "high",
        bool(wikirate.get("company_found")),
        metrics,
    )

    return {
        "brand": company_name,
        "clean_brand": clean_brand_name(company_name),
        "base_scores": score_base,
        "company_resolution": {
            "clean_brand": clean_brand_name(company_name),
            "wikidata_qid": None,
            "wikidata_label": company_name,
            "wikidata_description": None,
            "parent_company_name": company_name,
            "parent_company_qid": None,
            "resolution_confidence": "high",
            "resolution_method": "reviewed_company_alias",
            "reason": None,
        },
        "wikirate": {
            "company_found": bool(wikirate.get("company_found")),
            "company_name": wikirate.get("company_name"),
            "company_url": wikirate.get("company_url"),
            "metrics": metrics,
            "debug": wikirate.get("debug", []),
            "reason": wikirate.get("reason"),
        },
        "wikirate_metrics": metrics,
        "company_adjustments": adjustments,
        "adjustments": adjustments,
        "updated_scores_preview": apply_company_adjustments(score_base, adjustments),
        **confidence,
        "explanations": computed["explanations"] if metrics else [],
        "policy_evidence": computed["policy_evidence"] if metrics else [],
        "performance_evidence": computed["performance_evidence"] if metrics else [],
        "warnings": warnings,
    }


def apply_company_adjustments(base_scores: dict[str, int | float], adjustments: dict[str, int | float]) -> dict[str, int | float]:
    """Apply optional company-level adjustments without mutating base scores."""

    updated = dict(base_scores)
    for pillar, adjustment in (adjustments or {}).items():
        if pillar not in updated:
            continue
        updated[pillar] = min(100, max(0, updated[pillar] + adjustment))
    return updated


class WikiRateClient:
    """Small REST client for WikiRate JSON card endpoints."""

    _REQUEST_CACHE: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[dict[str, Any] | list[Any], dict[str, Any]]] = {}
    _LAST_REQUEST_AT = 0.0

    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
        debug: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.debug = debug
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT})

    def get_json(self, endpoint: str, **params: Any) -> dict[str, Any] | list[Any]:
        data, _meta = self.get_json_with_meta(endpoint, **params)
        return data

    def get_json_with_meta(self, endpoint: str, **params: Any) -> tuple[dict[str, Any] | list[Any], dict[str, Any]]:
        endpoint = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        request_params = {"api_key": self.api_key, **params}
        cache_key = (
            endpoint,
            tuple(sorted((str(key), str(value)) for key, value in request_params.items())),
        )
        if cache_key in self._REQUEST_CACHE:
            data, meta = self._REQUEST_CACHE[cache_key]
            cached_meta = {**meta, "cached": True}
            return data, cached_meta

        response = None
        for attempt in range(WIKIRATE_MAX_RETRIES):
            wait = WIKIRATE_REQUEST_DELAY_SECONDS - (time.monotonic() - self._LAST_REQUEST_AT)
            if wait > 0:
                time.sleep(wait)

            response = self.session.get(
                f"{self.base_url}{endpoint}",
                params=request_params,
                timeout=self.timeout,
            )
            self.__class__._LAST_REQUEST_AT = time.monotonic()

            if response.status_code != 429:
                break

            retry_after = response.headers.get("retry-after")
            backoff = float(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt)
            time.sleep(backoff)

        assert response is not None
        meta = {"url": _redact_api_key(response.url), "status_code": response.status_code, "cached": False}
        response.raise_for_status()
        if "json" not in response.headers.get("content-type", "").lower():
            raise ValueError("WikiRate returned a non-JSON response")
        data = response.json()
        self._REQUEST_CACHE[cache_key] = (data, meta)
        return data, meta

    def find_company(self, company_name: str) -> dict[str, Any] | None:
        direct = self._direct_company_lookup(company_name)
        if direct:
            return direct

        for params in (
            {"limit": 50, "search": company_name},
            {"limit": 50, "query": company_name},
            {"limit": 100},
        ):
            data = self.get_json("/Company.json", **params)
            match = _match_company(company_name, _extract_items(data))
            if match:
                return match
        return None

    def _direct_company_lookup(self, company_name: str) -> dict[str, Any] | None:
        for endpoint in _company_endpoint_candidates(company_name):
            try:
                data = self.get_json(endpoint)
            except (requests.RequestException, ValueError):
                continue
            if isinstance(data, dict) and _is_company_card(data) and _company_matches_brand(company_name, data):
                return data
        return None


# Backward-compatible wrappers for older notebook cells/scripts.
def first_brand(raw_brands: str | list[str] | None) -> str:
    return get_first_brand(raw_brands)


def lookup_company_esg(brand: str | list[str] | None, debug: bool = False) -> dict[str, Any]:
    company = lookup_wikirate_company(get_first_brand(brand))
    if not company.get("company_found"):
        return {"brand": get_first_brand(brand), "company_found": False, "metrics": {}, "adjustments": {}}
    metrics_result = fetch_wikirate_metrics(company["company_name"], debug=debug)
    computed = compute_company_adjustments(metrics_result.get("metrics", {}))
    return {
        "brand": get_first_brand(brand),
        "company_found": True,
        "company_name": metrics_result.get("company_name"),
        "company_url": metrics_result.get("company_url"),
        "metrics": metrics_result.get("metrics", {}),
        "metric_details": metrics_result.get("metrics", {}),
        "adjustments": computed["adjustments"],
        "reason": metrics_result.get("reason"),
    }


def enrich_brand_with_wikirate(brand: str, debug: bool = False) -> dict[str, Any]:
    return enrich_brand_with_company_esg(brand, debug=debug)


def _get_api_key() -> str:
    env_key = os.getenv("WIKIRATE_API_KEY", "").strip()
    if env_key:
        return env_key

    for env_path in DEFAULT_ENV_PATHS:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "WIKIRATE_API_KEY":
                return value.strip().strip('"').strip("'")
    return ""


def _extract_items(data: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("items", "answers", "companies", "results", "cards"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _wikidata_brand_score(clean_brand: str, item: dict[str, Any]) -> int:
    label = item.get("label", "")
    aliases = item.get("aliases", []) or []
    description = item.get("description", "")
    clean_label = clean_brand_name(label)
    clean_aliases = {clean_brand_name(alias) for alias in aliases}
    haystack = clean_brand_name(" ".join([label, description, *aliases]))

    score = 0
    if clean_label == clean_brand:
        score += 45
    elif clean_brand and clean_brand in clean_label:
        score += 20
    if clean_brand in clean_aliases:
        score += 35

    positive_terms = (
        "brand",
        "company",
        "corporation",
        "manufacturer",
        "product",
        "chocolate",
        "confectionery",
        "cosmetics",
        "skin care",
        "food",
        "supermarket",
        "multinational",
        "enterprise",
    )
    negative_terms = (
        "painting",
        "artwork",
        "work of art",
        "fruit",
        "person",
        "given name",
        "family name",
        "surname",
        "painter",
        "artist",
        "actress",
        "actor",
        "society",
        "movement",
        "concept",
        "religion",
        "nightclub",
        "operating system",
        "software",
        "commune",
        "album",
        "song",
        "film",
    )
    score += sum(12 for term in positive_terms if term in haystack)
    score -= sum(30 for term in negative_terms if term in haystack)
    return score


def _wikidata_entity_is_company(entity: dict[str, Any]) -> bool:
    description = clean_brand_name(entity.get("description", ""))
    company_terms = (
        "company",
        "corporation",
        "manufacturer",
        "supermarket",
        "enterprise",
        "business",
        "retailer",
        "organization",
        "organisation",
    )
    non_company_terms = (
        "brand of",
        "product brand",
        "chocolate",
        "cosmetics brand",
        "skin care brand",
        "painting",
        "artwork",
        "person",
        "society",
        "movement",
        "concept",
    )
    return any(term in description for term in company_terms) and not any(term in description for term in non_company_terms)


def _valid_company_target(name: str) -> bool:
    normalized = clean_brand_name(name)
    if not normalized:
        return False
    blocked_terms = (
        "society",
        "association",
        "movement",
        "religion",
        "philosophy",
        "concept",
        "painting",
        "artwork",
        "museum",
        "person",
        "family",
    )
    return not any(term in normalized for term in blocked_terms)


def _match_company(name: str, companies: list[dict[str, Any]]) -> dict[str, Any] | None:
    exact = [company for company in companies if _company_matches_brand(name, company)]
    if exact:
        return exact[0]
    normalized = _normalize_company_name(name)
    for company in companies:
        candidate_names = _company_name_candidates(company)
        if normalized and any(
            normalized in _normalize_company_name(candidate)
            or _normalize_company_name(candidate) in normalized
            for candidate in candidate_names
            if _normalize_company_name(candidate)
        ):
            return company
    return None


def _company_matches_brand(name: str, company: dict[str, Any]) -> bool:
    normalized = _normalize_company_name(name)
    return normalized in {
        _normalize_company_name(candidate)
        for candidate in _company_name_candidates(company)
    }


def _company_name_candidates(company: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("name", "title"):
        value = company.get(key)
        if isinstance(value, str):
            names.append(value)
    aliases = company.get("alias") or company.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    names.extend(alias for alias in aliases if isinstance(alias, str))
    url = company.get("url")
    if isinstance(url, str):
        stem = Path(urlparse(url).path).stem.replace("_", " ")
        if stem:
            names.append(stem)
    return list(dict.fromkeys(item.strip() for item in names if item.strip()))


def _is_company_card(data: dict[str, Any]) -> bool:
    card_type = data.get("type")
    if isinstance(card_type, dict):
        return card_type.get("name") == "Company" or card_type.get("type") == "Company"
    return card_type == "Company"


def _company_endpoint_candidates(company_name: str) -> list[str]:
    slug = _card_slug(company_name)
    compact = _card_slug(_normalize_company_name(company_name))
    candidates = [f"/{slug}.json"]
    if compact and compact != slug:
        candidates.append(f"/{compact}.json")
    return candidates


def _company_card_slug(company: dict[str, Any]) -> str:
    url = company.get("url")
    if isinstance(url, str):
        stem = Path(urlparse(url).path).stem
        if stem:
            return stem
    return _card_slug(str(company.get("name") or ""))


def _card_slug(value: str) -> str:
    slug = re.sub(r"[^\w]+", "_", value.strip(), flags=re.UNICODE)
    return re.sub(r"_+", "_", slug).strip("_")


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _normalize_company_name(value: str) -> str:
    normalized = _normalize(value)
    legal_suffixes = {
        "ag",
        "bv",
        "co",
        "company",
        "corp",
        "corporation",
        "gmbh",
        "inc",
        "kg",
        "limited",
        "llc",
        "ltd",
        "nv",
        "plc",
        "sa",
        "sas",
        "se",
        "spa",
    }
    tokens = normalized.split()
    while tokens and tokens[-1] in legal_suffixes:
        tokens.pop()
    return " ".join(tokens)


def _best_answer_for_spec(spec: MetricSpec, answers: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [answer for answer in answers if _metric_value(answer) not in (None, "", [], {})]
    if not usable:
        return None
    preferred = {_normalize(card) for card in spec.preferred_metric_cards}

    def score(answer: dict[str, Any]) -> tuple[int, int]:
        metric_name = _answer_metric_name(answer) or ""
        normalized = _normalize(metric_name)
        year = answer.get("year") if isinstance(answer.get("year"), int) else 0
        value_class = classify_metric_value(metric_name, _metric_value(answer))
        if spec.metric_kind == "negative_controversy":
            value_class = _classify_controversy_value(metric_name, _metric_value(answer))

        metric_score = 0
        if normalized in preferred:
            metric_score += 1000
        elif any(pref and pref in normalized for pref in preferred):
            metric_score += 400
        if value_class in {"positive", "negative"}:
            metric_score += 100
        if metric_name.count("+") > 1:
            metric_score -= 50
        if "research group" in normalized:
            metric_score -= 60
        return metric_score, int(year)

    selected = max(usable, key=score)
    selected_class = classify_metric_value(_answer_metric_name(selected) or "", _metric_value(selected))
    if spec.metric_kind == "negative_controversy":
        selected_class = _classify_controversy_value(_answer_metric_name(selected) or "", _metric_value(selected))
    return selected if selected_class in {"positive", "negative", "neutral"} else None


def _metric_value(data: Any) -> Any:
    if isinstance(data, list):
        for item in data:
            value = _metric_value(item)
            if value is not None:
                return value
        return None
    if not isinstance(data, dict):
        return None
    for key in ("value", "answer", "content", "metric_value", "calculated_value"):
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    for key in ("items", "answers", "results"):
        value = data.get(key)
        if isinstance(value, list):
            nested = _metric_value(value)
            if nested is not None:
                return nested
    return None


def _answer_metric_name(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    metric = data.get("metric")
    if isinstance(metric, dict):
        value = metric.get("name") or metric.get("title")
        return str(value) if value else None
    if metric:
        return str(metric)
    name = data.get("name")
    return str(name) if name else None


def _source_url(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    sources = data.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict):
                url = source.get("url") or source.get("link") or source.get("source_url")
                if isinstance(url, str):
                    return _redact_api_key(url)
    url = data.get("url") or data.get("html_url")
    return _redact_api_key(url) if isinstance(url, str) else None


def _answer_url(data: Any) -> str | None:
    if isinstance(data, dict):
        url = data.get("answer_url") or data.get("url")
        if isinstance(url, str):
            return _redact_api_key(url)
    return None


def _primary_pillar(adjustments: dict[str, int]) -> str | None:
    if not adjustments:
        return None
    return max(adjustments.items(), key=lambda item: abs(item[1]))[0]


def _failed_metric_record(spec: MetricSpec, failures: list[dict[str, Any]]) -> dict[str, Any]:
    first_failure = failures[0] if failures else {}
    return {
        "metric_name": spec.label,
        "value": None,
        "year": None,
        "classification": "failed",
        "metric_kind": spec.metric_kind,
        "pillar": _primary_pillar(spec.pillar_adjustments),
        "pillar_adjustments": {},
        "adjustment": 0,
        "source_url": None,
        "answer_url": None,
        "api_url": first_failure.get("api_url"),
        "http_status": first_failure.get("status_code"),
        "answers_returned": 0,
        "severe": False,
        "reason": first_failure.get("reason", "Request failed"),
        "explanation": f"{spec.label} could not be checked: {first_failure.get('reason', 'request failed')}.",
        "failed_requests": failures,
    }


def _metric_explanation(metric_name: str, adjustments: dict[str, int]) -> str:
    if not adjustments:
        return f"{metric_name} found on WikiRate, but no score adjustment was applied."
    parts = []
    for pillar, adjustment in adjustments.items():
        sign = "+" if adjustment > 0 else ""
        parts.append(f"{pillar.title()} {sign}{adjustment}")
    return f"{metric_name} found on WikiRate: {', '.join(parts)}"


def _usable_metric_count(metrics: dict[str, dict[str, Any]]) -> int:
    return sum(_is_usable_metric(metric) for metric in metrics.values())


def _is_usable_metric(metric: dict[str, Any]) -> bool:
    return (
        metric.get("classification") in {"positive", "negative"}
        and metric.get("http_status") != 429
        and metric.get("value") not in (None, "", [], {})
        and metric.get("adjustment", 0) != 0
    )


def _has_strong_company_signal(metrics: dict[str, dict[str, Any]]) -> bool:
    strong_positive_count = 0
    for key, metric in metrics.items():
        if not _is_usable_metric(metric):
            continue
        if metric.get("classification") == "negative" and (
            metric.get("metric_kind") == "negative_controversy" or metric.get("severe")
        ):
            return True
        if key in {
            "human_rights_policy",
            "modern_slavery_statement",
            "anti_corruption_policy",
            "supplier_code_of_conduct",
            "worker_grievance_mechanism",
            "whistleblower_protection",
        }:
            strong_positive_count += 1
    return strong_positive_count >= 3


def _company_enrichment_confidence_label(score: int) -> str:
    if score <= 20:
        return "low"
    if score <= 60:
        return "medium"
    return "high"


def _is_controversy_metric(metric_name: str) -> bool:
    return any(term in metric_name for term in ("controversy", "case", "allegation", "lawsuit", "fine", "violation"))


def _classify_controversy_value(metric_name: str, value: Any) -> str:
    if value in (None, "", [], {}):
        return "unknown"
    text = clean_brand_name(str(value))
    if text in {"unknown", "not available", "n a", "na", "no data", "not found", "missing"}:
        return "unknown"
    if text in {"no", "false", "0", "0.0", "none"}:
        return "neutral"
    if any(term in text for term in ("yes", "true", "confirmed", "verified", "case", "allegation", "controversy", "lawsuit", "fine")):
        return "negative"
    if isinstance(value, (int, float)):
        return "negative" if value > 0 else "neutral"
    if _looks_numeric(text):
        return "negative" if float(text) > 0 else "neutral"
    return "negative" if _is_controversy_metric(clean_brand_name(metric_name)) else "unknown"


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _redact_api_key(url: str) -> str:
    return re.sub(r"api_key=[^&]+", "api_key=REDACTED", url)


def clear_caches() -> None:
    """Clear API lookup caches for reproducible notebook reruns in one kernel."""

    search_wikidata_entity.cache_clear()
    get_parent_company_from_wikidata.cache_clear()
    resolve_brand_to_company.cache_clear()
    lookup_wikirate_company.cache_clear()
    _COMPANY_METRICS_CACHE.clear()
    WikiRateClient._REQUEST_CACHE.clear()
    WikiRateClient._LAST_REQUEST_AT = 0.0
