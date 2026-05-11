# Local Ollama Sub-Agent Configuration

This repository provides tools and configurations to allow AI agents (Gemini, Claude, Opencode) to offload data processing, classification, and reasoning tasks to your local Ollama GPU fleet.

## Fleet Nodes
- **Kokkoro (.5)**: 2x RTX 3060 (12GB) - Best for `gemma4:31b` heavy reasoning.
- **Pecorine (.8)**: 4x Tesla P100 (16GB) - Best for high VRAM batch tasks.
- **Kumo (.10)**: 3x Tesla P4 (8GB) - Best for fast `gemma4:e4b` classification.

## Core Tool Usage
The core script is `tools/ollama_tool.py`. All agents use this to bridge to the local fleet.
```bash
python3 tools/ollama_tool.py --node .5 --model gemma4:31b --prompt "Extract circle name from this filename..."
```

---

## 1. Opencode Configuration
Opencode agents operate natively in the terminal. The most effective way is to instruct them to use the CLI tool directly.

**System Prompt / Instructions (e.g., in a workspace `README.md` or via hcom):**
> "MANDATE: You have access to a local Ollama fleet for sub-tasking. DO NOT use your main API tokens for simple classification, summarization, or metadata extraction. Instead, execute `python3 tools/ollama_tool.py --node <node> --prompt '<prompt>'` to delegate the sub-task and read its output."

**Hcom Integration:**
If using `hcom` to launch Opencode, ensure permissions allow script execution:
```bash
export OPENCODE_PERMISSION='{"bash":{"python3 tools/ollama_tool.py *":"allow"}}'
hcom pty opencode --name gala
```

---

## 2. Claude Code Configuration
Claude respects `CLAUDE.md` for workspace rules and can load MCP tools via its global config.

**Instructions in `CLAUDE.md`:**
```markdown
## Sub-Agent Delegation (Ollama Fleet)
For data extraction, translation, or batch processing, you MUST offload the task to the local Ollama fleet.
- Run `python3 tools/ollama_tool.py --node .10` for fast/simple tasks.
- Run `python3 tools/ollama_tool.py --node .5` for complex reasoning.
```

**MCP Integration (`~/.claude.json`):**
To expose the python script as an official tool to Claude:
```json
{
  "mcpServers": {
    "ollama-bridge": {
      "command": "python3",
      "args": ["/absolute/path/to/tools/ollama_tool.py"]
    }
  }
}
```

---

## 3. Gemini CLI Configuration
Gemini uses `GEMINI.md` for context and has native extension loading.

**Instructions in `GEMINI.md`:**
```markdown
# Local Inference Mandate
Always use local LLM inference for data tasks to save context tokens. Use the `ollama-bridge` MCP server.
```

**Extension Setup:**
```bash
gemini extensions link /absolute/path/to/ollama-subagent-config
```
