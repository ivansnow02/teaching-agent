from typing import Dict, List, Literal, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph
from langgraph.graph.graph import CompiledGraph
from pydantic import BaseModel, Field

from src.agent import rag_agent

llm = init_chat_model("google_genai:gemini-2.0-flash")


class QuestionStem(BaseModel):
    """定义从内容中提取的单个问题题干"""
    question: str = Field(description="根据提供的上下文生成的问题")
    knowledge_points: List[str] = Field(description="从内容中提取的知识点列表")


class QuestionStems(BaseModel):
    """定义从内容中提取的问题题干列表"""
    questions: List[QuestionStem] = Field(description="问题题干列表")


class QuizState(TypedDict):
    """
    定义我们测验生成流水线的状态背包，它会在所有节点之间传递。
    """
    # 初始输入
    content: str  # 输入的内容或文本
    num_choice_questions: int  # 需要生成的选择题数量
    num_short_answer_questions: int  # 需要生成的简答题数量
    num_true_or_false_questions: int  # 需要生成的是非题数量
    # 中间处理数据
    choice_stems: List[dict]  # 从内容中提取的选择题题干列表
    short_stems: List[dict]  # 从内容中提取的简答题题干列表
    true_or_false_stems: List[dict]  # 从内容中提取的是非题题干列表
    distractor_options: List[str]  # 为选择题生成的干扰项
    multiple_choice_questions: List[dict]  # 生成的选择题列表
    short_answer_questions: List[dict]  # 生成的简答题列表
    true_or_false_questions: List[dict]  # 生成的是非题列表
    # 最终输出
    practice_exercises: dict  # 完整的练习题结构


class MultipleChoiceQuestion(BaseModel):
    """定义单个选择题的结构"""
    question: QuestionStem = Field(description="问题题干")
    distractors: List[str] = Field(description="一个包含多个看起来合理但错误的选项的列表")
    answer: str = Field(description="正确答案")


class ShortAnswerQuestion(BaseModel):
    """定义单个简答题的结构"""
    question: QuestionStem = Field(description="问题题干")
    reference_answer: str = Field(description="参考答案")


class PracticeExercises(BaseModel):
    """定义一套练习题的完整结构"""
    multiple_choice: List[MultipleChoiceQuestion] = Field(description="选择题列表")
    short_answer: List[ShortAnswerQuestion] = Field(description="简答题列表")
    true_or_false: List['TOrFQuestion'] = Field(description="是非题列表")


class DistractorOptions(BaseModel):
    """为选择题的正确答案生成干扰项"""
    distractors: List[str] = Field(description="一个包含多个看起来合理但错误的干扰选项的列表")


class TOrFQuestion(BaseModel):
    """定义单个是非题的结构"""
    question: QuestionStem = Field(description="问题题干")
    answer: bool = Field(description="正确答案，True表示正确，False表示错误")


def create_quiz_stems(state: QuizState) -> Dict:
    """
    从输入内容中提取问题题干。
    """
    content = state['content']
    num_choice_questions = state['num_choice_questions']
    num_short_answer_questions = state['num_short_answer_questions']
    num_true_or_false_questions = state['num_true_or_false_questions']

    choice_prompt = (
        "请生成选择题题干：\n"
        f"需要生成的选择题数量：{num_choice_questions}\n"
        "输出格式为JSON，包含一个questions字段，和一个knowledge_points字段，"
        "其中每个问题都是一个字符串，每个知识点都是一个字符串列表。"
        "\n---参考内容---\n"
        f"{content}\n"
    )
    short_prompt = (
        "请生成简答题题干：\n"
        f"需要生成的简答题数量：{num_short_answer_questions}\n"
        "输出格式为JSON，包含一个questions字段，和一个knowledge_points字段，"
        "其中每个问题都是一个字符串，每个知识点都是一个字符串列表。"
        "\n---参考内容---\n"
        f"{content}\n"
    )

    true_or_false_prompt = (
        "请生成是非题题干：\n"
        f"需要生成的是非题数量：{num_true_or_false_questions}\n"
        "输出格式为JSON，包含一个questions字段，和一个knowledge_points字段，"
        "其中每个问题都是一个字符串，每个知识点都是一个字符串列表。"
        "\n---参考内容---\n"
        f"{content}\n"
    )
    # 使用LLM生成选择题题干
    choice_response = llm.with_structured_output(QuestionStems).invoke([{"role": "user", "content": choice_prompt}])
    choice_stems = choice_response.questions

    # 使用LLM生成简答题题干
    short_response = llm.with_structured_output(QuestionStems).invoke([{"role": "user", "content": short_prompt}])
    short_stems = short_response.questions
    # 使用LLM生成是非题题干
    true_or_false_response = llm.with_structured_output(QuestionStems).invoke(
        [{"role": "user", "content": true_or_false_prompt}])
    true_or_false_stems = true_or_false_response.questions

    current_choice_stems = state.get('choice_stems', [])
    current_short_stems = state.get('short_stems', [])
    current_true_or_false_stems = state.get('true_or_false_stems', [])

    # 合并新生成的题干与当前状态中的题干
    choice_stems = current_choice_stems + choice_stems
    short_stems = current_short_stems + short_stems
    true_or_false_stems = current_true_or_false_stems + true_or_false_stems

    return {
        'choice_stems'       : choice_stems,
        'short_stems'        : short_stems,
        'true_or_false_stems': true_or_false_stems,
    }


