"""Explicit, checksummed model installation. Only this command downloads models."""

import json
from pathlib import Path
import tarfile
import urllib.request

from .core import json_text
from .runtime import MODEL_FILES, atomic_write, digest

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
ASSETS = [
    ("segmentation.tar.bz2", "speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2", "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488"),
    ("embedding.onnx", "speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx", "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b"),
    ("parakeet.tar.bz2", "asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2", "5793d0fd397c5778d2cf2126994d58e9d56b1be7c04d13c7a15bb1b4eafb16bf"),
]


def install(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    downloads = directory.parent / "downloads"
    downloads.mkdir(exist_ok=True)
    for filename, relative_url, checksum in ASSETS:
        asset = downloads / filename
        if not asset.exists() or digest(asset) != checksum:
            temporary = asset.with_suffix(asset.suffix + ".download")
            print(f"Downloading {filename}", flush=True)
            with urllib.request.urlopen(RELEASES + relative_url, timeout=60) as response, temporary.open("wb") as destination:
                import shutil
                shutil.copyfileobj(response, destination)
            if digest(temporary) != checksum:
                temporary.unlink()
                raise ValueError(f"Download checksum mismatch for {filename}")
            temporary.replace(asset)
        if filename.endswith(".tar.bz2"):
            with tarfile.open(asset) as archive:
                archive.extractall(directory, filter="data")
        else:
            import shutil
            shutil.copyfile(asset, directory / filename)
    manifest = {"source": "k2-fsa/sherpa-onnx GitHub release assets", "assets": [
        {"url": RELEASES + url, "sha256": checksum} for _, url, checksum in ASSETS
    ], "files": {relative: digest(directory / relative) for relative in MODEL_FILES.values()}}
    atomic_write(directory / "manifest.json", json_text(manifest))
    print(f"Models installed and verified: {directory}")
