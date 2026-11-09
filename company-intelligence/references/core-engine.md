# Core intelligence engine

## Evidence hierarchy

Prefer: regulatory filings and government records; investor relations, earnings transcripts, official releases and documentation; executive statements; reputable news and specialist research; credible partner/customer releases; aggregators and social posts only as discovery leads.

For high-impact claims, seek either one authoritative primary source or two independent credible sources. Preserve publication date, event date, geography, entity, URL, and a concise supporting excerpt or paraphrase.

## Atomic event schema

Capture: `event_id`, `event_date`, `published_date`, `entity`, `geography`, `primary_dimension`, `secondary_dimensions`, `fact`, `status`, `source`, `source_type`, `confidence`, `importance`, `related_events`, `assessment`, `affected_capability`, `stakeholder`, `opportunity_or_risk`, `validation_question`, and `next_action`.

Valid status values include announced, planned, piloting, contracted, launched, deployed, scaled, delayed, cancelled, and measured. Do not collapse them.

## Scoring

Score each dimension 1-5:

- Evidence: source authority, corroboration, and specificity.
- Recency: closeness to the requested window and event date.
- Strategic impact: likely effect on revenue, cost, risk, differentiation, customers, or operating model.
- Relevance: fit to the user's intent and audience.

Set confidence to high when the claim is direct and authoritative, medium when credible but incomplete, and low when indirect or speculative. Prioritize with `0.35 strategic impact + 0.25 relevance + 0.20 evidence + 0.20 recency`. Show qualitative priority rather than false numerical precision unless the user asks for scores.

## Event clustering and trends

Cluster events that express one strategic move. Avoid counting a launch, partner repost, regional repost, and executive interview as four independent moves. Compare with prior periods or management commitments before calling something a trend. Label a pattern as emerging, sustained, accelerating, decelerating, or contradicted, and state the supporting event count and time span.

## Analysis discipline

Use this chain:

1. Fact: what verifiably occurred.
2. Change: difference from the prior baseline or commitment.
3. Meaning: strategic or operational consequence.
4. Affected capability and stakeholder: business capability first; technology only when relevant.
5. Opportunity/risk: a specific hypothesis supported by the trigger.
6. Next action: owner or stakeholder, validation question, timing, and evidence needed.

Label facts, assessments, and hypotheses explicitly. Consider at least one alternative explanation for high-impact conclusions. Test opportunity hypotheses for need, urgency, ownership, feasibility, value, incumbent constraints, and disqualifying evidence.

## Search pattern

Combine company/entity aliases with the requested dates and pack categories. Include investor relations, annual/quarterly reports, earnings calls, leadership interviews, procurement/contract notices, partner releases, careers, architecture/engineering posts, and regulator sources as applicable. Search local-language terms for regional companies. Stop when priority topics have authoritative coverage and additional results repeat known events.
