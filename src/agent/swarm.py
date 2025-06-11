from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph.store.memory import InMemoryStore
from langgraph_swarm import create_handoff_tool, create_swarm

from src.agent.mem import summarization_node

checkpointer = InMemorySaver()
store = InMemoryStore()


def book_hotel(hotel_name: str):
    """Book a hotel"""
    return f"Successfully booked a stay at {hotel_name}."


def book_flight(from_airport: str, to_airport: str):
    """Book a flight"""
    return f"Successfully booked a flight from {from_airport} to {to_airport}."


transfer_to_hotel_assistant = create_handoff_tool(
    agent_name="hotel_assistant",
    description="Transfer user to the hotel-booking assistant.",
)
transfer_to_flight_assistant = create_handoff_tool(
    agent_name="flight_assistant",
    description="Transfer user to the flight-booking assistant.",
)

transfer_to_memory_manager = create_handoff_tool(
    agent_name="memory_manager",
    description="Transfer user to the memory management assistant.",
)

transfers = [
    transfer_to_hotel_assistant,
    transfer_to_flight_assistant,
]


def get_transfer_from_agent(agent_name: str):
    """Get transfer tools for a specific agent."""
    # 工具名称格式为 "transfer_to_{agent_name}"，我们需要排除指向当前代理的工具
    target_tool_name = f"transfer_to_{agent_name}"
    return [tool for tool in transfers if tool.name != target_tool_name]


flight_assistant_tools = get_transfer_from_agent("flight_assistant")

hotel_assistant_tools = get_transfer_from_agent("hotel_assistant")

memory_manager_tools = get_transfer_from_agent("memory_manager")


flight_assistant = create_react_agent(
    pre_model_hook=summarization_node,
    model="google_genai:gemini-2.5-flash-preview-05-20",
    tools=[book_flight] + flight_assistant_tools,
    prompt="You are a flight booking assistant",
    name="flight_assistant",
)
hotel_assistant = create_react_agent(
    pre_model_hook=summarization_node,
    model="google_genai:gemini-2.5-flash-preview-05-20",
    tools=[book_hotel] + hotel_assistant_tools,
    prompt="You are a hotel booking assistant",
    name="hotel_assistant",
)

# memory_manager = create_memory_manager_agent(store, tools=memory_manager_tools)

swarm = create_swarm(
    agents=[flight_assistant, hotel_assistant],
    default_active_agent="flight_assistant",
).compile(

    # checkpointer=checkpointer,
)

# Alias for backward compatibility


# for chunk in swarm.stream({
#     "messages": [
#         {
#             "role": "user",
#             "content": "book a flight from BOS to JFK and a stay at McKittrick Hotel",
#         }
#     ]
# }):
#     print(chunk)
#     print("\n")
