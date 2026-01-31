
import asyncio
import httpx
import xml.etree.ElementTree as ET
import urllib.parse

async def test_arxiv():
    query = "Blockchain"
    encoded_query = urllib.parse.quote(query)
    
    # URL construction matches knowledge_base.py
    arxiv_url = (
        f"https://export.arxiv.org/api/query?"
        f"search_query=all:{encoded_query}&"
        f"start=0&max_results=100&"
        f"sortBy=relevance&sortOrder=descending"
    )
    
    print(f"Querying URL: {arxiv_url}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(arxiv_url, timeout=30.0)
            
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print("Error response text:", response.text[:500])
            return

        content = response.text
        print(f"Response Length: {len(content)} characters")
        print("First 500 chars of response:\n", content[:500])
        
        # Test Parsing
        root = ET.fromstring(content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entries = root.findall('atom:entry', ns)
        print(f"Entries Found: {len(entries)}")
        
        if entries:
            first = entries[0]
            title = first.find('atom:title', ns)
            print(f"First element title: {title.text if title is not None else 'None'}")
            
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(test_arxiv())
