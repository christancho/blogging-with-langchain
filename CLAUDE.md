# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a LangGraph-based blog generation system that creates comprehensive, SEO-optimized articles and publishes them to Ghost CMS. The system uses a state graph workflow with 6 nodes, an editor approval gate, and a revision loop (max 3 attempts).

## Important Guidelines for Claude Code

**Git Operations:**
- **Do NOT automatically commit changes** unless explicitly requested by the user
- **Do NOT automatically push to remote** unless explicitly requested by the user
- Always ask for confirmation before creating commits or pushing code
- If the user asks for changes, make the changes but let them decide when to commit

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys
```

### Running the System
```bash
# Generate a blog post
python main.py "Your blog topic here"

# With custom tone
python main.py "Topic" --tone "conversational and engaging"

# With custom instructions
python main.py "Topic" --instructions "Focus on practical examples for beginners"

# Enable debug mode
python main.py "Topic" --debug

# Visualize the workflow graph
python main.py --visualize
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_tools.py

# Run with coverage
pytest --cov=. --cov-report=html

# Run with verbose output
pytest -v

# Run golden tests (regression tests with saved outputs)
pytest tests/golden_tests/
```

## Architecture

### State Graph Workflow
The system uses LangGraph's StateGraph with conditional routing:

```
Research → Writer → Formatter → SEO → Editor → Publisher
                      ↑                   |
                      |                   | (if rejected)
                      └───────────────────┘
                          (revision loop, max 3x)
