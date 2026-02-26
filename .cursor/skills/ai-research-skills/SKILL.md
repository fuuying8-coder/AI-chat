---
name: ai-research-skills
description: Guides use of the zechenzhangAGI/AI-Research-SKILLs library—85 production-ready AI research engineering skills across 21 categories (model architecture, fine-tuning, inference, RAG, agents, etc.). Use when implementing or researching AI/ML workflows, fine-tuning LLMs, distributed training, optimization, evaluation, or when the user mentions AI-Research-SKILLs, Orchestra Research, or specific frameworks (vLLM, TRL, Axolotl, PEFT, etc.).
---

# AI-Research-SKILLs (zechenzhangAGI)

Reference the **AI-Research-SKILLs** library when the task involves AI research engineering: training, fine-tuning, inference, evaluation, agents, RAG, or related tooling.

## What It Is

- **Repo**: [zechenzhangAGI/AI-Research-SKILLs](https://github.com/zechenzhangAGI/AI-Research-SKILLs) (also [Orchestra-Research/AI-Research-SKILLs](https://github.com/Orchestra-Research/AI-Research-SKILLs))
- **Content**: 85 skills in 21 categories; each skill is a `SKILL.md` plus optional references/scripts.
- **Install (optional)**: `npx @orchestra-research/ai-research-skills` — interactive installer for Cursor and other agents; installs to `~/.orchestra/skills/` with symlinks.

## When to Use This Skill

- User asks about **fine-tuning** (Axolotl, LLaMA-Factory, PEFT, Unsloth) → use **03-fine-tuning**.
- User asks about **inference/serving** (vLLM, TensorRT-LLM, llama.cpp, SGLang) → use **12-inference-serving**.
- User asks about **distributed training** (DeepSpeed, FSDP, Accelerate, Megatron, Lightning, Ray Train) → use **08-distributed-training**.
- User asks about **optimization** (Flash Attention, bitsandbytes, GPTQ, AWQ, HQQ, GGUF) → use **10-optimization**.
- User asks about **post-training / RL** (TRL, GRPO, OpenRLHF, SimPO, verl, slime, miles, torchforge) → use **06-post-training**.
- User asks about **agents** (LangChain, LlamaIndex, CrewAI, AutoGPT) → use **14-agents**.
- User asks about **RAG** (Chroma, FAISS, Pinecone, Qdrant, Sentence Transformers) → use **15-rag**.
- User asks about **evaluation** (lm-eval-harness, BigCode, NeMo Evaluator) → use **11-evaluation**.
- User asks about **model architecture** (LitGPT, Mamba, RWKV, NanoGPT, TorchTitan) → use **01-model-architecture**.
- User asks about **tokenization** (HuggingFace Tokenizers, SentencePiece) → use **02-tokenization**.
- User asks about **mechanistic interpretability** (TransformerLens, SAELens, pyvene, nnsight) → use **04-mechanistic-interpretability**.
- User asks about **data processing** (NeMo Curator, Ray Data) → use **05-data-processing**.
- User asks about **safety/alignment** (Constitutional AI, LlamaGuard, NeMo Guardrails, Prompt Guard) → use **07-safety-alignment**.
- User asks about **infrastructure** (Modal, SkyPilot, Lambda Labs) → use **09-infrastructure**.
- User asks about **MLOps** (W&B, MLflow, TensorBoard) → use **13-mlops**.
- User asks about **prompt engineering** (DSPy, Instructor, Guidance, Outlines) → use **16-prompt-engineering**.
- User asks about **observability** (LangSmith, Phoenix) → use **17-observability**.
- User asks about **multimodal** (CLIP, Whisper, LLaVA, BLIP-2, SAM, Stable Diffusion, AudioCraft) → use **18-multimodal**.
- User asks about **emerging techniques** (MoE, model merging, long context, speculative decoding, distillation, pruning) → use **19-emerging-techniques**.
- User asks about **ML paper writing** (NeurIPS, ICML, LaTeX, citations) → use **20-ml-paper-writing**.
- User asks about **research ideation** (brainstorming, creative thinking) → use **21-research-ideation**.

## How to Use

1. **If skills are installed** (e.g. via `npx @orchestra-research/ai-research-skills`): read the relevant skill from the installed path (e.g. under `~/.orchestra/skills/` or Cursor’s skills directory) and follow its instructions.
2. **If not installed**: use the GitHub repo. Open the category folder and the specific skill’s `SKILL.md`, e.g.:
   - `https://github.com/zechenzhangAGI/AI-Research-SKILLs/blob/main/12-inference-serving/vllm/SKILL.md`
   - `https://github.com/zechenzhangAGI/AI-Research-SKILLs/blob/main/03-fine-tuning/axolotl/SKILL.md`
3. **Apply the skill**: follow that skill’s “When to use” and steps; prefer its code patterns and references over inventing from scratch.

## Category Index (path prefix)

| Category | Repo path |
|----------|-----------|
| Model Architecture | `01-model-architecture/` |
| Tokenization | `02-tokenization/` |
| Fine-Tuning | `03-fine-tuning/` |
| Mechanistic Interpretability | `04-mechanistic-interpretability/` |
| Data Processing | `05-data-processing/` |
| Post-Training | `06-post-training/` |
| Safety & Alignment | `07-safety-alignment/` |
| Distributed Training | `08-distributed-training/` |
| Infrastructure | `09-infrastructure/` |
| Optimization | `10-optimization/` |
| Evaluation | `11-evaluation/` |
| Inference & Serving | `12-inference-serving/` |
| MLOps | `13-mlops/` |
| Agents | `14-agents/` |
| RAG | `15-rag/` |
| Prompt Engineering | `16-prompt-engineering/` |
| Observability | `17-observability/` |
| Multimodal | `18-multimodal/` |
| Emerging Techniques | `19-emerging-techniques/` |
| ML Paper Writing | `20-ml-paper-writing/` |
| Research Ideation | `21-research-ideation/` |

## Quick Install (for the user)

To install all or selected skills into Cursor (and other agents):

```bash
npx @orchestra-research/ai-research-skills
```

Then use “list” or “update” as needed. For full repo layout and README, see [GitHub](https://github.com/zechenzhangAGI/AI-Research-SKILLs).
