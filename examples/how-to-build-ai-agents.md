<!-- Real output of solution/ for the input {"topic": "how to build AI agents"}. Run on 2026-11-16 with anthropic/claude-haiku-5.5, 65 seconds. Not edited. -->

# Content brief: how to build AI agents

The most-viewed videos on this topic are beginner explainers that promise to make agents simple: Jeff Su, Futurepedia, Sandeep Swadia and Liam Ottley all open by reassuring a non-technical viewer that agents are easier than they look, or by naming a payoff. Hannah Fry's piece is the outlier, a news-style documentary about a self-built agent. The gap: none of the five openings shows a viewer the first build step on screen within the first minute. Jeff Su's opening is a wall of jargon, and the "build" promise is delivered mostly through definitions and frameworks rather than a working agent. A creator who opens by building a small agent live, in the first sentences, and keeps the definitions short would stand apart from every winner here.

## What is winning

### [AI Agents, Clearly Explained](https://www.youtube.com/watch?v=FwOTs4UxQS4)
Jeff Su - 5,740,795 views

> AI. AI. AI. AI. AI. AI. You know, more agentic. Agentic capabilities. An AI agent. Agents. Agentic workflows. Agents. Agents. Agent. Agent. Agent. Agent. Agentic. All right. Most explanations of AI agents is either too technical or too basic.

The rapid repetition of buzzwords names the confusion every viewer already feels, then the next line promises a middle path for people with zero technical background.

### [From Zero to Your First AI Agent in 25 Minutes (No Coding)](https://www.youtube.com/watch?v=EH5jx5qPabU)
Futurepedia - 4,607,177 views

> AI agents are one of the most exciting and fast-moving areas of AI. They're becoming incredibly powerful. And if you've been watching from the sidelines, it might feel like you're getting left behind.

It names a fear of falling behind and then, in the title and the next lines, promises a concrete outcome, a first agent in 25 minutes, so the viewer knows what they will walk away with.

### [How to Build & Sell AI Agents: Ultimate Beginner’s Guide](https://www.youtube.com/watch?v=w0H1-b044KY)
Liam Ottley - 3,979,729 views

> Two years ago, I taught myself how to build AI agents without any prior experience in AI. And since then, I've started multiple AI businesses that have generated over $5 million in revenue.

A credentialed personal story with large numbers establishes that the path works for someone who started at zero, which makes the promise to teach 'everything' believable.

### [You’re Not Behind (Yet): Learn AI Agents in 13 Minutes](https://www.youtube.com/watch?v=P5sKKnWCvzk)
Sandeep Swadia - 3,510,671 views

> Most people think they're using AI well when they get a decent answer from chat GPT. That was enough 6 months ago. It's not enough anymore.

It flatters the viewer's current habits and then says they are out of date, creating urgency before introducing a three-part test (ARR) that gives a fast decision rule.

### [Why AI Agents are either the best or worst thing we’ve ever built](https://www.youtube.com/watch?v=WnzR5aOElvw)
Hannah Fry - 2,762,892 views

> For the last few years, we've all been learning how to talk to AI. You ask it a question, it gives you an answer. You're in control. But a few months ago, something pretty seismic shifted.

It sets up a before-and-after contrast ('you're in control') and then a shift, which creates tension that the viewer wants resolved.

## Hook patterns

- Names the confusion the viewer already has, then promises a path for beginners: Jeff Su opens with a jargon loop and says most explanations are 'either too technical or too basic.'
- Names a fear of falling behind and attaches a concrete time promise: Futurepedia says 'you're getting left behind' and then the title promises a first agent in 25 minutes.
- Opens with a credentialed personal result that proves a zero-experience start is possible: Liam Ottley says he taught himself 'without any prior experience' and then cites '$5 million in revenue.'
- Says the viewer's current habit is out of date, then offers a short decision rule: Sandeep Swadia tells viewers that a decent ChatGPT answer 'It's not enough anymore,' then introduces his ARR test.

## Script ideas

### 1. I Built an AI Agent in 9 Minutes. Here's the Exact Setup.

**Hook:** Here's an AI agent I built this morning, and I'm going to build it again right now, in front of you, in under ten minutes. Every step is on screen, so you can pause and copy it.

- Show the finished agent working first, a 30-second demo that takes one real input and returns one real output.
- Define only the three parts you need to build it (goal, tools, a loop that checks its own output), skipping the vocabulary list.
- Build it live with no slides, timing each step on screen so the viewer can see how long it takes.
- Show the one place it failed, and the one-line fix, to prove it is a working build and not a demo.
- End with a copyable template and a single next task for the viewer to build the same agent for their own job.

### 2. Your AI Agent Will Fail the First Time. Here's How I Know Before You Ship It.

**Hook:** Every AI agent tutorial shows you the version that works. I'm going to show you the version I deleted, because it sent a client the wrong invoice twice before I caught it.

- Show the failed agent and the specific mistake it made, with the real output on screen.
- Explain the three checks you can add without code: a review step before any send action, a spending or action limit, and a log of every tool call.
- Rebuild the agent with those checks and run the same input again to show the difference.
- Give a short checklist for deciding which tasks should never be fully autonomous, pulling from the autonomous-recurring-reviewable idea in the Sandeep Swadia video but adding the failure cases it leaves out.

### 3. I Gave an AI Agent Access to My Spreadsheet for a Week. Here's What I Built First.

**Hook:** I gave an AI agent write access to a real spreadsheet for one week, and I'm going to tell you exactly which build decision I got wrong on day one.

- Name the one real workflow you chose (for example, sorting incoming leads) and why it is small enough to build in an afternoon.
- Walk through the build decisions in order: choosing the tool, limiting what it can write, and setting up the trigger.
- Show day-one results with numbers, including the error that the spreadsheet exposed.
- Show what you changed on day two and how the agent performed by day seven.
- Close with a rule the viewer can apply to any spreadsheet task, without needing to know how to code.
