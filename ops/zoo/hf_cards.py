#!/usr/bin/env python3
"""Fetch each base repo's README and pull the card's own stated purpose: the first real prose paragraph."""
import json, re, sys, time, urllib.request
REPOS = [
 "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16", "nvidia/Nemotron-Cascade-2-30B-A3B",
 "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
 "NousResearch/Hermes-4-14B", "NousResearch/Hermes-4-70B", "NousResearch/Hermes-4-405B",
 "NousResearch/NousCoder-14B", "NousResearch/nomos-1", "microsoft/Phi-4-reasoning-plus",
 "nvidia/OpenMath-Nemotron-14B", "nvidia/OpenMath-Nemotron-14B-Kaggle", "nvidia/OpenMath-Nemotron-32B",
 "google/gemma-4-26B-A4B-it", "google/gemma-4-31B-it", "google/gemma-4-E4B-it", "google/gemma-4-E2B-it",
 "google/embeddinggemma-300m", "openai/gpt-oss-20b",
 "ibm-granite/granite-embedding-english-r2", "ibm-granite/granite-embedding-reranker-english-r2", "ibm-granite/granite-guardian-4.1-8b",
 "nvidia/llama-nemotron-embed-1b-v2", "nvidia/llama-nemotron-rerank-1b-v2", "meta-llama/Llama-Prompt-Guard-2-86M",
 "allenai/olmOCR-2-7B-1025", "nvidia/Llama-3_3-Nemotron-Super-49B-v1_5", "allenai/Olmo-3.1-32B-Instruct",
 "mistralai/Mistral-Small-4-119B-2603", "mistralai/Magistral-Small-2509", "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
 "mistralai/Ministral-3-14B-Instruct-2512", "mistralai/Ministral-3-3B-Instruct-2512", "mistralai/Devstral-Small-2-24B-Instruct-2512",
 "black-forest-labs/FLUX.2-klein-9B", "microsoft/VibeVoice-1.5B", "microsoft/VibeVoice-Realtime-0.5B", "nvidia/NVIDIA-Nemotron-Parse-v1.2",
]
UA = {"User-Agent": "zoo-survey/0.1"}
def raw(repo):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"https://huggingface.co/{repo}/raw/main/README.md", headers=UA), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            err = e; time.sleep(1.5)
    return f"__ERR__ {err}"
def purpose(md):
    if md.startswith("__ERR__"): return md
    body = md
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) >= 3: body = parts[2]
    body = re.sub(r"<[^>]+>", " ", body)              # strip html
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)  # images
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)  # links to text
    paras = [p.strip() for p in re.split(r"\n\s*\n", body)]
    out = []
    for p in paras:
        if not p or p.startswith("#") or p.startswith("|") or p.startswith("```") or p.startswith("- ") or p.startswith("* "): continue
        p = re.sub(r"\s+", " ", p)
        if len(p) < 60: continue
        if re.match(r"^(\*\*)?(Note|Warning|Disclaimer|License|Model Developer|Model Dates|Model Type|Base Model)", p, re.I): continue
        out.append(p)
        if sum(len(x) for x in out) > 500: break
    return " ".join(out)[:700]
res = {}
for r in REPOS:
    md = raw(r)
    res[r] = purpose(md)
    print(r, "->", res[r][:110].replace("\n"," "), file=sys.stderr)
    time.sleep(0.3)
json.dump(res, sys.stdout, indent=1)
