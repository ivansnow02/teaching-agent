import asyncio
import os
from typing import Dict, List, TypedDict

from langchain.chat_models import init_chat_model
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

# --- 1. 常量与配置 ---
SCORE_DIFFERENCE_THRESHOLD = 0.2  # 分数差异阈值，超过此值则需要仲裁

# --- 2. Pydantic 模型定义 ---


# todo: 增加agent调用ragtool
class ConfigSchema(TypedDict):
    course_id: str


class Option(BaseModel):
    optionLabel: str
    optionText: str
    isCorrect: bool


class Question(BaseModel):
    questionType: str
    questionText: str
    difficulty: str
    options: List[Option]
    correctAnswer: str
    answerExplanation: str


class StudentAnswer(BaseModel):
    student_id: str
    answer: str


class DetectedError(BaseModel):
    error_description: str
    correction_suggestion: str


class SingleGradingResult(BaseModel):
    student_id: str
    is_correct: bool
    score: float
    analysis: str
    errors: List[DetectedError]
    reviewer: str  # 标记是哪个评审员（'reviewer_A', 'reviewer_B', 'arbitrator')


class FinalGradingResult(BaseModel):
    student_id: str
    final_score: float
    final_analysis: str
    is_controversial: bool  # 是否经过仲裁


class AggregatedReport(BaseModel):
    common_error_patterns: List[str]
    overall_performance_summary: str
    teaching_suggestions: List[str]


# --- 3. LangGraph 状态定义 ---


class BatchGradingState(TypedDict):
    question: Question
    student_answers: List[StudentAnswer]
    # 中间状态，存储所有评审结果
    review_results: Dict[str, List[SingleGradingResult]]  # key: student_id
    # 最终计分结果
    final_grading_results: List[FinalGradingResult]
    final_report: AggregatedReport


# --- 4. LLM 定义 ---

# 初评员LLM
reviewer_llm = init_chat_model(
    model="qwen-plus",
    model_provider="openai",
    temperature=0.2,  # 稍微增加一点多样性
    extra_body={"enable_thinking": False},
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)

# 仲裁员LLM (更强的模型)
arbitrator_llm = init_chat_model(
    model="qwen-max",
    model_provider="openai",
    temperature=0.0,  # 追求最准确的结果
    extra_body={"enable_thinking": False},
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)

# --- 5. 核心实现 ---


async def grade_answer(
    question: Question, student_answer: StudentAnswer, reviewer_id: str, llm
) -> SingleGradingResult:
    prompt = f"""你是一位严谨、细致、公正的AI助教（角色：{reviewer_id}）。你的任务是根据提供的标准答案和解析，对学生的回答进行自动化批改和分析。

**题目信息:**
- **题干**: {question.questionText}
- **标准答案**: {question.correctAnswer}
- **答案解析**: {question.answerExplanation}

**学生(ID: {student_answer.student_id})的回答:**
---
{student_answer.answer}
---

**批改任务:**
1.  **判断对错**: 确定学生的回答是否完全正确。
2.  **给出分数**: 基于回答的正确性、完整性，给出一个在 [0.0, 1.0] 区间内的浮点数分数。
3.  **错误定位**: 如果回答不完全正确，请精确、具体地指出每一个错误点。
4.  **提供建议**: 针对每一个错误点，给出清晰、有建设性的修正建议。
5.  **总体评价**: 给出一段综合性的评价。

**输出要求:** 必须严格按照以下JSON格式进行响应。
```json
{SingleGradingResult.model_json_schema()}
```"""
    structured_llm = llm.with_structured_output(SingleGradingResult)
    result = await structured_llm.ainvoke(prompt)
    result.student_id = student_answer.student_id
    result.reviewer = reviewer_id
    return result


async def initial_review_node(state: BatchGradingState) -> Dict:
    question = Question.model_validate(state["question"])
    student_answers = [
        StudentAnswer.model_validate(sa) for sa in state["student_answers"]
    ]
    tasks = []
    for answer in student_answers:
        # 每个学生答案都由两位初评员并行批改
        tasks.append(grade_answer(question, answer, "reviewer_A", reviewer_llm))
        tasks.append(grade_answer(question, answer, "reviewer_B", reviewer_llm))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    review_results: Dict[str, List[SingleGradingResult]] = {}
    for res in results:
        if isinstance(res, SingleGradingResult):
            if res.student_id not in review_results:
                review_results[res.student_id] = []
            review_results[res.student_id].append(res)

    return {"review_results": review_results}


