# Lokale Meetingtranskripte mit Sprecherzuordnung

Die App-Integration ist unter [Native App](../../docs/fork/native-app.md) beschrieben. Für die normale Meetily-Bedienung brauchst du dieses optionale CLI nicht.

Dieses CLI verarbeitet ein **abgeschlossenes Meetily-Meeting oder eine Audiodatei** vollständig lokal. Es ergänzt die Community Edition als separates Werkzeug; die Meetily-Oberfläche und ihre SQLite-Datenbank werden nicht verändert.

Auf Marcs M1 eingerichtet: Meetily 0.4.1 in `/Applications/meetily.app`, Python-Umgebung und Modelle im lokalen Checkout. Für Transkription und Sprecherzuordnung ist nach dem Setup keine Internetverbindung erforderlich.

## Ein Meeting verarbeiten

Im Repository:

```sh
tools/meeting-notes/meeting-notes process \
  "$HOME/Movies/meetily-recordings/MEETING-ORDNER" \
  --speakers 4 --title "akomo Jour fixe"
```

`--speakers` bezeichnet die Zahl der **hörbar sprechenden Personen**, nicht automatisch alle Eingeladenen. Bekannte Zahlen sind für den ersten Einsatz empfohlen. `--speakers auto` ist experimentell: In Referenztests wurden teilweise zusätzliche Sprecher erzeugt. Für 2–8 Personen ist der Pfad vorgesehen; getestet wurden zwei und vier Stimmen. Größere Runden und reale akomo-/Teams-Meetings sind noch nicht validiert.

Ergebnis im Unterordner `meeting-notes`:

| Datei | Verwendung |
| --- | --- |
| `transcript.md` | Lesbares Transkript mit Zeitstempeln und Sprecherlabels |
| `transcript.html` | Eigenständiges Transkript zum Öffnen oder Teilen als Datei, ohne externe Ressourcen |
| `transcript.json` | Wortzeitstempel, Sprechersegmente, Herkunft und maschinenlesbare Gesprächsbeiträge |
| `speaker-samples/*.wav` | Kurze lokale Hörproben zum manuellen Benennen der Stimmen |
| `speaker-names.json` | Namen zu stabilen Labels innerhalb dieses Meetings |
| `.cache/` | Zwischenergebnisse für Wiederholung und Fortsetzung |

Die originalen Meetily-Dateien bleiben erhalten. Unklare und überlappende Stellen werden markiert. Die Erkennung trennt Stimmen; sie kennt keine Teilnehmernamen. Gleichzeitiges Sprechen wird nicht in getrennte Audiospuren zerlegt und kann die Transkription beeinträchtigen.

## Stimmen benennen

Zuerst die Hörproben prüfen, anschließend:

```sh
tools/meeting-notes/meeting-notes export \
  "$HOME/Movies/meetily-recordings/MEETING-ORDNER/meeting-notes/transcript.json" \
  --name 'Speaker 1=Marc' --name 'Speaker 2=Anna'
```

Das rendert die Ausgaben erneut, ohne Audio-/Sprachmodelle auszuführen. Namen gelten nur für dieses Meeting. Es werden keine dauerhaften Stimmprofile angelegt. Vorhandene Zusammenfassungen mit alten Namen werden entfernt und können anschließend aus dem aktualisierten Transkript neu erstellt werden.

## Lokale Zusammenfassung

Marcs vorhandenes Ollama-Modell `qwen3:4b` wurde getestet. Ollama muss laufen:

```sh
ollama serve
```

In einem zweiten Terminal:

```sh
tools/meeting-notes/meeting-notes summarize \
  "$HOME/Movies/meetily-recordings/MEETING-ORDNER/meeting-notes/transcript.json" \
  --model qwen3:4b
```

Erzeugt `summary.md` und `summary.json`: besprochene Themen, Beschlüsse, Aufgaben und offene Fragen. Jede Notiz muss ein wörtliches Zitat aus einer angegebenen Transkriptzeile enthalten; erfundene Zitate und ungültige Quellen führen zum Abbruch. Die Markdown-Ausgabe verweist auf Zeitstempel. Das prüft die Herkunft, garantiert aber keine korrekte Interpretation – Protokolle müssen fachlich geprüft werden.

