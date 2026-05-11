# Local Ollama Sub-Agent Configuration

This repository contains the configuration and tools for Gemini/Claude agents to offload tasks to a local Ollama fleet.

## Fleet Nodes
- **Kokkoro (.5)**: 2x RTX 3060 (12GB x2) - Best for `gemma4:31b` reasoning.
- **Pecorine (.8)**: 4x Tesla P100 (16GB x4) - Best for high VRAM batch tasks.
- **Kumo (.10)**: 3x Tesla P4 (8GB x3) - Best for fast `gemma4:e4b` classification.

## Integration
Add the following to your agent's system prompt or `GEMINI.md`:
"Prioritize local LLM inference for data processing. Use the provided `ollama_tool.py` to query nodes .5, .8, or .10."

## Tool Usage (CLI)
```bash
python3 tools/ollama_tool.py --node .5 --model gemma4:31b --prompt "Analyze this metadata..."
```

## Gemini CLI Extension
To use as an extension, link this folder:
```bash
gemini extensions link .
```
Then you can call it via `/ollama:query` (once command is defined).
