"""Inference boundary. No network calls: all models must already be installed."""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .core import SpeakerSegment, Word, align_words, html, json_text, markdown, speech_windows, words_from_tokens

MODEL_FILES = {
    "segmentation": "sherpa-onnx-pyannote-segmentation-3-0/model.onnx",
    "embedding": "embedding.onnx",
    "encoder": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/encoder.int8.onnx",
    "decoder": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/decoder.int8.onnx",
    "joiner": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/joiner.int8.onnx",
    "tokens": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/tokens.txt",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def find_audio(source):
    source = Path(source).resolve()
    if source.is_file():
        return source
    for name in ("audio.mp4", "audio.m4a", "audio.wav", "recording.mp4"):
        if (source / name).is_file():
            return source / name
    candidates = [p for p in source.iterdir() if p.suffix.lower() in {".wav", ".mp4", ".m4a", ".mp3", ".flac", ".ogg", ".webm"}]
    if len(candidates) != 1:
        raise ValueError("Specify one audio file, or a Meetily meeting folder containing audio.mp4")
    return candidates[0]


def decode_audio(path):
    import numpy as np
    result = subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"
    ], check=True, capture_output=True)
    samples = np.frombuffer(result.stdout, dtype="<f4").copy()
    if not len(samples) or not np.isfinite(samples).all():
        raise ValueError("Audio is empty or contains invalid samples")
    return samples


def model_paths(directory):
    directory = Path(directory)
    paths = {key: directory / filename for key, filename in MODEL_FILES.items()}
    manifest = json.loads((directory / "manifest.json").read_text())
    for key, path in paths.items():
        if digest(path) != manifest["files"][MODEL_FILES[key]]:
            raise ValueError(f"Model checksum mismatch: {path}. Run setup-models again.")
    return paths, manifest


def diarize(samples, paths, speakers, threshold, threads):
    import sherpa_onnx
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(paths["segmentation"]), window_shift_ratio=0.1),
            num_threads=threads, provider="cpu",
        ),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(paths["embedding"]), num_threads=threads, provider="cpu"),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=speakers, threshold=threshold),
        min_duration_on=0.3, min_duration_off=0.5,
    )
    if not config.validate():
        raise ValueError("Invalid local diarization configuration")
    engine = sherpa_onnx.OfflineSpeakerDiarization(config)
    results = engine.process(samples).sort_by_start_time()
    # Cluster IDs need not be chronological. Canonical labels follow first appearance.
    ids = {}
    segments = []
    for result in results:
        label = ids.setdefault(result.speaker, f"Speaker {len(ids) + 1}")
        segments.append(SpeakerSegment(label, float(result.start), min(float(result.end), len(samples) / 16000)))
    return segments


def transcribe(samples, paths, segments, threads, checkpoint):
    import sherpa_onnx
    recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(paths["encoder"]), decoder=str(paths["decoder"]), joiner=str(paths["joiner"]), tokens=str(paths["tokens"]),
        num_threads=threads, provider="cpu", model_type="nemo_transducer", decoding_method="greedy_search",
    )
    words = []
    windows = list(speech_windows(segments, len(samples) / 16000))
    for i, (start, end, owner_start, owner_end) in enumerate(windows):
        cache = checkpoint / f"chunk-{i:05}.json"
        if cache.exists():
            chunk_words = [Word(**w) for w in json.loads(cache.read_text())]
        else:
            stream = recognizer.create_stream()
            stream.accept_waveform(16000, samples[round(start * 16000):round(end * 16000)])
            recognizer.decode_stream(stream)
            result = stream.result
            chunk_words = words_from_tokens(result.tokens, result.timestamps, result.durations, start)
            atomic_write(cache, json_text([asdict(w) for w in chunk_words]))
        words.extend(w for w in chunk_words if owner_start <= (w.start + w.end) / 2 < owner_end)
        print(f"Transcription {i + 1}/{len(windows)}", flush=True)
    return sorted(words, key=lambda w: w.start)


