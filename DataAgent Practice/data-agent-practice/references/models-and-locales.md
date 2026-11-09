# Models and locales

## Configurable model service

Use a secure backend environment or ignored `.env`. Default values are `MODEL_PROVIDER=huawei_maas` and `MODEL_NAME=glm-5.3`. Configure `MODEL_BASE_URL`, `MODEL_API_KEY` and optional `MODEL_TIMEOUT`; the MaaS endpoint is the OpenAI-compatible base URL shown by that account. Do not assume the model is served from Mexico just because the DWS cluster is in Mexico.

For another authorized compatible model, set `MODEL_PROVIDER=openai_compatible` and its model, URL and key. Keep one explicitly selected provider; never silently fall back to another account or service. Network errors and model plan validation failures must remain visible as failures.

The openJiuwen model generates a validated structured plan. `backend/planning.py` compiles supported metrics/dimensions into parameterized SQL. Broader natural language support does not grant arbitrary SQL execution or enlarge the subject's data scope. Without model configuration, only `DEMO_MODE=true` may use labeled `demo_rules`; production mode fails closed.

The UI model editor stores a **non-sensitive draft** only. It does not change backend credentials or prove a model call succeeded. Never add API keys to `src`, `public`, localStorage, `VITE_*`, GitHub examples or screenshots.

## Language and design

| Locale | User label | Preferred font |
|---|---|---|
| `zh-CN` | 简体中文 | Microsoft YaHei / 微软雅黑 with system fallback |
| `en-US` | English (US) | Arial |
| `es-ES` | Español | Verdana |

The top-right selector persists under localStorage `nexo-locale`. The shared sign-in page uses the same preference. No external font download is needed; Windows/installed fonts determine availability and local fallbacks apply elsewhere.

Keep orange/coral actions, white surfaces and light gray backgrounds consistent across all six workbench pages, drawers, dialogs, charts and login. Body/table text is 14–16px and secondary text at least 13px; handle narrow layouts by wrapping or scrolling rather than shrinking text.

`src/messages.json` is shared by frontend and `backend/localization.py`; ship it with **backend-only deployments as well**. `/api/analyze` accepts `locale` (`zh-CN`, `en-US`, `es-ES`) for plan titles and summaries. Dataset IDs, tenant IDs, domain keys, dates and warehouse values retain their canonical form.

When adding strings, update shared translations, dynamic chart/ARIA text, dialogs and API summaries. Verify persistence after reload, local font-family and query results for all three locales. Synthetic data stays English. Do not label preset review sentiments as live LLM inference.
