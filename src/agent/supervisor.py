"""Supervisor workflow for managing specialized agents with human-friendly output.

This module creates a supervisor that manages research, math, and human output agents
to provide comprehensive responses with user-friendly formatting.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor
from src.agent.mem import summarization_node
from langgraph.store.memory import InMemoryStore
from src.agent.graph import make_graph

store = InMemoryStore()
# Create specialized agents

model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-preview-05-20",
)


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


def web_search(query: str) -> str:
    """Search the web for information."""
    return (
        "Here are the headcounts for each of the FAANG companies in 2024:\n"
        "1. **Facebook (Meta)**: 67,317 employees.\n"
        "2. **Apple**: 164,000 employees.\n"
        "3. **Amazon**: 1,551,000 employees.\n"
        "4. **Netflix**: 14,000 employees.\n"
        "5. **Google (Alphabet)**: 181,269 employees."
    )



math_agent = create_react_agent(
    model=model,
    tools=[add, multiply],
    name="math_expert",
    pre_model_hook=summarization_node,
    prompt="You are a math expert. Always use one tool at a time.",
)

research_agent = create_react_agent(
    model=model,
    tools=[web_search],
    pre_model_hook=summarization_node,
    name="research_expert",
    prompt="You are a world class researcher with access to web search. Do not do any math.",
)

# human_output_agent = create_react_agent(
#     model=model,
#     pre_model_hook=summarization_node,
#     tools=[],
#     name="human_output_expert",
#     prompt=(
#         "You are an expert at formatting and presenting information to humans. "
#         "Your job is to take the results from other agents and format them in a clear, "
#         "engaging way for human consumption. Always use the format_output tool to "
#         "present the final results. Determine the appropriate output_type based on "
#         "the content (math, research, or general)."
#     ),
# )
# memory_manager = create_memory_manager_agent(store)


async def make_supervisor():

    rag_agent = await make_graph()
    # Create supervisor workflow
    workflow = create_supervisor(
        [research_agent, math_agent, rag_agent],
        model=model,
        prompt=(
            "You are a team supervisor managing a research expert, a math expert, and a human output expert. "
            "For current events, use research_agent. "
            "For math problems, use math_agent. "
            "Ensure that the final output is clear, engaging, and suitable for human readers."
            "For any knowledge base queries, use the rag_agent to retrieve relevant information."
        ),
        supervisor_name= "rag_supervisor"
    )

    # Compile and run
    supervisor = workflow.compile()
    return supervisor
