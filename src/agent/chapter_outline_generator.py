import os
from typing import Dict, List, TypedDict
from langchain.chat_models import init_chat_model
from langgraph.constants import END
from langgraph.graph import StateGraph
from langgraph.graph.graph import CompiledGraph
from pydantic import BaseModel, Field


# 结构化章节条目
class ChapterItem(BaseModel):
    title: str = Field(description="章节标题")
    content: str = Field(description="章节内容简介")
    order: int = Field(description="章节顺序")
    # type: str = Field(description="章节类型，theory为理论课，experiment为实训课")


class ChapterItemList(BaseModel):
    chapters: List[ChapterItem] = Field(description="章节列表")


# 状态类型
class ChapterState(TypedDict):
    """状态类型，用于存储课程大纲和章节列表"""

    has_experiment: bool
    hour_per_class: int
    raw_syllabus: str
    chapters: List[dict]


llm = init_chat_model(
    model="qwen3-235b-a22b",
    model_provider="openai",
    temperature=0,
    extra_body={"enable_thinking": False},
    api_key=os.getenv("DASH_SCOPE_API_KEY", ""),
    base_url=os.getenv(
        "DASH_SCOPE_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
)


def extract_chapters(state: ChapterState) -> Dict:
    raw_syllabus = state["raw_syllabus"]
    prompt = f"""
你是一个智能教案结构化专家，负责将课程大纲解析为结构化章节列表。

你需要结合相关课时来分配章节,每节课有{state.get("hour_per_class", 2)}小时。

**原始大纲内容**:
{raw_syllabus}

**是否包含实训课**:
{state.get("has_experiment", "false")}
**输出要求**:
请严格按照以下JSON数组格式进行响应，不要包含任何其他文本。
在title字段开头表明类型，例如第一章：XXXX或实训一：XXXXX
```json
{ChapterItemList.model_json_schema()}
```
每个章节对象都必须包含上述所有字段。
"""
    structured_llm = llm.with_structured_output(ChapterItemList)
    result = structured_llm.invoke(prompt)

    return {"chapters": result.chapters}


async def build_chapter_graph() -> CompiledGraph:
    workflow = StateGraph(ChapterState)
    workflow.add_node("extract_chapters", extract_chapters)
    workflow.set_entry_point("extract_chapters")
    workflow.add_edge("extract_chapters", END)
    return workflow.compile()
