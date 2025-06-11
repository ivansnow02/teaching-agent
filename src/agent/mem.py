
from langchain_core.messages.utils import count_tokens_approximately
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph.prebuilt.chat_agent_executor import AgentState
from langmem import create_manage_memory_tool, create_search_memory_tool
from langmem.short_term import SummarizationNode
from pydantic import BaseModel

model = ChatGoogleGenerativeAI(model="gemini-2.0-flash-lite")
# mem_model = ChatGoogleGenerativeAI(model="gemini-2.0-flash-lite", temperature=0.0)


# class MemoryTriple(BaseModel):
#     """存储语义关系的三元组."""

#     subject: str
#     predicate: str
#     object: str
#     context: str | None = None


# class UserPreference(BaseModel):
#     """存储用户偏好."""

#     category: str
#     preference: str
#     confidence: float = 1.0


# def create_memory_manager_agent(store, tools=None):
#     """创建专门的记忆管理代理."""

#     def memory_prompt(state):
#         """为记忆管理器准备提示."""
#         # 搜索现有相关记忆
#         existing_memories = store.search(
#             ("semantic_memories",),
#             query=state["messages"][-1].content if state["messages"] else "",
#         )

#         system_msg = f"""你是一个专门的记忆管理代理。从对话中提取和管理重要的知识、关系和事件。

# 现有记忆:
# <memories>
# {existing_memories}
# </memories>

# 使用 manage_memory 工具来:
# 1. 创建新的语义记忆
# 2. 更新过时的记忆
# 3. 删除不再有效的记忆
# 4. 建立实体间的关系

# 使用 search_memory 工具来查找相关的现有记忆。
# """
#         return [{"role": "system", "content": system_msg}, *state["messages"]]

#     return create_react_agent(
#         model=mem_model,
#         prompt=memory_prompt,
#         name="memory_manager",
#         tools=[
#             create_manage_memory_tool(namespace=("semantic_memories",)),
#             create_search_memory_tool(namespace=("semantic_memories",)),
#             create_manage_memory_tool(namespace=("user_preferences",)),
#             create_search_memory_tool(namespace=("user_preferences",)),
#         ] + tools if tools else [],
#     )


summarization_node = SummarizationNode(
    token_counter=count_tokens_approximately,
    model=model,
    max_tokens=384,
    max_summary_tokens=128,
    output_messages_key="llm_input_messages",
)


# class State(AgentState):
#     """扩展的代理状态，包含记忆管理功能."""

#     # NOTE: we're adding this key to keep track of previous summary information
#     # to make sure we're not summarizing on every LLM call
#     context: dict[str, Any]
#     # # 添加记忆管理相关状态（仅类型注解）
#     # memory_extraction_needed: bool
#     semantic_memories: list[MemoryTriple]
#     user_preferences: list[UserPreference]


# def should_extract_memories(state: State) -> bool:
#     """判断是否需要提取记忆."""
#     # 检查是否有新的重要信息
#     if not state.get("messages"):
#         return False

#     last_message = state["messages"][-1]
#     # 简单的启发式规则，实际可以更复杂
#     important_keywords = [
#         "prefer",
#         "like",
#         "dislike",
#         "remember",
#         "important",
#         "关系",
#         "管理",
#         "团队",
#     ]

#     # 修复：获取消息内容的正确方式
#     content = getattr(last_message, "content", str(last_message))
#     if isinstance(content, str):
#         return any(keyword in content.lower() for keyword in important_keywords)
#     return False


# def coordinate_memory_extraction(state: State, store, memory_manager):
#     """协调记忆提取过程."""

#     memory_manager.invoke({
#         "messages": state["messages"],
#         "config": {"configurable": {"user_id": state.get("user_id", "default")}},
#     })

#     return state
