# 1. Move Core Imports
import ast
from copy import deepcopy
import re
import time
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from pathlib import Path
from wikirate_lookup import (
    clean_brand_name,
    enrich_brand_with_company_esg,
    enrich_company_with_wikirate,
    get_first_brand,
)
from functools import lru_cache

# 2. Define Project Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "Data"
PROCESSED_DIR = BASE_DIR / "Processed"

LABEL_MAPPING_PATH = DATA_DIR / "open_products_labe_mapping_final.csv"
CONFIDENCE_MAPPING_PATH = DATA_DIR / "open_products_confidence_mapping_final.csv"

API_CACHE_TTL_SECONDS = 60 * 60
API_CACHE_MAX_ENTRIES = 256
_SEARCH_CACHE = {}
_BARCODE_CACHE = {}

# 3. Add API Configuration
HEADERS = {
    "User-Agent": "WBS-ESG-Analyzer/1.0 (student project)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}
SOURCES = {
    "food": "https://world.openfoodfacts.org",
    "beauty": "https://world.openbeautyfacts.org",
    "products": "https://world.openproductsfacts.org"
}
SOURCE_TO_DATABASE = {
    "food": "open_food_facts",
    "beauty": "open_beauty_facts",
    "products": "open_products_facts"
}

# 4. Define API Fields
USEFUL_FIELDS = [
    "code",
    "product_name",
    "generic_name",
    "brands",
    "quantity",
    "product_quantity",
    "categories",
    "categories_tags",
    "labels",
    "labels_tags",
    "ingredients_text",
    "ingredients_tags",
    "packaging",
    "packaging_tags",
    "countries",
    "countries_tags",
    "stores",
    "origins",
    "origins_tags",
    "manufacturing_places",
    "ecoscore_grade",
    "ecoscore_score",
    "image_url",
    "last_modified_t",
    "created_t"
]

FIELDS_PARAM = ",".join(USEFUL_FIELDS)

# 5. Add Generic Helpers
def read_mapping_csv(path):
    return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")

def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()

def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def normalize_tags(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [tag.strip() for tag in value.split(",")]
    return []

def parse_list_column(value):
    if isinstance(value, list):
        return value

    if pd.isna(value) or value == "":
        return []

    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, list):
            return parsed
        return []
    except Exception:
        return []

def unix_to_datetime(value):
    try:
        if pd.isna(value) or value == "":
            return None
        return datetime.fromtimestamp(int(value))
    except Exception:
        return None

def clamp(value, min_value=0, max_value=100):
    return max(min_value, min(max_value, value))


# 6. Add API Request Helper
def request_json(url, params=None, retries=5, timeout=60):
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=timeout
            )

            if response.status_code == 200:
                return response.json()

            if response.status_code in (429, 503) and attempt < retries:
                time.sleep(3 * attempt)
                continue

            return {
                "api_status": "error",
                "status_code": response.status_code,
                "url": response.url
            }

        except requests.RequestException as exc:
            if attempt < retries:
                time.sleep(3 * attempt)
                continue

            return {
                "api_status": "error",
                "status_code": None,
                "url": url,
                "error_message": str(exc)
            }


