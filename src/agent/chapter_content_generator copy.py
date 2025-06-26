import operator
import os
import pprint
from typing import Annotated, Dict, List, Optional, Tuple, TypedDict, Union

from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model
from langchain_core.prompts import PromptTemplate
from langgraph.constants import END
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field

from src.agent.tools import calculate_time, count_words, rag_tool


class ConfigSchema(TypedDict):
    course_id: str


class PlanExecutionState(TypedDict):
    """
    Represents the state of the plan execution.
    """

    raw_syllabus: str

    plan: List[str]

    # Annotated 用于为 past_steps 字段指定一个 reducer。
    # operator.add 会将新步骤附加到现有列表中，而不是替换它，
    # 这与 TypeScript 中的 (x, y) => x.concat(y) 行为相同。
    past_steps: Annotated[List[Tuple[str, str]], operator.add]

    response: str


class Plan(BaseModel):
    """Plan to follow in future"""

    steps: List[str] = Field(
        description="用于生成课程计划的步骤列表。每个步骤都是一个字符串，描述了要执行的操作，按照顺序排列。"
    )


planner = init_chat_model(
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


# 2. 从 Pydantic 模型生成 JSON Schema
plan_schema = Plan.model_json_schema()


class Response(BaseModel):
    """Response to user."""

    response: str


class Act(BaseModel):
    """Action to perform."""

    action: Union[Response, Plan] = Field(
        description="要执行的操作。如果你想直接回复用户，请使用 Response。"
        "如果你需要进一步调用工具获取答案，请使用 Plan。"
    )


async def plan_step(state: PlanExecutionState, config) -> Dict:
    """
    generate a lesson plan step based on the current state and configuration.
    :param state:
    :param config:
    :return:
    """

    prompt = f"""
你是一个教案生成专家。请将以下用户提供的教学大纲，转化为一个清晰、分步的教案撰写计划。
每个步骤应该是一个独立的、可执行的任务，确保内容只与教案相关。

大纲:
---
{state['raw_syllabus']}
---

请输出计划步骤。
请严格按照以下 JSON 格式输出，不要包含任何解释、注释或Markdown标记外的任何文本。
{plan_schema}"""

    structured_llm = planner.with_structured_output(Plan)
    try:
        result = await structured_llm.ainvoke(prompt)
        return {
            "plan": result.steps,
        }
    except Exception as e:
        print(f"规划失败: {e}")
        return {
            "plan": [],
        }


executioner = init_chat_model(
    model="qwen3-30b-a3b",
    model_provider="openai",
    temperature=0,
    extra_body={"enable_thinking": False},
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    # rate_limiter=rate_limiter,
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)

execution_agent = create_react_agent(
    model=executioner,
    tools=[rag_tool, count_words, calculate_time],
    prompt="你是一个教案撰写助手，负责执行教学计划中的步骤。提供的计划内容，撰写相应的任务并返回结果。确保内容至于教案有关，你需要运用rag_tool检索相关知识库，count_words计算生成字数，calculate_time计算内容教授所需时间。\n\n",
)


async def execute_step(state: PlanExecutionState, config) -> Dict:
    child_config = {"configurable": config.get("configurable", {})}

    plan = state["plan"]
    plan_str = "\n".join(f"{i+1}. {step}" for i, step in enumerate(plan))
    task = plan[0]
    task_formatted = f"""针对以下计划：{plan_str}\n\n你需要执行第{1}步：{task}。"""
    agent_response = await execution_agent.ainvoke(
        {"messages": [("user", task_formatted)]}, child_config
    )
    return {
        "past_steps": [(task, agent_response["messages"][-1].content)],
    }


async def replan_step(state: PlanExecutionState, config) -> Dict:
    """
    Replan the lesson plan based on the current state and configuration.
    :param state:
    :param config:
    :return:
    """

    prompt = f"""
你是一个教案生成专家。请根据以下信息重新规划教案。
你只能在需要时添加新的步骤，而不是修改或删除现有步骤。
确保步骤专注于教案的生成，而不是其他任务。

**原始目标**:
{state['raw_syllabus']}

**已完成的步骤和结果**:
{state["past_steps"] or 'null'}

**剩余的计划**:
{state["plan"] or 'null'}

**决策时间**:
请严格按照以下JSON格式进行响应，不要包含任何其他文本。
{Act.model_json_schema()}
请根据当前进展更新你的计划。如果不再需要更多步骤并且可以直接回复用户，请直接返回结果。否则，请填写接下来的计划。只需添加仍需完成的步骤，不要将已完成的步骤再次作为计划返回。
"""

    structured_llm = planner.with_structured_output(Act)
    result = await structured_llm.ainvoke(prompt)
    if isinstance(result.action, Response):
        return {"response": result.action.response}
    else:
        return {"plan": result.action.steps}


def should_end(state: PlanExecutionState):
    if "response" in state and state["response"]:
        return END
    else:
        return "agent"


def build_lesson_planner():
    workflow = StateGraph(PlanExecutionState, ConfigSchema)
    workflow.add_node("planner", plan_step)
    workflow.add_node("agent", execute_step)
    workflow.add_node("replanner", replan_step)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "agent")
    workflow.add_edge("agent", "replanner")
    workflow.add_conditional_edges(
        "replanner",
        # Next, we pass in the function that will determine which node is called next.
        should_end,
        ["agent", END],
    )

    return workflow.compile()
