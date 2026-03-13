import httpx
import base64
from typing import List, Optional, Dict, Any
from app.core.config import settings
from app.schemas.brief import AttendeeInfo
from app.core.utils.retry import async_retry, should_retry_http_error
from app.core.utils.cache import RedisCache, make_key


class AffinityClient:
    """Client for interacting with Affinity API."""
    
    BASE_URL = "https://api.affinity.co/v2"
    V1_BASE_URL = "https://api.affinity.co"
    
    def __init__(self) -> None:
        self.api_key = settings.affinity_api_key
        # Affinity API v2 expects Bearer authentication
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # Cached metadata to minimize API usage
        self._person_fields_cache: Optional[Dict[str, Any]] = None
        self._linkedin_field_ids: Optional[set] = None
        # v1 Basic header (fallback)
        self._v1_basic_auth = {
            "Authorization": "Basic " + base64.b64encode(f"{self.api_key}:".encode()).decode(),
            "Content-Type": "application/json",
        }
    
    @async_retry((httpx.HTTPError, Exception), tries=3, base_delay=0.5, max_delay=2.0, should_retry=should_retry_http_error)
    async def find_person_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find a person in Affinity by email address."""
        cache_key = make_key("aff", "person", email.lower())
        cached = await RedisCache.get_json(cache_key)
        if cached:
            return cached
        async with httpx.AsyncClient() as client:
            try:
                # Search for persons with the given email
                # Search persons by term (email)
                response = await client.get(
                    f"{self.BASE_URL}/persons",
                    headers=self.headers,
                    params={"term": email}
                )
                response.raise_for_status()

                data = response.json()
                persons = data.get("data", [])

                # Filter to find exact email match (term search is fuzzy)
                email_lower = email.lower()
                for person in persons:
                    person_emails = [e.lower() for e in person.get("emailAddresses", [])]
                    if email_lower in person_emails:
                        await RedisCache.set_json(cache_key, person, ttl_seconds=60 * 60 * 24)
                        return person
                return None

            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return None
            except Exception as e:
                print(f"Error finding person by email: {e}")
                return None
    
    @async_retry((httpx.HTTPError, Exception), tries=3, base_delay=0.5, max_delay=2.0, should_retry=should_retry_http_error)
    async def get_person_details(self, person_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a person."""
        cache_key = make_key("aff", "person_details", str(person_id))
        cached = await RedisCache.get_json(cache_key)
        if cached:
            return cached
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/persons/{person_id}",
                    headers=self.headers
                )
                response.raise_for_status()
                
                payload = response.json()
                await RedisCache.set_json(cache_key, payload, ttl_seconds=60 * 60 * 24)
                return payload
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return None
            except Exception as e:
                print(f"Error getting person details: {e}")
                return None

    @async_retry((httpx.HTTPError, Exception), tries=3, base_delay=0.5, max_delay=2.0, should_retry=should_retry_http_error)
    async def get_person_list_entries(self, person_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list entries (rows) for a person; used to inspect enriched field values like LinkedIn URL."""
        cache_key = make_key("aff", "person_entries", str(person_id))
        cached = await RedisCache.get_json(cache_key)
        if cached:
            return cached
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/persons/{person_id}/list-entries",
                    headers=self.headers,
                    params={"limit": limit}
                )
                response.raise_for_status()
                data = response.json() or {}
                entries = data.get("data", [])
                await RedisCache.set_json(cache_key, entries, ttl_seconds=60 * 60 * 24)
                return entries
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return []
            except Exception as e:
                print(f"Error getting person list entries: {e}")
                return []

    @async_retry((httpx.HTTPError, Exception), tries=3, base_delay=0.5, max_delay=2.0, should_retry=should_retry_http_error)
    async def get_person_fields(self) -> Dict[str, Any]:
        """Fetch and cache person field metadata (v2)."""
        if self._person_fields_cache is not None:
            return self._person_fields_cache
        cache_key = make_key("aff", "person_fields")
        cached = await RedisCache.get_json(cache_key)
        if cached:
            self._person_fields_cache = cached
            return cached
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/persons/fields",
                    headers=self.headers,
                )
                response.raise_for_status()
                self._person_fields_cache = response.json() or {}
                await RedisCache.set_json(cache_key, self._person_fields_cache, ttl_seconds=60 * 60 * 24)
            except Exception as e:
                print(f"Error getting person fields: {e}")
                self._person_fields_cache = {}
        return self._person_fields_cache

    async def ensure_linkedin_field_ids(self) -> set:
        """Identify field ids whose name suggests LinkedIn URL (cached)."""
        if self._linkedin_field_ids is not None:
            return self._linkedin_field_ids
        self._linkedin_field_ids = set()
        meta = await self.get_person_fields()
        for fld in meta.get("data", []):
            name = (fld.get("name") or "").lower()
            if "linkedin" in name and "url" in name:
                fid = fld.get("id")
                if fid:
                    self._linkedin_field_ids.add(str(fid))
        return self._linkedin_field_ids

    def _extract_linkedin_from_fields(self, list_entries: List[Dict[str, Any]]) -> Optional[str]:
        """Search list entry fields for a LinkedIn URL in either a 'LinkedIn URL' field or any value containing linkedin.com."""
        for entry in list_entries:
            for field in entry.get("fields", []):
                name = (field.get("name") or "").strip().lower()
                value = field.get("value")
                # Direct 'LinkedIn URL' field
                if name in ("linkedin url", "linkedIn url".lower()):
                    # value might be a string or an object containing url
                    if isinstance(value, str) and "linkedin.com" in value:
                        return value
                    if isinstance(value, dict):
                        url = value.get("url") or value.get("data") or ""
                        if isinstance(url, str) and "linkedin.com" in url:
                            return url
                        if isinstance(url, dict):
                            # try common keys
                            for k in ("url", "href"):
                                v = url.get(k)
                                if isinstance(v, str) and "linkedin.com" in v:
                                    return v
                # Any enriched field containing a linkedin URL
                if isinstance(value, str) and "linkedin.com" in value:
                    return value
                if isinstance(value, dict):
                    # scan nested
                    stack = [value]
                    while stack:
                        node = stack.pop()
                        for v in (node.values() if isinstance(node, dict) else []):
                            if isinstance(v, str) and "linkedin.com" in v:
                                return v
                            if isinstance(v, dict):
                                stack.append(v)
        return None

    @staticmethod
    def _extract_list_stage(list_entries: List[Dict[str, Any]]) -> tuple:
        """Extract list name and pipeline stage from list entries.

        Returns (list_name, stage) — either may be None.
        Looks for fields named Stage, Status, Pipeline Stage, etc.
        """
        _STAGE_FIELD_NAMES = {
            "stage", "status", "pipeline stage", "deal stage",
            "pipeline status", "investment stage",
        }
        list_name = None
        stage = None
        for entry in list_entries:
            # List name
            entry_list_name = None
            list_obj = entry.get("list")
            if isinstance(list_obj, dict):
                entry_list_name = list_obj.get("name")
            elif isinstance(list_obj, str):
                entry_list_name = list_obj
            if not entry_list_name:
                entry_list_name = entry.get("list_name")

            # Look for stage/status field
            for field in entry.get("fields", []):
                fname = (field.get("name") or "").strip().lower()
                if fname in _STAGE_FIELD_NAMES:
                    val = field.get("value")
                    if isinstance(val, str) and val:
                        stage = val
                        list_name = entry_list_name
                        return (list_name, stage)
                    if isinstance(val, dict):
                        # Dropdown fields may be {text: "..."} or {name: "..."}
                        stage = val.get("text") or val.get("name") or val.get("value")
                        if stage:
                            list_name = entry_list_name
                            return (list_name, stage)

            # If we found a list name but no stage, still record it
            if entry_list_name and not list_name:
                list_name = entry_list_name

        return (list_name, stage)

    @async_retry((httpx.HTTPError, Exception), tries=2, base_delay=0.5, max_delay=1.5, should_retry=should_retry_http_error)
    async def get_person_v1(self, person_id: int) -> Optional[Dict[str, Any]]:
        """Fallback to Affinity v1 person endpoint to fetch social profiles if available."""
        cache_key = make_key("aff", "v1_person", str(person_id))
        cached = await RedisCache.get_json(cache_key)
        if cached:
            return cached
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.V1_BASE_URL}/v1/persons/{person_id}", headers=self._v1_basic_auth
                )
                resp.raise_for_status()
                payload = resp.json()
                await RedisCache.set_json(cache_key, payload, ttl_seconds=60 * 60 * 24)
                return payload
            except Exception as e:
                print(f"Error getting v1 person {person_id}: {e}")
                return None

    @async_retry((httpx.HTTPError, Exception), tries=2, base_delay=0.5, max_delay=1.5, should_retry=should_retry_http_error)
    async def find_person_v1_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Search for a person in v1 API by email. Returns the v1 person record with social profiles."""
        cache_key = make_key("aff", "v1_person_email", email.lower())
        cached = await RedisCache.get_json(cache_key)
        if cached:
            return cached
        async with httpx.AsyncClient() as client:
            try:
                # v1 search by term (email)
                resp = await client.get(
                    f"{self.V1_BASE_URL}/v1/persons",
                    headers=self._v1_basic_auth,
                    params={"term": email}
                )
                resp.raise_for_status()
                persons = resp.json()
                if persons and isinstance(persons, list) and len(persons) > 0:
                    # Get first match, then fetch full details for social profiles
                    v1_id = persons[0].get("id")
                    if v1_id:
                        full_person = await self.get_person_v1(v1_id)
                        if full_person:
                            await RedisCache.set_json(cache_key, full_person, ttl_seconds=60 * 60 * 24)
                            return full_person
                return None
            except Exception as e:
                print(f"Error finding v1 person by email {email}: {e}")
                return None

    def _extract_linkedin_from_v1(self, v1_person: Dict[str, Any]) -> Optional[str]:
        """Extract LinkedIn URL from v1 person record."""
        # Check direct linkedin_url field
        candidate = v1_person.get("linkedin_url")
        if isinstance(candidate, str) and "linkedin.com" in candidate:
            return candidate
        # Check social_profiles array
        for prof in (v1_person.get("social_profiles") or []):
            if prof.get("type") == "linkedin" and isinstance(prof.get("url"), str):
                return prof.get("url")
        return None
    
    async def get_person_notes(self, person_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent notes for a person."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/persons/{person_id}/notes",
                    headers=self.headers,
                    params={"limit": limit}
                )
                response.raise_for_status()
                
                data = response.json()
                return data.get("data", [])
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return []
            except Exception as e:
                print(f"Error getting person notes: {e}")
                return []
    
    async def get_person_list_entries(self, person_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get list entries for a person to understand their context."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/persons/{person_id}/list-entries",
                    headers=self.headers,
                    params={"limit": limit}
                )
                response.raise_for_status()
                
                data = response.json()
                return data.get("data", [])
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return []
            except Exception as e:
                print(f"Error getting person list entries: {e}")
                return []
    
    async def enrich_attendee_info(self, attendee: AttendeeInfo) -> AttendeeInfo:
        """Enrich attendee information with Affinity data."""
        try:
            # Find person by email
            person_data = await self.find_person_by_email(attendee.email)
            
            if person_data:
                # Get additional details
                person_details = await self.get_person_details(person_data["id"])
                
                if person_details:
                    # Extract company information
                    company_name = None
                    company_domain = None
                    website_url = None
                    job_title = None
                    if "organizations" in person_details and person_details["organizations"]:
                        org = person_details["organizations"][0]
                        company_name = org.get("name")
                        company_domain = (org.get("domain") or org.get("website_domain") or None)
                        website_url = org.get("website_url") or (f"https://{company_domain}" if company_domain else None)
                        job_title = org.get("title") or job_title
                    # Top-level title if present
                    job_title = job_title or person_details.get("title")
                    
                    # Extract LinkedIn URL
                    linkedin_url = None
                    # Try social_profiles if present
                    if "social_profiles" in person_details:
                        for profile in person_details["social_profiles"]:
                            if profile.get("type") == "linkedin":
                                linkedin_url = profile.get("url")
                                break
                    # If still missing, try enriched fields via list entries
                    if not linkedin_url:
                        # Ensure field ids are cached (one-time call)
                        await self.ensure_linkedin_field_ids()
                        entries = await self.get_person_list_entries(person_data["id"], limit=50)
                        linkedin_url = self._extract_linkedin_from_fields(entries)

                    # Extract Affinity list name + pipeline stage from entries
                    if not hasattr(self, '_entries_fetched'):
                        self._entries_fetched = False
                    if entries is None:
                        entries = await self.get_person_list_entries(person_data["id"], limit=50)
                    list_name, stage = self._extract_list_stage(entries)
                    if list_name:
                        attendee.affinity_list_name = list_name
                    if stage:
                        attendee.affinity_stage = stage

                    # Final fallback: search v1 API by email (v1/v2 IDs are different!)
                    if not linkedin_url:
                        v1_person = await self.find_person_v1_by_email(attendee.email)
                        if v1_person:
                            linkedin_url = self._extract_linkedin_from_v1(v1_person)
                    
                    # Get recent notes for context
                    notes = await self.get_person_notes(person_data["id"], limit=3)
                    recent_context = []
                    last_note_summary = None
                    last_note_date = None
                    materials: List[str] = []
                    for note in notes:
                        body = note.get("body") or ""
                        if body:
                            snippet = (body[:200] + "...") if len(body) > 200 else body
                            recent_context.append(snippet)
                            if last_note_summary is None:
                                last_note_summary = snippet
                                last_note_date = note.get("created_at") or note.get("updated_at")
                        # Extract simple URLs as materials
                        for token in body.split():
                            if token.startswith("http://") or token.startswith("https://"):
                                materials.append(token)
                    
                    # Fetch company details for description
                    company_description = None
                    if company_domain:
                        company_details = await self.get_company_by_domain(company_domain)
                        if company_details:
                            company_description = company_details.get("description")
                            # Also get website if we don't have it
                            if not website_url:
                                website_url = company_details.get("website_url") or company_details.get("domain")
                                if website_url and not website_url.startswith("http"):
                                    website_url = f"https://{website_url}"

                    # Update attendee info
                    attendee.company = company_name
                    attendee.company_domain = company_domain
                    attendee.website_url = website_url
                    attendee.company_description = company_description
                    attendee.linkedin_url = linkedin_url
                    if job_title:
                        attendee.title = job_title
                    attendee.recent_emails = recent_context
                    attendee.last_note_summary = last_note_summary
                    attendee.last_note_date = last_note_date
                    attendee.materials = materials[:3]
                    
        except Exception as e:
            print(f"Error enriching attendee info for {attendee.email}: {e}")
        
        return attendee
    
    async def get_company_info(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a company."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/companies",
                    headers=self.headers,
                    params={"name": company_name}
                )
                response.raise_for_status()

                data = response.json()
                companies = data.get("data", [])

                if companies:
                    return companies[0]
                return None

            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return None
            except Exception as e:
                print(f"Error getting company info: {e}")
                return None

    @async_retry((httpx.HTTPError, Exception), tries=2, base_delay=0.5, max_delay=1.5, should_retry=should_retry_http_error)
    async def get_company_details(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed company info by ID (v2 API)."""
        cache_key = make_key("aff", "company_details", str(company_id))
        cached = await RedisCache.get_json(cache_key)
        if cached:
            return cached
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/companies/{company_id}",
                    headers=self.headers
                )
                response.raise_for_status()
                payload = response.json()
                await RedisCache.set_json(cache_key, payload, ttl_seconds=60 * 60 * 48)
                return payload
            except Exception as e:
                print(f"Error getting company details {company_id}: {e}")
                return None

    @async_retry((httpx.HTTPError, Exception), tries=2, base_delay=0.5, max_delay=1.5, should_retry=should_retry_http_error)
    async def get_company_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """Search for a company by domain and return full details."""
        cache_key = make_key("aff", "company_domain", domain.lower())
        cached = await RedisCache.get_json(cache_key)
        if cached:
            return cached
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/companies",
                    headers=self.headers,
                    params={"term": domain}
                )
                response.raise_for_status()
                data = response.json()
                companies = data.get("data", [])
                if companies:
                    # Get the first match and fetch full details
                    company_id = companies[0].get("id")
                    if company_id:
                        details = await self.get_company_details(company_id)
                        if details:
                            await RedisCache.set_json(cache_key, details, ttl_seconds=60 * 60 * 48)
                            return details
                return None
            except Exception as e:
                print(f"Error finding company by domain {domain}: {e}")
                return None 