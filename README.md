# Local Ollama Sub-Agent Configuration

This repository provides tools and configurations to allow AI agents (Gemini, Claude, Opencode) to offload data processing, classification, and reasoning tasks to your local Ollama GPU fleet.

## Fleet Nodes (verified 2026-06-29)

| Node | IP | GPU | VRAM | Best For |
|---|---|---|---|---|
| Silvia | .25 | Arc B580 | 12GB | Main logic, local inference |
| Kokkoro | .5 | 2x RTX 3060 | 24GB | `gemma4:31b` reasoning (offline 17:00 daily) |
| Kurumi | .80 | RTX 3080 | 10GB | Fast reasoning, vision |
| Kumo | .10 | 3x Tesla P4 | 24GB | Classification, `gemma4:e4b` |
| cmp70hx-gpu | .13 | CMP 70HX | 8GB | Classification, `gemma4:e4b` |
| cmp30hx-1 | .14 | CMP 30HX | 6GB | Classification, `gemma4:e4b` |
| cmp30hx-2 | .16 | CMP 30HX | 6GB | Classification, `gemma4:e4b` |
| Yuki | .6 | RX 7900 XTX | 24GB | **LOCKED** — bot active, read-only |

> ❌ Pecorine (.8) removed — P100 x4 decommissioned

## Available Models (Verified 2026-06-29)

| Model | Tier | Best For |
|---|---|---|
| `gemma4:e4b` | Fast | Classification, atomic tasks (all nodes) |
| `gemma4:12b` | Medium | Reasoning, summarize |
| `gemma4:27b` / `gemma4:31b` | Heavy | Complex reasoning, code review |
| `qwen2.5:7b` / `qwen2.5:14b` | Medium | Multilingual, code |
| `erukude/multiagent-orchestrator:3b` | Router | Task routing brain |
| `nomic-embed-text` | Embed | RAG embeddings |
| `moondream:1.8b` | Vision | OCR, image classify |
| `deepseek-r1:7b` / `deepseek-r1:32b` | Reasoning | Math, logic |

*Run `python3 tools/ollama_tool.py --list-nodes` for real-time fleet telemetry.*

## Core Tool Usage
The bridge script is `tools/ollama_tool.py`. All local/remote agents use this interface.
```bash
# Example: Delegate metadata extraction to the high-capacity node
python3 tools/ollama_tool.py --node .5 --model gemma4:31b --prompt "Map the primary logic flow in this source..."
```

---

## 1. Opencode Configuration
Opencode agents operate natively in the shell. Configuration involves white-listing the tool.

**Workspace Mandate (CLAUDE.md / GEMINI.md):**
> "OPERATIONAL RULE: Offload all classification and heavy data parsing to the local GPU fleet via `python3 tools/ollama_tool.py`. Do not exhaust primary API tokens for deterministic sub-tasks."

**Hcom Integration:**
Ensure `hcom` permissions allow the bridge tool:
```bash
export OPENCODE_PERMISSION='{"bash":{"python3 tools/ollama_tool.py *":"allow"}}'
hcom pty opencode --name gala
```

---

## 2. MCP Server Blueprint (Standardized)
Exposing the fleet as an **MCP (Model Context Protocol)** server allows Claude and Gemini to see it as a native tool.

### Setup for Claude Desktop (`~/.claude.json`)
```json
{
  "mcpServers": {
    "ollama-fleet": {
      "command": "python3",
      "args": ["/absolute/path/to/tools/ollama_tool.py"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/repo"
      }
    }
  }
}
```

### Setup for Gemini CLI (`gemini-extension.json`)
```json
{
  "name": "ollama-fleet-integrator",
  "mcpServers": [
    {
      "id": "ollama-bridge",
      "command": "python3",
      "args": ["tools/ollama_tool.py"],
      "transport": "stdio"
    }
  ]
}
```

---

## 3. Sub-Agent Workflows
- **Nodes .13/.14/.16 (CMP fleet)**: Use for `gemma4:e4b` classification (parallel batch).
- **Node .10 (Kumo)**: Use for `gemma4:e4b` / `gemma4:12b` (P4 x3, efficient).
- **Node .5 (Kokkoro)**: Use for `gemma4:31b` reasoning (offline daily at 17:00).
- **Node .80 (Kurumi)**: Use for vision tasks / fast reasoning.
- **Node .8 (Pecorine)**: Use for `deepseek-r1:32b` or batching (max VRAM).
