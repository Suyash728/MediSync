# A4.2 verification: steps 6-8
import json, sys, time, threading, datetime as dt, urllib.request, urllib.error
sys.path.insert(0, "/home/suyash/Projects/MediSync/backend")
from utils.config import settings
SB, SVC, ANON = settings.supabase_url, settings.supabase_service_key, settings.supabase_anon_key
BASE, DEMO_ID = "http://localhost:8000", "8c5cf54d-72f5-4a0d-adb4-d06a5fb4706b"

def sb_get(path):
    r = urllib.request.urlopen(urllib.request.Request(
        f"{SB}/rest/v1/{path}",
        headers={"apikey": SVC, "Authorization": f"Bearer {SVC}"}))
    return json.loads(r.read())

def sb_del(path):
    r = urllib.request.urlopen(urllib.request.Request(
        f"{SB}/rest/v1/{path}",
        headers={"apikey": SVC, "Authorization": f"Bearer {SVC}"},
        method="DELETE"))
    return r.status

def sb_patch(path, body):
    r = urllib.request.urlopen(urllib.request.Request(
        f"{SB}/rest/v1/{path}",
        data=json.dumps(body).encode(),
        headers={"apikey": SVC, "Authorization": f"Bearer {SVC}", "Content-Type": "application/json"},
        method="PATCH"))
    return r.status

def be_post(path, tok):
    req = urllib.request.Request(
        f"{BASE}{path}", data=b"{}",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="POST")
    try:
        r = urllib.request.urlopen(req)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

# Fresh auth
try:
    r = urllib.request.urlopen(urllib.request.Request(
        f"{SB}/auth/v1/token?grant_type=password",
        data=json.dumps({"email": "demo@medisync.app", "password": "Demo@2026"}).encode(),
        headers={"apikey": ANON, "Content-Type": "application/json"}))
    tok = json.loads(r.read())["access_token"]
    print(f"[auth] fresh token len={len(tok)}")
except Exception as ex:
    tok = open("/tmp/demo_token.txt").read().strip()
    print(f"[auth] fallback stored token ({ex})")

# ── STEP 6: zero-records ──────────────────────────────────────────────────────
print("\n=== STEP 6: zero-records ===")
n_before = len(sb_get(f"record_chunks?user_id=eq.{DEMO_ID}&select=record_id"))
print(f"chunks before: {n_before}")

sb_del(f"record_chunks?user_id=eq.{DEMO_ID}")
n_after = len(sb_get(f"record_chunks?user_id=eq.{DEMO_ID}&select=record_id"))
print(f"chunks after delete: {n_after}")

ts_before6 = sb_get(f"profiles?id=eq.{DEMO_ID}&select=suggestions_generated_at")[0]["suggestions_generated_at"]
print(f"generated_at before: {ts_before6}")
time.sleep(1)

code6, body6 = be_post("/suggestions/refresh", tok)
print(f"HTTP: {code6}")
print(f"suggestions: {json.dumps(body6.get('suggestions'))}")
print(f"generated_at: {body6.get('generated_at')}")

db6 = sb_get(f"profiles?id=eq.{DEMO_ID}&select=checkup_suggestions,suggestions_generated_at")[0]
print(f"DB checkup_suggestions: {json.dumps(db6['checkup_suggestions'])}")
print(f"DB generated_at:        {db6['suggestions_generated_at']}")

ok6 = (
    code6 == 200 and
    body6.get("suggestions") == [] and
    body6.get("generated_at") not in (None, ts_before6) and
    db6["suggestions_generated_at"] not in (None, ts_before6)
)
print(f"STEP 6: {'PASS' if ok6 else 'FAIL'}")

# ── STEP 7: concurrency ───────────────────────────────────────────────────────
print("\n=== STEP 7: concurrency ===")
results7 = []
def do_refresh():
    results7.append(be_post("/suggestions/refresh", tok))

threads = [threading.Thread(target=do_refresh) for _ in range(2)]
for t in threads: t.start()
for t in threads: t.join()

for i, (c, b) in enumerate(results7):
    print(f"call {i+1}: HTTP {c}, gen_at={b.get('generated_at')}, n_sug={len(b.get('suggestions', []))}")

db7 = sb_get(f"profiles?id=eq.{DEMO_ID}&select=checkup_suggestions,suggestions_generated_at")[0]
print(f"DB final gen_at={db7['suggestions_generated_at']}, n={len(db7.get('checkup_suggestions') or [])}")

ok7 = all(r[0] == 200 for r in results7) and db7.get("suggestions_generated_at") is not None
print(f"STEP 7: {'PASS' if ok7 else 'FAIL'}")

# ── STEP 8: restore ───────────────────────────────────────────────────────────
print("\n=== STEP 8: restore demo-ready state ===")
trial = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).isoformat()
sb_patch(f"profiles?id=eq.{DEMO_ID}", {"trial_ends_at": trial})
print(f"trial_ends_at restored: {trial}")
print("NOTE: chunks were deleted in step 6 — upload a document to restore RAG context and get real suggestions")

p = sb_get(f"profiles?id=eq.{DEMO_ID}&select=is_paid,trial_ends_at,checkup_suggestions,suggestions_generated_at")[0]
print(json.dumps(p, indent=2))
