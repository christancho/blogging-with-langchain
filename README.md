# LangGraph Blog Generation System

An automated blog post generation system built with LangGraph, LangChain, and Claude AI. This system generates comprehensive, SEO-optimized blog posts and publishes them to Ghost CMS.

## Features

- **Automated Research**: Uses Brave Search API to gather current information
- **AI-Powered Writing**: Generates comprehensive 3,500+ word articles
- **SEO Optimization**: Automatically optimizes content for search engines
- **Ghost CMS Integration**: Publishes directly to Ghost CMS as drafts
- **Quality Assurance**: Built-in content quality checks and validation
- **Modular Architecture**: Clean, maintainable codebase using LangGraph
- **LangSmith Tracing**: Optional integration for debugging and monitoring (optional)

## Architecture

The system uses a LangGraph state graph with 6 sequential nodes:

```
Research → Writer → SEO → Formatter → Reviewer → Publisher
```

Each node performs a specific task and updates the shared state.

## Prerequisites

**Required:**
- Python 3.10+
- Anthropic API key (Claude) or OpenRouter API key
- Brave Search API key
- Ghost CMS instance with Admin API access

**Optional:**
- LangSmith API key (for tracing and debugging)

## Installation

1. **Clone the repository**
```bash
cd blogging-with-langchain
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**

Create a `.env` file in the project root:

```env
# Primary LLM (Claude via Anthropic)
ANTHROPIC_API_KEY=your_anthropic_api_key
CLAUDE_MODEL=claude-3-5-sonnet-20241022
CLAUDE_TEMPERATURE=0.7

# Fallback LLM (OpenRouter)
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# LLM Selection (true = Anthropic, false = OpenRouter)
USE_PRIMARY_LLM=true

# Brave Search API
BRAVE_SEARCH_API_KEY=your_brave_search_api_key

# Ghost CMS
GHOST_API_KEY=your_ghost_admin_api_key
GHOST_API_URL=https://your-ghost-site.com
GHOST_AUTHOR_ID=your_author_id

# Optional: Customize settings
WORD_COUNT_TARGET=3500
MIN_INLINE_LINKS=10
PUBLISH_AS_DRAFT=true
```

## Usage

### Generate a Blog Post

```bash
python main.py "Your blog topic here"
```

**Examples:**
```bash
python main.py "AI and Machine Learning in Healthcare"
python main.py "Introduction to LangGraph and LangChain"
python main.py "Best Practices for Python Web Development"
```

### Visualize the Workflow

```bash
python main.py --visualize
```

### Enable Debug Mode

```bash
python main.py "Your topic" --debug
```

## Project Structure

```
blogging-with-langchain/
├── config.py              # Configuration settings
├── state.py               # BlogState TypedDict
├── graph.py               # LangGraph state graph definition
├── main.py                # Entry point
├── tools/                 # Custom tools
│   ├── brave_search.py    # Web search tool
│   ├── seo_analyzer.py    # SEO analysis
│   ├── html_formatter.py  # HTML/Markdown formatting
│   ├── ghost_cms.py       # Ghost CMS publishing
│   ├── tag_extractor.py   # Tag extraction
│   └── content_analyzer.py # Content quality analysis
├── prompts/               # Prompt templates
│   ├── research.py
│   ├── writer.py
│   ├── seo.py
│   ├── formatter.py
│   └── reviewer.py
├── nodes/                 # LangGraph node functions
│   ├── research_node.py
│   ├── writer_node.py
│   ├── seo_node.py
│   ├── formatter_node.py
│   ├── reviewer_node.py
│   └── publisher_node.py
├── tests/                 # Unit tests
│   ├── test_tools.py
│   └── test_config.py
├── output/                # Generated blog posts
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
└── .gitignore
```

## Workflow Details

### 1. Research Node
- Performs 5-7 web searches using Brave Search API
- Collects 5-10 credible sources
- Generates research summary

### 2. Writer Node
- Creates comprehensive 3,500+ word article
- Structured with intro, 4 main sections, conclusion
- Includes 10-15 inline citations from research

### 3. SEO Node
- Generates SEO-optimized title (50-60 chars)
- Creates meta description (150-160 chars)
- Extracts 5-8 relevant tags
- Identifies primary keywords

### 4. Formatter Node
- Formats content for Ghost CMS
- Ensures proper Markdown syntax
- Fixes heading hierarchy
- Normalizes spacing

### 5. Reviewer Node
- Validates content quality
- Checks word count, links, structure
- Calculates quality score
- Returns final approved content

### 6. Publisher Node
- Saves article to local `output/` directory
- Publishes to Ghost CMS as draft (or published)
- Returns post ID and URL

## Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_tools.py

# Run with coverage
pytest --cov=. --cov-report=html

# Run with verbose output
pytest -v
```

## Configuration Options

