import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sys

from . import models
from .runtime import export, process
from .summary import summarize


@contextmanager
def output_lock(directory):
    """OS locks release even after a crash; concurrent runs cannot mix exports."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".processing.lock").open("a+b") as lock:
        if sys.platform == "win32":
            import msvcrt
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if sys.platform == "win32":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def speaker_count(value):
    if value == "auto":
        return -1
    value = int(value)
    if not 1 <= value <= 32:
        raise argparse.ArgumentTypeError("Speaker count must be auto or 1–32")
    return value


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="Local speaker diarization and portable meeting transcripts")
    parser.add_argument("--models", type=Path, default=root / ".local-meeting-notes" / "models")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup-models", help="Download and verify local models (about 500 MB compressed)")
    run = commands.add_parser("process", help="Process an audio file or a completed Meetily meeting folder")
    run.add_argument("source", type=Path)
    run.add_argument("--output", type=Path)
    run.add_argument("--speakers", type=speaker_count, required=True, help="Number of audible speakers; auto is experimental")
    run.add_argument("--threshold", type=float, default=0.5)
    run.add_argument("--threads", type=int, default=2)
    run.add_argument("--title")
    render = commands.add_parser("export", help="Rename speakers and render existing analysis without inference")
    render.add_argument("transcript", type=Path)
    render.add_argument("--name", action="append", default=[], metavar="Speaker 1=Marc")
    summary = commands.add_parser("summarize", help="Cached, source-backed meeting notes with an explicit model endpoint")
    summary.add_argument("transcript", type=Path)
    summary.add_argument("--endpoint", default="http://127.0.0.1:11434")
    summary.add_argument("--model", required=True)
    summary.add_argument("--model-revision", default="", help="Change this when model weights behind the same name change")
    summary.add_argument("--api-kind", choices=["ollama", "openai"], default="ollama")
    summary.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "setup-models":
            with output_lock(args.models.parent):
                models.install(args.models)
        elif args.command == "process":
            if not 0 < args.threshold < 1 or not 1 <= args.threads <= 8:
                raise ValueError("Threshold must be between 0 and 1; threads must be 1–8")
            output = args.output or ((args.source if args.source.is_dir() else args.source.parent) / "meeting-notes")
            with output_lock(output):
                document = process(args.source, args.models, output, args.speakers, args.threshold, args.threads, args.title)
            print(f"Saved {len(document['turns'])} turns to {output.resolve()}")
        elif args.command == "export":
            document = json.loads(args.transcript.read_text())
            directory = args.transcript.parent
            with output_lock(directory):
                names_file = directory / "speaker-names.json"
                names = json.loads(names_file.read_text()) if names_file.exists() else {}
                known = {t["speaker"] for t in document["turns"]}
                for rename in args.name:
                    old, separator, new = rename.partition("=")
                    if not separator or old not in known or not new.strip() or "\n" in new:
                        raise ValueError(f"Invalid speaker mapping: {rename}")
                    names[old] = new.strip()
                export(document, directory, names)
            print(f"Exported {directory.resolve() / 'transcript.md'}")
        else:
            with output_lock(args.transcript.parent):
                result = summarize(args.transcript, args.endpoint, args.model, args.api_kind, args.allow_remote, args.model_revision)
            print(f"Saved {len(result['notes'])} source-backed notes; {sum(not u['cached'] for u in result['usage'])} model calls")
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
