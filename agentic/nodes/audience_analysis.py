"""
Audience analysis node - identifies target reader persona and pain points
"""
from datetime import datetime
from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from state import BlogState
from config import Config
from nodes.prompt_loader import PromptLoader


def audience_analysis_node(state: BlogState) -> Dict[str, Any]:
    """
    Audience analysis node: Identify target reader, pain points, and content angle.

    Runs after research and before writer to inform content direction.

    Args:
        state: Current blog state

    Returns:
        Partial state update with audience insights
    """
    print("\n" + "="*80)
    print("AUDIENCE ANALYSIS NODE")
    print("="*80)

    topic = state["topic"]
    instructions = state.get("instructions", "")
    research_summary = state.get("research_summary", "")

    print(f"Analyzing target audience for: {topic}")

    # Load and render prompt
    audience_template = PromptLoader.load("audience_analysis")
    current_date = datetime.now().strftime("%B %d, %Y")
    audience_prompt_text = audience_template.render(
        topic=topic,
        instructions=instructions or "No specific instructions provided.",
        research_summary=research_summary[:3000],  # Limit to avoid token overflow
        current_date=current_date
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", audience_prompt_text),
        ("human", "Analyze the target audience for this topic now.")
    ])

    try:
        llm = Config.get_llm()
        chain = prompt | llm | StrOutputParser()

        audience_insights = chain.invoke({})

        # Escape curly braces for prompt template compatibility
        audience_insights_escaped = audience_insights.replace("{", "{{").replace("}", "}}")

        print(f"\n✓ Audience analysis completed")
        print(f"  - Analysis length: {len(audience_insights)} characters")

        return {
            "audience_analysis": audience_insights_escaped
        }

    except Exception as e:
        print(f"\n✗ Audience analysis failed: {str(e)}")
        return {
            "audience_analysis": "",
            "warnings": state.get("warnings", []) + [f"Audience analysis skipped: {str(e)}"]
        }
