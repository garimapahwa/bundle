# YouTube content brief agent

The finished agent from the workshop. Give it a topic, and it tells a creator what is winning on
YouTube for that topic and what to make next.

## What it does

1. Searches YouTube for the most-viewed videos on the topic with
   [thirdwatch/youtube-scraper](https://apify.com/thirdwatch/youtube-scraper).
2. Reads how the strongest videos open, from their transcripts, with
   [thirdwatch/youtube-transcripts-scraper](https://apify.com/thirdwatch/youtube-transcripts-scraper).
3. Writes a brief: the winning videos, each hook quoted word for word, the patterns behind the
   hooks, and three script ideas.

The agent decides which videos are worth reading and whether it needs to read more. That is the
ReAct loop: reason, act, observe, repeat.

## Input

| Field | Type | What it is |
| --- | --- | --- |
| `topic` | string, required | The topic or niche, written the way a viewer would search for it |
| `maxVideos` | integer, default 5 | How many top videos the agent reads the opening of |
| `modelName` | string, default `deepseek/deepseek-v4.1-flash` | Any [OpenRouter model slug](https://openrouter.ai/models) |
| `debug` | boolean, default false | Writes the full tool results to the log |

## Output

One dataset item per run:

```json
{
    "topic": "how to start investing",
    "summary": "What wins in this topic and what to do about it.",
    "winning_videos": [
        {
            "title": "...",
            "url": "https://www.youtube.com/watch?v=...",
            "channel": "...",
            "views": 1234567,
            "hook": "The opening line, quoted from the transcript.",
            "why_it_works": "Why this opening keeps people watching."
        }
    ],
    "hook_patterns": ["A pattern specific enough to copy."],
    "script_ideas": [
        {
            "title": "...",
            "hook": "The first sentences to say on camera.",
            "outline": ["Beat 1", "Beat 2", "Beat 3"]
        }
    ]
}
```

The same brief is saved as a readable report under the `brief.md` key in the run's key-value
store.

## Where to look in the code

- [`my_actor/tools.py`](./my_actor/tools.py) - the two tools. Each one runs a Store Actor and
  returns a trimmed result.
- [`my_actor/models.py`](./my_actor/models.py) - the shape of the tool results and of the brief.
- [`my_actor/main.py`](./my_actor/main.py) - the input, the LLM, the agent loop, and the output.
- [`my_actor/utils.py`](./my_actor/utils.py) - the log lines you see in the Log tab, and the
  Markdown report.

## Run it

```bash
apify push
```

Then start it in Apify Console. It runs only on the Apify platform, because the LLM goes through
the [Apify OpenRouter proxy](https://apify.com/apify/openrouter). Your account must be able to
run public Actors: the free plan can, the Creator plan cannot.

Pick a topic where people talk on camera. Music-only videos have no transcript to read. A run
takes one to two minutes.
