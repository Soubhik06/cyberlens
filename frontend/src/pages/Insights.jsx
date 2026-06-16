import React, { useState, useEffect } from "react";
import axios from "axios";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, LineChart, Line, ResponsiveContainer } from "recharts";
import { TrendingUp, PieChart as PieIcon, BarChart2, ShieldAlert, Cpu } from "lucide-react";

const COLORS = ["#58a6ff", "#bc8cff", "#ff7b72", "#7ee787", "#d2a8ff", "#ff9b72"];

export default function Insights({ allDocs, stats }) {
  const [loadingCategoryAnalysis, setLoadingCategoryAnalysis] = useState(false);
  const [categoryAnalysisText, setCategoryAnalysisText] = useState("");
  
  const [loadingStreamAnalysis, setLoadingStreamAnalysis] = useState(false);
  const [streamAnalysisText, setStreamAnalysisText] = useState("");
  
  const [loadingTimelineAnalysis, setLoadingTimelineAnalysis] = useState(false);
  const [timelineAnalysisText, setTimelineAnalysisText] = useState("");

  // Chart Data preparation from client side aggregations
  const [pieData, setPieData] = useState([]);
  const [barData, setBarData] = useState([]);
  const [lineData, setLineData] = useState([]);

  useEffect(() => {
    if (!allDocs || allDocs.length === 0) return;

    // 1. Pie Data: Category distribution
    const catCounts = {};
    allDocs.forEach((d) => {
      const cat = d.fraud_category || "Unknown";
      catCounts[cat] = (catCounts[cat] || 0) + 1;
    });
    const formattedPie = Object.entries(catCounts)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 6);
    setPieData(formattedPie);

    // 2. Bar Data: Stream A vs B comparison by category
    const catStreamCounts = {};
    allDocs.forEach((d) => {
      const cat = d.fraud_category || "Unknown";
      const stream = d.stream === "A" ? "StreamA" : "StreamB";
      if (!catStreamCounts[cat]) {
        catStreamCounts[cat] = { name: cat, StreamA: 0, StreamB: 0 };
      }
      catStreamCounts[cat][stream]++;
    });
    const formattedBar = Object.values(catStreamCounts)
      .sort((a, b) => (b.StreamA + b.StreamB) - (a.StreamA + a.StreamB))
      .slice(0, 6);
    setBarData(formattedBar);

    // 3. Line Data: Document distribution by year
    const yearCounts = {};
    const extractYear = (dateStr) => {
      if (!dateStr) return null;
      const match = str(dateStr).match(/\b(20\d{2}|19\d{2})\b/);
      return match ? parseInt(match[0]) : null;
    };
    const str = (v) => String(v);

    allDocs.forEach((d) => {
      let year = null;
      if (d.original_date) {
        const parts = str(d.original_date).split("-");
        // Look for 4 digit year
        const match = parts.find(p => p.length === 4 && /^\d+$/.test(p));
        if (match) year = parseInt(match);
      }
      if (year && year >= 2013 && year <= 2026) {
        yearCounts[year] = (yearCounts[year] || 0) + 1;
      }
    });

    const formattedLine = Object.entries(yearCounts)
      .map(([year, count]) => ({ year: parseInt(year), count }))
      .sort((a, b) => a.year - b.year);
    setLineData(formattedLine);

  }, [allDocs]);

  // Generate AI Analysis Functions
  const generateAnalysis = async (type, question, setLoading, setText) => {
    setLoading(true);
    setText("");
    try {
      const response = await axios.post("/api/chat", {
        question: question + "\n\n[INSTRUCTION]: Provide a concise, professional, scholarly paragraph summarising these findings. Keep it strictly under 150 words.",
        history: []
      });
      
      const { answer } = response.data;
      
      // Typing animation
      const words = answer.split(" ");
      let currentWordIndex = 0;
      let streamedAnswer = "";
      
      const interval = setInterval(() => {
        if (currentWordIndex < words.length) {
          streamedAnswer += (currentWordIndex === 0 ? "" : " ") + words[currentWordIndex];
          setText(streamedAnswer);
          currentWordIndex++;
        } else {
          clearInterval(interval);
          setLoading(false);
        }
      }, 25);
      
    } catch (error) {
      console.error(error);
      setText("⚠️ AI generation failed. Verify backend connectivity.");
      setLoading(false);
    }
  };

  return (
    <div className="p-6 bg-darkBg text-textMain space-y-6 overflow-y-auto h-full">
      {/* Page Title */}
      <div className="border-b border-darkBorder pb-4">
        <h1 className="text-2xl font-bold text-[#58a6ff]">Indian Cybercrime Insight Engine</h1>
        <p className="text-sm text-textMuted mt-1">
          Automated charts, metrics overview, and dynamic AI research interpretations.
        </p>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-[#161b22] border border-darkBorder rounded-lg p-4 flex flex-col justify-center">
          <span className="text-xs text-textMuted uppercase font-semibold">Total Documents</span>
          <span className="text-3xl font-extrabold text-[#58a6ff] mt-1">
            {stats.total_document_count?.toLocaleString() || "0"}
          </span>
        </div>
        <div className="bg-[#161b22] border border-darkBorder rounded-lg p-4 flex flex-col justify-center">
          <span className="text-xs text-textMuted uppercase font-semibold">Stream A (Narratives & News)</span>
          <span className="text-3xl font-extrabold text-[#bc8cff] mt-1">
            {stats.stream_breakdown?.["Stream A"]?.toLocaleString() || "0"}
          </span>
        </div>
        <div className="bg-[#161b22] border border-darkBorder rounded-lg p-4 flex flex-col justify-center">
          <span className="text-xs text-textMuted uppercase font-semibold">Stream B (Govt Statistics)</span>
          <span className="text-3xl font-extrabold text-[#ff7b72] mt-1">
            {stats.stream_breakdown?.["Stream B"]?.toLocaleString() || "0"}
          </span>
        </div>
        <div className="bg-[#161b22] border border-darkBorder rounded-lg p-4 flex flex-col justify-center">
          <span className="text-xs text-textMuted uppercase font-semibold">Active Categories</span>
          <span className="text-3xl font-extrabold text-[#7ee787] mt-1">
            {stats.top_5_fraud_categories ? Object.keys(stats.top_5_fraud_categories).length : "0"}
          </span>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Donut Chart: Top categories */}
        <div className="bg-[#161b22] border border-darkBorder rounded-xl p-5 flex flex-col">
          <div className="flex items-center gap-2 text-sm font-semibold border-b border-darkBorder pb-2 mb-4">
            <PieIcon size={16} className="text-[#58a6ff]" />
            <span>Top Fraud Categories (Overall)</span>
          </div>
          <div className="h-64">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: "#111622", borderColor: "#21262d", color: "#c9d1d9" }}
                  />
                  <Legend verticalAlign="bottom" height={36} iconSize={10} iconType="circle" wrapperStyle={{ fontSize: 10 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-textMuted">No chart data.</div>
            )}
          </div>

          <div className="mt-4 pt-4 border-t border-darkBorder space-y-3">
            <button
              onClick={() =>
                generateAnalysis(
                  "category",
                  `Analyze the distribution of cybercrime fraud categories in India based on our registry records: ${JSON.stringify(
                    pieData
                  )}`,
                  setLoadingCategoryAnalysis,
                  setCategoryAnalysisText
                )
              }
              disabled={loadingCategoryAnalysis || pieData.length === 0}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-[#58a6ff]/10 hover:bg-[#58a6ff]/20 text-[#58a6ff] text-xs font-semibold border border-[#58a6ff]/20 transition-all focus:outline-none"
            >
              <Cpu size={14} />
              <span>{loadingCategoryAnalysis ? "Analyzing Findings..." : "Generate AI Analysis"}</span>
            </button>
            
            {categoryAnalysisText && (
              <div className="bg-[#0b0f17] border border-darkBorder rounded-lg p-3 text-xs leading-relaxed text-textMain">
                {categoryAnalysisText}
              </div>
            )}
          </div>
        </div>

        {/* Bar Chart: Stream Comparison */}
        <div className="bg-[#161b22] border border-darkBorder rounded-xl p-5 flex flex-col">
          <div className="flex items-center gap-2 text-sm font-semibold border-b border-darkBorder pb-2 mb-4">
            <BarChart2 size={16} className="text-[#bc8cff]" />
            <span>Victim Narratives (Stream A) vs. Govt Records (Stream B)</span>
          </div>
          <div className="h-64">
            {barData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData}>
                  <XAxis dataKey="name" tick={{ fill: "#8b949e", fontSize: 8 }} hide />
                  <YAxis tick={{ fill: "#8b949e", fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#111622", borderColor: "#21262d", color: "#c9d1d9" }}
                  />
                  <Legend verticalAlign="bottom" height={36} iconSize={10} wrapperStyle={{ fontSize: 10 }} />
                  <Bar dataKey="StreamA" name="Victim Narratives" fill="#bc8cff" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="StreamB" name="Official Statistics" fill="#ff7b72" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-textMuted">No chart data.</div>
            )}
          </div>

          <div className="mt-4 pt-4 border-t border-darkBorder space-y-3">
            <button
              onClick={() =>
                generateAnalysis(
                  "stream",
                  `Compare the victim-reported categories against official government database aggregates. Data: ${JSON.stringify(
                    barData
                  )}`,
                  setLoadingStreamAnalysis,
                  setStreamAnalysisText
                )
              }
              disabled={loadingStreamAnalysis || barData.length === 0}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-[#bc8cff]/10 hover:bg-[#bc8cff]/20 text-[#bc8cff] text-xs font-semibold border border-[#bc8cff]/20 transition-all focus:outline-none"
            >
              <Cpu size={14} />
              <span>{loadingStreamAnalysis ? "Analyzing Divergence..." : "Generate AI Analysis"}</span>
            </button>
            
            {streamAnalysisText && (
              <div className="bg-[#0b0f17] border border-darkBorder rounded-lg p-3 text-xs leading-relaxed text-textMain">
                {streamAnalysisText}
              </div>
            )}
          </div>
        </div>

        {/* Line Chart: Documents Timeline */}
        <div className="bg-[#161b22] border border-darkBorder rounded-xl p-5 flex flex-col lg:col-span-2">
          <div className="flex items-center gap-2 text-sm font-semibold border-b border-darkBorder pb-2 mb-4">
            <TrendingUp size={16} className="text-[#7ee787]" />
            <span>Timeline of Cybercrime Documentation (2013 - 2026)</span>
          </div>
          <div className="h-64">
            {lineData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={lineData}>
                  <XAxis dataKey="year" tick={{ fill: "#8b949e", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#8b949e", fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#111622", borderColor: "#21262d", color: "#c9d1d9" }}
                  />
                  <Legend verticalAlign="bottom" height={36} iconSize={10} wrapperStyle={{ fontSize: 10 }} />
                  <Line type="monotone" dataKey="count" name="Document Registrations" stroke="#7ee787" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-textMuted">No chart data.</div>
            )}
          </div>

          <div className="mt-4 pt-4 border-t border-darkBorder space-y-3">
            <button
              onClick={() =>
                generateAnalysis(
                  "timeline",
                  `Analyze the long-term trends and spikes in cybercrime reports documented over the years. Data: ${JSON.stringify(
                    lineData
                  )}`,
                  setLoadingTimelineAnalysis,
                  setTimelineAnalysisText
                )
              }
              disabled={loadingTimelineAnalysis || lineData.length === 0}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-[#7ee787]/10 hover:bg-[#7ee787]/20 text-[#7ee787] text-xs font-semibold border border-[#7ee787]/20 transition-all focus:outline-none"
            >
              <Cpu size={14} />
              <span>{loadingTimelineAnalysis ? "Analyzing Growth..." : "Generate AI Analysis"}</span>
            </button>
            
            {timelineAnalysisText && (
              <div className="bg-[#0b0f17] border border-darkBorder rounded-lg p-3 text-xs leading-relaxed text-textMain">
                {timelineAnalysisText}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
