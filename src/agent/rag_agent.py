"""LangGraph agent with RAG tools."""

import os
from typing import Literal, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.constants import END, START
from langgraph.graph import MessagesState, StateGraph
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from src.agent.prompt import GENERATE_PROMPT, GRADE_PROMPT, REWRITE_PROMPT
from src.agent.tools import get_rag_tools

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.25,  # <-- Super slow! We can only make a request once every 10 seconds!!
    check_every_n_seconds=0.1,  # Wake up every 100 ms to check whether allowed to make a request,
    max_bucket_size=10,  # Controls the maximum burst size.
)
#         search_mode: Search mode - "default", "naive", "local", "global", "hybrid", "mix"
response_model = init_chat_model(
    model="qwen3-235b-a22b",
    model_provider="openai",
    temperature=0,
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    # rate_limiter=rate_limiter,
    extra_body={"enable_thinking": False},
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)


class ConfigSchema(TypedDict):
    course_id: str


class RAGState(MessagesState):
    max_rewrite: int
    rewrite_count: int


async def generate_query_or_respond(state: RAGState, config):
    """Call the model to generate a response based on the current state. Given
    the question, it will decide to retrieve using the retriever tool, or simply respond to the user.
    """
    print("Generating query or responding...")
    course_id = config.get("configurable", {}).get("course_id", None)
    if "rewrite_count" not in state:
        state["rewrite_count"] = 0
    if "max_rewrite" not in state:
        state["max_rewrite"] = 3
    if course_id is None:
        raise ValueError("Course ID must be provided in the config.")
    retriever_tool = await get_rag_tools(course_id)
    response = await response_model.bind_tools(retriever_tool).ainvoke(
        state["messages"]
    )
    return {"messages": [response]}


class GradeDocuments(BaseModel):
    """Grade documents using a binary score for relevance check."""

    relevant: str = Field(
        description="Relevance score: 'yes' if relevant, or 'no' if not relevant"
    )


grader_model = init_chat_model(
    model="qwen3-235b-a22b",
    model_provider="openai",
    temperature=0,
    extra_body={"enable_thinking": False},
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    # rate_limiter=rate_limiter,
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)


def grade_documents(
    state: RAGState,
    config,
) -> Literal["generate_answer", "rewrite_question"]:
    rewrite_count = state["rewrite_count"]
    max_rewrite = state["max_rewrite"]
    if rewrite_count >= max_rewrite:
        return "generate_answer"

    question = state["messages"][0].content
    context = state["messages"][-1].content

    prompt = GRADE_PROMPT.format(question=question, context=context)
    response = grader_model.with_structured_output(GradeDocuments).invoke(
        [{"role": "user", "content": prompt}]
    )
    score = response.relevant

    if score == "yes":
        return "generate_answer"
    else:
        return "rewrite_question"


def rewrite_question(state: RAGState, config):
    rewrite_count = state["rewrite_count"]

    messages = state["messages"]
    question = messages[0].content
    prompt = REWRITE_PROMPT.format(question=question)
    response = response_model.invoke([{"role": "user", "content": prompt}])

    return {
        "messages": [{"role": "user", "content": response.content}],
        "rewrite_count": rewrite_count + 1,
    }


def generate_answer(state: RAGState):
    """Generate an answer."""
    question = state["messages"][0].content
    context = state["messages"][-1].content
    prompt = GENERATE_PROMPT.format(question=question, context=context)
    response = response_model.invoke([{"role": "user", "content": prompt}])
    return {"messages": [response]}


async def retrieve_documents(state: RAGState, config):
    """Retrieve documents using the RAG tool."""
    course_id = config.get("configurable", {}).get("course_id", None)

    if course_id is None:
        raise ValueError("User ID must be provided in the config.")

    retrieve_tools = await get_rag_tools(course_id)

    tool_node = ToolNode(retrieve_tools)

    result = await tool_node.ainvoke(state)

    return result


async def make_graph() -> CompiledGraph:
    """Run the graph."""
    workflow = StateGraph(RAGState, ConfigSchema)

    # Define the nodes we will cycle between
    workflow.add_node(generate_query_or_respond)
    workflow.add_node("retrieve", retrieve_documents)
    workflow.add_node(rewrite_question)
    workflow.add_node(generate_answer)

    workflow.add_edge(START, "generate_query_or_respond")

    # Decide whether to retrieve
    workflow.add_edge("generate_query_or_respond", "retrieve")

    # Edges taken after the `action` node is called.
    workflow.add_conditional_edges(
        "retrieve",
        # Assess agent decision
        grade_documents,
    )
    workflow.add_edge("generate_answer", END)
    workflow.add_edge("rewrite_question", "generate_query_or_respond")

    # Compile
    graph = workflow.compile(name="rag_agent")

    return graph
