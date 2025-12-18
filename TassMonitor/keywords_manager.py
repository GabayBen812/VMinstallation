"""
Keywords Manager - Handles dynamic keyword storage and retrieval from Supabase.
"""
import os
from typing import List, Optional
from supabase import create_client, Client
from threading import Lock


class KeywordsManager:
    """Manages keywords stored in Supabase with in-memory caching."""
    
    def __init__(self):
        self._cache: Optional[List[str]] = None
        self._lock = Lock()
        self._supabase: Optional[Client] = None
        self._initialized = False
        
    def _get_supabase_client(self) -> Optional[Client]:
        """Initialize and return Supabase client."""
        if self._supabase is not None:
            return self._supabase
            
        supabase_url = os.getenv("SUPABASE_URL", "").strip()
        supabase_key = os.getenv("SUPABASE_KEY", "").strip()
        
        if not supabase_url or not supabase_key:
            return None
            
        try:
            self._supabase = create_client(supabase_url, supabase_key)
            return self._supabase
        except Exception as e:
            print(f"ERROR: Failed to initialize Supabase client: {e}")
            return None
    
    def _ensure_table_exists(self) -> bool:
        """Ensure the keywords table exists in Supabase."""
        client = self._get_supabase_client()
        if not client:
            return False
            
        try:
            # Try to read from the table to check if it exists
            # If it doesn't exist, we'll get an error and can create it
            result = client.table("alert_keywords").select("keywords").limit(1).execute()
            return True
        except Exception:
            # Table might not exist - this is expected on first run
            # The user needs to create the table manually in Supabase
            print("WARNING: alert_keywords table not found in Supabase.")
            print("Please create a table named 'alert_keywords' with columns:")
            print("  - id: integer (primary key, auto-increment)")
            print("  - keywords: text (JSON array of keywords)")
            print("  - updated_at: timestamp (default: now())")
            return False
    
    def load_keywords(self) -> List[str]:
        """
        Load keywords from Supabase, with caching.
        Falls back to default keywords if Supabase is not available.
        """
        with self._lock:
            # Return cached keywords if available
            if self._cache is not None:
                return self._cache
            
            client = self._get_supabase_client()
            if not client:
                # Fallback to default keywords if Supabase not configured
                return self._get_default_keywords()
            
            if not self._initialized:
                if not self._ensure_table_exists():
                    # Use default keywords if table doesn't exist
                    self._cache = self._get_default_keywords()
                    return self._cache
                self._initialized = True
            
            try:
                # Fetch the most recent keywords entry
                # Try with order by desc, fallback to simple select if that fails
                try:
                    result = client.table("alert_keywords").select("keywords").order("updated_at", desc=True).limit(1).execute()
                except Exception:
                    # Fallback: get all and sort in Python (less efficient but works)
                    result = client.table("alert_keywords").select("keywords,updated_at").execute()
                    if result.data and len(result.data) > 0:
                        # Sort by updated_at descending
                        sorted_data = sorted(result.data, key=lambda x: x.get("updated_at", ""), reverse=True)
                        result.data = [sorted_data[0]] if sorted_data else []
                
                if result.data and len(result.data) > 0:
                    keywords_json = result.data[0].get("keywords")
                    if keywords_json:
                        # Parse JSON array
                        import json
                        if isinstance(keywords_json, str):
                            keywords = json.loads(keywords_json)
                        else:
                            keywords = keywords_json
                        
                        if isinstance(keywords, list) and all(isinstance(k, str) for k in keywords):
                            self._cache = keywords
                            print(f"Loaded {len(keywords)} keywords from Supabase")
                            return self._cache
                
                # No keywords found in database, use defaults
                print("No keywords found in Supabase, using defaults")
                self._cache = self._get_default_keywords()
                return self._cache
                
            except Exception as e:
                print(f"ERROR: Failed to load keywords from Supabase: {e}")
                # Fallback to default keywords
                return self._get_default_keywords()
    
    def update_keywords(self, keywords: List[str]) -> bool:
        """
        Update keywords in Supabase and refresh cache.
        
        Args:
            keywords: List of keyword strings to save
            
        Returns:
            True if successful, False otherwise
        """
        client = self._get_supabase_client()
        if not client:
            print("ERROR: Supabase not configured, cannot update keywords")
            return False
        
        if not self._ensure_table_exists():
            print("ERROR: alert_keywords table does not exist")
            return False
        
        try:
            # Insert new row with updated keywords
            # Supabase JSONB columns can accept Python lists directly
            result = client.table("alert_keywords").insert({
                "keywords": keywords
            }).execute()
            
            if result.data:
                # Update cache
                with self._lock:
                    self._cache = keywords.copy()
                print(f"Successfully updated {len(keywords)} keywords in Supabase")
                return True
            else:
                print("ERROR: Failed to insert keywords into Supabase")
                return False
                
        except Exception as e:
            print(f"ERROR: Failed to update keywords in Supabase: {e}")
            return False
    
    def invalidate_cache(self):
        """Invalidate the cache to force reload on next access."""
        with self._lock:
            self._cache = None
    
    def _get_default_keywords(self) -> List[str]:
        """Return default keywords as fallback."""
        return [
            "strike", "strikes", "striking", "struck",
            "airstrike", "airstrikes", "air strike", "air strikes",
            "attack", "attacks", "attacked", "attacking",
            "casualties", "casualty", "killed", "killing", "deaths", "dead", "wounded", "injured", "injuries",
            "bombing", "bombed", "bomb", "bombs",
            "missile", "missiles", "rocket", "rockets",
            "raid", "raids", "raided",
            "shelling", "shelled", "shell",
            "targeted", "targeting", "target",
            "explosion", "explosions", "exploded", "explode",
            "martyr", "martyrs", "martyred",
            "gaza", "lebanon", "lebanese",
        ]


# Global instance
_keywords_manager = None


def get_keywords_manager() -> KeywordsManager:
    """Get the global KeywordsManager instance."""
    global _keywords_manager
    if _keywords_manager is None:
        _keywords_manager = KeywordsManager()
    return _keywords_manager

