"""
State definition for the LangGraph Blog Generation workflow
"""
from typing import TypedDict, List, Optional, Dict, Any


class BlogState(TypedDict, total=False):
    """
    State that flows through the LangGraph workflow.

    Each node reads from and writes to this state dictionary.
    Fields are optional (total=False) to allow incremental updates.
    """

    # ============================================================================
    # Input
    # ============================================================================
    topic: str  # The blog topic to write about
    instructions: Optional[str]  # Custom instructions for this article (optional)
    tone: str  # Blog tone (default: Config.BLOG_TONE)
    word_count_target: int  # Target word count (default: Config.WORD_COUNT_TARGET)

    # ============================================================================
    # Research Configuration
    # ============================================================================
    deep_research_enabled: bool  # Whether deep research mode is enabled

    # ============================================================================
    # Research Node Outputs
    # ============================================================================
    research_results: Dict[str, Any]  # Search results, URLs, summaries
    research_sources: List[str]  # List of source URLs
    research_summary: str  # Compiled research findings

    # Deep research outputs (populated only when deep_research_enabled=True)
    research_queries: List[str]  # LLM-generated search queries
    research_fetched_urls: List[Dict[str, Any]]  # Fetched URL content with metadata
    research_key_facts: List[Dict[str, str]]  # Extracted facts with sources
    research_quotes: List[Dict[str, str]]  # Notable quotes with attribution
    research_themes: List[str]  # Main themes identified
    research_structured_data: Dict[str, Any]  # Complete synthesis for writer

    # ============================================================================
    # Content Writer Node Outputs
    # ============================================================================
    article_content: str  # Full article text (3500+ words)
    article_title: str  # Working title
    article_sections: List[Dict[str, str]]  # Structured sections
    inline_links: List[str]  # URLs used as inline citations

    # ============================================================================
    # SEO Optimizer Node Outputs
    # ============================================================================
    seo_metadata: Dict[str, Any]  # All SEO metadata
    seo_title: str  # Optimized title (50-60 chars)
    meta_description: str  # Meta description (150-160 chars)
    excerpt: str  # Article excerpt for listing pages (200-250 chars)
    tags: List[str]  # SEO tags (5-8 tags)
    keywords: List[str]  # Primary keywords
    keyword_density: float  # Calculated keyword density

    # ============================================================================
    # HTML Formatter Node Outputs
    # ============================================================================
    formatted_content: str  # Ghost CMS-compatible Markdown/HTML
    formatted_html: str  # Pure HTML if needed
    table_of_contents: Optional[str]  # Generated table of contents markdown

    # ============================================================================
    # Editor Node Outputs (Approval Gate)
    # ============================================================================
    approval_status: str  # "approved", "rejected", or "pending"
    approval_feedback: str  # Specific feedback if rejected (for writer revision)
    quality_score: float  # Overall quality score (0-1)
    quality_checks: Dict[str, bool]  # Individual quality checks
    review_notes: str  # Reviewer feedback
    revision_count: int  # Number of times article was revised (starts at 0)
    max_revisions: int  # Maximum allowed revisions (default: 3)
    final_content: str  # Approved content ready for publishing
    forced_publish_note: Optional[str]  # Note prepended if max revisions exceeded

    # ============================================================================
    # Ghost Publisher Node Outputs
    # ============================================================================
    ghost_post_id: Optional[str]  # Published post ID
    ghost_post_url: Optional[str]  # Published post URL
    publication_status: str  # "draft", "published", "failed"

    # ============================================================================
    # Error Handling
    # ============================================================================
    errors: List[str]  # Any errors encountered
    warnings: List[str]  # Any warnings

    # ============================================================================
    # Metadata
    # ============================================================================
    timestamp: str  # When the workflow started
    workflow_version: str  # Version of the workflow

    # ============================================================================
    # Cost Tracking
    # ============================================================================
    total_input_tokens: int  # Cumulative input tokens across all LLM calls
    total_output_tokens: int  # Cumulative output tokens across all LLM calls
    total_cost_usd: float  # Cumulative cost in USD
    cost_breakdown: Dict[str, Dict[str, Any]]  # Per-node cost breakdown
