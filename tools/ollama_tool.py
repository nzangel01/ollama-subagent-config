import requests
import argparse
import time
import os
import sys
import json

# Load node config from nodes.local.py (gitignored, private)
# Copy tools/nodes.example.py → tools/nodes.local.py and fill in your nodes.
_dir = os.path.dirname(os.path.abspath(__file__))
_local = os.path.join(_dir, "nodes.local.py")
_example = os.path.join(_dir, "nodes.example.py")
if not os.path.exists(_local):
    print(f"Error: {_local} not found. Copy nodes.example.py and configure your nodes.", file=sys.stderr)
    sys.exit(1)
_ns = {}
exec(open(_local).read(), _ns)
NODE_CONFIG = _ns["NODE_CONFIG"]

_health_cache = {}
HEALTH_CACHE_TTL = 30


def check_node_health(host, port, timeout=2):
    key = f"{host}:{port}"
    now = time.time()
    if key in _health_cache:
        ts, ok = _health_cache[key]
        if now - ts < HEALTH_CACHE_TTL:
            return ok
    try:
        resp = requests.get(f"http://{host}:{port}/api/ps", timeout=timeout)
        ok = resp.status_code == 200
    except Exception:
        ok = False
    _health_cache[key] = (now, ok)
    return ok


def get_loaded_models(host, port, timeout=2):
    try:
        resp = requests.get(f"http://{host}:{port}/api/ps", timeout=timeout)
        if resp.status_code == 200:
            return resp.json().get("models", [])
    except Exception:
        pass
    return []


def get_available_models(host, port, timeout=3):
    try:
        resp = requests.get(f"http://{host}:{port}/api/tags", timeout=timeout)
        if resp.status_code == 200:
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    return []


def _estimate_vram(model_name):
    name = model_name.lower()
    for tag, vram in [("70b", 45), ("32b", 20), ("31b", 20), ("27b", 18),
                      ("14b", 10), ("13b", 9), ("11b", 8), ("9b", 6),
                      ("8b", 5), ("7b", 5), ("4b", 3), ("3b", 2), ("1b", 1)]:
        if tag in name:
            return vram
    return 5


def find_best_nodes(target_model, preferred_node=None):
    vram_needed = _estimate_vram(target_model)
    is_large = vram_needed >= 18
    is_vision = any(x in target_model.lower() for x in ["vision", "llava"])

    candidates = []
    for key, info in NODE_CONFIG.items():
        host, port = info["host"], info["port"]
        if preferred_node and preferred_node != key:
            continue
        if not check_node_health(host, port):
            continue

        loaded = get_loaded_models(host, port)
        score = info["priority"] * 10

        # Sticky session — model already loaded
        if any(target_model in m.get("name", "") for m in loaded):
            score -= 100

        # CPU-only nodes: skip for large/vision models, use RAM headroom
        if info.get("cpu_only"):
            if is_large or is_vision:
                continue  # ไม่ส่ง large/vision ไป CPU node
            ram_gb = info.get("ram_gb", 0)
            if ram_gb < vram_needed * 2:  # RAM ต้องการ ~2x VRAM estimate
                score += 50
            score += 30  # CPU slow กว่า GPU เสมอ — prefer GPU first
        else:
            # VRAM penalty if node likely can't fit model
            if info["vram_total"] < vram_needed:
                score += 50

        # Prefer Kokkoro/Pecorine for large models
        if is_large and key in (".5", ".8"):
            score -= 20

        # Prefer Kurumi for vision
        if is_vision and key == ".80":
            score -= 15

        # Prefer local Silvia for small tasks
        if not is_large and key == ".24":
            score -= 5

        candidates.append((score, host, port))

    candidates.sort()
    return [(h, p) for _, h, p in candidates]


def query_ollama(host, port, model, prompt, timeout=120):
    url = f"http://{host}:{port}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    if "json" in prompt.lower():
        payload["format"] = "json"
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "No response")
    except requests.exceptions.Timeout:
        return f"Error: Timeout ({timeout}s) on {host}:{port}"
    except Exception as e:
        return f"Error: {host}:{port} — {e}"


