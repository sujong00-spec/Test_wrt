CREATE TABLE family_data (
  owner_id TEXT PRIMARY KEY NOT NULL,
  document TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0
);
