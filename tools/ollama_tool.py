import requests
import json
import argparse
import sys
import re

# Node Performance Metadata
NODE_CONFIG = {
    ".25": {
        "host": "192.168.1.25",
        "name": "Silvia",
        "gpu": "Intel Arc B580 (12GB VRAM)",
        "perf": "Medium-High (Battlemage)",
        "best_for": "Main Logic, Local Inference, AV1 Encode",
        "vram_per_gpu": 12
    },
    ".6": {
        "host": "192.168.1.6",
        "name": "Yuki",
        "gpu": "AMD RX 7900 XTX (24GB VRAM)",
        "perf": "High (RDNA3)",
        "best_for": "Large Context, Fast Inference, ROCm Tasks (LOCKED - bot active)",
        "vram_per_gpu": 24
    },
    ".5": {
        "host": "192.168.1.5",
        "name": "Kokkoro",
        "gpu": "2x RTX 3060 (24GB VRAM Total)",
        "perf": "Medium-High (Ampere)",
        "best_for": "Reasoning, Fast Inference, CUDA Tasks",
        "vram_per_gpu": 12
    },
    ".7": {
        "host": "192.168.1.7",
        "name": "Sheffy",
        "gpu": "RTX 2080Ti + Arc A380",
        "perf": "Vulkan Fix Needed / Port Unresponsive",
        "best_for": "Offline",
        "vram_per_gpu": 11
    },
    ".10": {
        "host": "192.168.1.10",
        "name": "Kumo",
        "gpu": "3x Tesla P4 (24GB VRAM Total)",
        "perf": "Efficient (Pascal)",
        "best_for": "Classification, Small Models (<8B)",
        "vram_per_gpu": 8
    },
    ".80": {
        "host": "192.168.1.80",
        "name": "Kurumi",
        "gpu": "RTX 3080 (10GB VRAM)",
        "perf": "High (Ampere)",
        "best_for": "Fast Reasoning, Vision Tasks",
        "vram_per_gpu": 10
    },
    ".117": {
        "host": "192.168.1.117",
        "name": "Silvia18",
        "gpu": "Intel Arc B580 / CPU (Secondary Interface)",
        "perf": "Medium-High / 25 Models loaded",
        "best_for": "Multi-model fallbacks",
        "vram_per_gpu": 12
    },
    ".13": {
        "host": "192.168.1.13",
        "name": "cmp70hx-gpu",
        "gpu": "NVIDIA CMP 70HX (8GB VRAM)",
        "perf": "Medium (Ampere, no display)",
        "best_for": "Classification, gemma4:e4b",
        "vram_per_gpu": 8
    },
    ".14": {
        "host": "192.168.1.14",
        "name": "cmp30hx-1",
        "gpu": "NVIDIA CMP 30HX (6GB VRAM)",
        "perf": "Medium (Turing, no display)",
        "best_for": "Classification, gemma4:e4b",
        "vram_per_gpu": 6
    },
    ".16": {
        "host": "192.168.1.16",
        "name": "cmp30hx-2",
        "gpu": "NVIDIA CMP 30HX (6GB VRAM)",
        "perf": "Medium (Turing, no display)",
        "best_for": "Classification, gemma4:e4b",
        "vram_per_gpu": 6
    },
    ".240": {
        "host": "192.168.1.240",
        "name": "TAKAO",
        "gpu": "Quadro P400 (2GB VRAM)",
        "perf": "Low Power (Pascal)",
        "best_for": "Light Metadata, CPU Fallback",
        "vram_per_gpu": 2
    }
}

def sanitize_input(text):
    """Prevent basic command injection and strip dangerous control characters."""
    if not text: return ""
    # Strip potentially dangerous shell characters if this output is piped
    clean = re.sub(r'[;&|`$<>!]', '', text)
    # Remove non-printable characters except newlines/tabs
    clean = "".join(char for char in clean if char.isprintable() or char in "\n\t")
    return clean.strip()

def get_node_info(host):
    """Fetch active models and available models from a node."""
    info = {"active": [], "available": []}
    try:
        # Check currently loaded models
        resp_ps = requests.get(f"http://{host}:11434/api/ps", timeout=2)
        if resp_ps.status_code == 200:
            info["active"] = [m['name'] for m in resp_ps.json().get("models", [])]
        
        # Check available local models (even if not loaded)
        resp_tags = requests.get(f"http://{host}:11434/api/tags", timeout=2)
        if resp_tags.status_code == 200:
            info["available"] = [m['name'] for m in resp_tags.json().get("models", [])]
            
        return info
    except:
        return None

def find_best_node(target_model):
    """Smarter selection based on presence, performance metadata, and current load."""
    best_host = None
    min_load = float('inf')
    
    # Heuristic: Determine if model is 'large' based on name
    is_large = any(x in target_model.lower() for x in ["31b", "32b", "70b", "deepseek-r1:3"])
    
    candidates = []
    
    for key, info in NODE_CONFIG.items():
        host = info["host"]
        node_info = get_node_info(host)
        if node_info is None: continue
        
        # Priority 1: Model already loaded (Sticky session)
        if any(target_model in m for m in node_info["active"]):
            return host
            
        # Check if model exists on this node
        exists = any(target_model in m for m in node_info["available"])
        if exists:
            # Priority 2: Match by capability (if model exists on preferred hardware)
            if is_large and key == ".5":
                return host
            
            # Add to potential candidates if exists but not active
            candidates.append((host, len(node_info["active"])))

    # Priority 3: Least loaded node among those that have the model
    if candidates:
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]
            
    # Fallback: Least loaded node across entire fleet (Ollama will try to pull or error)
    for key, info in NODE_CONFIG.items():
        host = info["host"]
        node_info = get_node_info(host)
        if node_info and len(node_info["active"]) < min_load:
            min_load = len(node_info["active"])
            best_host = host
            
    return best_host

def query_ollama(host, model, prompt, timeout=120):
    if not host:
        return "Error: No suitable Ollama node found."
        
    # Sanitize prompt before sending to local fleet
    safe_prompt = sanitize_input(prompt)
    
    url = f"http://{host}:11434/api/generate"
    payload = {
        "model": model,
        "prompt": safe_prompt,
        "stream": False,
        "format": "json" if "json" in safe_prompt.lower() else None
    }
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", "No response from model")
    except requests.exceptions.Timeout:
        return f"Error: Request timed out after {timeout} seconds on {host}."
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
    parser = argparse.ArgumentParser(description="Query local Ollama fleet with Performance-Aware Routing & Security")
    parser.add_argument("--node", default="auto", help=".5, .10, .25, .80, .117 or 'auto' (default)")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--prompt", help="Prompt to send")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds")
    parser.add_argument("--list-nodes", action="store_true", help="List all nodes, specs and their current load")
    
    args = parser.parse_args()
    
    if args.list_nodes:
        list_nodes()
    elif args.prompt:
        # Sanitize model name as well to be safe
        safe_model = re.sub(r'[^a-zA-Z0-9:._-]', '', args.model)
        
        if args.node == "auto":
            host = find_best_node(safe_model)
        else:
            # Map shorthand or use direct IP
            node_key = args.node if args.node.startswith(".") else f".{args.node}" if args.node.isdigit() else args.node
            host = NODE_CONFIG.get(node_key, {"host": args.node})["host"]
            
        print(query_ollama(host, safe_model, args.prompt, args.timeout))
    else:
        parser.print_help()
