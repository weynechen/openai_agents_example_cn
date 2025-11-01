import dotenv
import os

dotenv.load_dotenv()
import dump_promt


from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
import asyncio

spanish_agent = Agent(
    name="历史 agent",
    instructions="你是一个历史学家，你只会回答关于历史的问题。",
    model = LitellmModel(model="deepseek/deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY"))
)

english_agent = Agent(
    name="地理 agent",
    instructions="你是一个地理学家，你只会回答关于地理的问题。",
    model = LitellmModel(model="deepseek/deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY"))
)

triage_agent = Agent(
    name="分类 agent",
    instructions="根据用户的问题，分类到历史或地理领域，并转交给相应的 agent。",
    handoffs=[spanish_agent, english_agent],
    model = LitellmModel(model="deepseek/deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY"))
)


async def main():
    result = await Runner.run(triage_agent, input="北京在哪个省？") # 秦始皇在哪个朝代？
    print(result.final_output)
    # ¡Hola! Estoy bien, gracias por preguntar. ¿Y tú, cómo estás?


if __name__ == "__main__":
    asyncio.run(main())