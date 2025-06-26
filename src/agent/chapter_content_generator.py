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

from src.agent.tools import calculate_time, count_words, rag_tool


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
每个步骤应该是一个具体的操作，描述了要撰写的内容。

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
    task_formatted = f"""
针对以下计划：{task}\n\n你需要执行此步骤：{task}。
这是前面的历史步骤和结果：
{state["past_steps"] or 'null'}
"""
    agent_response = await execution_agent.ainvoke(
        {"messages": [("user", task_formatted)]}, child_config
    )

    return {
        "past_steps": [(task, agent_response["messages"][-1].content)],
    }


execution_agent = create_react_agent(
    model=executioner,
    tools=[rag_tool, count_words, calculate_time],
    prompt="你是一个教案撰写助手，负责执行教学计划中的步骤。提供的计划内容，撰写相应的任务并返回结果。确保内容至于教案有关，你需要运用rag_tool检索相关知识库，count_words计算生成字数，calculate_time计算内容教授所需时间。\n\n",
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
    for task in parallel_plan:
        task_formatted = f"""针对以下计划：{task}\n\n你需要执行此步骤：{task}。"""
        tasks.append(
            execution_agent.ainvoke(
                {"messages": [("user", task_formatted)]}, child_config
            )
        )

    results = await asyncio.gather(*tasks)
    past_steps = [
        (task, result["messages"][-1].content)
        for task, result in zip(parallel_plan, results)
    ]

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
    task_formatted = f"""
针对以下计划：{task}\n\n你需要执行此步骤：{task}。
这是前面的历史步骤和结果：
{state["past_steps"] or 'null'}
"""
    agent_response = await execution_agent.ainvoke(
        {"messages": [("user", task_formatted)]}, child_config
    )

    return {
        "past_steps": [(task, agent_response["messages"][-1].content)],
    }


# async def execute_step(state: PlanExecutionState, config) -> Dict:
#     child_config = {"configurable": config.get("configurable", {})}

#     plan = state["plan"]
#     plan_str = "\n".join(f"{i+1}. {step}" for i, step in enumerate(plan))
#     task = plan[0]
#     task_formatted = f"""针对以下计划：{plan_str}\n\n你需要执行第{1}步：{task}。"""
#     agent_response = await execution_agent.ainvoke(
#         {"messages": [("user", task_formatted)]}, child_config
#     )
#     return {
#         "past_steps": [(task, agent_response["messages"][-1].content)],
#     }


# async def replan_step(state: PlanExecutionState, config) -> Dict:
#     """
#     Replan the lesson plan based on the current state and configuration.
#     :param state:
#     :param config:
#     :return:
#     """

#     prompt = f"""
# 你是一个教案生成专家。请根据以下信息重新规划教案。
# 你只能在需要时添加新的步骤，而不是修改或删除现有步骤。
# 确保步骤专注于教案的生成，而不是其他任务。

# **原始目标**:
# {state['raw_syllabus']}

# **已完成的步骤和结果**:
# {state["past_steps"] or 'null'}

# **剩余的计划**:
# {state["sequential_plan"] or 'null'}

# **决策时间**:
# 请严格按照以下JSON格式进行响应，不要包含任何其他文本。
# {Act.model_json_schema()}
# 请根据当前进展更新你的计划。如果不再需要更多步骤并且可以直接回复用户，请直接返回结果。否则，请填写接下来的计划。只需添加仍需完成的步骤，不要将已完成的步骤再次作为计划返回。
# """

#     structured_llm = planner.with_structured_output(Act)
#     result = await structured_llm.ainvoke(prompt)
#     if isinstance(result.action, Response):
#         return {"response": result.action.response}
#     else:
#         return {"plan": result.action.steps}


# def should_end(state: PlanExecutionState):
#     if "response" in state and state["response"]:
#         return END
#     else:
#         return "execute_sequential_step"


async def write_lesson_plan(state: PlanExecutionState, config) -> Dict:
    """
    Write the lesson plan based on all past steps
    """
    past_steps = state["past_steps"]
    if not past_steps:
        return {"response": "没有可用的步骤来生成教案。"}

    # 将所有步骤合并为一个字符串
    steps_str = "\n".join(
        f"{i+1}. {step[0]}: \n\n{step[1]}\n\n" for i, step in enumerate(past_steps)
    )

    prompt = f"""你是一个教案撰写专家。请根据以下步骤生成完整的教案内容

{steps_str}
请确保内容清晰、连贯，并符合教学目标，不要减少任何步骤或内容。
"""

    result = await planner.ainvoke(prompt)
    return {
        "response": result,
    }


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
