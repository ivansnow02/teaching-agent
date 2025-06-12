"""New LangGraph Agent.

This module defines a custom graph.
"""

import dotenv

# from src.agent.supervisor import make_supervisor
# from src.agent.knowledge_analysis_agent import make_graph
from src.agent.lesson_plan_workflow import build_workflow
from src.agent.rag_agent import make_graph

dotenv.load_dotenv()

__all__ = [
    # "make_supervisor",
    # "make_graph",
    "build_workflow",
    "make_graph",
]
