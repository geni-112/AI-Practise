# Dataset and Calculation Reference

The canonical dataset is bundled at:

```text
assets/site/data/ai-hardware-config.json
```

## Dataset Structure

Top-level keys:

- `metadata`
- `hardware`
- `scenarios`
- `models`
- `cloudResources`
- `sources`

## Hardware Records

Each hardware record contains:

- `id`
- `name`
- `memoryGB`
- `usableMemoryRatio`
- `int8Tops`
- `fp16Tflops`
- `inferenceEfficiency`
- `confidence`
- `notes`

Current hardware:

- `ascend-910b`: 64GB planning assumption, medium confidence
- `ascend-950dt`: 144GB roadmap assumption, roadmap confidence

## Model Records

Each model record contains:

- `id`
- `name`
- `family`
- `releaseYear`
- `architecture`
- `totalParametersB`
- `activeParametersB`
- `maxContextTokens`
- `layers`
- `kvHeads`
- `headDim`
- `kvBytes`
- `kvCacheFactor`
- `weightOverheadFactor`
- `runtimeOverheadFactor`
- `frameworkReserveGB`
- `notes`
- `quantizations`

Current included models:

- `glm-5-1`: GLM-5.1, 744B total / 40B active planning basis, about 200K context, MoE + DSA
- `deepseek-v4-flash`: 284B total / 13B active, 1M context, hybrid compressed attention
- `glm-4-5`
- `qwen3-coder-480b`
- `deepseek-r1`
- `llama-3-3-70b`
- `qwen3-235b-a22b`

## Quantization Records

Each quantization record contains:

- `name`
- `bits`
- `qualityScore`
- `throughputFactor`
- `rationale`
- `scenarioFit`

GLM-5.1 quantization candidates:

- `BF16`
- `FP8`
- `NVFP4 / MXFP4`
- `AWQ 4-bit`
- `GGUF IQ2/2.7bpw`

DeepSeek-V4-Flash quantization candidates:

- `FP8 Mixed Base`
- `FP4 + FP8 Mixed`
- `4-bit MLX`

## Calculation Rules

Weight memory:

```text
totalParametersB * bits / 8 * weightOverheadFactor
```

KV cache:

```text
2 * layers * kvHeads * headDim * kvBytes * contextTokens * concurrency * kvCacheFactor / 1024^3
```

Runtime memory:

```text
weightMemory * runtimeOverheadFactor
```

Total memory:

```text
runtimeMemory + kvCacheMemory + frameworkReserveGB
```

Minimum card count:

```text
ceil(totalMemory / (hardware.memoryGB * hardware.usableMemoryRatio))
```

Estimated decode tokens per second per card:

```text
hardware.int8Tops * 1000 * hardware.inferenceEfficiency * quant.throughputFactor * scenario.throughputFactor / model.activeParametersB
```

The score combines:

- Fit score
- Quality score
- Context fit
- Scenario-specific bonus

## Source Policy

Before changing model facts, verify public sources. Use official model cards, official docs, config files, or public model indexes. Clearly label roadmap or low-confidence facts.

Current key sources:

- Huawei Cloud LA-Santiago region: `https://support.huaweicloud.com/intl/en-us/usermanual-organizations/org_03_0082.html`
- Ascend 910B third-party planning specs: `https://www.waredb.com/processor/ascend-910b`
- Ascend 950DT roadmap: `https://www.tomshardware.com/tech-industry/semiconductors/huawei-unveils-ascend-roadmap-backed-by-in-house-hbm`
- GLM-5.1 model card: `https://huggingface.co/zai-org/GLM-5.1`
- GLM-5.1 docs: `https://docs.z.ai/guides/llm/glm-5.1`
- GLM-5.1 quantized derivatives: `https://huggingface.co/models?other=base_model%3Aquantized%3Azai-org%2FGLM-5.1`
- DeepSeek-V4-Flash model card: `https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash`
- DeepSeek-V4-Flash config: `https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash/blob/main/config.json`
- Qwen3-Coder: `https://huggingface.co/Qwen/Qwen3-Coder-480B-A35B-Instruct`
- DeepSeek-R1: `https://huggingface.co/deepseek-ai/DeepSeek-R1`
- Llama 3.3 70B: `https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-meta-llama-3-3-70b-instruct.html`
