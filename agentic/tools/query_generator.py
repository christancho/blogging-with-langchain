"""
Query Generator Tool for deep research mode
"""
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from datetime import datetime
from agentic.config import Config


class QueryGeneratorTool:
    """
    Tool for generating intelligent, diverse search queries for research.
    Uses LLM to create topic-specific queries optimized for current information.
    """

    def generate_queries(
        self,
        topic: str,
        instructions: str = "",
        num_queries: int = 6,
        session_notes: str = ""
    ) -> List[str]:
        """
        Generate diverse search queries for topic exploration.

        Args:
            topic: The blog topic
            instructions: Optional custom instructions
            num_queries: Number of queries to generate
            session_notes: Optional author's hands-on session notes; when present,
                queries are steered to support that session

        Returns:
            List of search query strings
        """
        llm = Config.get_llm(temperature=Config.RESEARCH_TEMPERATURE)
        current_year = datetime.now().year

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", """You are a search query expert. Generate {num_queries} diverse, specific web search queries for researching this topic.

**Topic**: {topic}
{instructions_section}{session_notes_section}

**Requirements**:
1. Include year ({current_year}) for current information
2. Use specific technical terms, avoid vague language
3. Cover different angles: fundamentals, best practices, comparisons, use cases, recent developments, challenges
4. Make queries specific enough to find quality sources
5. Avoid generic queries like "what is X" - be more targeted

**Output Format**: One query per line, no numbering or formatting.

Example output:
Python async programming best practices {current_year}
Python asyncio vs threading performance comparison
Real-world Python asyncio use cases production environments
Common Python async await pitfalls and debugging

Generate queries now."""),
            ("human", "Generate {num_queries} research queries for: {topic}")
        ])

        instructions_section = f"**Custom Instructions**: {instructions}" if instructions else ""

        session_notes_section = (
            f"\n**Author's Session Notes** (the article is built on this hands-on session): {session_notes}\n\n"
            "Generate queries that support this session: official documentation for the tools and versions used, "
            "known issues behind the errors encountered, current best practices for the steps taken. "
            "Don't research the topic in the abstract."
            if session_notes else ""
        )

        chain = prompt_template | llm | StrOutputParser()

        result = chain.invoke({
            "topic": topic,
            "instructions_section": instructions_section,
            "session_notes_section": session_notes_section,
            "num_queries": num_queries,
            "current_year": current_year
        })

        # Parse queries (one per line)
        queries = [
            q.strip()
            for q in result.strip().split('\n')
            if q.strip() and not q.strip().startswith('#')
        ]

        return queries[:num_queries]
