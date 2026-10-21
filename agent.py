import os
from typing import TypedDict, Annotated
import operator
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from tools import fetch_contact, send_email

load_dotenv()

API_KEY = os.environ.get("NVIDIA_API_KEY", "")
print(f"Using NVIDIA API Key: {API_KEY[:4]}...")

# 1. Initialize LLM
llm = ChatOpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=API_KEY,
    model="nvidia/nemotron-3.5-super-vl-120b-a12b",
    temperature=0.2,
    max_tokens=1024
)

tools = [fetch_contact, send_email]
llm_with_tools = llm.bind_tools(tools)

# 2. System Prompt Defined Here
SYS_PROMPT = """You are an elite, highly professional Executive AI Assistant.
Your primary job is to manage the user's communications efficiently.

STRICT RULES:
1. Always use the `fetch_contact` tool if you do not know the exact email address.
2. If a contact is not found, DO NOT make up an email. Ask the user for the email address.
3. Draft emails clearly and concisely.
4. Keep a highly professional and polite tone at all times.
"""

# 3. Define Graph State & Agent Node
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]

def agent_node(state: AgentState):
    # System message is automatically prepended to every run here
    messages_with_sys = [SystemMessage(content=SYS_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages_with_sys)
    return {"messages": [response]}

# 4. Assemble Graph
builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

memory = MemorySaver()

# Compile graph with human-in-the-loop interruption before tools
agent_executor = builder.compile(
    checkpointer=memory,
    interrupt_before=["tools"]
)