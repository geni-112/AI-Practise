# ChatBI Semantic Query

## Purpose

Let a business user request a final result in ordinary language without requiring a predefined prompt or exposing unrestricted text-to-SQL execution.

## Safe Query Flow

1. Classify the message as `query`, `development`, or `clarification`.
2. Use deterministic parsing for known expressions and MaaS for unfamiliar phrasing when configured.
3. Ask MaaS for a structured query contract, never raw SQL.
4. Validate the contract against a versioned semantic catalog.
5. Compile allowlisted identifiers into parameterized, read-only SQL.
6. Execute only against a published Gold snapshot or governed serving view.
7. Return business results plus parser, catalog, filter, source, and run evidence.
8. Keep follow-up context as validated contracts rather than unrestricted conversation text.

## Query Contract

Use a structure similar to:

```json
{
  "intent": "query",
  "year": "2025",
  "region": "Yucatan",
  "regime": "",
  "resico": null,
  "group_by": "region",
  "metrics": ["annual_income_total"],
  "primary_metric": "annual_income_total",
  "limit": 10,
  "ascending": false,
  "confidence": 0.94,
  "clarification": ""
}
```

Accept only catalog identifiers. Canonicalize safe aliases before validation. Reject unknown dimensions, metrics, values, sort keys, and excessive limits.

## Semantic Catalog

Version and externalize the catalog. Include:

- approved dataset or serving view;
- dimensions, physical columns, labels, and allowed values;
- metrics, formulas, aggregations, units, and source columns;
- privacy policy and blocked fields;
- catalog version used for each answer.

Do not include direct identifiers as available analytical fields.

## MaaS Boundary

Send:

- the redacted current question;
- catalog identifiers and allowed values;
- privacy instructions;
- a small list of previously validated query contracts.

Do not send:

- raw taxpayer rows or direct identifiers;
- credentials, tokens, signed URLs, or unrestricted logs;
- previous free-form prompts that have not been redacted and validated;
- permission to create SQL or choose arbitrary tables.

Treat model output as untrusted. Validate it with a typed schema and catalog lookup before compilation.

## Safe Compiler

- Build identifiers only from catalog-owned strings.
- Put every user-derived value in a bound parameter.
- Permit `SELECT` only.
- Apply a bounded row limit.
- Reject comments, multiple statements, DDL, DML, and unknown functions.
- Record the compiled statement and parameter names as evidence without leaking sensitive values.

## Failure Semantics

Return a clarification when the question cannot be mapped safely. A model timeout, invalid JSON, unknown catalog value, or unavailable serving result should not become an empty spinner or raw HTTP error.

The response should say what information is needed, preserve the original question, and support retry. Record only a safe error type in public evidence.

## Current Demo Boundary

The minimal Agentic Tax Bigdata Demo evaluates queries over the latest published MRS Gold snapshot. The compiler output is query evidence until a governed DWS or MRS SQL gateway is explicitly enabled. Do not claim live SQL execution when the result came from a snapshot adapter.
