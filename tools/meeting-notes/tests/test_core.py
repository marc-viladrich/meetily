import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from meeting_notes.core import SpeakerSegment, Word, align_words, assign_speaker, html, speech_windows, words_from_tokens
from meeting_notes.runtime import export, process
from meeting_notes.summary import chunks, summarize, validate_endpoint, validated_notes


class AlignmentTests(unittest.TestCase):
    def test_subwords_and_punctuation_stay_in_one_word(self):
        words = words_from_tokens(["▁G", "uten", "▁Morgen", "."], [0, .1, .3, .5], [.1] * 4, 30)
        self.assertEqual([w.text for w in words], ["Guten", "Morgen."])
        self.assertAlmostEqual(words[1].end, 30.6)

    def test_mid_sentence_handoff_splits_without_losing_words(self):
        words = [Word("Hallo", 0, .4), Word("Marc.", .5, .9), Word("Hallo!", 1.1, 1.5)]
        segments = [SpeakerSegment("Speaker 1", 0, 1), SpeakerSegment("Speaker 2", 1, 2)]
        turns = align_words(words, segments)
        self.assertEqual([t["speaker"] for t in turns], ["Speaker 1", "Speaker 2"])
        self.assertEqual(" ".join(t["text"] for t in turns), "Hallo Marc. Hallo!")

    def test_overlap_and_missing_speech_are_never_forced_to_speaker_one(self):
        word = Word("Ja", 0, 1)
        self.assertEqual(assign_speaker(word, []), "Unklar")
        self.assertEqual(assign_speaker(word, [SpeakerSegment("A", 0, 1), SpeakerSegment("B", 0, 1)]), "Überlappung")

    def test_windows_cover_tail_and_have_exclusive_ownership(self):
        windows = list(speech_windows([SpeakerSegment("A", 0, 65.5)], 65.5))
        self.assertEqual([(w[2], w[3]) for w in windows], [(0, 30), (30, 60), (60, 65.5)])
        self.assertEqual(windows[-1][1], 65.5)
        self.assertEqual(windows[1][0], 29)

    def test_malformed_token_timing_is_rejected(self):
        with self.assertRaises(ValueError):
            words_from_tokens(["one"], [], [])

    def test_tdt_blank_duration_does_not_move_word_to_next_speaker(self):
        word = Word("best.", 3.28, 4.16)
        segments = [SpeakerSegment("A", 1.58, 3.41), SpeakerSegment("B", 4.4, 6.4)]
        self.assertEqual(assign_speaker(word, segments), "A")

    def test_small_boundary_offset_does_not_drop_first_word(self):
        self.assertEqual(assign_speaker(Word("A", 1.44, 1.60), [SpeakerSegment("A", 1.58, 3.4)]), "A")

    def test_html_escapes_transcript_and_has_no_remote_assets(self):
        document = {"title": "<script>title</script>", "turns": [{"speaker": "A", "start": 0, "text": "<script>alert(1)</script>"}]}
        rendered = html(document, {"A": "<b>Marc</b>"})
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;b&gt;Marc&lt;/b&gt;", rendered)
        self.assertNotIn("src=", rendered)

    def test_audio_changing_during_analysis_is_not_exported(self):
        with tempfile.TemporaryDirectory() as temp:
            audio = Path(temp) / "recording.wav"
            audio.write_bytes(b"initial recording")
            def changed(*args):
                audio.write_bytes(b"recording still in progress")
                return [SpeakerSegment("A", 0, 1)]
            with patch.dict("sys.modules", {"sherpa_onnx": types.SimpleNamespace(__version__="test")}), \
                 patch("meeting_notes.runtime.model_paths", return_value=({}, {"files": {}})), \
                 patch("meeting_notes.runtime.decode_audio", return_value=[0.0] * 16000), \
                 patch("meeting_notes.runtime.diarize", side_effect=changed), \
                 patch("meeting_notes.runtime.transcribe", return_value=[Word("Hallo", 0, 1)]):
                with self.assertRaisesRegex(ValueError, "changed during processing"):
                    process(audio, Path(temp), Path(temp) / "out", speakers=1)
            self.assertFalse((Path(temp) / "out/transcript.json").exists())


class SummaryTests(unittest.TestCase):
    def test_invented_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            validated_notes({"notes": [{"kind": "decision", "text": "Approved", "evidence": [{"id": "t0", "quote": "We approve"}]}]}, [{"id": "t0", "text": "Maybe later"}])

    def test_remote_endpoint_requires_explicit_opt_in(self):
        self.assertEqual(validate_endpoint("http://127.0.0.1:11434"), "http://127.0.0.1:11434")
        with self.assertRaises(ValueError):
            validate_endpoint("https://example.com/v1")

    def test_summary_cache_avoids_all_repeated_model_calls(self):
        document = {"fingerprint": "test", "title": "Meeting", "turns": [{"speaker": "A", "start": 0, "text": "Wir sprechen am Freitag wieder."}]}
        response = ([{"kind": "discussion", "text": "Nächstes Gespräch am Freitag", "evidence": [{"id": "t0", "quote": "am Freitag"}]}], {"input_tokens": 20})
        with tempfile.TemporaryDirectory() as temp:
            transcript = Path(temp) / "transcript.json"
            transcript.write_text(json.dumps(document))
            with patch("meeting_notes.summary.request_summary", return_value=response) as request:
                summarize(transcript, "http://localhost:11434", "test", model_revision="test")
                cached = summarize(transcript, "http://localhost:11434", "test", model_revision="test")
                self.assertEqual(request.call_count, 1)
                self.assertTrue(cached["usage"][0]["cached"])

    def test_long_turn_is_bounded_and_preserves_all_source_text(self):
        text = "ä" * 21000
        batches = list(chunks([{"speaker": "A", "text": text}], {}))
        self.assertEqual("".join(item["text"] for batch in batches for item in batch), text)
        self.assertTrue(all(len(json.dumps(batch, ensure_ascii=False)) < 8200 for batch in batches))

    def test_renaming_invalidates_stale_summary(self):
        document = {"title": "Meeting", "turns": []}
        with tempfile.TemporaryDirectory() as temp:
            export(document, temp, {})
            (Path(temp) / "summary.md").write_text("Speaker 1 said...")
            export(document, temp, {"Speaker 1": "Marc"})
            self.assertFalse((Path(temp) / "summary.md").exists())


if __name__ == "__main__":
    unittest.main()
