# Changelog

## 0.1.1 — unveröffentlicht

**Fix: Assist brach hart ab (`intent-failed`), sobald ein Tool lief.**
Der Conversation-Chat-Log fängt nur `HomeAssistantError` und `vol.Invalid` ab —
jede andere Exception reißt den ganzen Sprachlauf mit. Music Assistant lässt
umgekehrt in `handle_search` einen rohen `MusicAssistantError` durch. Beide
Enden sind jetzt dicht:

- `BardeTool.async_call` fängt zusätzlich jede weitere Exception, loggt sie mit
  Traceback und gibt sie als `{"fehler": …}` an das Modell zurück
- die Service-Fassade in `ma.py` macht dasselbe für `vol.Invalid` und
  Fremd-Exceptions aus Music Assistant

**Neu: Hörbücher und Podcasts** (z.B. über Audiobookshelf)

- `audiobook` und `podcast` als `media_type` in `musik_abspielen` und
  `musik_suchen`, und in der Standardsuche enthalten
- Ranking sortiert Gesprochenes unter Musik, damit „spiel Rumours" weiter das
  Album trifft

**Neu: Suchkaskade statt Fehlschlag.** Findet die Suche nichts, wird die
Anfrage schrittweise gelockert — erst der geratene `media_type`, dann der
`artist`, dann Füllwörter wie „Songs" („Hazbin Hotel Songs" → „Hazbin Hotel").
Jeder Schritt kostet eine Runde, läuft also nur bei einem leeren Ergebnis.

**Neu: Tool-Tests gegen echtes `hass`** (`tests/test_tools.py`) — sie halten
fest, dass kein Tool durchraist, egal was Music Assistant tut.

## 0.1.0 — unveröffentlicht

Erste Fassung, alle sechs Tools implementiert (Phasen 1–5 des Plans).

- LLM-API „Barde", registriert über `llm.async_register_api`
- Tools: `musik_abspielen`, `musik_suchen`, `musik_steuern`,
  `lautsprecher_gruppieren`, `musik_uebernehmen`, `was_laeuft`
- Player-Auflösung über Klartextnamen, Sprecher-Raum, laufende Wiedergabe,
  Standard-Player
- Eigenes Kandidaten-Ranking (exakter Treffer → Typ → Provider → Bibliothek)
- Dynamischer `api_prompt` mit Live-Lautsprecherzuständen und gecachten
  Playlist-Namen
- Config Flow (Single Instance) mit acht Optionen, deutsche Übersetzung

Noch nicht gegen eine laufende Instanz getestet — siehe README, Abschnitt
„Status".
