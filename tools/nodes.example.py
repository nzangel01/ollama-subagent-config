# Copy this file to nodes.local.py and fill in your actual values.
# nodes.local.py is gitignored — never commit real IPs or hostnames.

NODE_CONFIG = {
    "node-a": {
        "host": "192.168.x.x",   # your GPU node IP
        "port": 11434,
        "name": "MyNode",
        "gpu": "RTX 3060",
        "vram_per_gpu": 12,
        "gpu_count": 1,
        "vram_total": 12,
        "best_for": "Reasoning, Medium Models",
        "priority": 1,
    },
    "node-b": {
        "host": "192.168.x.x",
        "port": 11434,
        "name": "ClassifyNode",
        "gpu": "Tesla P4",
        "vram_per_gpu": 8,
        "gpu_count": 1,
        "vram_total": 8,
        "best_for": "Classification, gemma4:e4b",
        "priority": 2,
    },
    # Add more nodes as needed.
    # Fields: host, port, name, gpu, vram_per_gpu, gpu_count, vram_total, best_for, priority
    # Optional: cpu_only=True, ram_gb=N  (for CPU-only nodes)
}
