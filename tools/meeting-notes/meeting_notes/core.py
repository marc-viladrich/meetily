"""Pure timestamp alignment and portable transcript rendering."""

from dataclasses import dataclass
from html import escape
import json


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class SpeakerSegment:
    speaker: str
    start: float
    end: float


def words_from_tokens(tokens, timestamps, durations, offset=0.0):
    """Join SentencePiece tokens before assigning a speaker, including punctuation."""
    if not (len(tokens) == len(timestamps) == len(durations)):
        raise ValueError("ASR tokens, timestamps and durations must have equal lengths")
    words = []
    text, start, end = "", 0.0, 0.0
    for token, timestamp, duration in zip(tokens, timestamps, durations):
        if token.startswith("▁") or token.startswith(" "):
            if text:
                words.append(Word(text, start, end))
            text = token.lstrip("▁ ")
            start = offset + timestamp
        else:
            if not text:
                start = offset + timestamp
            text += token
        end = offset + timestamp + max(duration, 0.01)
    if text:
        words.append(Word(text, start, end))
    return words


def assign_speaker(word, segments):
    """Keep ambiguous overlapping speech explicit instead of inventing attribution."""
    # TDT duration can include the blank/pause before the next token. Attribution
    # uses the word onset, while the original duration remains in the export.
    end = min(word.end, word.start + 0.25)
    duration = max(end - word.start, 0.01)
    covered = {}
    for segment in segments:
        overlap = max(0.0, min(end, segment.end) - max(word.start, segment.start))
        if overlap:
            covered[segment.speaker] = covered.get(segment.speaker, 0.0) + overlap
    ranked = sorted(covered.items(), key=lambda item: (-item[1], item[0]))
    if not ranked or ranked[0][1] / duration < 0.5:
        # Accommodate the small offset between ASR and segmentation boundaries,
        # only when there is a single plausible voice at the word onset.
        nearby = {s.speaker for s in segments if s.start <= word.start + 0.3 and s.end >= word.start - 0.3}
        if len(nearby) == 1:
            return next(iter(nearby))
        return "Unklar"
    if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.6:
        return "Überlappung"
    return ranked[0][0]


def align_words(words, segments):
    turns = []
    ordered = sorted(segments, key=lambda s: s.start)
    cursor = 0
    active = []
    for word in words:
        active = [s for s in active if s.end >= word.start - 0.3]
        while cursor < len(ordered) and ordered[cursor].start <= max(word.end, word.start + 0.3):
            active.append(ordered[cursor])
            cursor += 1
        speaker = assign_speaker(word, active)
        if turns and turns[-1]["speaker"] == speaker and word.start - turns[-1]["end"] < 2.0:
            turns[-1]["text"] += " " + word.text
            turns[-1]["end"] = word.end
        else:
            turns.append({"speaker": speaker, "start": word.start, "end": word.end, "text": word.text})
    return turns


def speech_windows(segments, duration, size=30.0, context=1.0):
    """ASR only on speech, bounded chunks with context and exclusive ownership."""
    intervals = []
    for segment in sorted(segments, key=lambda s: s.start):
        start, end = max(0.0, segment.start - 0.3), min(duration, segment.end + 0.3)
        if intervals and start <= intervals[-1][1] + 0.5:
            intervals[-1][1] = max(intervals[-1][1], end)
        else:
            intervals.append([start, end])
    for start, end in intervals:
        owner_start = start
        while owner_start < end:
            owner_end = min(owner_start + size, end)
            yield (max(start, owner_start - context), min(end, owner_end + context), owner_start, owner_end)
            owner_start = owner_end


def timestamp(seconds):
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


def display_speaker(speaker, names):
    return names.get(speaker, speaker)


def markdown(document, names):
    lines = [f"# {document['title']}", "", "Automatisch erzeugtes Transkript. Sprecherzuordnung und Wortlaut bitte prüfen.", ""]
    for turn in document["turns"]:
        speaker = display_speaker(turn["speaker"], names).replace("\n", " ")
        lines.extend([f"**[{timestamp(turn['start'])}] {speaker}:** {turn['text']}", ""])
    return "\n".join(lines)


def html(document, names):
    rows = "\n".join(
        f'<article><time>{timestamp(t["start"])}</time><div><strong>{escape(display_speaker(t["speaker"], names))}</strong><p>{escape(t["text"])}</p></div></article>'
        for t in document["turns"]
    )
    title = escape(document["title"])
    return f'''<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>{title}</title><style>body{{font:17px/1.6 system-ui;max-width:860px;margin:40px auto;padding:0 24px;color:#182420;background:#fafcfb}}article{{display:flex;gap:24px;border-top:1px solid #d9e2de;padding:20px 0}}time{{font-variant-numeric:tabular-nums;color:#52645b}}p{{margin:4px 0}}h1{{line-height:1.2}}@media(max-width:600px){{article{{gap:12px}}}}</style>
<h1>{title}</h1><p>Automatisch erzeugtes Transkript. Sprecherzuordnung und Wortlaut bitte prüfen.</p>{rows}</html>'''


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
