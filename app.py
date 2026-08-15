import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app_backend import (
    enrich_selected_product_with_wikirate,
    get_product_by_barcode,
    search_product,
)

st.set_page_config(
    page_title="TrustShelf",
    page_icon="🛒",
    layout="wide",
)

st.markdown(
    """
<style>
:root {
    --bg:#0A081B; --card:#10142C; --card2:#0F1228;
    --cyan:#29DDDA; --mint:#16FFBB; --blue:#37A7E7;
    --purple:#8B6CFF; --yellow:#FFD166; --orange:#FFB347; --red:#FF5A5A;
    --text:#F5F7FF; --muted:rgba(245,247,255,.65);
    --label:rgba(245,247,255,.45); --deep:#091231;
}

.stApp {
    background-color:#02030A;
    background:
        radial-gradient(ellipse at 12% 0%,rgba(0,61,153,.22),transparent 30%),
        radial-gradient(ellipse at 92% 4%,rgba(32,22,184,.14),transparent 26%),
        linear-gradient(
            180deg,
            #07113A 0%,
            #050816 28%,
            #03050F 50%,
            #02030A 68%,
            #010207 100%
        );
    color: var(--text);
    isolation:isolate;
    overflow-x:hidden;
    box-shadow:inset 0 -35vh 120px rgba(1,2,7,.72);
}

.stApp::before {
    content:"";
    position:fixed;
    inset:-22% -30% -5%;
    background:
        linear-gradient(
            132deg,
            transparent 30%,
            rgba(0,217,255,.04) 37%,
            rgba(0,217,255,.48) 43%,
            rgba(0,109,255,.34) 48%,
            rgba(0,61,153,.12) 53%,
            transparent 60%
        ),
        linear-gradient(
            147deg,
            transparent 42%,
            rgba(0,109,255,.05) 47%,
            rgba(0,109,255,.38) 52%,
            rgba(32,22,184,.24) 58%,
            transparent 66%
        );
    background-size:115% 100%,125% 110%;
    background-position:-12% -8%,18% 0%;
    filter:blur(52px);
    opacity:.82;
    -webkit-mask-image:linear-gradient(to bottom,#000 0%,#000 44%,rgba(0,0,0,.52) 62%,transparent 82%);
    mask-image:linear-gradient(to bottom,#000 0%,#000 44%,rgba(0,0,0,.52) 62%,transparent 82%);
    animation:borealisBeams 14s ease-in-out infinite alternate;
    pointer-events:none;
    z-index:0;
    will-change:transform,background-position,opacity;
}

.stApp::after {
    content:"";
    position:fixed;
    inset:-18% -24% 22%;
    background:
        radial-gradient(ellipse at 18% 6%,rgba(0,217,255,.28),transparent 22%),
        radial-gradient(ellipse at 84% 14%,rgba(0,109,255,.34),transparent 29%),
        radial-gradient(ellipse at 60% 48%,rgba(32,22,184,.24),transparent 38%),
        linear-gradient(
            118deg,
            transparent 38%,
            rgba(55,167,231,.18) 47%,
            rgba(0,109,255,.08) 54%,
            transparent 64%
        );
    filter:blur(74px);
    opacity:.66;
    -webkit-mask-image:linear-gradient(to bottom,#000 0%,rgba(0,0,0,.85) 48%,transparent 90%);
    mask-image:linear-gradient(to bottom,#000 0%,rgba(0,0,0,.85) 48%,transparent 90%);
    animation:borealisDepth 19s ease-in-out infinite alternate;
    pointer-events:none;
    z-index:0;
    will-change:transform,opacity;
}

@keyframes borealisBeams {
    0% {
        transform:translate3d(-7%,-4%,0) scale(1.02) rotate(-3deg);
        background-position:-12% -8%,18% 0%;
        opacity:.58;
    }
    50% {
        transform:translate3d(2%,3%,0) scale(1.09) rotate(1deg);
        background-position:2% 2%,6% -4%;
        opacity:.92;
    }
    100% {
        transform:translate3d(8%,-1%,0) scale(1.14) rotate(4deg);
        background-position:14% -3%,-10% 4%;
        opacity:.70;
    }
}

@keyframes borealisDepth {
    0% {
        transform:translate3d(5%,-2%,0) scale(1.02) rotate(1deg);
        opacity:.48;
    }
    50% {
        transform:translate3d(-1%,3%,0) scale(1.08) rotate(-2deg);
        opacity:.72;
    }
    100% {
        transform:translate3d(-6%,-3%,0) scale(1.13) rotate(2deg);
        opacity:.60;
    }
}

@media (prefers-reduced-motion:reduce) {
    .stApp::before,
    .stApp::after {
        animation:none;
    }
}

[data-testid="stHeader"] {
    background:rgba(10,8,27,.76);
    z-index:2;
}
.block-container {
    max-width:1220px;
    padding-top:2rem;
    position:relative;
    z-index:1;
}

h1,h2,h3,h4,p,div,span,label {color: var(--text);}

[data-testid="stForm"] {
    background:linear-gradient(180deg,rgba(20,25,55,.96),rgba(14,18,40,.96));
    border:1px solid rgba(55,167,231,.18);
    border-radius:18px;
    padding:1rem;
    box-shadow:0 10px 30px rgba(0,0,0,.35);
}

[data-testid="stForm"]:hover {
    border-color:rgba(22,255,187,.30);
}

.stTextInput label,
.stSelectbox label,
.stRadio label,
.stCaptionContainer {
    color:var(--muted);
}

.stTextInput input,
.stSelectbox [data-baseweb="select"] {
    background:rgba(9,18,49,.58);
    border-color:rgba(55,167,231,.16);
    color:var(--text);
}

.stTextInput input:focus,
.stSelectbox [data-baseweb="select"]:focus-within {
    border-color:rgba(22,255,187,.30);
    box-shadow:0 0 0 1px rgba(22,255,187,.10);
}

.hero-row {display:flex; align-items:center; gap:.9rem;}
.logo-box {
    width: 56px;
    height: 56px;
    border-radius: 18px;
    background:
        radial-gradient(circle at 30% 20%,rgba(22,255,187,.52),transparent 35%),
        linear-gradient(135deg,rgba(41,221,218,.96),rgba(22,255,187,.86));
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow:
        0 0 18px rgba(41,221,218,.38),
        0 0 42px rgba(22,255,187,.18);
    position: relative;
    overflow: hidden;
    transition: transform 0.25s ease, box-shadow 0.25s ease;
}

.logo-box::after {
    content: "";
    position: absolute;
    inset: -40%;
    background: linear-gradient(
        120deg,
        transparent 35%,
        rgba(255,255,255,0.35) 50%,
        transparent 65%
    );
    transform: translateX(-80%);
    animation: logo-shine 4s ease-in-out infinite;
}

@keyframes logo-shine {
    0%, 70% { transform: translateX(-85%); }
    100% { transform: translateX(85%); }
}

.logo-icon {
    width: 34px;
    height: 34px;
    display: block;
    z-index: 1;
    position: relative;
    color: #061015;
    fill: none;
    stroke: currentColor;
    stroke-width: 2.1;
    stroke-linecap: round;
    stroke-linejoin: round;
}

.logo-box:hover {
    transform: translateY(-2px) scale(1.05);
    box-shadow:
        0 0 24px rgba(41,221,218,.52),
        0 0 55px rgba(22,255,187,.28);
}
.brand-title {
    font-size: clamp(2.5rem,5vw,4.6rem);
    font-weight:950; margin:0;
    background:linear-gradient(90deg,#16FFBB,#29DDDA,#37A7E7);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}
.tagline {
    color:var(--cyan); font-weight:900; letter-spacing:.12em;
    text-transform:uppercase; font-size:1.05rem; margin-top:.35rem;
}
.subtitle {color:var(--muted); max-width:760px; margin-top:.8rem;}

.neon-center-divider {
    width:76%;
    height:2px;
    margin:2.5rem auto;
    border-radius:999px;
    position:relative;
    background:linear-gradient(
        90deg,
        rgba(55,167,231,.00) 0%,
        rgba(55,167,231,.03) 15%,
        rgba(55,167,231,.08) 25%,
        rgba(55,167,231,.18) 35%,
        rgba(55,167,231,.45) 45%,
        rgba(55,167,231,.90) 50%,
        rgba(55,167,231,.45) 55%,
        rgba(55,167,231,.18) 65%,
        rgba(55,167,231,.08) 75%,
        rgba(55,167,231,.03) 85%,
        rgba(55,167,231,.00) 100%
    );
    box-shadow:
        0 0 8px rgba(55,167,231,.20),
        0 0 20px rgba(55,167,231,.15);
    animation:dividerGlow 8s ease-in-out infinite;
}

.neon-center-divider::before {
    content:"";
    position:absolute;
    left:50%;
    top:50%;
    width:240px;
    height:26px;
    transform:translate(-50%,-50%);
    border-radius:999px;
    background:radial-gradient(
        ellipse at center,
        rgba(55,167,231,.28) 0%,
        rgba(55,167,231,.12) 35%,
        rgba(55,167,231,.04) 60%,
        transparent 100%
    );
    filter:blur(12px);
    pointer-events:none;
}

@keyframes dividerGlow {
    0%,100% {opacity:.85;}
    50% {opacity:1;}
}

.card {
    background:linear-gradient(180deg,rgba(20,25,55,.96),rgba(14,18,40,.96));
    border:1px solid rgba(55,167,231,.18);
    border-radius:18px;
    padding:1rem;
    box-shadow:0 10px 30px rgba(0,0,0,.35);
}

.card-title {
    display:flex; justify-content:space-between; align-items:center;
    color:var(--text); font-weight:800; margin-bottom:.8rem;
}
.card-title small {color:var(--muted); font-weight:750;}

.stFormSubmitButton > button {
    width:100%;
    min-width:120px;
    max-width:140px;
    height:48px;
    border-radius:999px;
    border:1px solid rgba(22,255,187,.25);
    background:
        linear-gradient(rgba(9,18,49,.12),rgba(9,18,49,.12)),
        linear-gradient(135deg,rgba(22,255,187,.82),rgba(41,221,218,.82));
    color:#091231;
    font-size:1rem;
    font-weight:700;
    box-shadow:0 0 10px rgba(22,255,187,.12);
    cursor:pointer;
    transition:all .25s ease;
}
.stFormSubmitButton > button:hover {
    background:
        linear-gradient(rgba(9,18,49,.08),rgba(9,18,49,.08)),
        linear-gradient(135deg,rgba(22,255,187,.84),rgba(41,221,218,.84));
    color:#091231;
    border-color:rgba(22,255,187,.30);
    box-shadow:0 0 18px rgba(22,255,187,.18);
    transform:translateY(-1px);
}
.stFormSubmitButton > button:active {
    transform:translateY(0);
    box-shadow:0 0 8px rgba(22,255,187,.12);
}

[data-testid="stToggle"] label {
    color:#F5F7FF;
    font-size:1rem;
    font-weight:700;
}

[data-testid="stToggle"] [data-baseweb="checkbox"] > div:first-of-type {
    background:rgba(255,255,255,.10) !important;
    border-color:rgba(255,255,255,.12) !important;
    transition:all .25s ease;
}

[data-testid="stToggle"] [data-baseweb="checkbox"]:has(input:checked) > div:first-of-type {
    background:linear-gradient(90deg,#16FFBB,#29DDDA) !important;
    border-color:rgba(22,255,187,.30) !important;
    box-shadow:0 0 10px rgba(22,255,187,.12);
}

[data-testid="stToggle"] [data-baseweb="checkbox"] > div:first-of-type > div {
    background:#FFFFFF !important;
}

[data-testid="stToggle"] [data-baseweb="checkbox"]:has(input:checked) > div:first-of-type > div {
    background:#091231 !important;
}

[data-testid="stToggle"] [data-baseweb="checkbox"]:has(input:not(:checked)) > div:first-of-type {
    background:rgba(255,255,255,.10) !important;
}

[data-testid="stToggle"] [data-baseweb="checkbox"]:has(input:checked) > div:first-of-type {
    background:linear-gradient(90deg,#16FFBB,#29DDDA) !important;
    border-color:rgba(22,255,187,.30) !important;
    box-shadow:0 0 10px rgba(22,255,187,.12);
}

.product-card {
    background:linear-gradient(180deg,rgba(20,25,55,.96),rgba(14,18,40,.96));
    border:1px solid rgba(55,167,231,.18);
    border-radius:18px; padding:1rem;
    box-shadow:0 10px 30px rgba(0,0,0,.35);
    min-height:720px;
    display:flex;
    flex-direction:column;
}
.image-box {
    height:220px; border-radius:14px;
    background:rgba(9,18,49,.36);
    border:1px solid rgba(55,167,231,.12);
    display:flex; align-items:center; justify-content:center;
    overflow:hidden; margin-bottom:1rem;
    flex-shrink:0;
}
.image-box img {max-height:200px; max-width:92%; object-fit:contain;}
.no-image {color:var(--muted); font-weight:800;}
.product-name {font-size:1.35rem; font-weight:950; line-height:1.15; margin-bottom:.8rem;}
.meta-list {display:grid; gap:.55rem;}
.meta-item {
    background:rgba(15,18,40,.72);
    border:1px solid rgba(55,167,231,.10);
    border-radius:12px; padding:.65rem .75rem;
}
.meta-label {
    color:var(--label); text-transform:uppercase;
    letter-spacing:.08em; font-size:.66rem; font-weight:850;
}
.meta-value {margin-top:.25rem; font-size:.9rem; font-weight:760; overflow-wrap:anywhere;}

.score-overview-card,
.st-key-score_overview_card {
    background:linear-gradient(180deg,rgba(20,25,55,.96),rgba(14,18,40,.96));
    border:1px solid rgba(55,167,231,.18);
    border-radius:18px;
    padding:1rem;
    box-shadow:0 10px 30px rgba(0,0,0,.35),0 0 20px rgba(22,255,187,.10);
    min-height:720px;
}

.score-overview-heading {
    text-align:center;
    font-size:1.35rem;
    color:var(--text);
    font-weight:900;
    margin:0 0 1rem 0;
}

.score-card {
    width:100%;
    background:linear-gradient(180deg,rgba(24,30,64,.88),rgba(17,22,48,.90));
    border:1px solid rgba(55,167,231,.12);
    border-radius:12px;
    padding:.7rem .85rem;
    min-height:92px;
    margin-bottom:.42rem;
    box-shadow:0 10px 30px rgba(0,0,0,.22);
}

.score-accent {
    width:38px;
    height:3px;
    border-radius:999px;
    margin-bottom:.45rem;
    box-shadow:0 0 10px currentColor;
}

.score-name {font-size:.78rem; font-weight:900;}
.score-number {font-size:1.6rem; line-height:1; font-weight:950; margin-top:.3rem;}
.score-number span {color:var(--muted); font-size:.8rem;}
.progress-track {
    margin-top:.55rem; height:6px; border-radius:999px;
    background:rgba(255,255,255,.08); overflow:hidden;
}
.progress-fill {height:100%; border-radius:999px;}

.recommendation {
    width:fit-content; margin:1rem auto .4rem auto;
    padding:.62rem 1rem; border-radius:999px;
    background:rgba(15,18,40,.82);
    border:1px solid rgba(55,167,231,.16);
    font-weight:950;
}

.recommendation-compact {
    width:72%;
    min-width:0;
    max-width:100%;
    min-height:60px;
    margin:12px auto 14px auto;
    padding:.8rem 1rem;
    border-radius:999px;
    background:rgba(15,18,40,.82);
    border:1px solid rgba(55,167,231,.16);
    display:flex;
    align-items:center;
    justify-content:center;
    text-align:center;
    font-size:1.15rem;
    font-weight:800;
    line-height:1.2;
    white-space:nowrap;
}

.confidence-compact {
    width:72%;
    min-width:0;
    max-width:100%;
    min-height:60px;
    margin:0 auto 40px auto;
    padding:.8rem 1rem;
    border:1px solid rgba(55,167,231,.16);
    border-radius:999px;
    background:rgba(15,18,40,.82);
    display:flex;
    align-items:center;
    justify-content:center;
    text-align:center;
    font-size:1.15rem;
    font-weight:800;
    line-height:1.2;
    white-space:nowrap;
}

.st-key-donut_group {
    display:flex;
    flex-direction:column;
    align-items:center;
    width:100%;
}

.st-key-donut_group > div {
    width:100%;
}

.st-key-score_overview_card [data-testid="stHorizontalBlock"] {
    gap:.65rem;
}

.info-card {
    background:linear-gradient(180deg,rgba(20,25,55,.96),rgba(14,18,40,.96));
    border:1px solid rgba(55,167,231,.18);
    border-radius:18px; padding:1rem; margin-top:1rem;
    box-shadow:0 10px 30px rgba(0,0,0,.35);
}

.info-card.compact {
    padding:.8rem .9rem;
}

.info-card.compact .card-title {
    margin-bottom:.45rem;
}

.evidence-heading {
    margin-bottom:.8rem;
}

.evidence-heading-title {
    color:var(--text);
    font-size:1rem;
    font-weight:800;
}

.evidence-heading-subtitle {
    color:var(--muted);
    font-size:.72rem;
    font-weight:650;
    margin-top:.15rem;
}

.timeline-card {
    padding:1rem 1.25rem;
}

.timeline-track {
    position:relative;
    display:grid;
    grid-template-columns:repeat(var(--timeline-count),minmax(0,1fr));
    align-items:start;
    margin-top:.55rem;
    padding:.15rem .5rem .15rem .5rem;
}

.timeline-track::before {
    content:"";
    position:absolute;
    top:1.9rem;
    left:calc(50% / var(--timeline-count));
    right:calc(50% / var(--timeline-count));
    height:2px;
    border-radius:999px;
    background:rgba(245,247,255,.14);
}

.timeline-item {
    position:relative;
    z-index:1;
    display:flex;
    flex-direction:column;
    align-items:center;
    min-width:0;
    text-align:center;
    opacity:.42;
}

.timeline-item.active {
    opacity:1;
}

.timeline-range {
    min-height:1.1rem;
    color:var(--muted);
    font-size:.68rem;
    font-weight:650;
    white-space:nowrap;
}

.timeline-dot {
    width:.95rem;
    height:.95rem;
    margin:.36rem 0 .48rem 0;
    border:2px solid rgba(14,18,40,.96);
    border-radius:50%;
    background:var(--dot);
    box-shadow:0 0 0 2px rgba(245,247,255,.08);
}

.timeline-item.active .timeline-dot {
    box-shadow:
        0 0 0 2px rgba(245,247,255,.12),
        0 0 9px var(--dot),
        0 0 18px var(--dot);
}

.timeline-label {
    max-width:100%;
    color:var(--text);
    font-size:.72rem;
    font-weight:700;
    line-height:1.15;
    overflow-wrap:anywhere;
}

.bullet-groups {display:grid; gap:.9rem;}
.bullet-group-title {
    color:var(--cyan); font-size:.76rem; font-weight:800;
    text-transform:uppercase; letter-spacing:.08em; margin-bottom:.3rem;
}
.bullet-list {margin:0 0 0 1.1rem; padding:0;}
.bullet-list li {color:var(--muted); margin-bottom:.35rem;}

[data-testid="stExpander"] {
    border:1px solid rgba(55,167,231,.18);
    border-radius:18px;
    background:linear-gradient(180deg,rgba(20,25,55,.94),rgba(14,18,40,.94));
}

.card:hover,
.product-card:hover,
.st-key-score_overview_card:hover,
.info-card:hover {
    border-color:rgba(22,255,187,.30);
}
</style>
""",
    unsafe_allow_html=True,
)

