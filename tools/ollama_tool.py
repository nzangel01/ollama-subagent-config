import requests
import json
import argparse
import sys

def query_ollama(host, model, prompt, timeout=120):
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
    print("Ollama Fleet Nodes Status:")
    for key, host in nodes.items():
        try:
            resp = requests.get(f"http://{host}:11434/api/tags", timeout=2)
            if resp.status_code == 200:
                models = [m['name'] for m in resp.json().get('models', [])]
                print(f"✅ {key} ({host}): {', '.join(models)}")
            else:
                print(f"❌ {key} ({host}): Status {resp.status_code}")
        except:
            print(f"⚠️ {key} ({host}): UNREACHABLE")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query local Ollama fleet")
    parser.add_argument("--node", help=".5 (Kokkoro), .10 (Kumo), or .8 (Pecorine)")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--prompt", help="Prompt to send")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds")
    parser.add_argument("--list-nodes", action="store_true", help="List all nodes and available models")
    
    args = parser.parse_args()
    
    nodes = {
        ".5": "192.168.1.5",
        ".10": "192.168.1.10",
        ".8": "192.168.1.8"
    }
    
    if args.list_nodes:
        list_nodes(nodes)
    elif args.node and args.prompt:
        host = nodes.get(args.node, args.node)
        print(query_ollama(host, args.model, args.prompt, args.timeout))
    else:
        parser.print_help()
