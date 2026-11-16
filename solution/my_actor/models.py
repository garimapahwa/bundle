"""Pydantic models for the YouTube content brief agent.

Two kinds of models live here:
- What the tools hand back to the LLM (`Video`, `VideoOpening`).
- What the agent must return at the end (`ContentBrief`). This is the product the user pays for.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Video(BaseModel):
    """One search result returned by the `search_youtube_videos` tool."""

    title: str
    url: str
    channel: str
    views: int
    duration: str | None = None
    published: str | None = None


class VideoOpening(BaseModel):
    """The spoken opening of one video, returned by the `get_video_openings` tool."""

    url: str
    title: str | None = None
    channel: str | None = None
    views: int | None = None
    language: str | None = None
    opening: str = Field(description='The first words spoken in the video, taken from its transcript.')


class WinningVideo(BaseModel):
    """A top-performing video and the reason its opening works."""

    title: str
    url: str
    channel: str
    views: int
    hook: str = Field(description='The opening line, quoted word for word from the transcript.')
    why_it_works: str = Field(description='One or two sentences on why this opening keeps people watching.')


class ScriptIdea(BaseModel):
    """A video the creator could make next."""

    title: str = Field(description='A working title for the video.')
    hook: str = Field(description='The first one or two sentences to say on camera, built on one of the hook patterns.')
    outline: list[str] = Field(description='Three to five specific beats for the rest of the video.')


class ContentBrief(BaseModel):
    """The structured brief the agent returns. One brief is one dataset item."""

    topic: str
    summary: str = Field(description='Three or four sentences: what the winning videos have in common, and the gap.')
    winning_videos: list[WinningVideo] = Field(description='One entry per opening read, most-viewed first.')
    hook_patterns: list[str] = Field(description='Three or four patterns, each naming the move and the channel using it.')
    script_ideas: list[ScriptIdea] = Field(description='Exactly three ideas, each on an angle the winners missed.')
