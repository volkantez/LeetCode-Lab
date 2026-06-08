# LeetCode-Lab

Automatische Daten-Pipeline zur Code-Evaluierung von LLMs für LeetCode.

[English version](README.md)

## Beschreibung

Dieses Projekt importiert ausgewählte LeetCode-Aufgaben über die LeetCode-GraphQL-Schnittstelle. Anschließend werden mithilfe der OpenAI API automatisch Lösungen in den konfigurierten Programmiersprachen generiert und an LeetCode eingereicht. Die offiziellen Submission-Ergebnisse werden gespeichert, sodass die Leistung des verwendeten Modells in einem strukturierten, datensatzbasierten Workflow nachvollziehbar ausgewertet werden kann.

## Funktionen

- LeetCode-Aufgaben anhand einer Konfiguration auswählen und importieren.
- Aus jeder importierten Aufgabe einen standardisierten Prompt erzeugen.
- Lösungen in den konfigurierten Programmiersprachen über die OpenAI API generieren.
- Generierte Lösungen automatisch an LeetCode submitten.
- LeetCode-Status, Laufzeit, Speicher, bestandene Tests, Modell und Submission
  ID in einer Excel-kompatiblen CSV protokollieren.

## Voraussetzungen

- Python 3.9 oder neuer
- stabile Internetverbindung
- im Browser mit einem LeetCode-Account eingeloggt sein
- OpenAI API-Key


## Einrichtung

### Schritt 1: Repository Klonen

```bash
git clone https://github.com/volkantez/LeetCode-Lab.git
cd LeetCode-Lab
```

### Schritt 2: Umgebungsvariablen konfigurieren

Kopiere `.env.example` und erstelle im Projektordner eine neue Datei mit dem Namen `.env`:

```bash
cp .env.example .env
```

Trage danach die benötigten Werte ein:

```env
OPENAI_API_KEY=dein_openai_api_key
CSRF_TOKEN=dein_csrftoken_cookie
LEETCODE_SESSION=dein_LEETCODE_SESSION_cookie
```

`OPENAI_API_KEY` wird für die automatische Lösungsgenerierung benötigt. Einen
API-Key kannst du auf der [OpenAI API-Key-Seite](https://platform.openai.com/api-keys)
erstellen.

`LEETCODE_SESSION` und `CSRF_TOKEN` werden für offizielle LeetCode-
Submissions benötigt. Du findest sie in deinem Browser, nachdem du bei
LeetCode eingeloggt bist:

1. Öffne `https://leetcode.com` im Browser.
2. Öffne die Entwicklertools.
3. Öffne den Bereich `Application` beziehungsweise `Storage`.
4. Wähle unter `Cookies` die Domain `https://leetcode.com`.
5. Kopiere die Werte der Cookies `LEETCODE_SESSION` und `csrftoken` in deine
   `.env`-Datei.


### Schritt 3: Datensatz importieren

Die Aufgaben werden anhand der Konfiguration in `LeetCodeConfig.json` ausgewählt
und importiert. Dort werden auch der Datensatzname, die Programmiersprachen und
das Modell festgelegt. Das Standardmodell ist `gpt-5.2`.

In der Praxis sollten für unterschiedliche Modelle, Prompts oder
Experimentkonfigurationen getrennte Datensätze verwendet werden.

```bash
python3 -m src.cli import.dataset
```

Der Datensatzname wird über `dataset` festgelegt. Die Sprachen werden über
`languages` gesetzt. Beispiel:

```json
"dataset": "leetcode_2514_2550_gpt5.2",
"languages": ["python3", "cpp"]
```

Für jede Sprache werden eigene Aufgaben-JSONs gespeichert:

```text
datasets/<dataset>/problems/<language>/
```

Typische Sprachwerte sind `python`, `python3`, `cpp`, `java`, `javascript`,
`typescript`, `csharp`, `golang`, `rust`, `kotlin`, `swift` und `php`.


### Schritt 4: Datensatz lösen und submitten

Alle importierten Aufgaben aus dem konfigurierten `dataset` werden für jede
Sprache aus `languages` nacheinander mit der OpenAI API gelöst und anschließend
an LeetCode eingereicht:

```bash
python3 -m src.cli submit.dataset
```
Die generierten Lösungen werden pro Datensatz und Sprache gespeichert:

```text
datasets/<dataset>/solutions/<language>/
```
Die detaillierten LeetCode-Antworten inkl. zusammengefassten Ergebnisse werden hier gespeichert:

```text
datasets/<dataset>/results/
```

Bereits erfolgreich gelöste Aufgaben werden beim nächsten Lauf automatisch
innerhalb desselben Datensatzes und derselben Sprache übersprungen. 

## Prompt anpassen

Die Eingabe für das OpenAI-Modell wird über folgendes Template erzeugt:

```text
default_prompt.txt
```

Dieses Template kann angepasst werden, um das Verhalten der generierten Lösungen
zu beeinflussen. 

## Umfang und Grenzen

Die Korrektheit der generierten Lösungen wird über offizielle LeetCode-Submissions geprüft. Dadurch werden auch die versteckten Testfälle von LeetCode berücksichtigt.

Die Submission nutzt private LeetCode-Session-Cookies und direkte HTTP-Requests an LeetCode-Endpunkte. Das kann fehlschlagen, wenn die Session abläuft, LeetCode Endpunkte ändert, Cloudflare den Request blockiert oder LeetCode Submissions rate-limited.
Wenn die Cookies ablaufen, müssen die Werte in `.env` mit neuen
`LEETCODE_SESSION`- und `CSRF_TOKEN`-Werten aus dem Browser aktualisiert
werden.


## Kontext der Bachelorarbeit

Die Bachelorarbeit evaluierte modellgenerierten Code über Online-Submissions auf
LeetCode und erfasste Acceptance, Fehlerkategorien, Laufzeit und Speicher. 
Diese öffentliche Version macht den Workflow über eine feste Konfiguration und zwei CLI-Befehle leichter wiederholbar.

## Lizenz

[LICENSE](LICENSE)
