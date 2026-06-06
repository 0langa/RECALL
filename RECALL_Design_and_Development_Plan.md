# RECALL Design and Development Plan

## Executive Summary

RECALL (Retrieval, Ergonomics & Context Automation for Lifecycle Learning) is a local-first, self-contained Codex plugin that gives coding agents project-specific long-term memory.

It stores decisions, constraints, debugging history, user preferences, and other critical context in a local database and retrieves it across sessions and context resets. This plan extends the earlier memory-plugin design by adding richer categories, including `project_state`, `architecture`, `commands`, `lessons_learned`, `requirements`, and `risks`, and by allowing users to define custom categories.

Research into existing memory systems, including OpenBrain and Mem0, shows that memory can be organised into categories and that schemas can be extended with project-specific labels. RECALL uses these insights to offer flexible, structured memory without any external services.

## Research Findings

- **Structured memory is vital:** Persistent memory systems such as OpenBrain organise information into categories like facts, summaries, decisions, and project context. These categories allow an agent to recall targeted information rather than sifting through entire logs.
- **Customisable schemas:** Because users control the underlying database schema, they can extend it with custom categories to fit their workflow. Mem0 provides a concrete example where developers define `custom_categories` at the project level and retrieve memories using category filters.
- **Category-based retrieval improves relevance:** When categories are attached to memory entries, search functions can filter by category and metadata, such as user ID or priority, to return only the most relevant notes. This reduces token consumption and helps the agent focus on the correct context.
- **Local storage is feasible:** OpenBrain demonstrates that a personal memory layer can run on a local PostgreSQL database with optional vector embeddings. For a plugin, a lightweight local database such as SQLite combined with a vector index suffices.

## Design Principles

1. **Local-first** - All storage and computation happen on the user's machine; no calls to remote APIs.
2. **Self-contained distribution** - The plugin package contains all scripts, models, and dependencies. Users install it once without further setup.
3. **Rich category taxonomy** - RECALL ships with a set of default categories tuned for software projects and allows users to define custom categories at the project level.
4. **Structured and semantic recall** - Entries are tagged with categories and metadata for precise filtering. A local vector index provides semantic search when keywords differ.
5. **Efficiency** - Summaries and filtering keep token usage low. Retrieval selects only the most relevant entries to inject into context.
6. **Security** - The memory store is kept inside the project and added to `.gitignore`. Scripts avoid storing secrets or credentials.

## Memory Categories

RECALL organises memories into structured categories. Each entry stores the `category`, `timestamp`, `content`, and optional `metadata`, such as file path or user ID.

| Category | Purpose |
|---|---|
| `decisions` | Architectural choices, library selections, design rationale, and trade-offs. |
| `constraints` | Hard rules such as banned patterns, dependency pins, naming conventions, and security rules. |
| `debug_history` | Bugs, error patterns, failed attempts, root causes, fixes, and commands that worked. |
| `preferences` | User or project preferences, coding style, formatting rules, and workflow expectations. |
| `tasks` | Completed work, open TODOs, milestones, and current implementation status. |
| `session_summaries` | Compressed summaries of prior sessions to maintain continuity across context resets. |
| `project_state` | Current state of the repository: active branch, pending refactors, known broken areas, and checkpoints. |
| `architecture` | Stable system structure, module responsibilities, data flow diagrams, and overall system design. |
| `commands` | Verified commands for building, testing, linting, and running the project; shell snippets that proved useful. |
| `lessons_learned` | Reusable insights from prior mistakes or successful fixes that guide future development. |
| `requirements` | Explicit user requirements and acceptance criteria that must be met. |
| `risks` | Known fragile areas, performance bottlenecks, and security-sensitive code paths. |

## Custom Categories

RECALL allows projects to define additional categories tailored to their domain. Inspired by OpenBrain's claim that users can extend schemas to fit their workflow and Mem0's example of defining `custom_categories` at the project level, the plugin reads a `memory_config.json` file at the project root.

This file can declare custom category names and descriptions:

    {
      "categories": {
        "decisions": {
          "description": "Architecture and implementation decisions",
          "weight": 1.2
        },
        "project_state": {
          "description": "Current repository status",
          "weight": 1.0
        },
        "custom_api_contracts": {
          "description": "Stable API contracts that must not be broken",
          "weight": 1.5
        },
        "release_notes": {
          "description": "Important release history",
          "weight": 0.8
        }
      }
    }

If a user saves a memory with a category not listed in `memory_config.json`, the plugin adds it automatically with a default weight and logs a warning.

The `weight` parameter adjusts retrieval priority: higher-weighted categories surface more aggressively during recall. Unknown categories are accepted but flagged so the user can refine them.

## Plugin Architecture

