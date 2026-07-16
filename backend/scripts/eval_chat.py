# ── Drop this into backend/scripts/eval_chat.py for Prompt A2.4 ──

TEST_QUESTIONS = [
    # --- 4 ANSWERABLE MEDICAL QUESTIONS (Should score > 0.65) ---
    "What is my HbA1c level and when was it tested?",
    "What medications am I currently prescribed for diabetes?",
    "What is the exact dosage and frequency for my Metformin?",
    "Were there any flagged high values in my recent routine blood count?",

    # --- 4 ADVERSARIAL / OUT-OF-DOMAIN QUESTIONS (Should score < 0.65) ---
    "Who won the FIFA World Cup in 2022?",
    "What is the capital of France?",
    "Can you give me a recipe for chocolate chip cookies?",
    "What is the current stock price of Apple or Microsoft?"
]