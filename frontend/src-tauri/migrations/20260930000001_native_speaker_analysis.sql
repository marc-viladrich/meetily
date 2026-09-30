CREATE TABLE speaker_labels (
  meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  speaker TEXT NOT NULL,
  name TEXT NOT NULL,
  PRIMARY KEY (meeting_id, speaker)
);
CREATE TABLE speaker_jobs (
  meeting_id TEXT PRIMARY KEY REFERENCES meetings(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  requested_speakers INTEGER NOT NULL,
  error TEXT,
  result TEXT,
  updated_at TEXT NOT NULL
);
