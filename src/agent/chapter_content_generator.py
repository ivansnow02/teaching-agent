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
from sentence_transformers.cross_encoder.evaluation import classification

from src.agent.tools import (
    calculate_time,
    code_generate_tool,
    code_validate_tool,
    count_words,
    get_math_tool,
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
    before_parallel_plan: List[str]  # 用于存储并行执行前的步骤
    parallel_plan: List[str]
    after_parallel_plan: List[str]  # 用于存储并行执行后的步骤
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
你是一名资深教案设计专家。请根据以下课程大纲，生成一份详细、清晰、分步的教案撰写计划。

要求如下：
- 每个步骤应为一条具体且简明的教案撰写操作。
- 步骤内容应聚焦于教学内容本身，不涉及管理流程、平台操作等非教学环节。
- 步骤顺序合理，便于教师直接参考和执行。
- 可省略过于简单的步骤，例如：设计课程标题、组织教学顺序、准备示例
- 步骤要方便后续大模型生成，不要出现如“教师巡查”、“学生提问”等管理性描述。
- 不需要出现练习题设计环节

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


async def classify_task_step(state: PlanExecutionState, config) -> Dict:
    """
    Classify the task to be whether it can be executed parallelly or it needs to be executed after all previous tasks are completed.
    :param state:
    :param config:
    :return:
    """

    plan = state["plan"]
    if not plan:

        return {
            "before_parallel_plan": [],
            "parallel_plan": [],
            "after_parallel_plan": [],
        }

    class Classifier(BaseModel):
        before_parallel_plan: List[str] = Field(
            description="在并行执行之前需要完成的步骤列表。"
        )
        parallel_plan: List[str] = Field(description="可以并行执行的步骤列表。")
        after_parallel_plan: List[str] = Field(
            description="在并行执行之后需要完成的步骤列表。"
        )

    classification_prompt = f"""
你是一个智能教案执行分类专家。请根据以下计划步骤，判断每个步骤是否可以并行执行。

两个步骤可以并行执行的条件是它们之间没有依赖关系，例如课程主题的确定等需要在并行执行之前完成，课程内容的生成步骤可以并行，而课程内容的审核、总结、作业、评估等步骤需要在内容生成后顺序执行。

以下是计划步骤：
{plan}
请将每个步骤分类为以下三类：
1. 在并行执行之前需要完成的步骤（before_parallel_plan）
2. 可以并行执行的步骤（parallel_plan）
3. 在并行执行之后需要完成的步骤（after_parallel_plan）
JSON 对象，格式如下：
```json
{Classifier.model_json_schema()}
"""
    structured_llm = executioner.with_structured_output(Classifier)
    result = await structured_llm.ainvoke(classification_prompt)
    return {
        "before_parallel_plan": result.before_parallel_plan,
        "parallel_plan": result.parallel_plan,
        "after_parallel_plan": result.after_parallel_plan,
    }


async def summarize_step(detail: str) -> str:
    prompt = f"请用一句话总结以下内容，突出关键知识点和教学要点：\n\n{detail}"
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


async def execute_before_parallel_step(state: PlanExecutionState, config) -> Dict:
    """
    Execute a sequential step in the lesson plan.
    :param state:
    :param config:
    :return:
    """
    before_parallel_plan = state["before_parallel_plan"]
    if not before_parallel_plan:
        return {"past_steps": []}

    child_config = {"configurable": config.get("configurable", {})}
    task = before_parallel_plan[0]
    completed_steps = (
        [f"{step[0]}:\n\n{step[2]}" for step in state["past_steps"]]
        if state["past_steps"]
        else []
    )
    task_formatted = f"""
针对以下计划：{task}\n\n你需要执行此步骤：{task}。
这是前面的历史步骤和结果：
{completed_steps or 'null'}
"""
    agent_response = await execution_agent.ainvoke(
        {"messages": [("user", task_formatted)]}, child_config
    )
    detail = agent_response["messages"][-1].content
    summary = await summarize_step(detail)

    return {"past_steps": [(task, detail, summary)]}


math_tool = get_math_tool(
    init_chat_model(
        model="qwen2.5-coder-32b-instruct",
        model_provider="openai",
        temperature=0,
        # extra_body={"enable_thinking": False},
        api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
        base_url=os.getenv(
            "DASH_SCOPE_API_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )
)
execution_agent = create_react_agent(
    model=executioner,
    tools=[
        rag_tool,
        count_words,
        calculate_time,
        search,
        math_tool,
        code_generate_tool,
        code_validate_tool,
    ],
    prompt="""你是教案撰写助手，负责根据教学计划中的每个步骤，生成详细、连贯且可操作的教案内容。
请确保每个步骤内容详实、逻辑清晰，便于教师和学生直接参考。
如遇专业知识点或不确定内容，优先调用 rag_tool 检索知识库，必要时使用 search 搜索外部资料。
如涉及数学或计算问题，可调用 math_tool 进行辅助。
如涉及代码生成问题，可调用 code_generate_tool 进行辅助。
如涉及代码验证问题，可调用 code_validate_tool 进行辅助。
输出内容应聚焦于教学本身，避免涉及管理流程或平台操作。
需使用 markdown 标题（### 步骤名）表明当前步骤，标题应简短明了。
正文用简洁明了的语言，适当包含代码示例、注意事项或操作要点。
不需要出现练习题。
如有必要，可补充背景知识或关键概念说明，但避免冗余。
""",
)

import asyncio


async def execute_parallel_step(state: PlanExecutionState, config) -> Dict:
    """
    Execute a parallel step in the lesson plan.
    :param state:
    :param config:
    :return:
    """
    parallel_plan = state["parallel_plan"]
    if not parallel_plan:
        return {"past_steps": []}

    child_config = {"configurable": config.get("configurable", {})}
    tasks = []
    completed_steps = (
        [f"{step[0]}:\n\n{step[2]}" for step in state["past_steps"]]
        if state["past_steps"]
        else []
    )
    for task in parallel_plan:
        task_formatted = f"""已完成内容：{completed_steps or 'null'}
针对以下计划：{task}\n\n你需要执行此步骤：{task}。"""

        async def run_with_summary(task=task, task_formatted=task_formatted):
            result = await execution_agent.ainvoke(
                {"messages": [("user", task_formatted)]}, child_config
            )
            detail = result["messages"][-1].content
            summary = await summarize_step(detail)
            return (task, detail, summary)

        tasks.append(run_with_summary())

    past_steps = await asyncio.gather(*tasks)
    return {
        "past_steps": past_steps,
    }


async def execute_after_parallel_step(state: PlanExecutionState, config) -> Dict:
    """
    Execute a sequential step in the lesson plan.
    :param state:
    :param config:
    :return:
    """
    after_parallel_plan = state["after_parallel_plan"]
    if not after_parallel_plan:
        return {"past_steps": []}

    child_config = {"configurable": config.get("configurable", {})}
    task = after_parallel_plan[0]
    completed_steps = (
        [f"{step[0]}:\n\n{step[2]}" for step in state["past_steps"]]
        if state["past_steps"]
        else []
    )
    task_formatted = f"""
针对以下计划：{task}\n\n你需要执行此步骤：{task}。
这是前面的历史步骤和结果：
{completed_steps or 'null'}
"""
    agent_response = await execution_agent.ainvoke(
        {"messages": [("user", task_formatted)]}, child_config
    )
    detail = agent_response["messages"][-1].content
    summary = await summarize_step(detail)

    return {"past_steps": [(task, detail, summary)]}


# writer = init_chat_model(
#     model="deepseek-v3",
#     model_provider="openai",
#     temperature=0,
#     # extra_body={"enable_thinking": False},
#     api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
#     # rate_limiter=rate_limiter,
#     base_url=os.getenv(
#         "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
#     ),
# )


async def write_lesson_plan(state: PlanExecutionState, config) -> Dict:
    """
    Write the lesson plan based on all past steps
    """
    steps = state.get("past_steps", [])
    # 只取详细内容部分
    final_resp = "\n\n".join([f"{step[1]}" for step in steps])
    return {"response": final_resp}


def build_lesson_planner():
    workflow = StateGraph(PlanExecutionState, ConfigSchema)
    workflow.add_node("planner", plan_step)
    workflow.add_node("classify_task", classify_task_step)
    workflow.add_node("execute_before_parallel_step", execute_before_parallel_step)
    workflow.add_node("execute_parallel_step", execute_parallel_step)
    workflow.add_node("execute_after_parallel_step", execute_after_parallel_step)
    workflow.add_node("write_lesson_plan", write_lesson_plan)
    # workflow.add_node("replanner", replan_step)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "classify_task")
    workflow.add_edge("classify_task", "execute_before_parallel_step")
    workflow.add_edge("execute_before_parallel_step", "execute_parallel_step")
    workflow.add_edge("execute_parallel_step", "execute_after_parallel_step")
    workflow.add_edge("execute_after_parallel_step", "write_lesson_plan")
    workflow.add_edge("write_lesson_plan", END)
    # workflow.add_conditional_edges(
    #     "replanner",
    #     # Next, we pass in the function that will determine which node is called next.
    #     should_end,
    #     ["execute_sequential_step", END],
    # )

    return workflow.compile()
