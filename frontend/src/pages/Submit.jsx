import React, { useState } from "react";
import axios from "axios";
import confetti from "canvas-confetti";
import { AlertCircle, CheckCircle, Shield, Sparkles, Send } from "lucide-react";

export default function Submit({ cats, refreshStats }) {
  const [name, setName] = useState("");
  const [incidentDate, setIncidentDate] = useState("");
  const [location, setLocation] = useState("");
  const [category, setCategory] = useState(cats[0] || "");
  const [description, setDescription] = useState("");
  const [amountLost, setAmountLost] = useState("");
  const [reported, setReported] = useState("no");
  const [additionalDetails, setAdditionalDetails] = useState("");

  const [validationError, setValidationError] = useState("");
  const [loading, setLoading] = useState(false);
  
  // Multi-step submission state
  const [step, setStep] = useState("input"); // "input", "confirm", "success"
  const [aiSuggestion, setAiSuggestion] = useState(null);
  const [assignedDocId, setAssignedDocId] = useState("");

  // Validate form and fetch AI suggestion
  const handleAnalyze = async (e) => {
    e.preventDefault();
    setValidationError("");
    
    if (!description || description.trim().length < 100) {
      setValidationError("❌ Description must be at least 100 characters long.");
      return;
    }
    if (!incidentDate) {
      setValidationError("❌ Please select a valid incident date.");
      return;
    }
    if (!location.trim()) {
      setValidationError("❌ Please specify where it happened.");
      return;
    }

    setLoading(true);
    try {
      // Build classification prompt for Gemini via /api/chat
      const classificationPrompt = `
      Analyze the following user-submitted cybercrime experience and suggest the most accurate category and subcategory from the lists of existing categories and subcategories in the system.
      
      VALID CATEGORIES:
      ${JSON.stringify(cats)}
      
      VALID SUBCATEGORIES:
      ["Cyber Scam", "Financial Cyber Fraud", "UPI Fraud", "QR Code Fraud", "Payment Link Fraud", "Mobile Wallet Fraud", "OTP Fraud", "SIM Swap", "KYC Fraud", "Digital Arrest", "Impersonation Scam", "Video Call Coercion", "Phishing", "Vishing", "Smishing", "Loan App Fraud", "Loan App Extortion", "Investment Scam", "Stock Market Fraud", "Task Scam", "Identity Theft", "Data Breach", "Social Engineering", "Romance Scam", "Sextortion", "E-Commerce Fraud", "Delivery Fraud", "Ransomware", "Banking Malware", "Deepfake Fraud", "Utility Scam", "Aadhaar Fraud", "Cyber Stalking", "Unknown", "General Cybercrime"]
      
      USER EXPERIENCE:
      "${description}"
      
      Return the suggestion strictly as a JSON object with the following fields:
      - category: string, must be exactly one of the valid categories.
      - subcategory: string, must be exactly one of the subcategories.
      - confidence: integer, confidence score between 0 and 100.
      
      Return ONLY the raw JSON object. Do not include markdown codeblocks or other formatting.
      `;

      const response = await axios.post("/api/chat", {
        question: classificationPrompt,
        history: []
      });

      const textResult = response.data.answer;
      
      // Parse JSON from LLM text output
      let parsedSuggestion = { category: category, subcategory: "Unknown", confidence: 50 };
      const match = textResult.match(/\{.*\}/s);
      if (match) {
        try {
          parsedSuggestion = JSON.parse(match[0]);
        } catch (je) {
          console.error("Failed to parse AI JSON:", je);
        }
      }
      
      setAiSuggestion(parsedSuggestion);
      setStep("confirm");
    } catch (err) {
      console.error(err);
      // Fallback in case LLM query fails
      setAiSuggestion({ category: category, subcategory: "Unknown", confidence: 50 });
      setStep("confirm");
    } finally {
      setLoading(false);
    }
  };

  // Process submission
  const handleFinalSubmit = async (useAiClassification) => {
    setLoading(true);
    
    const finalCategory = useAiClassification && aiSuggestion ? aiSuggestion.category : category;
    
    const payload = {
      name: name.trim() ? name.trim() : "Anonymous",
      incident_date: incidentDate,
      location: location.trim(),
      fraud_category: finalCategory,
      description: description.trim(),
      amount_lost: amountLost ? parseFloat(amountLost) : 0.0,
      reported_to_authorities: reported,
      additional_details: additionalDetails.trim()
    };

    try {
      const response = await axios.post("/api/submit", payload);
      if (response.data.status === "success") {
        setAssignedDocId(response.data.doc_id);
        setStep("success");
        
        // Trigger confetti
        confetti({
          particleCount: 150,
          spread: 80,
          origin: { y: 0.6 }
        });
        
        // Refresh live stats in parent App component
        refreshStats();
      }
    } catch (error) {
      console.error(error);
      setValidationError("❌ Failed to submit experience. Verify backend connection.");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setName("");
    setIncidentDate("");
    setLocation("");
    setCategory(cats[0] || "");
    setDescription("");
    setAmountLost("");
    setReported("no");
    setAdditionalDetails("");
    setStep("input");
  };

  return (
    <div className="p-6 bg-darkBg text-textMain flex justify-center items-start overflow-y-auto h-full">
      <div className="w-full max-w-2xl bg-[#161b22] border border-darkBorder rounded-xl p-6 shadow-xl">
        {step === "input" && (
          <>
            <div className="border-b border-darkBorder pb-4 mb-6">
              <h1 className="text-xl font-bold text-[#58a6ff] flex items-center gap-2">
                <Shield size={20} />
                <span>Submit Experience Narrative</span>
              </h1>
              <p className="text-xs text-textMuted mt-1">
                Enter details below. Submissions are processed, structured as text, and immediately ingested into ChromaDB.
              </p>
            </div>

            {validationError && (
              <div className="mb-4 bg-[#ff7b72]/10 border border-[#ff7b72]/20 text-[#ff7b72] rounded-lg p-3 text-xs flex items-center gap-2">
                <AlertCircle size={16} />
                <span>{validationError}</span>
              </div>
            )}

            <form onSubmit={handleAnalyze} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Your Name (Optional)</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Anonymous"
                    className="w-full bg-[#0b0f17] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
                  />
                </div>
                <div>
                  <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Date of Incident *</label>
                  <input
                    type="date"
                    required
                    value={incidentDate}
                    onChange={(e) => setIncidentDate(e.target.value)}
                    className="w-full bg-[#0b0f17] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Where it Happened (City/State) *</label>
                  <input
                    type="text"
                    required
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="e.g. Mumbai, Maharashtra"
                    className="w-full bg-[#0b0f17] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
                  />
                </div>
                <div>
                  <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Fraud Type *</label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full bg-[#0b0f17] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
                  >
                    {cats.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Amount Lost if any (INR)</label>
                  <input
                    type="number"
                    value={amountLost}
                    onChange={(e) => setAmountLost(e.target.value)}
                    placeholder="0.00"
                    className="w-full bg-[#0b0f17] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
                  />
                </div>
                <div>
                  <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Reported to Police or Cyber portal *</label>
                  <select
                    value={reported}
                    onChange={(e) => setReported(e.target.value)}
                    className="w-full bg-[#0b0f17] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
                  >
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                    <option value="partial">Partial</option>
                  </select>
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-xs text-textMuted font-semibold uppercase">Describe your experience in detail *</label>
                  <span className={`text-[10px] ${description.length >= 100 ? "text-[#7ee787]" : "text-[#ff7b72]"}`}>
                    {description.length} / 100 chars min
                  </span>
                </div>
                <textarea
                  required
                  rows={6}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe your experience in detail. Minimum 100 characters required..."
                  className="w-full bg-[#0b0f17] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
                />
              </div>

              <div>
                <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Any other details (Optional)</label>
                <textarea
                  rows={2}
                  value={additionalDetails}
                  onChange={(e) => setAdditionalDetails(e.target.value)}
                  placeholder="e.g. fake websites, suspect mobile numbers, payment links used..."
                  className="w-full bg-[#0b0f17] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-[#58a6ff] text-[#0b0f17] hover:bg-[#58a6ff]/90 disabled:bg-[#161b22] disabled:text-textMuted text-sm font-bold transition-all focus:outline-none"
              >
                <span>{loading ? "Analyzing Description..." : "Analyze Submission"}</span>
              </button>
            </form>
          </>
        )}

        {step === "confirm" && aiSuggestion && (
          <div className="space-y-6 text-center py-4">
            <Sparkles size={48} className="text-[#bc8cff] mx-auto animate-bounce" />
            <h2 className="text-xl font-bold text-textMain">AI Auto Categorization</h2>
            
            <div className="bg-[#0b0f17] border border-darkBorder rounded-xl p-5 text-left space-y-3 max-w-md mx-auto">
              <p className="text-sm text-textMuted leading-relaxed">
                Our AI model has analyzed your description and suggests the following categorization:
              </p>
              <div className="border-t border-darkBorder pt-3 space-y-1 text-xs">
                <div><b>Suggested Category:</b> <span className="text-[#58a6ff]">{aiSuggestion.category}</span></div>
                <div><b>Suggested Subcategory:</b> <span className="text-[#bc8cff]">{aiSuggestion.subcategory || "General"}</span></div>
                <div><b>AI Confidence Score:</b> <span className="text-[#7ee787] font-semibold">{aiSuggestion.confidence}%</span></div>
              </div>
            </div>

            <p className="text-sm text-textMuted max-w-sm mx-auto">
              Would you like to proceed with the AI classification or use your manually selected category ("{category}")?
            </p>

            <div className="flex flex-col gap-2 max-w-xs mx-auto">
              <button
                onClick={() => handleFinalSubmit(true)}
                disabled={loading}
                className="w-full py-2.5 rounded-lg bg-[#58a6ff] text-[#0b0f17] hover:bg-[#58a6ff]/90 text-sm font-bold transition-all focus:outline-none"
              >
                Use AI Classification & Submit
              </button>
              <button
                onClick={() => handleFinalSubmit(false)}
                disabled={loading}
                className="w-full py-2.5 rounded-lg bg-[#161b22] border border-darkBorder text-textMain hover:border-[#8b949e] text-sm font-bold transition-all focus:outline-none"
              >
                Use Manual Selection & Submit
              </button>
              <button
                onClick={() => setStep("input")}
                disabled={loading}
                className="w-full py-2 rounded-lg text-xs text-[#ff7b72] hover:underline transition-all focus:outline-none mt-2"
              >
                Cancel & Go Back
              </button>
            </div>
          </div>
        )}

        {step === "success" && (
          <div className="text-center py-8 space-y-6">
            <CheckCircle size={56} className="text-[#7ee787] mx-auto" />
            <div className="space-y-2">
              <h2 className="text-2xl font-extrabold text-[#7ee787]">Submission Successful!</h2>
              <p className="text-sm text-textMuted max-w-sm mx-auto">
                Your narrative has been cataloged and successfully ingested into the research index vector collection.
              </p>
            </div>

            <div className="bg-[#0b0f17] border border-[#7ee787]/20 rounded-xl p-5 max-w-xs mx-auto text-center">
              <span className="text-[10px] text-textMuted uppercase block">Assigned Document ID</span>
              <span className="text-2xl font-mono font-bold text-[#58a6ff] tracking-wider block mt-1">
                {assignedDocId}
              </span>
            </div>

            <p className="text-xs text-textMuted max-w-xs mx-auto">
              This experience is now active and immediately searchable in the **Research Chat** and explorer views.
            </p>

            <button
              onClick={handleReset}
              className="px-6 py-2.5 rounded-lg bg-[#161b22] border border-darkBorder hover:border-[#58a6ff] text-textMain text-sm font-bold transition-all focus:outline-none"
            >
              Submit Another Experience
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
