import type { Transcript } from '@/types';

/** One representation for native copy/export and summary input. */
export function transcriptSpeakerText(transcript: Pick<Transcript, 'speaker' | 'speaker_name' | 'text'>): string {
  const label = transcript.speaker_name ?? transcript.speaker;
  return label ? `${label}: ${transcript.text}` : transcript.text;
}
