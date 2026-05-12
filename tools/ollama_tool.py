import requests
import json
import argparse
import sys

# Node Performance Metadata
NODE_CONFIG = {
    ".5": {
        "host": "192.168.1.5",
        "name": "Kokkoro",
        "gpu": "2x RTX 3060 (24GB VRAM Total)",
        "perf": "High (Ampere)",
        "best_for": "Reasoning, Fast Inference, Medium Models",
        "vram_per_gpu": 12
    },
    ".8": {
        "host": "192.168.1.8",
        "name": "Pecorine",
        "gpu": "4x Tesla P100 (64GB VRAM Total)",
        "perf": "High Capacity (Pascal)",
        "best_for": "Large Models (>20B), Massive Batching",
        "vram_per_gpu": 16
    },
    ".10": {
        "host": "192.168.1.10",
        "name": "Kumo",
        "gpu": "3x Tesla P4 (24GB VRAM Total)",
        "perf": "Efficient (Pascal)",
        "best_for": "Light Tasks, Classification, Small Models (<8B)",
        "vram_per_gpu": 8
    }
}

def get_node_info(host):
    """Fetch active models and VRAM usage from a node."""
    try:
        resp = requests.get(f"http://{host}:11434/api/ps", timeout=2)
        if resp.status_code == 200:
            return resp.json().get("models", [])
    except:
        return None
    return None

def find_best_node(target_model):
    """Smarter selection based on performance metadata and current load."""
    best_node = None
    best_host = None
    min_load = float('inf')
    
    # Heuristic: Determine if model is 'large' based on name (rough estimate)
    is_large = any(x in target_model.lower() for x in ["31b", "32b", "70b", "deepseek-r1:3"])
    
    for key, info in NODE_CONFIG.items():
        host = info["host"]
        models = get_node_info(host)
        if models is None: continue
        
        # Priority 1: Model already loaded (Sticky session)
        for m in models:
            if target_model in m['name']:
                return host
        
        # Priority 2: Match by capability
        if is_large and key == ".8": # Large models prefer Pecorine
            return host
        
        # Priority 3: Least loaded node
        load = len(models)
        if load < min_load:
            min_load = load
            best_host = host
            
    return best_host

def query_ollama(host, model, prompt, timeout=120):
    if not host:
        return "Error: No suitable Ollama node found."
        
    url = f"http://{host}:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json" if "json" in prompt.lower() else None
    }
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", "No response from model")
    except requests.exceptions.Timeout:
        return f"Error: Request timed out after {timeout} seconds."
    except Exception as e:
        return f"Error connecting to Ollama at {host}: {str(e)}"

def list_nodes():
    print(f"{'Node':<6} {'Name':<10} {'Status':<10} {'Best For':<35} {'Loaded Models'}")
    print("-" * 100)
    for key, info in NODE_CONFIG.items():
        host = info["host"]
        try:
            resp = requests.get(f"http://{host}:11434/api/ps", timeout=2)
            if resp.status_code == 200:
                models = [m['name'] for m in resp.json().get('models', [])]
                status = "✅ ONLINE"
                model_str = ", ".join(models) if models else "Idle"
                print(f"{key:<6} {info['name']:<10} {status:<10} {info['best_for']:<35} {model_str}")
            else:
                print(f"{key:<6} {info['name']:<10} ❌ ERROR")
        except:
            print(f"{key:<6} {info['name']:<10} ⚠️ OFFLINE")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query local Ollama fleet with Performance-Aware Routing")
    parser.add_argument("--node", default="auto", help=".5, .10, .8 or 'auto' (default)")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--prompt", help="Prompt to send")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds")
    parser.add_argument("--list-nodes", action="store_true", help="List all nodes, specs and their current load")
    
    args = parser.parse_args()
    
    if args.list_nodes:
        list_nodes()
    elif args.prompt:
        if args.node == "auto":
            host = find_best_node(args.model)
        else:
            # Map shorthand or use direct IP
            host = NODE_CONFIG.get(args.node, {"host": args.node})["host"]
            
        print(query_ollama(host, args.model, args.prompt, args.timeout))
    else:
        parser.print_help()