async def arbitration_node(state: BatchGradingState) -> Dict:
    question = Question.model_validate(state["question"])
    student_answers = [
        StudentAnswer.model_validate(sa) for sa in state["student_answers"]
    ]
    review_results = state["review_results"]
    student_answers_map = {sa.student_id: sa for sa in student_answers}

    tasks = []
    for student_id, reviews in review_results.items():
        if len(reviews) == 2:
            score_a = reviews[0].score
            score_b = reviews[1].score
            if abs(score_a - score_b) >= SCORE_DIFFERENCE_THRESHOLD:
                # 如果分数差异大，则提交给仲裁员
                tasks.append(
                    grade_answer(
                        question,
                        student_answers_map[student_id],
                        "arbitrator",
                        arbitrator_llm,
                    )
                )

    if not tasks:
        return {}

    arbitration_results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in arbitration_results:
        if isinstance(res, SingleGradingResult):
            review_results[res.student_id].append(res)

    return {"review_results": review_results}


def calculate_final_scores_node(state: BatchGradingState) -> Dict:
    review_results = state["review_results"]
    final_results = []

    for student_id, reviews in review_results.items():
        if len(reviews) == 2:  # 无争议
            final_score = (reviews[0].score + reviews[1].score) / 2
            final_analysis = f"综合意见:\n- 评审A: {reviews[0].analysis}\n- 评审B: {reviews[1].analysis}"
            is_controversial = False
        elif len(reviews) == 3:  # 有争议，已仲裁
            is_controversial = True
            scores = {r.reviewer: r.score for r in reviews}
            s_a, s_b, s_arb = (
                scores["reviewer_A"],
                scores["reviewer_B"],
                scores["arbitrator"],
            )

            # 取与仲裁分数最接近的两个分数的平均值
            if abs(s_a - s_arb) < abs(s_b - s_arb):
                final_score = (s_a + s_arb) / 2
            else:
                final_score = (s_b + s_arb) / 2

            # 最终分析以仲裁员为准
            final_analysis = next(
                r.analysis for r in reviews if r.reviewer == "arbitrator"
            )
        else:  # 数据异常
            continue

        final_results.append(
            FinalGradingResult(
                student_id=student_id,
                final_score=final_score,
                final_analysis=final_analysis,
                is_controversial=is_controversial,
            )
        )

    return {"final_grading_results": final_results}


async def report_generator_node(state: BatchGradingState) -> Dict:
    final_grading_results = state["final_grading_results"]
    question = Question.model_validate(state["question"])
    results_summary = [res.model_dump_json() for res in final_grading_results]

    prompt = f"""你是一位资深的教学分析专家。根据对全班学生针对同一道题的最终批改结果，洞察学情并提供教学建议。

**分析的题目:** {question.questionText}

**全班学生的最终得分与分析摘要:**
---
{results_summary}
---

**分析任务:**
1.  **总结共性错误模式**: 基于学生的最终分析报告，提炼出最普遍的共性错误。
2.  **总结整体表现**: 计算平均分，并对整体表现进行概括性描述。
3.  **提出教学建议**: 基于以上分析，为教师提供具体、可操作的教学建议。

**输出要求:** 必须严格按照以下JSON格式进行响应。
```json
{AggregatedReport.model_json_schema()}
```"""
    structured_llm = arbitrator_llm.with_structured_output(AggregatedReport)
    final_report = await structured_llm.ainvoke(prompt)
    return {"final_report": final_report}


# --- 6. 构建工作流 ---


def build_batch_grading_workflow():
    workflow = StateGraph(BatchGradingState, ConfigSchema)

    workflow.add_node("initial_review", initial_review_node)
    workflow.add_node("arbitration", arbitration_node)
    workflow.add_node("calculate_final_scores", calculate_final_scores_node)
    workflow.add_node("generate_report", report_generator_node)

    workflow.set_entry_point("initial_review")
    workflow.add_edge("initial_review", "arbitration")
    workflow.add_edge("arbitration", "calculate_final_scores")
    workflow.add_edge("calculate_final_scores", "generate_report")
    workflow.add_edge("generate_report", END)

    return workflow.compile()
