import dotenv
import os

dotenv.load_dotenv()

# Import dump_promt to register LiteLLM callback BEFORE using the model
import dump_promt

from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel

agent = Agent(name="Assistant", 
                    instructions="You are a helpful assistant",
                    model = LitellmModel(model="deepseek/deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY")),
                    )

result = Runner.run_sync(agent, "写一个秋天为主题的三行诗")
print(result.final_output)
