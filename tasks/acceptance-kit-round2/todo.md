# Todo: acceptance-kit-round2

- [x] Task 1: Probe what `${CLAUDE_PLUGIN_ROOT}` names for a `directory` marketplace (D53, open question) — user agreed 2026-10-08. Throwaway plugin `rootprobe` (one skill printing `ROOT=${CLAUDE_PLUGIN_ROOT}` and a marker line) in a throwaway `directory` marketplace under the scratchpad; snapshots of `installed_plugins.json`, `known_marketplaces.json`, `~/.claude/settings.json` first. `claude plugin marketplace add` (user settings) → `claude plugin install rootprobe@rootprobe-marketplace --scope local` in a scratch project: the record's `installPath` is the cache `~/.claude/plugins/cache/rootprobe-marketplace/rootprobe/0.0.1` and a copy was made there. `claude -p "/rootprobe:where"` → `ROOT=<scratchpad>/rootprobe/market/plugins/rootprobe` (the **source directory**, not the cache), `MARKER=version-one`. Changed the marker in the source only (the cache copy still says version-one) and ran again → `MARKER=version-two`, same ROOT: for a `directory` marketplace Claude loads the skill from the source live, and `${CLAUDE_PLUGIN_ROOT}` names that source; the `installPath` record and its cache copy are not what a session uses (matches the coordinator's R2-11 observation). Cleanup: plugin uninstalled, marketplace removed; all three snapshot files identical afterwards (JSON compared). Left behind: the cache directory `~/.claude/plugins/cache/rootprobe-marketplace/rootprobe/0.0.1` that `uninstall` did not remove (ours, harmless; deleting it is left to the user) and the scratch project's `.claude/settings.local.json` (`enabledPlugins: {}`, inside the scratchpad)
- [ ] Checkpoint (gate): Task 1 result and the D53 variant, reported to the user
- [ ] Task 2: Tree hash and stale copies in preflight (D54)
- [ ] Task 3: Allow lists, `--design`, launch line (D55, D56)
- [ ] Task 4: One root-resolution block in the three skills (D53)
- [ ] Task 4b: One node and one read for install, upgrade, retire and cleanup (D57, R2-12)
- [ ] Task 5: Docs
- [ ] Task 6: Live (read only, plus a temporary home for D57)
- [ ] Checkpoint (gate): module review
