# WorthIt — NLP-Based Personalized Purchase Decision System

WorthIt recommends laptops by considering **what the user values** and **which compromises they explicitly accept**. It combines a keyword/LLM-assisted query parser, review-derived aspect sentiment scores, a bounded-sacrifice ranking method, and optional price-efficiency scoring.

## What is implemented

- PostgreSQL storage for products, reviews, aspect mentions, and aggregated aspect scores.
- Review aspect/sentiment extraction (`core/absa.py`) and aggregation (`core/aggregate.py`). The default ABSA backend is a local rule/lexicon approach; it is not a transformer model.
- Query parsing for budget, priorities, and explicit sacrifices (`core/parser.py`). Without `ANTHROPIC_API_KEY`, the app uses its keyword fallback.
- Candidate retrieval and ranking (`core/retrieve.py`, `core/ranker.py`).
- Streamlit comparison of floor-off and floor-on results (`ui/app.py`).
- FastAPI endpoints for health and recommendations (`api/main.py`).
- Evaluation scripts for 36 labelled queries (`eval/`).

## Quick start — local Python + Docker database

Prerequisites: Python 3.11+ and Docker Desktop.

1. In PowerShell, open the project folder.
2. Create your local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Start PostgreSQL:

   ```powershell
   docker compose up -d db
   ```

4. Create a virtual environment and install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

5. Create database tables:

   ```powershell
   python scripts/01_init_db.py
   ```

6. Load or fetch data. If the database is already populated, **do not repeat the initial ingestion just to launch the app**. For a new dataset, set `REEF_API_KEY` in your private `.env`, then run:

   ```powershell
   python scripts/02_fetch_products.py
   python scripts/03_fetch_reviews.py
   python scripts/04_run_absa.py
   python scripts/05_sanity_check.py
   ```

7. Start the UI:

   ```powershell
   streamlit run ui/app.py
   ```

   Open the local URL printed by Streamlit (usually `http://localhost:8501`). Enter a query with a budget, such as `laptop under 80000 with great performance, dont mind heating`.

## API (optional)

With the database running and the Python dependencies installed:

```powershell
uvicorn api.main:app --reload
```

- Health: `GET http://127.0.0.1:8000/health`
- Interactive API docs: `http://127.0.0.1:8000/docs`
- Recommendation: `POST http://127.0.0.1:8000/recommend`

Example request body:

```json
{
  "query": "laptop under 80000 with great performance, dont mind heating",
  "top_k": 5,
  "use_floor": true
}
```

The query needs a maximum budget so the candidate set can be filtered. The UI currently accesses PostgreSQL directly; the API is a separate optional interface.

## Docker Compose (full demo)

Copy `.env.example` to `.env`, then run:

```powershell
docker compose up --build -d
python scripts/01_init_db.py
```

The last command assumes your local Python dependencies are installed and your local `.env` points at `localhost:5432`. If you initialize from the host while `DB_URL` is configured for a container hostname, temporarily set a host-local `DB_URL` or initialize the tables from a one-off container. For a pre-populated local database, no ingestion is needed. UI: `http://localhost:8501`; API docs: `http://localhost:8000/docs`.

The Docker Compose setup starts services but **does not automatically fetch product/review data**. Data ingestion is an explicit step because ReefAPI calls may consume credits.

## Refreshing data

The product fetch script upserts the current product metadata. To check existing products for new review text, run:

```powershell
python scripts/02_fetch_products.py
python scripts/03_fetch_reviews.py --refresh
python scripts/04_run_absa.py
```

`--refresh` checks review pages for products that already have reviews and inserts only review text not seen in the database. It consumes ReefAPI credits; use it only when you want fresh data and have a valid key. ABSA processes only reviews marked unprocessed, then refreshes aggregated aspect scores.

## Evaluation

The primary evaluation is the **unguarded** run:

```powershell
python eval/run_eval.py
```

It reports nDCG@10 and MAP@10 for `rating_sort`, `weight_zero`, `floor_only`, and `full`, followed by paired bootstrap comparisons. The separate guard experiment is post-hoc:

```powershell
python eval/guarded.py
```

The labelled set contains 36 queries and 451 product-query judgments. Labels were manually assigned by one annotator using aspect scores related to those used by the ranker; this creates potential circularity and must be stated as a limitation. Do not present the guard experiment as the primary result or claim every component improves every metric.

Additional diagnostics:

```powershell
python eval/status.py
python eval/diagnose.py
```

## Configuration

Important environment variables are listed in `.env.example`. `FLOOR_GUARD=0` keeps the primary ranking unguarded. `FLOOR_PERCENTILE=35`, `FLOOR_LAMBDA=3.0`, `PRIORITY_GAMMA=0.7`, `USE_PRICE_EFFICIENCY=1`, and `PRICE_WEIGHT=0.20` are the reported project defaults.

## Security

- Never commit or share `.env`; it may contain passwords and API keys.
- `.env.example` contains placeholders only.
- Do not include real credentials in reports, screenshots, or ZIP submissions.

## Project limitations

- The default aspect sentiment model is lexicon/rule-based and may miss context or sarcasm.
- The labelled evaluation uses a single annotator and aspect scores related to the ranking features.
- The current product pool is small (the reported dataset: 25 laptops and 493 reviews), so results should not be generalized to every laptop or marketplace.
- Price efficiency is pool-relative: scores depend on the candidate set for a query.
