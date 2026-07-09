import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import Plot from "react-plotly.js";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis,
  Tooltip, Legend, LineChart, Line, ResponsiveContainer
} from "recharts";
import {
  TrendingUp, PieChart as PieIcon, BarChart2,
  Cpu, Send, Loader2, Sparkles, MessageSquare
} from "lucide-react";

const COLORS = ["#58a6ff", "#bc8cff", "#ff7b72", "#7ee787", "#d2a8ff", "#ffa657"];

const SUGGESTIONS = [
  "How many UPI fraud cases happened each year?",
  "Show me the top fraud categories overall",
  "What are the overall cybercrime trends since 2013?",
  "Compare victim narratives vs government data",
  "How has phishing fraud evolved over time?",
  "Show investment and crypto fraud trends",
];

export default function Insights({ allDocs, stats }) {
  // ── Static chart state ───────────────────────────────────────────────────
  const [pieData, setPieData] = useState([]);
  const [barData, setBarData] = useState([]);
  const [lineData, setLineData] = useState([]);

  // ── Chat state ───────────────────────────────────────────────────────────
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // ── Build static charts from allDocs ─────────────────────────────────────
  useEffect(() => {
    if (!allDocs || allDocs.length === 0) return;

    // Pie: category distribution
    const catCounts = {};
    allDocs.forEach((d) => {
      const cat = d.fraud_category || "Unknown";
      catCounts[cat] = (catCounts[cat] || 0) + 1;
    });
    setPieData(
      Object.entries(catCounts)
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 6)
    );

    // Bar: stream comparison
    const catStream = {};
    allDocs.forEach((d) => {
      const cat = d.fraud_category || "Unknown";
      const s = d.stream === "A" ? "StreamA" : "StreamB";
      if (!catStream[cat]) catStream[cat] = { name: cat, StreamA: 0, StreamB: 0 };
      catStream[cat][s]++;
    });
    setBarData(
      Object.values(catStream)
        .sort((a, b) => (b.StreamA + b.StreamB) - (a.StreamA + a.StreamB))
        .slice(0, 6)
    );

    // Line: docs by year
    const yearCounts = {};
    const str = (v) => String(v);
    allDocs.forEach((d) => {
      let year = null;
      if (d.original_date) {
        const parts = str(d.original_date).split("-");
        const match = parts.find((p) => p.length === 4 && /^\d+$/.test(p));
        if (match) year = parseInt(match);
      }
      if (year && year >= 2013 && year <= 2026) {
        yearCounts[year] = (yearCounts[year] || 0) + 1;
      }
    });
    setLineData(
      Object.entries(yearCounts)
        .map(([year, count]) => ({ year: parseInt(year), count }))
        .sort((a, b) => a.year - b.year)
    );
  }, [allDocs]);

  // ── Auto-scroll chat to bottom ───────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Send message ─────────────────────────────────────────────────────────
  const sendMessage = async (question) => {
    const q = (question || inputValue).trim();
    if (!q) return;
    setInputValue("");
    setChatError("");

    const userMsg = { role: "user", text: q };
    setMessages((prev) => [...prev, userMsg]);
    setChatLoading(true);

    try {
      const res = await axios.post("/api/insights/chat", { question: q });
      const { answer, chart, chart_title } = res.data;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: answer, chart, chart_title }
      ]);
    } catch (err) {
      const detail = err.response?.data?.detail || "Request failed. Check backend.";
      setChatError(detail);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `⚠️ ${detail}`, chart: null, chart_title: "" }
      ]);
    } finally {
      setChatLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // ── Plotly config ─────────────────────────────────────────────────────────
  const plotConfig = {
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
    responsive: true,
  };

  return (
    <div className="h-full flex flex-col bg-[#0b0f17] text-[#c9d1d9] overflow-y-auto">
      <div className="p-6 space-y-6 flex-1">

        {/* ── Page Title ─────────────────────────────────────────────────── */}
        <div className="border-b border-[#21262d] pb-4">
          <h1 className="text-2xl font-bold text-[#58a6ff] flex items-center gap-2">
            <TrendingUp size={22} /> Indian Cybercrime Insight Engine
          </h1>
          <p className="text-sm text-[#8b949e] mt-1">
            Live statistics, dynamic charts, and an AI data assistant — powered by CyberLens registry data.
          </p>
        </div>

        {/* ── Metrics Row ────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "Total Documents", value: stats.total_document_count?.toLocaleString(), color: "#58a6ff" },
            { label: "Stream A — Narratives", value: stats.stream_breakdown?.["Stream A"]?.toLocaleString(), color: "#bc8cff" },
            { label: "Stream B — Govt Stats", value: stats.stream_breakdown?.["Stream B"]?.toLocaleString(), color: "#ff7b72" },
            { label: "Active Categories", value: stats.top_5_fraud_categories ? Object.keys(stats.top_5_fraud_categories).length : "–", color: "#7ee787" },
          ].map((m, i) => (
            <div key={i} className="bg-[#161b22] border border-[#21262d] rounded-xl p-4">
              <span className="text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider">{m.label}</span>
              <div className="text-3xl font-extrabold mt-1" style={{ color: m.color }}>{m.value || "0"}</div>
            </div>
          ))}
        </div>

        {/* ── Static Charts Grid ─────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Donut */}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5">
            <div className="flex items-center gap-2 text-sm font-semibold border-b border-[#21262d] pb-2 mb-4">
              <PieIcon size={15} className="text-[#58a6ff]" />
              <span>Top Fraud Categories (Overall)</span>
            </div>
            <div className="h-60">
              {pieData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData} cx="50%" cy="50%"
                      innerRadius={55} outerRadius={80}
                      paddingAngle={3} dataKey="value"
                    >
                      {pieData.map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ backgroundColor: "#111622", borderColor: "#21262d", color: "#c9d1d9" }} />
                    <Legend verticalAlign="bottom" height={36} iconSize={10} iconType="circle" wrapperStyle={{ fontSize: 10 }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-[#8b949e]">Loading chart…</div>
              )}
            </div>
          </div>

          {/* Grouped Bar: Stream A vs B */}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5">
            <div className="flex items-center gap-2 text-sm font-semibold border-b border-[#21262d] pb-2 mb-4">
              <BarChart2 size={15} className="text-[#bc8cff]" />
              <span>Narratives (A) vs. Official Records (B)</span>
            </div>
            <div className="h-60">
              {barData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barData}>
                    <XAxis dataKey="name" tick={{ fill: "#8b949e", fontSize: 8 }} hide />
                    <YAxis tick={{ fill: "#8b949e", fontSize: 9 }} />
                    <Tooltip contentStyle={{ backgroundColor: "#111622", borderColor: "#21262d", color: "#c9d1d9" }} />
                    <Legend verticalAlign="bottom" height={36} iconSize={10} wrapperStyle={{ fontSize: 10 }} />
                    <Bar dataKey="StreamA" name="Victim Narratives" fill="#bc8cff" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="StreamB" name="Official Stats" fill="#ff7b72" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-[#8b949e]">Loading chart…</div>
              )}
            </div>
          </div>

          {/* Timeline: full width */}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 lg:col-span-2">
            <div className="flex items-center gap-2 text-sm font-semibold border-b border-[#21262d] pb-2 mb-4">
              <TrendingUp size={15} className="text-[#7ee787]" />
              <span>Document Timeline — Cybercrime Registry (2013–2026)</span>
            </div>
            <div className="h-52">
              {lineData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={lineData}>
                    <XAxis dataKey="year" tick={{ fill: "#8b949e", fontSize: 10 }} />
                    <YAxis tick={{ fill: "#8b949e", fontSize: 9 }} />
                    <Tooltip contentStyle={{ backgroundColor: "#111622", borderColor: "#21262d", color: "#c9d1d9" }} />
                    <Line
                      type="monotone" dataKey="count" name="Docs Registered"
                      stroke="#7ee787" strokeWidth={2}
                      dot={{ r: 3, fill: "#7ee787" }}
                      activeDot={{ r: 5 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-[#8b949e]">Loading chart…</div>
              )}
            </div>
          </div>
        </div>

        {/* ── Data Intelligence Chatbot ───────────────────────────────────── */}
        <div className="bg-[#161b22] border border-[#21262d] rounded-xl overflow-hidden shadow-xl">
          {/* Header */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-[#21262d] bg-gradient-to-r from-[#58a6ff]/10 to-[#bc8cff]/10">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#58a6ff] to-[#bc8cff] flex items-center justify-center shadow-lg">
              <Sparkles size={16} className="text-white" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-[#c9d1d9]">Data Intelligence Chatbot</h2>
              <p className="text-[11px] text-[#8b949e]">
                Ask anything about the cybercrime dataset — get AI answers + dynamic charts
              </p>
            </div>
            <div className="ml-auto flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#7ee787] animate-pulse" />
              <span className="text-[10px] text-[#7ee787] font-semibold">LIVE</span>
            </div>
          </div>

          {/* Suggestion chips */}
          {messages.length === 0 && (
            <div className="px-5 pt-5 pb-2">
              <p className="text-[11px] font-semibold text-[#8b949e] uppercase tracking-wider mb-3 flex items-center gap-1.5">
                <MessageSquare size={11} /> Try asking…
              </p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(s)}
                    disabled={chatLoading}
                    className="text-[11px] bg-[#0d1117] border border-[#21262d] text-[#8b949e] hover:border-[#58a6ff] hover:text-[#58a6ff] rounded-full px-3 py-1.5 transition-all duration-200 disabled:opacity-40"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          <div className="px-5 py-4 space-y-6 min-h-[120px] max-h-[700px] overflow-y-auto">
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                {/* Avatar */}
                <div className={`w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center text-xs font-bold shadow ${
                  msg.role === "user"
                    ? "bg-gradient-to-br from-[#bc8cff] to-[#58a6ff] text-white"
                    : "bg-gradient-to-br from-[#58a6ff] to-[#7ee787] text-[#0b0f17]"
                }`}>
                  {msg.role === "user" ? "U" : "AI"}
                </div>

                <div className={`flex-1 max-w-[85%] space-y-3 ${msg.role === "user" ? "items-end flex flex-col" : ""}`}>
                  {/* Text bubble */}
                  <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow ${
                    msg.role === "user"
                      ? "bg-gradient-to-br from-[#58a6ff]/20 to-[#bc8cff]/20 border border-[#58a6ff]/30 text-[#c9d1d9] rounded-tr-sm"
                      : "bg-[#0d1117] border border-[#21262d] text-[#c9d1d9] rounded-tl-sm"
                  }`}>
                    {msg.text}
                  </div>

                  {/* Plotly chart (only for assistant messages) */}
                  {msg.role === "assistant" && msg.chart && (
                    <div className="w-full bg-[#0b0f17] border border-[#21262d] rounded-xl overflow-hidden shadow-lg">
                      {msg.chart_title && (
                        <div className="px-4 pt-3 pb-1 text-[11px] font-semibold text-[#58a6ff] uppercase tracking-wider border-b border-[#21262d]">
                          {msg.chart_title}
                        </div>
                      )}
                      <div className="w-full">
                        <Plot
                          data={msg.chart.data}
                          layout={{
                            ...msg.chart.layout,
                            autosize: true,
                            width: undefined,
                            height: 340,
                          }}
                          config={plotConfig}
                          style={{ width: "100%", height: "340px" }}
                          useResizeHandler
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Loading bubble */}
            {chatLoading && (
              <div className="flex gap-3 items-start">
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[#58a6ff] to-[#7ee787] flex items-center justify-center text-[#0b0f17] text-xs font-bold shadow flex-shrink-0">
                  AI
                </div>
                <div className="bg-[#0d1117] border border-[#21262d] rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin text-[#58a6ff]" />
                  <span className="text-xs text-[#8b949e]">Analysing dataset and building chart…</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input bar */}
          <div className="px-5 pb-5 pt-3 border-t border-[#21262d] bg-[#0d1117]/50">
            {chatError && (
              <div className="mb-2 text-[11px] text-[#ff7b72] bg-[#ff7b72]/10 border border-[#ff7b72]/20 rounded px-3 py-1.5">
                ⚠️ {chatError}
              </div>
            )}
            <div className="flex items-center gap-3">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={chatLoading}
                placeholder="e.g. How many UPI fraud cases happened per year? or Show top fraud categories…"
                className="flex-1 bg-[#0d1117] border border-[#21262d] focus:border-[#58a6ff] rounded-xl px-4 py-2.5 text-sm text-white placeholder-[#4a5568] outline-none transition-colors disabled:opacity-50"
              />
              <button
                onClick={() => sendMessage()}
                disabled={chatLoading || !inputValue.trim()}
                className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#58a6ff] to-[#bc8cff] flex items-center justify-center shadow-lg hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
              >
                {chatLoading ? (
                  <Loader2 size={16} className="animate-spin text-white" />
                ) : (
                  <Send size={16} className="text-white" />
                )}
              </button>
            </div>
            <p className="text-[10px] text-[#4a5568] mt-2 text-center">
              Powered by CyberLens Registry · Data grounded in Stream A &amp; B · Press Enter to send
            </p>
          </div>
        </div>

      </div>
    </div>
  );
}
