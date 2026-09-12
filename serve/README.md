# Serve

The serving lane: one llama.cpp or vLLM launch script per model vessel, plus
the gated art judge in `art/`. Every script is a thin wrapper that sets neutral
defaults and hands them to a real server binary. Ports, model paths, the llama
binary, and any GPU pin are environment variables with documented defaults, so
the same scripts run on any box with the weights staged.

Two backends, two shapes:

- **llama.cpp** (`serve-gemma.sh`, `serve-vision-27b.sh`, `serve-math-30b.sh`,
  `serve-code-14b.sh`, `serve-hermes-43-36b.sh`, the three `serve-openmath*`
  scripts, `serve-phi4rp.sh`): a local `llama-server`. `-ngl 99` puts every
  layer on the GPU. The CUDA build pins by GPU UUID (enumeration order can
  differ from nvidia-smi); the Vulkan build resolves its shared libraries
  through `LD_LIBRARY_PATH` because the baked RUNPATH goes stale on a move.
- **vLLM docker** (`serve-gptoss20b.sh`, `serve-guardian8b.sh`,
  `serve-nano-omni.sh`, `serve-olmocr7b.sh`, `serve-nemotron-embed.sh`,
  `serve-nemotron-rerank.sh`): a `docker run` of the vLLM image. Each guest
  passes an explicit `--gpu-memory-utilization` pool, because an omitted pool
  makes vLLM grab 0.9 of the card for any model. Guests run offline with the
  model store mounted read-only.

## Index

| script | model class | purpose | default port |
|---|---|---|---|
| `serve-gemma.sh` | Gemma 4 26B-A4B MoE, chat + vision | general chat and image vessel, Vulkan | 8080 |
| `serve-vision-27b.sh` | Qwen3.5-27B multimodal | the chat and vision face, CUDA | 8080 |
| `serve-math-30b.sh` | 30B math MoE | the math specialist, long context | 8083 |
| `serve-code-14b.sh` | 14B code model | the code specialist, lazy | 8082 |
| `serve-hermes-43-36b.sh` | Hermes-4.3-36B | the creative writer | 8094 |
| `serve-gptoss20b.sh` | gpt-oss-20b | bench guest, MXFP4 | 8092 |
| `serve-guardian8b.sh` | granite-guardian-4.1-8b | groundedness and tool-call auditor | 8091 |
| `serve-nano-omni.sh` | Nemotron-3-Nano-Omni-30B | burst tongue, wake-gated | 8003 |
| `serve-olmocr7b.sh` | olmOCR-2-7B | document OCR | 8087 |
| `serve-nemotron-embed.sh` | llama-nemotron-embed-1b-v2 | RAG embedder | 8094 |
| `serve-nemotron-rerank.sh` | llama-nemotron-rerank-1b-v2 | RAG reranker, offline | 8095 |
| `serve-openmath14b.sh` | OpenMath-Nemotron-14B | math bench guest | 8091 |
| `serve-openmath14bk.sh` | OpenMath-Nemotron-14B-Kaggle | math bench guest, tuned sibling | 8092 |
| `serve-openmath32b.sh` | OpenMath-Nemotron-32B | math bench guest, family ceiling | 8093 |
| `serve-phi4rp.sh` | Phi-4-reasoning-plus 14B | math bench guest | 8090 |

### Port convention

The serve lane keeps the 8080 to 8095 block for llama.cpp vessels and the
8000 to 8099 block for vLLM guests, so nothing in this lane collides with the
reserved control ports. Ports must be unique per box, not per fleet: two
vessels on different boxes may reuse a number (for example 8094 appears for
the Hermes writer and for the embedder, which never share a host). All
scripts bind loopback by default; set `HOST` to expose on a LAN or overlay.

## Capacity note: the 30B math vessel

`serve-math-30b.sh` needs a stable slot near 21GB and a long context. The
default context is 131072, whose KV is about 12.9GB at f16, so the vessel
wants a box that has that room idle. Do not wake it beside a dense ~87GB
120B vessel or a second 30B math guest on the same host. The freeze lesson is
real: waking two large math vessels together has locked a box solid. Serve
it where the room is, on the backend (Vulkan or CUDA) that measures fastest
for that silicon.

## Environment variables

Every value that varies by deployment is a variable with a neutral default:

- `MODELS_ROOT` (default `$HOME/models`) root of the model store; each script
  derives its `MODEL_DIR` from it. Override with `MODEL_DIR` or `MODEL`.
- `LLAMA_SERVER` (default `$HOME/llama.cpp/build/<backend>/bin/llama-server`).
- `HOST` (default `127.0.0.1`) and `PORT`.
- `GPU` (vLLM guests, nvidia-smi index) and `GPUMEM` (memory pool).
- `GPU_UUID` (CUDA vessel): pin the card by UUID; empty leaves the environment
  as-is.
- `LORA` (vision vessel): a GGUF adapter to ride the base weights; empty
  serves bare.
- `LLAMA_API_KEY_FILE`: a path to an API key file, passed through when set.
- `SERVE_ENV`: an optional env file to source for anything above.
- The art judge (see `art/`) uses `JUDGE_VISION_MODEL` and `VIEW_HARNESS`.

Two flags are deliberately load-bearing and shared across vessels:

- `--reasoning off --reasoning-budget 0` on the vision vessel. Qwen thinks by
  default and would spend the budget on hidden reasoning and return empty
  content with a healthy 200. See `serve-vision-27b.sh`.
- `--reasoning-format none` on the math vessels. The token-level extractor
  matches an open think tag but never its close, so the whole reply lands in
  `reasoning_content` and content arrives empty. The harness splits the raw
  inline tags at text level. See `serve-math-30b.sh`.
