Initialization
initialize_project MCP result
Criteria: agent initializes through MCP.
Tokens: activation JSON, gitignore result, category names, compact contract, first workflow.

initialize-project skill/CLI result
Criteria: agent initializes through skill adapter.
Tokens: same shape as MCP: activation + gitignore + category list + compact contract + workflow.

@recall initialize this project hook response
Criteria: user initializes through prompt hook.
Tokens: short “RECALL activated for project …” message.

Current provider skill load for initialization
Criteria: agent uses using-recall or manage-memory/initialize skill.
Tokens: invoked SKILL.md instructions.

Every Active Session / Startup
SessionStart hook context
Criteria: project active and provider runs SessionStart hook.
Tokens: compact contract + store overview.
Hard cap: 2000 chars ≈ ~500 tokens.

MCP initialize instructions
Criteria: current provider starts RECALL MCP server.
Tokens: compact contract in MCP instructions.

MCP tool schemas/descriptions
Criteria: current provider exposes RECALL MCP tools.
Tokens: tool names, descriptions, input schemas.

Provider skill registry metadata
Criteria: provider exposes RECALL skills.
Tokens: skill names/descriptions/frontmatter. Usually small.

Kimi skillInstructions / sessionStart skill
Criteria: current provider is Kimi and plugin sessionStart loads using-recall.
Tokens: manifest instruction and possibly using-recall skill text.

Every User Prompt, Conditional Output
UserPromptSubmit relevance assessment itself
Tokens: zero. Local only.

Auto memory context injection
Criteria: active project + persistent memory + recall_mode=always, or recall_mode=relevant and relevance passes, or explicit RECALL invocation.
Tokens: curated memory cards.
Cap: min(config token_budget, 900).

Explicit RECALL no-project warning
Criteria: explicit RECALL invocation but no project root signal.
Tokens: short setup warning.

Explicit capture-off warning
Criteria: explicit remember/define cue while capture_mode=off.
Tokens: short “capture is off” recovery text.

Explicit remember saved message
Criteria: @recall remember this… saves memory.
Tokens: short saved-memory message.

Explicit define-category message
Criteria: @recall define category….
Tokens: category result text.

Insufficient-memory message
Criteria: explicit RECALL invocation, no useful memory found.
Tokens: short “not enough relevant memory” message.

Conflict alert line
Criteria: retrieval context returned and unresolved claim conflicts exist.
Tokens: one alert line.

Tool/Skill Calls During Work
retrieve_memory MCP result / retrieve-memory skill result
Criteria: agent calls retrieval.
Tokens: query, results, health flags.
Big if limit high, card content long, summary=true, or verbose=true.

context_packet MCP/skill result
Criteria: agent asks for context packet.
Tokens: budgeted memory packet.
Default budget: 1200.

save_insight MCP/skill result
Criteria: agent saves memory.
Tokens: save result, id/category, maybe metadata/next_action.

update_memory / manage-memory lifecycle result
Criteria: agent edits/confirms/stales/supersedes/merges/prunes.
Tokens: record ids/status/metadata, sometimes old+new records.

review_memory / audit-memory result
Criteria: agent reviews store.
Tokens: inventory/health/issues. Grows with limit.

memory_hygiene route result
Criteria: agent asks whether candidate belongs in memory.
Tokens: small route decision.

memory_hygiene scan/plan/apply_safe result
Criteria: agent runs hygiene.
Tokens: proposals/actions. Can grow with issue count/limit.

memory_contract / contract result
Criteria: agent asks for contract.
Tokens: full contract + full category guidance. Large.

list-categories / define-category result
Criteria: agent lists or changes categories.
Tokens: category descriptions/examples/non_examples/update_rules. Large-ish.

doctor, repair, backup, restore, import, export, debug-tail, reconcile-*, refresh-* results
Criteria: diagnostics/recovery used.
Tokens: report JSON. debug-tail can be large.

Tool Hooks During Work
PostToolUse normal path
Criteria: tools run.
Tokens: usually zero; outputs only {"continue": true}. Evidence buffering local.

PreCompact normal path
Criteria: compaction hook runs.
Tokens: zero; outputs only {"continue": true}. Summary storage local.

Stop quiet finalizer message
Criteria: dirty buffered events + quiet mode + saved/corroborated memory.
Tokens: short “RECALL saved/updated N memories.”

Stop debug finalizer prompt
Criteria: observability_mode=debug and dirty events.
Tokens: finalizer prompt + packet summary. Expensive; debug-only.

Hook error messages
Criteria: hook exception.
Tokens: short failure message.