import json
import os
from typing import Dict, List, Literal, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.rate_limiters import InMemoryRateLimiter
from langgraph.graph import StateGraph
from langgraph.graph.graph import CompiledGraph
from pydantic import BaseModel, Field

from src.agent import rag_agent

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
    distractors: List[str] = Field(
        description="一个包含多个看起来合理但错误的选项的列表"
    )
    answer: str = Field(description="正确答案")


class ShortAnswerQuestion(BaseModel):
    """定义单个简答题的结构"""

    question: QuestionStem = Field(description="问题题干")
    reference_answer: str = Field(description="参考答案")


class PracticeExercises(BaseModel):
    """定义一套练习题的完整结构"""

    multiple_choice: List[MultipleChoiceQuestion] = Field(description="选择题列表")
    short_answer: List[ShortAnswerQuestion] = Field(description="简答题列表")
    true_or_false: List["TOrFQuestion"] = Field(description="是非题列表")


class DistractorOptions(BaseModel):
    """为选择题的正确答案生成干扰项"""

    distractors: List[str] = Field(
        description="一个包含多个看起来合理但错误的干扰选项的列表"
    )


class TOrFQuestion(BaseModel):
    """定义单个是非题的结构"""

    question: QuestionStem = Field(description="问题题干")
    answer: bool = Field(description="正确答案，True表示正确，False表示错误")


def create_quiz_stems(state: QuizState) -> Dict:
    content = state["content"]
    num_choice_questions = state["num_choice_questions"]
    num_short_answer_questions = state["num_short_answer_questions"]
    num_true_or_false_questions = state["num_true_or_false_questions"]

    prompt = f"""你是一个出题机器人。根据以下内容，生成一个包含三种类型题干的 JSON 对象。

### 参考内容
---
{content}
---

### 任务
1.  生成 {num_choice_questions} 个选择题题干。
2.  生成 {num_short_answer_questions} 个简答题题干。
3.  生成 {num_true_or_false_questions} 个是非题题干。
4.  对于每个题干，提取相关的知识点。`knowledge_points` 字段必须是一个字符串列表。

### JSON 输出格式
你必须严格按照以下 JSON 结构输出。顶层元素必须是一个 JSON 对象，而不是列表。
```json
{{
  "choice_questions": [
    {{
      "question": "<字符串 - 选择题题干>",
      "knowledge_points": ["<字符串 - 知识点A>", "<字符串 - 知识点B>"]
    }}
  ],
  "short_questions": [
    {{
      "question": "<字符串 - 简答题题干>",
      "knowledge_points": ["<字符串 - 知识点C>"]
    }}
  ],
  "true_or_false_questions": [
    {{
      "question": "<字符串 - 是非题题干>",
      "knowledge_points": ["<字符串 - 知识点D>"]
    }}
  ]
}}
```
### 参考内容
{content}
请严格按照上述指令和格式，生成所需的 json 输出。 """

    # 定义批量结构
    class AllStems(BaseModel):
        choice_questions: List[QuestionStem]
        short_questions: List[QuestionStem]
        true_or_false_questions: List[QuestionStem]

    response = llm.with_structured_output(AllStems).invoke(
        [{"role": "user", "content": prompt}]
    )
    return {
        "choice_stems": response.choice_questions,
        "short_stems": response.short_questions,
        "true_or_false_stems": response.true_or_false_questions,
    }


def check_choice_stems(
    state: QuizState,
) -> Literal["create_quiz_stems", "generate_all_answers"]:
    """
    检查选择题题干是否符合要求，若不符合，则重新生成缺失的题干。
    """
    choice_stems = state["choice_stems"]
    num_choice_questions = state["num_choice_questions"]
    num_ch = num_choice_questions - len(choice_stems)

    short_stems = state["short_stems"]
    num_short_answer_questions = state["num_short_answer_questions"]
    num_sh = num_short_answer_questions - len(short_stems)

    true_or_false_stems = state["true_or_false_stems"]
    num_true_or_false_questions = state["num_true_or_false_questions"]
    num_tf = num_true_or_false_questions - len(true_or_false_stems)

    # 如果选择题、简答题或是非题的超过，则截断
    if num_ch < 0:
        choice_stems = choice_stems[:num_choice_questions]
    if num_sh < 0:
        short_stems = short_stems[:num_short_answer_questions]
    if num_tf < 0:
        true_or_false_stems = true_or_false_stems[:num_true_or_false_questions]

    # 更新状态
    state["choice_stems"] = choice_stems
    state["short_stems"] = short_stems
    state["true_or_false_stems"] = true_or_false_stems
    state["num_choice_questions"] = num_choice_questions
    state["num_short_answer_questions"] = num_short_answer_questions
    state["num_true_or_false_questions"] = num_true_or_false_questions

    if num_ch > 0 or num_sh > 0 or num_tf > 0:
        return "create_quiz_stems"
    else:
        return "generate_all_answers"


