"""Prepare the reproducible macOS ARM64 native speaker engine; no user audio needed."""
import hashlib
import pathlib
import platform
import shutil
import subprocess
import tarfile
import urllib.request

if platform.system() != 'Darwin' or platform.machine() != 'arm64':
    raise SystemExit('This pinned helper bundle targets macOS ARM64. Port the build for other platforms.')

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / '.local-meeting-notes' / 'sherpa-native'
DEST = ROOT / 'frontend' / 'src-tauri' / 'resources' / 'speaker-engine'
CACHE.mkdir(parents=True, exist_ok=True)
DEST.mkdir(parents=True, exist_ok=True)

def fetch(url, sha, path):
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        with urllib.request.urlopen(url, timeout=180) as response:
            payload = response.read()
        if hashlib.sha256(payload).hexdigest() != sha:
            raise ValueError('Download checksum mismatch: ' + url)
        path.write_bytes(payload)
    return path

base = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
archive = fetch(base + 'v1.13.8/sherpa-onnx-v1.13.8-osx-arm64-shared-no-tts-lib.tar.bz2',
    'f3e0cbd86cc3f38dad30c97921b40e9a8bcc6f2c943777eb76ad77176993e417', CACHE / 'runtime.tar.bz2')
with tarfile.open(archive) as tar:
    tar.extractall(CACHE, filter='data')
fetch('https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/v1.13.8/sherpa-onnx/c-api/c-api.h',
    '2a1b95084be8fd1deb3228fcad2fd3f7f0258b64582f7402281ec174c7b7f4ce', CACHE / 'c-api.h')
seg = fetch(base + 'speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2',
    '24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488', CACHE / 'segmentation.tar.bz2')
with tarfile.open(seg) as tar:
    tar.extractall(CACHE, filter='data')
shutil.copy2(CACHE / 'sherpa-onnx-pyannote-segmentation-3-0/model.onnx', DEST / 'segmentation.onnx')
fetch(base + 'speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx',
    '1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b', DEST / 'embedding.onnx')
libs = CACHE / 'sherpa-onnx-v1.13.8-osx-arm64-shared-no-tts-lib/lib'
for name in ['libsherpa-onnx-c-api.dylib', 'libonnxruntime.dylib']:
    shutil.copy2(libs / name, DEST / name)
subprocess.run(['xcrun', 'clang++', '-std=c++17', '-O2', '-mmacosx-version-min=13.0',
    '-I' + str(CACHE), str(ROOT / 'tools/speaker-engine/main.cpp'),
    '-L' + str(DEST), '-lsherpa-onnx-c-api', '-Wl,-rpath,@executable_path',
    '-framework', 'CoreAudio', '-framework', 'CoreFoundation', '-o', str(DEST / 'speaker-engine')], check=True)
for name in ['libonnxruntime.dylib', 'libsherpa-onnx-c-api.dylib', 'speaker-engine']:
    subprocess.run(['codesign', '--force', '--sign', '-', str(DEST / name)], check=True)
print('Prepared', DEST)
