"""Tools the agent can call. Each tool runs an existing Actor from Apify Store.

The pattern is the same for every tool:
1. Build the input the Store Actor expects.
2. Run it with the Apify client (the run's `APIFY_TOKEN` is already there, no setup needed).
3. Read its dataset and hand the LLM only the fields it needs.

Step 3 is the one that matters. A full transcript can be 100,000 characters. The agent only
needs the opening of each video, so that is all the tool returns.
"""

from __future__ import annotations

from typing import Literal

from apify import Actor
from langchain_core.tools import tool

from .models import Video, VideoOpening

# The Store Actors this agent uses as tools.
YOUTUBE_SEARCH_ACTOR = 'thirdwatch/youtube-scraper'
YOUTUBE_TRANSCRIPT_ACTOR = 'thirdwatch/youtube-transcripts-scraper'

# Roughly the first minute of speech. Enough to see the hook, small enough to keep LLM cost low.
OPENING_CHARS = 1200


async def run_store_actor(actor_id: str, run_input: dict, timeout_secs: int = 180) -> list[dict]:
    """Run a Store Actor, wait for it to finish, and return the items from its dataset."""
    run = await Actor.apify_client.actor(actor_id).call(run_input=run_input, timeout_secs=timeout_secs)
    if not run:
        msg = f'Failed to start the Actor {actor_id}'
        raise RuntimeError(msg)
    if run.get('status') != 'SUCCEEDED':
        msg = f'The Actor {actor_id} finished with status {run.get("status")}'
        raise RuntimeError(msg)
    return (await Actor.apify_client.dataset(run['defaultDatasetId']).list_items()).items


@tool
async def search_youtube_videos(
    query: str,
    max_results: int = 10,
    sort_by: Literal['viewCount', 'relevance', 'date'] = 'viewCount',
) -> list[dict] | str:
    """Search YouTube and return matching videos with their view counts.

    Args:
        query: What to search for, written the way a viewer would type it.
        max_results: How many videos to return (1 to 20).
        sort_by: 'viewCount' for the most-viewed videos, 'relevance' for the closest matches,
            'date' for the newest uploads.

    Returns:
        A list of videos, each with title, url, channel, views, duration, and published.
    """
    await Actor.set_status_message(f'Searching YouTube for "{query}"')
    run_input = {
        'queries': [query],
        'maxResults': max(1, min(max_results, 20)),
        'searchType': 'videos',
        'sort': sort_by,
    }
    try:
        items = await run_store_actor(YOUTUBE_SEARCH_ACTOR, run_input)
    except Exception as exc:  # noqa: BLE001 - report the failure to the agent so it can react
        Actor.log.warning('YouTube search failed: %s', exc)
        return f'The search failed: {exc}. Try once more with a simpler query.'

    videos = [
        Video(
            title=item.get('title') or '',
            url=item['url'],
            channel=item.get('channelName') or '',
            views=item.get('viewCount') or 0,
            duration=item.get('durationText'),
            published=item.get('publishedTimeText'),
        )
        for item in items
        # Shorts have no real opening to study, so leave them out.
        if item.get('url') and not item.get('isShort')
    ]
    return [video.model_dump() for video in videos]


@tool
async def get_video_openings(video_urls: list[str]) -> dict | str:
    """Read how YouTube videos open: the first words spoken, taken from each video's transcript.

    Call it once, with all the videos worth studying, not with every search result. Videos
    without captions (music-only videos, for example) cannot be read and come back under
    `no_transcript`.

    Args:
        video_urls: YouTube watch URLs to read (at most 8 per call).

    Returns:
        `openings`: one entry per readable video with url, title, channel, views, language,
            and opening.
        `no_transcript`: the URLs that had no transcript.
    """
    urls = list(dict.fromkeys(video_urls))[:8]
    await Actor.set_status_message(f'Reading the openings of {len(urls)} videos')
    run_input = {
        'videoUrls': urls,
        'maxResults': len(urls),
        'includeTimestamps': False,
        'includeMetadata': True,
    }
    try:
        items = await run_store_actor(YOUTUBE_TRANSCRIPT_ACTOR, run_input, timeout_secs=300)
    except Exception as exc:  # noqa: BLE001 - report the failure to the agent so it can react
        Actor.log.warning('Transcript fetch failed: %s', exc)
        return f'Reading transcripts failed: {exc}. Try once more with fewer videos.'

    openings = [
        VideoOpening(
            url=item['video_url'],
            title=item.get('title'),
            channel=item.get('channel_name'),
            views=item.get('view_count'),
            language=item.get('language_code'),
            opening=item['transcript_text'][:OPENING_CHARS],
        )
        for item in items
        if item.get('video_url') and item.get('transcript_text')
    ]
    readable = {opening.url for opening in openings}
    return {
        'openings': [opening.model_dump() for opening in openings],
        'no_transcript': [url for url in urls if url not in readable],
    }
