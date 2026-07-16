"""
Dev-only script: evaluate retrieval scores for a set of test questions.

Prints question, top-3 similarity scores, and the is_relevant gate decision
for each question — NO LLM calls.  Use the output to pick SIMILARITY_FLOOR
empirically by reading the gap between answerable and adversarial questions.

Usage (from the backend/ directory, venv active):

    python scripts/eval_chat.py --user-id 8c5cf54d-72f5-4a0d-adb4-d06a5fb4706b
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Put backend/ on sys.path so we can import services/ and utils/.
# Run this script from the backend/ directory so pydantic-settings finds .env.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import rag as rag_svc   # noqa: E402

# ── Test questions ────────────────────────────────────────────────────────────
# Answerable: should clear SIMILARITY_FLOOR and return is_relevant=True.
# Adversarial: should fall below the floor and return is_relevant=False.

TEST_QUESTIONS = [
    # --- 4 ANSWERABLE MEDICAL QUESTIONS (Should score > SIMILARITY_FLOOR) ---
    "What is my HbA1c level and when was it tested?",
    "What medications am I currently prescribed for diabetes?",
    "What is the exact dosage and frequency for my Metformin?",
    "Were there any flagged high values in my recent routine blood count?",

    # --- 4 ADVERSARIAL / OUT-OF-DOMAIN QUESTIONS (Should score < SIMILARITY_FLOOR) ---
    "Who won the FIFA World Cup in 2022?",
    "What is the capital of France?",
    "Can you give me a recipe for chocolate chip cookies?",
    "What is the current stock price of Apple or Microsoft?",
]


async def run_eval(user_id: str) -> None:
    print(f"\nEvaluating retrieval for user: {user_id}")
    print(f"SIMILARITY_FLOOR = {rag_svc.SIMILARITY_FLOOR}\n")
    print("=" * 72)

    for question in TEST_QUESTIONS:
        matches = await rag_svc.search_records(user_id, question, k=3)
        relevant = rag_svc.is_relevant(matches)

        gate = "PASS ✓" if relevant else "FAIL ✗"
        print(f"\nQ: {question}")
        print(f"   Gate: {gate}  (is_relevant={relevant})")

        if matches:
            for rank, m in enumerate(matches, 1):
                sim = float(m.get("similarity", 0.0))
                snippet = m.get("content", "")[:60].replace("\n", " ")
                print(f"   [{rank}] sim={sim:.4f}  …{snippet}…")
        else:
            print("   (no chunks returned)")

    print("\n" + "=" * 72)
    print("Done.  Adjust SIMILARITY_FLOOR in services/rag.py based on the gap")
    print("between your lowest answerable score and highest adversarial score.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate RAG retrieval scores without LLM calls.",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        metavar="PATIENT_UUID",
        help="Patient UUID whose record_chunks to search against.",
    )
    args = parser.parse_args()
    asyncio.run(run_eval(args.user_id))


if __name__ == "__main__":
    main()
