"""Room and player name matching."""

from custom_components.barde.matching import (
    MATCH_THRESHOLD,
    best_match,
    core_form,
    match_score,
    normalize,
    strip_query_filler,
)


def test_normalize_unfolds_umlauts_and_punctuation() -> None:
    assert normalize("Küche (Sonos)") == "kueche sonos"
    assert normalize("Straße") == "strasse"


def test_core_form_drops_device_words() -> None:
    assert core_form("Wohnzimmer Lautsprecher") == "wohnzimmer"
    # A player literally named after the device stays matchable.
    assert core_form("Lautsprecher") == "lautsprecher"


def test_identical_names_score_full() -> None:
    assert match_score("Küche", "Kueche") == 1.0


def test_compound_name_matches_room() -> None:
    assert match_score("Wohnzimmer", "Wohnzimmerlautsprecher") >= MATCH_THRESHOLD


def test_spaced_device_suffix_matches_room() -> None:
    assert match_score("Wohnzimmer", "Wohnzimmer Lautsprecher") >= MATCH_THRESHOLD


def test_unrelated_names_do_not_match() -> None:
    assert match_score("Garage", "Wohnzimmer") < MATCH_THRESHOLD


def test_stt_typo_still_matches() -> None:
    assert match_score("Wohnzimma", "Wohnzimmer") >= MATCH_THRESHOLD


def test_best_match_picks_the_closer_alias() -> None:
    candidates = {
        "media_player.wohnzimmer": ["Wohnzimmer Lautsprecher", "Wohnzimmer"],
        "media_player.bad": ["Badezimmer", "Bad"],
    }
    match = best_match("bad", candidates)
    assert match is not None
    assert match[0] == "media_player.bad"


def test_best_match_returns_none_below_threshold() -> None:
    candidates = {"media_player.bad": ["Bad", "Badezimmer"]}
    assert best_match("Dachboden", candidates) is None


def test_strip_query_filler_removes_request_words() -> None:
    assert strip_query_filler("Hazbin Hotel Songs") == "Hazbin Hotel"
    assert strip_query_filler("Musik von Daft Punk") == "Daft Punk"


def test_strip_query_filler_keeps_original_spelling() -> None:
    assert strip_query_filler("Kochmusik") == "Kochmusik"


def test_strip_query_filler_can_empty_the_query() -> None:
    assert strip_query_filler("irgendwas Musik") == ""


def test_best_match_prefers_exact_over_substring() -> None:
    candidates = {
        "media_player.bad": ["Bad"],
        "media_player.badezimmer_gross": ["Badezimmer groß"],
    }
    match = best_match("Bad", candidates)
    assert match is not None
    assert match[0] == "media_player.bad"
