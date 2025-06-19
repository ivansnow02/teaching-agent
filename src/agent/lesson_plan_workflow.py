import json
import logging
import re
from typing import Dict, List, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.graph.graph import CompiledGraph
from pydantic import BaseModel, Field

from src.agent import quiz_generator, rag_agent
from src.agent.prompt import FINAL_PLAN_COMPILER_PROMPT, SYLLABUS_PARSE_PROMPT, TIME_ALLOCATOR_PROMPT
from src.agent.tools import count_words

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.25,  # <-- Super slow! We can only make a request once every 10 seconds!!
    check_every_n_seconds=0.1,  # Wake up every 100 ms to check whether allowed to make a request,
    max_bucket_size=10,  # Controls the maximum burst size.
)
llm = init_chat_model("google_genai:gemini-2.5-flash-lite-preview-06-17", rate_limiter=rate_limiter)


class ConfigSchema(TypedDict):
    user_id: str

class Chapter(BaseModel):
    """定义单个章节的结构"""
    chapter_title: str = Field(description="章节的标题")
    knowledge_points: List[str] = Field(description="章节包含的知识点列表")


class SyllabusStructure(BaseModel):
    """定义整个大纲的结构，它由多个章节组成"""
    chapters: List[Chapter] = Field(description="大纲的章节列表")


class Activity(BaseModel):
    """定义单个教学活动"""
    name: str = Field(description="活动名称, e.g., '理论讲解', '编码实战', '小组讨论'")
    minutes: int = Field(description="建议的分钟数")


class TimeAllocation(BaseModel):
    """定义时间分布的完整结构"""
    activities: List[Activity] = Field(description="一个包含所有教学活动及其建议时间的列表")
    rationale: str = Field(description="给出此时间分配建议的简要理由")


class LessonPlanState(TypedDict):
    """
    定义我们流水线的“状态背包”，它会在所有节点之间传递。
    """
    # 初始输入
    raw_syllabus: str
    # knowledge_base_retriever: Any # 在真实场景中你会传入你的检索器
    num_choice_questions: int  # 需要生成的选择题数量
    num_short_answer_questions: int  # 需要生成的简答题数量
    num_true_or_false_questions: int  # 需要生成的是非题数量

    # 中间处理数据
    parsed_syllabus: List[Dict]
    current_chapter_index: int
    chapter_results: List[Dict]

    # 最终输出
    final_lesson_plan: str


def parse_syllabus(state: LessonPlanState) -> Dict:
    """
    解析原始的大纲字符串，转换为结构化的章节列表。
    """

    raw_syllabus = state['raw_syllabus']

    structured_llm = llm.with_structured_output(SyllabusStructure)

    structured_syllabus = structured_llm.invoke(SYLLABUS_PARSE_PROMPT.format(raw_syllabus=raw_syllabus))

    parsed_data = [chapter.dict() for chapter in structured_syllabus.chapters]

    logging.info(f"Parsed syllabus: {parsed_data}")

    return {
        'parsed_syllabus'      : parsed_data,
        'current_chapter_index': 0,
        'chapter_results'      : []
    }


