"""YouTube content brief agent.

Input: a topic. Output: a brief on what is winning on YouTube for that topic, built from the
most-viewed videos and the way they open, with script ideas to make next.

The shape is the one from the workshop:
- The agent loop runs inside this Actor.
- Its tools are existing Actors from Apify Store (see `tools.py`).
- The result goes to the dataset.
"""

from __future__ import annotations

import logging
import os

from apify import Actor
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from .models import ContentBrief
from .tools import get_video_openings, search_youtube_videos
from .utils import brief_to_markdown, log_new_messages

SYSTEM_PROMPT = """You are a YouTube content strategist. A creator gives you a topic and you tell \
them what is winning on YouTube for it and what to make next.

Work in this order:
1. Call search_youtube_videos once to find the most-viewed videos for the topic.
2. Pick the {max_videos} strongest videos that are really about the topic, in the same language \
as the topic, where someone talks on camera. Skip music-only videos, compilations, ads, and \
off-topic results. Call get_video_openings once with all {max_videos} URLs.
3. If {max_videos} openings came back, go straight to the brief. Only if fewer came back, call \
get_video_openings one more time with other videos from the same search results.
4. Write the brief.

Rules for the brief:
- Use only what the tools returned. Never invent a video, a view count, or a quote.
- winning_videos has one entry for every opening you read, up to {max_videos}, most-viewed first. \
Leave out an opening that is in a different language from the topic.
- Every hook is the first one or two sentences of that video's opening, quoted word for word.
- Each hook pattern names the move and the channel that uses it, so a creator can copy it. \
"Opens with a result that sounds impossible, then promises to explain it (channel name)" is \
useful. "Starts with a question" is not.
- Give exactly 3 script ideas. Each one applies one of the hook patterns to an angle the winning \
videos have not covered, with the hook written out in the creator's voice.
- The summary says what the winners have in common and where the gap is. No generic advice."""


async def main() -> None:
    """Run the agent once for the topic in the Actor input and store the brief."""
    async with Actor:
        # 1. Input: one topic, written the way a creator would say it
        actor_input = await Actor.get_input() or {}

        topic = (actor_input.get('topic') or '').strip()
        if not topic:
            msg = 'Missing "topic" attribute in input!'
            raise ValueError(msg)

        max_videos = int(actor_input.get('maxVideos') or 5)
        model_name = actor_input.get('modelName') or 'anthropic/claude-haiku-5.5'
        if actor_input.get('debug', False):
            Actor.log.setLevel(logging.DEBUG)

        # 2. The LLM: routed through the Apify OpenRouter proxy, so no provider API key is needed.
        # The proxy only accepts the token of the run itself, so the tokens are billed to whoever
        # runs the Actor.
        llm = ChatOpenAI(
            model=model_name,
            base_url='https://openrouter.apify.actor/api/v1',
            api_key=os.environ['APIFY_TOKEN'],
            temperature=0.3,
            # A brief is about 2,000 tokens. The cap and the timeout stop a runaway answer early.
            max_tokens=4000,
            timeout=120,
        )

        # 3. The agent: an LLM in a loop, with Store Actors as its tools and a fixed output shape
        # see https://docs.langchain.com/oss/python/langchain/agents
        tools = [search_youtube_videos, get_video_openings]
        graph = create_agent(
            llm,
            tools,
            system_prompt=SYSTEM_PROMPT.format(max_videos=max_videos),
            response_format=ContentBrief,
        )

        # 4. Run the loop. The recursion limit caps how many steps it may take, which caps the cost.
        inputs: dict = {'messages': [('user', f'Topic: {topic}')]}
        brief: ContentBrief | None = None
        logged = 0
        try:
            async for state in graph.astream(inputs, {'recursion_limit': 14}, stream_mode='values'):
                logged = log_new_messages(state['messages'], logged)
                if state.get('structured_response') is not None:
                    brief = state['structured_response']
                    break
        except Exception as exc:  # noqa: BLE001 - a failed run must say why, and must not push a result
            Actor.log.exception('The agent stopped before it produced a brief')
            reason = f'The agent could not finish the brief ({type(exc).__name__}). Run it again, or try another model.'
            await Actor.fail(status_message=reason)
            return

        if not brief:
            Actor.log.error('Failed to get a brief from the agent!')
            await Actor.fail(status_message='Failed to get a brief from the agent!')
            return

        # 5. Output: a readable report in the key-value store, and the structured brief in the dataset
        store = await Actor.open_key_value_store()
        await store.set_value('brief.md', brief_to_markdown(brief), content_type='text/markdown')
        Actor.log.info('Saved the "brief.md" report into the key-value store!')

        # Charged automatically by the synthetic `apify-default-dataset-item` event (one item per brief)
        await Actor.push_data(brief.model_dump())
        Actor.log.info('Pushed the brief into the dataset!')
        await Actor.set_status_message(f'Brief ready: {len(brief.winning_videos)} videos studied')
