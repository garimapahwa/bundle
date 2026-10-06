"""Module defines the main entry point for the Apify Actor.

Feel free to modify this file to suit your specific needs.

To build Apify Actors, use the Apify SDK toolkit, read more at the official documentation:
https://docs.apify.com/sdk/python
"""

from __future__ import annotations

import logging
import os

from apify import Actor
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from .models import AgentStructuredOutput
from .tools import tool_calculator_sum, tool_scrape_instagram_profile_posts
from .utils import log_state


async def main() -> None:
    """Define a main entry point for the Apify Actor.

    This coroutine is executed using `asyncio.run()`, so it must remain an asynchronous function for proper execution.
    Asynchronous execution is required for communication with Apify platform, and it also enhances performance in
    the field of web scraping significantly.

    Raises:
        ValueError: If the input is missing required attributes.
    """
    async with Actor:
        # Handle input
        actor_input = await Actor.get_input()

        query = actor_input.get('query')
        if not query:
            msg = 'Missing "query" attribute in input!'
            raise ValueError(msg)

        model_name = actor_input.get('modelName', 'openai/gpt-4o-mini')
        if actor_input.get('debug', False):
            Actor.log.setLevel(logging.DEBUG)

        # Route the LLM through the Apify OpenRouter proxy, so no provider API key is needed
        llm = ChatOpenAI(
            model=model_name,
            base_url='https://openrouter.apify.actor/api/v1',
            api_key=os.environ['APIFY_TOKEN'],
        )

        # Create the agent graph
        # see https://docs.langchain.com/oss/python/langchain/agents
        tools = [tool_calculator_sum, tool_scrape_instagram_profile_posts]
        graph = create_agent(llm, tools, response_format=AgentStructuredOutput)

        inputs: dict = {'messages': [('user', query)]}
        response: AgentStructuredOutput | None = None
        last_message: str | None = None
        async for state in graph.astream(inputs, stream_mode='values'):
            log_state(state)
            if state.get('structured_response') is not None:
                response = state['structured_response']
                last_message = state['messages'][-1].content
                break

        if not response or not last_message:
            Actor.log.error('Failed to get a response from the agent!')
            await Actor.fail(status_message='Failed to get a response from the agent!')
            return

        # Push results to the key-value store and dataset
        store = await Actor.open_key_value_store()
        await store.set_value('response.txt', last_message)
        Actor.log.info('Saved the "response.txt" file into the key-value store!')

        # Charged automatically by the synthetic `apify-default-dataset-item` event (one item per answered query)
        await Actor.push_data(
            {
                'response': last_message,
                'structured_response': response.dict(),
            }
        )
        Actor.log.info('Pushed data into the dataset!')
