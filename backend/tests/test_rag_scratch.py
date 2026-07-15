import sys
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# 1. FORCE LOAD THE .ENV FILE BEFORE IMPORTING APP MODULES
# This looks for .env in the backend/ folder from the project root
load_dotenv("backend/.env") 

# Allow imports from backend/ regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Now Pydantic will find the keys when these modules initialize!
from services.rag import search_records, is_relevant

# The demo user UUID we backfilled earlier
DEMO_UUID = "8c5cf54d-72f5-4a0d-adb4-d06a5fb4706b"

def test_query(label, query):
    print(f"\n--- Testing: '{query}' ({label}) ---")
    try:
        matches = asyncio.run(search_records(DEMO_UUID, query, k=3))
        print(f"Retrieved {len(matches)} chunk(s):")
        
        for idx, match in enumerate(matches, 1):
            rec_id = match.get("record_id")
            content = match.get("content", "")
            sim = float(match.get("similarity", 0.0))
            print(f"  [{idx}] Record ID: {rec_id} | Similarity: {sim:.4f}")
            print(f"      Snippet: {content[:80]}...")
            
        relevant = is_relevant(matches)
        print(f"Gate Decision (is_relevant): {relevant}")
        return relevant
    except Exception as e:
        print(f"Error running search: {e}")
        return None

# Test 1: Medical question (Should return high similarity & True)
res1 = test_query("Answerable Medical Query", "what is my HbA1c")

# Test 2: Adversarial / Unrelated question (Should return low similarity & False)
res2 = test_query("Adversarial Out-of-Domain Query", "what is the capital of France")

print("\n─────────────────────────────────────────")
if res1 is True and res2 is False:
    print("SUCCESS: Retrieval and deterministic refusal gate are working perfectly!")
else:
    print("WARNING: Check your SIMILARITY_FLOOR threshold or embedding connection.")
print("─────────────────────────────────────────")