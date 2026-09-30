//! Native UI integration: reuse saved transcript text, add only local voice analysis.
//! Speaker IDs are voice clusters, never Teams participant identities.
use crate::state::AppState;
use anyhow::{anyhow, Result};
use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sqlx::{FromRow, SqlitePool};
use std::{
    collections::BTreeMap,
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::Mutex,
};
use tauri::{AppHandle, Emitter, Manager, Runtime};
use tauri_plugin_store::StoreExt;

static ANALYSIS_LOCK: Lazy<tokio::sync::Mutex<()>> = Lazy::new(|| tokio::sync::Mutex::new(()));
static QUEUE_LOCK: Lazy<tokio::sync::Mutex<()>> = Lazy::new(|| tokio::sync::Mutex::new(()));
static DIAGNOSTIC_LOCK: Mutex<()> = Mutex::new(());

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct SpeakerPreferences {
    pub enabled: bool,
    pub speaker_count: u32,
    pub teams_detection: bool,
}
impl Default for SpeakerPreferences {
    fn default() -> Self {
        Self {
            enabled: false,
            speaker_count: 2,
            teams_detection: false,
        }
    }
}

pub fn preferences<R: Runtime>(app: &AppHandle<R>) -> Result<SpeakerPreferences> {
    let store = app.store("speaker_preferences.json")?;
    match store.get("preferences") {
        Some(value) => Ok(serde_json::from_value(value)?),
        None => Ok(SpeakerPreferences {
            enabled: false,
            ..SpeakerPreferences::default()
        }),
    }
}

fn engine_dir<R: Runtime>(app: &AppHandle<R>) -> Result<PathBuf> {
    let bundled = app.path().resource_dir()?.join("resources/speaker-engine");
    if bundled.join("speaker-engine").is_file() {
        return Ok(bundled);
    }
    #[cfg(debug_assertions)]
    {
        let local = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/speaker-engine");
        if local.join("speaker-engine").is_file() {
            return Ok(local);
        }
    }
    Err(anyhow!("Speaker engine unavailable. Build the macOS ARM64 fork with tools/speaker-engine/prepare.py."))
}

#[derive(Debug, Serialize)]
pub struct SpeakerSettings {
    pub preferences: SpeakerPreferences,
    pub engine_available: bool,
    pub diagnostics_path: String,
}
#[tauri::command]
pub fn get_speaker_settings<R: Runtime>(app: AppHandle<R>) -> Result<SpeakerSettings, String> {
    (|| {
        Ok(SpeakerSettings {
            preferences: preferences(&app)?,
            engine_available: engine_dir(&app).is_ok(),
            diagnostics_path: app
                .path()
                .app_data_dir()?
                .join("diagnostics/events.jsonl")
                .to_string_lossy()
                .into(),
        })
    })()
    .map_err(|e: anyhow::Error| e.to_string())
}
#[tauri::command]
pub fn save_speaker_preferences<R: Runtime>(
    app: AppHandle<R>,
    preferences: SpeakerPreferences,
) -> Result<(), String> {
    if !(1..=8).contains(&preferences.speaker_count) {
        return Err("Choose 1–8 voices.".into());
    }
    if (preferences.enabled || preferences.teams_detection) && engine_dir(&app).is_err() {
        return Err("Speaker engine is unavailable in this build.".into());
    }
    let store = app
        .store("speaker_preferences.json")
        .map_err(|e| e.to_string())?;
    store.set(
        "preferences",
        serde_json::to_value(&preferences).map_err(|e| e.to_string())?,
    );
    store.save().map_err(|e| e.to_string())?;
    diagnostic(
        &app,
        "preferences_saved",
        serde_json::json!({"speaker_count": preferences.speaker_count, "enabled": preferences.enabled, "teams_detection": preferences.teams_detection}),
    );
    Ok(())
}

