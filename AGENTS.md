# Guidance for AI coding tools

This repo is a forkable starter for a hands-on Apify workshop: build an AI agent that uses
existing Apify Store Actors as tools, deploy it as an Actor, and monetize it. The full workshop
lives in [`README.md`](./README.md). It is both the workshop structure and your reference for
building agents here.

The user's Actor lives in [`python-langgraph/`](./python-langgraph): the Python LangGraph AI
agent template, wired to the Apify OpenRouter proxy. Build the user's agent there. Do not
scaffold a second Actor.

[`solution/`](./solution) is the finished workshop agent, kept as a fallback. Do not copy from
it or edit it unless the user asks. When the user asks to build the workshop agent, write it in
`python-langgraph/` from the prompt and the tool Actor table in `README.md`.

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
   [Monetize](https://docs.apify.com/platform/actors/publishing/monetize).

## Building an AI agent (step 2, the payoff)

The pattern: **the agent loop runs inside the Actor, Apify Store Actors are the tools it calls,
and the dataset is the output.**

- Keep the loop on LangChain's `create_agent`, as in the template, with a `system_prompt`, a
  Pydantic `response_format`, and a recursion limit.
- Call Actors as tools with `Actor.apify_client.actor('<username>/<name>').call(run_input=...)`,
  then read `run['defaultDatasetId']` with `Actor.apify_client.dataset(...).list_items()`.
  Read the tool Actor's input schema and a sample of its output before you write the tool.
- Tools return only the fields the model needs, trimmed. Never return a whole dataset item or a
  full transcript.
- If a tool Actor fails, return the error as text so the agent can react. Do not raise.
- Tool Actors must run under limited permissions, because an Actor with limited permissions can
  only call other Actors that also use them.
- Route the LLM through the [Apify OpenRouter proxy](https://apify.com/apify/openrouter): an
  OpenAI-compatible endpoint at `https://openrouter.apify.actor/api/v1`, with `APIFY_TOKEN` as
  the API key and any [OpenRouter model slug](https://openrouter.ai/models) as the model. The
  agent needs only `APIFY_TOKEN` at runtime - no provider API key. The proxy works only for
  Actors running on the Apify platform, so test with `apify push` and a run in Apify Console.
- Alternative route, only if the user asks: their own provider key. See "Use your own LLM key
  instead" in step 2 of the README.
- Push one dataset item per finished result. The synthetic `apify-default-dataset-item` event
  charges for it, so do not add a charge call for the same result.

## Writing style (for any docs edits)

- "Actor" is always capitalized when it means an Apify Actor. "task" and "schedule" stay
  lowercase.
- Use "Apify Store", "Apify Console", "Apify Proxy" (no "the"), but "the Apify platform".
- Headings in sentence case, never title case.
- No em dashes. Use a spaced hyphen ` - ` instead.
- US English, Oxford comma.
