import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { 
  Beaker, Play, CheckCircle, AlertCircle, Loader2, Copy, 
  Download, RefreshCw, ChevronDown, ChevronUp, Layers, BookOpen, Network
} from "lucide-react";

export default function GioiaAnalysis({ cats }) {
  const [question, setQuestion] = useState("");
  const [category, setCategory] = useState("");
  const [runId, setRunId] = useState(null);
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [checkpoints, setCheckpoints] = useState([]);
  const [error, setError] = useState(null);
  
  const [queryQuestion, setQueryQuestion] = useState("");
  const [queryAnswer, setQueryAnswer] = useState("");
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryWorkflow, setQueryWorkflow] = useState(null);
  const [queryError, setQueryError] = useState(null);
  const [expandedThemes, setExpandedThemes] = useState({});
  const toggleThemeExpand = (themeName) => {
    setExpandedThemes(prev => ({ ...prev, [themeName]: !prev[themeName] }));
  };

  const formatTime = (seconds) => {
    if (seconds === undefined || seconds === null || isNaN(seconds)) return "estimating...";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m === 0) return `${s}s`;
    return `${m}m ${s}s`;
  };

  const [expandedPanels, setExpandedPanels] = useState({
    structure: true,
    themes: false,
    dimensions: false,
    findings: true,
    query: true
  });
  
  const pollInterval = useRef(null);

  // Fetch checkpoints
  const fetchCheckpoints = async () => {
    try {
      const res = await axios.get("/api/gioia/checkpoints");
      setCheckpoints(res.data);
    } catch (err) {
      console.error("Failed to fetch checkpoints:", err);
    }
  };

  useEffect(() => {
    fetchCheckpoints();
    return () => {
      if (pollInterval.current) clearInterval(pollInterval.current);
    };
  }, []);

  // Poll status
  const startPolling = (id) => {
    setRunId(id);
    setError(null);
    if (pollInterval.current) clearInterval(pollInterval.current);
    
    pollInterval.current = setInterval(async () => {
      try {
        const res = await axios.get(`/api/gioia/status/${id}`);
        setStatus(res.data);
        
        if (res.data.status === "complete") {
          clearInterval(pollInterval.current);
          fetchResults(id);
          fetchCheckpoints();
        } else if (res.data.status === "failed") {
          clearInterval(pollInterval.current);
          setError(res.data.error || "Analysis failed at a pipeline stage.");
          fetchCheckpoints();
        }
      } catch (err) {
        console.error("Polling error:", err);
        clearInterval(pollInterval.current);
        setError("Failed to fetch status updates.");
      }
    }, 3000);
  };

  // Run new analysis
  const handleRun = async () => {
    if (!question.trim()) {
      alert("Please enter a research question.");
      return;
    }
    setResults(null);
    setStatus(null);
    try {
      const res = await axios.post("/api/gioia/run", {
        research_question: question,
        fraud_category: category || null
      });
      if (res.data.status === "success") {
        startPolling(res.data.run_id);
      }
    } catch (err) {
      console.error(err);
      alert("Failed to start analysis run.");
    }
  };

  // Resume run
  const handleResume = async (id, stageNum) => {
    try {
      const res = await axios.post(`/api/gioia/resume/${id}/${stageNum}`);
      if (res.data.status === "success") {
        startPolling(id);
      }
    } catch (err) {
      console.error(err);
      alert("Failed to resume analysis stage.");
    }
  };

  // Load results
  const fetchResults = async (id) => {
    try {
      const res = await axios.get(`/api/gioia/results/${id}`);
      setResults(res.data);
      setStatus(res.data.metadata);
    } catch (err) {
      console.error(err);
      setError("Failed to load completed analysis results.");
    }
  };

  // Select a historical run
  const handleSelectRun = (chk) => {
    if (pollInterval.current) clearInterval(pollInterval.current);
    setError(null);
    setRunId(chk.run_id);
    
    if (chk.status === "complete") {
      fetchResults(chk.run_id);
    } else {
      setResults(null);
      // set partial status and show progress tracker
      setStatus(chk);
      if (chk.status === "running") {
        startPolling(chk.run_id);
      }
    }
  };

  // Copy narrative to clipboard
  const handleCopyNarrative = () => {
    if (results?.narrative) {
      navigator.clipboard.writeText(results.narrative);
      alert("Narrative copied to clipboard!");
    }
  };

  const handleQueryAgent = async () => {
    if (!queryQuestion.trim()) {
      alert("Please enter a question.");
      return;
    }
    setQueryLoading(true);
    setQueryAnswer("");
    setQueryWorkflow(null);
    setQueryError(null);
    
    try {
      const res = await axios.post("/api/gioia/query", {
        run_id: runId,
        question: queryQuestion
      });
      setQueryAnswer(res.data.answer);
      setQueryWorkflow(res.data.workflow);
    } catch (err) {
      console.error(err);
      setQueryError(err.response?.data?.detail || "Failed to query the Gioia agent.");
    } finally {
      setQueryLoading(false);
    }
  };

  // Download findings narrative as doc file
  const handleDownloadDoc = () => {
    if (!results?.narrative) return;
    const text = results.narrative;
    const header = "<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'><head><title>Gioia Analysis Research Findings</title><style>body { font-family: 'Times New Roman', serif; line-height: 1.6; padding: 20px; }</style></head><body>";
    const footer = "</body></html>";
    const paragraphs = text.split("\n\n").map(p => `<p>${p.replace(/\n/g, "<br/>")}</p>`).join("");
    const html = header + paragraphs + footer;
    const blob = new Blob(['\ufeff' + html], { type: 'application/msword' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `gioia_findings_${runId}.doc`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const togglePanel = (panel) => {
    setExpandedPanels(prev => ({ ...prev, [panel]: !prev[panel] }));
  };

  // Steps matching timeline
  const stages = [
    { num: 1, name: "Intake Agent", desc: "collecting chunks", statKey: "chunks_count", label: "chunks retrieved" },
    { num: 2, name: "Extraction Agent", desc: "finding relevant passages", statKey: "excerpts_count", label: "excerpts extracted" },
    { num: 3, name: "First Order Coding", desc: "labelling excerpts", statKey: "first_order_count", label: "first-order codes" },
    { num: 4, name: "Second Order Coding", desc: "grouping into themes", statKey: "themes_count", label: "themes created" },
    { num: 5, name: "Dimension Agent", desc: "building theory", statKey: "dimensions_count", label: "aggregate dimensions" },
    { num: 6, name: "Narrative Agent", desc: "writing findings", statKey: null, label: null }
  ];

  return (
    <div className="h-full flex flex-col bg-[#0b0f17] overflow-y-auto p-6 text-[#c9d1d9]">
      {/* Title */}
      <div className="mb-6 pb-4 border-b border-[#21262d]">
        <div className="flex items-center gap-3">
          <Beaker className="text-[#58a6ff]" size={32} />
          <h1 className="text-3xl font-bold bg-gradient-to-r from-[#58a6ff] to-[#bc8cff] bg-clip-text text-transparent">
            Gioia Methodology Qualitative Coding Pipeline
          </h1>
        </div>
        <p className="text-[#8b949e] mt-1 text-sm">
          Run 6 sequential analytical agents to distill qualitative victim narratives and statistics into structured themes and a scholarly findings narrative.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* SECTION 1: RUN PANEL */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 shadow-lg">
            <h2 className="text-lg font-semibold text-[#58a6ff] mb-4 flex items-center gap-2">
              <Play size={18} /> Run New Qualitative Analysis
            </h2>
            <div className="flex flex-col gap-4">
              <div>
                <label className="block text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                  Research Question
                </label>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="e.g. Why do people fall victim to cybercrime and what mechanisms do perpetrators exploit?"
                  rows={3}
                  className="w-full bg-[#0d1117] border border-[#21262d] rounded-lg p-3 text-sm focus:border-[#58a6ff] focus:outline-none transition-colors"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                    Fraud Category Filter (Optional)
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full bg-[#0d1117] border border-[#21262d] rounded-lg p-2.5 text-sm focus:border-[#58a6ff] focus:outline-none transition-colors"
                  >
                    <option value="">All Categories (Unfiltered)</option>
                    {cats.map((c, idx) => (
                      <option key={idx} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-end">
                  <button
                    onClick={handleRun}
                    disabled={status?.status === "running"}
                    className="w-full bg-gradient-to-r from-[#58a6ff] to-[#bc8cff] hover:opacity-90 text-white font-semibold py-2.5 px-4 rounded-lg text-sm transition-opacity flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {status?.status === "running" ? (
                      <>
                        <Loader2 className="animate-spin" size={18} /> Running Agent Pipeline...
                      </>
                    ) : (
                      <>
                        <Beaker size={18} /> Run qualitative analysis
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Progress Tracker (Visible when a run is active/selected) */}
          {status && (
            <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 shadow-lg">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-semibold text-sm text-[#8b949e] uppercase tracking-wider">
                  Analysis Pipeline Progress (Run: <span className="font-mono text-xs text-[#bc8cff]">{status.run_id}</span>)
                </h3>
                <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                  status.status === "complete" ? "bg-[#10b981]/25 text-[#10b981] border border-[#10b981]/50" :
                  status.status === "failed" ? "bg-[#ff7b72]/25 text-[#ff7b72] border border-[#ff7b72]/50" :
                  "bg-[#58a6ff]/25 text-[#58a6ff] border border-[#58a6ff]/50 animate-pulse"
                }`}>
                  {status.status?.toUpperCase()}
                </span>
              </div>

              {error && (
                <div className="bg-[#ff7b72]/10 border border-[#ff7b72]/30 rounded-lg p-3 text-xs text-[#ff7b72] mb-4 flex items-center gap-2">
                  <AlertCircle size={16} />
                  <div>
                    <strong>Pipeline Error:</strong> {error}
                  </div>
                </div>
              )}

              {/* Real-time Perceived Progress Indicator */}
              {status.status === "running" && status.stats && (status.current_stage === 2 || status.current_stage === 3) && (
                <div className="bg-[#0d1117] border border-[#21262d] rounded-lg p-4 mb-6 space-y-3 shadow-inner">
                  <div className="flex justify-between items-center text-xs font-semibold">
                    <span className="text-[#58a6ff] flex items-center gap-2">
                      <Loader2 className="animate-spin" size={14} />
                      {status.current_stage === 2 ? "Screening Excerpts (Stage 2/6)" : "First-Order Qualitative Coding (Stage 3/6)"}
                    </span>
                    {status.stats.est_time_remaining !== undefined && (
                      <span className="text-[#bc8cff] font-mono">
                        Est. Time Remaining: {formatTime(status.stats.est_time_remaining)}
                      </span>
                    )}
                  </div>
                  
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-[11px] text-[#8b949e]">
                      <span>
                        {status.stats.current_batch !== undefined && status.stats.total_batches !== undefined ? 
                          `Batch ${status.stats.current_batch}/${status.stats.total_batches} Processing...` : 
                          "Analyzing Records..."}
                      </span>
                      <span>
                        {status.stats.processed_records !== undefined ? status.stats.processed_records : 0} / {status.stats.total_records || 400} Records Analyzed
                      </span>
                    </div>
                    
                    {/* Progress Bar */}
                    <div className="w-full bg-[#161b22] h-2 rounded-full overflow-hidden border border-[#21262d]">
                      <div 
                        className="h-full bg-gradient-to-r from-[#58a6ff] to-[#bc8cff] transition-all duration-500 rounded-full"
                        style={{ 
                          width: `${Math.min(100, (((status.stats.processed_records || 0) / (status.stats.total_records || 400)) * 100))}%` 
                        }}
                      />
                    </div>
                  </div>

                  {/* 429 Cooldown warning */}
                  {status.stats.rate_limit_waiting && (
                    <div className="bg-[#d29922]/15 border border-[#d29922]/30 rounded-lg p-2.5 text-xs text-[#d29922] flex items-center gap-2 animate-pulse mt-2">
                      <AlertCircle size={14} className="shrink-0" />
                      <span>
                        <strong>Rate Limit Cooldown:</strong> Groq API 429 error. Cooldown timer active (Exponential Backoff). Retrying automatically...
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Vertical Timeline */}
              <div className="relative border-l border-[#21262d] ml-4 pl-6 space-y-6">
                {stages.map((stage) => {
                  const currentStageNum = status.current_stage || 1;
                  const isDone = status.status === "complete" || (status.status !== "failed" && currentStageNum > stage.num);
                  const isCurrent = status.status === "running" && currentStageNum === stage.num;
                  const isStageFailed = status.status === "failed" && currentStageNum === stage.num;
                  const count = stage.statKey ? status.stats?.[stage.statKey] : null;

                  return (
                    <div key={stage.num} className="relative">
                      {/* Timeline Dot Icon */}
                      <span className={`absolute -left-[35px] top-0.5 flex items-center justify-center w-6 h-6 rounded-full border ${
                        isDone ? "bg-[#10b981] border-[#10b981] text-white" :
                        isStageFailed ? "bg-[#ff7b72] border-[#ff7b72] text-white" :
                        isCurrent ? "bg-[#58a6ff]/20 border-[#58a6ff] text-[#58a6ff]" :
                        "bg-[#0d1117] border-[#21262d] text-[#8b949e]"
                      }`}>
                        {isDone ? (
                          <CheckCircle size={14} />
                        ) : isCurrent ? (
                          <Loader2 className="animate-spin" size={14} />
                        ) : isStageFailed ? (
                          <AlertCircle size={14} />
                        ) : (
                          <span className="text-[10px] font-bold">{stage.num}</span>
                        )}
                      </span>

                      {/* Stage description */}
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                        <div>
                          <h4 className={`text-sm font-semibold ${isCurrent ? "text-[#58a6ff]" : "text-[#c9d1d9]"}`}>
                            Step {stage.num}: {stage.name}
                          </h4>
                          <p className="text-xs text-[#8b949e]">{stage.desc}</p>
                        </div>
                        
                        <div className="flex items-center gap-3">
                          {count !== null && count !== undefined && (
                            <span className="text-xs font-mono bg-[#0d1117] px-2 py-1 rounded border border-[#21262d] text-[#10b981]">
                              {count} {stage.label}
                            </span>
                          )}
                          {isStageFailed && (
                            <button
                              onClick={() => handleResume(status.run_id, stage.num)}
                              className="text-xs bg-[#ff7b72]/20 hover:bg-[#ff7b72]/30 text-[#ff7b72] border border-[#ff7b72]/40 rounded px-2.5 py-1 flex items-center gap-1 transition-colors"
                            >
                              <RefreshCw size={12} /> Resume Stage
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Previous Runs Section */}
        <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 shadow-lg flex flex-col h-fit">
          <h2 className="text-base font-semibold text-[#58a6ff] mb-4 flex items-center justify-between">
            <span>📚 Previous Analysis Runs</span>
            <button onClick={fetchCheckpoints} className="text-[#8b949e] hover:text-[#58a6ff]">
              <RefreshCw size={16} />
            </button>
          </h2>
          {checkpoints.length === 0 ? (
            <div className="text-xs text-[#8b949e] text-center py-6">
              No historical analysis checkpoints found.
            </div>
          ) : (
            <div className="space-y-3 max-h-[350px] overflow-y-auto pr-1">
              {checkpoints.map((chk, idx) => (
                <div 
                  key={idx} 
                  onClick={() => handleSelectRun(chk)}
                  className={`p-3 rounded-lg border text-left cursor-pointer transition-all hover:bg-[#1f242c] ${
                    runId === chk.run_id ? "bg-[#1f242c] border-[#58a6ff]" : "bg-[#0d1117] border-[#21262d]"
                  }`}
                >
                  <div className="flex justify-between items-start gap-2 mb-1">
                    <span className="text-[10px] font-mono text-[#8b949e]">
                      {new Date(chk.updated_at).toLocaleString()}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold ${
                      chk.status === "complete" ? "bg-[#10b981]/25 text-[#10b981]" :
                      chk.status === "failed" ? "bg-[#ff7b72]/25 text-[#ff7b72]" :
                      "bg-[#58a6ff]/25 text-[#58a6ff]"
                    }`}>
                      {chk.status}
                    </span>
                  </div>
                  <h4 className="text-xs font-semibold text-[#c9d1d9] line-clamp-2" title={chk.research_question}>
                    {chk.research_question}
                  </h4>
                  {chk.fraud_category && (
                    <span className="inline-block mt-1.5 text-[9px] bg-[#21262d] text-[#8b949e] px-1.5 py-0.5 rounded">
                      Filter: {chk.fraud_category}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* SECTION 2: RESULTS SECTION */}
      {results && (
        <div className="space-y-4">
          <div className="pb-2 border-b border-[#21262d]">
            <h2 className="text-xl font-semibold text-[#bc8cff] flex items-center gap-2">
              <Network size={20} /> Qualitative Coding Results
            </h2>
          </div>

          {/* Panel 1 — Data Structure (Visual Tree Layout) */}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl overflow-hidden shadow-lg">
            <button
              onClick={() => togglePanel("structure")}
              className="w-full flex items-center justify-between p-4 bg-[#1f242c]/50 hover:bg-[#1f242c] transition-colors"
            >
              <span className="font-semibold text-sm text-[#58a6ff] flex items-center gap-2">
                <Network size={16} /> Panel 1 — Visual Coding Structure (First Order &rarr; Themes &rarr; Dimensions)
              </span>
              {expandedPanels.structure ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            {expandedPanels.structure && (
              <div className="p-5 overflow-x-auto bg-[#0d1117]/50">
                <div className="min-w-[700px] flex flex-col gap-4">
                  {results.dimensions.map((dim, dIdx) => {
                    const dimThemes = results.second_order.filter(t => dim.themes.includes(t.theme_name));
                    return (
                      <div key={dIdx} className="border border-[#21262d] bg-[#111622]/40 rounded-xl flex flex-col md:flex-row shadow">
                        
                        {/* Codes & Themes Column */}
                        <div className="flex-1 flex flex-col border-r border-[#21262d]">
                          {dimThemes.map((theme, tIdx) => {
                            return (
                              <div key={tIdx} className="flex border-b border-[#21262d] last:border-b-0">
                                {/* Codes sub-column */}
                                <div className="flex-1 p-4 flex flex-col gap-2 bg-[#0d1117]/30 border-r border-[#21262d]">
                                  <div className="text-[10px] text-[#8b949e] font-semibold mb-1 uppercase tracking-wider">
                                    First-Order Concepts
                                  </div>
                                  {theme.codes.map((codeItem, cIdx) => {
                                    const codeStr = typeof codeItem === "object" ? codeItem.code : codeItem;
                                    return (
                                      <div key={cIdx} className="bg-[#161b22] border border-[#21262d] p-2 rounded-lg text-[11px] leading-relaxed text-[#c9d1d9] hover:border-[#58a6ff]/40 transition-colors">
                                        {codeStr}
                                      </div>
                                    );
                                  })}
                                </div>
                                
                                {/* Theme Column */}
                                <div className="w-72 p-4 bg-[#161b22]/10 flex flex-col justify-center gap-2">
                                  <div className="text-[10px] text-[#8b949e] font-semibold uppercase tracking-wider">
                                    Second-Order Theme
                                  </div>
                                  <span className="font-semibold text-xs text-[#bc8cff]">{theme.theme_name}</span>
                                  <span className="text-[10px] text-[#8b949e] leading-relaxed" title={theme.theme_description || theme.description}>
                                    {theme.theme_description || theme.description}
                                  </span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        
                        {/* Dimension Column */}
                        <div className="w-80 p-5 bg-[#58a6ff]/5 flex flex-col justify-center border-l border-[#21262d] md:border-l-0">
                          <div className="text-[10px] text-[#8b949e] font-semibold mb-1 uppercase tracking-wider">
                            Aggregate Dimension
                          </div>
                          <div className="text-[#58a6ff] font-bold text-sm mb-2">{dim.dimension_name}</div>
                          <p className="text-xs text-[#8b949e] leading-relaxed">{dim.theoretical_explanation}</p>
                        </div>
                        
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Panel 2 — Themes Explorer */}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl overflow-hidden shadow-lg">
            <button
              onClick={() => togglePanel("themes")}
              className="w-full flex items-center justify-between p-4 bg-[#1f242c]/50 hover:bg-[#1f242c] transition-colors"
            >
              <span className="font-semibold text-sm text-[#58a6ff] flex items-center gap-2">
                <Layers size={16} /> Panel 2 — Second Order Themes Explorer
              </span>
              {expandedPanels.themes ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            {expandedPanels.themes && (
              <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                {results.second_order.map((theme, idx) => (
                  <div key={idx} className="bg-[#0d1117] border border-[#21262d] rounded-lg p-4 flex flex-col justify-between">
                    <div>
                      <h4 className="font-semibold text-sm text-[#bc8cff] mb-1">{theme.theme_name}</h4>
                      <p className="text-xs text-[#8b949e] leading-relaxed mb-4">{theme.theme_description || theme.description}</p>
                      
                      <div className="border-t border-[#21262d] pt-3 mt-2">
                        <button
                          onClick={() => toggleThemeExpand(theme.theme_name)}
                          className="w-full flex items-center justify-between px-3 py-2 bg-[#161b22] hover:bg-[#1f242c] border border-[#21262d] rounded-lg text-xs text-[#58a6ff] font-medium transition-colors focus:outline-none"
                        >
                          <span className="flex items-center gap-1.5">
                            <Layers size={12} />
                            {expandedThemes[theme.theme_name] ? "Hide Evidence & Citations" : "Expand to see Evidence (1st-Order Codes & Citations)"}
                          </span>
                          {expandedThemes[theme.theme_name] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                        
                        {expandedThemes[theme.theme_name] && (
                          <div className="space-y-2.5 mt-3">
                            {theme.codes.map((codeItem, cIdx) => {
                              const codeStr = typeof codeItem === "object" ? codeItem.code : codeItem;
                              const codeObj = typeof codeItem === "object" ? codeItem : results.first_order.find(fo => fo.code === codeStr);
                              const docId = codeObj ? (codeObj.chunk_id || codeObj.doc_id || "Unknown") : "Unknown";
                              const quote = codeObj?.key_quote || codeObj?.quote;
                              return (
                                <div key={cIdx} className="bg-[#161b22]/40 border border-[#21262d] p-3 rounded-lg flex flex-col gap-2 shadow">
                                  <div className="flex justify-between items-start gap-4">
                                    <span className="text-xs font-semibold text-[#c9d1d9]">{codeStr}</span>
                                    <span className="font-mono text-[10px] text-[#58a6ff] bg-[#58a6ff]/10 px-1.5 py-0.5 rounded border border-[#58a6ff]/20 shrink-0">
                                      [{docId}]
                                    </span>
                                  </div>
                                  {quote && (
                                    <div className="text-[11px] text-[#8b949e] italic leading-relaxed border-l-2 border-[#bc8cff]/30 pl-2">
                                      "{quote}"
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Panel 3 — Dimensions */}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl overflow-hidden shadow-lg">
            <button
              onClick={() => togglePanel("dimensions")}
              className="w-full flex items-center justify-between p-4 bg-[#1f242c]/50 hover:bg-[#1f242c] transition-colors"
            >
              <span className="font-semibold text-sm text-[#58a6ff] flex items-center gap-2">
                <Network size={16} /> Panel 3 — Aggregate Dimensions & Theoretical Explanation
              </span>
              {expandedPanels.dimensions ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            {expandedPanels.dimensions && (
              <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                {results.dimensions.map((dim, idx) => (
                  <div key={idx} className="bg-[#0d1117] border border-[#21262d] rounded-lg p-4 flex flex-col justify-between">
                    <div>
                      <h4 className="font-bold text-sm text-[#58a6ff] mb-2">{dim.dimension_name}</h4>
                      <p className="text-xs text-[#c9d1d9] leading-relaxed mb-4 italic">{dim.theoretical_explanation}</p>
                      
                      <div className="border-t border-[#21262d] pt-3">
                        <span className="block text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                          Themes in this Dimension:
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {dim.themes.map((tName, tIdx) => (
                            <span key={tIdx} className="bg-[#bc8cff]/10 border border-[#bc8cff]/30 text-[#bc8cff] text-[10px] px-2 py-1 rounded">
                              {tName}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Panel 4 — Research Findings (Narrative) */}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl overflow-hidden shadow-lg">
            <button
              onClick={() => togglePanel("findings")}
              className="w-full flex items-center justify-between p-4 bg-[#1f242c]/50 hover:bg-[#1f242c] transition-colors"
            >
              <span className="font-semibold text-sm text-[#58a6ff] flex items-center gap-2">
                <BookOpen size={16} /> Panel 4 — Scholarly Findings Narrative
              </span>
              {expandedPanels.findings ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            {expandedPanels.findings && (
              <div className="p-6 bg-[#0d1117]">
                <div className="flex justify-end gap-2 mb-4">
                  <button
                    onClick={handleCopyNarrative}
                    className="text-xs bg-[#21262d] hover:bg-[#30363d] text-[#c9d1d9] border border-[#30363d] rounded px-3 py-1.5 flex items-center gap-1.5 transition-colors"
                  >
                    <Copy size={14} /> Copy to Clipboard
                  </button>
                  <button
                    onClick={handleDownloadDoc}
                    className="text-xs bg-[#58a6ff]/20 hover:bg-[#58a6ff]/30 text-[#58a6ff] border border-[#58a6ff]/40 rounded px-3 py-1.5 flex items-center gap-1.5 transition-colors"
                  >
                    <Download size={14} /> Download as Word Document
                  </button>
                </div>
                <div className="prose max-w-none text-[#c9d1d9] text-sm leading-relaxed space-y-4 font-serif">
                  {results.narrative.split("\n\n").map((para, idx) => (
                    <p key={idx} className="indent-8 text-justify">
                      {para}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
          
          {/* Panel 5 — Query Gioia Agent (Q&A) */}
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl overflow-hidden shadow-lg mt-6">
            <button
              onClick={() => togglePanel("query")}
              className="w-full flex items-center justify-between p-4 bg-[#1f242c]/50 hover:bg-[#1f242c] transition-colors"
            >
              <span className="font-semibold text-sm text-[#58a6ff] flex items-center gap-2">
                <Beaker size={16} /> Panel 5 — Query Gioia Agent (Interactive Q&A & Workflow Trace)
              </span>
              {expandedPanels.query ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            {expandedPanels.query && (
              <div className="p-6 bg-[#0d1117]/30 space-y-6">
                <div>
                  <label className="block text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                    Ask the Gioia Qualitative Research Agent a Question
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={queryQuestion}
                      onChange={(e) => setQueryQuestion(e.target.value)}
                      placeholder="Ask about victim profiles, coercion tactics, recovery, or policy gaps..."
                      className="flex-1 bg-[#0d1117] border border-[#21262d] rounded-lg px-4 py-2.5 text-sm focus:border-[#58a6ff] focus:outline-none transition-colors text-white"
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleQueryAgent();
                      }}
                    />
                    <button
                      onClick={handleQueryAgent}
                      disabled={queryLoading}
                      className="bg-[#58a6ff] hover:bg-[#478ed9] text-[#0d1117] font-semibold px-6 py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {queryLoading ? (
                        <>
                          <Loader2 className="animate-spin" size={16} /> Querying...
                        </>
                      ) : (
                        "Query"
                      )}
                    </button>
                  </div>
                </div>

                {queryError && (
                  <div className="bg-[#ff7b72]/10 border border-[#ff7b72]/30 rounded-lg p-3 text-xs text-[#ff7b72] flex items-center gap-2">
                    <AlertCircle size={16} />
                    <div>{queryError}</div>
                  </div>
                )}

                {queryAnswer && (
                  <div className="space-y-6">
                    {/* Workflow Trace */}
                    {queryWorkflow && (
                      <div className="border border-[#21262d] rounded-xl p-4 bg-[#161b22]/40 space-y-4">
                        <h4 className="text-xs font-bold text-[#8b949e] uppercase tracking-wider flex items-center gap-2">
                          <Network size={14} /> Agent Reasoning Trace Workflow
                        </h4>
                        
                        <div className="space-y-4 border-l border-[#21262d] ml-2 pl-4">
                          {/* Step 1: Retrieve Codes */}
                          <div>
                            <span className="text-xs font-semibold text-[#58a6ff] block mb-2">
                              Step 1: Retrieved Key Qualitative Concepts & Quotes
                            </span>
                            <div className="space-y-2">
                              {queryWorkflow.retrieved_codes?.map((item, idx) => (
                                <div key={idx} className="bg-[#0d1117] border border-[#21262d] p-3 rounded-lg text-xs">
                                  <div className="flex justify-between items-center mb-1 text-[10px] text-[#8b949e]">
                                    <span className="font-semibold text-[#bc8cff]">Concept: {item.code}</span>
                                    <span className="font-mono text-[9px] text-[#58a6ff]">[{item.source} | {item.date}]</span>
                                  </div>
                                  <p className="italic text-[#c9d1d9] mt-1 leading-relaxed">
                                    "{item.quote}"
                                  </p>
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Step 2: Map to Themes */}
                          <div>
                            <span className="text-xs font-semibold text-[#bc8cff] block mb-2">
                              Step 2: Mapped to Conceptual Themes
                            </span>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {queryWorkflow.mapped_themes?.map((item, idx) => (
                                <div key={idx} className="bg-[#0d1117] border border-[#21262d] p-3 rounded-lg text-xs">
                                  <div className="font-bold text-[#bc8cff] mb-1">{item.name}</div>
                                  <p className="text-[#8b949e] leading-relaxed">{item.description}</p>
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Step 3: Map to Aggregate Dimensions */}
                          <div>
                            <span className="text-xs font-semibold text-[#10b981] block mb-2">
                              Step 3: Mapped to Aggregate Theoretical Dimensions
                            </span>
                            <div className="space-y-2">
                              {queryWorkflow.mapped_dimensions?.map((item, idx) => (
                                <div key={idx} className="bg-[#0d1117] border border-[#21262d] p-3 rounded-lg text-xs">
                                  <div className="font-bold text-[#10b981] mb-1">{item.dimension_name}</div>
                                  <div className="text-[#c9d1d9]"><span className="text-[#8b949e] font-semibold">Theoretical Concept:</span> {item.theoretical_concept}</div>
                                  <div className="text-[#c9d1d9] mt-0.5"><span className="text-[#8b949e] font-semibold">Theoretical Implication:</span> {item.theoretical_implication}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Agent Response */}
                    <div className="bg-[#1f242c]/40 border border-[#21262d] rounded-xl p-5 space-y-3">
                      <h4 className="text-xs font-bold text-[#bc8cff] uppercase tracking-wider flex items-center gap-2">
                        <Beaker size={14} /> Synthesized Academic Answer
                      </h4>
                      <div className="prose max-w-none text-[#c9d1d9] text-sm leading-relaxed font-serif text-justify indent-8">
                        {queryAnswer.split("\n\n").map((para, idx) => (
                          <p key={idx} className="mb-3">
                            {para}
                          </p>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
