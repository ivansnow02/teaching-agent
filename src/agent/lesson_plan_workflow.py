import ast
import asyncio
import json
import logging
import os
import re
from typing import Dict, List, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.graph.graph import CompiledGraph
from pydantic import BaseModel, Field

from src.agent import quiz_generator, rag_agent

# 注意：由于我们直接在代码中定义了更健壮的prompt，以下导入将不再被使用，但暂时保留以供参考
# from src.agent.prompt import FINAL_PLAN_COMPILER_PROMPT, SYLLABUS_PARSE_PROMPT, TIME_ALLOCATOR_PROMPT

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.25,  # <-- Super slow! We can only make a request once every 10 seconds!!
    check_every_n_seconds=0.1,  # Wake up every 100 ms to check whether allowed to make a request,
    max_bucket_size=10,  # Controls the maximum burst size.
)
llm = init_chat_model(
    model="qwen3-235b-a22b",
    model_provider="openai",
    temperature=0,
    extra_body={"enable_thinking": False},
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    # rate_limiter=rate_limiter,
    base_url=os.getenv("DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
)


class ConfigSchema(TypedDict):
    course_id: str


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


    # num_choice_questions: int  # 需要生成的选择题数量
    # num_short_answer_questions: int  # 需要生成的简答题数量
    # num_true_or_false_questions: int  # 需要生成的是非题数量

    # 中间处理数据
    parsed_syllabus: List[Dict]
    current_chapter_index: int
    chapter_results: List[Dict]

    # 最终输出
    final_lesson_plan: str


def _parse_llm_json_output(json_string: str) -> List:
    """
    健壮地解析来自LLM输出的JSON字符串。
    处理markdown代码块，并回退到ast.literal_eval。
    """
    # 尝试直接在字符串中找到JSON数组
    match = re.search(r'\[.*\]', json_string, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass  # 如果失败，则继续尝试其他方法

    # 尝试清理markdown并再次解析
    try:
        cleaned_string = re.sub(r"^```[a-zA-Z]*\n?|```$", "", json_string.strip())
        return json.loads(cleaned_string)
    except json.JSONDecodeError:
        pass

    # 回退到ast.literal_eval
    try:
        return ast.literal_eval(json_string)
    except (ValueError, SyntaxError) as e:
        logging.error(f"无法从LLM输出中解析JSON/列表: {json_string}. 错误: {e}")
        return []  # 返回空列表以避免整个过程崩溃


def parse_syllabus(state: LessonPlanState) -> Dict:
    """
    解析原始的大纲字符串，转换为结构化的章节列表。
    """
    raw_syllabus = state['raw_syllabus']
    structured_llm = llm.with_structured_output(SyllabusStructure)
    try:
        # 优化：使用更明确的Prompt来指导模型
        prompt = (
            "你是一个教学大纲解析专家。你的任务是从用户提供的原始文本中，提取出结构化的课程大纲。\n"
            "你必须严格按照定义的 JSON 格式输出，不要添加任何解释、注释或 markdown 标记。\n"
            "JSON 结构如下:\n"
            "{\n"
            "  \"chapters\": [\n"
            "    {\n"
            "      \"chapter_title\": \"<章节标题>\",\n"
            "      \"knowledge_points\": [\"<知识点1>\", \"<知识点2>\"]\n"
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"请解析以下大纲内容：\n---\n{raw_syllabus}\n---"
        )
        structured_syllabus = structured_llm.invoke(prompt)
        parsed_data = [chapter.dict() for chapter in structured_syllabus.chapters]
        logging.info(f"解析后的大纲: {parsed_data}")
        return {
            'parsed_syllabus'      : parsed_data,
            'current_chapter_index': 0,
            'chapter_results'      : []
        }
    except Exception as e:
        logging.error(f"解析大纲失败: {e}")
        # 返回一个空结构，以防止工作流崩溃
        return {
            'parsed_syllabus'      : [],
            'current_chapter_index': 0,
            'chapter_results'      : []
        }


async def generate_chapter_content(state: LessonPlanState, config) -> Dict:
    """
    为当前章节生成内容，增加了错误处理和回退机制。
    此函数现在是“纯”的，只返回其工作结果，不修改传入的状态。
    """
    idx = state['current_chapter_index']
    chapter_info = state['parsed_syllabus'][idx]
    chapter_title = chapter_info['chapter_title']
    knowledge_points = chapter_info['knowledge_points']
    logging.info(f"正在为章节 {idx} 生成内容: {chapter_title}")

    # 1. 生成知识点讲解 (带容错)
    explanations = []
    try:
        # 优化：使用更明确的Prompt来指导模型
        prompt = (
            "你是一个内容生成助手。你的唯一任务是为给定的知识点列表生成讲解内容，并以严格的 JSON 格式返回。\n"
            "你的输出必须是一个 JSON 数组，数组中的每个元素都是一个字符串，对应一个知识点的讲解。\n"
            "绝对不能包含任何 markdown 标记 (如 ```json), 解释性文字, 或任何非 JSON 内容。\n\n"
            f"课程章节: 《{chapter_title}》\n"
            f"请为以下知识点列表生成讲解内容: {knowledge_points}\n\n"
            "--- 示例输出格式 ---\n"
            "[\"关于知识点1的详细讲解...\", \"关于知识点2的详细讲解...\", \"关于知识点3的详细讲解...\"]\n"
            "--- 要求 ---\n"
            "1. 内容精准、专业，面向大学生。\n"
            "2. 讲解内容应直接、简洁，不要包含开场白或总结。\n"
            "3. 数组元素的数量必须与知识点列表的数量完全一致。"
        )
        rag_graph = await rag_agent.make_graph()
        response = await rag_graph.ainvoke({"messages": [
            {"role": "user", "content": prompt}, ],
            "max_rewrite"                             : 3,
            "rewrite_count"                           : 0,

        }, config)
        explanations_str = response["messages"][-1].content
        explanations = _parse_llm_json_output(explanations_str)
        if not explanations or len(explanations) != len(knowledge_points):
            logging.warning(f"为章节 {chapter_title} 解析讲解内容失败或数量不匹配。")
            raise ValueError("解析讲解内容失败")
    except Exception as e:
        logging.error(f"为章节 {chapter_title} 生成讲解内容时出错: {e}")
        explanations = [f"知识点 '{kp}' 的讲解生成失败。" for kp in knowledge_points]

    # 2. 生成练习题 (带容错)
    quiz_result = {}
    try:
        content = (
                f"章节标题: {chapter_title}\n\n"
                "以下是本章节的核心知识点及讲解内容：\n" +
                "\n".join(
                    f"- {point}：{explanation}" for point, explanation in zip(knowledge_points, explanations)) + "\n\n")
        # 注意：如果quiz_generator中也存在不稳定的LLM调用，其prompt也需要按类似方式进行优化
        quiz_graph = quiz_generator.build_quiz_workflow()
        quiz_state = {
            'content'                    : content,
            'num_choice_questions'       : state['num_choice_questions'],
            'num_short_answer_questions' : state['num_short_answer_questions'],
            'num_true_or_false_questions': state['num_true_or_false_questions'],
        }
        quiz_result = await quiz_graph.ainvoke(quiz_state, config)
    except Exception as e:
        logging.error(f"为章节 {chapter_title} 生成练习题时出错: {e}")
        quiz_result = {"practice_exercises": "练习题生成失败。"}

    # 3. 分配时间 (带容错)
    time_allocation_dict = {}
    try:
        content_for_analysis = (
                f"章节标题: {chapter_title}\n\n"
                "### 核心知识点讲解:\n" +
                "\n".join(f"- {point}: {explanation}" for point, explanation in zip(knowledge_points, explanations)) +
                "\n\n### 配套练习题:\n" + str(quiz_result.get("practice_exercises", ""))
        )
        time_llm = llm.with_structured_output(TimeAllocation)
        # 修复：使用更强大、更明确的提示词，强制模型遵循JSON格式和字段名。
        prompt_for_time = (
            "你是一个教学计划助手，专门负责为课程章节评估和分配时间。\n"
            "你的任务是分析给定的章节内容（包括知识点讲解和练习题），然后输出一个结构化的时间分配方案。\n\n"
            "你必须严格按照以下 JSON 格式进行输出。你的整个输出必须是一个单独的、不包含任何其他文本的 JSON 对象。\n"
            "绝对不允许使用中文键名，必须使用下面指定的英文键名：`activities`, `name`, `minutes`, `rationale`。\n\n"
            "--- JSON 输出格式定义 ---\n"
            "{\n"
            "  \"activities\": [\n"
            "    {\"name\": \"<字符串，活动1的名称>\", \"minutes\": <整数，活动1的分钟数>},\n"
            "    {\"name\": \"<字符串，活动2的名称>\", \"minutes\": <整数，活动2的分钟数>}\n"
            "  ],\n"
            "  \"rationale\": \"<字符串，你做出此时间分配的简要理由>\"\n"
            "}\n\n"
            "--- 待分析的章节内容 ---\n"
            f"{content_for_analysis}\n\n"
            "--- 你的任务 ---\n"
            "请根据以上内容，生成时间分配的 JSON 对象。"
        )
        time_allocation_result = await time_llm.ainvoke(prompt_for_time)
        time_allocation_dict = time_allocation_result.model_dump()
    except Exception as e:
        logging.error(f"为章节 {chapter_title} 计算时间分配时出错: {e}")
        time_allocation_dict = {
            "activities": [{"name": "错误", "minutes": 0}],
            "rationale" : "时间分配生成失败。"
        }

    # 4. 组合并返回单个章节的结果
    result = {
        'chapter_title': chapter_title,
        'knowledge': [{'knowledge_point': point, 'explation': explanation} for point, explanation in
                      zip(knowledge_points, explanations)],
        'quiz'     : quiz_result.get("practice_exercises", {}),
        'time_allocation': time_allocation_dict
    }
    return result


async def generate_all_chapters(state: LessonPlanState, config):
    """
    并发生成所有章节内容，并处理单个任务的失败。
    """
    parsed_syllabus = state['parsed_syllabus']
    if not parsed_syllabus:
        logging.warning("大纲为空，跳过章节内容生成。")
        return {'chapter_results': [], 'current_chapter_index': 0}

    tasks = []
    for idx, chapter in enumerate(parsed_syllabus):
        # 创建一个独立的 state 副本给每个任务
        # 注意：state.copy() 是浅拷贝，但对于此处的用法是安全的，
        # 因为 generate_chapter_content 不再修改共享的列表。
        chapter_state = state.copy()
        chapter_state['current_chapter_index'] = idx
        tasks.append(generate_chapter_content(chapter_state, config))

    # 使用 return_exceptions=True 来防止一个失败的任务中断所有任务
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 正确地处理和收集结果
    final_chapter_results = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            chapter_title = parsed_syllabus[i].get('chapter_title', f'章节 {i + 1}')
            logging.error(f"处理章节 '{chapter_title}' 的任务失败: {res}")
            # 可选：可以添加一个失败的占位符，以便在最终报告中看到
            final_chapter_results.append({
                "chapter_title"  : f"{chapter_title} (处理失败)",
                "knowledge"      : [],
                "quiz"           : "生成失败",
                "time_allocation": {},
                "error"          : str(res)
            })
        elif isinstance(res, dict):
            # res 现在是单个章节的独立结果字典
            final_chapter_results.append(res)
        else:
            chapter_title = parsed_syllabus[i].get('chapter_title', f'章节 {i + 1}')
            logging.warning(f"处理章节 '{chapter_title}' 的任务返回了意外的结果: {res}")

    return {
        'chapter_results'      : final_chapter_results,
        'current_chapter_index': len(parsed_syllabus)  # 更新索引以表示所有章节已处理
    }


def decide_next_step(state: LessonPlanState) -> str:
    """此函数在新的并行流程中不再需要，但保留以供参考。"""
    if state['current_chapter_index'] < len(state['parsed_syllabus']):
        return "continue_processing"
    else:
        return "finalize"


async def finalize_plan(state: LessonPlanState) -> Dict:
    """汇总所有章节的内容，生成最终的教案（md），增加容错。"""
    chapter_results = state['chapter_results']
    if not chapter_results:
        logging.warning("没有可供最终化的章节结果。")
        return {"final_lesson_plan": "# 教案生成失败\n\n由于未能成功处理任何章节，无法生成最终教案。"}

    raw_plan = "\n\n---\n\n".join(
        f"## {result.get('chapter_title', '未知章节')}\n\n"
        f"### 知识点讲解:\n" +
        "\n".join(
            f"- **{kp.get('knowledge_point', 'N/A')}**: {kp.get('explation', 'N/A')}"
            for kp in result.get('knowledge', [])
        ) +
        f"\n\n### 练习题:\n"
        f"```json\n{json.dumps(result.get('quiz', {}), ensure_ascii=False, indent=2)}\n```" +
        f"\n\n### 时间分配:\n" +
        "\n".join(
            f"- {activity.get('name', 'N/A')}: {activity.get('minutes', 0)} 分钟"
            for activity in result.get('time_allocation', {}).get('activities', [])
        ) + f"\n*理由: {result.get('time_allocation', {}).get('rationale', 'N/A')}*"
        for result in chapter_results
    )

    try:
        final_llm = init_chat_model(
            model="qwen-plus",
            model_provider="openai",
            temperature=0,
            extra_body={"enable_thinking": False},
            api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
            base_url=os.getenv("DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
        # 优化：使用更明确的Prompt指导最终排版
        prompt = (
            "你是一位专业的教案编辑。你的任务是将一份草稿状态的教案内容进行美化、排版和润色，使其成为一份结构清晰、易于阅读的最终版 Markdown 格式教案。\n\n"
            "--- 排版要求 ---\n"
            "1. 使用 Markdown 格式，整体内容以 `# 课程教案` 作为顶级标题开始。\n"
            "2. 每个章节标题前添加 `---` 分隔线，并使用 `##` (H2) 级别。\n"
            "3. '知识点讲解', '练习题', '时间分配' 等小节使用 `###` (H3) 级别。\n"
            "4. 知识点和时间分配活动使用无序列表 (`-`)。\n"
            "5. 练习题部分，保持其 JSON 代码块格式。\n"
            "6. 语言风格要专业、流畅、精炼。\n\n"
            "--- 原始教案草稿 ---\n"
            f"{raw_plan}\n\n"
            "--- 你的任务 ---\n"
            "请根据以上要求，输出最终美化后的完整教案。"
        )
        result = await final_llm.ainvoke([{"role": "user", "content": prompt}])
        final_content = result.content
    except Exception as e:
        logging.error(f"使用LLM最终化教案失败。将返回原始拼接版本。错误: {e}")
        final_content = "# 最终教案 (原始版)\n\n" + raw_plan

    return {"final_lesson_plan": final_content}


async def build_plan_workflow() -> CompiledGraph:
    """
    构建教案生成工作流。
    流程: 解析大纲 -> 并发生成所有章节内容 -> 最终化教案。
    """
    workflow = StateGraph(LessonPlanState, ConfigSchema)

    workflow.add_node("parse_syllabus", parse_syllabus)
    workflow.set_entry_point("parse_syllabus")

    # 并行处理所有章节
    workflow.add_node("generate_all_chapters", generate_all_chapters)
    workflow.add_edge("parse_syllabus", "generate_all_chapters")

    # 汇总并生成最终计划
    workflow.add_node("finalize_plan", finalize_plan)
    workflow.add_edge("generate_all_chapters", "finalize_plan")
    workflow.add_edge("finalize_plan", END)

    return workflow.compile()
