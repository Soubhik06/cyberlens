import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { Send, ChevronDown, ChevronUp, Bot, User, Filter, AlertCircle } from "lucide-react";

export default function Chat({ cats, platforms, narrativeTypes, startYear, endYear }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState("Research Mode");

  // Filters State
  const [streamFilter, setStreamFilter] = useState("All Streams");
  const [catFilter, setCatFilter] = useState([]);
  const [platformFilter, setPlatformFilter] = useState([]);
  const [typeFilter, setTypeFilter] = useState([]);
  const [yearFilter, setYearFilter] = useState([startYear || 2013, endYear || 2026]);

  const messagesEndRef = useRef(null);

  // Scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Handle Ctrl+Enter submission
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && e.ctrlKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    const activeStream = streamFilter === "All Streams" ? null : (streamFilter.includes("Stream A") ? "A" : "B");

    try {
      // Map history to backend expected structure
      const historyPayload = messages.map(m => ({
        role: m.role,
        content: m.content
      }));

      // Prepare custom instructions based on mode
      const modeInst = {
        "Quick Answer": "Format: Quick Answer. Provide a concise response in maximum 2 to 3 sentences, straight to the point, with no elaboration.",
        "Research Mode": "Format: Research Mode. Provide a detailed structured analytical response with clear sections, citing specific patterns and evidence. The length must be strictly between 150 and 300 words.",
        "Deep Dive": "Format: Deep Dive. Provide a comprehensive long-form response with multiple angles, comparisons, and trends, suitable for academic writing. The length must be strictly under 500 words maximum."
      }[mode];

      const customQuestion = `${input}\n\n[INSTRUCTION]: Please reply strictly in accordance with this mode formatting rule: ${modeInst}\n[FILTERS APPLIED]: Stream: ${streamFilter}, Years: ${yearFilter[0]}-${yearFilter[1]}`;

      const response = await axios.post("/api/chat", {
        question: customQuestion,
        history: historyPayload
      });

      const { answer, sources } = response.data;

      // Simulate streaming (typing effect)
      const words = answer.split(" ");
      let currentWordIndex = 0;
      let streamedAnswer = "";

      const assistantMsgId = Date.now();
      setMessages((prev) => [
        ...prev,
        { id: assistantMsgId, role: "assistant", content: "", sources: sources, collapsed: true }
      ]);

      const interval = setInterval(() => {
        if (currentWordIndex < words.length) {
          streamedAnswer += (currentWordIndex === 0 ? "" : " ") + words[currentWordIndex];
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId ? { ...m, content: streamedAnswer } : m
            )
          );
          currentWordIndex++;
        } else {
          clearInterval(interval);
          setLoading(false);
        }
      }, 25);

    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "⚠️ Error querying RAG pipeline. Ensure the FastAPI backend is running.",
          sources: []
        }
      ]);
      setLoading(false);
    }
  };

  const toggleSourceCollapse = (msgIndex) => {
    setMessages((prev) =>
      prev.map((m, idx) => (idx === msgIndex ? { ...m, collapsed: !m.collapsed } : m))
    );
  };

  // Helper for filter selections
  const handleToggleFilter = (item, list, setList) => {
    if (list.includes(item)) {
      setList(list.filter((x) => x !== item));
    } else {
      setList([...list, item]);
    }
  };

  return (
    <div className="flex h-full bg-darkBg text-textMain">
      {/* Page Filters Sidebar */}
      <div className="w-80 border-r border-darkBorder bg-[#111622] p-4 flex flex-col gap-4 overflow-y-auto">
        <div className="flex items-center gap-2 font-bold text-sm text-[#58a6ff] uppercase tracking-wider border-b border-darkBorder pb-2">
          <Filter size={16} />
          <span>Research Filters</span>
        </div>

        {/* 1. Stream Selector */}
        <div>
          <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Data Stream</label>
          <select
            value={streamFilter}
            onChange={(e) => setStreamFilter(e.target.value)}
            className="w-full bg-[#161b22] border border-darkBorder rounded px-3 py-1.5 text-sm focus:outline-none focus:border-[#58a6ff]"
          >
            <option>All Streams</option>
            <option>Stream A (Narratives & News)</option>
            <option>Stream B (Official Statistics)</option>
          </select>
        </div>

        {/* 2. Year Range Slider */}
        <div>
          <label className="text-xs text-textMuted font-semibold uppercase block mb-1">
            Year Range: {yearFilter[0]} - {yearFilter[1]}
          </label>
          <input
            type="range"
            min={startYear || 2013}
            max={endYear || 2026}
            value={yearFilter[1]}
            onChange={(e) => setYearFilter([yearFilter[0], parseInt(e.target.value)])}
            className="w-full accent-[#58a6ff] bg-[#161b22] h-1.5 rounded-lg cursor-pointer"
          />
        </div>

        {/* 3. Fraud Category Select */}
        <div>
          <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Fraud Category</label>
          <div className="bg-[#161b22] border border-darkBorder rounded max-h-40 overflow-y-auto p-1.5 space-y-1">
            {cats.map((cat) => (
              <label key={cat} className="flex items-center gap-2 text-xs text-textMain cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={catFilter.includes(cat)}
                  onChange={() => handleToggleFilter(cat, catFilter, setCatFilter)}
                  className="rounded border-[#21262d] text-[#58a6ff] focus:ring-0"
                />
                <span className="truncate">{cat}</span>
              </label>
            ))}
          </div>
        </div>

        {/* 4. Source Platform Select */}
        <div>
          <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Source Platform</label>
          <div className="bg-[#161b22] border border-darkBorder rounded max-h-40 overflow-y-auto p-1.5 space-y-1">
            {platforms.map((plat) => (
              <label key={plat} className="flex items-center gap-2 text-xs text-textMain cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={platformFilter.includes(plat)}
                  onChange={() => handleToggleFilter(plat, platformFilter, setPlatformFilter)}
                  className="rounded border-[#21262d] text-[#58a6ff] focus:ring-0"
                />
                <span className="truncate">{plat}</span>
              </label>
            ))}
          </div>
        </div>

        {/* 5. Narrative Type Select */}
        <div>
          <label className="text-xs text-textMuted font-semibold uppercase block mb-1">Narrative/Data Type</label>
          <div className="bg-[#161b22] border border-darkBorder rounded max-h-40 overflow-y-auto p-1.5 space-y-1">
            {narrativeTypes.map((type) => (
              <label key={type} className="flex items-center gap-2 text-xs text-textMain cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={typeFilter.includes(type)}
                  onChange={() => handleToggleFilter(type, typeFilter, setTypeFilter)}
                  className="rounded border-[#21262d] text-[#58a6ff] focus:ring-0"
                />
                <span className="truncate">{type}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full bg-[#0b0f17]">
        {/* Chat Window */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto">
              <Bot className="text-[#58a6ff] mb-4 animate-pulse" size={48} />
              <h2 className="text-xl font-bold text-[#58a6ff]">India Cybercrime RAG System</h2>
              <p className="text-sm text-textMuted mt-2">
                Ask analytical research questions about UPI scams, digital arrests, investment fraud, or cyber policies in India. Sidebar filters will be automatically applied to the contextual lookup scope.
              </p>
            </div>
          ) : (
            messages.map((msg, index) => (
              <div
                key={index}
                className={`flex gap-4 p-4 rounded-lg border ${
                  msg.role === "user"
                    ? "bg-[#1f242c]/75 border-[#bc8cff]/20 ml-12"
                    : "bg-[#161b22]/75 border-[#58a6ff]/20 mr-12"
                }`}
              >
                <div className="shrink-0">
                  {msg.role === "user" ? (
                    <div className="w-8 h-8 rounded-full bg-[#bc8cff]/10 border border-[#bc8cff] flex items-center justify-center text-[#bc8cff]">
                      <User size={16} />
                    </div>
                  ) : (
                    <div className="w-8 h-8 rounded-full bg-[#58a6ff]/10 border border-[#58a6ff] flex items-center justify-center text-[#58a6ff]">
                      <Bot size={16} />
                    </div>
                  )}
                </div>

                <div className="flex-1 space-y-2">
                  <div className="font-semibold text-xs uppercase text-textMuted">
                    {msg.role === "user" ? "Researcher" : "Assistant Researcher"}
                  </div>
                  <div className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</div>

                  {/* Sources collapse drawer */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-darkBorder">
                      <button
                        onClick={() => toggleSourceCollapse(index)}
                        className="flex items-center gap-1.5 text-xs text-[#58a6ff] font-medium focus:outline-none"
                      >
                        {msg.collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                        <span>{msg.collapsed ? "Show Sources Cited" : "Hide Sources Cited"}</span>
                      </button>
                      
                      {!msg.collapsed && (
                        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                          {msg.sources.map((src, sIdx) => (
                            <div key={sIdx} className="bg-[#0f141c] border border-darkBorder rounded p-2 text-xs">
                              <span className="font-semibold text-[#58a6ff] block">
                                📄 [{src.doc_id}] {src.title || "Untitled Document"}
                              </span>
                              <span className="text-textMuted text-[10px]">
                                {src.source_platform || src.source_organisation || "Unknown Platform"} | {src.original_date || "Unknown Date"}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area fixed at bottom */}
        <div className="p-4 border-t border-[#21262d] bg-[#111622]">
          <div className="max-w-3xl mx-auto space-y-3">
            {/* Mode selection pills */}
            <div className="flex gap-2">
              {["Quick Answer", "Research Mode", "Deep Dive"].map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-3 py-1 rounded-full text-xs font-semibold border transition-all ${
                    mode === m
                      ? "bg-[#58a6ff] text-[#0b0f17] border-[#58a6ff]"
                      : "bg-[#161b22] text-[#8b949e] border-[#21262d] hover:text-[#c9d1d9]"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>

            {/* Main input container */}
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                placeholder="Ask a research question... (Ctrl+Enter to send)"
                className="flex-1 bg-[#161b22] border border-darkBorder rounded-lg px-4 py-2.5 text-sm resize-none focus:outline-none focus:border-[#58a6ff] text-textMain"
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="bg-[#58a6ff] text-[#0b0f17] hover:bg-[#58a6ff]/90 disabled:bg-[#161b22] disabled:text-[#8b949e] rounded-lg p-2.5 transition-colors focus:outline-none flex items-center justify-center shrink-0"
              >
                <Send size={18} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
