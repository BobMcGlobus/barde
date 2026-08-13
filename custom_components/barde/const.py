"""Constants for the Barde integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "barde"
MA_DOMAIN: Final = "music_assistant"
MEDIA_PLAYER_DOMAIN: Final = "media_player"

# Config / options keys
CONF_DEFAULT_PLAYER: Final = "default_player"
CONF_EXPOSE_PLAYLISTS: Final = "expose_playlists"
CONF_EXPOSE_FAVORITES: Final = "expose_favorites"
CONF_CONTEXT_TTL: Final = "context_ttl"
CONF_PROVIDER_PREFERENCE: Final = "provider_preference"
CONF_RESPECT_EXPOSURE: Final = "respect_exposure"
CONF_VOLUME_STEP: Final = "volume_step"
CONF_MA_ENTRY_ID: Final = "ma_config_entry_id"

DEFAULT_EXPOSE_PLAYLISTS: Final = True
DEFAULT_EXPOSE_FAVORITES: Final = False
DEFAULT_CONTEXT_TTL: Final = 15  # minutes
DEFAULT_PROVIDER_PREFERENCE: Final = ["library", "spotify"]
DEFAULT_RESPECT_EXPOSURE: Final = True
DEFAULT_VOLUME_STEP: Final = 10  # percentage points
MA_ENTRY_AUTO: Final = "auto"

# Providers offered in the options flow (custom values are allowed).
KNOWN_PROVIDERS: Final = [
    "library",
    "spotify",
    "tidal",
    "ytmusic",
    "apple_music",
    "deezer",
    "qobuz",
    "soundcloud",
    "jellyfin",
    "plex",
    "filesystem_local",
    "radiobrowser",
    "tunein",
]

# Media types Barde offers to the model. Music Assistant additionally knows
# audiobook/podcast/folder — deliberately left out, they are not what voice
# commands in this house are about.
MEDIA_TYPES: Final = ["track", "album", "artist", "playlist", "radio"]

ENQUEUE_MODES: Final = ["play", "replace", "next", "add"]

# Service calls are awaited; a wedged MA server must not hang the voice turn.
SERVICE_TIMEOUT: Final = 15

DEFAULT_SEARCH_LIMIT: Final = 10
MAX_PROMPT_PLAYLISTS: Final = 30
MAX_PROMPT_FAVORITES: Final = 12
MAX_PROMPT_PLAYERS: Final = 12
LIBRARY_FETCH_LIMIT: Final = 100

# Assistant id used for the exposure check.
CONVERSATION_ASSISTANT: Final = "conversation"
