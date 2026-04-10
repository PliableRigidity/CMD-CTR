import re
from html import unescape

def clean_text(text: str) -> str:
    if not text:
        return ""
        
    # Unescape HTML entities (&nbsp;, &quot;, etc.)
    text = unescape(text)
    
    # Remove HTML tags entirely
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text
