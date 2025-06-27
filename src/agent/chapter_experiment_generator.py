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

from src.agent.tools import (
    calculate_time,
    code_generate_tool,
    code_validate_tool,
    count_words,
    rag_tool,
    search,
)


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
    past_steps: Annotated[List[Tuple[str, str, str]], operator.add]

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
你是一名资深实训课教案设计专家。请根据以下课程大纲，生成一份实训课教案的详细实验操作步骤。

要求如下：
- 每个步骤应为一条简明的实验操作步骤。
- 步骤内容应聚焦于教学与实验过程本身，不涉及实验报告提交、平台操作等管理流程。
- 步骤顺序合理，便于教师直接用于课堂教学。
- 简单的步骤可以省略，例如：打开计算机
- 步骤要方便后续大模型生成，不要出现：教师巡查、学生提问等管理流程。

课程大纲:
---
{state['raw_syllabus']}
---

请严格按照以下 JSON 格式输出，不要包含任何解释、注释或Markdown标记外的任何文本。
{plan_schema}
"""

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
    tools=[rag_tool, search, code_generate_tool, code_validate_tool],
    prompt="""你是实训课教案撰写助手，负责根据教学计划中的每个步骤，生成详细、连贯且可操作的实验步骤内容。
请确保每个步骤内容详实、逻辑清晰，便于教师和学生直接参考。
如遇专业知识点或不确定内容，优先调用 rag_tool 检索知识库，必要时使用 search 搜索外部资料。
如果需要生成代码，优先调用 code_generate_tool，必要时使用 code_validate_tool 进行验证。
输出内容应聚焦于实验教学本身，避免涉及管理流程。
需使用markdown标题表明当前的步骤，请从###开始，步骤尽量简短作为标题
请用简洁明了的语言，适当包含代码示例、注意事项或操作要点。""",
)


async def summarize_step(detail: str) -> str:
    prompt = f"请用一句话总结以下内容，突出关键操作和要点：\n\n{detail}"
    resp_llm = init_chat_model(
        model="qwen3-14b",
        model_provider="openai",
        temperature=0,
        extra_body={"enable_thinking": False},
        api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
        base_url=os.getenv(
            "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
    )
    result = await resp_llm.ainvoke(prompt)
    return result.content.strip()


async def execute_step(state: PlanExecutionState, config) -> Dict:
    child_config = {"configurable": config.get("configurable", {})}

    plan = state["plan"]
    if not plan:
        return {"past_steps": []}

    completed = [step[0] for step in state.get("past_steps", [])]
    plan_str = "\n".join([f"{i+1}. {step}" for i, step in enumerate(completed + plan)])
    task = plan[0]
    task_formatted = f"""针对以下计划：{plan_str}\n\n你需要执行：{task}。"""
    agent_response = await execution_agent.ainvoke(
        {"messages": [("user", task_formatted)]}, config
    )
    detail = agent_response["messages"][-1].content

    # 移除已执行的步骤
    new_plan = plan[1:]
    summary = await summarize_step(detail)

    return {
        "past_steps": [(task, detail, summary)],
        "plan": new_plan,
    }


async def replan_step(state: PlanExecutionState, config) -> Dict:
    """
    Replan the lesson plan based on the current state and configuration.
    :param state:
    :param config:
    :return:
    """
    completed_steps = (
        [f"{step[0]}:\n\n{step[2]}" for step in state["past_steps"]]
        if state["past_steps"]
        else []
    )
    prompt = f"""
你是一个实训课教案生成专家。请根据以下信息重新规划实训课教案的步骤。
你需要根据当前的进展和剩余的计划，生成一个详细的教案步骤列表。

**原始目标**:
{state['raw_syllabus']}

**已完成的步骤**:
{completed_steps or 'null'}

**剩余的计划**:
{state['plan'] or 'null'}

请严格按照以下二选一的 JSON 格式输出，不要包含任何多余内容，不要加代码块标记：

1. 如果还需要继续生成计划，返回：
{{
  "action": {{
    "steps": [
      "步骤1",
      "步骤2"
    ]
  }}
}}

2. 如果可以直接回复用户，返回：
{{
  "action": {{
    "response": "你的最终答复内容"
  }}
}}

只允许上述两种格式，且字段名必须完全一致。
不要返回已经完成的步骤，只需返回新的步骤或最终答复内容。
"""

    structured_llm = planner.with_structured_output(Act)
    result = await structured_llm.ainvoke(prompt)
    if isinstance(result.action, Response):
        return {"response": result.action.response}
    else:
        return {"plan": result.action.steps}


def should_end(state: PlanExecutionState):
    if "response" in state and state["response"]:
        return "finalizer"
    else:
        return "agent"


async def compose_final_response(state: PlanExecutionState, config) -> Dict:
    steps = state.get("past_steps", [])

    final_resp = "\n\n".join([f"{step[1]}" for step in steps])

    return {"response": final_resp}


def build_experiment_planner():
    workflow = StateGraph(PlanExecutionState, ConfigSchema)
    workflow.add_node("planner", plan_step)
    workflow.add_node("agent", execute_step)
    workflow.add_node("replanner", replan_step)
    workflow.add_node("finalizer", compose_final_response)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "agent")
    workflow.add_edge("agent", "replanner")
    workflow.add_conditional_edges(
        "replanner",
        # Next, we pass in the function that will determine which node is called next.
        should_end,
        ["agent", "finalizer"],
    )
    workflow.add_edge("finalizer", END)

    return workflow.compile()
