import requests
import argparse
import time

# Node config — GPU verified 2026-05-14
NODE_CONFIG = {
    ".5": {
        "host": "192.168.1.5",
        "port": 11434,
        "name": "Kokkoro",
        "gpu": "2x RTX 3060",
        "vram_per_gpu": 12,
        "gpu_count": 2,
        "vram_total": 24,
        "best_for": "Reasoning, Large Models (31b/32b), Fast Inference",
        "priority": 1,
    },
    ".8": {
        "host": "192.168.1.8",
        "port": 11434,
        "name": "Pecorine",
        "gpu": "4x Tesla P100-PCIE",
        "vram_per_gpu": 16,
        "gpu_count": 4,
        "vram_total": 64,
        "best_for": "Large Batching (>20B), Vision (llava)",
        "priority": 2,
    },
    ".10": {
        "host": "192.168.1.10",
        "port": 11435,  # 11434 down — use 11435
        "name": "Kumo",
        "gpu": "3x Tesla P4",
        "vram_per_gpu": 8,
        "gpu_count": 3,
        "vram_total": 23,  # 8192+7680+7680 MiB (mixed lot)
        "best_for": "Light Tasks, Classification, Small Models (<4B)",
        "priority": 4,
    },
    ".24": {
        "host": "192.168.1.24",
        "port": 11434,
        "name": "Silvia",
        "gpu": "Intel Arc B580 (Battlemage G21)",
        "vram_per_gpu": 12,
        "gpu_count": 1,
        "vram_total": 12,
        "best_for": "Code, Embedding, Local Priority, Medium Models",
        "priority": 3,
    },
    ".80": {
        "host": "192.168.1.80",
        "port": 11434,
        "name": "Kurumi",
        "gpu": "RTX 3080",
        "vram_per_gpu": 10,
        "gpu_count": 1,
        "vram_total": 10,
        "best_for": "Vision, Fast Medium Models, Streaming",
        "priority": 2,
    },
}

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
        gpu_str = f"{info['gpu']} ({info['gpu_count']}x{info['vram_per_gpu']}GB)"
        print(f"{key:<5} {info['name']:<10} {status:<10} {gpu_str:<28} {info['vram_total']:<4}GB    {loaded_str:<20} {avail_str}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ollama Fleet — Fallback Routing")
    parser.add_argument("--node", default="auto", help=".5/.8/.10/.24/.80 or 'auto'")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--prompt", help="Prompt to send")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--list-nodes", action="store_true")
    args = parser.parse_args()

    if args.list_nodes:
        list_nodes()
    elif args.prompt:
        preferred = None if args.node == "auto" else args.node
        print(query_with_fallback(args.model, args.prompt, args.timeout, preferred))
    else:
        parser.print_help()