async def generate_all_answers(state: QuizState, config) -> Dict:
    choice_stems = state["choice_stems"]
    short_stems = state["short_stems"]
    true_or_false_stems = state["true_or_false_stems"]

    # 为每个题干检索相关内容
    async def enrich_with_context(stems):
        enriched = []
        for stem in stems:
            question = stem.question
            knowledge_points = stem.knowledge_points
            true_prompt = (
                f"请为以下题干检索相关信息：\n"
                f"题干：{question}\n"
                f"相关知识点：{', '.join(knowledge_points)}\n"
            )
            rag_graph = await rag_agent.make_graph()
            response = await rag_graph.ainvoke(
                {
                    "messages": [
                        {"role": "user", "content": true_prompt},
                    ],
                    "max_rewrite": 3,
                    "rewrite_count": 0,
                },
                config,
            )
            context = response["messages"][-1].content
            enriched.append(
                {
                    "question": {
                        "question": stem.question,
                        "knowledge_points": stem.knowledge_points,
                    },
                    "context": context,
                }
            )
        return enriched

    choice_stems_ctx = await enrich_with_context(choice_stems)
    short_stems_ctx = await enrich_with_context(short_stems)
    true_or_false_stems_ctx = await enrich_with_context(true_or_false_stems)

    prompt = "请根据每道题的题干和检索到的相关内容生成答案，输出 JSON，包含 choice_questions、short_questions、true_or_false_questions 三个字段：\n"
    prompt += "choice_questions: 每个元素包含 question, answer（正确选项）, distractors（3个干扰项）所有选项（包括正确答案和干扰项）应简洁明了，长度和风格尽量一致。正确答案只需准确表达核心意思，不要包含过多细节或修饰。\n"
    prompt += "short_questions: 每个元素包含 question, reference_answer\n"
    prompt += "true_or_false_questions: 每个元素包含 question, answer（True/False）\n"

    prompt += "\n【选择题】\n"
    for idx, x in enumerate(choice_stems_ctx):
        prompt += f"{idx + 1}. 题干：{x['question']['question']}，知识点：{', '.join(x['question']['knowledge_points'])}\n相关内容：{x['context']}\n"
    prompt += "\n【简答题】\n"
    for idx, x in enumerate(short_stems_ctx):
        prompt += f"{idx + 1}. 题干：{x['question']['question']}，知识点：{', '.join(x['question']['knowledge_points'])}\n相关内容：{x['context']}\n"
    prompt += "\n【是非题】\n"
    for idx, x in enumerate(true_or_false_stems_ctx):
        prompt += f"{idx + 1}. 题干：{x['question']['question']}，知识点：{', '.join(x['question']['knowledge_points'])}\n相关内容：{x['context']}\n"
    prompt = f"""你是一个专业的出题专家。你的任务是根据提供的题干和相关内容，生成答案和干扰项。
你必须严格按照下面的JSON结构输出，不要包含任何额外的解释或文字。
### JSON 输出结构
```json
{{
  "choice_questions": [
    {{
      "question": {{
        "question": "<字符串 - 问题题干>",
        "knowledge_points": ["<字符串 - 知识点>"]
      }},
      "answer": "<字符串 - 正确答案>",
      "distractors": ["<字符串 - 干扰项1>", "<字符串 - 干扰项2>", "<字符串 - 干扰项3>"]
    }}
  ],
  "short_questions": [
    {{
      "question": {{
        "question": "<字符串 - 问题题干>",
        "knowledge_points": ["<字符串 - 知识点>"]
      }},
      "reference_answer": "<字符串 - 参考答案>"
    }}
  ],
  "true_or_false_questions": [
    {{
      "question": {{
        "question": "<字符串 - 问题题干>",
        "knowledge_points": ["<字符串 - 知识点>"]
      }},
      "answer": <布尔值 - true 或 false, 不是字符串 "true" 或 "false">
    }}
  ]
}}
```

### 输入数据
这是用于生成测验的数据。每个问题都提供了题干和相关内容。


#### 选择题
{json.dumps(choice_stems_ctx, indent=2, ensure_ascii=False)}


#### 简答题
{json.dumps(short_stems_ctx, indent=2, ensure_ascii=False)}


#### 是非题
{json.dumps(true_or_false_stems_ctx, indent=2, ensure_ascii=False)}

现在，请根据提供的输入数据生成最终的 json 输出。"""

    class AllAnswersWithContext(BaseModel):
        choice_questions: List[MultipleChoiceQuestion]
        short_questions: List[ShortAnswerQuestion]
        true_or_false_questions: List[TOrFQuestion]

    response = llm.with_structured_output(AllAnswersWithContext).invoke(
        [{"role": "user", "content": prompt}]
    )

    return {
        "multiple_choice_questions": response.choice_questions,
        "short_answer_questions": response.short_questions,
        "true_or_false_questions": response.true_or_false_questions,
    }


def summarize_practice_exercises(state: QuizState) -> Dict:
    """
    汇总所有生成的练习题，形成最终的练习题结构。
    """
    multiple_choice_questions = state["multiple_choice_questions"]
    short_answer_questions = state["short_answer_questions"]
    true_or_false_questions = state["true_or_false_questions"]

    practice_exercises = PracticeExercises(
        multiple_choice=multiple_choice_questions,
        short_answer=short_answer_questions,
        true_or_false=true_or_false_questions,
    )

    return {"practice_exercises": practice_exercises.model_dump()}


def build_quiz_workflow() -> CompiledGraph:
    workflow = StateGraph(QuizState, config_schema=ConfigSchema)

    workflow.add_node("create_quiz_stems", create_quiz_stems)
    workflow.add_node("generate_all_answers", generate_all_answers)
    workflow.add_node("summarize_practice_exercises", summarize_practice_exercises)

    workflow.set_entry_point("create_quiz_stems")
    workflow.add_conditional_edges("create_quiz_stems", check_choice_stems)
    workflow.add_edge("generate_all_answers", "summarize_practice_exercises")

    return workflow.compile()