def query_with_fallback(model, prompt, timeout=120, preferred_node=None):
    nodes = find_best_nodes(model, preferred_node)
    if not nodes:
        names = ", ".join(
            f"{v['name']}({v['host']}:{v['port']}) [{v['gpu']} {v['vram_total']}GB]"
            for v in NODE_CONFIG.values()
        )
        return f"Error: All Ollama nodes offline. Checked: {names}"

    last_err = ""
    for host, port in nodes:
        result = query_ollama(host, port, model, prompt, timeout)
        if not result.startswith("Error:"):
            return result
        _health_cache.pop(f"{host}:{port}", None)
        last_err = result

    return f"Error: All nodes failed. Last: {last_err}"


ORCHESTRATOR_MODEL = "erukude/multiagent-orchestrator:3b"
# Prefer kokkoro (.5) for orchestrator (low latency RTX 3060) and fallback to kumo (.10, always-on PVE)
ORCHESTRATOR_NODE = (".5", ".10", ".80")  # fallback order: kokkoro → kumo → kurumi


def orchestrate(task: str, agents: list[dict]) -> dict | None:
    """Ask multiagent-orchestrator which agent to call. Returns parsed JSON or None."""
    for key in ORCHESTRATOR_NODE:
        if key not in NODE_CONFIG:
            continue
        info = NODE_CONFIG[key]
        host, port = info["host"], info["port"]
        if not check_node_health(host, port):
            continue
        try:
            resp = requests.post(
                f"http://{host}:{port}/api/chat",
                json={
                    "model": ORCHESTRATOR_MODEL,
                    "stream": False,
                    "messages": [{"role": "user", "content":
                        f"Task: {task}\nAvailable agents: {agents}\n"
                        "Pick the best agent and return JSON only."
                    }],
                },
                timeout=30,
            )
            content = resp.json().get("message", {}).get("content", "")
            # Extract JSON from response
            import re as _re
            m = _re.search(r'\{.*\}', content, _re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
    return None


def list_nodes():
    print(f"\n{'Node':<5} {'Name':<10} {'Status':<10} {'GPU':<28} {'VRAM':<10} {'Loaded':<20} Available")
    print("-" * 115)
    for key, info in NODE_CONFIG.items():
        host, port = info["host"], info["port"]
        online = check_node_health(host, port, timeout=3)
        if online:
            loaded = [m["name"] for m in get_loaded_models(host, port)]
            available = get_available_models(host, port)
            status = "✅ ONLINE"
            loaded_str = ", ".join(loaded) if loaded else "Idle"
            avail_str = ", ".join(available[:3]) + ("…" if len(available) > 3 else "")
        else:
            status = "❌ OFFLINE"
            loaded_str = avail_str = "-"
        if info.get("cpu_only"):
            gpu_str = f"{info['gpu']}"
            mem_str = f"{info.get('ram_gb', '?')}GB RAM"
        else:
            gpu_str = f"{info['gpu']} ({info['gpu_count']}x{info['vram_per_gpu']}GB)"
            mem_str = f"{info['vram_total']}GB VRAM"
        print(f"{key:<5} {info['name']:<10} {status:<10} {gpu_str:<30} {mem_str:<12} {loaded_str:<20} {avail_str}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ollama Fleet — Fallback Routing")
    parser.add_argument("--node", default="auto", help=".5/.8/.10/.24/.80 or 'auto'")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--prompt", help="Prompt to send")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--list-nodes", action="store_true")
    parser.add_argument("--orchestrate", help="Describe task to route via multiagent-orchestrator")
    parser.add_argument("--agents", help='JSON agent list e.g. \'[{"name":"a","skills":["x"]}]\'')
    args = parser.parse_args()

    if args.list_nodes:
        list_nodes()
    elif args.orchestrate:
        agents = json.loads(args.agents) if args.agents else [
            {"name": "text-parser", "skills": ["filename", "regex", "metadata"]},
            {"name": "vision-classifier", "skills": ["image", "video", "OCR"]},
            {"name": "embedding-search", "skills": ["semantic", "RAG", "similarity"]},
            {"name": "code-executor", "skills": ["python", "bash", "rename", "move"]},
            {"name": "summarizer", "skills": ["document", "text", "Thai", "Japanese"]},
        ]
        result = orchestrate(args.orchestrate, agents)
        print(json.dumps(result, ensure_ascii=False, indent=2) if result else "Error: orchestrator unavailable")
    elif args.prompt:
        preferred = None if args.node == "auto" else args.node
        print(query_with_fallback(args.model, args.prompt, args.timeout, preferred))
    else:
        parser.print_help()