SOURCE_OPTIONS = {
    "All databases": None,
    "Food": "food",
    "Beauty": "beauty",
    "Products": "products",
}

COLORS = {
    "Environmental": "#16FFBB",
    "Social": "#29DDDA",
    "Governance": "#37A7E7",
    "Ethics": "#8B6CFF",
    "Remaining": "rgba(255,255,255,0.14)",
}


def html_escape(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def safe_score(value, fallback=50):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return fallback


def safe_confidence(value):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def get_text(product, *keys, fallback="Unknown"):
    for key in keys:
        value = product.get(key)
        if value is not None and str(value).strip():
            return value
    return fallback


def get_dimension_score(product, dimension):
    aliases = {
        "environmental": ["environmental_score", "environmental"],
        "social": ["social_score", "social"],
        "governance": ["governance_score", "governance"],
        "ethics": ["ethics_score", "ethic_score", "ethics", "ethic"],
    }
    for key in aliases.get(dimension, []):
        if product.get(key) is not None:
            return safe_score(product.get(key))
    return 50


def get_overall_score(product):
    if product.get("overall_score") is not None:
        return safe_score(product.get("overall_score"))
    if product.get("overall") is not None:
        return safe_score(product.get("overall"))

    env = get_dimension_score(product, "environmental")
    soc = get_dimension_score(product, "social")
    gov = get_dimension_score(product, "governance")
    eth = get_dimension_score(product, "ethics")
    return safe_score(env * 0.40 + soc * 0.25 + gov * 0.15 + eth * 0.20)


def get_confidence_score(product):
    return safe_confidence(
        product.get(
            "confidence_score",
            product.get("confidence", product.get("wikirate_confidence_score")),
        )
    )


def product_label(row):
    name = row.get("product_name") or "Unnamed product"
    brand = row.get("brand") or row.get("brands") or "Unknown brand"
    source = row.get("source") or "unknown source"
    barcode = row.get("barcode") or row.get("code") or "no barcode"
    return f"{name} - {brand} ({source}, {barcode})"


def run_search(search_mode, query, source_filter):
    if search_mode == "Product name":
        return search_product(query, page_size=100, source_filter=source_filter)
    return get_product_by_barcode(query)


def recommendation_badge(score):
    score = safe_score(score)
    if score <= 39:
        return "Not Recommended", "#FF5A5A"
    if score <= 54:
        return "Low Conscious Choice", "#FFB347"
    if score <= 69:
        return "Moderately Conscious", "#FFD166"
    if score <= 84:
        return "Conscious Choice", "#16FFBB"
    return "Highly Conscious", "#37A7E7"


def active_score_range(score):
    score = safe_score(score)
    if score <= 39:
        return "0-39"
    if score <= 54:
        return "40-54"
    if score <= 69:
        return "55-69"
    if score <= 84:
        return "70-84"
    return "85-100"


def active_confidence_range(score):
    score = safe_confidence(score)
    if score <= 30:
        return "0-30"
    if score <= 60:
        return "31-60"
    return "61-100"


def render_product_card(product):
    product_name = html_escape(get_text(product, "product_name", fallback="Unknown product"))
    brand = html_escape(get_text(product, "brand", "brands", fallback="Unknown brand"))
    source = html_escape(get_text(product, "source", fallback="Unknown"))
    barcode = html_escape(get_text(product, "barcode", "code", fallback="Unknown barcode"))
    category = html_escape(get_text(product, "categories", fallback="Unknown category"))
    image_url = product.get("image_url")

    if isinstance(image_url, str) and image_url.strip():
        image_html = f'<img src="{html_escape(image_url)}" alt="Product image">'
    else:
        image_html = '<div class="no-image">No product image</div>'

    st.markdown(
        f"""
<div class="product-card">
    <div class="image-box">{image_html}</div>
    <div class="product-name">{product_name}</div>
    <div class="meta-list">
        <div class="meta-item"><div class="meta-label">Brand</div><div class="meta-value">{brand}</div></div>
        <div class="meta-item"><div class="meta-label">Source</div><div class="meta-value">{source}</div></div>
        <div class="meta-item"><div class="meta-label">Barcode</div><div class="meta-value">{barcode}</div></div>
        <div class="meta-item"><div class="meta-label">Category</div><div class="meta-value">{category}</div></div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_score_card(name, score, color):
    score = safe_score(score)
    st.markdown(
        f"""
<div class="score-card">
    <div class="score-accent" style="background:{color}; color:{color};"></div>
    <div class="score-name" style="color:{color};">{html_escape(name)}</div>
    <div class="score-number">{score}<span>/100</span></div>
    <div class="progress-track">
        <div class="progress-fill" style="width:{score}%; background:{color}; box-shadow:0 0 10px {color}40;"></div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


def donut_contributions(env, soc, gov, eth, overall):
    raw = {
        "Environmental": safe_score(env) * 0.40,
        "Social": safe_score(soc) * 0.25,
        "Governance": safe_score(gov) * 0.15,
        "Ethics": safe_score(eth) * 0.20,
    }

    raw_total = sum(raw.values())
    overall = safe_score(overall)
    scale = overall / raw_total if raw_total > 0 else 0

    scaled = {key: max(0, val * scale) for key, val in raw.items()}
    scaled["Remaining"] = max(0, 100 - overall)
    return scaled


def render_overall_donut(env, soc, gov, eth, overall):
    overall = safe_score(overall)
    values_dict = donut_contributions(env, soc, gov, eth, overall)

    labels = list(values_dict.keys())
    values = list(values_dict.values())
    colors = [COLORS[label] for label in labels]

    def rgba(hex_color, alpha):
        color = hex_color.lstrip("#")
        red, green, blue = (
            int(color[index:index + 2], 16)
            for index in (0, 2, 4)
        )
        return f"rgba({red},{green},{blue},{alpha})"

    glow_colors = [
        rgba(COLORS[label], 0.16)
        if label != "Remaining"
        else "rgba(255,255,255,0.04)"
        for label in labels
    ]

    fig = go.Figure()

    fig.add_trace(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.68,
            sort=False,
            direction="clockwise",
            domain={"x": [0.01, 0.99], "y": [0.0, 0.97]},
            marker={
                "colors": ["rgba(0,0,0,0.30)"] * len(labels),
                "line": {"width": 0},
            },
            textinfo="none",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.add_trace(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.69,
            sort=False,
            direction="clockwise",
            domain={"x": [0.0, 1.0], "y": [0.01, 1.0]},
            marker={"colors": glow_colors, "line": {"width": 0}},
            textinfo="none",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    fig.add_trace(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.72,
            sort=False,
            direction="clockwise",
            domain={"x": [0.035, 0.965], "y": [0.035, 0.965]},
            marker={"colors": colors, "line": {"width": 0}},
            textinfo="none",
            hovertemplate="<b>%{label}</b><br>%{value:.1f}<extra></extra>",
            showlegend=False,
        )
    )

    fig.update_layout(
        height=470,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel={
            "bgcolor": "rgba(10,8,27,0.96)",
            "bordercolor": "rgba(55,167,231,0.28)",
            "font": {"color": "#F5F7FF", "size": 13},
        },
        annotations=[
            {
                "text": f"<b>{overall}</b>",
                "x": 0.5,
                "y": 0.535,
                "font": {"size": 38, "color": "#F5F7FF"},
                "showarrow": False,
            },
            {
                "text": "/100",
                "x": 0.5,
                "y": 0.455,
                "font": {"size": 14, "color": "rgba(245,247,255,0.65)"},
                "showarrow": False,
            },
            {
                "text": "Overall Score",
                "x": 0.5,
                "y": 0.405,
                "font": {"size": 12, "color": "rgba(245,247,255,0.45)"},
                "showarrow": False,
            },
        ],
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False, "responsive": True},
    )


def render_recommendation(score):
    label, color = recommendation_badge(score)
    st.markdown(
        f"""
<div class="recommendation" style="color:{color}; box-shadow:0 0 16px {color}1A;">
    {html_escape(label)}
</div>
""",
        unsafe_allow_html=True,
    )


def render_compact_recommendation(score):
    label, color = recommendation_badge(score)
    st.markdown(
        f"""
<div class="recommendation-compact"
     style="color:{color}; border-color:{color}3D; box-shadow:0 0 12px {color}12;">
    {html_escape(label)}
</div>
""",
        unsafe_allow_html=True,
    )


def render_compact_confidence(confidence):
    confidence = safe_confidence(confidence)
    if confidence <= 30:
        label, color = "Low confidence", "#FF5A5A"
    elif confidence <= 60:
        label, color = "Medium confidence", "#FFD166"
    else:
        label, color = "High confidence", "#16FFBB"

    st.markdown(
        f"""
<div class="confidence-compact"
     style="color:{color}; border-color:{color}3D; box-shadow:0 0 12px {color}12;">
    {label.title()}
</div>
""",
        unsafe_allow_html=True,
    )


def render_timeline_item(range_label, label, color, active_range):
    active = " active" if range_label == active_range else ""
    return f"""
<div class="timeline-item{active}">
    <div class="timeline-range">{html_escape(range_label)}</div>
    <div class="timeline-dot" style="--dot:{color};"></div>
    <div class="timeline-label">{html_escape(label)}</div>
</div>
"""


def render_score_guide(overall_score):
    active = active_score_range(overall_score)
    items = [
        ("0-39", "Not Rec.", "#FF5A5A"),
        ("40-54", "Low", "#FFB347"),
        ("55-69", "Moderate", "#FFD166"),
        ("70-84", "Conscious", "#16FFBB"),
        ("85-100", "Highly", "#37A7E7"),
    ]
    html = "".join(render_timeline_item(r, l, c, active) for r, l, c in items)
    st.markdown(
        f"""
<div class="info-card timeline-card">
    <div class="card-title"><span>Score Guide</span></div>
    <p style="color:rgba(245,247,255,0.65); margin:0 0 .45rem 0; font-size:.8rem;">
        Score Guide shows how conscious the product is based on the final weighted ESGE score.
    </p>
    <div class="timeline-track" style="--timeline-count:5;">{html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_confidence_card(confidence):
    confidence = safe_confidence(confidence)
    active = active_confidence_range(confidence)
    items = [
        ("0-30", "Low", "#FF5A5A"),
        ("31-60", "Medium", "#FFD166"),
        ("61-100", "High", "#16FFBB"),
    ]
    html = "".join(render_timeline_item(r, l, c, active) for r, l, c in items)
    st.markdown(
        f"""
<div class="info-card timeline-card">
    <div class="card-title"><span>Confidence</span></div>
    <p style="color:rgba(245,247,255,0.65); margin:0 0 .45rem 0; font-size:.8rem;">
        Confidence shows how much supporting evidence is available.
    </p>
    <div class="timeline-track" style="--timeline-count:3;">{html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def bullet_list(items):
    clean = [html_escape(item) for item in items if item is not None and str(item).strip()]
    if not clean:
        clean = ["No evidence available."]
    return "<ul class='bullet-list'>" + "".join(f"<li>{item}</li>" for item in clean) + "</ul>"


def append_unique(items, message):
    if message and message not in items:
        items.append(message)


def translate_evidence_entries(entries, topic_rules, fallback):
    translated = []
    if not isinstance(entries, list):
        return translated

    for entry in entries:
        text = str(entry or "").strip().lower()
        if not text:
            continue

        matched = False
        for keywords, message in topic_rules:
            if any(keyword in text for keyword in keywords):
                append_unique(translated, message)
                matched = True
                break
        if not matched:
            append_unique(translated, fallback)

    return translated


def render_evidence_summary(product):
    product_items = []
    matched_labels = product.get("matched_labels", [])
    if isinstance(matched_labels, list) and matched_labels:
        clean_labels = [
            str(label).strip()
            for label in matched_labels[:8]
            if label is not None and str(label).strip()
        ]
        if clean_labels:
            product_items.append(
                "The following product labels influenced the score: "
                + ", ".join(clean_labels)
                + "."
            )
        else:
            product_items.append(
                "No sustainability or ethical certification labels were found for this product."
            )
    else:
        product_items.append(
            "No sustainability or ethical certification labels were found for this product."
        )

    ecoscore_grade = str(
        product.get("ecoscore_grade")
        or product.get("ecoscore_grade_used")
        or ""
    ).strip().lower()
    if ecoscore_grade in {"a", "b"}:
        product_items.append(
            "The Eco-Score is relatively strong and supports the environmental score."
        )
    elif ecoscore_grade == "c":
        product_items.append(
            "The Eco-Score is moderate and had a neutral to slightly positive environmental effect."
        )
    elif ecoscore_grade in {"d", "e"}:
        product_items.append(
            "The Eco-Score is low and reduced the environmental score."
        )
    else:
        product_items.append(
            "No Eco-Score was available, and missing data was not treated as negative evidence."
        )

    company_items = []
    company = product.get("wikirate_company")
    if company:
        company_items.append(f"Parent company was matched to {company}.")
    else:
        company_items.append(
            "No reliable parent company match was found, so no company-level adjustment was applied."
        )

    policy_evidence = product.get("wikirate_policy_evidence", [])
    policy_rules = [
        (
            ("modern slavery statement",),
            "Modern slavery disclosure evidence was found.",
        ),
        (
            ("anti-corruption", "anti corruption", "anti-bribery", "anti bribery"),
            "Anti-corruption policy evidence was found.",
        ),
        (
            ("supply chain transparency", "traceability", "supply chain disclosure"),
            "Supply-chain transparency evidence was found.",
        ),
        (
            ("worker grievance", "grievance mechanism"),
            "Worker grievance mechanism evidence was found.",
        ),
        (
            ("whistleblower", "whistleblowing"),
            "Whistleblower protection evidence was found.",
        ),
        (
            ("supplier code of conduct", "supplier code"),
            "A supplier code of conduct was found.",
        ),
        (
            ("freedom of association", "collective bargaining"),
            "Worker representation and collective bargaining policy evidence was found.",
        ),
        (
            ("living wage",),
            "Living wage commitment evidence was found.",
        ),
        (
            ("diversity", "inclusion"),
            "Diversity and inclusion policy evidence was found.",
        ),
        (
            ("human rights policy", "human rights risks", "human rights impacts"),
            "Human rights policy evidence was found.",
        ),
    ]
    policy_items = translate_evidence_entries(
        policy_evidence,
        policy_rules,
        "Positive company disclosure evidence was found.",
    )
    for item in policy_items:
        append_unique(company_items, item)

    adjustments = product.get("wikirate_company_adjustments", {})
    if isinstance(adjustments, dict):
        positive_areas = []
        if (adjustments.get("social") or 0) > 0:
            positive_areas.append("Social")
        if (adjustments.get("governance") or 0) > 0:
            positive_areas.append("Governance")
        if positive_areas:
            company_items.append(
                "Company policy evidence slightly improved the "
                + " and ".join(positive_areas)
                + " score"
                + ("s." if len(positive_areas) > 1 else ".")
            )

    concern_items = []
    performance_evidence = product.get("wikirate_performance_evidence", [])
    controversy_rules = [
        (
            ("child labour", "child labor"),
            "Child labour controversy evidence was found.",
        ),
        (
            ("forced labour", "forced labor", "modern slavery controversy"),
            "Forced labour or modern slavery controversy evidence was found.",
        ),
        (
            ("corruption", "bribery"),
            "Corruption or bribery controversy evidence was found.",
        ),
        (
            ("discrimination",),
            "Serious discrimination controversy evidence was found.",
        ),
        (
            ("human rights allegation", "human rights controversy"),
            "Serious human rights controversy evidence was found.",
        ),
        (
            ("greenwashing", "misleading sustainability"),
            "Greenwashing or misleading sustainability claim evidence was found.",
        ),
    ]
    controversy_items = translate_evidence_entries(
        performance_evidence,
        controversy_rules,
        "Serious controversy evidence was found.",
    )
    for item in controversy_items:
        append_unique(concern_items, item)

    ethics_reduced = (
        isinstance(adjustments, dict)
        and (adjustments.get("ethics") or 0) < 0
    )
    if ethics_reduced:
        concern_items.append("Controversy evidence reduced the Ethics score.")

    warnings = product.get("wikirate_warnings", [])
    warning_items = []
    if isinstance(warnings, list):
        for warning in warnings:
            text = str(warning or "").strip().lower()
            if not text:
                continue
            if "mixed company evidence" in text or "do not cancel out" in text:
                append_unique(
                    warning_items,
                    "Positive company policies do not cancel out controversy evidence.",
                )
            elif "limited to" in text or "bonuses capped" in text:
                append_unique(
                    warning_items,
                    "Positive company bonuses were capped because serious controversy evidence exists.",
                )
            elif "bonuses suppressed" in text:
                if "ethics" in text:
                    message = "Positive Ethics bonuses were not applied because serious controversy evidence exists."
                elif "social" in text:
                    message = "Positive Social bonuses were not applied because serious controversy evidence exists."
                elif "governance" in text:
                    message = "Positive Governance bonuses were not applied because serious controversy evidence exists."
                else:
                    message = "Some positive policy bonuses were not applied because serious controversy evidence exists."
                append_unique(warning_items, message)
            elif "severe controversy" in text:
                append_unique(
                    warning_items,
                    "Serious controversy evidence was found alongside positive company policies.",
                )
            elif "could not be resolved" in text:
                append_unique(
                    warning_items,
                    "The parent company could not be matched reliably.",
                )
            elif "metric requests failed" in text or "enrichment failed" in text:
                append_unique(
                    warning_items,
                    "Some company evidence could not be retrieved and was not used.",
                )
            elif "no usable metric" in text:
                append_unique(
                    warning_items,
                    "No usable company evidence was found, and missing data did not affect the score.",
                )
            else:
                append_unique(
                    warning_items,
                    "Additional company-level caution was identified in the supporting evidence.",
                )

    for item in warning_items:
        append_unique(concern_items, item)

    if not controversy_items and not warning_items and not ethics_reduced:
        concern_items.append(
            "No major controversy warning was available in the supporting evidence."
        )
    concern_items.append("Missing data was not treated as negative evidence.")

    confidence = get_confidence_score(product)
    if confidence <= 30:
        confidence_level = "a low amount"
    elif confidence <= 60:
        confidence_level = "a medium amount"
    else:
        confidence_level = "a high amount"
    confidence_items = [
        f"Confidence is {confidence}/100, meaning the result is based on {confidence_level} of supporting evidence."
    ]

    groups = [
        ("Product-level information", product_items),
        ("Company-level information", company_items),
        ("Concerns / warnings", concern_items),
        ("Confidence", confidence_items),
    ]

    html = "".join(
        f"""
<div>
    <div class="bullet-group-title">{html_escape(title)}</div>
    {bullet_list(items)}
</div>
"""
        for title, items in groups
    )

    st.markdown(
        f"""
<div class="info-card">
    <div class="evidence-heading">
        <div class="evidence-heading-title">Evidence Summary</div>
        <div class="evidence-heading-subtitle">What influenced this score?</div>
    </div>
    <div class="bullet-groups">{html}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_technical_details(product):
    detail_columns = [
        "source", "barcode", "code", "categories", "labels",
        "ecoscore_grade", "ecoscore_score", "matched_labels",
        "matched_score_groups", "score_reasons", "wikirate_company",
        "wikirate_company_found", "wikirate_company_adjustments",
        "wikirate_confidence_score", "wikirate_confidence_label",
        "wikirate_policy_evidence", "wikirate_performance_evidence",
        "wikirate_warnings",
    ]
    data = {col: product.get(col) for col in detail_columns if col in product}
    if data:
        st.dataframe(pd.DataFrame([data]), use_container_width=True)
    else:
        st.caption("No technical details available.")


# Header
st.markdown(
    """
<section>
    <div class="hero-row">
        <div class="logo-box">
            <svg class="logo-icon" viewBox="0 0 32 32" aria-hidden="true">
                <path d="M3.5 5.5h3.1l2.1 11.7a2.4 2.4 0 0 0 2.4 2h11.7"></path>
                <path d="M7.3 8.5h18.2l-2.1 7.8H8.7"></path>
                <path d="m12.3 12.4 2.2 2.1 4.4-4.5"></path>
                <circle cx="11.2" cy="24.2" r="1.7"></circle>
                <circle cx="22.1" cy="24.2" r="1.7"></circle>
            </svg>
        </div>
        <h1 class="brand-title">TrustShelf</h1>
    </div>
    <div class="tagline">Make Better Buying Decisions</div>
    <p class="subtitle">
        Search any product to understand its environmental, social and ethical impact before you buy.
    </p>
</section>
<div class="neon-center-divider"></div>
""",
    unsafe_allow_html=True,
)

# Search
with st.form("product_search_form"):
    barcode_search = st.toggle("Barcode search", value=False)
    search_mode = "Barcode" if barcode_search else "Product name"

    query_col, button_col = st.columns([4, 1], vertical_alignment="bottom")
    with query_col:
        query = st.text_input("Enter product name or barcode", placeholder="Try: Nutella, shampoo, chocolate, or a barcode")
    with button_col:
        analyze_clicked = st.form_submit_button("Analyze")

if analyze_clicked and query.strip():
    with st.spinner("Searching and scoring products..."):
        results = run_search(search_mode, query.strip(), source_filter=None)

    if results.empty:
        st.warning("No matching products found.")
        st.session_state.pop("results", None)
    else:
        st.session_state["results"] = results.reset_index(drop=True)

# Results
if "results" in st.session_state:
    results = st.session_state["results"]
    product_options = {product_label(row): idx for idx, row in results.iterrows()}

    selected_label = st.selectbox("Select product", list(product_options.keys()))
    selected_product = results.loc[product_options[selected_label]].to_dict()

    with st.spinner("Checking company-level evidence..."):
        product = enrich_selected_product_with_wikirate(selected_product)

    environmental_score = get_dimension_score(product, "environmental")
    social_score = get_dimension_score(product, "social")
    governance_score = get_dimension_score(product, "governance")
    ethics_score = get_dimension_score(product, "ethics")
    overall_score = get_overall_score(product)
    confidence_score = get_confidence_score(product)

    st.markdown('<div class="neon-center-divider"></div>', unsafe_allow_html=True)

    product_col, right_col = st.columns([0.9, 2.1], vertical_alignment="top")

    with product_col:
        render_product_card(product)

    with right_col:
        with st.container(key="score_overview_card"):
            st.markdown(
                '<div class="score-overview-heading">Score Overview</div>',
                unsafe_allow_html=True,
            )
            donut_col, cards_col = st.columns(
                [1.45, 1],
                vertical_alignment="center",
            )

            with donut_col:
                with st.container(key="donut_group"):
                    render_overall_donut(
                        environmental_score,
                        social_score,
                        governance_score,
                        ethics_score,
                        overall_score,
                    )
                    render_compact_recommendation(overall_score)
                    render_compact_confidence(confidence_score)

            with cards_col:
                render_score_card(
                    "Environmental",
                    environmental_score,
                    COLORS["Environmental"],
                )
                render_score_card("Social", social_score, COLORS["Social"])
                render_score_card(
                    "Governance",
                    governance_score,
                    COLORS["Governance"],
                )
                render_score_card("Ethics", ethics_score, COLORS["Ethics"])

    st.markdown('<div class="neon-center-divider"></div>', unsafe_allow_html=True)

    render_score_guide(overall_score)
    render_confidence_card(confidence_score)
    st.markdown('<div class="neon-center-divider"></div>', unsafe_allow_html=True)

    render_evidence_summary(product)

    with st.expander("Technical details"):
        render_technical_details(product)
