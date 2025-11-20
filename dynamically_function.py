import dotenv
import os

dotenv.load_dotenv()
import dump_promt

import asyncio
import inspect
import json
import threading
from typing import Any, Callable, get_type_hints

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents import Agent, Runner, FunctionTool
from agents.extensions.models.litellm_model import LitellmModel
from agents.tool_context import ToolContext


# ============================================================================
# Part 1: FastAPI Remote Server with Auto-Registration
# ============================================================================

app = FastAPI(title="Remote Tool Server")

# Registry to store all registered tools
TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


def remote_tool(func: Callable) -> Callable:
    """
    Decorator to automatically register a function as a remote tool.
    Extracts function signature, type hints, and docstring to create tool schema.
    """
    # Get function metadata
    func_name = func.__name__
    doc = inspect.getdoc(func) or "No description available"
    signature = inspect.signature(func)
    type_hints = get_type_hints(func)
    
    # Build JSON schema for parameters
    properties = {}
    required = []
    
    for param_name, param in signature.parameters.items():
        param_type = type_hints.get(param_name, str)
        
        # Map Python types to JSON schema types
        json_type = "string"  # default
        if param_type == int:
            json_type = "integer"
        elif param_type == float:
            json_type = "number"
        elif param_type == bool:
            json_type = "boolean"
        elif param_type == str:
            json_type = "string"
        
        properties[param_name] = {
            "type": json_type,
            "description": f"Parameter {param_name}"
        }
        
        # Check if parameter is required (no default value)
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
    
    parameters_schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False
    }
    
    # Register the tool
    TOOL_REGISTRY[func_name] = {
        "name": func_name,
        "description": doc,
        "parameters_schema": parameters_schema,
        "function": func
    }
    
    print(f"[Server] Registered tool: {func_name}")
    
    return func


# ============================================================================
# Define Remote Tools with Decorator
# ============================================================================

@remote_tool
def get_weather(city: str) -> str:
    """Returns current weather information for a given city"""
    # Simulate weather data
    weather_data = {
        "Beijing": "sunny, 25°C",
        "Shanghai": "cloudy, 22°C",
        "New York": "rainy, 18°C",
        "London": "foggy, 15°C",
    }
    return f"The weather in {city} is {weather_data.get(city, 'unknown - no data available')}."


@remote_tool
def calculate_sum(a: int, b: int) -> str:
    """Calculates the sum of two integers"""
    result = a + b
    return f"The sum of {a} and {b} is {result}."


# ============================================================================
# API Endpoints
# ============================================================================

class ToolCallRequest(BaseModel):
    tool_name: str
    parameters: dict[str, Any]


class ToolCallResponse(BaseModel):
    result: str
    success: bool


@app.get("/tool/list")
async def list_tools():
    """Return list of all registered tools with their schemas"""
    tools = []
    for tool_name, tool_info in TOOL_REGISTRY.items():
        tools.append({
            "name": tool_info["name"],
            "description": tool_info["description"],
            "parameters_schema": tool_info["parameters_schema"]
        })
    
    print(f"[Server] /tool/list called, returning {len(tools)} tools")
    return {"tools": tools}


@app.post("/tool/call")
async def call_tool(request: ToolCallRequest):
    """Execute a registered tool by name"""
    tool_name = request.tool_name
    params = request.parameters
    
    print(f"[Server] /tool/call - {tool_name} with params: {params}")
    
    if tool_name not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    
    try:
        tool_func = TOOL_REGISTRY[tool_name]["function"]
        result = tool_func(**params)
        
        print(f"[Server] Tool executed successfully, result: {result}")
        return ToolCallResponse(result=result, success=True)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameters: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "registered_tools": len(TOOL_REGISTRY)}


def run_fastapi_server():
    """Run FastAPI server in a background thread"""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


# ============================================================================
# Part 2: Client - Dynamic Tool Registration
# ============================================================================

async def fetch_remote_tools(api_base_url: str = "http://127.0.0.1:8000") -> list[dict]:
    """
    Fetch available tools from remote server's /tool/list endpoint
    
    Args:
        api_base_url: Base URL of the remote server
        
    Returns:
        List of tool definitions
    """
    print(f"\n[Client] Fetching tools from {api_base_url}/tool/list...")
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{api_base_url}/tool/list")
        response.raise_for_status()
        data = response.json()
        tools = data["tools"]
        
        print(f"[Client] Received {len(tools)} tool definitions from server")
        for tool in tools:
            print(f"  - {tool['name']}: {tool['description']}")
        
        return tools


