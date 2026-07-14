# Import the function your AI agent just built
from services.embeddings import embed_documents

# Let's test it with two completely different short strings
test_strings = ["Patient prescribed Metformin for diabetes.", "Who won the football match?"]

print("Sending strings to Gemini...")
results = embed_documents(test_strings)

# 1. Did we get 2 vectors back?
print(f"Number of vectors returned: {len(results)} (Expected: 2)")

# 2. Is the first vector exactly 768 numbers long?
print(f"Length of first vector: {len(results[0])} (Expected: 768)")

# 3. Are the two vectors different from each other?
are_different = results[0] != results[1]
print(f"Are the two vectors different?: {are_different} (Expected: True)")