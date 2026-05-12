import requests
import json
import argparse
import sys

def get_node_info(host):
    """Fetch active models and VRAM usage from a node."""
    try:
        resp = requests.get(f"http://{host}:11434/api/ps", timeout=2)
        if resp.status_code == 200:
            return resp.json().get("models", [])
    except:
        return None
    return None

def find_best_node(nodes, target_model):
    """Select the best node based on whether the model is already loaded or which has fewer models."""
    best_node = None
    min_load = float('inf')
    
    for key, host in nodes.items():
        models = get_node_info(host)
        if models is None: continue # Skip unreachable
        
        # Priority 1: Model already loaded
        for m in models:
            if target_model in m['name']:
                return host
        
        # Priority 2: Least loaded node
        load = len(models)
        if load < min_load:
            min_load = load
            best_node = host
            
    return best_node

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

def list_nodes(nodes):
    print(f"{'Node':<10} {'Status':<12} {'Loaded Models'}")
    print("-" * 40)
    for key, host in nodes.items():
        try:
            resp = requests.get(f"http://{host}:11434/api/ps", timeout=2)
            if resp.status_code == 200:
                models = [m['name'] for m in resp.json().get('models', [])]
                status = "✅ ONLINE"
                model_str = ", ".join(models) if models else "Idle"
                print(f"{key:<10} {status:<12} {model_str}")
            else:
                print(f"{key:<10} ❌ ERROR      Status {resp.status_code}")
        except:
            print(f"{key:<10} ⚠️ UNREACHABLE")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query local Ollama fleet with Auto-Load Balancing")
    parser.add_argument("--node", default="auto", help=".5, .10, .8 or 'auto' (default)")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--prompt", help="Prompt to send")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds")
    parser.add_argument("--list-nodes", action="store_true", help="List all nodes and their current load")
    
    args = parser.parse_args()
    
    nodes = {
        ".5": "192.168.1.5",
        ".10": "192.168.1.10",
        ".8": "192.168.1.8"
    }
    
    if args.list_nodes:
        list_nodes(nodes)
    elif args.prompt:
        if args.node == "auto":
            host = find_best_node(nodes, args.model)
            if host:
                # Map back to key for display
                node_key = [k for k, v in nodes.items() if v == host][0]
                # print(f"[AUTO] Selected node {node_key}")
                pass
        else:
            host = nodes.get(args.node, args.node)
            
        print(query_ollama(host, args.model, args.prompt, args.timeout))
    else:
        parser.print_help()
