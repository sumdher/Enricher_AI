# chat/graph.py

import os
import sys
import ast
from typing import Annotated, Literal
from dotenv import load_dotenv

from pydantic import BaseModel
from typing_extensions import TypedDict
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_experimental.utilities import PythonREPL
from langchain_deepseek import ChatDeepSeek
from langchain_core.tools import tool
from langchain_core.runnables.config import RunnableConfig

load_dotenv()


class PydanticState(BaseModel):
    messages: Annotated[list, add_messages]

class State(TypedDict):
    messages: Annotated[list, add_messages]

@tool
def python_repl(code: str) -> str:
    """
    Execute safe Python code using an in-memory REPL.
    """
    repl = PythonREPL()
    try:
        result = repl.run(code)
    except BaseException as e:
        return f"Failed to execute. Error: {repr(e)}"
    return f"{result}"

def init_graph(tid: str, sys_msg: str | None = None, human_msg: str | None = None) -> CompiledStateGraph:
    memory = MemorySaver()
    graph_builder = StateGraph(PydanticState)

    search_tool = TavilySearchResults(max_results=1)
    tools = [search_tool, python_repl]

    llm = ChatDeepSeek(
        model="deepseek-chat",
        temperature=0.0,
        streaming=True,
    )
    llm_with_tools = llm.bind_tools(tools)

    def chatbot(state: State):
        return {"messages": [llm_with_tools.invoke(state["messages"])]}

    graph_builder.add_node("chatbot", chatbot)
    tool_node = ToolNode(tools=tools)
    graph_builder.add_node("tools", tool_node)

    graph_builder.add_conditional_edges("chatbot", tools_condition)
    graph_builder.add_edge("tools", "chatbot")
    graph_builder.set_entry_point("chatbot")

    graph = graph_builder.compile(checkpointer=memory)
    config: RunnableConfig = {"configurable": {"thread_id": tid}}

    if sys_msg:
        graph.invoke({"messages": [SystemMessage(content=sys_msg)]}, config)
    if human_msg:
        graph.invoke({"messages": [HumanMessage(content=human_msg)]}, config)

    return graph
