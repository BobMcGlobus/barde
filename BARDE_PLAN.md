# BARDE — Music Assistant LLM Tools für Home Assistant

**Ziel:** Eine HACS-Custom-Integration, die dem Assist-Conversation-Agent eine kleine,
handgeschnittene Tool-API für Music Assistant anbietet — Songs/Alben/Playlists gezielt
auf bestimmten Speakern starten, Räume gruppieren, Lautstärke und Transport steuern,
Queue übernehmen.

**Zielinstanz:** Casa de Jonas (192.168.2.107)
**Status:** Kickoff / noch nicht implementiert
**Analog zu:** Herold (HACS-Integration mit LLM Tools native)

---

## 1. Warum nicht MCP

Das Music Assistant **FastMCP Server** Plugin (MA 2.9+) exponiert `/mcp/v1` als
streamable HTTP mit Bearer-Token. Die HA-Integration `mcp` kann als Client aber nur
SSE + OAuth (Stand HA 2026.8.1, Feature Request home-assistant/discussions#1383 offen).
Ein Anschluss bräuchte also einen mcp-proxy-Container als Transport-Übersetzer.

Selbst mit Bridge wäre es die schlechtere Lösung:

- ~20–30 generische Tool-Definitionen in **jedem** Assist-Turn → Latenz + Tokenkosten
  in einer Pipeline, die bereits Voxtral (STT) + Cartesia (TTS) durchläuft
- Das Modell muss zwischen HA-`media_player`-Entities (Assist-API) und MA-internen
  Player-IDs (MCP) unterscheiden → Fehlerquelle bei „spiel das im Wohnzimmer"
- 29 Permission-Toggles als zweiter Konfigurationsort
- Plugin ist laut MA-Docs explizit experimentell

**Entscheidung:** Direkter Zugriff über die `music_assistant.*` Service-Actions der
bereits konfigurierten MA-Integration. Keine zusätzliche Verbindung, kein Token,
kein Container.

### Verworfene Alternative: eigener MusicAssistantClient

`music_assistant_client` ist zur Laufzeit verfügbar (Dependency der MA-Integration).
Zwei Wege, beide abgelehnt:

- Eigene Websocket-Verbindung aufbauen → seit MA 2.9 Authentication nötig, also
  wieder Token-Verwaltung im Config Flow
- `entry.runtime_data.mass` der MA-Integration abgreifen → private API, bricht
  potenziell bei jedem HA-Release

Service-Calls sind die dokumentierte, stabile Schnittstelle. Falls sich später
herausstellt, dass etwas fehlt (z.B. Player-Gruppen-Metadaten), ist der Umstieg auf
den Client punktuell nachrüstbar.

---

## 2. Architektur

```
Assist Pipeline (Casa de Jonas)
  └─ Conversation Agent (LLM)
       ├─ LLM API "Assist"              ← Lichter, Klima, Sensoren (unverändert)
       └─ LLM API "Barde"           ← NEU, diese Integration
            └─ 6 Tools
                 └─ hass.services.async_call(blocking=True, return_response=True)
                      └─ music_assistant.* / media_player.*
                           └─ MA Server (Add-on / Domovoi)
```

Registrierung über `llm.async_register_api()`. HA erlaubt seit 2025.x die Auswahl
mehrerer LLM-APIs pro Agent — „Assist" und „Barde" laufen also parallel.

### Dateistruktur

```
custom_components/barde/
├── __init__.py           # async_setup_entry, llm.async_register_api
├── manifest.json         # domain: barde, dependencies: [music_assistant, conversation]
├── config_flow.py        # Single-Instance, Optionen s.u.
├── const.py
├── api.py                # BardeAPI(llm.API), api_prompt-Aufbau
├── tools/
│   ├── __init__.py       # TOOLS-Liste
│   ├── play.py           # musik_abspielen
│   ├── search.py         # musik_suchen
│   ├── control.py        # musik_steuern
│   ├── group.py          # lautsprecher_gruppieren
│   ├── transfer.py       # musik_uebernehmen
│   └── status.py         # was_laeuft
├── resolver.py           # Player-Auflösung, Kandidaten-Ranking
├── context.py            # Library-Cache (Playlists, Favoriten) für den api_prompt
├── strings.json
└── translations/de.json
```

### Config-Flow-Optionen

| Option | Typ | Default | Zweck |
|---|---|---|---|
| `default_player` | entity selector (MA media_player) | — | Fallback, wenn kein Raum ableitbar |
| `expose_playlists` | bool | true | Playlist-Namen in den api_prompt aufnehmen |
| `expose_favorites` | bool | false | Lieblingskünstler in den api_prompt |
| `context_ttl` | int (min) | 15 | Cache-Dauer für Library-Kontext |
| `provider_preference` | multi-select | library, spotify | Reihenfolge beim Ranking |
| `respect_exposure` | bool | true | Nur zu Assist exponierte Player ansteuern |
| `ma_config_entry_id` | string | auto | Bei mehreren MA-Instanzen explizit wählen |

---

## 3. Tools

Bewusst **sechs** Tools. Jeder zusätzliche Tool-Eintrag kostet Kontext in jedem Turn;
Transport-Kommandos werden deshalb in einem Tool mit `action`-Enum gebündelt statt
in acht Einzeltools.

Alle Rückgaben bleiben klein (3–8 Felder), damit der LLM-Turn nicht aufbläht.

### 3.1 `musik_abspielen`

Der Kern. Macht **search → rank → play**, nicht direkt `play_media` mit einem Namen.
Grund: `play_media` mit Klartext-Namen resolved intern selbst und nimmt den ersten
Treffer. Eigenes Ranking erlaubt Typ- und Provider-Präferenz und eine ehrliche
Rückmeldung, was tatsächlich läuft.

```python
parameters = vol.Schema(
    {
        vol.Required("query"): str,  # "Rumours", "Kochmusik", "Daft Punk"
        vol.Optional("media_type"): vol.In(
            ["track", "album", "artist", "playlist", "radio"]
        ),
        vol.Optional("artist"): str,  # Disambiguierung: Album X *von* Y
        vol.Optional("player"): str,  # Raum- oder Player-Name, Klartext
        vol.Optional("enqueue", default="replace"): vol.In(
            ["play", "replace", "next", "add"]
        ),
        vol.Optional("radio_mode", default=False): bool,
        vol.Optional("shuffle", default=False): bool,
    }
)
```

Ablauf:

1. Player auflösen (→ `resolver.py`)
2. `music_assistant.search` mit `name=query`, `media_type=[...]`, optional `artist`,
   `limit=10`
3. Kandidaten ranken:
   - Exakter (case-insensitive) Namenstreffer schlägt Teiltreffer
   - Angeforderter `media_type` schlägt andere Typen
   - Ohne `media_type`: playlist > album > artist > track (Sprachbefehle meinen
     selten einen Einzeltrack, wenn ein gleichnamiges Album existiert)
   - `provider_preference` als Tiebreak
   - Library-Items vor Streaming-Items
4. `music_assistant.play_media` mit `media_id=<uri>`, `media_type`, `enqueue`,
   `radio_mode`
5. Bei `shuffle=true`: `media_player.shuffle_set`

Rückgabe:
```json
{"gespielt": "Rumours", "typ": "album", "künstler": "Fleetwood Mac",
 "player": "Wohnzimmer", "quelle": "library", "alternativen": 2}
```

`alternativen` gibt dem Modell die Chance, von sich aus „ich hab X gespielt, es gäbe
auch noch…" zu sagen, ohne einen zweiten Tool-Call zu brauchen.

### 3.2 `musik_suchen`

Sucht ohne abzuspielen. Für „was hast du von Daft Punk" und für Fälle, in denen der
LLM erst rückfragen soll.

```python
vol.Schema(
    {
        vol.Required("query"): str,
        vol.Optional("media_type"): vol.In([...]),
        vol.Optional("artist"): str,
        vol.Optional("limit", default=5): vol.All(int, vol.Range(min=1, max=15)),
        vol.Optional("library_only", default=False): bool,
    }
)
```

Gibt pro Treffer **nur** `{name, artist, typ, uri, quelle}` zurück — keine Artwork-URLs,
keine Metadaten-Blobs. Die `uri` kann `musik_abspielen` als `query` entgegennehmen
(URI-Erkennung per Präfix-Check, dann Search überspringen).

### 3.3 `musik_steuern`

Transport und Lautstärke in einem Tool.

```python
vol.Schema(
    {
        vol.Required("action"): vol.In(
            [
                "pause",
                "weiter",
                "stop",
                "naechster",
                "vorheriger",
                "lautstaerke",
                "lauter",
                "leiser",
                "stumm",
                "laut",
                "shuffle_an",
                "shuffle_aus",
                "wiederholen_an",
                "wiederholen_aus",
                "queue_leeren",
            ]
        ),
        vol.Optional("player"): str,
        vol.Optional("wert"): vol.All(
            int, vol.Range(min=0, max=100)
        ),  # nur bei lautstaerke
    }
)
```

Mapping auf `media_player.media_pause` / `media_play` / `media_stop` /
`media_next_track` / `media_previous_track` / `volume_set` / `volume_up` /
`volume_down` / `volume_mute` / `shuffle_set` / `repeat_set` / `clear_playlist`.

`lauter`/`leiser` als relative Schritte (±10 Prozentpunkte, Option), weil Assist-Nutzer
fast nie absolute Werte nennen.

### 3.4 `lautsprecher_gruppieren`

Das, was der eingebaute Intent gar nicht kann.

```python
vol.Schema(
    {
        vol.Required("aktion"): vol.In(["gruppieren", "trennen", "alle_trennen"]),
        vol.Optional("hauptplayer"): str,  # Leader; default = Raum des Sprechers
        vol.Optional("player"): [str],  # zu joinende Räume/Player
    }
)
```

→ `media_player.join` (`group_members`) bzw. `media_player.unjoin`.

`alle_trennen` iteriert über alle MA-Player mit nicht-leerem `group_members`-Attribut.

Rückgabe: `{"gruppe": ["Wohnzimmer","Küche","Bad"], "leader": "Wohnzimmer"}`

### 3.5 `musik_uebernehmen`

„Nimm das mit in die Küche." → `music_assistant.transfer_queue`.

```python
vol.Schema(
    {
        vol.Required("nach"): str,
        vol.Optional("von"): str,  # default: Raum des Sprechers
        vol.Optional("auto_play", default=True): bool,
    }
)
```

### 3.6 `was_laeuft`

```python
vol.Schema(
    {vol.Optional("player"): str, vol.Optional("queue_anzeigen", default=False): bool}
)
```

Liest primär den Entity-State (kein Service-Call nötig): `media_title`,
`media_artist`, `media_album_name`, `volume_level`, `state`, `group_members`.
Nur bei `queue_anzeigen=true` zusätzlich `music_assistant.get_queue`, dann maximal
die nächsten 5 Einträge.

Ohne `player`: Zustand **aller** spielenden MA-Player, damit „läuft irgendwo noch
Musik?" in einem Turn beantwortbar ist.

---

## 4. Player-Auflösung (`resolver.py`)

Reihenfolge, erster Treffer gewinnt:

1. **Explizit genannt** — Fuzzy-Match des `player`-Arguments gegen Friendly Names und
   Area-Namen aller MA-`media_player`-Entities. Normalisierung: lowercase, Umlaute
   entfalten, Wortstämme („Wohnzimmerlautsprecher" ↔ „Wohnzimmer").
2. **Raum des Sprechers** — `llm_context.device_id` → Device Registry → `area_id` →
   Entity Registry: MA-`media_player` in derselben Area. Bei mehreren: der mit
   `state != 'off'`, sonst der erste alphabetisch.
3. **Aktuell spielender Player**, falls genau einer spielt (für „mach lauter" ohne
   Raumangabe von einem Handy aus).
4. **`default_player`** aus den Optionen.
5. Fehler mit hilfreichem Text: `{"fehler": "Kein Player gefunden", "verfügbar": [...]}`
   — der LLM kann dann sinnvoll rückfragen statt zu halluzinieren.

Bei `respect_exposure=true` werden nicht zu Assist exponierte Player aus allen
Kandidatenlisten gefiltert (`homeassistant.components.homeassistant.exposed_entities.async_should_expose`).

Konsequent `entity_id` verwenden, nie `device_id` in den Service-Calls.

---

## 5. api_prompt (`api.py` + `context.py`)

Der `api_prompt` wird pro `async_get_api_instance()` gebaut und ist der Hebel für
Trefferquote. Inhalt:

```
Du bist der Barde des Hauses und steuerst Music Assistant.

Verfügbare Lautsprecher (Raum → Zustand):
  Wohnzimmer → spielt "Get Lucky" (Daft Punk)
  Küche → aus
  Bad → aus, gruppiert mit Wohnzimmer

Wenn kein Raum genannt wird, nimm den Raum, aus dem gesprochen wurde.
Frage nicht nach, wenn ein plausibler Treffer existiert — spiele ihn und sage,
was du gewählt hast.

Bekannte Playlists: Kochmusik, Einschlafen, Werkstatt, Sonntagmorgen, …
```

Der Rollenrahmen im ersten Satz ist nicht nur Kosmetik — eine klare Rollenzuweisung
verbessert bei mehreren parallel aktiven LLM-APIs die Trefferquote der Tool-Auswahl.

Der Playlist-Block kommt aus `music_assistant.get_library(media_type=playlist)`,
gecacht nach `context_ttl`. Das ist der Unterschied zwischen „leg die Kochmusik auf"
→ funktioniert vs. → Suche nach dem Wort „Kochmusik" in allen Streaming-Providern.

Player-Zustände werden nicht gecacht (Entity-States sind ohnehin im Speicher).

**Budget:** Der komplette Prompt sollte unter ~400 Tokens bleiben. Bei mehr als 30
Playlists nur die zuletzt gespielten bzw. favorisierten aufnehmen.

---

## 6. Implementierungsphasen

**Phase 1 — Skelett**
`manifest.json`, Config Flow (Single Instance, nur `default_player`),
`llm.async_register_api` mit einem Dummy-Tool. Ziel: Die API taucht in der
Agent-Konfiguration auf und ein Tool-Call kommt durch.

**Phase 2 — Kern**
`musik_abspielen` + `musik_suchen` + `resolver.py`. Ab hier real nutzbar.

**Phase 3 — Rest**
`musik_steuern`, `lautsprecher_gruppieren`, `musik_uebernehmen`, `was_laeuft`.

**Phase 4 — Kontext**
`context.py`, dynamischer `api_prompt`, restliche Config-Optionen, deutsche
Übersetzungen.

**Phase 5 — Härtung**
Fehlerpfade (MA offline, Player unavailable, leeres Suchergebnis), Timeouts auf
Service-Calls, Logging, HACS-Metadaten, README.

---

## 7. Risiken / offene Punkte

| Punkt | Anmerkung |
|---|---|
| `llm.Tool` / `llm.API`-Signaturen | Haben sich zwischen HA-Releases mehrfach geändert. Vor Phase 1 gegen `homeassistant/helpers/llm.py` der laufenden Version prüfen und die getestete Version im README festhalten. |
| `return_response=True` | `search`, `get_library`, `get_queue` sind `SupportsResponse.ONLY` — der Parameter ist Pflicht, nicht optional. |
| `config_entry_id` | Die MA-Actions brauchen ihn. Auto-Discovery über `hass.config_entries.async_entries("music_assistant")`; bei mehr als einem Eintrag Option erzwingen. |
| Umlaute im Tool-Namen | Tool-*Namen* ASCII halten (`musik_abspielen` ok), aber Enum-*Werte* dürfen deutsch sein. Manche Modelle stolpern über Umlaute in Schema-Keys — deshalb `lautstaerke` statt `lautstärke`. |
| Deutsche vs. englische Tool-Namen | Deutsche Namen + deutsche Descriptions verbessern bei deutschsprachigen Prompts messbar die Auswahl. Falls der Agent auf ein Modell mit schwächerem Deutsch wechselt, englische Namen mit deutschen Descriptions als Fallback testen. |
| Latenz | Ziel: `musik_abspielen` unter 800 ms von Tool-Call bis Playback-Start. `search` mit `limit=10` gegen viele Provider kann länger dauern — ggf. `library_only` als First Pass, Streaming erst als Fallback. |
| Doppelte Tools | Wenn „Assist" parallel aktiv ist, kennt das Modell auch `HassMediaSearchAndPlay`. Im `api_prompt` explizit anweisen, für Musik die Barde-Tools zu nutzen. Alternativ MA-Player aus der Assist-Exposure nehmen — dann fällt aber auch die native Lautstärkesteuerung weg. Erst Variante 1 testen. |

---

## 8. Testfälle (deutsch, gegen echte Instanz)

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

Jeder Fall zweimal: einmal vom Voice-Satelliten im Raum, einmal aus der App ohne
Area-Kontext.
