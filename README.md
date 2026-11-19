# Real Estate Chatbot v3 (DarGlobal + Wasalt)

Production-ready hybrid RAG chatbot combining **Reciprocal Rank Fusion (RRF)**, JSON-LD + Next.js structured extraction, accurate currency handling, and strict hard-constraint enforcement.

## Architecture

```
┌─────────────┐    HTTP     ┌──────────────┐    pgvector + FTS    ┌──────────────┐
│  React/Vite │ ──────────► │  FastAPI     │ ───────────────────► │  PostgreSQL  │
│  (nginx)    │             │  (backend)   │                       │  + pgvector  │
└─────────────┘             └──────────────┘                       └──────────────┘
                                   │
                              OpenRouter
                              (LLM API)
```

## Key Features in v3

| Feature | Detail |
|---|---|
| **Hybrid Retrieval (RRF)** | Combines `pgvector` cosine similarity + PostgreSQL FTS via Reciprocal Rank Fusion |
| **JSON-LD Priority** | Schema.org JSON-LD extracted first, Next.js `__NEXT_DATA__` second, HTML specs third |
| **Accurate Currency** | Currency extracted from page content only — never guessed |
| **Accurate Dates** | `last_updated` reflects page data; `scraped_at` reflects crawl time |
| **Hard Filters** | Country, city, bedrooms (including listed ranges), budget, currency filters strictly enforced |
| **No Silent Relaxation** | Returns "no match" message instead of wrong results |

## Project Structure

```
realestate-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app
│   │   ├── rag.py         # Hybrid RRF retrieval + filter detection
│   │   ├── llm.py         # OpenRouter LLM call
│   │   └── db.py          # psycopg3 + pgvector connection
│   ├── scraper/
│   │   └── ingest.py      # JSONL → PostgreSQL ingestion pipeline
│   ├── requirements.txt
│   └── Dockerfile
├── scraper/
│   ├── crawl.py           # Sitemap crawler (darglobal + wasalt)
│   ├── common.py          # HTML/JSON-LD/Next.js extraction helpers
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/App.jsx        # React chat UI
│   ├── nginx.conf         # nginx reverse proxy
│   ├── Dockerfile
│   └── package.json
├── db/
│   └── init.sql           # PostgreSQL schema + pgvector setup
├── docker-compose.yml
├── .env.example
└── README.md
```

## Quickstart

### Prerequisites
- Docker & Docker Compose v2
- An API key from [OpenRouter](https://openrouter.ai) or [Groq](https://console.groq.com)

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY or GROQ_API_KEY
```

### 2. Scrape data (run once, outside Docker or via profile)

**Option A — local Python:**
```bash
cd scraper
pip install -r requirements.txt
playwright install chromium
python crawl.py darglobal 300
python crawl.py wasalt 300
```

**Option B — Docker:**
```bash
docker compose --profile tools run --rm scraper python crawl.py darglobal 300
docker compose --profile tools run --rm scraper python crawl.py wasalt 300
```

To add more listings without replacing the existing JSONL data, use the scraper's append mode:

```bash
docker compose --profile tools run --rm scraper python crawl.py wasalt 47 --append
docker compose --profile tools run --rm ingest
```

### 3. Start database and ingest

```bash
# Start only DB
docker compose up -d db

# Run ingestion (exits when done)
docker compose --profile tools run --rm ingest
```

### 4. Start full stack

```bash
docker compose up -d --build
```

Open **http://localhost** in your browser.

### 5. Restart / update

```bash
docker compose down
docker compose up -d --build
```

## Deploy to Render

Render deploys the frontend, backend, and database as separate services; it does not run this Docker Compose file as one stack.

1. Push the repository to GitHub. Keep `.env` out of the repository.
2. Create a Render PostgreSQL database in the same region as the backend. Apply `db/init.sql` to the new database using its SQL console or `psql`.
3. Create a Render **Docker web service** for the backend from the repository root. Set the Dockerfile path to `backend/Dockerfile`, health-check path to `/health`, and configure:
   - `DATABASE_URL`: the database's internal connection URL
   - `CORS_ORIGINS`: the exact public URL of the frontend
   - `OPENROUTER_API_KEY` or `GROQ_API_KEY`: a provider key
   - Optional model variables from the environment-variable table
4. Load the property data once. The backend image includes `data/*.jsonl`. From a machine with Docker, build the image and run the importer against the database's external connection URL:

   ```powershell
   docker build -f backend/Dockerfile -t realestate-chatbot-backend .
   $env:DATABASE_URL = "<Render external database URL>"
   docker run --rm -e DATABASE_URL realestate-chatbot-backend python -m scraper.ingest
   Remove-Item Env:DATABASE_URL
   ```

5. Create a Render **Static Site** for the frontend. Set the root directory to `frontend`, build command to `npm ci && npm run build`, and publish directory to `dist`. Set `VITE_API_BASE_URL` to the backend's public URL, then set the backend's `CORS_ORIGINS` to the resulting frontend URL.
6. Open the frontend URL and test a property search. Keep provider and database credentials in Render environment settings, never in GitHub.

The first backend start downloads the embedding model if it is not already cached. Allow extra startup time and use an instance with enough memory for the model.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | One provider key required | OpenRouter API key |
| `OPENROUTER_MODEL` | optional | Model slug; defaults to the configured OpenRouter fallback list |
| `GROQ_API_KEY` | One provider key required | Optional Groq API key |
| `GROQ_MODEL` | optional | Model slug; defaults to the configured Groq fallback list |
| `DATABASE_URL` | auto | Set by compose from `POSTGRES_*` vars |
| `POSTGRES_USER` | optional | Default: `app` |
| `POSTGRES_PASSWORD` | optional | Default: `app` |
| `POSTGRES_DB` | optional | Default: `realestate` |
| `EMBED_MODEL` | optional | Default: `BAAI/bge-small-en-v1.5` |
| `CORS_ORIGINS` | optional | Comma-separated browser origins; defaults to local development origins |
| `VITE_API_BASE_URL` | Render frontend | Public URL of the backend; leave unset for the local nginx proxy |

## Supported Filter Queries

The chatbot understands natural language filters:

- **City:** "in Dubai", "in Riyadh", "in London"
- **Country:** "in UAE", "in Saudi Arabia"  
- **Budget:** "under SAR 2 million", "below AED 500k", "max $300,000"
- **Bedrooms:** "3 bedroom", "2-bed", "studio"
- **Currency:** "SAR", "AED", "USD", "GBP"
- **Property type:** "villa", "apartment", "penthouse", "townhouse"
- **Source:** "Dar Global", "Wasalt"

## Development

```bash
# Backend only (hot reload)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend only
cd frontend
npm install
npm run dev
```