```

**Key Files:**
- `graph.py`: StateGraph definition, conditional routing logic, and workflow orchestration
- `state.py`: BlogState TypedDict defining all state fields
- `config.py`: Configuration management with automatic LLM fallback (Anthropic → OpenRouter)

### Node Architecture
All nodes follow a consistent pattern:
1. Receive current `BlogState`
2. Perform specific task (research, write, format, etc.)
3. Return dict updates to merge into state
4. Never mutate state directly

**Node files** (`nodes/` directory):
- `research.py`: Web search via Brave API, generates research summary
- `writer.py`: Handles both initial writing and revisions (checks `revision_count` to decide which prompt to use)
- `formatter.py`: Normalizes Markdown, fixes heading hierarchy (ensures 1 H1)
- `seo.py`: Generates SEO metadata (title, description, excerpt, tags, keywords)
- `editor.py`: Quality gate with approval/rejection logic, sets `approval_status` and `revision_count`
- `publisher.py`: Saves locally and publishes to Ghost CMS

### Prompt System
Prompts are Jinja2 templates stored in `prompts/*.txt` and loaded via `PromptLoader` utility:

- `research.txt`: Research planning and source gathering
- `writer.txt`: Initial article generation (3500+ words)
- `revision.txt`: Article revision based on editor feedback
- `formatter.txt`: Content formatting and cleanup
- `seo.txt`: SEO optimization
- **Note**: No separate `editor.txt` - editor node uses Python logic for quality checks

**Loading prompts:**
```python
from nodes.prompt_loader import PromptLoader

template = PromptLoader.load("writer")
prompt = template.render(
    topic=state["topic"],
    tone=Config.BLOG_TONE,
    research=state["research_summary"],
    # ... other context variables
)
```

### Tools Architecture
Tools in `tools/` provide utilities for each node:

- `brave_search.py`: Web search integration
- `content_analyzer.py`: Quality analysis (word count, link count, structure)
- `seo_analyzer.py`: SEO metrics calculation
- `tag_extractor.py`: Tag extraction from content
- `html_formatter.py`: Markdown/HTML formatting
- `ghost_cms.py`: Ghost Publishing API integration

## Conditional Routing Logic

The editor node acts as an approval gate with three possible outcomes:

1. **Approved** (`approval_status: "approved"`): All quality checks pass → route to Publisher
2. **Rejected** (`approval_status: "rejected"`): Checks fail, revisions available → route back to Writer
3. **Force Publish** (`approval_status: "force_publish"`): Checks fail, max revisions reached → route to Publisher with warning note

**Quality Checks** (all must pass for approval):
- Word count ≥ 3500
- Inline links ≥ 10
- Exactly 1 H1 heading
- At least 4 H2 sections
- Well-structured content

**Implementation**: See `route_editor_decision()` in graph.py:52

## Configuration System

The `Config` class in config.py handles all settings with automatic fallback:

**LLM Fallback Chain:**
1. Try Anthropic Claude (primary)
2. Fall back to OpenRouter if Anthropic fails
3. Requires at least one API key

**Key Settings:**
- `WORD_COUNT_TARGET`: 3500
- `MIN_INLINE_LINKS`: 10
- `NUM_SECTIONS`: 4
- `BLOG_TONE`: "informative and insightful" (override with --tone)
- `PUBLISH_AS_DRAFT`: true
- `MAX_REVISIONS`: 3

**Environment Variables:** All loaded from `.env` (see .env.example for template)

## LangSmith Integration

Optional tracing/debugging via LangSmith:

**Enable:**
```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key
LANGCHAIN_PROJECT=blog-generation
```

**What gets traced:**
- Each node execution with inputs/outputs
- All LLM calls with prompts and responses
- Token usage and costs
- Execution timeline and duration

## Common Development Tasks

### Adding a New Quality Check
1. Update `editor.py`: Add check logic to editor_node()
2. Update `state.py`: Add new field to `quality_checks` dict if needed
3. Update `revision.txt`: Include new check in revision guidance

### Modifying a Prompt
1. Edit the corresponding `.txt` file in `prompts/`
2. Templates use Jinja2 syntax: `{{ variable }}`, `{% if %}`, etc.
3. Clear cache in development: `PromptLoader.clear_cache()`
4. Test changes with `python main.py "test topic" --debug`

### Adding a New Node
1. Create `nodes/new_node.py` with function signature: `def new_node(state: BlogState) -> dict`
2. Add to `nodes/__init__.py`
3. Update workflow in `graph.py`: `workflow.add_node("new_node", new_node)`
4. Add edges: `workflow.add_edge("previous", "new_node")`
5. Update `state.py` with new output fields

### Changing the Workflow Order
**Current:** Research → Writer → Formatter → SEO → Editor → Publisher

To modify:
1. Update edges in `graph.py`: `workflow.add_edge(source, target)`
2. Update conditional routing if needed: `route_editor_decision()`
3. Regenerate visualization: `python main.py --visualize`
4. Update documentation and diagrams

## Testing Guidelines

### Unit Tests
- Test files mirror source structure: `tests/test_tools.py` tests `tools/*.py`
- Use pytest fixtures for common setup
- Mock external APIs (Brave, Anthropic, Ghost)
- Test each tool independently

### Golden Tests
Located in `tests/golden_tests/`:
- Store expected outputs for regression testing
- Verify workflow produces consistent results
- Update golden files when intentionally changing output format

### Testing a Workflow Change
1. Add unit tests for new node/tool logic
2. Run full workflow with test topic: `python main.py "test topic"`
3. Verify output in `output/` directory
4. Check all quality checks pass (word count, links, structure)

## State Management

The `BlogState` TypedDict flows through the entire graph. Key principles:

- **Immutable updates**: Nodes return dicts that merge into state
- **Typed fields**: All fields defined in state.py with type hints
- **Optional fields**: Uses `total=False` to allow partial state
- **No direct mutation**: Never modify state in-place

**Critical state fields:**
- `approval_status`: Controls routing ("approved", "rejected", "force_publish")
- `revision_count`: Tracks revision attempts (0-3)
- `editor_feedback`: Passed to writer during revisions
- `final_content`: Set by editor after approval
- `errors` / `warnings`: Accumulate throughout workflow

## Ghost CMS Integration

Publishing to Ghost requires:
- Admin API key (content management)
- API URL (your Ghost instance)
- Author ID (for attribution)

**Implementation:** `tools/ghost_cms.py`

**Publishing logic:**
1. Remove H1 from content (sent separately as title)
2. Prepend forced publish note if applicable
3. Create post with metadata (title, excerpt, meta description, tags)
4. Set status: draft or published (based on `PUBLISH_AS_DRAFT`)
5. Return post ID and URL

## Debugging Tips

### Enable Debug Mode
```bash
python main.py "topic" --debug
```
Shows detailed error traces and execution flow.

### Check Intermediate Outputs
Set in .env:
```env
SAVE_INTERMEDIATE_OUTPUTS=true
```
Saves state after each node execution.

### LangSmith Tracing
Essential for debugging LLM calls:
- View exact prompts sent to LLM
- See full responses and token usage
- Identify which node is causing issues
- Replay failed runs

### Common Issues

**"Configuration validation failed":**
- Missing required API keys in .env
- At least one of ANTHROPIC_API_KEY or OPENROUTER_API_KEY required
- Check .env.example for template

**Articles rejected repeatedly:**
- Check editor feedback in console output
- Verify word count target is reasonable
- Ensure research provides enough sources for inline links
- Review quality checks in editor.py:editor_node()

**Ghost publishing fails:**
- Verify Ghost Admin API key is valid (not Content API key)
- Check GHOST_API_URL format (https://yoursite.com)
- Ensure GHOST_AUTHOR_ID is correct

## Code Style and Conventions

- **Docstrings**: All functions have docstrings explaining args, returns, and purpose
- **Type hints**: Used throughout (BlogState, Config, node functions)
- **Error handling**: Accumulate errors in state rather than raising exceptions
- **Logging**: Use print statements for user feedback (not logging module)
- **File structure**: Organized by responsibility (nodes, tools, prompts, tests)
