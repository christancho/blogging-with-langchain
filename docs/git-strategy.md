# Git Strategy

Three-environment trunk-based flow with automated GitHub Projects lifecycle. Each unit of work is a feature branch → PR → `dev` → staging → production.

---

## Branch Model

```
main   ← production (protected)
stg    ← staging  (protected)
dev    ← integration (protected)
  └── feature/123-slug  ← all feature work
```

**Rules:**
- All feature work branches from `dev`, targets `dev`
- Never branch from `stg` or `main`
- Never PR directly into `stg` or `main` — promotion is automated
- Never commit directly to `dev`, `stg`, or `main`

---

## Branch Naming

```
feature/{issue-number}-{slug}
```

Examples:
- `feature/42-add-login`
- `feature/18-user-dashboard`
- `feature/103-fix-signup-error`

The number is the GitHub issue number for the work being done. The slug is a short description — kebab-case, 2–4 words.

---

## Starting a Feature Branch

```bash
git checkout dev
git pull
git checkout -b feature/42-add-login
```

At the start of any resumed work session on an existing branch:

```bash
git merge dev
```

Always merge latest `dev` before doing anything — features merged to `dev` after your branch was cut are otherwise invisible.

---

## Commit Conventions

Conventional commits, no emojis:

```
feat: add user login page
fix: handle empty email on signup
chore: upgrade dependencies
docs: document deployment process
refactor: extract auth logic into separate module
```

---

## Pull Requests

### Target

Always target `dev`. Never `stg` or `main`.

### Body (required)

Every PR must include:

1. **Summary** — bullet list of what changed
2. **Test plan** — what was verified
3. **Closes lines** — one per issue the PR resolves

```markdown
## Summary
- Added user login with email and password
- Redirects to dashboard on success

## Test plan
- [x] Tested valid login flow
- [x] Tested invalid credentials error message

Closes #42
```

The `Closes #N` lines drive GitHub Projects automation — do not omit them.

### Title

Short, imperative, under 70 characters:

```
feat: add user login page
```

### Review

This repo is public. `main`, `stg`, and `dev` all require **1 approving review from a code owner** before a PR can merge (see [CODEOWNERS](../.github/CODEOWNERS) — currently `@christancho` for everything). External contributors cannot merge their own PRs. The repo owner can — GitHub's "merge without waiting for requirements to be met" bypass is available to the Admin role on this rule (see [Branch Protection Rules](#branch-protection-rules) below).

---

## Promotion Pipeline (Automated)

Once a feature PR merges to `dev`, GitHub Actions handles the rest:

```
feature branch → dev   (manual PR, human review)
dev → stg              (auto-created PR, merge when ready to test)
stg → main             (auto-created PR, merge when ready to release)
```

The `dev→stg` PR is created automatically on every merge to `dev`. The `stg→main` PR is created automatically on every merge to `stg`. Both are titled `promote: {from} -> {to}` with a commit log in the body.

**Important:** these promotion PRs use `dev` and `stg` themselves as the PR *head* branch. If your repo has "Automatically delete head branches" enabled in Settings → General, GitHub will delete `dev`/`stg` the moment their promotion PR merges. This repo has that setting turned **off** for exactly that reason — don't turn it back on.

---

## GitHub Projects Status Flow

| Status | Trigger | How |
|---|---|---|
| **Backlog** | Issue created | Automated — `issue-to-backlog` workflow |
| **Ready** | PM triages and prioritises | Manual — PM moves card |
| **In Progress** | `feature/*` branch pushed | Automated — GitHub Action |
| **In Review** | PR opened with `Closes #N` | Automated — GitHub Action |
| **Done** | PR merged to `dev` | Automated — built-in GitHub Projects |

Board: https://github.com/christancho/blogging-with-langchain/projects (project #13)

Two manual moves in the whole flow: PM moves **Backlog → Ready** during grooming; developer moves nothing — branch creation and PR events handle everything else.

Use a **Blocked** label (not a column) when an issue is stuck. An issue can be `In Progress + Blocked` which is more expressive than a separate column that's usually empty.

---

## GitHub Actions Workflows

Six workflows wire up the automation. Each reads `.github/project-config.json` for node IDs and uses `GH_PAT` (a personal access token with `repo` + `project` scopes) as `GH_TOKEN`.

| File | Trigger | Action |
|---|---|---|
| `issue-to-backlog.yml` | Issue opened | Adds issue to board → Backlog |
| `issue-to-in-progress.yml` | `feature/*` branch pushed | Issue → In Progress |
| `issue-to-in-review.yml` | PR opened → `dev` | Issues → In Review |
| `pr-to-stg.yml` | PR merged → `dev` | Issues → Done + create `dev→stg` PR |
| `pr-to-main.yml` | PR merged → `stg` | Create `stg→main` PR |
| `gitleaks.yml` | Push, PR, weekly schedule | Scans full history for leaked secrets |

The helper script `.github/scripts/move-issue.sh <issue_number> "<Status Name>"` handles the GraphQL mutation. Workflows call it in a loop over extracted issue numbers.

---

## Project Config File

`.github/project-config.json` stores the GitHub Projects node IDs so workflows don't hardcode them. Must exist, populated, on **all three** of `main`, `dev`, and `stg` — different workflows check it out from different branches depending on their trigger (issue-opened events read the default branch, `main`; branch-push events read whatever branch was pushed). Do not edit by hand — regenerate via the GraphQL calls in the PR that first wired this up if it ever needs to change.

```json
{
  "project_node_id": "PVT_...",
  "status_field_id": "PVTSSF_...",
  "options": {
    "Backlog":      "...",
    "Ready":        "...",
    "In Progress":  "...",
    "In Review":    "...",
    "Done":         "..."
  }
}
```

---

## Branch Protection Rules

Applied via two separate GitHub **Rulesets** (Settings → Rules → Rulesets), both targeting `main`, `stg`, and `dev`:

### "Require review to merge"

| Rule | Value |
|---|---|
| `required_approving_review_count` | 1 |
| `require_code_owner_review` | `true` |
| `require_last_push_approval` | `true` |
| Bypass | Admin role, always |

### "Block deletion of dev, stg, main"

| Rule | Value |
|---|---|
| `deletion` | restricted |
| `non_fast_forward` | restricted (no force pushes) |
| Bypass | **none — not even Admin** |

These are deliberately two separate rulesets rather than one. GitHub ruleset bypass permissions apply to every rule inside a ruleset, not per-rule — splitting review (bypassable, so the repo owner can merge their own PRs) from deletion (never bypassable, so a promotion-PR merge or a stray `git push --delete` can't destroy `dev`/`stg`/`main`) requires two rulesets, not one.

To temporarily allow deleting/rewriting one of these branches on purpose, disable or edit the "Block deletion" ruleset first, do the operation, then restore it.

---

## Required Secrets

| Secret | Scope | Used for |
|---|---|---|
| `GH_PAT` | `repo`, `project` | All GitHub Actions — moves issues, creates promotion PRs |

---

## GitHub Project Fields

| Field | Type | Options |
|---|---|---|
| **Status** | Single select | Backlog, Ready, In Progress, In Review, Done |
| **Priority** | Single select | P0 (critical), P1 (high), P2 (normal) |
| **Size** | Single select | XS, S, M, L, XL |
| **Estimate** | Number | Story points or hours |

Plus GitHub's built-in fields: Assignees, Labels, Milestone, Linked pull requests, Reviewers, Parent issue.
