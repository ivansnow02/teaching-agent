import http
import logging
import math
import os
import re
from typing import List, Optional

import httpx
from langchain.chat_models import init_chat_model
import numexpr
from langchain.chains.openai_functions import create_structured_output_runnable
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_tavily import TavilySearch

from src.agent import rag_agent


async def get_rag_tools(course_id: str = None):
    """
    获取 RAG 工具
    """
    logging.info(f"Retrieving RAG tools for user_id: {course_id}")

    rag_client = MultiServerMCPClient(
        {
            "rag": {
                "command": "uv",
                "args": [
                    "run",
                    "src/agent/mcp/rag_tools.py",
                    "--course-id",
                    f"{course_id}",
                ],
                "transport": "stdio",
            }
        }
    )

    return await rag_client.get_tools()


@tool
async def count_words(text: str) -> int:
    """
    计算文本中的字数
    :param text: 输入文本
    :return: 字数
    """
    if not text:
        return 0
    return len(text.split())


@tool
async def calculate_time(word_count: int, words_per_minute: int = 200) -> int:
    """
    根据字数计算所需时间（分钟）
    :param word_count: 字数
    :param words_per_minute: 每分钟阅读的字数，默认为200
    :return: 所需时间（分钟）
    """
    if word_count <= 0 or words_per_minute <= 0:
        return 0
    return max(1, word_count // words_per_minute)


@tool
async def rag_tool(question: str, config: RunnableConfig) -> str:
    """
    RAG 工具，用于回答问题
    :param question: 用户提问
    :param config: 配置参数
    :return: 回答内容
    """
    rag_graph = await rag_agent.make_graph()
    response = await rag_graph.ainvoke(
        {
            "messages": [{"role": "user", "content": question}],
            "max_rewrite": 3,
            "rewrite_count": 0,
        },
        config,
    )
    return response["messages"][-1].content


_MATH_DESCRIPTION = (
    "math(problem: str, context: Optional[list[str]]) -> float:\n"
    " - 解决所提供的数学问题。\n"
    ' - `problem` 可以是简单的数学问题（例如 "1 + 3"），也可以是文字题（例如 "如果有3个苹果和2个苹果，一共有多少苹果"）。\n'
    " - 你不能在一次调用中计算多个表达式。例如，`math('1 + 3, 2 + 4')` 是不允许的。"
    "如果需要计算多个表达式，必须分别调用，如 `math('1 + 3')`，然后再 `math('2 + 4')`\n"
    " - 尽量减少 `math` 操作的数量。例如，不要先调用 "
    '2. math("10%的$1是多少") 再调用 3. math("$1 + $2")，'
    '而是必须直接调用 2. math("110%的$1是多少")，以减少math操作次数。\n'
    # Context specific rules below
    " - 你可以选择性地提供字符串列表 `context`，以帮助代理解决问题。"
    "如果需要多个上下文来回答问题，可以将它们作为字符串列表提供。\n"
    " - 除非你将前面操作的输出作为 `context` 提供，否则 `math` 操作无法看到前面操作的输出。"
    "如果需要对前面操作的输出进行数学运算，必须将其作为 `context` 提供。\n"
    " - 绝对不能将 `search` 类型操作的输出作为 `problem` 参数中的变量。"
    "因为 `search` 返回的是包含实体信息的文本，而不是数字或数值。"
    "因此，当需要提供 `search` 操作的输出时，必须将其作为 `context` 参数提供给 `math` 操作。"
    '例如，1. search("Barack Obama") 然后 2. math("age of $1") 是绝对不允许的。'
    '应使用 2. math("Barack Obama的年龄", context=["$1"])。\n'
    " - 当你询问有关 `context` 的问题时，请明确单位。"
    '例如，"xx的身高是多少？" 或 "xx是多少百万？" 而不是 "xx是多少？"\n'
)


_SYSTEM_PROMPT = """将数学问题翻译为可以用 Python 的 numexpr 库执行的表达式。使用运行该代码的输出回答问题。

问题：${{带有数学问题的问题}}
```text
${{解决该问题的单行数学表达式}}
```
...numexpr.evaluate(text)...
```output
${{运行代码的输出}}
```
答案：${{答案}}

开始。

问题：37593 * 67 等于多少？
ExecuteCode({{code: "37593 * 67"}})
...numexpr.evaluate("37593 * 67")...
```output
2518731
```
答案：2518731

问题：37593 的五次方根是多少？
ExecuteCode({{code: "37593**(1/5)"}})
...numexpr.evaluate("37593**(1/5)")...
```output
8.222831614237718
```
答案：8.222831614237718
"""

_ADDITIONAL_CONTEXT_PROMPT = """以下是其他函数提供的额外上下文。\
    请用它来替换问题中的 ${{#}} 变量或其他词语。\
    \n\n${context}\n\n注意，上下文变量在代码中尚未定义。\
你必须提取相关数字，并直接在代码中使用。"""


class ExecuteCode(BaseModel):
    """The input to the numexpr.evaluate() function."""

    reasoning: str = Field(
        ...,
        description="The reasoning behind the code expression, including how context is included, if applicable.",
    )

    code: str = Field(
        ...,
        description="The simple code expression to execute by numexpr.evaluate().",
    )


def _evaluate_expression(expression: str) -> str:
    try:
        local_dict = {"pi": math.pi, "e": math.e}
        output = str(
            numexpr.evaluate(
                expression.strip(),
                global_dict={},  # restrict access to globals
                local_dict=local_dict,  # add common mathematical functions
            )
        )
    except Exception as e:
        raise ValueError(
            f'Failed to evaluate "{expression}". Raised error: {repr(e)}.'
            " Please try again with a valid numerical expression"
        )

    # Remove any leading and trailing brackets from the output
    return re.sub(r"^\[|\]$", "", output)


def get_math_tool(llm):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("user", "{problem}"),
            MessagesPlaceholder(variable_name="context", optional=True),
        ]
    )
    extractor = prompt | llm.with_structured_output(
        ExecuteCode, method="function_calling"
    )

    def calculate_expression(
        problem: str,
        context: Optional[List[str]] = None,
        config: Optional[RunnableConfig] = None,
    ):
        chain_input = {"problem": problem}
        if context:
            context_str = "\n".join(context)
            if context_str.strip():
                context_str = _ADDITIONAL_CONTEXT_PROMPT.format(
                    context=context_str.strip()
                )
                chain_input["context"] = [SystemMessage(content=context_str)]
        code_model = extractor.invoke(chain_input, config)
        try:
            return _evaluate_expression(code_model.code)
        except Exception as e:
            return repr(e)

    return StructuredTool.from_function(
        name="math",
        func=calculate_expression,
        description=_MATH_DESCRIPTION,
    )


