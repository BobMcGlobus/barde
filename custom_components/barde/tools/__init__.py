"""The six Barde tools.

Six on purpose: every tool definition costs context in *every* Assist turn, so
the transport commands live in one tool with an ``action`` enum instead of
eight separate ones.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .control import ControlTool
from .group import GroupTool
from .play import PlayTool
from .search import SearchTool
from .status import StatusTool
from .transfer import TransferTool

if TYPE_CHECKING:
    from homeassistant.helpers import llm

    from ..api import BardeRuntime

TOOLS = (
    PlayTool,
    SearchTool,
    ControlTool,
    GroupTool,
    TransferTool,
    StatusTool,
)


def build_tools(runtime: BardeRuntime) -> list[llm.Tool]:
    """Instantiate the tool set for one conversation."""
    return [tool(runtime) for tool in TOOLS]


__all__ = [
    "TOOLS",
    "ControlTool",
    "GroupTool",
    "PlayTool",
    "SearchTool",
    "StatusTool",
    "TransferTool",
    "build_tools",
]
