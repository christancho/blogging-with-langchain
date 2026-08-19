# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a LangGraph-based blog generation system that creates comprehensive, SEO-optimized articles and publishes them to Ghost CMS. The system uses a state graph workflow with 8 nodes, a fact-check gate, an editor approval gate, and two revision loops (max 3 attempts each).

- Setup, usage, and workflow/node behavior (including the editor's actual approval criteria): [`README.md`](README.md)
- Implementation-level reference for extending the codebase — node internals, extension procedures, state fields, SSE log-streaming internals: [`docs/architecture.md`](docs/architecture.md)

## Important Guidelines for Claude Code

**Git Operations:**

- **Do NOT automatically commit changes** unless explicitly requested by the user
- **Do NOT automatically push to remote** unless explicitly requested by the user
- Always ask for confirmation before creating commits or pushing code
- If the user asks for changes, make the changes but let them decide when to commit

## Git Workflow

Full reference: [`docs/git-strategy.md`](docs/git-strategy.md).

**Branch model:** `main` (production) ← `stg` (staging) ← `dev` (integration) ← `feature/{issue-number}-{slug}` (all feature work).

- Branch from `dev`, target `dev`. Never branch from or PR directly into `stg`/`main` — promotion between them is automated (see below).
- Never commit directly to `dev`, `stg`, or `main`.

**Starting work:**

```bash
git checkout dev && git pull
git checkout -b feature/42-add-login
```

On an existing branch, run `git merge dev` first to pick up anything merged since the branch was cut.

**Commits:** Conventional commits, no emojis (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`).

**Pull requests:** Target `dev` only. Body must include a Summary, a Test plan, and one `Closes #N` (or `Fixes`/`Resolves`) line per issue resolved — this drives the GitHub Projects automation in Task Management below. Title short and imperative, under 70 characters. Merging into `main`, `stg`, or `dev` requires 1 approving code-owner review (`.github/CODEOWNERS`).

**Promotion (fully automated — never open these by hand):** once a feature PR merges to `dev`, `.github/workflows/pr-to-stg.yml` auto-creates a `dev → stg` PR, and merging that triggers `pr-to-main.yml` to auto-create `stg → main`. Both are titled `promote: {from} -> {to}`. Merge them when ready to advance a release.

## Behavioral Guidelines

> Inspired by [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)

### 1. Think before coding

Before implementing anything:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick one silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity first

Write the minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical changes

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that **your** changes made unused. Don't remove pre-existing dead code unless asked.

Every changed line should trace directly to the user's request.

### 4. Goal-driven execution

Transform tasks into verifiable goals before starting:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan upfront:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

##  Code Style and Conventions

- **No silent error swallowing**: Never use bare `except: pass` or `except Exception: pass` (or equivalent) that silently discard errors. Every `except` block must at minimum log or print the error. If a fallback is used, the error must still be visible in the output. Errors that are caught and hidden are bugs waiting to happen.
- **No fabricated metrics**: Quality signals (editor cohesiveness score, SEO metrics, content-analyzer stats, etc.) must come from the LLM assessment or a real computation — never hardcode or guess a plausible-looking number. If a value can't be computed yet, return `None`/`null` rather than a magic number. This doesn't apply to `Config` thresholds (`WORD_COUNT_TARGET`, `MIN_INLINE_LINKS`, etc.) — those are deliberately-set configuration, not computed output.
- **Docstrings**: All functions have docstrings explaining args, returns, and purpose
- **Type hints**: Used throughout (BlogState, Config, node functions)
- **Error handling**: Accumulate errors in state rather than raising exceptions
- **Logging**: Use print statements for user feedback (not logging module)
- **File structure**: Organized by responsibility (agentic/nodes, agentic/tools, agentic/prompts, tests)

## Task Management

Tracked in **GitHub Projects** (board #13 — [https://github.com/christancho/blogging-with-langchain/projects](https://github.com/christancho/blogging-with-langchain/projects)). Full flow: `docs/git-strategy.md`.

- Use `gh issue create` for new work. New issues are auto-added to the board as **Backlog** by `.github/workflows/issue-to-backlog.yml`.
- Status moves are automated end-to-end — don't hand-drag cards, and don't hand-set an item to Done and assume the issue closed:
  - **Backlog → Ready**: manual, during triage/grooming (the one human step in the flow)
  - **Ready → In Progress**: automatic when a `feature/{issue}-{slug}` branch is pushed (`issue-to-in-progress.yml`)
  - **In Progress → In Review**: automatic when a PR targeting `dev` includes a `Closes #N` line (`issue-to-in-review.yml`)
  - **In Review → Done**: automatic when that PR merges into `dev` (`pr-to-stg.yml`)
- Every PR body must include `Closes #N` for each issue it resolves — this is what the board automation keys off of; omitting it breaks the board regardless of whether GitHub's native issue-closing also fires.
- `.github/project-config.json` holds the board's GraphQL node IDs and must stay in sync across `main`, `dev`, and `stg`. Don't hand-edit it — regenerate via the GraphQL calls in the PR that first wired it up if it ever needs to change.
- Do NOT use TodoWrite, task files, or in-session task lists as a substitute for tracking multi-step feature work — GitHub Issues is the source of truth.

##  Self-Correcting Rules Engine

This file contains a growing ruleset that improves over time. **At session start, read the entire "Learned Rules" section before doing anything.**

### How it works

1. When the user corrects you or you make a mistake, **immediately append a new rule** to the "Learned Rules" section at the bottom of this file.
2. Rules are numbered sequentially and written as clear, imperative instructions.
3. Format: `N. [CATEGORY] Never/Always do X — because Y.`
4. Categories: `[STYLE]`, `[CODE]`, `[ARCH]`, `[TOOL]`, `[PROCESS]`, `[DATA]`, `[UX]`, `[OTHER]`
5. Before starting any task, scan all rules below for relevant constraints.
6. If two rules conflict, the higher-numbered (newer) rule wins.
7. Never delete rules. If a rule becomes obsolete, append a new rule that supersedes it.

### When to add a rule

- User explicitly corrects your output ("no, do it this way")
- User rejects a file, approach, or pattern
- You hit a bug caused by a wrong assumption about this codebase
- User states a preference ("always use X", "never do Y")

### Rule format example

```
14. [CODE] Always use `bun` instead of `npm` — user preference, bun is installed globally.
15. [STYLE] Never add emojis to commit messages — project convention.
16. [ARCH] API routes live in `src/server/routes/`, not `src/api/` — existing codebase pattern.
```

---

## Learned Rules

<!-- New rules are appended below this line. Do not edit above this section. -->

1. [PROCESS] Never commit non-trivial logic (algorithms, calculations, data transformations) without first verifying it against real output — passing tests are not sufficient if the logic was never actually run.
2. [CODE] Never write empty or silent error handlers — every caught error must either re-throw, be logged with explicit source attribution, or be stored somewhere visible. If an error is genuinely safe to ignore, add a comment explaining the invariant that guarantees it.
3. [CODE] Never suppress compiler or runtime warnings — always fix the root cause. Warnings exist for a reason; silencing them hides real problems.
4. [CODE] Never fire-and-forget operations that can fail — background tasks must persist their result (success or error) somewhere the user can see it. Logging to console alone is not enough for user-facing operations.
5. [PROCESS] Always choose Subagent-Driven execution (never Inline Execution) when the writing-plans skill's handoff offers a choice — user default preference, stated explicitly. Proceed with it directly without asking again.