The plugin follows the Codex plugin structure and adds a configuration file for categories:

    RECALL/
    ├── .codex-plugin/
    │   └── plugin.json
    ├── skills/
    │   ├── save_insight/
    │   │   └── SKILL.md
    │   ├── retrieve_memory/
    │   │   └── SKILL.md
    │   ├── define_category/
    │   │   └── SKILL.md (optional helper skill)
    │   └── ... (other skills as needed)
    ├── hooks/
    │   ├── hooks.json
    │   └── scripts/
    │       ├── session_start.py
    │       ├── pre_compact.py
    │       ├── post_tool_use.py
    │       ├── prompt_inspector.py
    │       ├── stop.py
    │       └── update_categories.py
    ├── scripts/
    │   ├── memory_manager.py
    │   ├── embedder.py
    │   ├── summarizer.py
    │   └── config.py
    ├── .codex_memory/ (created at runtime)
    │   ├── memory.sqlite (or JSONL files per category)
    │   ├── vector_index.bin
    │   └── memory_config.json (copied from project root or generated)
    ├── assets/
    │   └── icon.svg
    └── README.md

## Manifest: `plugin.json`

The manifest lists the plugin's name, version, description, and paths to the skills and hooks. It is identical in purpose to the previous design but uses `RECALL` as the package name.

## Skills

### 1. `save_insight`

Accepts any valid category. If the category is not in the config, it prompts the user to confirm creation of a custom category and optionally provide its description and weight.

Then it records the new category via `config.py`.

### 2. `retrieve_memory`

Reads the category weights from `memory_config.json` and sorts results accordingly.

Users can specify which categories to include or exclude when calling the skill.

### 3. `define_category` optional helper skill

Lets users create or update categories explicitly.

It takes a category name, description, and weight, then updates `memory_config.json`.

## Hooks

The plugin uses the same lifecycle hooks as before: `SessionStart`, `PreCompact`, `PostToolUse`, `UserPromptSubmit`, and `Stop`.

An additional `UpdateCategories` hook could run when `memory_config.json` changes to reload the categories into memory.

| Event | Script | Functionality |
|---|---|---|
| `SessionStart` | `session_start.py` | Load relevant memory by category and inject summarised context into the conversation. |
| `PreCompact` | `pre_compact.py` | Summarise recent conversation and store it in `session_summaries`. |
| `PostToolUse` | `post_tool_use.py` | Extract errors or commands from tool outputs and save them under `debug_history` or `commands`. |
| `UserPromptSubmit` | `prompt_inspector.py` | Detect "remember this" cues and route to `save_insight`; detect "define category" cues and route to `define_category`. |
| `Stop` | `stop.py` | Flush buffers and finalise the session summary. |

## Memory Storage

RECALL supports two storage backends.

### 1. SQLite Database With a Unified Table

A single `memories` table holds all entries with the following columns:

- `id`
- `category`
- `timestamp`
- `content`
- `metadata`
- `embedding` as `BLOB`

Indexes on `category` and `timestamp` speed up retrieval. SQLite is embedded and requires no installation.

### 2. JSONL Files Per Category

For simpler use cases, RECALL can write each category to a separate `.jsonl` file. This format is easy to inspect but slower to query when the data grows.

Users can choose the backend in `memory_config.json`.

### Vector Index

Regardless of the backend, RECALL maintains a local vector index using FAISS or Chroma in:

    .codex_memory/vector_index.bin

The `embedder.py` script computes embeddings with a bundled sentence transformer model. On save, the embedding is appended to the index. On retrieval, the query embedding is used to perform semantic search.

Category filters and weights from `memory_config.json` narrow the candidate set before summarisation.

## Configuration File: `memory_config.json`

When a project first uses RECALL, a default `memory_config.json` is created in `.codex_memory/` with the built-in categories and their descriptions and weights.

Users can edit this file or invoke the `define_category` skill to add new entries.

| Field | Description |
|---|---|
| `categories` | A dictionary mapping category names to metadata, including `description` and `weight`. |
| `backend` | Storage backend: `sqlite` or `jsonl`. |
| `token_budget` | Maximum number of tokens for injected summaries. |
| `recency_days` | Optional recency filter for retrieval. |
| `embedding_model` | Path to the local embedding model. |
| `summarizer_model` | Path to an optional local summarisation model. |

## Data Flow

### Saving Insights

1. The `save_insight` skill, or the `post_tool_use` / `pre_compact` hooks, calls `memory_manager.add_record(category, content, metadata)`.
2. `memory_manager` validates the category against `memory_config.json`.
3. If the category is unknown, `memory_manager` calls `config.add_category` to register the new category, prompting the user if interactive.
4. The entry is stored in the database or JSONL file with an embedding.
5. The vector index is updated.

### Defining or Updating Categories

1. The optional `define_category` skill, or direct editing of `memory_config.json`, lets users create new categories, change descriptions, or adjust weights.
2. `config.py` writes these changes.
3. The category cache is reloaded.

