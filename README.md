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
