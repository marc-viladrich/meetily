# Meetily fork

- Create normal pull requests ready for review; no drafts unless Marc explicitly asks.
- Keep `main` as the upstream baseline. Develop on `marc/meeting-transcripts` and fetch updates from `upstream`.
- Supported app code lives in `frontend/src-tauri` and `frontend/src`. Do not add dependencies on the archived FastAPI backend.
- Native transcripts and speaker names belong to Meetily's SQLite database. Do not create a parallel UI transcript store.
- Diarization identifies voices, not Teams participants. Preserve ambiguous and mixed turns explicitly. Never invent participant names or word timing.
- The macOS Teams microphone signal is a recording reminder, not proof that a meeting has started. Never automatically record based only on an opened process, URL, or microphone preview.
- The native speaker helper runs in a separate process so its ONNX Runtime cannot collide with Parakeet. Generated models and runtime binaries are ignored; prepare them with pinned checksums in `tools/speaker-engine/prepare.py`.
- Validate native changes with TypeScript, focused Rust/database tests, the real app, and real stored values. Keep private audio, transcripts, database backups and proof recordings out of Git.

- Resource constraint: Marc reported severe fan/heat load. Keep automatic analysis off. Do not run heavy builds, inference, and recording tests in parallel. The one-thread/low-priority profile still needs isolated resource measurements before enabling automatic speaker analysis.
