import requests
import json
import argparse
import sys

def query_ollama(host, model, prompt):
    url = f"http://{host}:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "No response from model")
    except Exception as e:
        return f"Error connecting to Ollama at {host}: {str(e)}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query local Ollama fleet")
    parser.add_argument("--node", required=True, help=".5 (Kokkoro), .10 (Kumo), or .8 (Pecorine)")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()
    
    nodes = {
        ".5": "192.168.1.5",
        ".10": "192.168.1.10",
        ".8": "192.168.1.8"
    }
    
    host = nodes.get(args.node, args.node)
    print(query_ollama(host, args.model, args.prompt))
