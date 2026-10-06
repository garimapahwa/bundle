# Build, deploy, and monetize AI agents

Build a real AI agent, ship it to the Apify platform, and turn it into something people (and
other agents) can pay to use - all from this one forked repo.

## How it works

In about 40 minutes you will build an AI agent and take it through the full Apify Actor
lifecycle: build, deploy, and monetize.

This is a **live, build-along workshop**. We pick one example use case and build it together,
end to end, while explaining each step:

- We start from the AI agent template in [`python-langgraph/`](./python-langgraph), turn it into
  our example agent, then deploy and monetize it live.
- You follow along in your own fork, working inside `python-langgraph/`.
- Each step ends with a "Your project" nudge, so by the end you can swap the example for your
  own idea and take it straight into your own project.

The example is chosen on the day. It is just a vehicle for the lifecycle, so anything you build
follows the same shape.

An **[Actor](https://docs.apify.com/platform/actors)** is a serverless program on
[the Apify platform](https://docs.apify.com/platform): it takes JSON input, does a task, and
writes results to a [dataset](https://docs.apify.com/platform/storage/dataset). That simple
shape is all you need to build, deploy, monetize, and eventually run a full AI agent.

> **New to Apify?** Skim [What is Apify](https://docs.apify.com/platform) and
> [Actors](https://docs.apify.com/platform/actors) before you start. A full link list lives in
> [Resources](#resources) at the bottom.

## Scope

What we cover, in order. Each step builds on the last.

1. [Step 1: Setup and your first Actor](#step-1-setup-and-your-first-actor) (~10 min)
2. [Step 2: Build your agent](#step-2-build-your-agent) (~20 min)
3. [Step 3: Call it from anywhere](#step-3-call-it-from-anywhere) (~3 min)
4. [Step 4: Monetize and publish](#step-4-monetize-and-publish) (~7 min)
5. [Step 5: Use Apify in your own projects](#step-5-use-apify-in-your-own-projects)

## Prerequisites

- An **[Apify account](https://console.apify.com/sign-up)**. You can sign up for free, and the
  free tier's monthly usage credits are plenty for this workshop.
- **[Python 3.10+](https://www.python.org/downloads/)**.
- An **AI coding tool with Agent Skills support** - [Claude Code](https://docs.claude.com/en/docs/claude-code),
  [Cursor](https://cursor.com/), or similar. You will install an Apify skill into it.

The agent calls its LLM through the [Apify OpenRouter proxy](https://apify.com/apify/openrouter),
so you need no LLM provider key. Prefer your own key? See
[Use your own LLM key instead](#use-your-own-llm-key-instead) in step 2.

---

## Step 1: Setup and your first Actor

Install your tools, log in, then deploy and run your first Actor.

**Time:** ~10 minutes

### 1. Check your Python version

```bash
python --version  # should be 3.10 or higher
```

If it is missing or too old, install it before continuing.

### 2. Install the Apify CLI

The [Apify CLI](https://docs.apify.com/cli/) is how you create, run, and deploy Actors from
your terminal. The installation script builds a standalone executable, so you don't need
Node.js. See the [installation guide](https://docs.apify.com/cli/docs/installation) for other
install methods.

On macOS or Linux:

```bash
curl -fsSL https://apify.com/install-cli.sh | bash
apify --version
```

On Windows (PowerShell):

```powershell
irm https://apify.com/install-cli.ps1 | iex
apify --version
```

You should see a version number printed.

### 3. Log in to Apify

```bash
apify login --method console
```

This opens Apify Console in your browser. Approve the login there, and the CLI is linked to your
Apify account. It is the only time you log in.

To check that it worked, run:

```bash
apify info
```

You should see the details of your Apify account.

### 4. Install the Apify Actor Development skill

This skill teaches your AI coding tool how to scaffold, build, and deploy Actors. It powers the
vibe-coding in step 2.

Clone the [apify/agent-skills](https://github.com/apify/agent-skills) repo and copy the skill
into your AI coding tool's skills folder. For Claude Code, that is `.claude/skills/` in this
repo:

```bash
git clone --depth 1 https://github.com/apify/agent-skills.git /tmp/agent-skills
mkdir -p .claude/skills
cp -r /tmp/agent-skills/skills/apify-actor-development .claude/skills/
```

For other tools, copy the same `skills/apify-actor-development` folder into the skills folder
your tool's docs point to. You can browse all available skills in the
[apify/agent-skills](https://github.com/apify/agent-skills) repo, and read what this one does
in its [SKILL.md](https://github.com/apify/agent-skills/blob/main/skills/apify-actor-development/SKILL.md).

### 5. Tour the structure

Your Actor is the [`python-langgraph/`](./python-langgraph) folder: the Python LangGraph AI
agent template, already wired to the Apify OpenRouter proxy. Move into it and work there for
the rest of the workshop:

```bash
cd python-langgraph
```

Find these files (all defined in the
[Actor definition](https://docs.apify.com/platform/actors/development/actor-definition) docs):

- [`.actor/actor.json`](https://docs.apify.com/platform/actors/development/actor-definition/actor-json) -
  your Actor's metadata and configuration.
- [`.actor/input_schema.json`](https://docs.apify.com/platform/actors/development/actor-definition/input-schema) -
  the shape of the JSON input your Actor accepts.
- `my_actor/` - your Actor's code. `main.py` runs the agent loop and `tools.py` holds the tools
  it can call.
- [`Dockerfile`](https://docs.apify.com/platform/actors/development/actor-definition/dockerfile) -
  how your Actor is built and run on the Apify platform.

### 6. Deploy and run it

The OpenRouter proxy works only for Actors running on the Apify platform, so every run in this
workshop happens there. Push the Actor:

```bash
apify push
```

This builds your Actor on the Apify platform and uploads your code. When it finishes, the CLI
prints a link to your Actor in Apify Console. Open it, keep the prefilled input, and click
**Start**. Watch the agent reason and call tools in the **Log** tab, then check the result in
the **Dataset** tab. The [Running Actors](https://docs.apify.com/platform/actors/running) docs
walk through Apify Console.

> **Note:** The Actor model is just this: JSON input goes in, the Actor runs a task, and
> results go out to a dataset. Everything else in this workshop builds on that shape.

**Your project:** look at `.actor/input_schema.json` and decide what one input your own agent
would take.

**Resources**

- [Apify CLI installation](https://docs.apify.com/cli/docs/installation) and
  [command reference](https://docs.apify.com/cli/docs/reference)
- [Actor definition](https://docs.apify.com/platform/actors/development/actor-definition):
  [actor.json](https://docs.apify.com/platform/actors/development/actor-definition/actor-json),
  [input schema](https://docs.apify.com/platform/actors/development/actor-definition/input-schema),
  [Dockerfile](https://docs.apify.com/platform/actors/development/actor-definition/dockerfile)
- [Running Actors](https://docs.apify.com/platform/actors/running) and
  [Storage](https://docs.apify.com/platform/storage)
- [apify/agent-skills](https://github.com/apify/agent-skills)

Continue to [Step 2: Build your agent](#step-2-build-your-agent).

---

## Step 2: Build your agent

This is the heart of the workshop. Turn the template into your own AI agent: a reasoning loop
that calls tools and writes its results to a dataset.

**Time:** ~20 minutes

### 1. Understand the pattern

An AI agent on Apify is just an Actor with three parts:

- **The agent loop runs inside the Actor.** The Actor's code drives an LLM that reasons, decides
  what to do next, and repeats until the task is done.
- **Apify Actors are the tools.** When the agent needs real data or an action, it calls another
  Actor from [Apify Store](https://apify.com/store) (a scraper, a search Actor, your own Actor)
  with the [Apify client for Python](https://docs.apify.com/api/client/python/). The template's
  `tools.py` does exactly this with an Instagram scraper. Every run on the platform gets
  `APIFY_TOKEN` automatically, so the client needs no extra setup.
- **The dataset is the output.** Whatever the agent produces gets written to the dataset, just
  like in step 1.

The template hand-wires the loop with **[LangGraph](https://langchain-ai.github.io/langgraph/)**.
You can also let a framework run it for you with the
**[OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)**
(`pip install openai-agents`, `from agents import Agent, Runner`). Use whichever you prefer.

Either way, the LLM client points at the
[Apify OpenRouter proxy](https://docs.apify.com/sdk/python/docs/guides/ai-agents#apify-openrouter-proxy),
an OpenAI-compatible endpoint at `https://openrouter.apify.actor/api/v1`. It uses your
`APIFY_TOKEN` as the API key and any [OpenRouter model slug](https://openrouter.ai/models) as the
model, as in `my_actor/main.py`:

```python
llm = ChatOpenAI(
    model='openai/gpt-4o-mini',
    base_url='https://openrouter.apify.actor/api/v1',
    api_key=os.environ['APIFY_TOKEN'],
)
```

### 2. Pick your agent

Pick the example we build together in this workshop, or bring your own. Keep it small enough to
finish in this step: one clear input, one tool Actor, one useful output.

### 3. Vibe-code it with your AI tool

You installed the `apify-actor-development` skill in step 1, so let your AI coding tool build it
for you. Describe the agent and let it implement the code in `python-langgraph/`. For example:

```
Turn this Actor into an AI agent that takes a {your input} as input, uses the
{an Apify Store Actor} Actor as a tool to fetch data, runs an agent loop with
{LangGraph or the OpenAI Agents SDK}, and writes the {your result} to the dataset.
Keep using the Apify OpenRouter proxy (https://openrouter.apify.actor/api/v1) as the LLM,
authenticated with APIFY_TOKEN, so no provider API key is needed. Follow the Apify
Actor Development skill.
```

Let the tool update your input schema, add dependencies, and write the loop. Review what it
generates.

### 4. Push and run it

Same loop as in step 1: run `apify push`, start the Actor in Apify Console with your input,
watch the agent loop in the **Log** tab, and check the result in the **Dataset** tab. Repeat for
every change.

This is the payoff - a working agent built from a single prompt.

**Your project:** swap the three parts for your idea - the input, the tool Actor it calls, and
the output it writes. The pattern stays the same.

### Use your own LLM key instead

<details>
<summary>Call OpenAI directly with your own <code>OPENAI_API_KEY</code>, and run locally</summary>

With your own key, the agent no longer needs the proxy, so it also runs on your machine with
`apify run` (this needs Python 3.10+). The tokens bill your provider account, not the user's.

1. Add the key to your shell environment. Never commit keys to the repo.

   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

2. In `my_actor/main.py`, use the provider's client with its defaults, which read
   `OPENAI_API_KEY` from the environment, and pass an OpenAI model name such as `gpt-4o-mini`:

   ```python
   llm = ChatOpenAI(model=model_name)
   ```

   In the vibe-coding prompt, replace the OpenRouter sentence with: "Use OpenAI with the
   `OPENAI_API_KEY` environment variable, so it works both locally and once deployed."

3. Run it locally. `apify run` injects your token from `apify login` as `APIFY_TOKEN`, so tool
   Actors still work. Output lands in `storage/datasets/default/`. See the
   [Storage docs](https://docs.apify.com/platform/storage).

   ```bash
   apify run
   ```

4. Give the deployed Actor its own copy of the key. Store it as a secret and reference it from
   `.actor/actor.json`, then `apify push` as usual:

   ```bash
   apify secrets add openaiApiKey "sk-..."
   ```

   ```json
   "environmentVariables": {
       "OPENAI_API_KEY": "@openaiApiKey"
   }
   ```

   Secrets live on the Apify platform and are injected at runtime, encrypted at rest and
   redacted from logs. Without this, the deployed run fails at the first model call. See
   [secret environment variables](https://docs.apify.com/platform/actors/development/programming-interface/environment-variables).

5. When you monetize in step 4, your event prices need to cover your token costs.

</details>

**Resources**

- [LangGraph docs](https://langchain-ai.github.io/langgraph/) and
  [OpenAI Agents SDK docs](https://openai.github.io/openai-agents-python/)
- [Apify OpenRouter proxy](https://apify.com/apify/openrouter) and
  [OpenRouter models](https://openrouter.ai/models)
- [Apify client for Python](https://docs.apify.com/api/client/python/) (call Actors as tools)
- [Apify Store](https://apify.com/store) (find Actors to use as tools)
- [Secret environment variables](https://docs.apify.com/platform/actors/development/programming-interface/environment-variables)
- [apify-actor-development SKILL.md](https://github.com/apify/agent-skills/blob/main/skills/apify-actor-development/SKILL.md)

Continue to [Step 3: Call it from anywhere](#step-3-call-it-from-anywhere).

---

## Step 3: Call it from anywhere

Your agent already runs in the cloud. That also means anyone, or any agent, can start it.

**Time:** ~3 minutes

### 1. Over the API

Every Actor has a run endpoint, so you (or another agent) can trigger it over HTTP from anywhere:

```
https://api.apify.com/v2/acts/<your-username>~<actor-name>/runs?token=<API_TOKEN>
```

This is how your agent gets called in production. See
[Run Actor and retrieve data via API](https://docs.apify.com/academy/api/run-actor-and-retrieve-data-via-api)
and the [Apify API reference](https://docs.apify.com/api/v2).

### 2. Over MCP

Your Actor is also reachable through the Apify MCP server, so any MCP client - Claude, Cursor,
or another agent - can discover and run it as a tool. Point the client at
`https://mcp.apify.com` (OAuth on first use). Combined with pay per event in step 4, this is how
an autonomous agent finds and pays for your Actor. See
[Apify MCP server](https://docs.apify.com/platform/integrations/mcp).

**Your project:** think about who calls your agent - a person in Apify Console, your own app
over the API, or another agent over MCP.

**Resources**

- [Apify MCP server](https://docs.apify.com/platform/integrations/mcp) (`https://mcp.apify.com`)
- [API integration](https://docs.apify.com/platform/integrations/api) and the
  [Apify API reference](https://docs.apify.com/api/v2)
- [Run Actor and retrieve data via API](https://docs.apify.com/academy/api/run-actor-and-retrieve-data-via-api)

Continue to [Step 4: Monetize and publish](#step-4-monetize-and-publish).

---

## Step 4: Monetize and publish

Put a price on your agent, then publish it to Apify Store, so other people, and other agents,
can discover, run, and pay for it.

**Time:** ~7 minutes

### 1. Add your billing details

Before you can monetize, add your billing and payout details in Apify Console under
**Settings > Billing**, and complete
[identity verification](https://docs.apify.com/platform/actors/publishing/monetize/monthly-payouts#verify-your-identity).
You need both to receive payouts, and verification is also required for agentic payments.

### 2. Price it with pay per event

We use **pay per event (PPE)**: users pay for specific events you define, such as each result
produced. It is the most flexible model for agents, and the only one AI agents can pay for on
their own. Apify supports other
[pricing models](https://docs.apify.com/platform/actors/running/actors-in-store#pricing-models)
too.

Apify adds two [synthetic events](https://docs.apify.com/platform/actors/publishing/monetize/pay-per-event#synthetic-events)
that are charged automatically, with no code in your Actor:

- `apify-actor-start` - charged on every run start, and Apify covers the compute of the first 5
  seconds of each run. Keep the default price, and don't add your own start event.
- `apify-default-dataset-item` - charged for each item your Actor writes to its default dataset.
  If your agent pushes one item per answered query, like the `python-langgraph` template does,
  this is your per-result price.

Add a custom event charged with `Actor.charge()` only when your Actor delivers value that is
not a dataset item.

> **Note:** Leave LLM token costs out of your prices. The proxy runs on the token of the user
> who starts your Actor, so they already pay for their tokens directly. Using your own key? See
> the last point of [Use your own LLM key instead](#use-your-own-llm-key-instead).

### 3. Set up monetization

In the **Publishing** tab of your Actor, open **Monetization** and follow the wizard (full
walkthrough in [Set up monetization](https://docs.apify.com/platform/actors/monetize/set-up-monetization)):

1. **Actor pricing** - configure the events and their prices. Leave **Pay per event + usage**
   off.
2. **Primary event** - pick the one event that best represents the value your Actor delivers
   (for example, one result returned).
3. **Review** - confirm everything, then submit.

> **Note:** Your Actor automatically becomes eligible for autonomous agent payment over
> protocols like x402 and Skyfire when it uses PPE without **Pay per event + usage**, runs
> with [limited permissions](https://docs.apify.com/platform/actors/development/permissions),
> does not use Standby mode, and you have completed identity verification. There is no separate
> opt-in, so an AI agent can discover and pay for your Actor on its own. See
> [agentic payments](https://docs.apify.com/platform/actors/publishing/monetize#make-your-actor-eligible-for-agentic-payments).

### 4. Publish to Apify Store

In the **Publishing** tab, complete the publish checklist and submit your Actor to Apify Store.
A public Actor is what other people (and agents) can discover and run. See
[Publish your Actor](https://docs.apify.com/platform/actors/publishing/publish) for the full
checklist.

### 5. Track your earnings

Once your Actor has paying users, follow revenue and usage in Apify Console under
**Development > Insights > Analytics**. Payout invoices are generated automatically each month.

**Your project:** decide what one event represents the value your agent delivers, and what a
user would pay for it.

**Resources**

- [Publishing overview](https://docs.apify.com/platform/actors/publishing) and
  [Publish your Actor](https://docs.apify.com/platform/actors/publishing/publish)
- [Monetize your Actor](https://docs.apify.com/platform/actors/publishing/monetize) (agentic
  payments eligibility) and
  [Set up monetization](https://docs.apify.com/platform/actors/monetize/set-up-monetization)
- [Pay per event](https://docs.apify.com/platform/actors/publishing/monetize/pay-per-event)
- [Apify Store](https://apify.com/store)

Continue to [Step 5: Use Apify in your own projects](#step-5-use-apify-in-your-own-projects).

---

## Step 5: Use Apify in your own projects

You now have the full lifecycle working. To build your own agent, swap the input, the tool
Actor, and the output, then push and publish it just like in steps 1 to 4.

### Don't build from scratch - use ready-made Actors

You do not have to build everything yourself. [Apify Store](https://apify.com/store) has
thousands of ready-made Actors - scrapers, data extractors, integrations, and AI tools - that
you can use in your project in three ways:

- **As MCP tools, with zero glue code** - point your AI coding tool or agent at the
  [Apify MCP server](https://docs.apify.com/platform/integrations/mcp) (`https://mcp.apify.com`)
  and every Store Actor becomes a tool it can discover and call. The fastest way to give an agent
  real capabilities.
- **As tools your agent calls directly** - wire a Store Actor into your agent with the
  [Apify client for Python](https://docs.apify.com/api/client/python/), exactly like the workshop
  agent did.
- **As building blocks in any project** - call a Store Actor over the
  [API](https://docs.apify.com/api/v2) from any stack to get data or automation without writing
  the scraper or integration yourself. Even if your project is not an AI agent, this is
  the fastest way to get real data into it.

Browse [Apify Store](https://apify.com/store), find an Actor for your domain, and wire it in.

**Resources**

- [Apify Store](https://apify.com/store) (thousands of ready-made Actors for your project)
- [Apify MCP server](https://docs.apify.com/platform/integrations/mcp)
- [Apify API reference](https://docs.apify.com/api/v2) (call any Actor from any stack)
- [Input schema](https://docs.apify.com/platform/actors/development/actor-definition/input-schema)
  and [dataset schema](https://docs.apify.com/platform/actors/development/actor-definition/dataset-schema)
- Full link list in [Resources](#resources) below

That is the full lifecycle, plus everything Apify gives you for your next project. Now go build. Back
to the top: [Build, deploy, and monetize AI agents](#build-deploy-and-monetize-ai-agents).

---

## Resources

Everything linked across the steps, grouped for quick reference.

### Platform and Actors

- [The Apify platform](https://docs.apify.com/platform)
- [Actors overview](https://docs.apify.com/platform/actors)
- [Running Actors](https://docs.apify.com/platform/actors/running) and
  [Actors in Store](https://docs.apify.com/platform/actors/running/actors-in-store)
- [Apify Store](https://apify.com/store)

### CLI and SDKs

- [Apify CLI](https://docs.apify.com/cli/) -
  [installation](https://docs.apify.com/cli/docs/installation),
  [command reference](https://docs.apify.com/cli/docs/reference)
- [Apify SDK for Python](https://docs.apify.com/sdk/python)
- [Apify client for Python](https://docs.apify.com/api/client/python/)
- [Actor templates](https://apify.com/templates)

### Actor definition and storage

- [Actor definition](https://docs.apify.com/platform/actors/development/actor-definition)
- [actor.json](https://docs.apify.com/platform/actors/development/actor-definition/actor-json)
- [Input schema](https://docs.apify.com/platform/actors/development/actor-definition/input-schema)
  and [secret inputs](https://docs.apify.com/platform/actors/development/actor-definition/input-schema/secret-input)
- [Dataset schema](https://docs.apify.com/platform/actors/development/actor-definition/dataset-schema)
- [Dockerfile](https://docs.apify.com/platform/actors/development/actor-definition/dockerfile)
- [Storage](https://docs.apify.com/platform/storage) and
  [datasets](https://docs.apify.com/platform/storage/dataset)
- [Environment variables and secrets](https://docs.apify.com/platform/actors/development/programming-interface/environment-variables)

### Running over the API and MCP

- [Apify MCP server](https://docs.apify.com/platform/integrations/mcp) (`https://mcp.apify.com`) -
  use Store Actors as tools, and expose your own Actor to MCP clients
- [API integration](https://docs.apify.com/platform/integrations/api)
- [Run Actor and retrieve data via API](https://docs.apify.com/academy/api/run-actor-and-retrieve-data-via-api)
- [Apify API reference](https://docs.apify.com/api/v2)

### Publishing and monetization

- [Publishing overview](https://docs.apify.com/platform/actors/publishing)
- [Publish your Actor](https://docs.apify.com/platform/actors/publishing/publish)
- [Monetize your Actor](https://docs.apify.com/platform/actors/publishing/monetize)
- [Set up monetization](https://docs.apify.com/platform/actors/monetize/set-up-monetization)
- [Pay per event](https://docs.apify.com/platform/actors/publishing/monetize/pay-per-event)
- [Pricing models](https://docs.apify.com/platform/actors/running/actors-in-store#pricing-models)

### AI agents and tooling

- [Apify agent skills](https://github.com/apify/agent-skills) and the
  [apify-actor-development skill](https://github.com/apify/agent-skills/blob/main/skills/apify-actor-development/SKILL.md)
- [LangGraph](https://langchain-ai.github.io/langgraph/)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Apify OpenRouter proxy](https://apify.com/apify/openrouter) and
  [OpenRouter models](https://openrouter.ai/models)
- [Claude Code](https://docs.claude.com/en/docs/claude-code)

Back to the top: [Build, deploy, and monetize AI agents](#build-deploy-and-monetize-ai-agents).
