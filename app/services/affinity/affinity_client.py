import httpx
from typing import List, Optional, Dict, Any
from app.core.config import settings
from app.schemas.brief import AttendeeInfo


class AffinityClient:
    """Client for interacting with Affinity API."""
    
    BASE_URL = "https://api.affinity.co/v2"
    
    def __init__(self):
        self.api_key = settings.affinity_api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def find_person_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find a person in Affinity by email address."""
        async with httpx.AsyncClient() as client:
            try:
                # Search for persons with the given email
                response = await client.get(
                    f"{self.BASE_URL}/persons",
                    headers=self.headers,
                    params={"email": email}
                )
                response.raise_for_status()
                
                data = response.json()
                persons = data.get("data", [])
                
                if persons:
                    return persons[0]  # Return the first match
                return None
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return None
            except Exception as e:
                print(f"Error finding person by email: {e}")
                return None
    
    async def get_person_details(self, person_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a person."""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/persons/{person_id}",
                    headers=self.headers
                )
                response.raise_for_status()
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return None
            except Exception as e:
                print(f"Error getting person details: {e}")
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
                    if "organizations" in person_details and person_details["organizations"]:
                        company_name = person_details["organizations"][0].get("name")
                    
                    # Extract LinkedIn URL
                    linkedin_url = None
                    if "social_profiles" in person_details:
                        for profile in person_details["social_profiles"]:
                            if profile.get("type") == "linkedin":
                                linkedin_url = profile.get("url")
                                break
                    
                    # Get recent notes for context
                    notes = await self.get_person_notes(person_data["id"], limit=3)
                    recent_context = []
                    for note in notes:
                        if note.get("body"):
                            recent_context.append(note["body"][:200] + "...")
                    
                    # Update attendee info
                    attendee.company = company_name
                    attendee.linkedin_url = linkedin_url
                    attendee.recent_emails = recent_context
                    
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