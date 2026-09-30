# Meetily-Fork: Stand und Upstream-Strategie

Stand: 30. September 2026. Ausgangspunkt: `Zackriya-Solutions/meetily`, `main` bei `a2cb62e827da7ef59f65064c97233efb2313878e` (Release 0.4.1).

Fork: `marc-viladrich/meetily`. `origin` zeigt auf den Fork, `upstream` auf das Original. `main` bleibt die ursprüngliche Basis; `marc/meeting-transcripts` enthält unsere Ergänzungen als reguläre Commits. Alle Änderungen dieses ersten Schritts liegen in zusätzlichen Werkzeugen, Dokumentation, einer eigenen Test-Workflow-Datei und Ignore-Regeln. Es wurden keine fremden Feature-PRs pauschal gemergt.

## Ergebnis der PR-Prüfung

Offene PRs wurden über GitHub CLI erfasst. Die vier Diarization-Kandidaten wurden lokal als `review/pr-NUMMER` abgerufen und ihre Implementierungen verglichen. Die folgenden Automations-/Export-/API-Kandidaten wurden zusätzlich anhand ihrer Beschreibung und Diffs geprüft. Ein mergebarer Zustand ist keine Qualitätsfreigabe.

| Bereich | Kandidaten | Befund und Entscheidung |
| --- | --- | --- |
| Nemotron-Diarization | [#809](https://github.com/Zackriya-Solutions/meetily/pull/809) | Aktueller, konfliktfreier Ansatz mit Umbenennen/Hörproben. Auf Windows/CUDA vom Autor getestet. Der Live-Worker wird ergänzt; der Importpfad bekommt nur neue Testfelder, keine eigentliche Diarization. Fallbacks vergeben teilweise „Speaker 1“ ohne sichere Erkennung. Windows-UI-/Startup-Änderungen sind fachfremd. Nicht als fertigen macOS-/Importpfad übernommen. |
| CAM++-Diarization | [#511](https://github.com/Zackriya-Solutions/meetily/pull/511) | Native Rust/ONNX-Einbettung, Live-Labels, Stimmprofile und zusätzliche Overlap-Arbeit. Konflikte mit aktuellem Main. CAM++ wurde als Modellvergleich ausprobiert: Die verwendete ONNX-Datei führte im ersten englischen Referenztest zwei Stimmen zusammen; ERes2Net trennte sie. Keine allgemeine Qualitätsaussage über sämtliche CAM++-Varianten. |
| Diarization-Grundlage | [#598](https://github.com/Zackriya-Solutions/meetily/pull/598) | Umfangreiche Typen, Speicherung, Alignment und UI; noch kein vollständiger produktiver Modellpfad. Hilfreiche Referenz für eine spätere Oberfläche. |
| Breiter Feature-Fork | [#538](https://github.com/Zackriya-Solutions/meetily/pull/538) | 116 Dateien einschließlich lokaler API, Modellen und UI. Im betrachteten Offline-Pfad liefert `segmentation.rs` einzelne Frames als Segmente; `offline.rs` verwirft Segmente unter 0,5 s. Damit fällt dieser Pfad vor der Einbettung leer aus. Nicht als Gesamtpaket übernommen. |
| Advanced Exports | [#714](https://github.com/Zackriya-Solutions/meetily/pull/714), zuvor #707; außerdem #515/#478 | #714 ergänzt Markdown/HTML, Druck/PDF, Stapel-/Abschnittsexport und zusätzliche UI-/Template-Änderungen. Konflikte mit Main. Für das erste Sprechertranskript übernehmen wir den Bedarf in einem eigenständigen Markdown-/HTML-Export. |
| Meeting-Erkennung | [#733](https://github.com/Zackriya-Solutions/meetily/pull/733), abhängig von #732 | Kein zuverlässiger Teams-Desktop-Pfad. Die URL-Regel `teams.microsoft.com/v2/` ist breiter als ein aktiver Call. Der Watcher startet nach manuellem Stop erneut, wenn ein Signal weiterhin anliegt: `(true, false, _)` trifft vor dem Aufräumzweig. Kein Settings-Opt-in. Vorerst nicht integriert. |
| Kalender | [#666](https://github.com/Zackriya-Solutions/meetily/pull/666), [#797](https://github.com/Zackriya-Solutions/meetily/pull/797) | Google-Kalender-/Meet-Ansätze, keine vorhandene Microsoft-Kalender-/Teams-Integration. Konflikte. Später EventKit/ICS oder Microsoft Graph anhand des tatsächlich verwendeten Kalenders auswählen. |
| Lokale Steuerung/CLI | [#499](https://github.com/Zackriya-Solutions/meetily/pull/499), [#457](https://github.com/Zackriya-Solutions/meetily/pull/457) | #499 bietet lokale HTTP-Steuerung, jedoch ohne Zugriffstoken/Origin-Prüfung und mit zusätzlicher Frontend-Koordination. #457 bietet URL-Schema plus macOS-Notifications. Beides benötigt weitere Integrationstests. Unser CLI steuert aktuell Nachverarbeitung, nicht die Aufnahme. |
| Eigene ASR-Modelle/API | [#669](https://github.com/Zackriya-Solutions/meetily/pull/669), #506 | Zusätzliche Audio-Transkriptionsprovider und lokale Whisper-Dateipfade. Für den lokalen Parakeet-Pfad nicht benötigt. Dies ist etwas anderes als ein eigener LLM-Endpunkt für Zusammenfassungen. |
| Eigener KI-Endpunkt/Summaries | Bereits in `main`; weitere Provider-PRs #671/#678, Prompt-Arbeit #480 | Ollama, Custom OpenAI und Summary-Templates existieren bereits. Für deutsche Notizen kann der Main-Pfad mehrere englische Zwischen-/Übersetzungsschritte ausführen. Die Ergänzung extrahiert direkt deutsche, quellenbelegte Notizen mit einem Aufruf pro neuem Textblock und Cache. |
| Webhooks | [Issue #595](https://github.com/Zackriya-Solutions/meetily/issues/595), geschlossener PR #423 | Kein hier verifizierter, allgemeiner produktiver Abschluss-Webhook. Vorzugsweise später auf dem erfolgreichen Export aufsetzen und Versand wiederholbar machen. |
| Fragen an Meetings | [#810](https://github.com/Zackriya-Solutions/meetily/pull/810), #770 | Weitere Gesprächs-/Suchfunktionen; nicht nötig für den ersten Transkriptpfad und noch nicht im Detail geprüft. |

Geprüfte Diarization-Stände:

```text
#809 a196fc8eae61312c1f5d442a4636281bd0c3b26a
#511 5661422408492a51e6ac28292d1f26b4e378d6d3
#598 90b67c04df87e4a5916680917b9902737dd86af4
#538 cbc780f5cd97003b2dbb2ab7a1e3d07815701a6d
```

Es wurden nicht sämtliche tausend Forks einzeln gescannt. Die Prüfung konzentriert sich auf konkrete offene Beiträge für die angefragten Funktionen. Private PRO-Implementierungen sind keine Grundlage dieses Forks.

## Architekturentscheidung

Der erste Arbeitsablauf ist **Meetily-Aufnahme → lokale Nachverarbeitung → geprüftes Transkript/Protokoll**. Das unabhängige Werkzeug nutzt sherpa-onnx für Segmentierung und Clustering und Parakeet v3 für Wortzeitstempel. Es ist kein neuer FastAPI-Backend-Server und verwendet nicht das archivierte `backend/`.

Die Alternative wäre eine native Übernahme von #809 oder #511 mit Änderungen an Live-Worker, Sitzungszustand, SQLite, Import, Recovery und mehreren UI-Ansichten. Das erhöht die Fläche für Upstream-Konflikte und löst die derzeitigen Modell-/Importprobleme nicht automatisch. Der separate Pfad ist für den ersten überprüfbaren Stand kleiner und funktioniert auch mit einem unveränderten Community-Binary. Eine spätere native Oberfläche kann dieselben versionierten JSON-Ergebnisse konsumieren.

Transcript-JSON ist das Quellartefakt. Markdown und HTML sind daraus abgeleitet. Sprecherbenennungen werden separat gespeichert. Inferenz-Cache-Schlüssel enthalten Audiohash, Modellprüfsummen, Runtime-/Pipelineversion und Analyseparameter; Summary-Cache-Schlüssel zusätzlich Prompt, Schema, Endpunkt, Modellversion und benannte Quellzeilen. Betriebssystem-Sperren lösen sich nach einem Prozessabbruch. Einzeldateien werden atomar ersetzt; Wiederholung rendert einen eventuell unterbrochenen Export fertig.

## Upstream aktualisieren

```sh
scripts/sync-marc-upstream.sh
```

Dieser Aufruf holt Änderungen und zeigt neue Commits. Auf `marc/meeting-transcripts` mit sauberem Arbeitsbaum:

```sh
scripts/sync-marc-upstream.sh --merge
PYTHONPATH=tools/meeting-notes .venv-meeting-notes/bin/python tools/meeting-notes/verify.py
git push origin marc/meeting-transcripts
```

Der Merge bewahrt die gemeinsame Git-Historie. Der Originalstand lässt sich weiter direkt nachvollziehen; unsere Ergänzung ist kein unabhängiger Snapshot. Falls gewünscht, kann der Fork-Main separat mit `gh repo sync marc-viladrich/meetily --source Zackriya-Solutions/meetily --branch main` aktualisiert werden. Neue Upstream-Features ersetzen eigene Funktionen gezielt nach Tests; kein unbeaufsichtigtes Mischen offener PRs.

## Nachgewiesener Stand

Auf Apple M1, 16 GB RAM, mit CPU-Inferenz:

- 14 Regressionstests: Alignment, Sprecherwechsel, TDT-Pausenzeiten, Overlap, Chunk-Ende, sichere HTML-Ausgabe, Quellenvalidierung, Cache, Namensänderungen und noch laufende Audioaufnahmen.
- Öffentliche Referenzdateien: zwei Sprecher/16 s, zwei Sprecher/34 s und vier Sprecher/56,86 s wurden mit vorgegebener Sprecherzahl getrennt. Diarization dauerte im gemessenen Lauf etwa 1,5 s / 6,7 s / 8,2 s.
- Vollständiger erster Referenzlauf: 33 Wörter, zwei richtig zugeordnete Gesprächsbeiträge; circa 3,9 s einschließlich ASR. Deutscher Kurztest lieferte den erwarteten Satz.
- Wiederholung mit verbotener erneuter Diarization/ASR erzeugte identische Ergebnisse aus dem Cache.
- Lokales `qwen3:4b`: künstlicher deutscher Protokolltest mit explizitem Beschluss, Aufgabe und offener Frage; 425 Input- und 220 Output-Tokens. Die unverbindliche Website-Idee wurde nicht als Beschluss ausgegeben. Wiederholung: null Modellaufrufe. Das ist ein Integrationstest, kein echtes akomo-Meeting.
- HTML im T3-Browser geöffnet und visuell kontrolliert.
- Unveränderter nativer Meetily-Main besteht `cargo check -p meetily --locked`. Unter diesem Checkout-Pfad enthalten externe Metal-Buildskripte ein Problem mit `&`; ein separater `CARGO_TARGET_DIR` ohne Sonderzeichen behebt es. Für Xcode wird `DEVELOPER_DIR` explizit gesetzt. Die geprüften Sidecar-Binaries stammen aus dem offiziellen 0.4.1-Paket.

Noch offen: echtes deutsches Teams-Meeting, acht Personen, lange Sitzungen und Übersprechen, native Bedienoberfläche für die Ergänzung, Meeting-/Kalender-Erkennung, Versand-Webhooks und gehostete Freigabelinks. Das installierte Community-Paket ist keine neu gebaute PRO-Version.

Bedienung: [tools/meeting-notes/README.md](../../tools/meeting-notes/README.md).
