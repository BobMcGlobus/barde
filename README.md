<img src="https://raw.githubusercontent.com/BobMcGlobus/barde/main/custom_components/barde/brand/logo.png" alt="Barde" width="380">

# Barde 🎵

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Lint](https://github.com/BobMcGlobus/barde/actions/workflows/lint.yml/badge.svg)](https://github.com/BobMcGlobus/barde/actions/workflows/lint.yml)
[![Test](https://github.com/BobMcGlobus/barde/actions/workflows/test.yml/badge.svg)](https://github.com/BobMcGlobus/barde/actions/workflows/test.yml)
[![Validate](https://github.com/BobMcGlobus/barde/actions/workflows/validate.yml/badge.svg)](https://github.com/BobMcGlobus/barde/actions/workflows/validate.yml)

> **⚠️ Alpha — noch nicht gegen eine laufende Instanz getestet.** Der Code ist
> vollständig, Lint und Unit-Tests laufen grün, aber der erste Durchlauf gegen
> echte Lautsprecher steht aus. Siehe [Status](#status).

**Barde** ist eine Home Assistant Custom Integration, die dem
Assist-Conversation-Agent eine kleine, handgeschnittene Tool-API für
**Music Assistant** gibt: Songs, Alben und Playlists gezielt auf bestimmten
Lautsprechern starten, Räume gruppieren, Lautstärke und Transport steuern,
die Warteschlange in einen anderen Raum übernehmen.

Barde registriert sich als LLM-API neben „Assist" — Lichter, Klima und Sensoren
laufen unverändert über die eingebaute API, Musik über Barde.

## Warum nicht MCP

Music Assistant bringt ab 2.9 ein FastMCP-Server-Plugin mit. Die HA-Seite kann
als MCP-Client aber nur SSE + OAuth, MA spricht streamable HTTP mit
Bearer-Token — es bräuchte also einen `mcp-proxy`-Container dazwischen. Selbst
dann wären es ~20–30 generische Tool-Definitionen in **jedem** Assist-Turn, und
das Modell müsste zwischen HA-`media_player`-Entities und MA-internen Player-IDs
unterscheiden.

Barde nutzt stattdessen die dokumentierten `music_assistant.*` Service-Actions
der bereits konfigurierten MA-Integration: keine zweite Verbindung, kein Token,
kein Container, sechs Tools statt dreißig.

## Voraussetzungen

- **Home Assistant 2026.7.0 oder neuer**
- Eingerichtete **Music Assistant**-Integration mit mindestens einem Player
- Ein Conversation-Agent, der LLM-APIs unterstützt (OpenAI, Anthropic, Ollama,
  Google Generative AI …)

## Installation via HACS (Custom Repository)

1. HACS öffnen → Menü (⋮ oben rechts) → **Benutzerdefinierte Repositories**
2. Repository-URL eintragen: `https://github.com/BobMcGlobus/barde`,
   Typ: **Integration**
3. „Barde" suchen, herunterladen, Home Assistant neu starten
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Barde**

## Einrichtung

Nach dem Hinzufügen muss die API dem Agenten noch zugewiesen werden:

**Einstellungen → Sprachassistenten → \<dein Agent\> → Konfigurieren →
LLM-APIs** → „Barde" zusätzlich zu „Assist" anhaken.

Alles Weitere läuft über **Konfigurieren** am Barde-Eintrag
(siehe [Optionen](#optionen)).

## Die sechs Tools

Bewusst sechs. Jede Tool-Definition kostet Kontext in *jedem* Turn — die
Transport-Kommandos stecken deshalb in einem Tool mit `action`-Enum statt in
acht Einzeltools. Alle Rückgaben bleiben klein (3–8 Felder).

| Tool | Zweck | Wichtige Parameter |
|---|---|---|
| `musik_abspielen` | Suchen, ranken, abspielen | `query`, `media_type`, `artist`, `player`, `enqueue`, `radio_mode`, `shuffle` |
| `musik_suchen` | Suchen ohne Abspielen | `query`, `media_type`, `artist`, `limit`, `library_only` |
| `musik_steuern` | Transport + Lautstärke | `action`, `player`, `wert` |
| `lautsprecher_gruppieren` | Multiroom | `aktion`, `hauptplayer`, `player[]` |
| `musik_uebernehmen` | Queue in anderen Raum | `nach`, `von`, `auto_play` |
| `was_laeuft` | Status, optional Queue | `player`, `queue_anzeigen` |

`musik_steuern` kennt: `pause`, `weiter`, `stop`, `naechster`, `vorheriger`,
`lautstaerke` (mit `wert` 0–100), `lauter`, `leiser`, `stumm`, `laut`,
`shuffle_an`, `shuffle_aus`, `wiederholen_an`, `wiederholen_aus`,
`queue_leeren`.

### Warum eigenes Ranking

`music_assistant.play_media` nimmt zwar auch Klartext-Namen entgegen, resolved
dann aber intern und nimmt den ersten Treffer. Barde macht **search → rank →
play** und kann dadurch Typ- und Provider-Präferenzen berücksichtigen und ehrlich
zurückmelden, was tatsächlich läuft:

```json
{"gespielt": "Rumours", "typ": "album", "künstler": "Fleetwood Mac",
 "player": "Wohnzimmer", "quelle": "library", "alternativen": 2}
```

Reihenfolge: exakter Namenstreffer → angeforderter `media_type` → Standardordnung
(playlist > album > artist > track > radio > audiobook > podcast) → passender
Künstler → `provider_preference` → Bibliothek vor Streaming → Namensähnlichkeit.

`alternativen` gibt dem Modell die Chance, von sich aus „ich hab X gespielt, es
gäbe auch noch …" zu sagen, ohne einen zweiten Tool-Call zu brauchen.

### Hörbücher und Podcasts

`audiobook` und `podcast` sind gleichberechtigte `media_type`-Werte und werden
auch ohne Angabe mitgesucht — Provider wie **Audiobookshelf** kommen damit ohne
Extrabehandlung durch. Im Ranking stehen sie unter der Musik, damit „spiel
Rumours" weiterhin das Album trifft und nicht ein gleichnamiges Hörbuch.

### Wenn die Suche nichts findet

Sprachanfragen tragen Rauschen, das die Bibliothek nicht kennt. Statt sofort
aufzugeben, lockert `musik_abspielen` die Anfrage schrittweise — und zwar nur
bei leerem Ergebnis, jeder Schritt kostet eine Runde:

1. wie angefragt
2. ohne den geratenen `media_type` (das Modell tippt gern auf `track`)
3. ohne `artist` (Music Assistant baut daraus `"Künstler - Titel"`, ein
   falscher Credit killt die Suche)
4. ohne Füllwörter: „Hazbin Hotel Songs" → „Hazbin Hotel"

### Fehlerverhalten

Ein Tool antwortet immer. Home Assistants Chat-Log fängt bei Tool-Calls nur
`HomeAssistantError` und `vol.Invalid` ab — jede andere Exception beendet den
kompletten Assist-Lauf mit „Unexpected error during intent recognition". Music
Assistant wiederum lässt in `handle_search` einen rohen `MusicAssistantError`
durch. Barde fängt deshalb alles, loggt es mit Traceback und gibt dem Modell
ein `{"fehler": …}`, über das es sprechen kann.

## Player-Auflösung

Erster Treffer gewinnt:

1. **Explizit genannt** — Fuzzy-Match gegen Friendly Names, Entity-Aliase und
   Area-Namen. Umlaute werden entfaltet, Gerätewörter ignoriert
   („Wohnzimmerlautsprecher" ↔ „Wohnzimmer"), Tippfehler bis zu einem gewissen
   Grad toleriert.
2. **Raum des Sprechers** — über `device_id` → Device Registry → Area.
3. **Der eine Player, der gerade spielt** — für „mach lauter" vom Handy aus.
4. **`default_player`** aus den Optionen.
5. Sonst ein Fehler mit Liste: `{"fehler": …, "verfügbar": ["Wohnzimmer", …]}` —
   damit das Modell sinnvoll rückfragen kann statt zu halluzinieren.

Es wird konsequent mit `entity_id` gearbeitet, nie mit `device_id`.

## api_prompt

Wird pro Konversation gebaut und ist der eigentliche Hebel für die Trefferquote:

```
Du bist der Barde des Hauses und steuerst Music Assistant.

Verfügbare Lautsprecher (Raum → Zustand):
  Wohnzimmer → spielt "Get Lucky" (Daft Punk)
  Küche → aus
  Bad → aus, gruppiert mit Wohnzimmer

Wenn kein Raum genannt wird, nimm den Raum, aus dem gesprochen wurde.
Frage nicht nach, wenn ein plausibler Treffer existiert — spiele ihn und sage,
was du gewählt hast.
Für alles rund um Musik nutze die Barde-Tools, nicht die allgemeinen
Medien-Intents von Assist.

Bekannte Playlists: Einschlafen, Kochmusik, Sonntagmorgen, Werkstatt
```

Die Lautsprecherzustände kommen live aus der State Machine, die Playlist-Namen
aus `music_assistant.get_library` und werden `context_ttl` Minuten gecacht. Der
Playlist-Block ist der Unterschied zwischen „leg die Kochmusik auf" →
funktioniert und → Suche nach dem Wort „Kochmusik" bei allen Streaming-Anbietern.

## Optionen

| Option | Default | Zweck |
|---|---|---|
| Standard-Lautsprecher | — | Fallback, wenn kein Raum ableitbar ist |
| Playlist-Namen in den Prompt | an | Playlists im `api_prompt` nennen |
| Lieblingskünstler in den Prompt | aus | Favoriten im `api_prompt` nennen |
| Bibliotheks-Cache | 15 min | Gültigkeit des Library-Kontexts |
| Lautstärkeschritt | 10 | Prozentpunkte für `lauter`/`leiser` |
| Bevorzugte Quellen | library, spotify | Reihenfolge beim Ranking |
| Nur freigegebene Lautsprecher | an | Nicht zu Assist exponierte Player ignorieren |
| Music-Assistant-Instanz | Automatisch | Nur nötig bei mehreren MA-Instanzen |

Optionsänderungen laden die Integration neu, der Cache wird dabei verworfen.

## Sprachbeispiele

```
"spiel Rumours"                              → Album, Raum des Sprechers
"spiel das Album Rumours von Fleetwood Mac"  → Disambiguierung über artist
"leg die Kochmusik auf"                      → Playlist aus dem api_prompt
"spiel Daft Punk in der Küche"               → artist + expliziter Raum
"mach im Wohnzimmer und Bad das gleiche"     → gruppieren
"lauter"                                     → relativer Schritt, Raum implizit
"stell auf 30 Prozent"                       → absoluter Wert
"nimm das mit ins Bad"                       → transfer_queue
"was läuft gerade"                           → Status ohne Player-Angabe
"was hast du von Portishead"                 → Suche ohne Playback
"mach die Gruppe wieder auf"                 → alle_trennen
"spiel was zum Einschlafen"                  → Playlist-Fuzzy oder radio_mode
```

Jeder Fall gehört zweimal getestet: einmal vom Voice-Satelliten im Raum, einmal
aus der App ohne Area-Kontext.

## Status

Was verifiziert ist:

- `ruff check` und `ruff format` sind sauber
- 23 Unit-Tests für Ranking und Namens-Matching laufen grün
- HACS-Validierung und hassfest laufen in CI durch
- In CI wird das Paket mit installiertem Home Assistant importiert (aktuell
  2026.2.3, die Version die `pytest-homeassistant-custom-component` mitbringt) —
  die Importkette bis `homeassistant.helpers.llm` trägt also
- Die verwendeten Signaturen (`llm.API`, `llm.Tool`, `llm.APIInstance`,
  `ToolInput`, `LLMContext`) und die Feldnamen der `music_assistant.*`-Actions
  sind gegen den HA-Core-Stand (`dev`, August 2026) geprüft

Was nicht verifiziert ist: **alles, was eine laufende Instanz braucht.** Der
Config Flow, die Registrierung der API, die tatsächlichen Antwortformate von
`search`/`get_library`/`get_queue` und jede Tool-Runde sind ungetestet.

Die `llm`-Helper-Signaturen haben sich zwischen HA-Releases mehrfach geändert.
Getestet gegen: _(hier die HA-Version eintragen, sobald es lief)_.

## Abweichungen vom Plan

- **`manifest.json`**: `music_assistant` steht unter `after_dependencies`, nicht
  unter `dependencies`. So startet Barde auch, wenn MA (noch) fehlt, und meldet
  einen verständlichen Fehler, statt gar nicht zu laden.
- **Zusätzliche Module**: `matching.py` und `ranking.py` enthalten die reine
  Logik ohne HA-Importe (dadurch ohne laufendes `hass` testbar), `ma.py` kapselt
  die Service-Calls, `exceptions.py` die Fehlertypen.
- **`was_laeuft` mit `queue_anzeigen`**: `music_assistant.get_queue` liefert
  keine Liste kommender Titel, sondern nur Länge, aktuellen und nächsten
  Eintrag — entsprechend gibt das Tool `queue_länge` und `als_nächstes` zurück
  statt der geplanten „nächsten 5 Einträge".
- **Neue Option `volume_step`** (im Plan nur als Klammerbemerkung erwähnt).

## Entwicklung

```bash
pip install -r requirements_test.txt
```

```bash
pytest tests/ -v
```

```bash
ruff check . && ruff format --check .
```

Die Tests in `tests/` kommen ohne Home-Assistant-Installation aus: fehlt
`homeassistant`, stubbt `tests/conftest.py` das Paket, sodass die reinen
Logikmodule trotzdem importierbar sind.

### Brand-Images

Seit Home Assistant 2026.3 bringen Custom Integrations ihre Brand-Images selbst
mit — das `home-assistant/brands`-Repository nimmt dafür keine PRs mehr an. Die
acht Dateien liegen unter `custom_components/barde/brand/` (`icon`, `logo`,
jeweils zusätzlich als `dark_*` und `@2x`) und sind gezeichnet, nicht gemalt:

```bash
pip install pillow && python scripts/generate_brand_images.py
```

## Lizenz

MIT — siehe [LICENSE](LICENSE).