search = TavilySearch(max_results=2, description="搜索相关信息以回答问题。")


@tool
async def code_generate_tool(requirement: str, config: RunnableConfig) -> str:
    """
    代码生成工具，根据用户需求生成代码
    :param requirement: 用户的代码需求描述
    :param config: 配置参数
    :return: 生成的代码
    """
    from src.agent.code_agent import build_code_generator

    code_agent = build_code_generator()
    response = await code_agent.ainvoke(
        {
            "messages": [{"role": "user", "content": requirement}],
        },
        config,
    )
    return response["messages"][-1].content


@tool
async def code_validate_tool(code: str, config: RunnableConfig) -> str:
    """
    代码验证工具，检查代码正确性并给出建议
    :param code: 需要验证的代码
    :param config: 配置参数
    :return: 验证结果或建议
    """
    from src.agent.code_agent import build_code_validator

    validator_agent = build_code_validator()
    response = await validator_agent.ainvoke(
        {
            "messages": [{"role": "user", "content": code}],
        },
        config,
    )
    return response["messages"][-1].content


BACKEND_BASE_URL = "http://127.0.0.1:8080/api/eduagentx"


@tool
async def get_stu_exam_status(stu_id: str, config: RunnableConfig) -> str:
    """
    获取学生考试信息
    :param stu_id: 学生ID
    :param config: 配置参数
    :return: 学生考试状态
    """
    # /exam/statistics/student/{studentId}/course/{courseId}

    courseId = config.get("configurable", {}).get("courseId", None)

    url = BACKEND_BASE_URL + f"/exam/statistics/student/{stu_id}/course/{courseId}"

    user_info = config.get("configurable", {}).get("langgraph_auth_user", None)

    auth_header = user_info.get("authorization", None)

    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }

    resp = httpx.get(
        url,
        headers=headers,
    )
    if resp.status_code != http.HTTPStatus.OK:
        raise ValueError(
            f"Failed to get student exam status. Status code: {resp.status_code}, "
            f"Response: {resp.text}"
        )

    prompt = f"""
请根据以下学生考试历史数据，自动生成一段对该学生知识点掌握情况的评价，内容需包括整体表现、各章节掌握情况、存在的主要问题及改进建议，语言简明、客观、具体。

【学生考试数据】
{resp.data}

【输出要求】
- 先简要评价学生整体知识点掌握情况（如准确率、得分等）。
- 指出各章节的掌握情况，突出薄弱章节。
- 列举主要错误或易错题型，并分析原因。
- 给出针对性的学习建议。

请用中文输出评价内容。
"""
    llm = init_chat_model(
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

    response = await llm.ainvoke(
        {
            "messages": [{"role": "user", "content": prompt}],
        },
        config,
    )

    return (
        response["messages"][-1].content.strip()
        if response["messages"]
        else "No response generated."
    )