def create_remote_function_tool(
    tool_definition: dict,
    remote_api_url: str = "http://127.0.0.1:8000/tool/call"
) -> FunctionTool:
    """
    Create a FunctionTool from a tool definition received from remote server.
    
    directly construct FunctionTool without decorator overhead.
    
    Args:
        tool_definition: Dict containing tool metadata from /tool/list
        remote_api_url: URL of the remote /tool/call endpoint
        
    Returns:
        FunctionTool ready to be used with an Agent
    """
    tool_name = tool_definition["name"]
    tool_description = tool_definition["description"]
    params_schema = tool_definition["parameters_schema"]
    
    async def on_invoke_tool(ctx: ToolContext, input_json: str) -> str:
        """
        Handler that gets called when the LLM invokes this tool.
        Calls the remote /tool/call endpoint.
        """
        # Parse parameters from LLM
        params = json.loads(input_json) if input_json else {}
        
        print(f"\n[Client] Calling remote tool '{tool_name}' with params: {params}")
        
        try:
            # Call the remote /tool/call API
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    remote_api_url,
                    json={
                        "tool_name": tool_name,
                        "parameters": params
                    }
                )
                response.raise_for_status()
                
                result_data = response.json()
                result = result_data["result"]
                
                print(f"[Client] Remote tool '{tool_name}' returned: {result}")
                return result
                
        except httpx.TimeoutException:
            error_msg = f"Remote tool '{tool_name}' timed out"
            print(f"[Client Error] {error_msg}")
            return error_msg
        except httpx.HTTPError as e:
            error_msg = f"Remote tool '{tool_name}' HTTP error: {str(e)}"
            print(f"[Client Error] {error_msg}")
            return error_msg
        except Exception as e:
            error_msg = f"Remote tool '{tool_name}' failed: {str(e)}"
            print(f"[Client Error] {error_msg}")
            return error_msg
    
    # Directly construct FunctionTool - Solution A
    return FunctionTool(
        name=tool_name,
        description=tool_description,
        params_json_schema=params_schema,
        on_invoke_tool=on_invoke_tool,
        strict_json_schema=True,
    )


async def create_agent_with_dynamic_tools(api_base_url: str = "http://127.0.0.1:8000") -> Agent:
    """
    Create an agent with tools dynamically fetched from remote server
    
    Args:
        api_base_url: Base URL of the remote server
        
    Returns:
        Agent configured with remote tools
    """
    # Fetch tool definitions from remote server
    tool_definitions = await fetch_remote_tools(api_base_url)
    
    # Convert each tool definition to a FunctionTool
    remote_tools = [
        create_remote_function_tool(tool_def, f"{api_base_url}/tool/call")
        for tool_def in tool_definitions
    ]
    
    print(f"\n[Client] Created {len(remote_tools)} FunctionTool objects")
    
    # Create agent with dynamically registered remote tools
    agent = Agent(
        name="Remote Tool Agent",
        instructions="You are a helpful assistant with access to remote tools. Use them to answer user questions.",
        tools=remote_tools,
        model=LitellmModel(
            model="deepseek/deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY")
        )
    )
    
    return agent


# ============================================================================
# Part 3: Main Program
# ============================================================================

async def main():
    """Main function to run the demo"""
    
    print("=" * 80)
    print("OpenAI Agents - Dynamic Remote Function Tools Demo")
    print("=" * 80)
    
    # Start FastAPI server in background thread
    print("\n[Server] Starting remote API server on http://127.0.0.1:8000...")
    server_thread = threading.Thread(target=run_fastapi_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    await asyncio.sleep(2)
    
    # Verify server is running
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:8000/health")
            health = response.json()
            print(f"[Server] Health check: {health}")
    except Exception as e:
        print(f"[Error] Failed to connect to server: {e}")
        return
    
    # Create agent with dynamically fetched remote tools
    agent = await create_agent_with_dynamic_tools()
    
    # Test queries
    test_queries = [
        "What's the weather like in Beijing today?",
        "Calculate the sum of 42 and 58",
        "What's the weather in London and what's 100 plus 200?"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print("\n" + "=" * 80)
        print(f"Test Query {i}: {query}")
        print("=" * 80)
        
        result = await Runner.run(agent, input=query)
        
        print("\n[Final Output]")
        print(result.final_output)
    
    print("\n" + "=" * 80)
    print("Demo completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