def check_choice_stems(state: QuizState) -> Literal["create_quiz_stems", "generate_choice_questions"]:
    """
    检查选择题题干是否符合要求，若不符合，则重新生成缺失的题干。
    """
    choice_stems = state['choice_stems']
    num_choice_questions = state['num_choice_questions']
    num_ch = num_choice_questions - len(choice_stems)

    short_stems = state['short_stems']
    num_short_answer_questions = state['num_short_answer_questions']
    num_sh = num_short_answer_questions - len(short_stems)

    true_or_false_stems = state['true_or_false_stems']
    num_true_or_false_questions = state['num_true_or_false_questions']
    num_tf = num_true_or_false_questions - len(true_or_false_stems)

    if num_ch > 0 or num_sh > 0 or num_tf > 0:
        return "create_quiz_stems"
    else:
        return "generate_choice_questions"


async def generate_choice_questions(state: QuizState) -> Dict:
    """
    为选择题生成答案
    """
    choice_stems: QuestionStems = state['choice_stems']
    if not choice_stems:
        return {
            'multiple_choice_questions': [],
        }

    questions = []
    for x in choice_stems:
        stem = x.question
        knowledge_points = x.knowledge_points
        true_prompt = (
            f"请为以下选择题题干生成正确选项：\n"
            f"题干：{stem}\n"
            f"相关知识点：{', '.join(knowledge_points)}\n"
            "只需要提供正确选项，直接返回文本\n"
        )
        rag_graph = await rag_agent.make_graph()
        response = await rag_graph.ainvoke({"messages": [
            {"role": "user", "content": true_prompt}
        ]})
        ans = response["messages"][-1].content

        distractor_prompt = (
            f"请为以下选择题题干生成干扰项：\n"
            f"题干：{stem}\n"
            f"正确选项：{ans}\n"
            f"相关知识点：{', '.join(knowledge_points)}\n"
            "请提供至少3个看起来合理但错误的选项，直接返回文本\n"
        )
        structed_llm = llm.with_structured_output(DistractorOptions)
        distractor_response = structed_llm.invoke([{"role": "user", "content": distractor_prompt}])
        distractors = distractor_response.distractors

        question_data = {
            "question"   : x,
            "distractors": distractors,
            "answer"     : ans,
        }
        questions.append(question_data)
    # 更新状态中的选择题列表
    return {
        'multiple_choice_questions': questions,
    }


async def generate_short_answer_questions(state: QuizState) -> Dict:
    """
    为简答题生成参考答案
    """
    short_stems = state['short_stems']

    if not short_stems:
        return {
            'short_answer_questions': [],
        }

    questions = []
    for x in short_stems:
        stem = x.question
        knowledge_points = x.knowledge_points
        # 将知识点添加到提示中以帮助生成更精确的答案
        prompt = (
            f"请为以下简答题题干生成参考答案：\n"
            f"题干：{stem}\n"
            f"相关知识点：{', '.join(knowledge_points)}\n"
            "请提供一个简洁明了的参考答案，直接返回文本\n"
        )

        rag_graph = await rag_agent.make_graph()
        response = await rag_graph.ainvoke({"messages": [
            {"role": "user", "content": prompt}
        ]})
        ans = response["messages"][-1].content

        # 构建简答题数据，包含知识点
        question_data = {
            "question"        : x,
            "reference_answer": ans,
        }
        questions.append(question_data)

    return {
        'short_answer_questions': questions,
    }


async def generate_true_or_false_questions(state: QuizState) -> Dict:
    """
    为是非题生成答案
    """
    true_or_false_stems = state['true_or_false_stems']
    if not true_or_false_stems:
        return {
            'true_or_false_questions': [],
        }

    questions = []

    for x in true_or_false_stems:
        stem = x.question
        knowledge_points = x.knowledge_points
        prompt = (
            f"请判断以下陈述的真伪。你的回答必须且只能是 'True' 或 'False'，不包含任何其他字符。\n\n"
            f"陈述：'{stem}'"
            f"\n相关知识点：{', '.join(knowledge_points)}\n"
        )
        rag_graph = await rag_agent.make_graph()
        response = await rag_graph.ainvoke({"messages": [
            {"role": "user", "content": prompt}
        ]})
        ans = response["messages"][-1].content.lower() == 'true'

        question_data = {
            "question": x,
            "answer"  : ans
        }
        questions.append(question_data)

    return {
        'true_or_false_questions': questions,
    }


def summarize_practice_exercises(state: QuizState) -> Dict:
    """
    汇总所有生成的练习题，形成最终的练习题结构。
    """
    multiple_choice_questions = state['multiple_choice_questions']
    short_answer_questions = state['short_answer_questions']
    true_or_false_questions = state['true_or_false_questions']

    practice_exercises = PracticeExercises(
        multiple_choice=multiple_choice_questions,
        short_answer=short_answer_questions,
        true_or_false=true_or_false_questions
    )

    return {
        'practice_exercises': practice_exercises.model_dump()
    }


def build_quiz_workflow() -> CompiledGraph:
    workflow = StateGraph(QuizState)

    workflow.add_node("create_quiz_stems", create_quiz_stems)
    workflow.add_node("generate_choice_questions", generate_choice_questions)
    workflow.add_node("generate_short_answer_questions", generate_short_answer_questions)
    workflow.add_node("generate_true_or_false_questions", generate_true_or_false_questions)
    workflow.add_node("summarize_practice_exercises", summarize_practice_exercises)

    workflow.set_entry_point("create_quiz_stems")
    workflow.add_conditional_edges(
        "create_quiz_stems",
        check_choice_stems
    )
    workflow.add_edge("generate_choice_questions", "generate_short_answer_questions")
    workflow.add_edge("generate_short_answer_questions", "generate_true_or_false_questions")
    workflow.add_edge("generate_true_or_false_questions", "summarize_practice_exercises")

    return workflow.compile()
