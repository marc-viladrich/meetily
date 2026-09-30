// Runs inference in a separate process to isolate its ONNX Runtime from Meetily's.
#include "c-api.h"
#include <CoreAudio/CoreAudio.h>
#include <CoreFoundation/CoreFoundation.h>
#include <fstream>
#include <iostream>
#include <map>
#include <vector>
#include <cstring>

template <typename T>
bool property(AudioObjectID object, AudioObjectPropertySelector selector, T &value) {
  AudioObjectPropertyAddress address{selector, kAudioObjectPropertyScopeGlobal,
                                     kAudioObjectPropertyElementMain};
  UInt32 size = sizeof(T);
  return AudioObjectGetPropertyData(object, &address, 0, nullptr, &size, &value) == noErr;
}

int teams_status() {
  if (__builtin_available(macOS 14.2, *)) {
    AudioObjectPropertyAddress address{kAudioHardwarePropertyProcessObjectList,
                                      kAudioObjectPropertyScopeGlobal,
                                      kAudioObjectPropertyElementMain};
    UInt32 size = 0;
    if (AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &address, 0, nullptr, &size)) return 2;
    std::vector<AudioObjectID> processes(size / sizeof(AudioObjectID));
    if (AudioObjectGetPropertyData(kAudioObjectSystemObject, &address, 0, nullptr, &size, processes.data())) return 2;
    bool active = false;
    int matches = 0;
    for (auto process : processes) {
      CFStringRef bundle = nullptr;
      if (!property(process, kAudioProcessPropertyBundleID, bundle) || !bundle) continue;
      char name[512] = {};
      CFStringGetCString(bundle, name, sizeof(name), kCFStringEncodingUTF8);
      CFRelease(bundle);
      if (std::strcmp(name, "com.microsoft.teams2") != 0 &&
          std::strcmp(name, "com.microsoft.teams") != 0 &&
          std::strncmp(name, "com.microsoft.teams2.", 21) != 0) continue;
      ++matches;
      UInt32 input = 0;
      if (property(process, kAudioProcessPropertyIsRunningInput, input)) active |= input != 0;
    }
    std::cout << "{\"supported\":true,\"microphone_active\":" << (active ? "true" : "false")
              << ",\"teams_processes\":" << matches << "}\n";
  } else {
    std::cout << "{\"supported\":false,\"microphone_active\":false,\"teams_processes\":0}\n";
  }
  return 0;
}

int main(int argc, char **argv) {
  if (argc == 2 && std::strcmp(argv[1], "--teams-status") == 0) return teams_status();
  if (argc != 5) { std::cerr << "Expected segmentation, embedding, speaker count, mono 16kHz f32 file\n"; return 2; }
  int count = std::atoi(argv[3]);
  if (count < 1 || count > 8) return 2;
  std::ifstream file(argv[4], std::ios::binary | std::ios::ate);
  if (!file) return 2;
  auto bytes = file.tellg();
  if (bytes <= 0 || bytes % sizeof(float) != 0 || bytes / sizeof(float) > INT32_MAX) return 2;
  std::vector<float> samples(bytes / sizeof(float));
  file.seekg(0); file.read(reinterpret_cast<char *>(samples.data()), bytes);
  if (!file) return 2;
  SherpaOnnxOfflineSpeakerDiarizationConfig config{};
  config.segmentation.pyannote.model = argv[1];
  config.segmentation.pyannote.window_shift_ratio = 0.1f;
  config.segmentation.num_threads = 1;
  config.segmentation.provider = "cpu";
  config.embedding.model = argv[2];
  config.embedding.num_threads = 1;
  config.embedding.provider = "cpu";
  config.clustering.num_clusters = count;
  config.clustering.threshold = 0.5f;
  config.min_duration_on = 0.3f;
  config.min_duration_off = 0.5f;
  auto engine = SherpaOnnxCreateOfflineSpeakerDiarization(&config);
  if (!engine) return 3;
  auto result = SherpaOnnxOfflineSpeakerDiarizationProcess(engine, samples.data(), samples.size());
  if (!result) { SherpaOnnxDestroyOfflineSpeakerDiarization(engine); return 3; }
  auto segments = SherpaOnnxOfflineSpeakerDiarizationResultSortByStartTime(result);
  int n = SherpaOnnxOfflineSpeakerDiarizationResultGetNumSegments(result);
  std::map<int, int> names;
  std::cout << "[";
  for (int i = 0; i < n; ++i) {
    if (!names.count(segments[i].speaker)) names[segments[i].speaker] = names.size() + 1;
    if (i) std::cout << ",";
    std::cout << "{\"start\":" << segments[i].start << ",\"end\":" << segments[i].end
              << ",\"speaker\":\"Speaker " << names[segments[i].speaker] << "\"}";
  }
  std::cout << "]\n";
  SherpaOnnxOfflineSpeakerDiarizationDestroySegment(segments);
  SherpaOnnxOfflineSpeakerDiarizationDestroyResult(result);
  SherpaOnnxDestroyOfflineSpeakerDiarization(engine);
}