### Automatic Logging

1. `post_tool_use.py` parses tool outputs, such as Bash errors, and saves them under `debug_history` or `commands`.
2. `pre_compact.py` summarises the recent conversation and saves the summary under `session_summaries` and `lessons_learned` if relevant.
3. `session_start.py` loads summaries from relevant categories, such as `project_state`, `requirements`, and `risks`, and injects them into the conversation.

### Retrieval

1. When the session starts or `retrieve_memory` is called, `memory_manager.query(query_text, categories, k)` filters the database using specified categories and optional recency.
2. The default retrieval scope is all categories except low-weight categories.
3. The query embedding is computed.
4. A vector search is performed on the filtered set.
5. Category weights multiply similarity scores to prioritise critical information.
6. `summarizer.py` condenses the top results to fit within `token_budget`.
7. Summaries are returned to the agent for injection.

## Summarisation and Embedding

To maintain local-first operation, RECALL uses bundled models.

### Embedding

Use a compact sentence transformer, such as `all-MiniLM-L6-v2` or `bge-small-en`, loaded via `sentence-transformers`.

The model is stored in `scripts/models/` and loaded on demand. Embeddings are 384-dimensional and adequate for semantic search on typical project data.

### Summarisation

Start with a heuristic summariser that selects key sentences using TF-IDF or frequency-based scoring. This avoids bundling large models.

For users desiring higher quality, an optional small summarisation model, such as `t5-small`, can be included and selected in `memory_config.json`.

## Security and Privacy

RECALL is entirely local; no network calls occur.

Secrets or credentials should never be stored in memory. Hooks should parse tool outputs cautiously and redact tokens that resemble API keys or passwords.

Users are advised to add `.codex_memory/` to `.gitignore` to prevent accidental commits.

## Packaging and Distribution

The plugin is packaged as a zipped directory that includes:

- Python scripts and a `venv/` with dependencies such as `faiss-cpu`, `sentence-transformers`, and SQLite bindings.
- Model files in `scripts/models/`.
- Manifest and hook definitions.
- A default `memory_config.json` template.

A build script, `build_plugin.sh`, installs dependencies into `venv/`, copies models and scripts, generates the plugin archive, and validates the package with the Codex CLI.

Documentation in `README.md` explains installation and usage.

Installation paths include:

    plugins/
    .agents/plugins/marketplace.json

Usage covers skills and configuration.

## Development Plan

### 1. Scaffold the Plugin

Create the directory structure and manifest. Add default `memory_config.json` with built-in categories and weights.

### 2. Implement Configuration Management

Write `config.py` to load, validate, and update `memory_config.json`, including default categories and user-defined ones.

### 3. Develop the Memory Manager

Implement reading and writing in either SQLite or JSONL formats. Add category validation and embedding support.

### 4. Add Vector Search

Integrate FAISS or Chroma for semantic search. Index entries by embedding and maintain category metadata for filtering.

### 5. Build Skills

Implement `save_insight`, `retrieve_memory`, and optional `define_category` skills. Write `SKILL.md` files with clear instructions for the agent.

### 6. Define Hooks

Configure `hooks.json` and implement the following scripts:

- `session_start.py`
- `pre_compact.py`
- `post_tool_use.py`
- `prompt_inspector.py`
- `stop.py`
- `update_categories.py`

Ensure they call the memory manager and configuration manager appropriately.

### 7. Implement Summarisation

Start with heuristic summarisation. Optionally integrate a small model.

Provide a pluggable interface in `summarizer.py`.

### 8. Packaging and Testing

Write `build_plugin.sh` to assemble the plugin.

Create unit tests for:

- `memory_manager`
- `config`

Use sample projects to simulate Codex sessions and verify recall across context resets.

### 9. Documentation and Release

Prepare:

- `README.md`
- `CHANGELOG.md`
- example workflows

Publish the plugin to a Git repository and share installation instructions.

Collect user feedback and iterate on:

- category defaults
- retrieval weighting
- summarisation quality

## Conclusion

By integrating a rich category system and support for user-defined categories, RECALL transforms Codex into an agent that never forgets key project information.

The design leverages research showing that categorised memory and custom schemas improve retrieval and relevance. Combined with a local database, vector search, and summarisation, RECALL offers developers a powerful and private memory layer that preserves context across weeks or months of development, all within a single installable plugin.

## References

1. What Is OpenBrain? The Personal AI Memory Database You Own and Control | MindStudio  
   https://www.mindstudio.ai/blog/what-is-openbrain-personal-ai-memory-database
2. mem0/mem0-plugin/skills/mem0/references/use-cases.md at main - mem0ai/mem0 - GitHub  
   https://github.com/mem0ai/mem0/blob/main/mem0-plugin/skills/mem0/references/use-cases.md
