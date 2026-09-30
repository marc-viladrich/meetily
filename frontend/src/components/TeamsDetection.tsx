'use client';

import { useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { toast } from 'sonner';
import { useRecordingState } from '@/contexts/RecordingStateContext';
import { SpeakerSettingsData } from '@/components/SpeakerSettings';

interface TeamsStatus { supported: boolean; microphone_active: boolean }

export function TeamsDetection() {
  const { isRecording } = useRecordingState();
  useEffect(() => {
    let cancelled = false;
    let activePolls = 0;
    let idlePolls = 0;
    let notified = false;
    let pending = false;
    const check = async () => {
      if (pending) return;
      pending = true;
      try {
        const data = await invoke<SpeakerSettingsData>('get_speaker_settings');
        if (!data.preferences.teams_detection) { toast.dismiss('teams-audio-reminder'); activePolls = 0; notified = false; return; }
        const signal = await invoke<TeamsStatus>('get_teams_audio_status');
        if (cancelled) return;
        if (!signal.supported || !signal.microphone_active) {
          activePolls = 0;
          if (++idlePolls >= 3) { notified = false; toast.dismiss('teams-audio-reminder'); }
          return;
        }
        idlePolls = 0;
        if (++activePolls >= 3 && !notified && !isRecording) {
          notified = true;
          toast('Teams verwendet das Mikrofon', {
            id: 'teams-audio-reminder', duration: Infinity,
            description: 'Möglicher Call oder Vorraum. Möchtest du aufnehmen?',
            action: { label: 'Aufnahme starten', onClick: () => window.dispatchEvent(new CustomEvent('start-recording-from-sidebar')) },
            cancel: { label: 'Schließen', onClick: () => {} },
          });
        }
      } catch (e) { console.warn('Teams detection unavailable:', e); }
      finally { pending = false; }
    };
    void check();
    const timer = setInterval(() => { void check(); }, 2000);
    return () => { cancelled = true; clearInterval(timer); toast.dismiss('teams-audio-reminder'); };
  }, [isRecording]);
  return null;
}