All settings can be customized in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `WORD_COUNT_TARGET` | 3500 | Target word count for articles |
| `NUM_SECTIONS` | 4 | Number of main content sections |
| `MIN_INLINE_LINKS` | 10 | Minimum inline citations required |
| `TARGET_KEYWORD_DENSITY` | 1.5 | Target keyword density (%) |
| `PUBLISH_AS_DRAFT` | true | Publish as draft or published |
| `OUTPUT_DIR` | output | Local output directory |

## LangSmith Tracing (Optional)

LangSmith provides powerful tracing and debugging capabilities for your LangGraph workflows. With LangSmith, you can:

- 📊 **Visualize the entire workflow** - See each node execution in a timeline
- 🔍 **Inspect LLM calls** - View prompts, responses, and token usage
- ⏱️ **Track performance** - Monitor execution time for each node
- 💰 **Monitor costs** - Track API usage across runs
- 🐛 **Debug issues** - Replay runs and identify bottlenecks
- 📈 **Analytics** - Aggregate metrics across multiple runs

### Setup LangSmith

1. **Create a LangSmith account** at [smith.langchain.com](https://smith.langchain.com)

2. **Get your API key** from the LangSmith dashboard

3. **Add to your `.env` file:**
```env
# Enable LangSmith tracing
LANGCHAIN_TRACING_V2=true

# Your LangSmith API key
LANGCHAIN_API_KEY=your_langsmith_api_key_here

# Optional: Custom project name (defaults to "blog-generation")
LANGCHAIN_PROJECT=my-blog-project
```

4. **Run the system** - Tracing is now automatic!

```bash
python main.py "Your topic"
```

5. **View traces** at [smith.langchain.com](https://smith.langchain.com)

### What You'll See in LangSmith

Each blog generation run will show:

- **Research Node**: All web searches and sources gathered
- **Writer Node**: LLM prompt and full article generation
- **SEO Node**: SEO analysis and optimization
- **Formatter Node**: Content formatting transformations
- **Reviewer Node**: Quality checks and final approval
- **Publisher Node**: Ghost CMS API calls

### Example Trace View

```
Blog Generation Run (3m 42s)
├── research_node (45s)
│   ├── BraveSearchTool: "AI trends" (3s)
│   ├── BraveSearchTool: "machine learning 2024" (2s)
│   └── LLM Call: Research summary (40s)
├── writer_node (2m 15s)
│   └── LLM Call: Generate 3500 word article (2m 15s)
├── seo_node (18s)
│   └── LLM Call: SEO optimization (18s)
├── formatter_node (5s)
│   └── LLM Call: Format for Ghost CMS (5s)
├── reviewer_node (12s)
│   └── ContentAnalysisTool + LLM Call (12s)
└── publisher_node (7s)
    └── GhostCMSTool: Publish to CMS (7s)
```

### Disable LangSmith

To disable tracing, set in `.env`:
```env
LANGCHAIN_TRACING_V2=false
```

Or simply remove/comment out the LangSmith variables.

## Troubleshooting

### Configuration Errors

If you see configuration validation errors:
```
Configuration validation failed:
  - ANTHROPIC_API_KEY is required when using primary LLM
```

Ensure your `.env` file has all required API keys.

### API Rate Limits

- **Brave Search**: Free tier allows 2,000 queries/month
- **Anthropic**: Check your plan's rate limits
- **Ghost CMS**: Typically no rate limits for Admin API

### Quality Score Low

If quality scores are consistently low:
- Check that the LLM is generating full 3,500+ word articles
- Verify inline links are being included
- Ensure proper heading structure (1 H1, 4+ H2s)

## Cost Estimates

**Per blog post:**
- Claude 3.5 Sonnet via Anthropic: ~$0.15-0.30
- OpenRouter (Claude 3.5 Sonnet): ~$0.15-0.30
- Brave Search: Free (within limits)
- Ghost CMS: Varies by hosting

## Comparison to CrewAI Version

This LangGraph implementation provides:
- ✅ More explicit state management
- ✅ Better debugging and observability (LangSmith tracing)
- ✅ Simpler, more Pythonic code
- ✅ Easier to extend and customize
- ✅ Direct LangChain integration
- ✅ No CrewAI dependency overhead
- ✅ Built-in LangSmith support for monitoring and debugging

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - feel free to use this project however you like!

## Acknowledgments

- Inspired by the [Blogging-with-CrewAI](https://github.com/christancho/Blogging-with-CrewAI) project
- Built with [LangChain](https://github.com/langchain-ai/langchain) and [LangGraph](https://github.com/langchain-ai/langgraph)
- Powered by [Anthropic Claude](https://www.anthropic.com/)

## Support

For issues or questions:
- Open an issue on GitHub
- Check the troubleshooting section above
- Review the example `.env` configuration

---

**Built with ❤️ using LangGraph and Claude**
