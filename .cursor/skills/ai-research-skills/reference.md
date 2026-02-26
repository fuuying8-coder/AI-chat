# AI-Research-SKILLs — Reference

## Repository

- **GitHub**: https://github.com/zechenzhangAGI/AI-Research-SKILLs  
- **Mirror**: https://github.com/Orchestra-Research/AI-Research-SKILLs  
- **Install**: `npx @orchestra-research/ai-research-skills` (installs to `~/.orchestra/skills/`, symlinks to Cursor and other agents)

## Categories and skills (85 total)

| Category | Path | Skills |
|----------|------|--------|
| Model Architecture | 01-model-architecture | LitGPT, Mamba, RWKV, NanoGPT, TorchTitan |
| Tokenization | 02-tokenization | HuggingFace Tokenizers, SentencePiece |
| Fine-Tuning | 03-fine-tuning | Axolotl, LLaMA-Factory, PEFT, Unsloth |
| Mech Interp | 04-mechanistic-interpretability | TransformerLens, SAELens, pyvene, nnsight |
| Data Processing | 05-data-processing | NeMo Curator, Ray Data |
| Post-Training | 06-post-training | TRL, GRPO, OpenRLHF, SimPO, verl, slime, miles, torchforge |
| Safety & Alignment | 07-safety-alignment | Constitutional AI, LlamaGuard, NeMo Guardrails, Prompt Guard |
| Distributed Training | 08-distributed-training | DeepSpeed, FSDP, Accelerate, Megatron-Core, Lightning, Ray Train |
| Infrastructure | 09-infrastructure | Modal, Lambda Labs, SkyPilot |
| Optimization | 10-optimization | Flash Attention, bitsandbytes, GPTQ, AWQ, HQQ, GGUF |
| Evaluation | 11-evaluation | lm-eval-harness, BigCode, NeMo Evaluator |
| Inference & Serving | 12-inference-serving | vLLM, TensorRT-LLM, llama.cpp, SGLang |
| MLOps | 13-mlops | W&B, MLflow, TensorBoard |
| Agents | 14-agents | LangChain, LlamaIndex, CrewAI, AutoGPT |
| RAG | 15-rag | Chroma, FAISS, Pinecone, Qdrant, Sentence Transformers |
| Prompt Engineering | 16-prompt-engineering | DSPy, Instructor, Guidance, Outlines |
| Observability | 17-observability | LangSmith, Phoenix |
| Multimodal | 18-multimodal | CLIP, Whisper, LLaVA, BLIP-2, SAM, Stable Diffusion, AudioCraft |
| Emerging Techniques | 19-emerging-techniques | MoE, Model Merging, Long Context, Speculative Decoding, Distillation, Pruning |
| ML Paper Writing | 20-ml-paper-writing | ML Paper Writing |
| Research Ideation | 21-research-ideation | Research Brainstorming, Creative Thinking |

## Skill layout in repo

Each skill lives under its category, e.g. `12-inference-serving/vllm/SKILL.md`. Many skills also include `references/` (README, API, issues, etc.) and optional `scripts/` or `assets/`.
