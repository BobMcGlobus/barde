"""End-to-end tool behaviour against a real hass.

The rule these tests protect: a tool must always answer. Home Assistant's chat
log only recovers from ``HomeAssistantError`` and ``vol.Invalid`` — anything
else aborts the whole Assist run with "Unexpected error during intent
recognition", which is what happened in the field.

Skipped when Home Assistant is not installed (see tests/conftest.py).
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("homeassistant")

from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from homeassistant.core import (  # noqa: E402
    Context,
    HomeAssistant,
    ServiceCall,
    SupportsResponse,
)
from homeassistant.helpers import entity_registry as er, llm  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.barde.const import (  # noqa: E402
    DOMAIN,
    MA_DOMAIN,
    MEDIA_TYPES,
)

PLAYER = "media_player.wohnzimmer"

EMPTY_RESULT: dict[str, list] = {
    "artists": [],
    "albums": [],
    "tracks": [],
    "playlists": [],
    "radio": [],
    "audiobooks": [],
    "podcasts": [],
}


def _result(**buckets: list[dict[str, Any]]) -> dict[str, list]:
    return {**EMPTY_RESULT, **buckets}


ALBUM_HIT = _result(
    albums=[
        {
            "name": "Hazbin Hotel",
            "uri": "library://album/12",
            "media_type": "album",
            "artists": [{"name": "Sam Haft"}],
        }
    ]
)


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let hass load custom_components/barde."""


