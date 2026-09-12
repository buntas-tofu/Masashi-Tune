#!/usr/bin/env python3
"""HF Hub survey: for each base model, what quant/format repos exist, plus the base card facts.
Public API only, no auth. Output JSON to stdout."""
import json, sys, time, urllib.request, urllib.parse, re

BASES = [
 # (label, base_repo, search_terms)
 ("Nemotron-3-Super-120B-A12B", "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B", ["Nemotron-3-Super-120B"]),
 ("Nemotron-Cascade-2-30B-A3B", "nvidia/Nemotron-Cascade-2-30B-A3B", ["Nemotron-Cascade-2"]),
 ("Nemotron-3-Nano-Omni-30B-A3B", "nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16", ["Nemotron-3-Nano-Omni"]),
 ("Nemotron-3-Nano-30B-A3B", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16", ["Nemotron-3-Nano-30B"]),
 ("Hermes-4-14B", "NousResearch/Hermes-4-14B", ["Hermes-4-14B"]),
 ("Hermes-4-70B", "NousResearch/Hermes-4-70B", ["Hermes-4-70B"]),
 ("Hermes-4-405B", "NousResearch/Hermes-4-405B", ["Hermes-4-405B"]),
 ("NousCoder-14B", "NousResearch/NousCoder-14B", ["NousCoder"]),
 ("Phi-4-reasoning-plus", "microsoft/Phi-4-reasoning-plus", ["Phi-4-reasoning-plus"]),
 ("OpenMath-Nemotron-14B", "nvidia/OpenMath-Nemotron-14B", ["OpenMath-Nemotron-14B"]),
 ("OpenMath-Nemotron-32B", "nvidia/OpenMath-Nemotron-32B", ["OpenMath-Nemotron-32B"]),
 ("gemma-4-26B-A4B", "google/gemma-4-26B-A4B-it", ["gemma-4-26B-A4B"]),
 ("gemma-4-31B", "google/gemma-4-31B-it", ["gemma-4-31B"]),
 ("gemma-4-E4B", "google/gemma-4-E4B-it", ["gemma-4-E4B"]),
 ("gemma-4-E2B", "google/gemma-4-E2B-it", ["gemma-4-E2B"]),
 ("embeddinggemma-300m", "google/embeddinggemma-300m", ["embeddinggemma-300m"]),
 ("gpt-oss-20b", "openai/gpt-oss-20b", ["gpt-oss-20b"]),
 ("granite-embedding-english-r2", "ibm-granite/granite-embedding-english-r2", ["granite-embedding-english-r2"]),
 ("granite-embedding-reranker-english-r2", "ibm-granite/granite-embedding-reranker-english-r2", ["granite-embedding-reranker"]),
 ("granite-guardian-4.1-8b", "ibm-granite/granite-guardian-4.1-8b", ["granite-guardian-4.1"]),
 ("llama-nemotron-embed-1b-v2", "nvidia/llama-nemotron-embed-1b-v2", ["llama-nemotron-embed-1b"]),
 ("llama-nemotron-rerank-1b-v2", "nvidia/llama-nemotron-rerank-1b-v2", ["llama-nemotron-rerank-1b"]),
 ("Llama-Prompt-Guard-2-86M", "meta-llama/Llama-Prompt-Guard-2-86M", ["Prompt-Guard-2-86M"]),
 ("olmOCR-2-7B-1025", "allenai/olmOCR-2-7B-1025", ["olmOCR-2-7B"]),
 ("Llama-3.3-Nemotron-Super-49B-v1.5", "nvidia/Llama-3_3-Nemotron-Super-49B-v1_5", ["Nemotron-Super-49B-v1_5", "Nemotron-Super-49B-v1.5"]),
 ("Olmo-3.1-32B-Instruct", "allenai/Olmo-3.1-32B-Instruct", ["Olmo-3.1-32B"]),
 ("Mistral-Small-4-119B", "mistralai/Mistral-Small-4-119B-2603", ["Mistral-Small-4-119B"]),
 ("Magistral-Small-2509", "mistralai/Magistral-Small-2509", ["Magistral-Small-2509"]),
 ("Mistral-Small-3.2-24B", "mistralai/Mistral-Small-3.2-24B-Instruct-2506", ["Mistral-Small-3.2-24B"]),
 ("Ministral-3-14B", "mistralai/Ministral-3-14B-Instruct-2512", ["Ministral-3-14B"]),
 ("Ministral-3-3B", "mistralai/Ministral-3-3B-Instruct-2512", ["Ministral-3-3B"]),
 ("Devstral-Small-2-24B", "mistralai/Devstral-Small-2-24B-Instruct-2512", ["Devstral-Small-2"]),
 ("FLUX.2-klein-9B", "black-forest-labs/FLUX.2-klein-9B", ["FLUX.2-klein"]),
 ("VibeVoice-1.5B", "microsoft/VibeVoice-1.5B", ["VibeVoice"]),
 ("Nemotron-Parse-v1.2", "nvidia/NVIDIA-Nemotron-Parse-v1.2", ["Nemotron-Parse"]),
]

UA = {"User-Agent": "zoo-survey/0.1 (model-card survey; public API only)"}

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            err = e; time.sleep(1.5*(i+1))
    return {"_error": str(err)}

def bucket(mid, tags):
    m = mid.lower(); t = " ".join(tags).lower()
    b = []
    if "gguf" in m or "gguf" in t: b.append("GGUF")
    if "nvfp4" in m or "-fp4" in m or "_fp4" in m or "nvfp4" in t: b.append("NVFP4")
    if re.search(r"(^|[-_])fp8", m) or "fp8" in t: b.append("FP8")
    if "mxfp4" in m: b.append("MXFP4")
    if "awq" in m or "awq" in t: b.append("AWQ")
    if "gptq" in m or "gptq" in t: b.append("GPTQ")
    if re.search(r"w4a16|int4|4bit|-4-bit", m) or "compressed-tensors" in t and "int4" in m: b.append("INT4/W4A16")
    if "mlx" in m or "mlx" in t: b.append("MLX")
    if "exl2" in m or "exl3" in m: b.append("EXL")
    if "bnb" in m or "bitsandbytes" in t: b.append("BNB")
    if "onnx" in m or "onnx" in t: b.append("ONNX")
    return b

out = []
for label, base, terms in BASES:
    meta = get(f"https://huggingface.co/api/models/{urllib.parse.quote(base, safe='/')}")
    st = meta.get("safetensors", {}) if isinstance(meta, dict) else {}
    card = meta.get("cardData", {}) if isinstance(meta, dict) else {}
    seen = {}
    for term in terms:
        res = get(f"https://huggingface.co/api/models?search={urllib.parse.quote(term)}&limit=100&sort=downloads&direction=-1")
        if isinstance(res, list):
            for r in res:
                mid = r.get("id") or r.get("modelId")
                if not mid or mid in seen: continue
                seen[mid] = {"id": mid, "downloads": r.get("downloads"), "tags": r.get("tags", []), "buckets": bucket(mid, r.get("tags", []))}
    hits = list(seen.values())
    fmt = {}
    for h in hits:
        for b in h["buckets"]:
            fmt.setdefault(b, []).append((h["id"], h["downloads"] or 0))
    fmt_sorted = {k: sorted(v, key=lambda x: -x[1])[:6] for k, v in fmt.items()}
    official = [h["id"] for h in hits if h["id"].split("/")[0].lower() == base.split("/")[0].lower()]
    out.append({
        "label": label, "base": base,
        "pipeline_tag": meta.get("pipeline_tag") if isinstance(meta, dict) else None,
        "license": card.get("license") if isinstance(card, dict) else None,
        "gated": meta.get("gated") if isinstance(meta, dict) else None,
        "params_total": st.get("total") if isinstance(st, dict) else None,
        "downloads": meta.get("downloads") if isinstance(meta, dict) else None,
        "tags": [t for t in (meta.get("tags", []) if isinstance(meta, dict) else []) if not t.startswith(("region:", "dataset:", "arxiv:", "base_model:", "license:"))][:18],
        "base_error": meta.get("_error") if isinstance(meta, dict) else None,
        "n_hits": len(hits),
        "official_repos": official[:20],
        "formats": fmt_sorted,
    })
    print(f"{label:40} base_ok={not meta.get('_error') if isinstance(meta,dict) else False} hits={len(hits)} formats={sorted(fmt_sorted.keys())}", file=sys.stderr)
    time.sleep(0.4)
json.dump(out, sys.stdout, indent=1)
