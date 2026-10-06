# Guidance for AI coding tools

This repo is a forkable starter for a hands-on Apify Actor workshop. The full workshop lives in
[`README.md`](./README.md): intro, prerequisites, example use cases, five steps, and a
resources list. `README.md` is both the workshop structure and your reference for building
agents here.

The user's Actor lives in [`python-langgraph/`](./python-langgraph): the Python LangGraph AI
agent template, wired to the Apify OpenRouter proxy. Build the user's agent there. Do not
scaffold a second Actor.

## Defer to the Apify Actor Development skill

For scaffolding, building, debugging, or deploying Actors, defer to the **Apify Actor
Development Agent Skill** (`apify-actor-development`). Do not duplicate its instructions here.

Install it by copying `skills/apify-actor-development` from
[apify/agent-skills](https://github.com/apify/agent-skills) into the tool's skills folder (for
Claude Code, `.claude/skills/`).

## Actor lifecycle (the workflow this repo teaches)

1. **Set up** - `apify login` once, then work in `python-langgraph/`.
   [CLI reference](https://docs.apify.com/cli/docs/reference),
   [Python SDK](https://docs.apify.com/sdk/python).
2. **Build, deploy, and run** - `apify push`, then run it in Apify Console and check the **Log**
   and **Dataset** tabs. There are no local runs: the OpenRouter proxy works only on the Apify
   platform. [Running Actors](https://docs.apify.com/platform/actors/running).
3. **Call it** - over the [API](https://docs.apify.com/api/v2) or the
   [Apify MCP server](https://docs.apify.com/platform/integrations/mcp).
4. **Monetize** - in the **Publishing** tab, set up pay per event, then publish to Apify Store.
   PPE Actors without "Pay per event + usage", with limited permissions, and without Standby are
   auto-eligible for agentic payment (x402 / Skyfire) once the developer completes identity
   verification. [Monetize](https://docs.apify.com/platform/actors/publishing/monetize).

## Actor anatomy

- [`.actor/actor.json`](https://docs.apify.com/platform/actors/development/actor-definition/actor-json) -
  metadata and config.
- [`.actor/input_schema.json`](https://docs.apify.com/platform/actors/development/actor-definition/input-schema) -
  the JSON input shape.
- `my_actor/` - Actor code (`main.py` runs the agent loop, `tools.py` holds the tools).
- [`Dockerfile`](https://docs.apify.com/platform/actors/development/actor-definition/dockerfile) -
  build and run definition.
- Output goes to a [dataset](https://docs.apify.com/platform/storage/dataset).
- Keep secrets in env vars or [`apify secrets`](https://docs.apify.com/platform/actors/development/programming-interface/environment-variables),
  never in the repo.

## Building an AI agent (step 2, the payoff)

The pattern: **the agent loop runs inside the Actor, Apify Actors are the tools it calls, and
the dataset is the output.**

- Drive the loop with [LangGraph](https://langchain-ai.github.io/langgraph/) (hand-wired) or the
  [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) (framework).
- Call Actors as tools with the
  [Apify client for Python](https://docs.apify.com/api/client/python/); find tools in
  [Apify Store](https://apify.com/store).
- Route the LLM through the [Apify OpenRouter proxy](https://apify.com/apify/openrouter): an
  OpenAI-compatible endpoint at `https://openrouter.apify.actor/api/v1`, with `APIFY_TOKEN` as
  the API key and any [OpenRouter model slug](https://openrouter.ai/models) as the model. The
  agent needs only `APIFY_TOKEN` at runtime - no provider API key. The proxy works only for
  Actors running on the Apify platform, so test with `apify push` and a run in Apify Console.
- Alternative route, only if the user asks: their own provider key (for example
  `OPENAI_API_KEY`), as an env var locally and an
  [`apify secrets`](https://docs.apify.com/cli/docs/vars#define-secrets) secret once deployed.
  This route also runs locally with `apify run`. See "Use your own LLM key instead" in step 2 of
  the README.

## Writing style (for any docs edits)

- "Actor" is always capitalized when it means an Apify Actor. "task" and "schedule" stay
  lowercase.
- Use "Apify Store", "Apify Console", "Apify Proxy" (no "the"), but "the Apify platform".
- Headings in sentence case, never title case.
- No em dashes. Use a spaced hyphen ` - ` instead.
- US English, Oxford comma.
