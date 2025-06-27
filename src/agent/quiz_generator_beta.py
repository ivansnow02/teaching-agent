import json
import os
import re
import struct
from typing import Dict, List, Literal, TypedDict

from langchain_core.output_parsers import JsonOutputParser
from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.graph import StateGraph, END, state
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import StructuredResponseSchema
from enum import Enum
from pydantic import BaseModel, Field

from src.agent import prompt, rag_agent
from src.agent.tools import rag_tool
from src.agent.tools import search

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.25,  # <-- Super slow! We can only make a request once every 10 seconds!!
    check_every_n_seconds=0.1,  # Wake up every 100 ms to check whether allowed to make a request,
    max_bucket_size=10,  # Controls the maximum burst size.
)
llm = init_chat_model(
    model="qwen3-235b-a22b",
    model_provider="openai",
    extra_body={"enable_thinking": False},
    temperature=0,
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    # rate_limiter=rate_limiter,
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)


class ConfigSchema(TypedDict):
    course_id: str


class Option(BaseModel):
    optionLabel: str = Field(description="选项标签")
    optionText: str = Field(description="选项文本")
    isCorrect: bool = Field(description="是否为正确答案")


class QuestionType(str, Enum):
    single_choice = "single_choice"
    multiple_choice = "multiple_choice"
    short_answer = "short_answer"


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Question(BaseModel):
    questionType: QuestionType = Field(description="题目类型")
    questionText: str = Field(description="题目文本")
    difficulty: Difficulty = Field(description="题目难度")
    options: List[Option] = Field(description="题目选项")
    correctAnswer: str = Field(description="正确答案")
    answerExplanation: str = Field(description="答案解析")


class Quiz(BaseModel):
    questions: List[Question] = Field(description="题目列表")


class QuestionForm(BaseModel):
    questionType: QuestionType = Field(description="题目类型")
    knowledgePoints: str = Field(description="知识点列表")
    difficulty: Difficulty = Field(description="题目难度")


class QuizPlan(BaseModel):
    questions: List[QuestionForm] = Field(description="题目列表")


class QuizState(TypedDict):
    requirements: str

    plan: QuizPlan

    single_questions_plan: QuizPlan
    multiple_questions_plan: QuizPlan
    short_answer_questions_plan: QuizPlan

    quiz: Quiz


async def quiz_planner(
    state: QuizState,
    config,
) -> Dict:
    """
    Generate a quiz plan based on the requirements
    """

    requirements = state["requirements"]

    prompt = f"""
你是一个出题规划者，帮助老师出一份测验卷。请根据要求生成**题目生成计划**：

请严格按照以下 JSON 格式输出，不要包含任何解释、注释或Markdown标记外的任何文本。

使用rag_tool工具获取知识点信息，使知识点均匀分布到每个题目，每个题目的知识点需要相关，确保每个知识点至少出现在一个题目中。

注意：knowledgePoints 字段必须是字符串，可用逗号隔开。
difficulty 字段必须是字符串，表示题目的难度等级，可选值只能为 easy、medium、hard。
questionType 字段必须是字符串，表示题目的类型，可选值只能为 single_choice、multiple_choice、short_answer。
你只能使用以下字段，不要擅自加上其他内容：

- questionType
- knowledgePoints
- difficulty

示例：
```json
{{QuizPlan.model_json_schema()}}
```
"""

    # structured_llm = llm.with_structured_output(QuizPlan)

    # resp = await structured_llm.ainvoke(prompt)

    planner = create_react_agent(
        model=llm,
        tools=[rag_tool, search],
        prompt=prompt,
    )

    resp = await planner.ainvoke({"messages": [("user", requirements)]}, config)
    # output parse
    json_parser = JsonOutputParser(pydantic_object=QuizPlan)
    try:
        plan = json_parser.parse(resp["messages"][-1].content)
        # 兼容 LLM 返回 {"QuizPlan": [...]}
        if isinstance(plan, dict) and "QuizPlan" in plan:
            plan = QuizPlan(questions=plan["QuizPlan"])
    except Exception as e:
        print(f"解析失败: {e}")
        return {"plan": QuizPlan(questions=[])}
    return {"plan": plan}


async def quiz_classifier(state: QuizState) -> Dict:
    """Classify the quiz plan into different types of questions"""
    # 兼容 dict 类型
    if isinstance(state["plan"], dict):
        state["plan"] = QuizPlan(**state["plan"])
    single_questions = []
    multiple_questions = []
    short_answer_questions = []

    for question in state["plan"].questions:
        if question.questionType == QuestionType.single_choice:
            single_questions.append(question)
        elif question.questionType == QuestionType.multiple_choice:
            multiple_questions.append(question)
        elif question.questionType == QuestionType.short_answer:
            short_answer_questions.append(question)

    return {
        "single_questions_plan": QuizPlan(questions=single_questions),
        "multiple_questions_plan": QuizPlan(questions=multiple_questions),
        "short_answer_questions_plan": QuizPlan(questions=short_answer_questions),
    }


