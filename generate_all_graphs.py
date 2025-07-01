
import asyncio
import os

# Import all the graph builder functions
from src.agent.chapter_outline_generator import build_chapter_graph
from src.agent.chapter_content_generator import build_lesson_planner
from src.agent.quiz_generator import build_quiz_workflow
from src.agent.lesson_plan_workflow import build_plan_workflow
from src.agent.rag_agent import make_graph as make_rag_graph
from src.agent.supervisor import make_supervisor

async def main():
    """
    Generates and saves all LangGraph graphs as PNG images.
    """
    # Create a directory to store the graphs
    output_dir = "graph_images"
    os.makedirs(output_dir, exist_ok=True)
    print(f"Graph images will be saved in the '{output_dir}/' directory.")

    # Dictionary of graph builders and their output names
    graph_builders = {
        "chapter_outline_graph": build_chapter_graph,
        "chapter_content_graph": build_lesson_planner,
        "quiz_workflow_graph": build_quiz_workflow,
        "lesson_plan_workflow_graph": build_plan_workflow,
        "rag_agent_graph": make_rag_graph,
        "supervisor_graph": make_supervisor,
    }

    for name, builder in graph_builders.items():
        print(f"Generating graph for: {name}...")
        try:
            # Check if the builder is an async function
            if asyncio.iscoroutinefunction(builder):
                graph_runnable = await builder()
            else:
                graph_runnable = builder()

            # Get the graph object
            graph = graph_runnable.get_graph()

            # Define the output path for the PNG file
            output_path = os.path.join(output_dir, f"{name}.png")

            # Save the graph as a PNG image
            # This requires pygraphviz and mermaid-cli to be installed
            try:
                with open(output_path, "wb") as f:
                    f.write(graph.draw_mermaid_png())
                print(f"✅ Successfully saved graph to {output_path}")
            except Exception as draw_error:
                print(f"❌ Failed to draw graph for {name}. Error: {draw_error}")
                print("  Please ensure 'pygraphviz' and 'mermaid-cli' are installed.")
                print("  Install with: pip install pygraphviz && npm install -g @mermaid-js/mermaid-cli")


        except Exception as e:
            print(f"❌ Failed to generate or process graph for {name}. Error: {e}")

if __name__ == "__main__":
    print("Starting graph generation process...")
    # Note: This script requires environment variables (like API keys) to be set,
    # as some graph builders initialize models at the module level.
    # Please ensure your .env file is configured correctly before running.
    asyncio.run(main())
    print("Graph generation process finished.")
