"""New LangGraph Agent.

This module defines a custom graph.
"""

import dotenv

# from src.agent.supervisor import make_supervisor
# from src.agent.knowledge_analysis_agent import make_graph
from src.agent.lesson_plan_workflow import build_plan_workflow
from src.agent.quiz_generator import build_quiz_workflow
from src.agent.rag_agent import make_graph
from src.agent.chapter_content_generator import build_lesson_planner
from src.agent.chapter_outline_generator import build_chapter_graph
from src.agent.code_agent import build_code_agent
from src.agent.chapter_experiment_generator import build_experiment_planner
from src.agent.quiz_generator_beta import build_quiz_planner_v2

dotenv.load_dotenv()

__all__ = [
    # "make_supervisor",
    # "make_graph",
    "build_plan_workflow",
    "make_graph",
    "build_quiz_workflow",
    "build_lesson_planner",
    "build_chapter_graph",
    "build_code_agent",
    "build_experiment_planner",
    "build_quiz_planner_v2",
]
