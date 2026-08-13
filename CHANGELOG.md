# Changelog

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
