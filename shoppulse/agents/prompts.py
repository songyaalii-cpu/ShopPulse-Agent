"""Grounded prompts; numeric calculation remains in deterministic services."""


REQUEST_PARSER_PROMPT = """Parse the user's e-commerce analytics request into the supplied schema.
Choose only documented metrics, dimensions, and intents. Do not calculate values and do not invent filters.
Dates refer to business data dates, not the current wall-clock date."""

ANSWER_WRITER_PROMPT = """Write a concise operations analysis using only the supplied structured evidence.
Separate facts, analytical judgment, possible explanations, recommended actions, and limitations.
Never state correlation as proven causality and never expose customer PII."""
