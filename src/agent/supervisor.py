"""Supervisor workflow for managing specialized agents with human-friendly output.

This module creates a supervisor that manages research, math, and human output agents
to provide comprehensive responses with user-friendly formatting.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

from src.agent.mem import summarization_node
from langgraph.store.memory import InMemoryStore
from src.agent.rag_agent import make_graph
from src.agent.prompt import SUPERVISOR_PROMPT
from src.agent.tools import rag_client

store = InMemoryStore()
# Create specialized agents

model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-preview-05-20",
)



async def make_supervisor():

    rag_agent = await make_graph()
    # Create supervisor workflow
    workflow = create_supervisor(
        [rag_agent],
        model=model,
        prompt=SUPERVISOR_PROMPT,
        supervisor_name= "rag_supervisor"
    )

    # Compile and run
    supervisor = workflow.compile()
    return supervisor
