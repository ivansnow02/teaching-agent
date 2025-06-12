import logging
from typing import Dict, List, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph
from langgraph.graph.graph import CompiledGraph
from pydantic import BaseModel, Field

from src.agent import quiz_generator, rag_agent
from src.agent.prompt import SYLLABUS_PARSE_PROMPT

llm = init_chat_model("google_genai:gemini-2.0-flash")


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


async def generate_chapter_content(state: LessonPlanState) -> Dict:
    """
    为当前章节生成内容。
    """

    idx = state['current_chapter_index']
    chapter_info = state['parsed_syllabus'][idx]
    chapter_title = chapter_info['chapter_title']

    logging.info(f"Generating content for chapter: {chapter_title}")

    # 生成知识点讲解
    explanations = []
    for point in chapter_info['knowledge_points']:
        prompt = (
            f"你是一位资深的课程内容撰写者。请为课程《{chapter_title}》"
            f"中的知识点“{point}”撰写一段核心讲解内容。\n"
            "要求如下：\n"
            "1. 内容必须精准、专业，面向大学生。\n"
            "2. 直接开始讲解知识点，不要包含任何开场白、问候语或总结性文字。\n"
            "3. 专注于讲解这一个知识点本身，不要过多发散。\n"
            # "4. 如果适合，可以提供一个简短的代码示例来说明。"
        )
        rag_graph = await rag_agent.make_graph()
        response = await rag_graph.ainvoke({"messages": [
            {
                "role"   : "user",
                "content": prompt,
            }
        ]})

        explanations.append(response["messages"][-1].content)

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
    quiz_result = await quiz_graph.ainvoke(quiz_state)

    # todo 计算时间分配

    result = {
        'chapter_title': chapter_title,
        'knowledge'    : [
            {
                'knowledge_point': point,
                'explation'      : explanation
            } for point, explanation in zip(chapter_info['knowledge_points'], explanations)
        ],
        'quiz'         : quiz_result["practice_exercises"],
    }
    current_results = state['chapter_results']
    current_results.append(result)
    return {"chapter_results": current_results}


async def build_plan_workflow() -> CompiledGraph:
    workflow = StateGraph(LessonPlanState)

    workflow.add_node("parse_syllabus", parse_syllabus)
    workflow.set_entry_point("parse_syllabus")
    workflow.add_node("generate_chapter_content", generate_chapter_content)
    workflow.add_edge("parse_syllabus", "generate_chapter_content")

    return workflow.compile()
