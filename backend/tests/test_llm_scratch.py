import sys
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# 1. Load your real environment variables first
load_dotenv("backend/.env")

# Allow imports from backend/ regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import your settings and the new async llm_client
from utils.config import settings
from services.llm_client import complete

async def run_resilience_test():
    print("\n────────────────────────────────────────────────────────")
    print(" 🧪 STARTING PROMPT A2.2 RESILIENCE TEST (Groq -> Gemini)")
    print("────────────────────────────────────────────────────────\n")

    # --- TEST 1: Primary Groq Call ---
    print("1️⃣  Testing PRIMARY provider (Groq)...")
    try:
        ans1, provider1 = await complete("Say the word 'Hello' and nothing else.", system="You are a concise assistant.")
        print(f"   ✅ Response: '{ans1.strip()}'")
        print(f"   🏷️  Provider returned: '{provider1}' (Expected: 'groq')")
        
        if provider1 != "groq":
            print("   ⚠️ WARNING: Did not return 'groq'. Check if your Groq API key is valid or already rate-limited!")
    except Exception as e:
        print(f"   ❌ Test 1 Failed with error: {e}")

    print("\n--------------------------------------------------------\n")

    # --- TEST 2: Sabotage Key & Test Gemini Fallback ---
    print("2️⃣  Sabotaging GROQ_API_KEY in memory to test fallback...")
    
    # Save the good key so we can restore it
    real_groq_key = settings.groq_api_key
    
    try:
        # Temporarily inject a fake key into Pydantic settings / os.environ
        settings.groq_api_key = "gsk_FAKE_INVALID_KEY_FOR_TESTING_FALLBACK"
        os.environ["GROQ_API_KEY"] = "gsk_FAKE_INVALID_KEY_FOR_TESTING_FALLBACK"
        
        print("   🔑 (Key is now broken. Calling complete() again...)")
        ans2, provider2 = await complete("Say the word 'Hello' and nothing else.", system="You are a concise assistant.")
        
        print(f"   ✅ Response: '{ans2.strip()}'")
        print(f"   🏷️  Provider returned: '{provider2}' (Expected: 'gemini')")
        
        if provider2 == "gemini":
            print("\n   🎉 SUCCESS: Groq failed as expected and successfully fell back to Gemini!")
        else:
            print(f"\n   ⚠️ WARNING: Expected 'gemini', but got '{provider2}'. Check your exception catching in llm_client.py!")
            
    except Exception as e:
        print(f"\n   ❌ Fallback Failed! Your llm_client.py threw an unhandled exception instead of falling back: {e}")
        
    finally:
        # --- TEST 3: Restore the Key ---
        print("\n3️⃣  Restoring real Groq API key...")
        settings.groq_api_key = real_groq_key
        if real_groq_key:
            os.environ["GROQ_API_KEY"] = real_groq_key
        print("   🔒 Key restored securely in memory.")

    print("\n────────────────────────────────────────────────────────")
    print(" 🏁 TEST COMPLETE")
    print("────────────────────────────────────────────────────────\n")

# Run the async loop
if __name__ == "__main__":
    asyncio.run(run_resilience_test())