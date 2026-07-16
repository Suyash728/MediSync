import asyncio
import httpx
from dotenv import load_dotenv

# Force load variables
load_dotenv("backend/.env")

# The URL where your uvicorn server is running
BASE_URL = "http://localhost:8000"

# If your endpoint enforces Bearer auth, put a valid Supabase JWT token here.
# If you bypass auth during dev or override it, leave this as "test-token"
FAKE_OR_REAL_TOKEN = "your_supabase_jwt_token_here"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {FAKE_OR_REAL_TOKEN}"
}

async def run_endpoint_tests():
    print("\n────────────────────────────────────────────────────────")
    print(" 🧪 STARTING PROMPT A2.3 ENDPOINT TEST (/api/chat)")
    print("────────────────────────────────────────────────────────\n")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        
        # --- TEST 1: Grounded Medical Question ---
        print("1️⃣  Testing Grounded Medical Query: 'what medications am I on?'...")
        payload1 = {"message": "what medications am I on?", "conversation_id": null if False else None}
        
        try:
            resp1 = await client.post("/api/chat", json=payload1, headers=headers)
            print(f"   📈 Status Code: {resp1.status_code}")
            
            if resp1.status_code == 200:
                data1 = resp1.json()
                print(f"   💬 Answer   : {data1.get('answer')[:100]}...")
                print(f"   🛑 Refused  : {data1.get('refused')} (Expected: False)")
                print(f"   📚 Sources  : {len(data1.get('sources', []))} found (Expected: > 0)")
                print(f"   🏷️  Provider : {data1.get('provider')}")
            else:
                print(f"   ❌ Request failed: {resp1.text}")
        except Exception as e:
            print(f"   ❌ Connection error (is Uvicorn running?): {e}")

        print("\n--------------------------------------------------------\n")

        # --- TEST 2: Adversarial Out-of-Domain Question ---
        print("2️⃣  Testing Adversarial Query: 'who won the world cup'...")
        payload2 = {"message": "who won the world cup", "conversation_id": None}
        
        try:
            resp2 = await client.post("/api/chat", json=payload2, headers=headers)
            print(f"   📈 Status Code: {resp2.status_code}")
            
            if resp2.status_code == 200:
                data2 = resp2.json()
                print(f"   💬 Answer   : {data2.get('answer')}")
                print(f"   🛑 Refused  : {data2.get('refused')} (Expected: True)")
                print(f"   📚 Sources  : {len(data2.get('sources', []))} found (Expected: 0)")
                print(f"   🏷️  Provider : {data2.get('provider')}")
                
                if data2.get("refused") is True and len(data2.get("sources", [])) == 0:
                    print("\n   🎉 SUCCESS: Zero-cost refusal gate blocked the question over HTTP!")
            else:
                print(f"   ❌ Request failed: {resp2.text}")
        except Exception as e:
            print(f"   ❌ Connection error: {e}")

    print("\n────────────────────────────────────────────────────────")
    print(" 🏁 TEST COMPLETE")
    print("────────────────────────────────────────────────────────\n")

if __name__ == "__main__":
    asyncio.run(run_endpoint_tests())