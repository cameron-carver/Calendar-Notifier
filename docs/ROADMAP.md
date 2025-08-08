# Roadmap / Follow-ups

- **Affinity LinkedIn URL enrichment robustness**
  - Current: Try v2 persons + list-entries (scan for "LinkedIn URL" or any value containing linkedin.com). If missing, fallback to a Google "linkedin" search link in the email.
  - Future fix: Also map v2 person to v1 person id via `/v1/persons?term=<email>` then call `/v1/persons/{id}` to read social profiles when available. This addresses v1/v2 id mismatches observed during testing.
  - Ensure API key has sufficient permissions (e.g., "Export data from Lists") for list-entry field access. See: https://developer.affinity.co/
  - Cache field metadata and resolved v1 ids to minimize API calls and avoid hitting rate limits.

- **Optional enhancements**
  - Add provider-based enrichment fallback (e.g., people/company data) when Affinity lacks social profiles.
  - Telemetry: log which enrichment source supplied a LinkedIn URL (v2 fields, v1 social profile, external, fallback).
