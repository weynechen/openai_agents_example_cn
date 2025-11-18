import dotenv
import os

dotenv.load_dotenv()
import dump_promt
# dump_promt.set_filename_prefix("my_custom_name")

import asyncio

from agents import Agent, Runner, function_tool
from agents.extensions.models.litellm_model import LitellmModel

# Custom cleaning tools
@function_tool
def material_check(materials: str) -> str:
    """Check if cleaning materials are ready. Input material list, return check result."""
    return f"Materials checked: {materials}. All materials are ready, cleaning can begin."

@function_tool
def cleaning_step(step: str) -> str:
    """Execute a specific cleaning step. Input step description, return execution result."""
    return f"Completed step: {step}. Step executed successfully, can proceed to next step."

@function_tool
def inspection(inspection_content: str) -> str:
    """Check current cleaning effect. Input inspection content, return inspection result."""
    return f"Inspection result: {inspection_content}. Cleaning effect is good, suggest continue or finish cleaning."

# ReAct instructions
REACT_INSTRUCTIONS = """You are an AI assistant that strictly follows the ReAct (Reasoning and Acting) pattern.

Core Rules - Must Follow Strictly:
1. Think step by step using the available tools
2. For each step, explain your reasoning before taking action
3. Use tools to gather information or take actions
4. Based on tool results (observations), decide the next step
5. Continue this process until the task is complete

Available Tools:
- material_check: Check if cleaning materials are prepared
- cleaning_step: Execute a specific cleaning step
- inspection: Check the cleaning effect

Process Flow:
1. First, analyze the task and check materials
2. Plan cleaning steps based on the situation (e.g., for greasy pan: use hot water + dish soap + scrubber)
3. Execute cleaning steps one by one
4. Inspect the result and decide if additional steps are needed
5. Provide final answer when task is complete

Important:
- Break down the task into clear, actionable steps
- Use tools to actually perform actions, don't just describe
- Be thorough but efficient
"""

agent = Agent(
    name="ReAct Cleaning Agent",
    instructions=REACT_INSTRUCTIONS,
    tools=[material_check, cleaning_step, inspection],
    model=LitellmModel(model="deepseek/deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY"))
)


async def main():
    print("=" * 60)
    print("ReAct Agent - Pan Cleaning Task")
    print("=" * 60)
    print()
    
    result = await Runner.run(agent, input="Task: Clean a very greasy frying pan")
    
    print("\n" + "=" * 60)
    print("Final Result:")
    print("=" * 60)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())