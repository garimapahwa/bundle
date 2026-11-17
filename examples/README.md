# Real output

What the finished agent in [`solution/`](../solution) returned for three topics. Nothing here was edited:
each brief is the `brief.md` from the run's key-value store, and each JSON file is the run's one dataset item.

| Input topic | Run time | Report | Dataset item |
| --- | --- | --- | --- |
| `how to build AI agents` | 65 s | [brief](./how-to-build-ai-agents.md) | [JSON](./how-to-build-ai-agents.json) |
| `how to start investing` | 76 s | [brief](./how-to-start-investing.md) | [JSON](./how-to-start-investing.json) |
| `how to learn coding` | 105 s | [brief](./how-to-learn-coding.md) | [JSON](./how-to-learn-coding.json) |

All three ran on `anthropic/claude-haiku-5.5` through the Apify OpenRouter proxy. Each made three tool calls:
one search, one read of the openings, and the structured brief.
