"""Candidate ranking — which hit actually gets played."""

from custom_components.barde.ranking import (
    Candidate,
    flatten,
    is_uri,
    provider_of,
    rank,
)

SEARCH_RESPONSE = {
    "albums": [
        {
            "name": "Rumours",
            "uri": "library://album/1",
            "media_type": "album",
            "artists": [{"name": "Fleetwood Mac"}],
        }
    ],
    "tracks": [
        {
            "name": "Rumours",
            "uri": "spotify://track/9",
            "media_type": "track",
            "artists": [{"name": "Tribute Band"}],
        }
    ],
    "playlists": [],
    "artists": [],
    "radio": [],
}


def _candidate(
    name: str,
    media_type: str,
    provider: str = "library",
    artist: str | None = None,
) -> Candidate:
    return Candidate(
        name=name,
        uri=f"{provider}://{media_type}/{name}",
        media_type=media_type,
        artist=artist,
        provider=provider,
    )


def test_is_uri_recognises_ma_uris() -> None:
    assert is_uri("library://album/1")
    assert is_uri("spotify://playlist/aabbcc")
    assert not is_uri("Rumours")
    assert not is_uri("Sgt. Pepper's Lonely Hearts Club Band")


def test_provider_of() -> None:
    assert provider_of("spotify://track/9") == "spotify"
    assert provider_of("Rumours") == ""


def test_flatten_reads_name_uri_and_artist() -> None:
    candidates = flatten(SEARCH_RESPONSE)
    assert len(candidates) == 2
    album = next(c for c in candidates if c.media_type == "album")
    assert album.name == "Rumours"
    assert album.artist == "Fleetwood Mac"
    assert album.provider == "library"


def test_flatten_appends_version_to_name() -> None:
    candidates = flatten(
        {"tracks": [{"name": "Zombie", "uri": "x://1", "version": "Live"}]}
    )
    assert candidates[0].name == "Zombie (Live)"


def test_flatten_skips_items_without_uri() -> None:
    assert flatten({"tracks": [{"name": "kaputt"}]}) == []


def test_album_beats_track_of_the_same_name() -> None:
    ranked = rank(flatten(SEARCH_RESPONSE), "Rumours")
    assert ranked[0].media_type == "album"


def test_requested_media_type_wins() -> None:
    ranked = rank(flatten(SEARCH_RESPONSE), "Rumours", media_type="track")
    assert ranked[0].media_type == "track"


def test_exact_name_beats_type_priority() -> None:
    candidates = [
        _candidate("Kochmusik für lange Abende", "playlist"),
        _candidate("Kochmusik", "track"),
    ]
    assert rank(candidates, "Kochmusik")[0].media_type == "track"


def test_provider_preference_breaks_ties() -> None:
    candidates = [
        _candidate("Discovery", "album", provider="tidal"),
        _candidate("Discovery", "album", provider="spotify"),
    ]
    ranked = rank(candidates, "Discovery", provider_preference=["library", "spotify"])
    assert ranked[0].provider == "spotify"


def test_library_wins_when_no_preference_applies() -> None:
    candidates = [
        _candidate("Discovery", "album", provider="tidal"),
        _candidate("Discovery", "album", provider="library"),
    ]
    ranked = rank(candidates, "Discovery", provider_preference=[])
    assert ranked[0].provider == "library"


def test_artist_hint_disambiguates() -> None:
    candidates = [
        _candidate("Rumours", "album", artist="Cover Collective"),
        _candidate("Rumours", "album", artist="Fleetwood Mac"),
    ]
    ranked = rank(candidates, "Rumours", artist="Fleetwood Mac")
    assert ranked[0].artist == "Fleetwood Mac"


def test_ranking_is_stable_for_equal_candidates() -> None:
    first = Candidate("Gleich", "library://album/1", "album")
    second = Candidate("Gleich", "library://album/2", "album")
    assert rank([first, second], "Gleich") == [first, second]


def test_empty_response_ranks_to_nothing() -> None:
    assert rank(flatten(None), "irgendwas") == []
