'use client';

import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { Switch } from '@/components/ui/switch';

export interface SpeakerPreferences { enabled: boolean; speaker_count: number; teams_detection: boolean }
export interface SpeakerSettingsData { preferences: SpeakerPreferences; engine_available: boolean; diagnostics_path: string }

export function SpeakerSettings({ compact = false }: { compact?: boolean }) {
  const [data, setData] = useState<SpeakerSettingsData | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { invoke<SpeakerSettingsData>('get_speaker_settings').then(setData).catch(e => setError(String(e))); }, []);
  const save = async (patch: Partial<SpeakerPreferences>) => {
    if (!data) return;
    setSaving(true); setError('');
    const preferences = { ...data.preferences, ...patch };
    try {
      await invoke('save_speaker_preferences', { preferences });
      setData({ ...data, preferences });
      window.dispatchEvent(new CustomEvent('speaker-preferences-changed'));
    } catch (e) { setError(String(e)); } finally { setSaving(false); }
  };
  return <section className={compact ? 'border rounded-lg p-3 text-sm bg-white' : 'bg-white rounded-xl border p-6 space-y-5'} aria-label="Sprecher und Teams">
    {!compact && <h2 className="text-lg font-semibold">Sprecherzuordnung und Teams</h2>}
    {!data && !error && <p role="status">Einstellungen werden geladen…</p>}
    {data && <>
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={compact ? 'speaker-auto-compact' : 'speaker-auto'} className="font-medium">Sprecher nach Stop zuordnen</label>
        <Switch id={compact ? 'speaker-auto-compact' : 'speaker-auto'} checked={data.preferences.enabled} disabled={saving || !data.engine_available} onCheckedChange={enabled => void save({ enabled })} />
      </div>
      {data.engine_available ? <div className="flex items-center gap-3 mt-2">
        <label htmlFor={compact ? 'speaker-count-compact' : 'speaker-count'}>Erwartete Stimmen</label>
        <select id={compact ? 'speaker-count-compact' : 'speaker-count'} className="border rounded px-2 py-1 bg-white" value={data.preferences.speaker_count} disabled={saving} onChange={e => void save({ speaker_count: Number(e.target.value) })}>
          {Array.from({ length: 8 }, (_, i) => i + 1).map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </div> : <p className="text-sm text-gray-600">Die lokale Speaker-Engine fehlt in diesem Build.</p>}
      {!compact && <>
        <p className="text-sm text-gray-600">Die Analyse ergänzt das vorhandene Transkript lokal. „Speaker 1“ usw. bezeichnet Stimmen, keine Teams-Konten. Namen kannst du im fertigen Transkript vergeben. Abschnitte mit mehreren Stimmen werden gekennzeichnet.</p>
        <div className="flex items-center justify-between gap-3">
          <label htmlFor="teams-detection" className="font-medium">Bei Teams-Mikrofonnutzung an die Aufnahme erinnern</label>
          <Switch id="teams-detection" checked={data.preferences.teams_detection} disabled={saving || !data.engine_available} onCheckedChange={teams_detection => void save({ teams_detection })} />
        </div>
        <p className="text-sm text-gray-600">Für Teams Desktop auf macOS ab 14.2. Auch der Vorraum oder ein Testanruf kann das Signal auslösen. Die Aufnahme startest du selbst; Teilnehmernamen und Meetingtitel werden nicht ausgelesen.</p>
        <details className="text-sm"><summary className="cursor-pointer">Lokale Diagnose</summary><p className="mt-2 break-all">{data.diagnostics_path}</p><p className="mt-1 text-gray-600">Protokolliert Verarbeitungsstatus und Teams-Audiosignale, ohne Transkripttext oder Namen. Aufnahmen von vor diesem Build haben keine solchen Erkennungslogs.</p></details>
      </>}
    </>}
    {error && <p role="alert" className="text-sm text-red-700 mt-2">{error}</p>}
  </section>;
}
