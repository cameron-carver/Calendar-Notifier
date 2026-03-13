"""Web enrichment service — uses OpenAI with web search to look up attendees
not found in Affinity, to summarise company websites by domain, and to fetch
curated AI/tech news."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional, List, Dict, Any

from openai import OpenAI

from app.core.config import settings
from app.core.utils.cache import RedisCache, make_key
from app.schemas.brief import AttendeeInfo


# Fields we consider "enriched enough" — if any are present, skip person web lookup
_ENRICHMENT_FIELDS = ("company", "title", "linkedin_url")


def _needs_enrichment(att: AttendeeInfo) -> bool:
    """Return True when Affinity left the attendee basically empty."""
    return not any(getattr(att, f, None) for f in _ENRICHMENT_FIELDS)


class WebEnrichmentService:
    """Look up attendees via OpenAI Responses API + web_search_preview."""

    CACHE_TTL = 60 * 60 * 48       # 48 hours for successful lookups
    CACHE_TTL_EMPTY = 60 * 60 * 6  # 6 hours for empty results (retry sooner)

    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.enabled: bool = bool(settings.openai_api_key) and getattr(
            settings, "enable_web_enrichment", True
        )

    async def enrich_attendee(self, attendee: AttendeeInfo) -> AttendeeInfo:
        """Enrich an attendee only if Affinity left them empty.

        Returns the same object (mutated in-place) for pipeline consistency.
        """
        if not self.enabled or not _needs_enrichment(attendee):
            return attendee

        # Check cache first
        cache_key = make_key("web", "person", attendee.email.lower())
        cached = await RedisCache.get_json(cache_key)
        if cached is not None:
            self._apply(attendee, cached)
            return attendee

        # Build a targeted prompt
        result = self._lookup(attendee)
        if result:
            # Check if any useful data was found
            has_data = any(
                v and isinstance(v, str) and v.lower() != "null"
                for v in result.values()
            )
            ttl = self.CACHE_TTL if has_data else self.CACHE_TTL_EMPTY
            await RedisCache.set_json(cache_key, result, ttl_seconds=ttl)
            self._apply(attendee, result)

        return attendee

    async def enrich_company_description(self, attendee: AttendeeInfo) -> AttendeeInfo:
        """Fill in company_description by looking up the company's website/domain.

        Runs independently of person-level enrichment.  Fires when we have a
        domain (from email or prior enrichment) but no company_description yet.
        """
        if not self.enabled:
            return attendee
        if getattr(attendee, "company_description", None):
            return attendee  # already have one

        # Derive domain to search
        domain = getattr(attendee, "company_domain", None)
        if not domain and attendee.email and "@" in attendee.email:
            domain = attendee.email.split("@")[1].lower()
        if not domain:
            return attendee

        # Skip generic email providers — no company site to look up
        _GENERIC_DOMAINS = {
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "icloud.com", "aol.com", "protonmail.com", "live.com",
            "me.com", "msn.com", "mail.com", "ymail.com",
        }
        if domain.lower() in _GENERIC_DOMAINS:
            return attendee
        # Also skip .edu — not a company
        if domain.lower().endswith(".edu"):
            return attendee

        # Check cache
        cache_key = make_key("web", "company", domain.lower())
        cached = await RedisCache.get_json(cache_key)
        if cached is not None:
            desc = cached.get("description")
            if desc and isinstance(desc, str) and desc.lower() != "null":
                attendee.company_description = desc
            return attendee

        # Look up the company
        result = self._lookup_company(domain, getattr(attendee, "company", None))
        if result:
            # Clean citation artifacts before caching
            raw_desc = result.get("description")
            if raw_desc and isinstance(raw_desc, str) and raw_desc.lower() != "null":
                result["description"] = self._clean_description(raw_desc)
            has_data = bool(
                result.get("description")
                and isinstance(result["description"], str)
                and result["description"].lower() != "null"
            )
            ttl = self.CACHE_TTL if has_data else self.CACHE_TTL_EMPTY
            await RedisCache.set_json(cache_key, result, ttl_seconds=ttl)
            desc = result.get("description")
            if desc and isinstance(desc, str) and desc.lower() != "null":
                attendee.company_description = desc
        else:
            # Cache the miss
            await RedisCache.set_json(
                cache_key, {"description": None}, ttl_seconds=self.CACHE_TTL_EMPTY
            )

        return attendee

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_description(text: str) -> str:
        """Strip markdown citation links and source annotations from descriptions."""
        # Remove markdown links: [text](url) → text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove bare parenthetical URLs: (https://...)
        text = re.sub(r'\s*\(https?://[^)]+\)', '', text)
        # Remove trailing source refs like "Source: ..."
        text = re.sub(r'\s*Source:\s*\S+\s*$', '', text, flags=re.IGNORECASE)
        return text.strip()

    def _lookup_company(self, domain: str, company_name: Optional[str] = None) -> Optional[dict]:
        """Look up a company by its domain/website and return a short description."""
        name_hint = f" (company may be called {company_name})" if company_name else ""
        query = (
            f"Visit or look up the website {domain}{name_hint} and return ONLY a JSON object "
            f"(no markdown, no explanation):\n\n"
            f'{{"description": "2-3 sentence summary of what this company does, '
            f'their product/service, and what stage or industry they are in"}}\n\n'
            f"Focus on what the company builds or sells. Be specific and concise."
        )

        try:
            resp = self.client.responses.create(
                model="gpt-4o-mini",
                tools=[{"type": "web_search_preview", "search_context_size": "low"}],
                input=query,
                max_output_tokens=250,
            )
            raw = (resp.output_text or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            raw_text = (resp.output_text or "") if "resp" in dir() else ""
            try:
                start = raw_text.index("{")
                end = raw_text.rindex("}") + 1
                data = json.loads(raw_text[start:end])
                if isinstance(data, dict):
                    return data
            except (ValueError, json.JSONDecodeError):
                pass
            print(f"[WebEnrich] Company JSON parse failed for {domain}: {raw_text[:200]}")
        except Exception as e:
            print(f"[WebEnrich] Error looking up company {domain}: {e}")
        return None

    def _lookup(self, att: AttendeeInfo) -> Optional[dict]:
        """Call OpenAI Responses API with web search to look up the person."""
        name = att.name or ""
        email = att.email or ""
        domain = email.split("@")[1] if "@" in email else ""

        query = (
            f"Search LinkedIn for \"{name}\" at the company with domain {domain}. "
            f"Find their LinkedIn profile and read their CURRENT job title.\n\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Company domain: {domain}\n\n"
            f"Return ONLY a JSON object (no markdown, no explanation) with this exact structure. "
            f"Use null for any field you cannot determine:\n"
            f'{{"title": "their CURRENT job title from LinkedIn", "company": "company name", '
            f'"company_domain": "company website domain like example.com", '
            f'"linkedin_url": "full linkedin profile URL", '
            f'"company_description": "one sentence about what the company does"}}'
        )

        try:
            resp = self.client.responses.create(
                model="gpt-4o-mini",
                tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
                input=query,
                max_output_tokens=300,
            )
            raw = (resp.output_text or "").strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            # Try to extract JSON from mixed text
            raw_text = (resp.output_text or "") if "resp" in dir() else ""
            try:
                start = raw_text.index("{")
                end = raw_text.rindex("}") + 1
                data = json.loads(raw_text[start:end])
                if isinstance(data, dict):
                    return data
            except (ValueError, json.JSONDecodeError):
                pass
            print(f"[WebEnrich] JSON parse failed for {att.email}: {raw_text[:200]}")
        except Exception as e:
            print(f"[WebEnrich] Error looking up {att.email}: {e}")
        return None

    @classmethod
    def _apply(cls, att: AttendeeInfo, data: dict) -> None:
        """Apply web-lookup results to the attendee, only filling empty fields."""
        for field in ("title", "company", "company_domain", "linkedin_url",
                      "company_description"):
            val = data.get(field)
            if val and isinstance(val, str) and val.lower() != "null":
                # Only fill if the field is currently empty
                if not getattr(att, field, None):
                    # Clean citation artifacts from descriptions
                    if field == "company_description":
                        val = cls._clean_description(val)
                    setattr(att, field, val)
        # Derive website_url from company_domain if missing
        if not att.website_url and att.company_domain:
            domain = att.company_domain
            if not domain.startswith("http"):
                domain = f"https://{domain}"
            att.website_url = domain

    # ------------------------------------------------------------------
    # AI / tech news
    # ------------------------------------------------------------------

    async def fetch_ai_news(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch cutting-edge AI news using OpenAI web search.

        Targets Hacker News, AI-focused publications, and research blogs.
        Returns a list of article dicts with: title, url, source, summary,
        relevance_tag.

        Cached per day (6-hour TTL) to avoid redundant API calls.
        """
        if not self.enabled:
            return []

        # Check cache first
        today_str = date.today().isoformat()
        cache_key = make_key("web", "ai_news", today_str)
        cached = await RedisCache.get_json(cache_key)
        if cached is not None:
            return cached

        query = (
            f"Search Hacker News, AI-focused tech publications (TechCrunch AI, "
            f"The Information, Ars Technica, VentureBeat AI), and research blogs "
            f"for the most interesting AI innovations and deployments from the "
            f"past 2-3 days.\n\n"
            f"Focus on:\n"
            f"- New ways AI is being applied in production (real deployments, not demos)\n"
            f"- Technical breakthroughs and novel architectures\n"
            f"- New AI tooling, frameworks, and infrastructure\n"
            f"- Fast-moving companies deploying AI in creative or unexpected ways\n"
            f"- Open source AI releases and milestones\n\n"
            f"NOT interested in: funding rounds, acquisitions, executive hires, "
            f"general business news, or opinion pieces.\n\n"
            f"Return ONLY a JSON array of {limit} articles. Each article must have:\n"
            f'{{"title": "headline", "url": "article URL", "source": "publication name", '
            f'"summary": "1-2 sentence summary of why this matters", '
            f'"relevance_tag": "deployment|research|tooling|infrastructure|open-source"}}\n\n'
            f"Return ONLY valid JSON array, no markdown, no explanation."
        )

        try:
            resp = self.client.responses.create(
                model="gpt-4o-mini",
                tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
                input=query,
                max_output_tokens=800,
            )

            raw = (resp.output_text or "").strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()

            articles = json.loads(raw)

            if isinstance(articles, list):
                # Clean and validate
                cleaned = []
                for a in articles[:limit]:
                    if isinstance(a, dict) and a.get("title"):
                        cleaned.append({
                            "title": self._clean_description(a.get("title", "")),
                            "url": a.get("url"),
                            "source": a.get("source"),
                            "summary": self._clean_description(a.get("summary", "")),
                            "relevance_tag": a.get("relevance_tag"),
                        })
                # Cache for 6 hours
                await RedisCache.set_json(cache_key, cleaned, ttl_seconds=60 * 60 * 6)
                return cleaned

        except json.JSONDecodeError:
            raw_text = (resp.output_text or "") if "resp" in dir() else ""
            # Try to extract JSON array from mixed text
            try:
                start = raw_text.index("[")
                end = raw_text.rindex("]") + 1
                articles = json.loads(raw_text[start:end])
                if isinstance(articles, list):
                    cleaned = []
                    for a in articles[:limit]:
                        if isinstance(a, dict) and a.get("title"):
                            cleaned.append({
                                "title": self._clean_description(a.get("title", "")),
                                "url": a.get("url"),
                                "source": a.get("source"),
                                "summary": self._clean_description(a.get("summary", "")),
                                "relevance_tag": a.get("relevance_tag"),
                            })
                    await RedisCache.set_json(cache_key, cleaned, ttl_seconds=60 * 60 * 6)
                    return cleaned
            except (ValueError, json.JSONDecodeError):
                pass
            print(f"[WebEnrich] AI news JSON parse failed: {raw_text[:200]}")
        except Exception as e:
            print(f"[WebEnrich] Error fetching AI news: {e}")

        return []
