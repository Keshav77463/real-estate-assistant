CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
  id SERIAL PRIMARY KEY,
  source TEXT NOT NULL,                  -- 'darglobal' | 'wasalt'
  url TEXT UNIQUE NOT NULL,
  doc_type TEXT,                         -- 'project' | 'listing' | 'page'
  title TEXT,
  developer TEXT,
  brand_partner TEXT,
  city TEXT,
  district TEXT,
  country TEXT,
  transaction_type TEXT,                 -- 'sale' | 'rent' | 'daily_rental' | 'off_plan'
  property_type TEXT,                    -- 'villa' | 'apartment' | 'penthouse' | 'land' | 'townhouse' | 'duplex' | 'residential_tower'
  unit_types TEXT,
  status TEXT,                           -- 'Under Development' | 'Completed' | 'Upcoming' | 'Active'
  completion_date TEXT,
  price NUMERIC,
  currency TEXT,
  area_sqm NUMERIC,
  bedrooms INT,
  bathrooms INT,
  furnishing TEXT,
  amenities TEXT[],
  fixtures TEXT[],
  rega_license TEXT,
  last_updated TEXT,
  raw JSONB,
  scraped_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chunks (
  id SERIAL PRIMARY KEY,
  doc_id INT REFERENCES documents(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  embedding vector(384),
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE INDEX chunks_emb_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX docs_filter_idx ON documents (source, city, country, property_type, status, currency);
CREATE INDEX docs_num_idx ON documents (price, bedrooms, area_sqm);
