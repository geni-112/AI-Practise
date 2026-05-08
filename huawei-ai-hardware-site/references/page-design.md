# Page Design Reference

## Language and Typography

- Use English UI copy.
- Use `Arial, sans-serif` for the whole page.
- Keep all source files ASCII when possible to avoid Windows PowerShell and encoding issues.

## Layout

Use a functional app layout, not a marketing landing page:

1. Full-width hero with real image background and concise title.
2. Left configuration panel.
3. Right recommendation/result panel.
4. Calculation details section.
5. Huawei Cloud resource plan section.
6. Public data and assumptions section.

## Inputs

The filter form must include:

- Hardware SKU: Ascend 910B, Ascend 950DT
- Hardware count
- Model
- Use case: Coding, Chatbot, RAG / Knowledge Base, Agent / Tool Use, Reasoning
- Context tokens: 8K, 32K, 64K, 100K, 128K, 200K, 256K, 512K, 1M
- Concurrency: 1, 4, 8, 16, 32, 64, 128, 256, 512, 800

Behavior:

- Require at least three filled inputs before generating a result.
- Require both hardware and model to calculate memory.
- Default missing scenario to `chatbot`.
- Default missing context to 32K.
- Default missing concurrency to 1.
- Default missing hardware count to 1.

## Result Panel

Show:

- Fit status
- Plain-English recommendation sentence
- Model
- Use case
- Recommended quantization
- Minimum hardware count
- Memory pressure meter
- Context fit meter
- Estimated per-user decode tokens/s
- Recommendation rationale
- All quantization candidates with fit/undersized status

## Calculation Section

Show four cards:

- Weight memory
- Runtime reserve
- KV cache
- Total memory

Each card should show the numeric value and formula.

## Visual Style

- Use restrained colors: light background, white panels, teal primary accent.
- Keep card radius at 8px.
- Avoid heavy gradients except the hero image overlay.
- Avoid decorative blobs/orbs.
- Make dense operational information scannable.
- Ensure text does not overlap at mobile widths.

## Current Public Hero Image

The current template uses:

```text
https://images.unsplash.com/photo-1518709268805-4e9042af2176?auto=format&fit=crop&w=1800&q=80
```

If network access or image licensing requirements change, replace with another relevant real data-center or hardware image.
