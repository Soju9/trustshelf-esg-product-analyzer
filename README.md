# TrustShelf - ESG Product Analyzer

TrustShelf is a Streamlit application that helps users evaluate consumer products through environmental, social, governance, and ethics signals.

The app searches product data from Open Food Facts, Open Beauty Facts, and Open Products Facts, applies a transparent scoring model, and optionally enriches results with company-level evidence from WikiRate.

This project was created collaboratively as a final project for the WBS Coding School Data Science / AI program.

## Equal Authorship

This repository is one of two independently owned portfolio copies of the same collaborative project.

Equal contributors:

- Nicolas Menges - GitHub: https://github.com/Soju9
- Khadija Al Shinno - GitHub: https://github.com/khadijaAL15

Neither repository is intended to imply that one contributor owns the work and the other only forked it.

## Features

- Product search by name
- Barcode search
- Data retrieval from:
  - Open Food Facts
  - Open Beauty Facts
  - Open Products Facts
- ESGE scoring:
  - Environmental
  - Social
  - Governance
  - Ethics
- Overall weighted product score
- Confidence score based on available evidence
- Product-level label and Eco-Score interpretation
- Optional company-level enrichment using WikiRate and Wikidata
- Streamlit dashboard with product image, score overview, evidence summary, and technical details

## Tech Stack

- Python
- Streamlit
- Pandas
- NumPy
- Requests
- Plotly
- Open Food Facts APIs
- Open Beauty Facts API
- Open Products Facts API
- WikiRate API
- Wikidata API

## Project Structure

```text
.
├── app.py
├── app_backend.py
├── wikirate_lookup.py
├── demo_wikirate_lookup.py
├── wikirate_integration.md
├── Data/
├── Processed/
├── Raw/
├── Notebooks/
├── requirements.txt
├── .env.example
├── .gitignore
├── AUTHORS.md
└── LICENSE
```

## How The Scoring Works

The base score starts from product-level evidence gathered from the Open Facts ecosystem.

Product-level signals include:

- Open Facts labels
- Eco-Score, where available
- Product category and source database
- Confidence mapping based on available evidence

The final overall score combines four dimensions:

| Dimension | Weight |
|---|---:|
| Environmental | 40% |
| Social | 25% |
| Governance | 15% |
| Ethics | 20% |

Missing data is not treated as negative evidence. Instead, limited evidence reduces the confidence score.

## Score Interpretation

| Score Range | Meaning |
|---:|---|
| 0-39 | Not Recommended |
| 40-54 | Low Conscious Choice |
| 55-69 | Moderately Conscious Choice |
| 70-84 | Conscious Choice |
| 85-100 | Highly Conscious Choice |

## Confidence Interpretation

The confidence score reflects how much supporting evidence was available.

| Confidence Range | Meaning |
|---:|---|
| 0-30 | Low confidence |
| 31-60 | Medium confidence |
| 61-100 | High confidence |

## Optional WikiRate Enrichment

The WikiRate layer adds company-level context.

Example flow:

```text
Product brand
-> cleaned brand name
-> Wikidata company / parent company lookup
-> WikiRate company profile lookup
-> selected ESG metrics
-> optional Social, Governance, and Ethics adjustments
```

Company-level evidence does not replace product-level scoring. It only adds a transparent enrichment layer.

Positive company policy evidence gives small bonuses. Serious controversy signals can reduce Social, Governance, or Ethics scores. Missing company data does not reduce the score.

## Setup

Clone the repository:

```bash
git clone https://github.com/YOUR-USERNAME/trustshelf-esg-product-analyzer.git
cd trustshelf-esg-product-analyzer
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Activate it on macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Optional: create a `.env` file if you want WikiRate enrichment:

```env
WIKIRATE_API_KEY=your_wikirate_api_key_here
```

Run the app:

```bash
streamlit run app.py
```

## Example Searches

Try searching for:

```text
Nutella
Milka
shampoo
chocolate
Nivea
Persil
```

You can also use barcode search from the toggle inside the app.

## Data Sources

- Open Food Facts
- Open Beauty Facts
- Open Products Facts
- WikiRate
- Wikidata

## Main Files

| File / Folder | Purpose |
|---|---|
| `app.py` | Streamlit frontend and visual dashboard |
| `app_backend.py` | Product search, API retrieval, scoring, confidence logic, and enrichment integration |
| `wikirate_lookup.py` | WikiRate and Wikidata company-level enrichment |
| `demo_wikirate_lookup.py` | Small demo script for testing WikiRate enrichment |
| `wikirate_integration.md` | Notes explaining the WikiRate integration design |
| `Data/` | Label and confidence mapping files |
| `Processed/` | Processed scoring-ready sample datasets |
| `Raw/` | Raw API sample data |
| `Notebooks/` | Exploration, ETL, scoring, and backend test notebooks |

## Limitations

- Product data depends on external Open Facts databases and may be incomplete.
- API availability and returned fields can change over time.
- ESG scoring is based on transparent project-defined rules, not certified ESG ratings.
- Missing data lowers confidence but is not treated as negative evidence.
- WikiRate enrichment requires an API key and may not find every company.
- Company-level evidence is approximate and should be interpreted as context, not proof.

## Educational Context

This project was developed as a final project for the WBS Coding School Data Science / AI program.

It demonstrates:

- API integration
- ETL and data cleaning
- Rule-based scoring logic
- Confidence scoring
- Streamlit dashboard development
- Product-level and company-level ESG data modeling
- Collaborative project delivery

## License

This project is released under the MIT License.

See `LICENSE` for details.
