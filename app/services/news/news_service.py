import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.config import settings


class NewsService:
    """Service for aggregating news about people and companies."""
    
    BASE_URL = "https://newsapi.org/v2"
    
    def __init__(self):
        self.api_key = settings.news_api_key
        if not self.api_key:
            print("⚠️  News API key not configured. News aggregation will be skipped.")
    
    async def get_news_for_person(self, name: str, company: Optional[str] = None, limit: int = 3) -> List[Dict[str, Any]]:
        """Get recent news articles about a person."""
        if not self.api_key:
            return []
            
        async with httpx.AsyncClient() as client:
            try:
                # Build search query
                query_parts = [name]
                if company:
                    query_parts.append(company)
                
                query = " AND ".join(query_parts)
                
                # Calculate date range (last 30 days)
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                response = await client.get(
                    f"{self.BASE_URL}/everything",
                    params={
                        "q": query,
                        "from": start_date.strftime("%Y-%m-%d"),
                        "to": end_date.strftime("%Y-%m-%d"),
                        "sortBy": "relevancy",
                        "language": "en",
                        "pageSize": limit,
                        "apiKey": self.api_key
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                articles = data.get("articles", [])
                
                # Format articles
                formatted_articles = []
                for article in articles:
                    formatted_articles.append({
                        "title": article.get("title"),
                        "description": article.get("description"),
                        "url": article.get("url"),
                        "published_at": article.get("publishedAt"),
                        "source": article.get("source", {}).get("name")
                    })
                
                return formatted_articles
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return []
            except Exception as e:
                print(f"Error getting news for person {name}: {e}")
                return []
    
    async def get_news_for_company(self, company_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get recent news articles about a company."""
        if not self.api_key:
            return []
            
        async with httpx.AsyncClient() as client:
            try:
                # Calculate date range (last 30 days)
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                response = await client.get(
                    f"{self.BASE_URL}/everything",
                    params={
                        "q": f'"{company_name}"',
                        "from": start_date.strftime("%Y-%m-%d"),
                        "to": end_date.strftime("%Y-%m-%d"),
                        "sortBy": "relevancy",
                        "language": "en",
                        "pageSize": limit,
                        "apiKey": self.api_key
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                articles = data.get("articles", [])
                
                # Format articles
                formatted_articles = []
                for article in articles:
                    formatted_articles.append({
                        "title": article.get("title"),
                        "description": article.get("description"),
                        "url": article.get("url"),
                        "published_at": article.get("publishedAt"),
                        "source": article.get("source", {}).get("name")
                    })
                
                return formatted_articles
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return []
            except Exception as e:
                print(f"Error getting news for company {company_name}: {e}")
                return []
    
    async def get_industry_news(self, industry_keywords: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent industry news based on keywords."""
        if not self.api_key:
            return []
            
        async with httpx.AsyncClient() as client:
            try:
                # Build query from keywords
                query = " OR ".join([f'"{keyword}"' for keyword in industry_keywords])
                
                # Calculate date range (last 7 days for industry news)
                end_date = datetime.now()
                start_date = end_date - timedelta(days=7)
                
                response = await client.get(
                    f"{self.BASE_URL}/everything",
                    params={
                        "q": query,
                        "from": start_date.strftime("%Y-%m-%d"),
                        "to": end_date.strftime("%Y-%m-%d"),
                        "sortBy": "relevancy",
                        "language": "en",
                        "pageSize": limit,
                        "apiKey": self.api_key
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                articles = data.get("articles", [])
                
                # Format articles
                formatted_articles = []
                for article in articles:
                    formatted_articles.append({
                        "title": article.get("title"),
                        "description": article.get("description"),
                        "url": article.get("url"),
                        "published_at": article.get("publishedAt"),
                        "source": article.get("source", {}).get("name")
                    })
                
                return formatted_articles
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error occurred: {e}")
                return []
            except Exception as e:
                print(f"Error getting industry news: {e}")
                return []
    
    async def enrich_attendee_with_news(self, attendee_info: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich attendee information with relevant news."""
        if not self.api_key:
            attendee_info["news_articles"] = []
            return attendee_info
            
        try:
            # Get news for the person
            person_news = await self.get_news_for_person(
                attendee_info["name"], 
                attendee_info.get("company"),
                limit=settings.max_news_articles_per_person
            )
            
            # Get news for their company
            company_news = []
            if attendee_info.get("company"):
                company_news = await self.get_news_for_company(
                    attendee_info["company"],
                    limit=settings.max_news_articles_per_person
                )
            
            # Combine and deduplicate news
            all_news = person_news + company_news
            unique_news = []
            seen_urls = set()
            
            for article in all_news:
                if article["url"] not in seen_urls:
                    unique_news.append(article)
                    seen_urls.add(article["url"])
            
            attendee_info["news_articles"] = unique_news[:settings.max_news_articles_per_person]
            
        except Exception as e:
            print(f"Error enriching attendee with news: {e}")
            attendee_info["news_articles"] = []
        
        return attendee_info 