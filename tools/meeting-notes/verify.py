#!/usr/bin/env python3
"""Explicit real-model smoke test. Downloads only public reference audio."""

from collections import Counter
import json
from pathlib import Path
import time
import urllib.request

from meeting_notes.core import json_text
from meeting_notes.runtime import atomic_write, decode_audio, diarize, digest, model_paths, process

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".local-meeting-notes"
ASSETS = [
    ("1-two-speakers-en.wav", "f1c877dc01595e28be7147bf2fe38e5268147a868bf3fdb5c37b97f5940e21f3", 2),
    ("2-two-speakers-en.wav", "ee9c33d34e8f0fda4b78277f609944a1565aa16e6e2146f4cb8f0efb0d70030b", 2),
    ("0-four-speakers-zh.wav", "bedf036caed208386c67b4ef4b11f83d74dd0d420b102163a1c33cd09cde7010", 4),
]


def main():
    fixtures = STATE / "reference-audio"
    fixtures.mkdir(parents=True, exist_ok=True)
    paths, _ = model_paths(STATE / "models")
    report = {"diarization": []}
    for name, checksum, count in ASSETS:
        path = fixtures / name
        if not path.exists():
            urllib.request.urlretrieve("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/" + name, path)
        assert digest(path) == checksum, f"Fixture changed: {name}"
        samples = decode_audio(path)
        started = time.monotonic()
        segments = diarize(samples, paths, count, .5, 2)
        elapsed = time.monotonic() - started
        labels = Counter(s.speaker for s in segments)
        assert len(labels) == count, (name, labels)
        assert all(0 <= s.start < s.end <= len(samples) / 16000 for s in segments)
        report["diarization"].append({"fixture": name, "expected_speakers": count, "detected_speakers": len(labels),
                                       "audio_seconds": len(samples) / 16000, "inference_seconds": round(elapsed, 3)})
    # Stable known two-speaker fixture: the first two sentences and last two
    # sentences belong to different voices. This checks attribution, not just K.
    output = STATE / "verified-transcript"
    started = time.monotonic()
    document = process(fixtures / ASSETS[0][0], STATE / "models", output, speakers=2, title="Referenztest – zwei Sprecher")
    text = " ".join(t["text"] for t in document["turns"])
    assert len(document["turns"]) == 2, document["turns"]
    assert "pencil" in document["turns"][0]["text"].lower()
    assert "lodging" in document["turns"][1]["text"].lower()
    assert document["turns"][0]["speaker"] != document["turns"][1]["speaker"]
    assert "steady green flame" in text and "sweet girl" in text
    report["transcription"] = {"turns": len(document["turns"]), "words": len(document["words"]),
                                "elapsed_seconds": round(time.monotonic() - started, 3)}
    # A second run must use cached analysis. Patch inference to make accidental
    # recomputation fail, so output equality alone cannot mask an expensive rerun.
    from unittest.mock import patch
    with patch("meeting_notes.runtime.diarize", side_effect=AssertionError("Diarization reran")), patch("meeting_notes.runtime.transcribe", side_effect=AssertionError("ASR reran")):
        cached = process(fixtures / ASSETS[0][0], STATE / "models", output, speakers=2, title=document["title"])
    assert document == cached
    report["cached_run"] = "identical output, zero diarization/ASR calls"
    german = STATE / "models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/test_wavs/de.wav"
    result = process(german, STATE / "models", STATE / "verified-german", speakers=1, title="Referenztest – Deutsch")
    assert "Alles hat ein Ende, nur die Wurst hat zwei." in " ".join(t["text"] for t in result["turns"])
    report["german"] = "expected sentence transcribed"
    atomic_write(STATE / "verification.json", json_text(report))
    print(json_text(report))


if __name__ == "__main__":
    main()