# 7. Load Scoring Resources
@lru_cache(maxsize=4)
def _load_scoring_resources_cached(label_mtime, confidence_mtime):
    label_mapping = read_mapping_csv(LABEL_MAPPING_PATH)
    confidence_mapping = read_mapping_csv(CONFIDENCE_MAPPING_PATH)

    label_mapping.columns = label_mapping.columns.str.strip()
    confidence_mapping.columns = confidence_mapping.columns.str.strip()

    required_label_columns = ["database", "label_keyword", "matched_label", "score_group"]
    required_confidence_columns = ["label_keyword", "matched_label", "score_group"]

    missing_label_columns = [
        col for col in required_label_columns
        if col not in label_mapping.columns
    ]
    missing_confidence_columns = [
        col for col in required_confidence_columns
        if col not in confidence_mapping.columns
    ]

    if missing_label_columns:
        raise ValueError(
            "Missing columns in label mapping: "
            f"{missing_label_columns}. Available columns: {label_mapping.columns.tolist()}"
        )

    if missing_confidence_columns:
        raise ValueError(
            "Missing columns in confidence mapping: "
            f"{missing_confidence_columns}. Available columns: {confidence_mapping.columns.tolist()}"
        )

    label_mapping = label_mapping.dropna(subset=required_label_columns).copy()
    confidence_mapping = confidence_mapping.dropna(subset=required_confidence_columns).copy()

    label_mapping["label_keyword_clean"] = (
        label_mapping["label_keyword"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    confidence_mapping["label_keyword_clean"] = (
        confidence_mapping["label_keyword"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    score_columns = ["environmental", "social", "governance", "ethic"]

    for col in score_columns:
        label_mapping[col] = pd.to_numeric(
            label_mapping[col],
            errors="coerce"
        ).fillna(0)

    confidence_mapping["confidence_weight"] = pd.to_numeric(
        confidence_mapping["confidence_weight"],
        errors="coerce"
    ).fillna(0)

    eco_baselines = build_eco_baselines(label_mapping)

    return label_mapping, confidence_mapping, eco_baselines


def load_scoring_resources():
    resources = _load_scoring_resources_cached(
        LABEL_MAPPING_PATH.stat().st_mtime_ns,
        CONFIDENCE_MAPPING_PATH.stat().st_mtime_ns,
    )
    label_mapping, confidence_mapping, eco_baselines = resources
    return (
        label_mapping.copy(deep=True),
        confidence_mapping.copy(deep=True),
        dict(eco_baselines),
    )


# 8. Build Eco Baselines
def eco_grade_from_matched_label(value):
    value = normalize_text(value)
    if "eco-score" not in value:
        return None

    grade_text = value.replace("eco-score", "").strip()

    if grade_text in ["a-plus", "a+", "a plus"]:
        return "a-plus"
    if grade_text in ["a", "b", "c", "d", "e", "f"]:
        return grade_text
    return None

def build_eco_baselines(label_mapping):
    eco_baseline_rows = label_mapping[
        (label_mapping["score_group"] == "eco_score")
        & (label_mapping["score_type"] == "baseline")
    ].copy()

    eco_baseline_rows["eco_grade"] = eco_baseline_rows["matched_label"].apply(
        eco_grade_from_matched_label
    )

    eco_baselines = dict(
        zip(
            eco_baseline_rows["eco_grade"],
            eco_baseline_rows["environmental"]
        )
    )

    if "a" in eco_baselines:
        eco_baselines["a-plus"] = eco_baselines["a"]

    return eco_baselines


# 9. Add Product Search
def _get_cached_api_value(cache, key):
    cached = cache.get(key)
    if not cached:
        return None

    cached_at, value = cached
    if time.monotonic() - cached_at > API_CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    return deepcopy(value)


def _store_cached_api_value(cache, key, value):
    if len(cache) >= API_CACHE_MAX_ENTRIES:
        oldest_key = min(cache, key=lambda item: cache[item][0])
        cache.pop(oldest_key, None)
    cache[key] = (time.monotonic(), deepcopy(value))


def clear_backend_caches():
    _SEARCH_CACHE.clear()
    _BARCODE_CACHE.clear()
    _load_scoring_resources_cached.cache_clear()
    _get_wikirate_enrichment_cached.cache_clear()
    _get_reviewed_company_enrichment_cached.cache_clear()


def search_from_source(source_name, query, page_size=20, page=1):
    normalized_query = " ".join(str(query).strip().lower().split())
    cache_key = (source_name, normalized_query, int(page_size), int(page))
    cached = _get_cached_api_value(_SEARCH_CACHE, cache_key)
    if cached is not None:
        return cached

    base_url = SOURCES[source_name]
    url = f"{base_url}/cgi/search.pl"

    params = {
        "search_terms": normalized_query,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": page_size,
        "page": page,
        "fields": FIELDS_PARAM,
    }

    data = request_json(url, params=params)

    if data.get("api_status") == "error":
        return []

    products = data.get("products", [])
    _store_cached_api_value(_SEARCH_CACHE, cache_key, products)
    return deepcopy(products)

# 10. Add Barcode Lookup
def extract_from_source(source_name, barcode):
    normalized_barcode = str(barcode).strip()
    cache_key = (source_name, normalized_barcode)
    cached = _get_cached_api_value(_BARCODE_CACHE, cache_key)
    if cached is not None:
        return cached

    base_url = SOURCES[source_name]
    url = f"{base_url}/api/v3/product/{normalized_barcode}"

    params = {
        "fields": FIELDS_PARAM
    }

    data = request_json(url, params=params)

    if data.get("api_status") == "error":
        return None

    product = data.get("product", {})

    if not product:
        return None

    _store_cached_api_value(_BARCODE_CACHE, cache_key, product)
    return deepcopy(product)

# 11. Transform API Product to Unified Schema
def transform_to_unified(product, source_name, retrieval_method, search_query=""):
    return {
        "source": source_name,
        "retrieval_method": retrieval_method,
        "search_query": search_query,
        "barcode": product.get("code"),
        "product_name": clean_text(product.get("product_name")),
        "generic_name": clean_text(product.get("generic_name")),
        "brand": clean_text(product.get("brands")),
        "quantity": clean_text(product.get("quantity")),
        "product_quantity": product.get("product_quantity"),
        "categories": clean_text(product.get("categories")),
        "category_tags": normalize_tags(product.get("categories_tags")),
        "labels": clean_text(product.get("labels")),
        "label_tags": normalize_tags(product.get("labels_tags")),
        "ingredients_text": clean_text(product.get("ingredients_text")),
        "ingredient_tags": normalize_tags(product.get("ingredients_tags")),
        "packaging": clean_text(product.get("packaging")),
        "packaging_tags": normalize_tags(product.get("packaging_tags")),
        "countries": clean_text(product.get("countries")),
        "country_tags": normalize_tags(product.get("countries_tags")),
        "stores": clean_text(product.get("stores")),
        "origins": clean_text(product.get("origins")),
        "origin_tags": normalize_tags(product.get("origins_tags")),
        "manufacturing_places": clean_text(product.get("manufacturing_places")),
        "ecoscore_grade": clean_text(product.get("ecoscore_grade")).lower(),
        "ecoscore_score": product.get("ecoscore_score"),
        "image_url": clean_text(product.get("image_url")),
        "created_datetime": unix_to_datetime(product.get("created_t")),
        "last_modified_datetime": unix_to_datetime(product.get("last_modified_t")),
    }

# 12. Germany Filter
GERMANY_COUNTRY_TAG = "en:germany"

def is_german_product(product):
    country_tags = normalize_tags(product.get("countries_tags"))
    return GERMANY_COUNTRY_TAG in country_tags

# For unified products:
def is_german_unified(product):
    return GERMANY_COUNTRY_TAG in product.get("country_tags", [])


# 12b. Source sanity filter
BEAUTY_KEYWORDS = {
    "shampoo", "haarshampoo", "conditioner", "hair conditioner",
    "duschgel", "shower gel", "soap", "seife", "cosmetic",
    "kosmetik", "deodorant", "toothpaste", "zahnpasta",
    "toothbrush", "zahnburste", "skin care", "skincare",
    "hair care", "haarpflege", "body care", "korperpflege",
    "reinigungsschaum", "cleansing foam", "gesichtsreinigung",
    "handcreme", "hand cream", "haartonikum", "hair tonic",
    "gesichtspflege", "facial care", "face care", "body lotion",
    "body milk", "korperlotion", "deodorant refill",
    "deo", "deo nachfuller", "deo refill",
    "scrub", "face scrub", "facial scrub", "body scrub",
    "peeling", "gesichtspeeling", "korperpeeling",
    "exfoliant", "exfoliating", "exfoliation",
    "moisturizer", "moisturiser", "moisturizing cream",
    "face cream", "facial cream", "crema viso", "idratante",
    "gel nettoyant", "cleansing gel", "reinigungsgel",
    "handseife", "flussigseife", "liquid soap",
    "antiperspirant", "anti transpirant", "roll on",
}

HEALTH_KEYWORDS = {
    "augentropfen", "eye drops", "euphrasia", "visiodoron",
    "nasenspray", "nasal spray", "hustensaft", "cough syrup",
    "arzneimittel", "medicine", "medication", "pharmacy",
    "apotheke", "wundsalbe", "heilsalbe",
}

PRODUCT_KEYWORDS = {
    "battery", "batteries", "batterie", "batterien",
    "alkaline", "knopfzelle", "power bank",
    "detergent", "laundry detergent", "waschmittel",
    "colorwaschmittel", "feinwaschmittel", "vollwaschmittel",
    "waschpulver", "weichspuler", "fabric softener",
    "haushaltschemie", "entkalker",
    "staubmagnet", "dust magnet", "regeneriersalz",
    "dishwasher salt", "spulmaschinentabs", "spuhlmaschinentabs",
    "dishwasher tabs",
    "smartphone", "mobile phone", "iphone",
}

FOOD_KEYWORDS = {
    "food", "lebensmittel", "beverage", "getrank", "snack",
    "chocolate", "schokolade", "milk", "milch", "coffee",
    "kaffee", "cereal", "musli", "spread", "brotaufstrich",
    "confectionery", "susswaren", "dessert",
    "haferdrink", "oat drink", "haverdrink",
    "pflanzendrink", "plant drink", "plant based drink",
}

BEAUTY_CATEGORY_MARKERS = {
    "open beauty facts",
    "beauty products",
    "cosmetics",
    "personal care",
}

NON_FOOD_CATEGORY_MARKERS = {
    "non food products",
    "incorrect product type",
}


def normalize_classifier_text(value):
    text = normalize_text(value).replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def text_contains_any(text, keywords):
    normalized_text = normalize_classifier_text(text)
    for keyword in keywords:
        normalized_keyword = normalize_classifier_text(keyword)
        if not normalized_keyword:
            continue
        if len(normalized_keyword) < 4:
            if re.search(rf"\b{re.escape(normalized_keyword)}\b", normalized_text):
                return True
        elif normalized_keyword in normalized_text:
            return True
    return False


def detect_product_type(product):
    category_tags = product.get("category_tags", [])
    if not isinstance(category_tags, (list, tuple, set)):
        category_tags = [] if pd.isna(category_tags) else [str(category_tags)]

    category_text = " ".join(str(tag) for tag in category_tags)
    name_text = " ".join([
        clean_text(product.get("product_name")),
        clean_text(product.get("generic_name")),
        clean_text(product.get("brand")),
    ])
    categories_text = clean_text(product.get("categories"))

    category_text = normalize_classifier_text(
        f"{category_text} {categories_text}"
    )
    name_text = normalize_classifier_text(name_text)

    if text_contains_any(category_text, BEAUTY_CATEGORY_MARKERS):
        return "beauty"

    if text_contains_any(name_text, BEAUTY_KEYWORDS):
        return "beauty"

    if text_contains_any(name_text, HEALTH_KEYWORDS):
        return "health"

    if text_contains_any(name_text, PRODUCT_KEYWORDS):
        return "products"

    if text_contains_any(category_text, BEAUTY_KEYWORDS):
        return "beauty"

    if text_contains_any(category_text, HEALTH_KEYWORDS):
        return "health"

    if text_contains_any(category_text, PRODUCT_KEYWORDS):
        return "products"

    if text_contains_any(name_text, FOOD_KEYWORDS):
        return "food"

    if not text_contains_any(category_text, NON_FOOD_CATEGORY_MARKERS):
        if text_contains_any(category_text, FOOD_KEYWORDS):
            return "food"

    return "unknown"

def passes_source_sanity_check(product):
    source = product.get("source")
    detected_type = detect_product_type(product)

    if source == "food" and detected_type in {"beauty", "health"}:
        return False

    if source == "beauty" and detected_type == "food":
        return False

    return True


def assign_effective_source(product):
    original_source = product.get("source")
    detected_type = product.get("detected_product_type") or detect_product_type(product)

    type_to_source = {
        "food": "food",
        "beauty": "beauty",
        "health": "products",
        "products": "products",
    }
    effective_source = type_to_source.get(detected_type, original_source)

    product["original_source"] = original_source
    product["effective_source"] = effective_source
    product["source"] = effective_source
    product["classification_rerouted"] = bool(
        original_source
        and effective_source
        and original_source != effective_source
    )
    return product


def normalize_product_identity(value):
    value = normalize_match_text(value)
    value = re.sub(r"\b(?:de|en|fr)\b", " ", value)
    return " ".join(value.split())


def has_useful_value(value):
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    if pd.isna(value):
        return False
    return str(value).strip().lower() not in {"", "unknown", "nan", "none"}


def calculate_result_quality(row):
    useful_fields = [
        "barcode",
        "product_name",
        "brand",
        "quantity",
        "product_quantity",
        "categories",
        "labels",
        "image_url",
        "ecoscore_grade",
        "ingredients_text",
    ]
    return sum(has_useful_value(row.get(field)) for field in useful_fields)


def deduplicate_search_results(results_df):
    if results_df.empty:
        return results_df

    deduplicated = results_df.copy()
    deduplicated["barcode_clean"] = (
        deduplicated["barcode"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    deduplicated["name_clean"] = (
        deduplicated["product_name"]
        .fillna("")
        .apply(normalize_product_identity)
    )
    deduplicated["brand_clean"] = (
        deduplicated["brand"]
        .fillna("")
        .apply(normalize_product_identity)
    )
    deduplicated["quantity_clean"] = deduplicated.apply(
        lambda row: normalize_product_identity(
            row.get("quantity")
            if has_useful_value(row.get("quantity"))
            else row.get("product_quantity")
        ),
        axis=1,
    )
    deduplicated["result_quality"] = deduplicated.apply(
        calculate_result_quality,
        axis=1,
    )

    deduplicated = deduplicated.sort_values(
        ["result_quality", "confidence_score", "overall_score"],
        ascending=False,
    )

    with_barcode = deduplicated[deduplicated["barcode_clean"] != ""]
    without_barcode = deduplicated[deduplicated["barcode_clean"] == ""]

    with_barcode = with_barcode.drop_duplicates(
        subset=["barcode_clean"],
        keep="first",
    )

    deduplicated = pd.concat(
        [with_barcode, without_barcode],
        ignore_index=True,
    )

    has_identity = (
        (deduplicated["name_clean"] != "")
        & (deduplicated["brand_clean"] != "")
    )
    identified = deduplicated[has_identity].drop_duplicates(
        subset=["brand_clean", "name_clean", "quantity_clean"],
        keep="first",
    )
    unidentified = deduplicated[~has_identity]

    deduplicated = pd.concat(
        [identified, unidentified],
        ignore_index=True,
    )

    return deduplicated.drop(
        columns=[
            "barcode_clean",
            "name_clean",
            "brand_clean",
            "quantity_clean",
            "result_quality",
        ],
        errors="ignore",
    )


# 13. Matching Functions
def normalize_match_text(value):
    value = normalize_text(value)
    value = value.replace("en:", "").replace("de:", "").replace("fr:", "")
    value = value.replace("-", " ").replace("_", " ").replace(":", " ")
    return " ".join(value.split())

def keyword_matches_tag(keyword, tag):
    keyword_clean = normalize_match_text(keyword)
    tag_clean = normalize_match_text(tag)

    if not keyword_clean:
        return False

    if len(keyword_clean) < 4:
        return keyword_clean in tag_clean.split()

    return keyword_clean in tag_clean

def normalize_tag_list(values):
    return [normalize_text(value) for value in values]

# 14. Match Labels
def get_applicable_mapping_rows(source, label_mapping):
    database = SOURCE_TO_DATABASE.get(source)

    return label_mapping[
        (label_mapping["database"] == "shared")
        | (label_mapping["database"] == database)
    ].copy()

def match_labels(product_tags, source, label_mapping):
    product_tags_clean = normalize_tag_list(product_tags)
    applicable_mapping = get_applicable_mapping_rows(source, label_mapping)

    matched_rows = applicable_mapping[
        applicable_mapping["label_keyword_clean"].apply(
            lambda keyword: any(
                keyword_matches_tag(keyword, tag)
                for tag in product_tags_clean
            )
        )
    ].copy()

    return matched_rows

# 15. Deduplicate Score Groups
def deduplicate_score_groups(matched_rows):
    if matched_rows.empty:
        return matched_rows

    matched_rows = matched_rows.copy()

    matched_rows["score_sum"] = (
        matched_rows["environmental"].abs()
        + matched_rows["social"].abs()
        + matched_rows["governance"].abs()
        + matched_rows["ethic"].abs()
    )

    return (
        matched_rows
        .sort_values("score_sum", ascending=False)
        .drop_duplicates(subset="score_group", keep="first")
    )

# 16. Confidence Function
MIN_CONFIDENCE_SCORE = 15
PRODUCT_CONFIDENCE_WEIGHT = 0.60
COMPANY_CONFIDENCE_WEIGHT = 0.40

def calculate_confidence(matched_rows, has_ecoscore, confidence_mapping):
    confidence = MIN_CONFIDENCE_SCORE

    if not matched_rows.empty:
        matched_score_groups = matched_rows["score_group"].dropna().unique()

        matched_confidence = confidence_mapping[
            confidence_mapping["score_group"].isin(matched_score_groups)
        ].copy()

        matched_confidence = matched_confidence.drop_duplicates(
            subset="score_group",
            keep="first"
        )

        confidence += matched_confidence["confidence_weight"].sum()

    if has_ecoscore:
        eco_confidence = confidence_mapping[
            confidence_mapping["score_group"] == "eco_score"
        ]["confidence_weight"]

        if not eco_confidence.empty:
            confidence += eco_confidence.iloc[0]

    return min(100, round(confidence, 1))


def calculate_combined_confidence(product_confidence, company_confidence):
    product_confidence = clamp(float(product_confidence or 0))
    company_confidence = clamp(float(company_confidence or 0))
    combined = (
        product_confidence * PRODUCT_CONFIDENCE_WEIGHT
        + company_confidence * COMPANY_CONFIDENCE_WEIGHT
    )
    return round(combined, 1)


# 17. Score Function
NEUTRAL_BASELINE_SCORE = 50

OVERALL_WEIGHTS = {
    "environmental": 0.40,
    "social": 0.25,
    "governance": 0.15,
    "ethic": 0.20
}

def score_product(product, label_mapping, confidence_mapping, eco_baselines):
    source = product.get("effective_source") or product["source"]
    label_tags = product.get("label_tags", [])
    ecoscore_grade = normalize_text(product.get("ecoscore_grade", ""))

    matched_rows = match_labels(label_tags, source, label_mapping)
    matched_rows = deduplicate_score_groups(matched_rows)

    environmental = NEUTRAL_BASELINE_SCORE
    social = NEUTRAL_BASELINE_SCORE
    governance = NEUTRAL_BASELINE_SCORE
    ethic = NEUTRAL_BASELINE_SCORE

    has_ecoscore = source == "food" and ecoscore_grade in eco_baselines

    if has_ecoscore:
        environmental = eco_baselines[ecoscore_grade]

    if not matched_rows.empty:
        environmental += matched_rows["environmental"].sum()
        social += matched_rows["social"].sum()
        governance += matched_rows["governance"].sum()
        ethic += matched_rows["ethic"].sum()

    environmental = clamp(environmental)
    social = clamp(social)
    governance = clamp(governance)
    ethic = clamp(ethic)

    overall = (
        environmental * OVERALL_WEIGHTS["environmental"]
        + social * OVERALL_WEIGHTS["social"]
        + governance * OVERALL_WEIGHTS["governance"]
        + ethic * OVERALL_WEIGHTS["ethic"]
    )

    confidence = calculate_confidence(
        matched_rows,
        has_ecoscore,
        confidence_mapping
    )

    explanation_notes = []

    if has_ecoscore:
        explanation_notes.append(
            f"Environmental baseline uses Eco-Score {ecoscore_grade}."
        )
    else:
        explanation_notes.append(
            "No usable Eco-Score found; environmental score starts from the neutral baseline of 50."
        )

    if matched_rows.empty:
        explanation_notes.append(
            "No positive or negative label evidence found in the current mapping."
        )
    else:
        explanation_notes.append(
            f"Matched {len(matched_rows)} scoring signal(s) from product labels."
        )

    return {
        "environmental_score": round(environmental, 1),
        "social_score": round(social, 1),
        "governance_score": round(governance, 1),
        "ethics_score": round(ethic, 1),
        "overall_score": round(overall, 1),
        "confidence_score": confidence,
        "product_confidence_score": confidence,
        "matched_labels": matched_rows["matched_label"].tolist(),
        "matched_score_groups": matched_rows["score_group"].tolist(),
        "score_reasons": matched_rows["reason"].fillna("").tolist(),
        "score_explanation": " ".join(explanation_notes),
        "used_ecoscore": has_ecoscore,
        "ecoscore_grade_used": ecoscore_grade if has_ecoscore else None,
    }


# 17.5 Enrich brand with company ESG data from WikiRate (optional advanced feature)
COMPANY_TITLE_ALIASES = {
    "activia": "Danone Group",
    "alnatura": "Alnatura",
    "alpro": "Danone Group",
    "apple": "Apple",
    "ariel": "Procter & Gamble",
    "alverde": "dm-drogerie markt",
    "babylove": "dm-drogerie markt",
    "balea": "dm-drogerie markt",
    "beiersdorf": "Beiersdorf",
    "ben & jerry's": "Ben & Jerry's",
    "ben&jerry's": "Ben & Jerry's",
    "ben and jerry's": "Ben & Jerry's",
    "bellarom": "Lidl",
    "bon gelati": "Lidl",
    "cien": "Lidl",
    "colgate": "Colgate-Palmolive",
    "crownfield": "Lidl",
    "danone": "Danone Group",
    "dmbio": "dm-drogerie markt",
    "domol": "Dirk Rossmann GmbH",
    "duracell": "Duracell",
    "ferrero": "Ferrero SpA",
    "favorina": "Lidl",
    "frosch": "Werner & Mertz",
    "garnier": "L'Oreal",
    "head & shoulders": "Procter & Gamble",
    "henkel": "Henkel",
    "dm": "dm-drogerie markt",
    "dm drogerie markt": "dm-drogerie markt",
    "dm-drogerie markt": "dm-drogerie markt",
    "dirk rossmann": "Dirk Rossmann GmbH",
    "dirk rossmann gmbh": "Dirk Rossmann GmbH",
    "isana": "Dirk Rossmann GmbH",
    "jacobs": "JDE Peet's",
    "kerastase": "L'Oreal",
    "kérastase": "L'Oreal",
    "kitkat": "Nestle",
    "lavazza": "Lavazza",
    "lenor": "Procter & Gamble",
    "lidl": "Lidl",
    "rossmann": "Dirk Rossmann GmbH",
    "l oreal": "L'Oreal",
    "loreal": "L'Oreal",
    "mars": "Mars",
    "mikado": "Mondelez International",
    "milbona": "Lidl",
    "milka": "Mondelez International",
    "mister choc": "Lidl",
    "mondelez": "Mondelez International",
    "nescafe": "Nestle",
    "nescafé": "Nestle",
    "nestle": "Nestle",
    "nivea": "Beiersdorf",
    "oral b": "Procter & Gamble",
    "oral-b": "Procter & Gamble",
    "oreo": "Mondelez International",
    "palmolive": "Colgate-Palmolive",
    "persil": "Henkel",
    "perwoll": "Henkel",
    "philadelphia": "Mondelez International",
    "procter gamble": "Procter & Gamble",
    "ritter sport": "Alfred Ritter",
    "rituals": "Rituals Cosmetics",
    "sagrotan": "Reckitt",
    "sondey": "Lidl",
    "spee": "Henkel",
    "storck": "August Storck",
    "swiffer": "Procter & Gamble",
    "tony's chocolonely": "Tony's Chocolonely",
    "tonys chocolonely": "Tony's Chocolonely",
    "unilever": "Unilever",
    "vemondo": "Lidl",
    "weleda": "Weleda",
}
REVIEWED_COMPANY_NAMES = {
    clean_brand_name(company_name)
    for company_name in COMPANY_TITLE_ALIASES.values()
}


def canonicalize_company_candidate(candidate):
    normalized_candidate = normalize_classifier_text(candidate)
    if not normalized_candidate:
        return ""

    for alias, canonical_name in COMPANY_TITLE_ALIASES.items():
        normalized_alias = normalize_classifier_text(alias)
        normalized_canonical = normalize_classifier_text(canonical_name)
        if normalized_candidate in {normalized_alias, normalized_canonical}:
            return canonical_name

    return str(candidate).strip()


def get_company_lookup_candidates(product):
    candidates = []
    brand_value = str(product.get("brand", "") or product.get("brands", ""))

    for brand in re.split(r"[,;|]", brand_value):
        brand = canonicalize_company_candidate(brand)
        if brand:
            candidates.append(brand)

    product_title = normalize_classifier_text(
        " ".join([
            str(product.get("product_name", "")),
            str(product.get("generic_name", "")),
        ])
    )
    for alias, canonical_name in COMPANY_TITLE_ALIASES.items():
        normalized_alias = normalize_classifier_text(alias)
        if normalized_alias and re.search(
            rf"\b{re.escape(normalized_alias)}\b",
            product_title,
        ):
            candidates.append(canonical_name)

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        candidate = canonicalize_company_candidate(candidate)
        key = clean_brand_name(candidate)
        if key and key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)
    return unique_candidates


def wikirate_enrichment_quality(enrichment):
    metrics = enrichment.get("wikirate_metrics", {}) or {}
    usable_metrics = sum(
        metric.get("classification") in {"positive", "negative"}
        and metric.get("value") not in (None, "", [], {})
        and metric.get("http_status") != 429
        for metric in metrics.values()
    )
    return (
        usable_metrics,
        enrichment.get("company_enrichment_confidence", 0),
        int(bool(enrichment.get("wikirate", {}).get("company_found"))),
        int(bool(enrichment.get("company_resolution", {}).get("parent_company_name"))),
    )


def get_wikirate_enrichment(brand):
    if not brand or pd.isna(brand):
        return None

    normalized_brand = clean_brand_name(get_first_brand(str(brand)))
    if not normalized_brand:
        return None

    return _get_wikirate_enrichment_cached(normalized_brand)


@lru_cache(maxsize=256)
def _get_wikirate_enrichment_cached(normalized_brand):
    try:
        return enrich_brand_with_company_esg(normalized_brand)
    except Exception as error:
        return {
            "company_adjustments": {"social": 0, "governance": 0, "ethics": 0},
            "company_enrichment_confidence": 0,
            "company_enrichment_confidence_label": "low",
            "explanations": [],
            "policy_evidence": [],
            "performance_evidence": [],
            "warnings": [f"WikiRate enrichment failed: {error}"],
            "wikirate": {"company_found": False},
            "company_resolution": {},
        }


@lru_cache(maxsize=128)
def _get_reviewed_company_enrichment_cached(normalized_company):
    canonical_company = next(
        (
            company_name
            for company_name in COMPANY_TITLE_ALIASES.values()
            if clean_brand_name(company_name) == normalized_company
        ),
        normalized_company,
    )
    try:
        return enrich_company_with_wikirate(canonical_company)
    except Exception as error:
        return {
            "company_adjustments": {"social": 0, "governance": 0, "ethics": 0},
            "company_enrichment_confidence": 0,
            "company_enrichment_confidence_label": "low",
            "explanations": [],
            "policy_evidence": [],
            "performance_evidence": [],
            "warnings": [f"WikiRate company enrichment failed: {error}"],
            "wikirate": {"company_found": False},
            "company_resolution": {
                "parent_company_name": canonical_company,
                "resolution_confidence": "high",
                "resolution_method": "reviewed_company_alias",
            },
        }


def get_best_wikirate_enrichment(product):
    candidates = get_company_lookup_candidates(product)
    enrichments = [
        enrichment
        for candidate in candidates
        if (
            enrichment := (
                _get_reviewed_company_enrichment_cached(clean_brand_name(candidate))
                if clean_brand_name(candidate) in REVIEWED_COMPANY_NAMES
                else get_wikirate_enrichment(candidate)
            )
        ) is not None
    ]
    if not enrichments:
        return None
    return max(enrichments, key=wikirate_enrichment_quality)


def apply_wikirate_adjustments(score, product):
    product_confidence = score.get(
        "product_confidence_score",
        score.get("confidence_score", 0),
    )
    score["product_confidence_score"] = product_confidence

    enrichment = get_best_wikirate_enrichment(product)

    if not enrichment:
        score["wikirate_confidence_score"] = 0
        score["wikirate_confidence_label"] = "low"
        score["combined_confidence_score"] = calculate_combined_confidence(
            product_confidence,
            0,
        )
        score["confidence_score"] = score["combined_confidence_score"]
        return score

    adjustments = enrichment.get("company_adjustments", {})

    score["social_score"] = clamp(score["social_score"] + adjustments.get("social", 0))
    score["governance_score"] = clamp(score["governance_score"] + adjustments.get("governance", 0))
    score["ethics_score"] = clamp(score["ethics_score"] + adjustments.get("ethics", 0))

    score["overall_score"] = round(
        score["environmental_score"] * OVERALL_WEIGHTS["environmental"]
        + score["social_score"] * OVERALL_WEIGHTS["social"]
        + score["governance_score"] * OVERALL_WEIGHTS["governance"]
        + score["ethics_score"] * OVERALL_WEIGHTS["ethic"],
        1
    )

    company_confidence = enrichment.get("company_enrichment_confidence", 0)
    score["wikirate_company_adjustments"] = adjustments
    score["wikirate_confidence_score"] = company_confidence
    score["wikirate_confidence_label"] = enrichment.get("company_enrichment_confidence_label")
    score["wikirate_explanations"] = enrichment.get("explanations", [])
    score["wikirate_policy_evidence"] = enrichment.get("policy_evidence", [])
    score["wikirate_performance_evidence"] = enrichment.get("performance_evidence", [])
    score["wikirate_warnings"] = enrichment.get("warnings", [])
    score["wikirate_company"] = enrichment.get("company_resolution", {}).get("parent_company_name")
    score["wikirate_company_found"] = enrichment.get("wikirate", {}).get("company_found", False)
    score["combined_confidence_score"] = calculate_combined_confidence(
        product_confidence,
        company_confidence,
    )
    score["confidence_score"] = score["combined_confidence_score"]

    return score


# 18. Build score_unified_product()
def score_unified_product(product, include_wikirate=False):
    label_mapping, confidence_mapping, eco_baselines = load_scoring_resources()

    score = score_product(
        product,
        label_mapping,
        confidence_mapping,
        eco_baselines
    )

    if include_wikirate:
        score = apply_wikirate_adjustments(score, product)

    return {
        **product,
        **score
    }


def enrich_selected_product_with_wikirate(product):
    enriched_product = dict(product)
    enriched_product = apply_wikirate_adjustments(enriched_product, enriched_product)
    return enriched_product

# Later, for performance, cache the resources in Streamlit

#19. Build search_product(query) - key function
def search_product(
    query,
    page_size=10,
    germany_only=True,
    source_filter=None,
    apply_sanity_filter=True,
    include_wikirate=False,
):
    label_mapping, confidence_mapping, eco_baselines = load_scoring_resources()

    results = []

    if source_filter is None or apply_sanity_filter:
        source_names = list(SOURCES.keys())
    elif isinstance(source_filter, str):
        source_names = [source_filter]
    else:
        source_names = list(source_filter)

    source_names = [source_name for source_name in source_names if source_name in SOURCES]
    if source_filter is None:
        effective_source_filter = None
    elif isinstance(source_filter, str):
        effective_source_filter = {source_filter}
    else:
        effective_source_filter = {
            source_name
            for source_name in source_filter
            if source_name in SOURCES
        }

    for source_name in source_names:
        raw_products = search_from_source(
            source_name,
            query,
            page_size=page_size
        )

        for raw_product in raw_products:
            if germany_only and not is_german_product(raw_product):
                continue

            unified_product = transform_to_unified(
                raw_product,
                source_name=source_name,
                retrieval_method="search",
                search_query=query
            )
            unified_product["detected_product_type"] = detect_product_type(unified_product)
            if apply_sanity_filter:
                unified_product = assign_effective_source(unified_product)
            else:
                unified_product["original_source"] = source_name
                unified_product["effective_source"] = source_name
                unified_product["classification_rerouted"] = False

            if (
                effective_source_filter is not None
                and unified_product["effective_source"] not in effective_source_filter
            ):
                continue

            score = score_product(
                unified_product,
                label_mapping,
                confidence_mapping,
                eco_baselines
            )

            if include_wikirate:
                score = apply_wikirate_adjustments(score, unified_product)

            results.append({
                **unified_product,
                **score
            })

    results_df = pd.DataFrame(results)

    if results_df.empty:
        return results_df

    results_df = deduplicate_search_results(results_df)
    results_df = results_df.sort_values(
        ["overall_score", "confidence_score"],
        ascending=False,
    ).reset_index(drop=True)

    return results_df

# 20. Build get_product_by_barcode(barcode)
def get_product_by_barcode(
    barcode,
    germany_only=True,
    include_wikirate=False,
    apply_sanity_filter=True,
):
    label_mapping, confidence_mapping, eco_baselines = load_scoring_resources()

    results = []

    for source_name in SOURCES.keys():
        raw_product = extract_from_source(source_name, barcode)

        if raw_product is None:
            continue

        if germany_only and not is_german_product(raw_product):
            continue

        unified_product = transform_to_unified(
            raw_product,
            source_name=source_name,
            retrieval_method="barcode",
            search_query=""
        )
        unified_product["detected_product_type"] = detect_product_type(unified_product)

        if apply_sanity_filter:
            unified_product = assign_effective_source(unified_product)
        else:
            unified_product["original_source"] = source_name
            unified_product["effective_source"] = source_name
            unified_product["classification_rerouted"] = False

        score = score_product(
            unified_product,
            label_mapping,
            confidence_mapping,
            eco_baselines
        )

        if include_wikirate:
            score = apply_wikirate_adjustments(score, unified_product)

        results.append({
            **unified_product,
            **score
        })

    return pd.DataFrame(results)
