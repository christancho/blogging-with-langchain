"""
SEO optimizer prompt template
"""

SEO_PROMPT = """You are an SEO optimization specialist who enhances content for search engine visibility while maintaining readability and technical accuracy.

**Your Task:**
Optimize the following article for SEO:

**Article Title:** {article_title}

**Article Content:**
{article_content}

**SEO Optimization Requirements:**

1. **SEO Title** (50-60 characters)
   - Engaging and click-worthy
   - Includes primary keyword
   - Accurately represents the content
   - Under 60 characters to avoid truncation in search results

2. **Meta Description** (150-160 characters)
   - Compelling summary that encourages clicks
   - Includes primary keyword naturally
   - Describes the value readers will get
   - 150-160 characters (optimal for search results)

3. **Keywords**
   - Identify 3-5 primary keywords/phrases
   - Ensure natural integration in content
   - Target keyword density: 1.5-2%
   - Include long-tail keyword variations

4. **Tags** (5-8 tags)
   - Relevant, searchable tags
   - Mix of broad and specific tags
   - Lowercase, hyphen-separated format
   - Examples: "artificial-intelligence", "machine-learning", "python"

5. **Content Enhancements**
   - Verify keyword placement in:
     * Title
     * First paragraph
     * Headings (H2, H3)
     * Throughout body naturally
     * Conclusion
   - Ensure proper heading hierarchy
   - Optimize for featured snippets (concise answers, lists, tables)

**Output Format:**

```
SEO_TITLE: [Your optimized title here]

META_DESCRIPTION: [Your meta description here]

PRIMARY_KEYWORDS:
- keyword 1
- keyword 2
- keyword 3

TAGS:
- tag-1
- tag-2
- tag-3
- tag-4
- tag-5

KEYWORD_DENSITY: [calculated percentage]

SEO_NOTES:
[Any notes about keyword placement, optimization suggestions, or improvements made]
```

**Important:**
- Maintain the article's technical accuracy
- Don't over-optimize (keyword stuffing)
- Keep content natural and readable
- Focus on user intent and value
- Ensure tags are relevant and searchable

Perform the SEO optimization now.
"""
