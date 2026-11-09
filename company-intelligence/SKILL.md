---
name: company-intelligence
description: Produce evidence-backed, decision-ready intelligence for any enterprise, company, business group, competitor, customer account, partner, or market. Use for company profiles, change monitoring, executive briefs, account intelligence, competitor intelligence, market intelligence, sales insights, battlecards, strategy, financial and operating performance, leadership, customers, expansion, investment, partnerships, M&A, risk, supply chain, digital transformation, or evidence-based business and technology opportunity discovery. Apply a universal enterprise framework first, then add an industry pack only when it improves the analysis; treat cloud, AI, data, and IT as optional lenses rather than the default subject.
---

# Company Intelligence

Produce decision-ready enterprise intelligence by combining a universal company model, a common evidence engine, the user's intent, and—only when useful—an industry pack. Keep the subject, industry, intent, audience, and technology lens separate.

## Route the request

1. Define a research contract: subject, entity boundary, geography, time window, intent, audience, focus topics, comparison baseline, and requested depth. Infer missing fields when low-risk and disclose the assumptions.
2. Disambiguate the legal entity, brand, geography, and parent/subsidiary when material.
3. Preserve an explicit time window. If absent, use 90 days for change monitoring and the latest fiscal year for baseline context.
4. Classify intent:
   - `competitor`: capability/strategy delta, threat, opportunity, battlecard.
   - `account`: business change, priority, trigger/pain, IT implication, opportunity, next engagement.
   - `market`: patterns across companies, market direction, whitespace, implications.
   - `partner`: ecosystem fit, joint value, overlap, dependencies, and engagement path.
   - `investment`: performance, strategy execution, catalysts, risks, and open questions; do not provide personalized financial advice.
   - `general`: balanced enterprise brief when intent is unspecified.
5. Select the requested output audience: executive, account, sales, strategy, investment, or technical. Default to executive plus account insight for customer research; executive plus battlecard for competitor research.
6. Classify the industry. Load one primary pack only when it adds useful KPIs, terminology, sources, or questions. Use the general-enterprise pack when no specialist pack fits; load a second pack only for a genuinely cross-industry business.

## Load required references

Always read [universal-enterprise-framework.md](references/universal-enterprise-framework.md) and [core-engine.md](references/core-engine.md). Then read:

- Cloud providers, AI/data platforms, enterprise software: [cloud-ai.md](references/industry-packs/cloud-ai.md)
- Banks and financial institutions: [banking.md](references/industry-packs/banking.md)
- Telecommunications: [telecom.md](references/industry-packs/telecom.md)
- Retail, consumer, marketplaces: [retail.md](references/industry-packs/retail.md)
- Industrial, automotive, supply chain: [manufacturing.md](references/industry-packs/manufacturing.md)
- Internet and digital platforms: [internet.md](references/industry-packs/internet.md)
- Government and public institutions: [government.md](references/industry-packs/government.md)
- All other companies: [general-enterprise.md](references/industry-packs/general-enterprise.md)

Read [intent-and-output.md](references/intent-and-output.md) for the selected intent and output format. Do not load unrelated packs.

## Execute

1. Build a compact enterprise baseline with the universal framework. Select only dimensions relevant to the research contract.
2. Create an issue tree and search plan from the user's focus, not from a fixed cloud taxonomy.
3. Search the requested period using official sources first, then high-quality independent sources. Search in the company's home language and English when useful.
4. Record atomic events. Separate sourced facts from inference; never turn an inference into a fact.
5. Verify material claims, score confidence and importance, cluster related events, and compare them with the baseline.
6. Derive implications through this chain: `fact -> change -> business meaning -> affected capability/stakeholder -> opportunity or threat -> next action`. Add an IT, cloud, data, AI, or security implication only when the business change requires it or the user requests it.
7. Apply the pack's KPIs, terminology, sources, and questions without replacing the universal framework.
8. Synthesize across events. Identify reinforcing signals, contradictions, dependencies, timing, scenarios, and unknowns.
9. Render for the intent and audience. Lead with changes, meaning, and decisions—not company biography or a list of news.

## Guardrails

- Cite every material current fact with a direct source and date.
- State when evidence is single-source, contradictory, stale, paywalled, or unavailable.
- Use exact dates rather than relative wording when ambiguity is possible.
- Distinguish announced, planned, piloted, contracted, deployed, and measured outcomes.
- Treat product/vendor mapping as a hypothesis unless procurement or deployment is evidenced.
- Do not infer a technology opportunity merely because the company is growing, investing, or discussing transformation. Name the business trigger and required capability first.
- Avoid generic opportunity lists. Tie every recommendation to a verified trigger and name the stakeholder and validation question.
- Do not fabricate financial figures, quotes, relationships, technology stacks, or intent.

## Minimum completion standard

Return: research contract and as-of date; enterprise baseline; executive takeaways; prioritized changes; intent-specific analysis; evidence-linked opportunities/risks; recommended actions; sources; and gaps/uncertainties. Make the distinction among `Fact`, `Assessment`, and `Hypothesis` visible. If the requested period contains no meaningful change, say so and report the strongest verified signals rather than padding the result.