async def generate_chapter_content(state: LessonPlanState, config) -> Dict:
    """
    为当前章节生成内容。
    """

    idx = state['current_chapter_index']
    chapter_info = state['parsed_syllabus'][idx]
    chapter_title = chapter_info['chapter_title']
    knowledge_points = chapter_info['knowledge_points']

    logging.info(f"Generating content for chapter {idx}: {chapter_title}")
    # 批量生成讲解
    prompt = (
        f"你是一位资深的课程内容撰写者。请为课程《{chapter_title}》"
        f"中的以下知识点分别撰写一段核心讲解内容，"
        "严格输出 JSON 数组，每个元素为字符串，每个字符串为对应知识点的讲解。"
        "不要输出任何解释、注释或 Markdown 代码块标记。\n"
        f"{knowledge_points}\n"
        "示例输出：\n"
        "[\"讲解1\", \"讲解2\", \"讲解3\"]\n"
        "要求：\n"
        "1. 内容精准、专业，面向大学生。\n"
        "2. 直接开始讲解知识点，不要包含开场白、问候语或总结性文字。\n"
        "3. 专注于讲解知识点本身，不要过多发散。\n"
    )
    rag_graph = await rag_agent.make_graph()
    response = await rag_graph.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config
    )
    explanations = response["messages"][-1].content
    # 假设 explanations 是 LLM 返回的字符串
    print(f"Received explanations: {explanations}")
    try:
        explanations_list = json.loads(explanations)
    except json.JSONDecodeError:
        cleaned = re.sub(r"^```[a-zA-Z]*\n?|```$", "", explanations.strip())
        explanations_list = json.loads(cleaned)
    except Exception:
        # 如果不是严格的 JSON，可以用 ast.literal_eval 或正则等方式兜底
        import ast
        explanations_list = ast.literal_eval(explanations)

    # 然后用 explanations_list 替换原有 explanations 变量
    for point, explanation in zip(chapter_info['knowledge_points'], explanations_list):
        if not isinstance(explanation, str):
            raise ValueError(f"Expected explanation for '{point}' to be a string, got {type(explanation)}")
    explanations = explanations_list

    num_choice_questions = state['num_choice_questions']
    num_short_answer_questions = state['num_short_answer_questions']
    num_true_or_false_questions = state['num_true_or_false_questions']

    # 生成题目
    quiz_graph = quiz_generator.build_quiz_workflow()
    content = (
            f"章节标题: {chapter_title}\n\n"
            "以下是本章节的核心知识点及讲解内容：\n" +
            "\n".join(
                f"- {point}：{explanation}"
                for point, explanation in zip(chapter_info['knowledge_points'], explanations)
            ) + "\n\n")

    quiz_state = {
        'content'                    : content,
        'num_choice_questions'       : num_choice_questions,
        'num_short_answer_questions' : num_short_answer_questions,
        'num_true_or_false_questions': num_true_or_false_questions,
    }
    quiz_result = await quiz_graph.ainvoke(quiz_state, config)

    # 1. 准备用于分析的章节内容
    content_for_analysis = (
            f"章节标题: {chapter_title}\n\n"
            "### 核心知识点讲解:\n" +
            "\n".join(
                f"- {point}: {explanation}"
                for point, explanation in zip(chapter_info["knowledge_points"], explanations)
            ) +
            "\n\n### 配套练习题:\n" +
            str(quiz_result["practice_exercises"]) +
            "### 章节字数（非最终）：\n" +
            str(count_words(content + str(quiz_result)))
    )

    # 2. 调用 LLM 进行时间分配
    logging.info(f"Calculating time allocation for chapter: {chapter_title}")

    # 让 LLM 输出结构化的 TimeAllocation 对象
    time_llm = llm.with_structured_output(TimeAllocation)

    time_allocation_result = await time_llm.ainvoke(
        TIME_ALLOCATOR_PROMPT.format(chapter_content_for_analysis=content_for_analysis)
    )

    time_allocation_dict = time_allocation_result.model_dump()

    result = {
        'chapter_title': chapter_title,
        'knowledge'    : [
            {
                'knowledge_point': point,
                'explation'      : explanation
            } for point, explanation in zip(chapter_info['knowledge_points'], explanations)
        ],
        'quiz'         : quiz_result["practice_exercises"],
        'time_allocation': time_allocation_dict
    }
    current_results = state['chapter_results']
    current_results.append(result)
    state['current_chapter_index'] += 1
    return {
        "chapter_results"      : current_results,
        "current_chapter_index": state["current_chapter_index"]
    }


def decide_next_step(state: LessonPlanState) -> str:
    if state['current_chapter_index'] < len(state['parsed_syllabus']):
        return "continue_processing"
    else:
        return "finalize"


async def finalize_plan(state: LessonPlanState) -> Dict:
    """汇总所有章节的内容，生成最终的教案（md）。"""
    chapter_results = state['chapter_results']
    final_lesson_plan = "\n\n".join(
        f"## {result['chapter_title']}\n\n"
        f"### 知识点讲解:\n" +
        "\n".join(
            f"- {kp['knowledge_point']}: {kp['explation']}"
            for kp in result['knowledge']
        ) +
        "\n\n### 练习题:\n" +
        json.dumps(result['quiz'], ensure_ascii=False, indent=2) +  # 用 JSON 格式美化
        "\n\n### 时间分配:\n" +
        "\n".join(
            f"- {activity['name']}: {activity['minutes']} 分钟"
            for activity in result['time_allocation']['activities']
        )
        for result in chapter_results
    )

    final_llm = init_chat_model("google_genai:gemini-2.5-flash", rate_limiter=rate_limiter)

    prompt = FINAL_PLAN_COMPILER_PROMPT + "\n\n" + final_lesson_plan

    result = await final_llm.ainvoke(
        [{"role": "user", "content": prompt}]
    )

    return {"final_lesson_plan": result.content}

async def build_plan_workflow() -> CompiledGraph:
    workflow = StateGraph(LessonPlanState, ConfigSchema)

    workflow.add_node("parse_syllabus", parse_syllabus)
    workflow.set_entry_point("parse_syllabus")
    workflow.add_node("generate_chapter_content", generate_chapter_content)
    workflow.add_edge("parse_syllabus", "generate_chapter_content")
    workflow.add_conditional_edges(
        "generate_chapter_content",
        decide_next_step,
        {"continue_processing": "generate_chapter_content", "finalize": "finalize_plan"},
    )
    workflow.add_node("finalize_plan", finalize_plan)
    workflow.add_edge("finalize_plan", END)


    return workflow.compile()
