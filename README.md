# Local Ollama Sub-Agent Configuration

This repository provides tools and configurations to allow AI agents (Gemini, Claude, Opencode) to offload data processing, classification, and reasoning tasks to your local Ollama GPU fleet.

## Fleet Nodes (verified 2026-09-05 — live `curl /api/tags` on every node)

| Node | Endpoint | GPU | VRAM | Bandwidth | Best For |
|---|---|---|---|---|---|
| **Silvia** | `127.0.0.1:11434` | Arc B580 (Vulkan) | 12GB | 456 GB/s | Fastest in fleet. **Ceiling ~10B** — a 14B spills to CPU and times out |
| **Kokkoro** | `.5:11434` | 2x RTX 3060 | 24GB | 360 GB/s | Largest single pool. Runs 30B fully on GPU (99% resident) |
| **Kumo** | `.10:11434`, `:11435`, `:11436` | 2x Tesla P4 | 16GB | 192 GB/s | Always-on batch / classify. 3 parallel instances |
| **Yuki** | `.6:11434` | RX 7900 XTX (ROCm gfx1100) | 24GB | 960 GB/s | ⚠️ **Trade bot host — coordinate before use.** Ollama is up and GPU-visible |

### Not inference nodes — do not route here
| Node | Why |
|---|---|
| cmp70hx `.13` | **ComfyUI on :8188 only** — no Ollama |
| Kurumi `.80` | Owner's gaming PC — off-limits |
| cmp30hx `.14` / `.16` | VMs stopped |
| Pecorine `.8` | P100 x4 decommissioned |
| BC-250 `.87` | MoE-only experiment box, usually powered off |

### Notes that cost us time
- **Kokkoro is now one Ollama instance across both cards** (`CUDA_VISIBLE_DEVICES=0,1`, drop-in override). The old split — `ollama.service` on GPU0 `:11434` + `ollama-gpu1.service` on GPU1 `:11435` — meant a single process saw only 12GB, so a 30B model landed 82% in system RAM. Port `.5:11435` is retired.
- **Check residency, not just "does it load".** `curl <node>:11434/api/ps` and compare `size_vram` to `size`; anything under 100% falls off a cliff rather than degrading smoothly.
- **Yuki keeps `/` at 49GB by design.** Large files belong on `/var/lib/docker` (300GB free). Ollama's libs and models are bind-mounted there — a symlink does not work because the `ollama` user cannot traverse `/var/lib/docker`.

## Orchestrator Node

| Model | Primary | Fallback |
|---|---|---|
| `erukude/multiagent-orchestrator:3b` | kokkoro `.5` | kumo `.10` |

Kurumi has been removed from the fallback chain — it is a personal machine, not fleet capacity.

## Available Models (verified 2026-09-05)

| Model | Tier | Best For |
|---|---|---|
| `gemma4:e4b` | Fast | Classification, atomic tasks (all nodes) |
| `qwen3.5:latest` (9.7B) | Fast | Silvia's sweet spot — fully GPU-resident, real `tool_calls` |
| `qwen3-coder:30b` | Heavy | Kokkoro only. Agentic coding, emits structured `tool_calls` |
| `gemma4:12b` | Medium | Reasoning, summarize |
| `gemma4:27b` / `gemma4:31b` | Heavy | Complex reasoning, code review |

> ⚠️ **Gemma models cannot drive a tool-using agent.** Every `gemma4` variant we tested writes the call out as prose ("I'll call calc...") instead of emitting a structured `tool_calls` array, so the harness never sees it. Verified working: `qwen3.5`, `qwen3:14b`, `qwen3-coder:30b`, `gpt-oss:20b`. Test any new model with a one-shot tool-call request before wiring it into an agent.
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
- **Node .10 (Kumo)**: Use for `gemma4:e4b` / `gemma4:12b` (2x P4, always-on).
- **Node .5 (Kokkoro)**: Use for `gemma4:31b` reasoning (offline daily at 17:00).
- **Node .80 (Kurumi)**: Use for vision tasks / fast reasoning.
- **Node .6 (Yuki)**: Use for `gemma4:27b`/`31b` — LOCKED during bot hours.