def export(document, output, names):
    output = Path(output)
    old_names = output / "speaker-names.json"
    if old_names.exists() and json.loads(old_names.read_text()) != names:
        # A summary containing previous speaker names is no longer current.
        for filename in ("summary.md", "summary.json"):
            (output / filename).unlink(missing_ok=True)
    atomic_write(output / "transcript.md", markdown(document, names))
    atomic_write(output / "transcript.html", html(document, names))
    atomic_write(output / "speaker-names.json", json_text(names))
    atomic_write(output / "transcript.json", json_text(document))


def speaker_samples(samples, segments, output):
    """Private voice clips for manual naming; never embedded in the shareable HTML."""
    import numpy as np
    import wave
    directory = Path(output) / "speaker-samples"
    directory.mkdir(parents=True, exist_ok=True)
    for label in sorted({s.speaker for s in segments}):
        # Prefer a clean interval without another active speaker.
        candidates = [s for s in segments if s.speaker == label and not any(
            other.speaker != label and max(other.start, s.start) < min(other.end, s.end) for other in segments
        )]
        if not candidates:
            continue
        chosen = max(candidates, key=lambda s: s.end - s.start)
        clip = samples[round(chosen.start * 16000):round(min(chosen.end, chosen.start + 6) * 16000)]
        with wave.open(str(directory / f"{label.replace(' ', '-')}.wav"), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes((np.clip(clip, -1, 1) * 32767).astype("<i2").tobytes())


def process(source, models, output, speakers=-1, threshold=0.5, threads=2, title=None):
    audio = find_audio(source)
    output = Path(output).resolve()
    paths, manifest = model_paths(models)
    from . import VERSION
    import sherpa_onnx
    audio_hash = digest(audio)
    fingerprint = hashlib.sha256(json_text({
        "audio": audio_hash, "models": manifest["files"], "speakers": speakers,
        "threshold": threshold, "pipeline": VERSION, "runtime": sherpa_onnx.__version__, "threads": threads,
    }).encode()).hexdigest()
    previous = output / "transcript.json"
    if previous.exists() and json.loads(previous.read_text())["fingerprint"] != fingerprint:
        raise ValueError("This output directory belongs to a different audio/configuration. Choose a new --output directory.")
    checkpoint = output / ".cache" / fingerprint
    checkpoint.mkdir(parents=True, exist_ok=True)
    names_path = output / "speaker-names.json"
    names = json.loads(names_path.read_text()) if names_path.exists() else {}
    final_cache = checkpoint / "analysis.json"
    if final_cache.exists():
        document = json.loads(final_cache.read_text())
        print("Using cached transcript and speaker analysis", flush=True)
    else:
        samples = decode_audio(audio)
        print(f"Diarization: {len(samples) / 16000:.1f}s audio, CPU, {threads} threads", flush=True)
        segment_cache = checkpoint / "speakers.json"
        if segment_cache.exists():
            segments = [SpeakerSegment(**s) for s in json.loads(segment_cache.read_text())]
        else:
            segments = diarize(samples, paths, speakers, threshold, threads)
            atomic_write(segment_cache, json_text([asdict(s) for s in segments]))
        if not segments:
            raise ValueError("No speech detected. Existing exports were preserved.")
        words = transcribe(samples, paths, segments, threads, checkpoint)
        if not words:
            raise ValueError("ASR returned no words. Existing exports were preserved.")
        document = {"schema_version": 1, "fingerprint": fingerprint, "title": title or audio.parent.name,
                    "duration": len(samples) / 16000, "models": manifest, "speakers": [asdict(s) for s in segments],
                    "words": [asdict(w) for w in words], "turns": align_words(words, segments)}
        if digest(audio) != audio_hash:
            raise ValueError("The audio file changed during processing. Wait until recording is finished.")
        speaker_samples(samples, segments, output)
        atomic_write(final_cache, json_text(document))
    document["title"] = title or document["title"]
    if digest(audio) != audio_hash:
        raise ValueError("The audio file changed during processing. Wait until recording is finished.")
    export(document, output, names)
    return document
