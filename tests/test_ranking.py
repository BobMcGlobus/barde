"""Candidate ranking — which hit actually gets played."""

from custom_components.barde.ranking import (
    Candidate,
    filter_by_name,
    flatten,
    from_library,
    is_uri,
    provider_of,
    rank,
    search_attempts,
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


def test_flatten_reads_audiobooks_and_podcasts() -> None:
    candidates = flatten(
        {
            "audiobooks": [
                {"name": "Der Hobbit", "uri": "audiobookshelf://audiobook/7"}
            ],
            "podcasts": [{"name": "Lage der Nation", "uri": "abs://podcast/3"}],
        }
    )
    assert {c.media_type for c in candidates} == {"audiobook", "podcast"}
    assert candidates[0].provider == "audiobookshelf"


def test_music_outranks_spoken_word_without_a_requested_type() -> None:
    candidates = [
        _candidate("Der Hobbit", "audiobook", provider="audiobookshelf"),
        _candidate("Der Hobbit", "album"),
    ]
    assert rank(candidates, "Der Hobbit")[0].media_type == "album"


def test_requested_audiobook_wins_over_album() -> None:
    candidates = [
        _candidate("Der Hobbit", "album"),
        _candidate("Der Hobbit", "audiobook", provider="audiobookshelf"),
    ]
    ranked = rank(candidates, "Der Hobbit", media_type="audiobook")
    assert ranked[0].media_type == "audiobook"


def test_search_attempts_only_the_request_when_nothing_to_loosen() -> None:
    assert search_attempts("Rumours", None, None) == [("Rumours", None, None)]


def test_search_attempts_drop_media_type_then_artist() -> None:
    assert search_attempts("Rumours", "track", "Fleetwood Mac") == [
        ("Rumours", "track", "Fleetwood Mac"),
        ("Rumours", None, "Fleetwood Mac"),
        ("Rumours", None, None),
    ]


def test_search_attempts_strip_filler_words_last() -> None:
    # The reported failure: "Hazbin Hotel Songs" guessed as a track.
    assert search_attempts("Hazbin Hotel Songs", "track", None) == [
        ("Hazbin Hotel Songs", "track", None),
        ("Hazbin Hotel Songs", None, None),
        ("Hazbin Hotel", None, None),
    ]


def test_search_attempts_add_the_ampersand_spelling() -> None:
    assert search_attempts("Kack- und Sachgeschichten", None, None) == [
        ("Kack- und Sachgeschichten", None, None),
        ("Kack & Sachgeschichten", None, None),
    ]


def test_search_attempts_are_deduplicated() -> None:
    attempts = search_attempts("Rumours", None, None)
    assert attempts == [("Rumours", None, None)]


def test_from_library_reads_items() -> None:
    candidates = from_library(
        {
            "items": [
                {"name": "Kack & Sachgeschichten", "uri": "abs://podcast/1"},
                {"name": "KREWKAST", "uri": "abs://podcast/2"},
            ]
        },
        "podcast",
    )
    assert [candidate.name for candidate in candidates] == [
        "Kack & Sachgeschichten",
        "KREWKAST",
    ]
    assert candidates[0].media_type == "podcast"


def test_filter_by_name_keeps_only_plausible_hits() -> None:
    candidates = [
        _candidate("Kack & Sachgeschichten", "podcast"),
        _candidate("Kack & Sachgeschichten Premium", "podcast"),
        _candidate("Nerd & Kultur", "podcast"),
    ]
    hits = filter_by_name(candidates, "Kack- und Sachgeschichten")
    assert [hit.name for hit in hits] == [
        "Kack & Sachgeschichten",
        "Kack & Sachgeschichten Premium",
    ]
