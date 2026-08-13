"""Picking the right podcast episode."""

from custom_components.barde.episodes import (
    Episode,
    matching,
    newest_first,
    to_episodes,
)

FEED = [
    {
        "name": "Folge 42: Ironman, Teil 2",
        "uri": "abs://episode/42",
        "position": 42,
        "released": "2026-08-01",
        "duration": 5400,
    },
    {
        "name": "Folge 43: Kaffee",
        "uri": "abs://episode/43",
        "position": 43,
        "released": "2026-08-08",
        "duration": 3600,
        "fully_played": True,
    },
    {
        "name": "Folge 41: Ironman, Teil 1",
        "uri": "abs://episode/41",
        "position": 41,
        "released": "2026-07-25",
    },
]


def test_to_episodes_reads_the_feed() -> None:
    episodes = to_episodes(FEED)
    assert len(episodes) == 3
    assert episodes[0].position == 42
    assert episodes[1].fully_played is True


def test_to_episodes_skips_entries_without_uri() -> None:
    assert to_episodes([{"name": "kaputt"}]) == []


def test_newest_first_sorts_by_release_date() -> None:
    names = [episode.name for episode in newest_first(to_episodes(FEED))]
    assert names[0] == "Folge 43: Kaffee"
    assert names[-1] == "Folge 41: Ironman, Teil 1"


def test_newest_first_falls_back_to_position() -> None:
    episodes = [
        Episode(name="alt", uri="a", position=1),
        Episode(name="neu", uri="b", position=9),
    ]
    assert newest_first(episodes)[0].name == "neu"


def test_matching_finds_a_keyword_in_a_long_title() -> None:
    hits = matching(to_episodes(FEED), "Ironman")
    assert [hit.position for hit in hits] == [42, 41]


def test_matching_orders_the_better_hit_first() -> None:
    hits = matching(to_episodes(FEED), "Ironman Teil 1")
    assert hits[0].position == 41


def test_matching_without_a_query_is_newest_first() -> None:
    assert matching(to_episodes(FEED), "")[0].name == "Folge 43: Kaffee"


def test_matching_returns_nothing_for_an_unrelated_query() -> None:
    assert matching(to_episodes(FEED), "Weihnachtsspecial") == []


def test_episode_payload_stays_small() -> None:
    payload = to_episodes(FEED)[0].as_dict()
    assert payload == {
        "titel": "Folge 42: Ironman, Teil 2",
        "uri": "abs://episode/42",
        "datum": "2026-08-01",
        "dauer_min": 90,
    }
