# Sprecherzuordnung in Meetily

Die Erweiterung ist in der nativen Meetily-App integriert. Die über das Onboarding heruntergeladenen Engines werden weiterverwendet: Parakeet für Transkription, Built-in AI/Qwen oder der ausgewählte Provider für Zusammenfassungen. Für Sprecherzuordnung kommen Pyannote-Segmentierung und ERes2Net hinzu; sie ersetzen weder Parakeet noch Qwen.

## Bedienung

Auf der Startseite: **Sprecher nach Stop zuordnen** einschalten und die Zahl der tatsächlich sprechenden Stimmen wählen (1–8). Die automatische Zuordnung ist aus Ressourcengründen standardmäßig ausgeschaltet; zwei Stimmen sind vorbelegt. Während einer Aufnahme wird keine neue manuelle Analyse gestartet. Aufnahme wie gewohnt starten und stoppen. Nach dem Speichern ergänzt eine lokale Analyse die Sprecherlabels. Import und erneute Transkription verwenden denselben Analysepfad.

In einem gespeicherten Meeting **Sprecherzuordnung** öffnen, Stimmenzahl wählen und **Sprecher zuordnen** klicken. Unter jedem eindeutigen Voice-Cluster kann ein Name gespeichert werden. Die Namen gelten nur für dieses Meeting und werden bei geänderter Stimmenzahl verworfen. Die Audioanalyse wird bei gleichem Audio, Modellen, Helper und Stimmenzahl aus dem Cache gelesen.

Die App behält den vorhandenen Transkripttext und seine Zeitstempel. Ihre vorhandenen Abschnitte sind nicht wortgenau: Wenn ein Abschnitt mehrere wesentliche Stimmen enthält, steht dort **Mehrere Stimmen**, bei fehlender oder geringer Sprachabdeckung **Unklar**. Eine vollständige Aufteilung solcher Abschnitte auf einzelne Wörter bleibt eine weitere Ausbaustufe. Das optionale CLI bietet bereits eine getrennte erneute Parakeet-Transkription mit Wortzeitstempeln.

**Speaker 1** bezeichnet eine Stimme, keine Teilnehmeridentität. Es gibt keine automatische Teams-Namenszuordnung. Derselbe Mensch über zwei Geräte ist kein verlässlicher Zwei-Personen-Test. Zwei unterschiedliche sprechende Menschen und ein bekannter Ablauf sind dafür besser.

Gespeicherte Namen erscheinen im Transkript, im vorhandenen Kopieren-Export und im Eingabetext der nativen Summary-Funktion. Die Erweiterung schreibt keine Zusammenfassungen automatisch um.

## Teams-Hinweis und Diagnose

Unter **Settings → Recordings → Sprecherzuordnung und Teams** kann die Erinnerung bei Teams-Mikrofonnutzung eingeschaltet werden. Der Mac meldet aktive Eingangsstreams der Teams-Desktop-Prozesse über Core Audio (macOS ≥14.2). Drei aktive Abfragen im Abstand von zwei Sekunden lösen einen Hinweis aus. **Aufnahme starten** benutzt Meetilys vorhandenen Aufnahmeablauf. Nach Schließen kommt der Hinweis für das gleiche durchgehende Signal nicht wieder; erst nach mindestens drei inaktiven Abfragen wird er erneut möglich.

Auch Vorraum, Geräteeinstellungen oder Testanruf können dieses Signal auslösen. Ein sicherer automatischer Aufnahmestart, ein Meetingtitel und Teilnehmernamen sind damit nicht umgesetzt. Browser-Teams und Kalender-Anbindung sind ebenfalls nicht enthalten.

Lokale Ereignisse stehen unter `diagnostics/events.jsonl` im vorhandenen Meetily-Appdatenverzeichnis. Sie enthalten Zeit, Signal, Jobstatus und Zählwerte, ohne Gesprächsinhalt oder Namen. Rotation bei 2 MB, eine Vorgängerdatei. Frühere Aufnahmen hatten diese Diagnose noch nicht: Ihr Teams-Beitritt lässt sich daraus nicht rückwirkend rekonstruieren. `speaker_jobs` hält den letzten Verarbeitungsstand; unterbrochene Jobs sind nach Neustart als wiederholbarer Fehler sichtbar.

## Architektur und Build

Die vorhandene `transcripts.speaker`-Spalte hält die Voice-Cluster. Zwei additive Tabellen enthalten meetingbezogene Namen und Jobstatus. Die Datenbank bleibt die Quelle für Oberfläche, Pagination, Kopieren und Summary-Eingabe. Änderungen an Transkript oder Audio während der Analyse verhindern das Überschreiben mit veralteten Ergebnissen.