@pytest.fixture
async def barde(hass: HomeAssistant) -> MockConfigEntry:
    """Set up a Barde entry with one Music Assistant player."""
    ma_entry = MockConfigEntry(domain=MA_DOMAIN, title="Music Assistant")
    ma_entry.add_to_hass(hass)
    ma_entry.mock_state(hass, ConfigEntryState.LOADED)

    er.async_get(hass).async_get_or_create(
        "media_player",
        MA_DOMAIN,
        "player-1",
        config_entry=ma_entry,
        suggested_object_id="wohnzimmer",
    )
    hass.states.async_set(PLAYER, "idle", {"friendly_name": "Wohnzimmer"})

    entry = MockConfigEntry(domain=DOMAIN, title="Barde")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _register_search(
    hass: HomeAssistant, responses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Register a fake music_assistant.search; returns the recorded calls."""
    calls: list[dict[str, Any]] = []

    async def handler(call: ServiceCall) -> dict[str, Any]:
        calls.append(dict(call.data))
        return responses.pop(0) if responses else EMPTY_RESULT

    hass.services.async_register(
        MA_DOMAIN, "search", handler, supports_response=SupportsResponse.ONLY
    )
    return calls


async def _call_tool(hass: HomeAssistant, name: str, **args: Any) -> dict[str, Any]:
    """Invoke a Barde tool the way a conversation agent would."""
    llm_context = llm.LLMContext(
        platform="test",
        context=Context(),
        language="de",
        assistant="conversation",
        device_id=None,
    )
    api = await llm.async_get_api(hass, DOMAIN, llm_context)
    tool = next(candidate for candidate in api.tools if candidate.name == name)
    return await tool.async_call(
        hass,
        llm.ToolInput(tool_name=name, tool_args=args),
        api.llm_context,
    )


async def test_api_exposes_all_tools(hass: HomeAssistant, barde) -> None:
    llm_context = llm.LLMContext(
        platform="test",
        context=Context(),
        language="de",
        assistant="conversation",
        device_id=None,
    )
    api = await llm.async_get_api(hass, DOMAIN, llm_context)
    assert {tool.name for tool in api.tools} == {
        "musik_abspielen",
        "musik_suchen",
        "podcast_folgen",
        "musik_steuern",
        "lautsprecher_gruppieren",
        "musik_uebernehmen",
        "einschlaftimer",
        "was_laeuft",
    }
    assert "Barde" in api.api_prompt or "Lautsprecher" in api.api_prompt


async def test_play_starts_the_ranked_album(hass: HomeAssistant, barde) -> None:
    _register_search(hass, [ALBUM_HIT])
    played = async_mock_service(hass, MA_DOMAIN, "play_media")

    result = await _call_tool(
        hass, "musik_abspielen", query="Hazbin Hotel", player="Wohnzimmer"
    )

    assert result["gespielt"] == "Hazbin Hotel"
    assert result["typ"] == "album"
    assert len(played) == 1
    assert played[0].data["media_id"] == "library://album/12"
    assert played[0].data["entity_id"] == PLAYER


async def test_play_falls_back_when_the_guessed_type_finds_nothing(
    hass: HomeAssistant, barde
) -> None:
    """The reported failure: 'Hazbin Hotel Songs' guessed as a track."""
    searches = _register_search(hass, [EMPTY_RESULT, EMPTY_RESULT, ALBUM_HIT])
    async_mock_service(hass, MA_DOMAIN, "play_media")

    result = await _call_tool(
        hass,
        "musik_abspielen",
        query="Hazbin Hotel Songs",
        media_type="track",
        player="Wohnzimmer",
    )

    assert result["gespielt"] == "Hazbin Hotel"
    # Dropping the media type widens the search to everything Barde knows,
    # audiobooks and podcasts included.
    assert [(call["name"], call.get("media_type")) for call in searches] == [
        ("Hazbin Hotel Songs", ["track"]),
        ("Hazbin Hotel Songs", MEDIA_TYPES),
        ("Hazbin Hotel", MEDIA_TYPES),
    ]


async def test_play_survives_a_foreign_exception_from_music_assistant(
    hass: HomeAssistant, barde
) -> None:
    """MusicAssistantError is not a HomeAssistantError — it must not escape."""

    async def handler(call: ServiceCall) -> dict[str, Any]:
        raise RuntimeError("MA exploded")

    hass.services.async_register(
        MA_DOMAIN, "search", handler, supports_response=SupportsResponse.ONLY
    )

    result = await _call_tool(
        hass, "musik_abspielen", query="Rumours", player="Wohnzimmer"
    )

    assert "fehler" in result
    assert "MA exploded" in result["fehler"]


async def test_play_reports_an_unknown_room_with_alternatives(
    hass: HomeAssistant, barde
) -> None:
    _register_search(hass, [ALBUM_HIT])

    result = await _call_tool(
        hass, "musik_abspielen", query="Rumours", player="Dachboden"
    )

    assert "fehler" in result
    assert result["verfügbar"] == ["Wohnzimmer"]


async def test_play_reports_when_nothing_is_found(hass: HomeAssistant, barde) -> None:
    _register_search(hass, [])

    result = await _call_tool(
        hass, "musik_abspielen", query="Gibtsnicht", player="Wohnzimmer"
    )

    assert "fehler" in result


async def test_search_returns_audiobooks(hass: HomeAssistant, barde) -> None:
    _register_search(
        hass,
        [
            _result(
                audiobooks=[
                    {
                        "name": "Der Hobbit",
                        "uri": "audiobookshelf://audiobook/7",
                        "media_type": "audiobook",
                    }
                ]
            )
        ],
    )

    result = await _call_tool(hass, "musik_suchen", query="Der Hobbit")

    assert result["treffer"][0]["typ"] == "audiobook"
    assert result["treffer"][0]["quelle"] == "audiobookshelf"


def _register_library(
    hass: HomeAssistant, items_by_type: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Register a fake music_assistant.get_library."""
    calls: list[dict[str, Any]] = []

    async def handler(call: ServiceCall) -> dict[str, Any]:
        calls.append(dict(call.data))
        return {"items": items_by_type.get(call.data["media_type"], [])}

    hass.services.async_register(
        MA_DOMAIN, "get_library", handler, supports_response=SupportsResponse.ONLY
    )
    return calls


async def test_podcast_is_found_in_the_library_despite_the_spoken_und(
    hass: HomeAssistant, barde
) -> None:
    """The reported failure: "Kack- und Sachgeschichten" vs "Kack & …"."""
    _register_search(hass, [])
    _register_library(
        hass,
        {
            "podcast": [
                {"name": "Kack & Sachgeschichten", "uri": "abs://podcast/1"},
                {"name": "Kack & Sachgeschichten Premium", "uri": "abs://podcast/2"},
                {"name": "KREWKAST", "uri": "abs://podcast/3"},
            ]
        },
    )
    played = async_mock_service(hass, MA_DOMAIN, "play_media")

    result = await _call_tool(
        hass,
        "musik_abspielen",
        query="Kack- und Sachgeschichten",
        media_type="podcast",
        player="Wohnzimmer",
    )

    assert result["gespielt"] == "Kack & Sachgeschichten"
    assert result["typ"] == "podcast"
    assert played[0].data["media_id"] == "abs://podcast/1"


async def test_untyped_request_falls_back_to_the_spoken_word_library(
    hass: HomeAssistant, barde
) -> None:
    _register_search(hass, [])
    _register_library(
        hass, {"podcast": [{"name": "KREWKAST", "uri": "abs://podcast/3"}]}
    )
    async_mock_service(hass, MA_DOMAIN, "play_media")

    result = await _call_tool(
        hass, "musik_abspielen", query="Krewkast", player="Wohnzimmer"
    )

    assert result["gespielt"] == "KREWKAST"


async def test_computed_name_alias_does_not_break_matching(
    hass: HomeAssistant, barde
) -> None:
    """entry.aliases may hold the COMPUTED_NAME sentinel instead of a string."""
    computed = getattr(er, "COMPUTED_NAME", None)
    if computed is None:
        pytest.skip("this core has no COMPUTED_NAME aliases")
    er.async_get(hass).async_update_entity(PLAYER, aliases={computed, "Büro"})
    _register_search(hass, [ALBUM_HIT])
    async_mock_service(hass, MA_DOMAIN, "play_media")

    result = await _call_tool(
        hass, "musik_abspielen", query="Hazbin Hotel", player="Büro"
    )

    assert result["gespielt"] == "Hazbin Hotel"


class _FakeEpisode:
    """What music_assistant_client returns, reduced to what Barde reads."""

    def __init__(self, name: str, position: int, released: str | None) -> None:
        self.name = name
        self.uri = f"abs://episode/{position}"
        self.position = position
        self.duration = 3600
        self.fully_played = False
        self.metadata = SimpleNamespace(
            release_date=date.fromisoformat(released) if released else None
        )


class _FakeMusic:
    def __init__(self, episodes: list[_FakeEpisode]) -> None:
        self._episodes = episodes
        self.asked_for: list[tuple[str, str]] = []

    async def get_item_by_uri(self, uri: str) -> SimpleNamespace:
        return SimpleNamespace(item_id="1", provider="library", uri=uri)

    async def get_podcast_episodes(self, item_id: str, provider: str) -> list:
        self.asked_for.append((item_id, provider))
        return self._episodes


def _register_client(hass: HomeAssistant, episodes: list[_FakeEpisode]) -> _FakeMusic:
    """Attach a fake Music Assistant client to the MA config entry."""
    music = _FakeMusic(episodes)
    ma_entry = hass.config_entries.async_entries(MA_DOMAIN)[0]
    ma_entry.runtime_data = SimpleNamespace(mass=SimpleNamespace(music=music))
    return music


PODCAST_LIBRARY = {
    "podcast": [
        {"name": "Kack & Sachgeschichten", "uri": "library://podcast/1"},
        {"name": "KREWKAST", "uri": "library://podcast/2"},
    ]
}

EPISODES = [
    _FakeEpisode("Folge 41: Ironman, Teil 1", 41, "2026-07-25"),
    _FakeEpisode("Folge 43: Kaffee", 43, "2026-08-08"),
    _FakeEpisode("Folge 42: Ironman, Teil 2", 42, "2026-08-01"),
]


async def test_episodes_are_listed_newest_first(hass: HomeAssistant, barde) -> None:
    _register_library(hass, PODCAST_LIBRARY)
    _register_client(hass, EPISODES)

    result = await _call_tool(
        hass, "podcast_folgen", podcast="Kack- und Sachgeschichten", anzahl=2
    )

    assert result["podcast"] == "Kack & Sachgeschichten"
    assert [folge["titel"] for folge in result["folgen"]] == [
        "Folge 43: Kaffee",
        "Folge 42: Ironman, Teil 2",
    ]
    assert result["anzahl"] == 3


async def test_newest_episode_is_played(hass: HomeAssistant, barde) -> None:
    _register_library(hass, PODCAST_LIBRARY)
    _register_client(hass, EPISODES)
    played = async_mock_service(hass, MA_DOMAIN, "play_media")

    result = await _call_tool(
        hass,
        "podcast_folgen",
        podcast="Kack und Sachgeschichten",
        abspielen=True,
        player="Wohnzimmer",
    )

    assert result["gespielt"] == "Folge 43: Kaffee"
    assert played[0].data["media_id"] == "abs://episode/43"


async def test_a_named_episode_is_found_and_played(hass: HomeAssistant, barde) -> None:
    _register_library(hass, PODCAST_LIBRARY)
    _register_client(hass, EPISODES)
    played = async_mock_service(hass, MA_DOMAIN, "play_media")

    result = await _call_tool(
        hass,
        "podcast_folgen",
        podcast="Kack & Sachgeschichten",
        suche="Ironman Teil 1",
        abspielen=True,
        player="Wohnzimmer",
    )

    assert result["gespielt"] == "Folge 41: Ironman, Teil 1"
    assert played[0].data["media_id"] == "abs://episode/41"


async def test_unknown_podcast_lists_what_exists(hass: HomeAssistant, barde) -> None:
    _register_library(hass, PODCAST_LIBRARY)
    _register_client(hass, EPISODES)

    result = await _call_tool(hass, "podcast_folgen", podcast="Tatort")

    assert "KREWKAST" in result["fehler"]


async def test_missing_client_is_reported_not_raised(
    hass: HomeAssistant, barde
) -> None:
    """The MA client is private API — its absence must stay survivable."""
    _register_library(hass, PODCAST_LIBRARY)

    result = await _call_tool(hass, "podcast_folgen", podcast="Kack & Sachgeschichten")

    assert "fehler" in result


async def test_control_steps_the_volume(hass: HomeAssistant, barde) -> None:
    hass.states.async_set(
        PLAYER, "playing", {"friendly_name": "Wohnzimmer", "volume_level": 0.4}
    )
    calls = async_mock_service(hass, "media_player", "volume_set")

    result = await _call_tool(hass, "musik_steuern", action="lauter")

    assert result["lautstärke"] == 50
    assert calls[0].data["volume_level"] == 0.5


async def test_sleep_timer_pauses_and_reports_the_end_time(
    hass: HomeAssistant, barde
) -> None:
    hass.states.async_set(
        PLAYER, "playing", {"friendly_name": "Wohnzimmer", "volume_level": 0.5}
    )
    paused = async_mock_service(hass, "media_player", "media_pause")

    result = await _call_tool(
        hass, "einschlaftimer", minuten=30, ausblenden=False, player="Wohnzimmer"
    )
    assert result["minuten"] == 30
    assert ":" in result["endet_um"]

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done()

    assert len(paused) == 1


async def test_sleep_timer_can_be_cancelled(hass: HomeAssistant, barde) -> None:
    hass.states.async_set(
        PLAYER, "playing", {"friendly_name": "Wohnzimmer", "volume_level": 0.5}
    )
    paused = async_mock_service(hass, "media_player", "media_pause")

    await _call_tool(
        hass, "einschlaftimer", minuten=30, ausblenden=False, player="Wohnzimmer"
    )
    cancelled = await _call_tool(
        hass, "einschlaftimer", aktion="abbrechen", player="Wohnzimmer"
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done()

    assert cancelled["abgebrochen"] is True
    assert paused == []


async def test_sleep_timer_status_and_was_laeuft_agree(
    hass: HomeAssistant, barde
) -> None:
    hass.states.async_set(
        PLAYER, "playing", {"friendly_name": "Wohnzimmer", "volume_level": 0.5}
    )
    await _call_tool(hass, "einschlaftimer", minuten=45, player="Wohnzimmer")

    status = await _call_tool(hass, "einschlaftimer", aktion="status")
    playing = await _call_tool(hass, "was_laeuft", player="Wohnzimmer")

    assert status["timer"] == [{"player": "Wohnzimmer", "verbleibend_min": 45}]
    assert playing["einschlaftimer_min"] == 45


async def test_sleep_timer_fades_down_and_restores_the_volume(
    hass: HomeAssistant, barde
) -> None:
    hass.states.async_set(
        PLAYER, "playing", {"friendly_name": "Wohnzimmer", "volume_level": 0.6}
    )
    volumes = async_mock_service(hass, "media_player", "volume_set")
    paused = async_mock_service(hass, "media_player", "media_pause")

    await _call_tool(hass, "einschlaftimer", minuten=10, player="Wohnzimmer")

    # Walk past the start of the fade and through every step.
    for offset in range(9, 22):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=offset))
        await hass.async_block_till_done()

    levels = [call.data["volume_level"] for call in volumes]
    fade, restore = levels[:-1], levels[-1]
    assert len(fade) > 2, "expected a gradual fade, not one jump"
    assert fade == sorted(fade, reverse=True), f"fade must fall: {fade}"
    assert fade[0] < 0.6
    assert len(paused) == 1
    assert restore == 0.6


async def test_status_without_a_player_lists_what_plays(
    hass: HomeAssistant, barde
) -> None:
    hass.states.async_set(
        PLAYER,
        "playing",
        {
            "friendly_name": "Wohnzimmer",
            "media_title": "Get Lucky",
            "media_artist": "Daft Punk",
        },
    )

    result = await _call_tool(hass, "was_laeuft")

    assert result["laeuft"] is True
    assert result["player"][0]["titel"] == "Get Lucky"


async def test_unknown_arguments_do_not_raise(hass: HomeAssistant, barde) -> None:
    _register_search(hass, [ALBUM_HIT])
    async_mock_service(hass, MA_DOMAIN, "play_media")

    result = await _call_tool(
        hass,
        "musik_abspielen",
        query="Hazbin Hotel",
        player="Wohnzimmer",
        erfunden="was das Modell sich ausgedacht hat",
        artist="",
    )

    assert result["gespielt"] == "Hazbin Hotel"