writer = create_react_agent(
    model=llm,
    tools=[rag_tool, search],
    prompt="""你是测验卷出题助手，根据题目生成计划为老师生成结构化、标准化的测验题目。
要求：
- 内容准确、清晰，题干简明，选项合理，答案唯一且有解析。
- 如遇专业知识点或不确定内容，优先调用 rag_tool 检索知识库。
- 输出仅限测验内容，避免无关信息。
- 每题包含字段：
  - questionType（题目类型）
  - questionText（题干）
  - difficulty（难度）
  - options（选项，单/多选题必填，简答题可为空）
  - correctAnswer（正确答案，单/多选为选项标签，简答题为参考答案）
  - answerExplanation（答案解析）
- 选择题选项用 A/B/C/D 标签，单选仅一个正确答案，多选可多个。
- 简答题需给出参考答案和简明解析。
- 输出严格为 JSON 格式，不含 Markdown 标记或多余解释。
- 如需补充背景知识，仅限答案解析，且应简明扼要。

**示例输出：**
```json
{{
"questionType": "single_choice",
"questionText": "在计算机图形学中，将三维坐标转换为二维屏幕坐标的过程称为？",
"difficulty": "easy",
"options": [
{{
    "optionLabel": "A",
    "optionText": "投影变换",
    "optionOrder": 1,
    "isCorrect": true
}},
{{
    "optionLabel": "B",
    "optionText": "视口变换",
    "optionOrder": 2,
    "isCorrect": false
}},
{{
    "optionLabel": "C",
    "optionText": "模型变换",
    "optionOrder": 3,
    "isCorrect": false
}},
{{
    "optionLabel": "D",
    "optionText": "观察变换",
    "optionOrder": 4,
    "isCorrect": false
}}
],
"correctAnswer": "A",
"answerExplanation": "投影变换是将三维场景投射到二维屏幕上的过程，包括透视投影和正交投影两种方式。"
}},
{{
"questionType": "multiple_choice",
"questionText": "正交投影的特点包括：",
"difficulty": "medium",
"options": [
{{
    "optionLabel": "A",
    "optionText": "平行线在投影后仍然平行",
    "optionOrder": 1,
    "isCorrect": true
}},
{{
    "optionLabel": "B",
    "optionText": "物体大小不随距离变化",
    "optionOrder": 2,
    "isCorrect": true
}},
{{
    "optionLabel": "C",
    "optionText": "适用于工程制图和CAD系统",
    "optionOrder": 3,
    "isCorrect": true
}},
{{
    "optionLabel": "D",
    "optionText": "有明显的透视效果",
    "optionOrder": 4,
    "isCorrect": false
}}
],
"correctAnswer": "A,B,C",
"answerExplanation": "正交投影保持平行线平行，物体大小不随距离变化，常用于需要精确尺寸的工程制图。"
}},
{{
"questionType": "short_answer",
"questionText": "请简述透视投影和正交投影的主要区别，并说明它们各自适用的场景。",
"difficulty": "hard",
"options": [],
"correctAnswer": "透视投影：模拟人眼观察方式，远处物体看起来更小，有消失点，平行线会相交，适用于游戏、虚拟现实等需要真实感的场景。正交投影：物体大小不随距离变化，平行线保持平行，不会产生近大远小的效果，适用于CAD、工程制图等需要保持精确测量和比例的场景。",
"answerExplanation": "两种投影方式各有特点和适用场景，理解它们的区别对于选择合适的投影方式很重要。"
}}
```
""",
)


import asyncio


async def quiz_generator(state: QuizState, config) -> Dict:
    """
    Parallel quiz generation for different question types
    """

    async def generate_questions(plan: QuizPlan) -> List[Question]:
        # 兼容 dict 类型
        if isinstance(plan, dict):
            plan = QuizPlan(**plan)
        if not plan.questions:
            return []

        async def generate_question(
            q: QuestionForm, questionType: QuestionType
        ) -> Dict:
            question_type_str = ""
            if questionType == QuestionType.single_choice:
                question_type_str = f"""请根据以下单选题的生成计划生成单选题："""
            elif questionType == QuestionType.multiple_choice:
                question_type_str = f"""请根据以下多选题的生成计划生成多选题："""
            elif questionType == QuestionType.short_answer:
                question_type_str = f"""请根据以下简答题的生成计划生成简答题："""
            response = await writer.ainvoke(
                {
                    "messages": [
                        (
                            "user",
                            question_type_str
                            + f"""\n\n{json.dumps(q.model_dump())}
输出格式必须为 JSON 格式，不要包含 Markdown 标记或多余解释。
**示例**
```json
{{Question.model_json_schema()}}
```
""",
                        )
                    ]
                },
                config,
            )
            json_parser = JsonOutputParser(pydantic_object=Question)
            return json_parser.parse(response["messages"][-1].content)

        tasks = []
        for question in plan.questions:
            tasks.append(generate_question(question, question.questionType))

        results = await asyncio.gather(*tasks)

        return results

    single_questions = await generate_questions(state["single_questions_plan"])
    multiple_questions = await generate_questions(state["multiple_questions_plan"])
    short_answer_questions = await generate_questions(
        state["short_answer_questions_plan"]
    )

    return {"quiz": single_questions + multiple_questions + short_answer_questions}


async def build_quiz_planner_v2():
    workflow = StateGraph(QuizState, ConfigSchema)

    workflow.add_node("quiz_planner", quiz_planner)

    workflow.set_entry_point("quiz_planner")

    workflow.add_node("quiz_classifier", quiz_classifier)
    workflow.add_edge("quiz_planner", "quiz_classifier")

    workflow.add_node("quiz_generator", quiz_generator)
    workflow.add_edge("quiz_classifier", "quiz_generator")

    workflow.add_edge("quiz_generator", END)

    return workflow.compile()
