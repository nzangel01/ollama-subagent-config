import requests
import json
import argparse
import sys
import time

# Node Performance Metadata — updated 2026-05-14 (network scan)
NODE_CONFIG = {
    ".5": {
        "host": "192.168.1.5",
        "port": 11434,
        "name": "Kokkoro",
        "gpu": "2x RTX 3060 (24GB Total)",
        "best_for": "Reasoning, Large Models (31b/32b)",
        "vram_total": 24,
        "priority": 1,
    },
    ".8": {
        "host": "192.168.1.8",
        "port": 11434,
        "name": "Pecorine",
        "gpu": "4x Tesla P100 (64GB Total)",
        "best_for": "Large Batching, Vision (llava)",
        "vram_total": 64,
        "priority": 2,
    },
    ".10": {
        "host": "192.168.1.10",
        "port": 11435,
        "name": "Kumo",
        "gpu": "3x Tesla P4 (24GB Total)",
        "best_for": "Light Tasks, Small Models (<4B)",
        "vram_total": 24,
        "priority": 4,
    },
    ".24": {
        "host": "192.168.1.24",
        "port": 11434,
        "name": "Silvia",
        "gpu": "Intel Arc B580 (12GB)",
        "best_for": "Code, Embedding, Local Priority",
        "vram_total": 12,
        "priority": 3,
    },
    ".80": {
        "host": "192.168.1.80",
        "port": 11434,
        "name": "Kurumi",
        "gpu": "RTX 3080 (10GB)",
        "best_for": "Vision, Fast Medium Models",
        "vram_total": 10,
        "priority": 2,
    },
}

# Health cache — avoid pinging every node on every request
_health_cache = {}
HEALTH_CACHE_TTL = 30  # seconds


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
                      ("8b", 5), ("7b", 5), ("4b", 3), ("3b", 2)]:
        if tag in name:
            return vram
    return 5


def find_best_nodes(target_model, preferred_node=None):
    """Return ordered list of (host, port) to try, skipping offline nodes."""
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

        # Sticky session bonus
        if any(target_model in m.get("name", "") for m in loaded):
            score -= 100

        # VRAM penalty
        if info["vram_total"] < vram_needed:
            score += 50

        # Large model preference
        if is_large and key in (".5", ".8"):
            score -= 20

        # Vision preference
        if is_vision and key == ".80":
            score -= 15

        # Local preference for small tasks
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
    """Try nodes in order. Auto-fallback if a node is down or errors."""
    nodes = find_best_nodes(model, preferred_node)

    if not nodes:
        names = ", ".join(f"{v['name']}({v['host']}:{v['port']})" for v in NODE_CONFIG.values())
        return f"Error: All Ollama nodes offline. Checked: {names}"

    last_err = ""
    for host, port in nodes:
        result = query_ollama(host, port, model, prompt, timeout)
        if not result.startswith("Error:"):
            return result
        _health_cache.pop(f"{host}:{port}", None)  # invalidate on error
        last_err = result

    return f"Error: All nodes failed. Last: {last_err}"


def list_nodes():
    print(f"\n{'Node':<5} {'Name':<10} {'Status':<10} {'GPU':<25} {'VRAM':<7} {'Loaded':<25} Available")
    print("-" * 110)
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
        print(f"{key:<5} {info['name']:<10} {status:<10} {info['gpu']:<25} {info['vram_total']:<4}GB  {loaded_str:<25} {avail_str}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ollama Fleet — Fallback Routing")
    parser.add_argument("--node", default="auto", help=".5/.8/.10/.24/.80 or 'auto'")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--prompt", help="Prompt to send")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--list-nodes", action="store_true", help="Show all nodes and their status")
    args = parser.parse_args()

    if args.list_nodes:
        list_nodes()
    elif args.prompt:
        preferred = None if args.node == "auto" else args.node
        print(query_with_fallback(args.model, args.prompt, args.timeout, preferred))
    else:
        parser.print_help()
