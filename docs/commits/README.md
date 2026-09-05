# Deferred-Commit Ledger — Schema & Replay Procedure

This directory holds the **commit ledger**: the record of every intended git commit for
HealthyVytals, created while git is not yet initialized (see `DESIGN.md` §9A.6). When git
becomes available, the ledger is replayed to reconstruct a clean, linear history that shows
exactly how the application was built — **one functionality per commit, in order**.

## Files

| File | Role |
|---|---|
| `ledger.json` | **Source of truth.** Machine-readable, ordered array of commit entries. Replay reads this. |
| `../COMMIT_LEDGER.md` | Human-readable mirror of the same entries (for review/skimming). |
| `README.md` | This file — schema + replay instructions. |

`ledger.json` and `COMMIT_LEDGER.md` MUST stay in sync. `ledger.json` wins if they diverge.

## `ledger.json` schema

```jsonc
{
  "project": "HealthyVytals",
  "generator": "AI-assisted incremental build (DESIGN.md §9A.6)",
  "repo_root": "healthyvytals/",          // paths in entries are relative to this
  "ledger_version": 1,
  "commits": [
    {
      "seq": 1,                            // 1-based, strictly increasing, = commit order
      "id": "c001",                        // stable short id
      "message": {
        "subject": "feat(core): add env-driven application settings",
        "body": "Implements TASKS 0.3. SQLite default per ADR-0001...\n\nRefs: DESIGN §7, §12.2"
      },
      "files": [                           // exact paths to `git add`, in order
        "backend/app/core/config.py",
        "backend/app/core/__init__.py"
      ],
      "task_ids": ["0.3"],                 // TASKS.md rows satisfied
      "rule_refs": ["§12.2"],              // DESIGN.md rules/sections, if any
      "phase": 0,
      "rationale": "One-line why this slice exists.",
      "depends_on": []                     // seqs that must be committed before this one
    }
  ]
}
```

### Field rules
- **seq** — 1-based, contiguous, never reused. Order is the commit order.
- **message.subject** — Conventional Commits (`type(scope): summary`), imperative, ≤72 chars.
- **message.body** — the *why*; references TASKS ids and DESIGN sections. May be multi-line.
- **files** — every path that belongs to this commit and **only** this commit. A file may
  appear in a later commit again if it is legitimately modified by a later slice.
- **Append-only** — never edit or delete a past entry. To change earlier files, add a new
  commit entry (mirrors immutable git history).

## Replay procedure (once git is initialized)

Give this file + `ledger.json` to an AI or run a script. For each entry in `commits`,
ordered by `seq`:

```bash
cd healthyvytals/           # = repo_root
git add <files[0]> <files[1]> ...          # exactly the entry's files, in listed order
git commit -m "<subject>" -m "<body>"       # exact message from the entry
```

Guidance for the replay agent:
1. Process strictly in `seq` order; honor `depends_on`.
2. `git add` **only** the files listed for that entry — do not `git add .`.
3. Use the message verbatim. Do not rewrite it.
4. If a listed file is missing on disk, **stop and report** — do not improvise.
5. After the last entry, the working tree should be clean and the history linear.

The end state: a commit graph where reading `git log` top-to-bottom is a step-by-step
narrative of how HealthyVytals was constructed.
