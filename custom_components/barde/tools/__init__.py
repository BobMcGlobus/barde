"""The Barde tools.

Deliberately few: every tool definition costs context in *every* Assist turn,
so the transport commands live in one tool with an ``action`` enum instead of
eight separate ones. ``podcast_folgen`` is the one addition that earns its
keep — single episodes are simply not reachable through the other tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .control import ControlTool
from .episodes import EpisodesTool
from .group import GroupTool
from .play import PlayTool
from .search import SearchTool
from .sleeptimer import SleepTimerTool
from .status import StatusTool
from .transfer import TransferTool

if TYPE_CHECKING:
    from homeassistant.helpers import llm

    from ..api import BardeRuntime

TOOLS = (
    PlayTool,
    SearchTool,
    EpisodesTool,
    ControlTool,
    GroupTool,
    TransferTool,
    SleepTimerTool,
    StatusTool,
)


def build_tools(runtime: BardeRuntime) -> list[llm.Tool]:
    """Instantiate the tool set for one conversation."""
    return [tool(runtime) for tool in TOOLS]


__all__ = [
    "TOOLS",
    "ControlTool",
    "EpisodesTool",
    "GroupTool",
    "PlayTool",
    "SearchTool",
    "SleepTimerTool",
    "StatusTool",
    "TransferTool",
    "build_tools",
]
