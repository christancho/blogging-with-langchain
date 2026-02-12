"""
Content Synthesis Tool for deep research mode
"""
import json
from typing import List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config import Config


class ContentSynthesisTool:
    """
    Tool for synthesizing research content into structured findings.
    Extracts key facts, quotes, themes from fetched web content.
    """

    def synthesize_content(
        self,
        topic: str,
        fetched_contents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Synthesize fetched content into structured research data.

        Args:
            topic: Research topic
            fetched_contents: List of {url, content, type} dicts from URLFetcherTool

        Returns:
            {
                "summary": "Executive summary",
                "key_facts": [{"fact": "...", "source": "...", "confidence": "high"}],
                "quotes": [{"quote": "...", "author": "...", "source": "..."}],
                "themes": ["theme1", "theme2"],
                "sources_by_priority": ["url1", "url2"]
            }
        """
        llm = Config.get_llm()

        # Build content section for prompt
        content_sections = []
        for idx, content_data in enumerate(fetched_contents[:15], 1):  # Limit to 15 to avoid token overflow
            content_sections.append(f"\n--- Source {idx}: {content_data['url']} ---")
            # Truncate very long content
            content = content_data['content'][:8000]  # Max 8k chars per source
            content_sections.append(content)

        combined_content = "\n".join(content_sections)

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", """You are a research synthesis expert. Analyze the provided web content and extract structured insights.

**Topic**: {topic}
**Number of sources**: {num_sources}

**Fetched Content**:
{content}

**Your Task**: Extract structured information as JSON.

**Required JSON Output**:
{{
  "summary": "2-3 paragraph executive summary of findings",
  "key_facts": [
    {{
      "fact": "Specific factual statement",
      "source": "https://exact-source-url.com",
      "confidence": "high"
    }}
  ],
  "quotes": [
    {{
      "quote": "Exact quote text",
      "author": "Author name or Unknown",
      "source": "https://source-url.com"
    }}
  ],
  "themes": ["Main theme or pattern"],
  "sources_by_priority": ["https://most-authoritative.com"]
}}

**Guidelines**:
- **key_facts**: Extract 10-15 verifiable facts with exact source URLs. Confidence: "high" = verified across multiple sources, "medium" = single authoritative source, "low" = uncertain
- **quotes**: Select 5-8 most impactful quotes (expert opinions, data, insights). Include author if identifiable
- **themes**: Identify 3-5 recurring patterns or main topics across all sources
- **sources_by_priority**: Rank top 10 sources by authority, relevance, and content quality

Output valid JSON only, no additional text."""),
            ("human", "Synthesize the research content above.")
        ])

        chain = prompt_template | llm | StrOutputParser()

        result = chain.invoke({
            "topic": topic,
            "num_sources": len(fetched_contents),
            "content": combined_content
        })

        # Parse JSON (handle potential markdown code blocks)
        result_clean = result.strip()
        if result_clean.startswith("```"):
            # Remove markdown code block markers
            result_clean = result_clean.split("```")[1]
            if result_clean.startswith("json"):
                result_clean = result_clean[4:]
            result_clean = result_clean.strip()

        try:
            synthesis = json.loads(result_clean)
        except json.JSONDecodeError as e:
            print(f"⚠️  JSON parse error: {e}")
            print(f"Raw result: {result[:500]}")
            # Return minimal structure on parse failure
            synthesis = {
                "summary": "Synthesis failed - see raw research",
                "key_facts": [],
                "quotes": [],
                "themes": [],
                "sources_by_priority": [c["url"] for c in fetched_contents]
            }

        return synthesis