Die Verarbeitung nutzt begrenzte Textblöcke, eine strukturierte Antwort und **einen Modellaufruf pro neuem Block**. Es gibt keine zusätzlichen Übersetzungs- oder Zusammenführungsaufrufe. Identische Wiederholungen nutzen den Cache und brauchen null weitere Modellaufrufe. Ollamas Modell-Digest wird automatisch in den Cache-Schlüssel aufgenommen. Tokenzahlen stehen in `summary.json`.

Ein anderer OpenAI-kompatibler Dienst lässt sich explizit wählen:

```sh
MEETING_NOTES_API_KEY='DEIN_API_KEY' tools/meeting-notes/meeting-notes summarize \
  /pfad/transcript.json --api-kind openai \
  --endpoint https://DEIN-ENDPOINT/v1 --model DEIN-MODELL \
  --model-revision DEINE-VERSION --allow-remote
```

Bei diesem Aufruf werden Textblöcke an den gewählten Dienst übertragen. Schlüssel werden nicht gespeichert. Für veränderte Gewichte unter derselben Modellbezeichnung `--model-revision` ändern. Anbieter müssen JSON-Antworten unterstützen. Meetily selbst unterstützt bereits Ollama und eigene OpenAI-kompatible Summary-Endpunkte; diese Ergänzung ist für den zusätzlichen Export-/Cache-Workflow gedacht.

## Ablage und Teilen

`--output /pfad/zum/meetingordner` legt Exporte an einem gewählten Ort ab, beispielsweise in einem eigenen OneDrive-Ordner. Jede andere Audiodatei oder veränderte Analysekonfiguration braucht einen neuen Ausgabeordner, damit vorhandene Sprecherbenennungen nicht versehentlich neu zugeordnet werden.

Die HTML-Datei enthält ausschließlich Text. Ein Fathom-artiger öffentlicher Freigabelink wird hier noch nicht bereitgestellt. Dafür braucht es eine bewusst gewählte Ablage mit Zugriffssteuerung, beispielsweise eine OneDrive-Dateifreigabe oder einen späteren eigenen Viewer.

## Einrichtung auf einem weiteren Rechner

Voraussetzungen: Python 3.12+, FFmpeg; getestet auf macOS arm64 mit Python 3.14. Die Python-Bibliothek ist plattformübergreifend, die beigelegten Shell-Starter richten sich an macOS/Linux.

```sh
tools/meeting-notes/setup.sh
```

Der Download umfasst ungefähr 530 MB komprimierte Modelle. Modell- und Paketversionen sind festgelegt. Die Downloads werden gegen festgeschriebene SHA-256-Werte geprüft. Modelle und private Ausgaben gehören nicht ins Git-Repository. Downloads erfolgen nur im Setup; lokale Verarbeitung lädt nichts nach.

## Prüfen

Schnelle Regressionstests ohne Modelle oder Netzwerk:

```sh
PYTHONPATH=tools/meeting-notes python3 -m unittest discover -s tools/meeting-notes/tests -v
```

Echter Modelltest mit öffentlichen Referenzdateien:

```sh
PYTHONPATH=tools/meeting-notes .venv-meeting-notes/bin/python tools/meeting-notes/verify.py
```

Dieser Test lädt öffentliche Testaudios herunter, prüft zwei und vier Sprecher, die tatsächliche Zuordnung der englischen Sätze zu zwei Stimmen, ein deutsches Transkript und einen wiederholten Lauf ohne erneute Inferenz. Ergebnis: `.local-meeting-notes/verification.json`. Er ist kein Qualitätsbenchmark für echte Teams-Aufnahmen.

## Modelle und Herkunft

- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx), Apache-2.0: lokale ONNX-Inferenz und vollständige Diarization-Pipeline.
- [pyannote segmentation 3.0](https://huggingface.co/pyannote/segmentation-3.0), MIT, CNRS/pyannote: Sprechersegmentierung. Die Lizenz bleibt im heruntergeladenen Modellordner erhalten.
- [3D-Speaker / ERes2Net](https://github.com/modelscope/3D-Speaker), Apache-2.0: Stimmrepräsentationen; ONNX-Konvertierung über sherpa-onnx.
- [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), CC-BY-4.0: mehrsprachige Transkription und Zeitstempel; INT8-ONNX-Konvertierung über sherpa-onnx. Modellherkunft und Prüfsummen werden in `transcript.json` dokumentiert.

Es werden keine Modellgewichte oder privaten Meetings mit diesem Fork veröffentlicht.
