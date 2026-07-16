import { ChatResponse } from "./types";

/**
 * Mock Chat API provider for the MediSync AI Assistant.
 *
 * Implements a simulated response delay and matches input queries to return:
 *   1. A successful clinical summary with source cards for record queries (e.g. medications).
 *   2. A clean refusal response (refused: true) with no sources for items not in records (e.g. cholesterol).
 *   3. A friendly general greeting for generic prompts.
 */

export const mockChatApi = {
  async send(
    message: string,
    conversationId: string | null,
    authToken?: string
  ): Promise<ChatResponse> {
    // Simulate network latency (1000ms delay)
    await new Promise((resolve) => setTimeout(resolve, 1000));

    const query = message.toLowerCase().trim();

    // 1. Refusal case 1: Cholesterol
    if (
      query.includes("cholesterol") ||
      query.includes("lipid") ||
      query.includes("ldl") ||
      query.includes("hdl")
    ) {
      return {
        answer:
          "I couldn't find any cholesterol or lipid panel results in your uploaded health records. Please upload an official lab report containing your lipid profile to view these details.",
        refused: true,
        sources: [],
        provider: "gemini",
      };
    }

    // 2. Refusal case 2: COVID-19
    if (query.includes("covid") || query.includes("corona") || query.includes("vaccine")) {
      return {
        answer:
          "There are no references to COVID-19 diagnoses, treatments, or vaccinations in your active health ledger. If you have certificates or discharge papers regarding COVID-19, you can upload them via the dashboard.",
        refused: true,
        sources: [],
        provider: "groq",
      };
    }

    // 3. Info case: Medications
    if (
      query.includes("medication") ||
      query.includes("medicine") ||
      query.includes("meds") ||
      query.includes("drug") ||
      query.includes("prescribe")
    ) {
      return {
        answer:
          "Based on your uploaded medical records, you have active prescriptions for the following medications:\n\n1. **Metformin 500mg** — Taken twice daily for glycemic control (Prescribed by Dr. Priya Mehta at Apollo Hospitals).\n2. **Atorvastatin 20mg** — Taken once daily at bedtime for lipid regulation.\n3. **Lisinopril 10mg** — Taken once daily in the morning for blood pressure management.\n\nPlease note a minor interaction alert has been noted between Lisinopril and your diet (ensure low potassium substitutes).",
        refused: false,
        sources: [
          {
            record_id: "d3b07384-d113-495c-9cdb-1a733e8a4a51",
            snippet:
              "Apollo Hospital Prescription: Metformin 500mg tab BID after meals. Lisinopril 10mg tab QD. Patient instructed to follow up in 3 months.",
          },
          {
            record_id: "a9f600db-a1e4-4a4f-9e7f-b52f6df4dfca",
            snippet:
              "Discharge Summary: Patient discharged on home meds including Atorvastatin 20mg daily HS, resume Lisinopril. Monitor BP weekly.",
          },
        ],
        provider: "groq",
      };
    }

    // 4. Info case: Timeline / Reports
    if (query.includes("report") || query.includes("timeline") || query.includes("recent")) {
      return {
        answer:
          "Your health timeline contains 2 processed medical documents:\n\n* **Apollo CBC Report (Lab Report)** from 2026-07-10: Showing normal red blood cell count, mild vitamin B12 deficiency (320 pg/mL).\n* **Discharge Summary** from 2026-07-02: Following an elective arthroscopy, recovery uneventful.",
        refused: false,
        sources: [
          {
            record_id: "d3b07384-d113-495c-9cdb-1a733e8a4a51",
            snippet:
              "Lab Report: Vitamin B12 level is 320 pg/mL (Reference range: 200 - 900 pg/mL). RBC count 4.5 million/uL.",
          },
        ],
        provider: "gemini",
      };
    }

    // 5. Default welcoming response
    return {
      answer:
        "Hello! I am your MediSync AI Assistant. I can scan your uploaded prescriptions, lab reports, and medical records to:\n\n* List your active medications and dosages\n* Recall lab results (e.g. blood counts, vitals)\n* Identify record facilities, dates, and doctors\n\nWhat health question can I help you answer today?",
      refused: false,
      sources: [],
      provider: "groq",
    };
  },
};
