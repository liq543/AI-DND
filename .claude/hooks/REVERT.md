# Reverting the DM rules hooks to the old setup

**Current setup (since the token-saving change):**
- `dm/turn-rules.md` goes in before every prompt.
- `dm/standing-orders.md` goes in at session start and after each compaction.
- Before shell commands, only the area or creature checklist is added, and only for engine commands that build or show
  an area (`map gen` / `map import-grid` / `map show` / `scene`) or add creatures (`npc add` / `encounter spawn`).
- The Stop check is a short list. It runs only on turns that ran engine commands that change the game.

**Old setup:** the full digest plus the standing orders on every prompt, before and after every tool call, and in every
Stop check. It's saved in git as the tag `hooks-v1-per-tool-call`.

## To revert (run from the repo root)

```bash
git checkout hooks-v1-per-tool-call -- .claude/settings.json .claude/hooks/dm_rules.py dm/turn-rules.md dm/standing-orders.md
```

Then commit. That restores the four files exactly as they were. One caveat: any standing orders added after the change
would need to be re-added to the restored `dm/standing-orders.md`. Compare with
`git diff hooks-v1-per-tool-call -- dm/standing-orders.md` first.

## To revert just one part

- **Per-tool-call injection back:** in `.claude/settings.json`, set the `PreToolUse` matcher back to `"*"` and re-add
  the `PostToolUse` block from the tag.
- **Full digest in the Stop check:** use the tag's `dm_rules.py`.
- **Standing orders per prompt:** have `UserPromptSubmit` print the orders too. Keep the total under ~10 KB, or the
  payload gets cut to a preview.