Die Speaker-Engine ist ein eigener kleiner Prozess mit Sherpa-ONNX 1.13.8 und dessen eigener ONNX Runtime. Damit werden keine inkompatiblen Runtime-Bibliotheken in Meetilys Parakeet-Prozess geladen. Während der Sprecheranalyse gibt es keine Netzwerkaufrufe, keine LLM-Aufrufe und keine Tokenkosten. Der nächste Build begrenzt Sherpa auf einen Inferenzthread und startet den Helper mit niedriger Priorität. Die Ressourcenkosten dieses geänderten Profils sind noch nicht gemessen. Die Engines aus Meetilys Onboarding und ihre Einstellungen bleiben unverändert.

Der aktuelle native Helper-Build ist **macOS ARM64**. Ohne vorbereiteten Helper sind die Zusatzfunktionen deaktiviert; die übrige Community Edition bleibt baubar. Für andere Plattformen muss der Helper-Build portiert werden.

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer python3 tools/speaker-engine/prepare.py
cd frontend
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  CARGO_TARGET_DIR="$HOME/Library/Caches/meetily-cargo" \
  CMAKE_POLICY_VERSION_MINIMUM=3.5 NEXT_TELEMETRY_DISABLED=1 \
  pnpm tauri build --debug --config src-tauri/tauri.marc.conf.json --bundles app
```

Die Vorbereitung lädt ausschließlich gepinnte offizielle Runtime-/Modellartefakte und prüft SHA-256. Die Python-CLI-Umgebung ist für die native App nicht erforderlich. Der Target-Pfad außerhalb des Checkouts vermeidet Shell-Fehler in Whisper/Metal-Builds bei Leerzeichen und `&` im Projektpfad. Der Fork verwendet seinen eigenen Update-Endpunkt und erzeugt keine mit dem Upstream-Schlüssel signierten Update-Artefakte.

Tests: `pnpm --dir frontend exec tsc --noEmit`; im Rust-Workspace `cargo test -p meetily speakers::tests --lib` mit obigen Build-Umgebungsvariablen. Die Datenbankprüfung umfasst Pagination und meetingbezogene Namen ohne Übertragung auf ein anderes Meeting. Referenzaudio mit 2/2/4 Stimmen prüft den tatsächlichen nativen Helper. Acht Stimmen, lange deutsche Teams-Meetings und Überlappungen mehrerer Personen bleiben echte Praxistests.

## T3 Code und Git

Das Git-Repository ist der Unterordner `meetily`, nicht der Sammelordner `Side Projects`. Eine verknüpfte PR wird unabhängig vom Projektpfad angezeigt. Daher kann im übergeordneten T3-Projekt gleichzeitig **Initialize Git** erscheinen.

In T3 ein Projekt für den vollständigen Repository-Pfad öffnen: `/Users/marcviladrich/Freelance/AI & Automation/Side Projects/meetily`. Neue Entwicklungsthreads in diesem Projekt erstellen. Den Sammelordner nicht als zusätzliches Git-Repository initialisieren. `origin` zeigt auf `marc-viladrich/meetily`, `upstream` auf das Original; GitHub CLI, Push und PR-Verknüpfung sind bereits eingerichtet.

## Ressourcenprüfung nach dem ersten App-Test

Marcs 16-GB-M1 meldete starke Wärme und Lüfterlast während der Entwicklung. Ein laufender Rust-Compiler belegte dabei ca. 560 % CPU; gleichzeitig wurde die native lokale Summary-Engine getestet (ca. 2,2 GB Modell-RSS). Builds und Summary-Prozess wurden beendet. Automatische Sprecheranalyse ist im installierten Testbuild ausgeschaltet. Es wurden danach keine weiteren Inferenz- oder Build-Lasttests gestartet.

Die Sprecheranalyse im getesteten Zwei-Thread-Profil benötigte für 189,67 Sekunden Audio in der Debug-App ca. 74 Sekunden einschließlich Decoding; der direkte Helper mit FFmpeg-Vorbereitung ca. 47 Sekunden. Das reicht nicht als Beleg für einen alltagstauglichen Einsatz neben Teams. Der installierte Build wurde funktional geprüft, gilt aber bis zu einem isolierten Ressourcenvergleich nicht als freigegeben.

Die Ein-Thread-/Niedrigprioritätsänderungen und die Aufnahme-Startprüfung im letzten Source-Stand sind noch nicht gebaut und noch nicht gegen die App geprüft. Eine neue Aufnahme, die während bereits laufender Analyse startet, braucht zusätzlich eine verlässliche Pause/Abbruchsteuerung. Vor einer erneuten Freigabe: getrennt Aufnahme allein, Teams plus Aufnahme, und anschließend manuelle Sprecheranalyse vergleichen; CPU, GPU, Speicher, Laufzeit und subjektive Wärme messen. Keine parallelen Builds oder Zusammenfassungstests dabei.

Die native Qwen-Zusammenfassung konnte die Aufnahme technisch verarbeiten, enthielt aber unbelegte Behauptungen über automatische Meeting-Erkennung und falsche Maßnahmen. Sie ist damit noch keine belastbare automatisch übernehmbare Zusammenfassung.
