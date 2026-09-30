'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Button } from '@/components/ui/button';
import { SpeakerSettingsData } from '@/components/SpeakerSettings';

interface SpeakerJob { status: string; requested_speakers: number; error: string | null; result: string | null }
interface VoiceName { speaker: string; name: string | null }

export function SpeakerPanel({ meetingId, onRefresh }: { meetingId: string; onRefresh?: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(2);
  const [job, setJob] = useState<SpeakerJob | null>(null);
  const [voices, setVoices] = useState<VoiceName[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [available, setAvailable] = useState(false);
  const lastCompletion = useRef<string | null>(null);
  const initialCountLoaded = useRef(false);
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;
  const activeId = useRef(meetingId); activeId.current = meetingId;
  const load = useCallback(async () => {
    const [current, names] = await Promise.all([
      invoke<SpeakerJob | null>('get_speaker_job', { meetingId }),
      invoke<VoiceName[]>('get_meeting_speakers', { meetingId }),
    ]);
    if (activeId.current !== meetingId) return;
    setJob(current); setVoices(names);
    if (current && !initialCountLoaded.current) { setCount(current.requested_speakers); initialCountLoaded.current = true; }
    if (current?.status === 'completed' && lastCompletion.current !== current.result) {
      lastCompletion.current = current.result;
      await refreshRef.current?.();
    }
  }, [meetingId]);
  useEffect(() => {
    lastCompletion.current = null; initialCountLoaded.current = false; setJob(null); setVoices([]); setError('');
    invoke<SpeakerSettingsData>('get_speaker_settings').then(data => {
      if (activeId.current !== meetingId) return;
      setAvailable(data.engine_available);
      if (!initialCountLoaded.current) setCount(data.preferences.speaker_count);
    }).catch(e => setError(String(e)));
    void load().catch(e => setError(String(e)));
    const timer = setInterval(() => { void load().catch(e => setError(String(e))); }, 2000);
    return () => clearInterval(timer);
  }, [load, meetingId]);
  const run = async () => {
    setBusy(true); setError('');
    try { await invoke('analyze_meeting_speakers', { meetingId, speakerCount: count }); await load(); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  const rename = async (speaker: string, name: string) => {
    setBusy(true); setError('');
    try { await invoke('rename_meeting_speaker', { meetingId, speaker, name }); await load(); await refreshRef.current?.(); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  const running = busy || job?.status === 'queued' || job?.status === 'running';
  return <div className="border-b px-4 py-3 text-sm">
    <div className="flex items-center justify-between gap-2">
      <button type="button" className="font-medium underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2" aria-expanded={open} onClick={() => setOpen(!open)}>Sprecherzuordnung {open ? '▴' : '▾'}</button>
      <span role="status" className="text-gray-600">{running ? 'Wird lokal analysiert…' : job?.status === 'completed' ? 'Zuordnung gespeichert' : job?.status === 'failed' ? 'Analyse fehlgeschlagen' : 'Noch nicht zugeordnet'}</span>
    </div>
    {open && <div className="space-y-3 mt-3">
      <p className="text-gray-600">Stimmenanalyse für das vorhandene Transkript. Keine automatische Zuordnung zu Teams-Namen. Die Transkription bleibt erhalten.</p>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="meeting-speaker-count">Erwartete Stimmen</label>
        <select id="meeting-speaker-count" value={count} disabled={running} onChange={e => setCount(Number(e.target.value))} className="border rounded px-2 py-1 bg-white">
          {Array.from({ length: 8 }, (_, i) => i + 1).map(n => <option key={n} value={n}>{n}</option>)}
        </select>
        <Button size="sm" disabled={running || !available} onClick={() => void run()}>{job?.status === 'completed' ? 'Erneut zuordnen' : 'Sprecher zuordnen'}</Button>
      </div>
      {!available && <p>Speaker-Engine in diesem Build nicht verfügbar.</p>}
      {job?.result && <p className="text-gray-600">{(() => { const r = JSON.parse(job.result); return `${r.voices} ${r.voices === 1 ? 'Stimme' : 'Stimmen'} · ${r.segments} Abschnitte · ${r.mixed} mit mehreren Stimmen · ${r.unclear} unklar${r.cached ? ' · Audioanalyse aus Cache' : ''}`; })()}</p>}
      {voices.map(voice => <VoiceNameForm key={`${meetingId}:${voice.speaker}:${voice.name}`} voice={voice} disabled={running} onSave={rename} />)}
      {voices.length > 0 && <p className="text-gray-600">Namen gelten für dieses Meeting. Bei einer anderen Stimmenzahl werden sie zurückgesetzt.</p>}
    </div>}
    {(error || job?.error) && <p role="alert" className="text-red-700 mt-2">{error || job?.error}</p>}
  </div>;
}

function VoiceNameForm({ voice, disabled, onSave }: { voice: VoiceName; disabled: boolean; onSave: (speaker: string, name: string) => Promise<void> }) {
  const [name, setName] = useState(voice.name ?? voice.speaker);
  return <form className="flex flex-wrap items-center gap-2" onSubmit={e => { e.preventDefault(); void onSave(voice.speaker, name); }}>
    <label htmlFor={`name-${voice.speaker}`}>{voice.speaker}</label>
    <input id={`name-${voice.speaker}`} className="border rounded px-2 py-1 min-w-0 max-w-full" value={name} maxLength={80} required disabled={disabled} onChange={e => setName(e.target.value)} />
    <Button type="submit" size="sm" variant="outline" disabled={disabled || !name.trim() || name === (voice.name ?? voice.speaker)}>Name speichern</Button>
  </form>;
}