pub fn diagnostic<R: Runtime>(app: &AppHandle<R>, event: &str, data: serde_json::Value) {
    let result: Result<()> = (|| {
        let _guard = DIAGNOSTIC_LOCK
            .lock()
            .map_err(|_| anyhow!("Diagnostic lock poisoned"))?;
        let dir = app.path().app_data_dir()?.join("diagnostics");
        std::fs::create_dir_all(&dir)?;
        let path = dir.join("events.jsonl");
        if std::fs::metadata(&path)
            .map(|m| m.len() > 2_000_000)
            .unwrap_or(false)
        {
            std::fs::rename(&path, dir.join("events.previous.jsonl"))?;
        }
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)?;
        writeln!(
            file,
            "{}",
            serde_json::json!({"time": chrono::Utc::now().to_rfc3339(), "event": event, "data": data})
        )?;
        Ok(())
    })();
    if let Err(error) = result {
        log::warn!("Could not write local diagnostic event: {error}");
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct VoiceInterval {
    pub start: f64,
    pub end: f64,
    pub speaker: String,
}

/// Conservative segment assignment: keep mixed turns visible instead of inventing word timing.
pub fn assign_segment(start: Option<f64>, end: Option<f64>, intervals: &[VoiceInterval]) -> String {
    let (Some(start), Some(end)) = (start, end) else {
        return "Unklar".into();
    };
    if !start.is_finite() || !end.is_finite() || start >= end {
        return "Unklar".into();
    }
    let mut scores = BTreeMap::<&str, f64>::new();
    for interval in intervals {
        let overlap = (end.min(interval.end) - start.max(interval.start)).max(0.0);
        if overlap > 0.0 {
            *scores.entry(&interval.speaker).or_default() += overlap;
        }
    }
    let mut scores: Vec<_> = scores.into_iter().collect();
    scores.sort_by(|a, b| b.1.total_cmp(&a.1));
    let Some((speaker, coverage)) = scores.first() else {
        return "Unklar".into();
    };
    // A second voice with >= 20% of detected speech is meaningful, not a dominant-voice label.
    let total = scores.iter().map(|(_, amount)| amount).sum::<f64>();
    if scores
        .get(1)
        .is_some_and(|(_, amount)| *amount >= 0.2 * total && *amount >= 0.3)
    {
        return "Mehrere Stimmen".into();
    }
    if *coverage < (end - start) * 0.4 {
        return "Unklar".into();
    }
    speaker.to_string()
}

fn hash_file(path: &Path) -> Result<String> {
    let mut hash = Sha256::new();
    let mut file = std::fs::File::open(path)?;
    let mut buf = [0u8; 65536];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hash.update(&buf[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

#[derive(Clone, Debug, Serialize, PartialEq, FromRow)]
struct SavedTurn {
    id: String,
    transcript: String,
    audio_start_time: Option<f64>,
    audio_end_time: Option<f64>,
}
async fn saved_turns(pool: &SqlitePool, meeting_id: &str) -> Result<Vec<SavedTurn>> {
    Ok(sqlx::query_as("SELECT id, transcript, audio_start_time, audio_end_time FROM transcripts WHERE meeting_id = ? ORDER BY id")
        .bind(meeting_id).fetch_all(pool).await?)
}

async fn analyze<R: Runtime>(
    app: &AppHandle<R>,
    pool: &SqlitePool,
    meeting_id: &str,
    count: u32,
) -> Result<serde_json::Value> {
    let folder: Option<String> =
        sqlx::query_scalar("SELECT folder_path FROM meetings WHERE id = ?")
            .bind(meeting_id)
            .fetch_one(pool)
            .await?;
    let folder = PathBuf::from(folder.ok_or_else(|| anyhow!("This meeting has no saved audio."))?);
    let metadata: serde_json::Value =
        serde_json::from_slice(&std::fs::read(folder.join("metadata.json"))?)?;
    if metadata["status"] != "completed" {
        return Err(anyhow!("Wait until the recording is completed."));
    }
    let audio = crate::audio::retranscription::find_audio_file(&folder)?;
    let source = saved_turns(pool, meeting_id).await?;
    if source.is_empty() {
        return Err(anyhow!("This meeting has no saved transcript."));
    }
    let engine = engine_dir(app)?;
    let cache_dir = app.path().app_data_dir()?.join("speaker-cache");
    std::fs::create_dir_all(&cache_dir)?;
    let task_audio = audio.clone();
    let task_engine = engine.clone();
    let (fingerprint, intervals, cached) = tokio::task::spawn_blocking(move || -> Result<_> {
        let fingerprint = hash_file(&task_audio)?;
        // Cache invalidates if either bundled model or inference binary changes.
        let key = format!(
            "{:x}",
            Sha256::digest(format!(
                "native-v1:{fingerprint}:{count}:{}:{}:{}",
                hash_file(&task_engine.join("segmentation.onnx"))?,
                hash_file(&task_engine.join("embedding.onnx"))?,
                hash_file(&task_engine.join("speaker-engine"))?
            ))
        );
        let cache_path = cache_dir.join(format!("{key}.json"));
        if cache_path.exists() {
            let intervals: Vec<VoiceInterval> =
                serde_json::from_slice(&std::fs::read(cache_path)?)?;
            return Ok((fingerprint, intervals, true));
        }
        let samples = crate::audio::decoder::decode_audio_file(&task_audio)?.to_whisper_format();
        let mut pcm = tempfile::NamedTempFile::new()?;
        pcm.write_all(bytemuck::cast_slice(&samples))?;
        pcm.flush()?;
        let output = std::process::Command::new("/usr/bin/nice")
            .arg("-n")
            .arg("15")
            .arg(task_engine.join("speaker-engine"))
            .arg(task_engine.join("segmentation.onnx"))
            .arg(task_engine.join("embedding.onnx"))
            .arg(count.to_string())
            .arg(pcm.path())
            .output()?;
        if !output.status.success() {
            return Err(anyhow!("Local speaker engine failed ({})", output.status));
        }
        let intervals: Vec<VoiceInterval> = serde_json::from_slice(&output.stdout)?;
        let duration = samples.len() as f64 / 16000.0;
        for interval in &intervals {
            if !interval.start.is_finite()
                || !interval.end.is_finite()
                || interval.start < 0.0
                || interval.end <= interval.start
                || interval.end > duration + 1.0
                || !(1..=count).any(|n| interval.speaker == format!("Speaker {n}"))
            {
                return Err(anyhow!("Speaker engine returned invalid intervals."));
            }
        }
        let mut temp = tempfile::NamedTempFile::new_in(&cache_dir)?;
        serde_json::to_writer(&mut temp, &intervals)?;
        temp.persist(cache_path)?;
        Ok((fingerprint, intervals, false))
    })
    .await??;
    let verify_audio = audio.clone();
    if tokio::task::spawn_blocking(move || hash_file(&verify_audio)).await?? != fingerprint {
        return Err(anyhow!(
            "The audio changed during analysis. Retry after recording finishes."
        ));
    }
    let assignments: Vec<_> = source
        .iter()
        .map(|turn| {
            (
                turn,
                assign_segment(turn.audio_start_time, turn.audio_end_time, &intervals),
            )
        })
        .collect();
    let mut tx = pool.begin().await?;
    let current: Vec<SavedTurn> = sqlx::query_as("SELECT id, transcript, audio_start_time, audio_end_time FROM transcripts WHERE meeting_id = ? ORDER BY id")
        .bind(meeting_id).fetch_all(&mut *tx).await?;
    if current != source {
        return Err(anyhow!(
            "The transcript changed during analysis. Retry with the current transcript."
        ));
    }
    let previous: Option<i64> = sqlx::query_scalar(
        "SELECT requested_speakers FROM speaker_jobs WHERE meeting_id = ? AND result IS NOT NULL",
    )
    .bind(meeting_id)
    .fetch_optional(&mut *tx)
    .await?;
    if previous.is_some_and(|old| old != count as i64) {
        sqlx::query("DELETE FROM speaker_labels WHERE meeting_id = ?")
            .bind(meeting_id)
            .execute(&mut *tx)
            .await?;
    }
    for (turn, speaker) in &assignments {
        sqlx::query("UPDATE transcripts SET speaker = ? WHERE id = ? AND meeting_id = ?")
            .bind(speaker)
            .bind(&turn.id)
            .bind(meeting_id)
            .execute(&mut *tx)
            .await?;
    }
    let result = serde_json::json!({"voices": intervals.iter().map(|s| &s.speaker).collect::<std::collections::BTreeSet<_>>().len(), "segments": source.len(), "mixed": assignments.iter().filter(|(_, s)| s == "Mehrere Stimmen").count(), "unclear": assignments.iter().filter(|(_, s)| s == "Unklar").count(), "cached": cached});
    sqlx::query("UPDATE speaker_jobs SET status = 'completed', requested_speakers = ?, error = NULL, result = ?, updated_at = ? WHERE meeting_id = ?")
        .bind(count as i64).bind(result.to_string()).bind(chrono::Utc::now().to_rfc3339()).bind(meeting_id).execute(&mut *tx).await?;
    tx.commit().await?;
    diagnostic(
        app,
        "speaker_analysis_completed",
        serde_json::json!({"meeting_id": meeting_id, "result": result}),
    );
    Ok(result)
}

pub async fn start<R: Runtime>(
    app: AppHandle<R>,
    meeting_id: String,
    count: u32,
) -> Result<(), String> {
    if !(1..=8).contains(&count) {
        return Err("Choose 1–8 voices.".into());
    }
    if crate::audio::recording_commands::is_recording().await {
        return Err("Speaker analysis is deferred until the recording has ended.".into());
    }
    engine_dir(&app).map_err(|e| e.to_string())?;
    let queue_guard = QUEUE_LOCK.lock().await;
    let pool = app.state::<AppState>().db_manager.pool().clone();
    let pending: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM speaker_jobs WHERE meeting_id = ? AND status IN ('queued','running')",
    )
    .bind(&meeting_id)
    .fetch_one(&pool)
    .await
    .map_err(|e| e.to_string())?;
    if pending > 0 {
        return Err("This meeting is already queued for speaker analysis.".into());
    }
    // Keep the last successful count/result while retrying, so names invalidate correctly.
    sqlx::query("INSERT INTO speaker_jobs (meeting_id, status, requested_speakers, updated_at) VALUES (?, 'queued', ?, ?) ON CONFLICT(meeting_id) DO UPDATE SET status = 'queued', error = NULL, updated_at = excluded.updated_at")
        .bind(&meeting_id).bind(count as i64).bind(chrono::Utc::now().to_rfc3339()).execute(&pool).await.map_err(|e| e.to_string())?;
    drop(queue_guard);
    tauri::async_runtime::spawn(async move {
        let _guard = ANALYSIS_LOCK.lock().await;
        while crate::audio::recording_commands::is_recording().await {
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        }
        let _ = sqlx::query("UPDATE speaker_jobs SET status = 'running' WHERE meeting_id = ?")
            .bind(&meeting_id)
            .execute(&pool)
            .await;
        diagnostic(
            &app,
            "speaker_analysis_started",
            serde_json::json!({"meeting_id": meeting_id, "requested_speakers": count}),
        );
        if let Err(error) = analyze(&app, &pool, &meeting_id, count).await {
            let message = error.to_string();
            let _ = sqlx::query("UPDATE speaker_jobs SET status = 'failed', error = ?, updated_at = ? WHERE meeting_id = ?")
                .bind(&message).bind(chrono::Utc::now().to_rfc3339()).bind(&meeting_id).execute(&pool).await;
            diagnostic(
                &app,
                "speaker_analysis_failed",
                serde_json::json!({"meeting_id": meeting_id, "error": message}),
            );
        }
        let _ = app.emit(
            "speaker-analysis-updated",
            serde_json::json!({"meeting_id": meeting_id}),
        );
    });
    Ok(())
}

pub fn after_save<R: Runtime>(app: AppHandle<R>, meeting_id: String) {
    if let Ok(settings) = preferences(&app) {
        if settings.enabled {
            tauri::async_runtime::spawn(async move {
                if let Err(error) =
                    start(app.clone(), meeting_id.clone(), settings.speaker_count).await
                {
                    diagnostic(
                        &app,
                        "speaker_analysis_not_started",
                        serde_json::json!({"meeting_id": meeting_id, "error": error}),
                    );
                }
            });
        }
    }
}

#[tauri::command]
pub async fn analyze_meeting_speakers<R: Runtime>(
    app: AppHandle<R>,
    meeting_id: String,
    speaker_count: u32,
) -> Result<(), String> {
    start(app, meeting_id, speaker_count).await
}

#[derive(Serialize, FromRow)]
pub struct SpeakerJob {
    pub status: String,
    pub requested_speakers: i64,
    pub error: Option<String>,
    pub result: Option<String>,
}
#[tauri::command]
pub async fn get_speaker_job(
    state: tauri::State<'_, AppState>,
    meeting_id: String,
) -> Result<Option<SpeakerJob>, String> {
    sqlx::query_as(
        "SELECT status, requested_speakers, error, result FROM speaker_jobs WHERE meeting_id = ?",
    )
    .bind(meeting_id)
    .fetch_optional(state.db_manager.pool())
    .await
    .map_err(|e| e.to_string())
}

#[derive(Serialize, FromRow)]
pub struct VoiceName {
    pub speaker: String,
    pub name: Option<String>,
}
#[tauri::command]
pub async fn get_meeting_speakers(
    state: tauri::State<'_, AppState>,
    meeting_id: String,
) -> Result<Vec<VoiceName>, String> {
    sqlx::query_as("SELECT DISTINCT t.speaker, l.name FROM transcripts t LEFT JOIN speaker_labels l ON l.meeting_id = t.meeting_id AND l.speaker = t.speaker WHERE t.meeting_id = ? AND t.speaker LIKE 'Speaker %' ORDER BY t.speaker")
        .bind(meeting_id).fetch_all(state.db_manager.pool()).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn rename_meeting_speaker(
    state: tauri::State<'_, AppState>,
    meeting_id: String,
    speaker: String,
    name: String,
) -> Result<(), String> {
    if !(1..=8).any(|n| speaker == format!("Speaker {n}"))
        || name.trim().is_empty()
        || name.chars().count() > 80
    {
        return Err("Enter a name of 1–80 characters for an existing voice.".into());
    }
    let pool = state.db_manager.pool();
    let exists: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM transcripts WHERE meeting_id = ? AND speaker = ?")
            .bind(&meeting_id)
            .bind(&speaker)
            .fetch_one(pool)
            .await
            .map_err(|e| e.to_string())?;
    if exists == 0 {
        return Err("This voice is no longer in the transcript. Refresh first.".into());
    }
    sqlx::query("INSERT INTO speaker_labels (meeting_id, speaker, name) VALUES (?, ?, ?) ON CONFLICT(meeting_id,speaker) DO UPDATE SET name = excluded.name")
        .bind(meeting_id).bind(speaker).bind(name.trim()).execute(pool).await.map_err(|e| e.to_string())?;
    Ok(())
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct TeamsStatus {
    pub supported: bool,
    pub microphone_active: bool,
    pub teams_processes: u32,
}
#[tauri::command]
pub async fn get_teams_audio_status<R: Runtime>(app: AppHandle<R>) -> Result<TeamsStatus, String> {
    let engine = engine_dir(&app).map_err(|e| e.to_string())?;
    let output = tokio::process::Command::new(engine.join("speaker-engine"))
        .arg("--teams-status")
        .output()
        .await
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err("macOS audio process status is unavailable.".into());
    }
    serde_json::from_slice(&output.stdout).map_err(|e| e.to_string())
}

pub fn initialize<R: Runtime>(app: AppHandle<R>) {
    tauri::async_runtime::spawn(async move {
        let pool = app.state::<AppState>().db_manager.pool().clone();
        // Interrupted jobs are visible and retryable; never remain 'running' after restart.
        let _ = sqlx::query("UPDATE speaker_jobs SET status = 'failed', error = 'Analysis interrupted. Please retry.' WHERE status IN ('queued','running')").execute(&pool).await;
        let mut last = None;
        loop {
            if preferences(&app)
                .map(|p| p.teams_detection)
                .unwrap_or(false)
            {
                match get_teams_audio_status(app.clone()).await {
                    Ok(status) => {
                        if last.as_ref() != Some(&status) {
                            diagnostic(
                                &app,
                                "teams_audio_status",
                                serde_json::to_value(&status).unwrap_or_default(),
                            );
                            let _ = app.emit("teams-audio-status", &status);
                            last = Some(status);
                        }
                    }
                    Err(error) => {
                        diagnostic(
                            &app,
                            "teams_detection_failed",
                            serde_json::json!({"error": error}),
                        );
                    }
                }
            } else {
                last = None;
            }
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    fn voice(start: f64, end: f64, speaker: &str) -> VoiceInterval {
        VoiceInterval {
            start,
            end,
            speaker: speaker.into(),
        }
    }
    #[test]
    fn preserves_mixed_turns_and_missing_timestamps() {
        let intervals = vec![voice(0., 3., "Speaker 1"), voice(3., 6., "Speaker 2")];
        assert_eq!(assign_segment(Some(0.), Some(3.), &intervals), "Speaker 1");
        assert_eq!(
            assign_segment(Some(0.), Some(6.), &intervals),
            "Mehrere Stimmen"
        );
        assert_eq!(assign_segment(None, Some(6.), &intervals), "Unklar");
        assert_eq!(assign_segment(Some(7.), Some(8.), &intervals), "Unklar");
        assert_eq!(
            assign_segment(Some(0.), Some(30.), &intervals),
            "Mehrere Stimmen"
        );
    }

    #[tokio::test]
    async fn speaker_names_survive_pagination_without_leaking_between_meetings() {
        let pool = SqlitePool::connect("sqlite::memory:").await.unwrap();
        sqlx::migrate!("./migrations").run(&pool).await.unwrap();
        for id in ["first", "second"] {
            sqlx::query("INSERT INTO meetings(id,title,created_at,updated_at) VALUES (?, ?, '2026-09-30 12:00:00', '2026-09-30 12:00:00')")
                .bind(id).bind(id).execute(&pool).await.unwrap();
            for n in 0..3 {
                sqlx::query("INSERT INTO transcripts(id,meeting_id,transcript,timestamp,audio_start_time,audio_end_time,speaker) VALUES (?, ?, 'Er kommt um vier.', '12:00:00', ?, ?, 'Speaker 1')")
                    .bind(format!("{id}-{n}")).bind(id).bind(n as f64).bind((n + 1) as f64).execute(&pool).await.unwrap();
            }
        }
        sqlx::query("INSERT INTO speaker_labels(meeting_id,speaker,name) VALUES ('first','Speaker 1','Testname')").execute(&pool).await.unwrap();
        let (first, total) = crate::database::repositories::meeting::MeetingsRepository::get_meeting_transcripts_paginated(&pool, "first", 1, 2).await.unwrap();
        assert_eq!(total, 3);
        assert_eq!(first[0].speaker_name.as_deref(), Some("Testname"));
        assert_eq!(first[0].transcript, "Er kommt um vier.");
        let second = crate::database::repositories::meeting::MeetingsRepository::get_meeting(
            &pool, "second",
        )
        .await
        .unwrap()
        .unwrap();
        assert!(second.transcripts.iter().all(|t| t.speaker_name.is_none()));
        assert!(second
            .transcripts
            .iter()
            .all(|t| t.speaker.as_deref() == Some("Speaker 1")));
    }
}
