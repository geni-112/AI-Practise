# /huawei-add-model — Add a new model or quantization to the AI Capacity Planner

Guides you through editing the data model, validating it, syncing the JS fallback,
and deploying the change live.

Config file: `C:\Users\Matebook\huawei-ai-hardware-site\data\ai-hardware-config.json`

---

## Part A — Add a new quantization to an existing model

### Step 1 — Find the model entry in the JSON

```powershell
$json = Get-Content "C:\Users\Matebook\huawei-ai-hardware-site\data\ai-hardware-config.json" | ConvertFrom-Json
$json.models | Select-Object id, displayName, @{n='quants';e={$_.quantizations.Count}}
```

### Step 2 — Edit the file

Open `data/ai-hardware-config.json` and add a new entry to the model's `quantizations` array.

**Quantization object schema**:
```json
{
  "id": "unique-id-lowercase-hyphen",
  "name": "Display Name",
  "bits": 4,
  "weightOverheadFactor": 1.05,
  "throughputFactor": 2.55,
  "kvBits": 8,
  "qualityScore": 85,
  "scenarioBoost": ["chatbot", "coding"]
}
```

**Field guidance**:

| Field | Meaning | Typical values |
|-------|---------|----------------|
| `bits` | Weight precision | 16 (BF16/FP16), 8 (FP8/INT8), 4 (AWQ/GPTQ/GGUF Q4), 3 (GGUF Q3), 2 (GGUF Q2/IQ2) |
| `weightOverheadFactor` | Memory multiplier over raw bit-packing | 1.04–1.10 (higher = more overhead) |
| `throughputFactor` | Relative decode speed vs BF16 | BF16=1.0, FP8≈1.8, INT8≈1.75, 4-bit≈2.5, 2-bit≈3.2 |
| `kvBits` | KV cache precision | 16 for BF16, 8 for quantized |
| `qualityScore` | 0–100 quality vs full precision | BF16=97, FP8=93, INT8=91, AWQ4=86, GGUF Q4=83, GGUF Q2=58 |
| `scenarioBoost` | Scenarios where this quant excels | `chatbot`, `coding`, `rag`, `agent`, `reasoning` |

**Common quantization reference**:
```json
{ "id": "bf16",      "name": "BF16",            "bits": 16, "weightOverheadFactor": 1.05, "throughputFactor": 1.00, "kvBits": 16, "qualityScore": 97, "scenarioBoost": [] },
{ "id": "fp8",       "name": "FP8",             "bits": 8,  "weightOverheadFactor": 1.04, "throughputFactor": 1.82, "kvBits": 8,  "qualityScore": 93, "scenarioBoost": ["chatbot"] },
{ "id": "int8",      "name": "INT8 (SmoothQuant)","bits": 8, "weightOverheadFactor": 1.05, "throughputFactor": 1.75, "kvBits": 8,  "qualityScore": 91, "scenarioBoost": ["rag"] },
{ "id": "awq4",      "name": "AWQ 4-bit",       "bits": 4,  "weightOverheadFactor": 1.05, "throughputFactor": 2.55, "kvBits": 8,  "qualityScore": 86, "scenarioBoost": ["agent"] },
{ "id": "gptq-int4", "name": "GPTQ INT4",       "bits": 4,  "weightOverheadFactor": 1.05, "throughputFactor": 2.50, "kvBits": 8,  "qualityScore": 85, "scenarioBoost": [] },
{ "id": "gguf-q4",   "name": "GGUF Q4_K_M",     "bits": 4,  "weightOverheadFactor": 1.06, "throughputFactor": 2.35, "kvBits": 8,  "qualityScore": 83, "scenarioBoost": [] },
{ "id": "gguf-q3",   "name": "GGUF Q3_K_M",     "bits": 3,  "weightOverheadFactor": 1.07, "throughputFactor": 2.85, "kvBits": 8,  "qualityScore": 74, "scenarioBoost": [] },
{ "id": "gguf-q2",   "name": "GGUF Q2_K",       "bits": 2,  "weightOverheadFactor": 1.10, "throughputFactor": 3.40, "kvBits": 4,  "qualityScore": 58, "scenarioBoost": [] }
```

---

## Part B — Add a completely new model

### Step 1 — Gather model architecture specs

You need (from the model card / technical report):
- Total parameter count (B)
- Active parameter count (B) — same as total for dense; fraction for MoE
- Number of layers
- Number of KV heads (GQA)
- Head dimension
- Max context length
- Architecture type: `dense` or `moe`

### Step 2 — Calculate kvCacheFactor

For dense GQA models: `kvCacheFactor = 1.0`
For MoE with MLA (compressed KV like DeepSeek/GLM): `kvCacheFactor = 0.04–0.08`
For standard MoE without MLA: `kvCacheFactor = 0.1–0.2`

### Step 3 — Add the model object

Insert into the `models` array in `ai-hardware-config.json`:
```json
{
  "id": "model-id-hyphen",
  "name": "Short Name",
  "displayName": "Full Name (size + arch)",
  "architecture": "dense",
  "totalParametersB": 70,
  "activeParametersB": 70,
  "layers": 80,
  "kvHeads": 8,
  "headDim": 128,
  "kvCacheFactor": 1.00,
  "frameworkReserveGB": 4,
  "maxContextTokens": 128000,
  "supportedContext": [8192, 32768, 65536, 100000, 128000],
  "note": "Source: model card URL",
  "quantizations": [ ... ]
}
```

**frameworkReserveGB guide**: 3–4 GB for small models, 5–6 for medium, 7–8 for 500B+

---

## Step 3 — Validate the JSON

```powershell
$json = Get-Content "C:\Users\Matebook\huawei-ai-hardware-site\data\ai-hardware-config.json" | ConvertFrom-Json
Write-Host "Models: $($json.models.Count)"
$json.models | ForEach-Object {
    Write-Host "  $($_.displayName): $($_.quantizations.Count) quants"
}
```

JSON must parse without errors. If `ConvertFrom-Json` throws, find and fix the syntax error first.

## Step 4 — Sync INLINE_CONFIG and deploy

```powershell
cd "C:\Users\Matebook\huawei-ai-hardware-site"
powershell -NonInteractive -ExecutionPolicy Bypass -File fix-inline-config.ps1
powershell -NonInteractive -ExecutionPolicy Bypass -File deploy-and-reinstall.ps1
```

## Step 5 — Verify live

```powershell
$cfg = (Invoke-WebRequest "http://110.238.65.209/data/ai-hardware-config.json" -UseBasicParsing).Content | ConvertFrom-Json
$cfg.models | Select-Object id, @{n='quants';e={$_.quantizations.Count}}
```
