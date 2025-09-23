CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE projects (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  sponsor TEXT,
  start_date DATE,
  target_end DATE,
  status TEXT
);

CREATE TABLE meetings (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id),
  title TEXT,
  start_ts TIMESTAMPTZ,
  end_ts   TIMESTAMPTZ,
  cadence  TEXT,
  attendees TEXT[]
);

CREATE TABLE minutes (
  id SERIAL PRIMARY KEY,
  meeting_id INT REFERENCES meetings(id),
  ts TIMESTAMPTZ DEFAULT now(),
  source_url TEXT,
  raw_text   TEXT,
  embedding  vector(768)
);

DO $$ BEGIN
  CREATE TYPE item_type AS ENUM ('decision','action','accomplishment','risk','issue','blocker');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE item_status AS ENUM ('open','in_progress','done');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE items (
  id SERIAL PRIMARY KEY,
  minutes_id INT REFERENCES minutes(id) ON DELETE CASCADE,
  project_id INT REFERENCES projects(id) ON DELETE CASCADE,
  type item_type NOT NULL,
  title TEXT,
  detail TEXT,
  owner TEXT,
  due_date DATE,
  status item_status DEFAULT 'open',
  priority INT,
  severity INT,
  evidence_start INT,
  evidence_end   INT,
  confidence REAL
);

CREATE INDEX idx_items_project_type ON items(project_id, type);
CREATE INDEX idx_items_due ON items(due_date) WHERE status <> 'done';
CREATE INDEX idx_minutes_embedding ON minutes USING ivfflat (embedding vector_cosine_ops);
