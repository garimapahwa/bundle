"""Helpers: readable logging of the agent loop, and the Markdown version of the brief."""

from __future__ import annotations

import json

from apify import Actor
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from .models import ContentBrief


def log_new_messages(messages: list[BaseMessage], already_logged: int) -> int:
    """Log every message the agent loop added since the last call, and return the new count.

    This is what you watch in the Log tab: the model deciding to call a tool (reason and act),
    then the tool result coming back (observe), until the model has enough to answer.
    """
    for message in messages[already_logged:]:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                Actor.log.info('AGENT -> %s(%s)', tool_call['name'], json.dumps(tool_call['args'], ensure_ascii=False))
            if not message.tool_calls and message.content:
                Actor.log.info('AGENT: %s', str(message.content)[:300])
        elif isinstance(message, ToolMessage):
            Actor.log.info('TOOL  <- %s returned %s', message.name, _describe(message.content))
            Actor.log.debug('Full tool result: %s', message.content)
    return len(messages)


def _describe(content: str | list) -> str:
    """Summarize a tool result in a few words for the log."""
    try:
        data = json.loads(content) if isinstance(content, str) else content
    except ValueError:
        return str(content)[:200]
    if isinstance(data, list):
        return f'{len(data)} videos'
    if isinstance(data, dict) and 'openings' in data:
        return f'{len(data["openings"])} openings ({len(data.get("no_transcript", []))} videos had no transcript)'
    return str(content)[:200]


def brief_to_markdown(brief: ContentBrief) -> str:
    """Render the brief as a Markdown report a creator can read straight away."""
    lines = [f'# Content brief: {brief.topic}', '', brief.summary, '', '## What is winning', '']
    for video in brief.winning_videos:
        lines += [
            f'### [{video.title}]({video.url})',
            f'{video.channel} - {video.views:,} views',
            '',
            f'> {video.hook}',
            '',
            video.why_it_works,
            '',
        ]
    lines += ['## Hook patterns', '']
    lines += [f'- {pattern}' for pattern in brief.hook_patterns]
    lines += ['', '## Script ideas', '']
    for number, idea in enumerate(brief.script_ideas, start=1):
        lines += [f'### {number}. {idea.title}', '', f'**Hook:** {idea.hook}', '']
        lines += [f'- {beat}' for beat in idea.outline]
        lines.append('')
    return '\n'.join(lines)
