# LangGraph Blog Generation System

An automated blog post generation system built with LangGraph, LangChain, and Claude AI. This system generates comprehensive, SEO-optimized blog posts and publishes them to Ghost CMS.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running with Docker](#running-with-docker)
- [Usage (CLI)](#usage)
- [Web Interface](#web-interface)
- [API](#api)
- [Project Structure](#project-structure)
- [Workflow Details](#workflow-details)
- [Social Media Notifications](#social-media-notification-system)
- [Running Tests](#running-tests)
- [Configuration Options](#configuration-options)
- [LangSmith Tracing](#langsmith-tracing-optional)
- [Troubleshooting](#troubleshooting)
- [Cost Estimates](#cost-estimates)

## Features

- **Automated Research**: Uses Brave Search API to gather current information and generate headline candidates
- **Audience Analysis**: Identifies target reader persona, pain points, and content angle before writing
- **AI-Powered Writing**: Generates comprehensive 3,500+ word articles with compelling hooks, storytelling, and authentic voice
- **Fact Checking**: Verifies factual claims against web sources after writing, with a revision loop (max 3 attempts)
- **Tone Presets**: Choose from built-in tone presets (`conversational`, `expert_casual`, `storyteller`, `practical`, `thought_leader`) or define your own
- **Custom Instructions**: Provide per-article instructions to guide the content direction
- **SEO Optimization**: Automatically optimizes content for search engines with excerpt support
- **Ghost CMS Integration**: Publishes directly to Ghost CMS with full metadata (title, excerpt, meta description, tags)
- **Editor Approval Gate**: LLM-based editorial review scoring cohesiveness, hook quality, storytelling, and authentic voice
- **Revision Loop**: Failed articles automatically route back to writer with specific, actionable feedback (max 3 attempts)
- **Forced Publishing**: Articles exceeding max revisions force-publish with editor's note explaining unresolved issues
- **Visual Recommendations**: Formatter suggests where to add images, charts, tables, and diagrams
- **Quality Assurance**: Built-in content quality checks (word count, inline links, structure, headings, sections)
- **Date-Aware Prompts**: All prompts receive the current date for timely, relevant content
- **Modular Architecture**: Clean, maintainable codebase using LangGraph
- **LangSmith Tracing**: Optional integration for debugging and monitoring

## Architecture

The system uses a LangGraph state graph with 8 nodes and two approval gate workflows:

```
Research → Audience Analysis → Writer → Fact Checker → Formatter → SEO → Editor (Approval Gate)
                                  ↑           |                               ├─→ Approved → Publisher
                                  └───────────┘ (Fact Check Loop, max 3x)    └─→ Rejected ↻ Writer (Revision Loop, max 3x)
```

### Workflow Diagram

![Blog Generation Workflow](media/blog_graph.png)

Each node performs a specific task and updates the shared state:

- **Research**: Gathers information via web search, generates headline candidates
- **Audience Analysis**: Identifies target reader persona, pain points, goals, and content angle
- **Writer**: Generates comprehensive article with hooks, storytelling, and authentic voice (or revises based on fact checker / editor feedback)
- **Fact Checker**: Verifies factual claims against web sources; routes back to Writer if issues found (max 3 attempts), force-passes if exhausted
- **Formatter**: Normalizes and formats content for readability
  - Fixes heading hierarchy (ensures exactly 1 H1)
  - Cleans up Markdown formatting and spacing
  - Analyzes content and suggests visual element placements (images, charts, tables)
  - Prepares content for SEO and editorial review
- **SEO**: Optimizes for search engines (title, description, excerpt, keywords, tags)
- **Editor**: Quality approval gate with rejection and revision loop
  - Scores cohesiveness, hook quality, storytelling, and authentic voice (0-10 each)
  - Checks mechanical requirements (word count, links, structure, H1, sections)
  - Provides specific, actionable feedback for revisions
  - Allows max 3 revision attempts before forced publishing
  - Sets approval status for conditional routing
- **Publisher**: Publishes to Ghost CMS with complete metadata

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
# LLM Configuration (with automatic fallback)
# The system tries Anthropic first, falls back to OpenRouter if it fails
# At least one API key is required

# Primary: Anthropic Claude (recommended)
ANTHROPIC_API_KEY=your_anthropic_api_key
CLAUDE_MODEL=claude-3-5-sonnet-20241022
CLAUDE_TEMPERATURE=0.7

# Fallback: OpenRouter (used if Anthropic fails)
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=openai/gpt-4o

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

## Running with Docker

The easiest way to run the full stack (API, web UI, and database) is with Docker Compose.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose (or [Portainer](https://www.portainer.io/))

### Setup

1. **Copy the example env file and fill in your values**

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | Password for the PostgreSQL database |
| `JWT_SECRET` | Secret key for signing JWT tokens |
| `UI_PASSWORD` | Password to log into the web UI |
| `WEB_URL` | Public URL of the web frontend (e.g. `http://localhost:3000`) |
| `NEXT_PUBLIC_API_URL` | Public URL of the API (e.g. `http://localhost:8000`) — baked into the frontend build |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `CLAUDE_MODEL` | Claude model to use (e.g. `claude-sonnet-4-6`) |
| `CLAUDE_TEMPERATURE` | LLM temperature (e.g. `0.7`) |
| `BRAVE_SEARCH_API_KEY` | Brave Search API key |
| `GHOST_API_KEY` | Ghost Admin API key |
| `GHOST_API_URL` | Your Ghost instance URL (e.g. `https://yoursite.com`) |
| `GHOST_AUTHOR_ID` | Ghost author ID for published posts |
| `LANGCHAIN_TRACING_V2` | Enable LangSmith tracing (`true` / `false`) |
| `LANGCHAIN_API_KEY` | LangSmith API key (required if tracing is enabled) |
| `LANGCHAIN_PROJECT` | LangSmith project name (e.g. `blog-generation`) |

2. **Build and start all services**

```bash
docker compose up -d --build
```

3. **Access the app**

| Service | URL |
|---------|-----|
| Web UI | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |

### Portainer

If deploying via Portainer, paste the contents of `docker-compose.yml` into the stack editor and set all environment variables in the **Environment variables** panel — no `.env` file needed.

### Stopping

```bash
docker compose down
```

To also remove the database volume:

```bash
docker compose down -v
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

### Customize Blog Tone

Override the default tone using built-in presets or a custom description:

```bash
# Use a preset
python main.py "Your topic" --tone "preset:conversational"
python main.py "Advanced Python Patterns" --tone "preset:expert_casual"
python main.py "AI Strategy Guide" --tone "preset:thought_leader"

# Or use a custom tone description
python main.py "Your topic" --tone "technical and detailed"
python main.py "Getting Started with AI" --tone "educational and accessible"
```

**Built-in tone presets:**
| Preset | Style |
|--------|-------|
| `preset:conversational` | Friendly and approachable, like a knowledgeable friend |
| `preset:expert_casual` | Knowledgeable yet informal, like a senior colleague |
| `preset:storyteller` | Narrative-driven, weaving real-world stories throughout |
| `preset:practical` | Direct, actionable, and results-focused |
| `preset:thought_leader` | Bold, opinionated, and forward-looking |

Or use any custom tone description (e.g., `"conversational and engaging"`, `"technical and detailed"`).

Set the default tone in your `.env` file:
```env
BLOG_TONE=conversational and engaging
```

### Add Custom Instructions

Provide additional guidance for the article generation:

```bash
python main.py "Machine Learning Basics" --instructions "Focus on practical Python examples for beginners"
python main.py "Advanced Python" -i "Target experienced developers, include performance considerations"
python main.py "Web Development" --instructions "Emphasize security best practices throughout"
```

Custom instructions are passed to multiple nodes:
- **Writer**: Influences article structure, focus, and tone
- **SEO**: Guides keyword selection and optimization strategy
- **Editor**: Informs editorial feedback and quality checks

### Visualize the Workflow

```bash
python main.py --visualize
```

This generates a visualization of the workflow graph showing all nodes and their connections.

### Enable Debug Mode

```bash
python main.py "Your topic" --debug
```

Displays detailed error traces and debugging information during execution.

## Web Interface

The system includes a Next.js web dashboard for managing blog generation without using the CLI.

### Running the Web Interface

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Pages

| Page | Description |
|------|-------------|
| **New Post** | Create a new blog generation job with topic, tone, word count, and custom instructions |
| **Queue** | View pending and in-progress jobs |
| **History** | Browse completed jobs and their results |
| **Settings** | Set default tone and word count, change password |

### Authentication

The web interface is password-protected. The default password is set via the `UI_PASSWORD` environment variable (defaults to `changeme` — change this before deploying).

## API

A FastAPI backend provides the HTTP interface between the web UI and the agentic pipeline.

### Running the API

```bash
# From the repo root
uvicorn api.main:app --reload
```

The API runs at [http://localhost:8000](http://localhost:8000). Interactive docs available at `/docs`.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/login` | Authenticate and receive a JWT token |
| `GET` | `/jobs` | List all jobs (newest first) |
| `POST` | `/jobs` | Queue a new blog generation job |
| `DELETE` | `/jobs/{id}` | Remove a pending job |
| `GET` | `/settings` | Get default tone and word count |
| `PATCH` | `/settings` | Update default tone and word count |
| `POST` | `/settings/password` | Change the UI password |

### Background Worker

The API runs a background worker thread that picks up pending jobs and runs them through the full agentic pipeline. Job status (`pending`, `running`, `completed`, `failed`) and the current node are updated in real time.

### Database

Uses PostgreSQL via SQLAlchemy async. Run migrations with:

```bash
cd api && alembic upgrade head
```

Set `DATABASE_URL` in your `.env`:
```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/blogforge
```

## Project Structure

```
blogging-with-langchain/
├── agentic/               # LangGraph pipeline (standalone core)
│   ├── config.py          # Configuration settings
│   ├── state.py           # BlogState TypedDict
│   ├── graph.py           # LangGraph state graph definition
│   ├── republish.py       # Republish utility script
│   ├── tools/             # Custom tools
│   │   ├── brave_search.py
│   │   ├── seo_analyzer.py
│   │   ├── html_formatter.py
│   │   ├── ghost_cms.py
│   │   ├── tag_extractor.py
│   │   └── content_analyzer.py
│   ├── prompts/           # Jinja2 prompt templates (all date-aware)
│   │   ├── research.txt
│   │   ├── audience_analysis.txt
│   │   ├── writer.txt
│   │   ├── revision.txt
│   │   ├── seo.txt
│   │   ├── formatter.txt
│   │   └── editor.txt
│   └── nodes/             # LangGraph node functions
│       ├── prompt_loader.py
│       ├── research.py
│       ├── audience_analysis.py
│       ├── writer.py
│       ├── seo.py
│       ├── formatter.py
│       ├── editor.py
│       ├── publisher.py
│       └── __init__.py
├── api/                   # FastAPI HTTP interface
│   ├── alembic/           # Database migrations
│   ├── alembic.ini
│   └── ...
├── web/                   # Next.js frontend
├── main.py                # CLI entry point
├── tests/                 # Unit tests
├── requirements.txt
└── .gitignore
```

## Workflow Details

### 1. Research Node
- Performs 5-7 web searches using Brave Search API
- Collects 5-10 credible sources
- Generates research summary with source information
- Generates 5-7 headline candidates for the writer to choose from

### 2. Audience Analysis Node
- Identifies the primary reader persona (role, experience level, existing knowledge)
- Surfaces top 3 pain points that brought the reader to search for this topic
- Defines reader goals and desired outcomes
- Recommends content angle and engagement hooks
- Informs the writer to craft content tailored to the target audience

### 3. Writer Node
- Creates comprehensive 3,500+ word article
- **Structured with:** Introduction, 4 main sections, Conclusion
- **Hook requirements (first 2 sentences):**
  - Surprising statistics or facts
  - Thought-provoking questions targeting specific pain points
  - Relatable "you" scenarios
  - Bold, contrarian statements
  - Real-world stories mirroring the reader's struggle
- **Storytelling & Examples (minimum 2 per article):**
  - Concrete real-world examples and case studies
  - Before/after scenarios showing transformation
  - Specific, named examples (companies, tools, projects)
  - Examples that mirror the reader's likely situation
- **Authentic Voice:**
  - Conversational "you" language throughout
  - Honest acknowledgment of complexity
  - Natural rhythm with varied sentence lengths
  - No corporate jargon or filler phrases
- **Engagement strategies:**
  - Strategic bolding of key insights
  - Metaphors and analogies
  - Rhetorical questions
  - Short, scannable paragraphs (2-4 sentences max)
  - Mini-cliffhangers between sections
- **Features:** 10-15 inline citations, headline candidates from research, audience-tailored content
- **Custom instructions:** Applied to influence article direction and focus

### 4. Fact Checker Node
- Verifies factual claims in the article against live web sources using Brave Search
- Identifies inaccurate, outdated, or unverifiable claims
- Routes back to Writer with specific correction feedback if issues found
- Allows max 3 revision attempts before force-passing to Formatter
- Sets `fact_check_status` (`passed`, `failed`, `force_passed`) for conditional routing

### 5. SEO Node
- Generates SEO-optimized title (50-60 chars)
- Creates meta description (150-160 chars)
- **Generates article excerpt** (200-250 chars for listing pages)
- Extracts 5-8 relevant tags
- Identifies 3-5 primary keywords
- Calculates keyword density (targets 1.5-2%)
- **Custom instructions:** Guides keyword selection and optimization strategy

### 6. Formatter Node
- Formats content for Ghost CMS
- Ensures proper Markdown syntax
- Fixes heading hierarchy
- Normalizes spacing and line breaks
- Generates visual placement recommendations (hero images, comparison tables, workflow diagrams, charts, screenshots)

### 7. Editor Node (Approval Gate)

**Editorial Scoring (LLM-based, 0-10 each):**
- Cohesiveness & Flow (must score ≥ 7)
- Hook Quality (must score ≥ 7)
- Storytelling & Examples (must score ≥ 6)
- Authentic Voice (must score ≥ 6)

**Mechanical Requirements (must all pass):**
- ✓ Word count ≥ 95% of target
- ✓ Minimum 10 inline links
- ✓ Exactly 1 H1 heading
- ✓ At least 4 H2 sections

**Approval Paths:**
1. **✅ APPROVED**: All scores meet thresholds and mechanical requirements pass
   - Sets `approval_status: "approved"`
   - Routes to Publisher node

2. **❌ REJECTED + Revisions Available**: Scores or checks fail, attempts < 3
   - Sets `approval_status: "rejected"`
   - Provides specific feedback per dimension (hook, storytelling, voice, mechanics)
   - Increments `revision_count`
   - Routes back to Writer node with editor feedback
   - Writer uses `revision.txt` prompt with targeted guidance for each low-scoring dimension

3. **⚠️ FORCE PUBLISH**: Checks fail, revisions exhausted (≥ 3 attempts)
   - Sets `approval_status: "force_publish"`
   - Prepends editor's note with all scores and unresolved issues
   - Routes to Publisher node with forced note
   - Marks article with warning in logs

### 8. Publisher Node
- Checks for forced publish note and prepends if present
- Saves article to local `output/` directory with timestamp
- Removes H1 title from content (sent separately to avoid duplication)
- Publishes to Ghost CMS with complete metadata:
  - Title (SEO-optimized)
  - Content (formatted, with forced publish note if applicable)
  - Meta description
  - **Excerpt** (for listing pages)
  - Tags
- Publishes as draft or published based on `PUBLISH_AS_DRAFT` setting
- Returns post ID and URL
- Logs warnings if article was force-published

## Social Media Notification System

When a blog post is published to Ghost CMS, an automated notification system sends you an email with AI-generated social media post proposals:

- **LinkedIn post** — Professional tone, optimized for engagement (<3000 chars)
- **Bluesky post** — Conversational tone, concise format (<300 chars)

### How It Works

```
Blog Published → Ghost CMS → Ghost Webhook → Next.js API Route → Email
                                                      ↓
                                             Anthropic API
                                           (generates posts)
```

The webhook is handled by the Next.js app at `/api/webhook/ghost`. Ghost calls this endpoint whenever a post is published, the route generates social copy using Claude, and delivers it via Mailgun.

### Setup

Requires:
1. Mailgun account (free tier: 5,000 emails/month)
2. Ghost CMS webhook pointing to your deployed web URL: `https://your-web-url.com/api/webhook/ghost`

Add to your web environment:
```env
MAILGUN_API_KEY=your_mailgun_api_key
MAILGUN_DOMAIN=your_mailgun_domain
EMAIL_FROM=noreply@yourdomain.com
EMAIL_TO=you@youremail.com
ANTHROPIC_API_KEY=your_anthropic_api_key
```

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
| `BLOG_TONE` | informative and insightful | Writing tone and style |
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

- **Research Node**: All web searches, sources gathered, headline candidates generated
- **Audience Analysis Node**: Target reader persona and pain point identification
- **Writer Node**: LLM prompt and full article generation (with audience context and headlines)
- **Fact Checker Node**: Web searches for claim verification and LLM fact assessment
- **SEO Node**: SEO analysis, optimization, and excerpt generation
- **Formatter Node**: Content formatting transformations and visual recommendations
- **Editor Node**: Editorial scoring (cohesiveness, hook, storytelling, voice) and quality validation
- **Publisher Node**: Ghost CMS API calls

### Example Trace View

```
Blog Generation Run (4m 30s)
├── research_node (45s)
│   ├── BraveSearchTool: "AI trends" (3s)
│   ├── BraveSearchTool: "machine learning 2026" (2s)
│   └── LLM Call: Research summary + headlines (40s)
├── audience_analysis_node (20s)
│   └── LLM Call: Audience persona + pain points (20s)
├── writer_node (2m 15s)
│   └── LLM Call: Generate 3500 word article (2m 15s)
├── fact_checker_node (30s)
│   ├── BraveSearchTool: Verify claim 1 (5s)
│   ├── BraveSearchTool: Verify claim 2 (5s)
│   └── LLM Call: Fact check assessment (20s)
├── formatter_node (5s)
│   └── LLM Call: Format for Ghost CMS + visual suggestions (5s)
├── seo_node (20s)
│   └── LLM Call: SEO optimization + excerpt generation (20s)
├── editor_node (15s)
│   └── LLM Call: Score cohesiveness, hook, storytelling, voice (15s)
└── publisher_node (7s)
    └── GhostCMSTool: Publish with excerpt to CMS (7s)
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
  - At least one LLM API key is required (ANTHROPIC_API_KEY or OPENROUTER_API_KEY)
```

Ensure your `.env` file has at least one LLM API key configured.

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
