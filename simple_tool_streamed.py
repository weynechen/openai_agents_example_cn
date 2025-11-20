import dotenv
import os

dotenv.load_dotenv()
import dump_promt
# dump_promt.set_filename_prefix("my_custom_name")

import asyncio

from agents import Agent, Runner, function_tool
from agents.extensions.models.litellm_model import LitellmModel
from openai.types.responses import ResponseTextDeltaEvent

@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."


agent = Agent(
    name="Hello world",
    instructions="You are a helpful agent.",
    tools=[get_weather],
    model = LitellmModel(model="deepseek/deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY"))
)


async def main():
    result = Runner.run_streamed(agent, input="今天北京天气怎么样？")
    async for event in result.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            print(event.data.delta, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())