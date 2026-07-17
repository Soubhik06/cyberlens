import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { 
  Beaker, Play, CheckCircle, AlertCircle, Loader2, Copy, 
  Download, RefreshCw, ChevronDown, ChevronUp, Layers, BookOpen, Network, AlertOctagon, Search, FileSpreadsheet, Eye
} from "lucide-react";

export default function GioiaStandalone({ cats }) {
  const [question, setQuestion] = useState("Why do people fall victim to cybercrime and what mechanisms do perpetrators exploit?");
  const [category, setCategory] = useState("");
  const [maxRecords, setMaxRecords] = useState(500);
  const [runId, setRunId] = useState(null);
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [checkpoints, setCheckpoints] = useState([]);
  const [error, setError] = useState(null);
  
  // Standalone Chunks Viewer States
  const [chunks, setChunks] = useState([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [selectedChunk, setSelectedChunk] = useState(null);

  // Q&A Agent box states
  const [queryQuestion, setQueryQuestion] = useState("");
  const [queryAnswer, setQueryAnswer] = useState("");
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryWorkflow, setQueryWorkflow] = useState(null);
  const [queryError, setQueryError] = useState(null);

  // Expansion panel states
  const [expandedPanels, setExpandedPanels] = useState({
    structure: true,
    themes: false,
    dimensions: false,
    findings: true,
    query: true
  });
  
  const [expandedThemes, setExpandedThemes] = useState({});

  const togglePanel = (panel) => {
    setExpandedPanels(prev => ({ ...prev, [panel]: !prev[panel] }));
  };

  const toggleThemeExpand = (themeName) => {
    setExpandedThemes(prev => ({ ...prev, [themeName]: !prev[themeName] }));
  };

  const pollInterval = useRef(null);

  // Fetch checkpoints
  const fetchCheckpoints = async () => {
    try {
      const res = await axios.get("/api/gioia/checkpoints");
      setCheckpoints(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchCheckpoints();
    return () => {
      if (pollInterval.current) clearInterval(pollInterval.current);
    };
  }, []);

  // Fetch stage 1 chunks once available
  const fetchChunks = async (id) => {
    setChunksLoading(true);
    try {
      const res = await axios.get(`/api/gioia/chunks/${id}`);
      setChunks(res.data);
    } catch (err) {
      console.error("Failed to load chunks:", err);
    } finally {
      setChunksLoading(false);
    }
  };

  // Start status polling
  const startPolling = (id) => {
    setRunId(id);
    if (pollInterval.current) clearInterval(pollInterval.current);

    pollInterval.current = setInterval(async () => {
      try {
        const res = await axios.get(`/api/gioia/status/${id}`);
        setStatus(res.data);
        
        // Fetch chunks if stage 1 is done and we haven't loaded them yet
        if (res.data.current_stage >= 2 && chunks.length === 0 && !chunksLoading) {
          fetchChunks(id);
        }

        if (res.data.status === "complete") {
          clearInterval(pollInterval.current);
          fetchResults(id);
          fetchCheckpoints();
        } else if (res.data.status === "failed") {
          clearInterval(pollInterval.current);
          setError(res.data.error || "Pipeline execution failed.");
          fetchCheckpoints();
        }
      } catch (err) {
        console.error(err);
        setError("Failed to fetch status updates.");
      }
    }, 2000);
  };

  // Run new qualitative analysis
  const handleRun = async () => {
    if (!question.trim()) {
      alert("Please enter a research question.");
      return;
    }
    setResults(null);
    setStatus(null);
    setChunks([]);
    setError(null);
    setQueryAnswer("");
    setQueryWorkflow(null);
    
    try {
      const res = await axios.post("/api/gioia/run", {
        research_question: question,
        fraud_category: category || null,
        max_records: Number(maxRecords) || 500,
        filter_category: false  // Disable strict category filtering for standalone evaluation
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

  // Stop run
  const handleStop = async (id) => {
    try {
      const res = await axios.post(`/api/gioia/stop/${id}`);
      if (res.data.status === "success") {
        const statusRes = await axios.get(`/api/gioia/status/${id}`);
        setStatus(statusRes.data);
        if (pollInterval.current) clearInterval(pollInterval.current);
      }
    } catch (err) {
      console.error(err);
      alert("Failed to stop analysis pipeline.");
    }
  };

  // Load results
  const fetchResults = async (id) => {
    try {
      const res = await axios.get(`/api/gioia/results/${id}`);
      setResults(res.data);
      setStatus(res.data.metadata);
      fetchChunks(id);
    } catch (err) {
      console.error(err);
      setError("Failed to load completed analysis results.");
    }
  };

  // Select a historical run
  const handleSelectRun = (chk) => {
    if (pollInterval.current) clearInterval(pollInterval.current);
    setError(null);
    setResults(null);
    setChunks([]);
    setQueryAnswer("");
    setQueryWorkflow(null);
    
    if (chk.status === "complete") {
      fetchResults(chk.run_id);
    } else {
      setStatus(chk);
      setRunId(chk.run_id);
      if (chk.status === "running") {
        startPolling(chk.run_id);
      }
    }
  };

  // Query Q&A Agent method
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

  // Copy narrative to clipboard
  const handleCopyNarrative = () => {
    if (!results?.narrative) return;
    const text = typeof results.narrative === "string" ? results.narrative : 
      `${results.narrative?.methods_paragraph || ""}\n\n${results.narrative?.findings_section || ""}`;
    navigator.clipboard.writeText(text);
    alert("Scholarly narrative copied to clipboard!");
  };

  // Download findings narrative as doc file
  const handleDownloadDoc = () => {
    if (!results?.narrative) return;
    const text = typeof results.narrative === "string" ? results.narrative : 
      `${results.narrative?.methods_paragraph || ""}\n\n${results.narrative?.findings_section || ""}`;
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

  const filteredChunks = chunks.filter(c => {
    const matchesSearch = 
      c.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (c.title || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
      (c.text || "").toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesType = typeFilter === "ALL" || c.narrative_type === typeFilter;
    return matchesSearch && matchesType;
  });

  const stageDescriptions = [
    { num: 1, name: "Intake Agent", desc: "collecting chunks", statKey: "chunks_count", label: "records retrieved" },
    { num: 2, name: "Extraction Agent", desc: "finding relevant passages", statKey: "excerpts_count", label: "relevant excerpts" },
    { num: 3, name: "First Order Coding", desc: "labelling excerpts", statKey: "first_order_count", label: "first-order codes" },
    { num: 4, name: "Second Order Coding", desc: "grouping into themes", statKey: "themes_count", label: "second-order themes" },
    { num: 5, name: "Dimension Agent", desc: "building theory", statKey: "dimensions_count", label: "aggregate dimensions" },
    { num: 6, name: "Narrative Agent", desc: "writing findings", statKey: null, label: null }
  ];

  return (
    <div className="min-h-screen flex flex-col bg-[#0b0f17] text-[#c9d1d9] font-sans p-6 overflow-y-auto">
      {/* HEADER SECTION */}
      <div className="mb-6 pb-6 border-b border-[#21262d] flex justify-between items-center">
        <div>
          <div className="flex items-center gap-3">
            <FileSpreadsheet className="text-[#58a6ff]" size={36} />
            <h1 className="text-3xl font-bold bg-gradient-to-r from-[#58a6ff] to-[#bc8cff] bg-clip-text text-transparent">
              Seeded Gioia Standalone Evaluator (500 Chunks)
            </h1>
          </div>
          <p className="text-[#8b949e] mt-1 text-sm">
            Evaluate qualitative coding consistency against a deterministic 500-sample slice. Free of parliamentary data.
          </p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={() => window.location.href = "/"}
            className="px-4 py-2 border border-[#21262d] hover:bg-[#161b22] rounded-lg text-sm transition-colors text-[#58a6ff]"
          >
            ← Back to Main App
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* PANEL 1: CONFIGURATION & LAUNCH */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 shadow-lg">
            <h2 className="text-lg font-semibold text-[#58a6ff] mb-4 flex items-center gap-2">
              <Play size={18} /> Configure Seeded Qualitative Session
            </h2>
            <div className="flex flex-col gap-4">
              <div>
                <label className="block text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                  Research Question (Determines seed for deterministic sampling)
                </label>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Enter research question..."
                  rows={2}
                  className="w-full bg-[#0d1117] border border-[#21262d] rounded-lg p-3 text-sm focus:border-[#58a6ff] focus:outline-none transition-colors"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                    Fraud Category Filter
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
                <div>
                  <label className="block text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                    Target Chunk count
                  </label>
                  <input
                    type="number"
                    value={maxRecords}
                    onChange={(e) => setMaxRecords(Math.max(10, parseInt(e.target.value) || 0))}
                    min={10}
                    max={10000}
                    className="w-full bg-[#0d1117] border border-[#21262d] rounded-lg p-2.5 text-sm focus:border-[#58a6ff] focus:outline-none transition-colors"
                  />
                </div>
                <div className="flex items-end">
                  <button
                    onClick={handleRun}
                    disabled={status?.status === "running"}
                    className="w-full bg-gradient-to-r from-[#58a6ff] to-[#bc8cff] hover:opacity-90 text-white font-semibold py-2.5 px-4 rounded-lg text-sm transition-opacity flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {status?.status === "running" ? (
                      <>
                        <Loader2 className="animate-spin" size={18} /> Running...
                      </>
                    ) : (
                      <>
                        <Beaker size={18} /> Start Pipeline
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* REALTIME PROGRESS DASHBOARD */}
          {status && (
            <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 shadow-lg">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-semibold text-sm text-[#8b949e] uppercase tracking-wider">
                  Pipeline Status Tracking (ID: <span className="font-mono text-xs text-[#bc8cff]">{status.run_id}</span>)
                </h3>
                <div className="flex items-center gap-2">
                  {status.status === "running" && (
                    <button
                      onClick={() => handleStop(status.run_id)}
                      className="flex items-center gap-1 px-2.5 py-1 bg-[#ff7b72]/15 hover:bg-[#ff7b72]/25 text-[#ff7b72] border border-[#ff7b72]/30 rounded-lg text-xs font-medium transition-colors"
                    >
                      <AlertOctagon size={13} /> Stop
                    </button>
                  )}
                  <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                    status.status === "complete" ? "bg-[#10b981]/25 text-[#10b981] border border-[#10b981]/50" :
                    status.status === "failed" ? "bg-[#ff7b72]/25 text-[#ff7b72] border border-[#ff7b72]/50" :
                    "bg-[#58a6ff]/25 text-[#58a6ff] border border-[#58a6ff]/50 animate-pulse"
                  }`}>
                    {status.status?.toUpperCase()}
                  </span>
                </div>
              </div>

              {error && (
                <div className="bg-[#ff7b72]/10 border border-[#ff7b72]/30 rounded-lg p-3 text-xs text-[#ff7b72] mb-4 flex items-center gap-2">
                  <AlertCircle size={16} />
                  <div><strong>Error:</strong> {error}</div>
                </div>
              )}

              {/* Progress Stage Tracker */}
              <div className="space-y-4">
                {stageDescriptions.map((stage) => {
                  const currentStageNum = status.current_stage || 1;
                  const isDone = status.status === "complete" || (status.status !== "failed" && currentStageNum > stage.num);
                  const isCurrent = status.status === "running" && currentStageNum === stage.num;
                  const isStageFailed = status.status === "failed" && currentStageNum === stage.num;
                  const count = stage.statKey ? status.stats?.[stage.statKey] : null;

                  return (
                    <div 
                      key={stage.num}
                      className={`border rounded-lg p-3 transition-colors ${
                        isCurrent ? "bg-[#58a6ff]/5 border-[#58a6ff]/40" :
                        isStageFailed ? "bg-[#ff7b72]/5 border-[#ff7b72]/40" :
                        isDone ? "bg-[#10b981]/5 border-[#10b981]/20" :
                        "bg-[#0d1117]/30 border-[#21262d]"
                      }`}
                    >
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2.5">
                          {isDone ? <CheckCircle size={16} className="text-[#10b981]" /> :
                           isStageFailed ? <AlertCircle size={16} className="text-[#ff7b72]" /> :
                           isCurrent ? <Loader2 size={16} className="text-[#58a6ff] animate-spin" /> :
                           <div className="w-4 h-4 rounded-full border border-[#8b949e] flex items-center justify-center text-[10px] text-[#8b949e]">{stage.num}</div>}
                          <div>
                            <span className="font-semibold text-sm">{stage.name}</span>
                            <span className="text-xs text-[#8b949e] ml-2">({stage.desc})</span>
                          </div>
                        </div>
                        {count !== null && (
                          <span className="text-xs font-mono bg-[#21262d] px-2 py-0.5 rounded text-[#8b949e]">
                            {count} {stage.label}
                          </span>
                        )}
                        {!isDone && isStageFailed && (
                          <button
                            onClick={() => handleResume(status.run_id, stage.num)}
                            className="text-xs text-[#ff7b72] border border-[#ff7b72]/40 hover:bg-[#ff7b72]/10 px-2 py-0.5 rounded"
                          >
                            Resume Stage
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* PANEL 2: SESSIONS SIDEBAR */}
        <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 shadow-lg flex flex-col h-[500px]">
          <h2 className="text-lg font-semibold text-[#58a6ff] mb-4 flex items-center gap-2">
            <RefreshCw size={18} /> Sessions Repository
          </h2>
          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {checkpoints.length === 0 ? (
              <p className="text-xs text-[#8b949e] italic">No prior runs recorded on this machine.</p>
            ) : (
              checkpoints.map((chk, idx) => (
                <div 
                  key={idx}
                  onClick={() => handleSelectRun(chk)}
                  className={`border rounded-lg p-3 cursor-pointer transition-colors ${
                    runId === chk.run_id ? "bg-[#58a6ff]/10 border-[#58a6ff]/50" : "bg-[#0d1117] border-[#21262d] hover:bg-[#161b22]"
                  }`}
                >
                  <div className="flex justify-between items-start mb-1.5">
                    <span className="font-mono text-[10px] text-[#bc8cff] truncate max-w-[170px]">{chk.run_id}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                      chk.status === "complete" ? "bg-[#10b981]/15 text-[#10b981]" :
                      chk.status === "failed" ? "bg-[#ff7b72]/15 text-[#ff7b72]" :
                      "bg-[#58a6ff]/15 text-[#58a6ff]"
                    }`}>
                      {chk.status}
                    </span>
                  </div>
                  <p className="text-xs text-[#c9d1d9] line-clamp-2">{chk.research_question}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* PANEL 3: INTERACTIVE EXCEL-LIKE CHUNKS VIEW */}
      {chunks.length > 0 && (
        <div className="bg-[#161b22] border border-[#21262d] rounded-xl p-5 shadow-lg mb-8">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4 border-b border-[#21262d] pb-4">
            <div>
              <h2 className="text-lg font-semibold text-[#58a6ff] flex items-center gap-2">
                <FileSpreadsheet size={20} /> Seeded Sample Tracker (Total: {chunks.length} Chunks)
              </h2>
              <p className="text-xs text-[#8b949e] mt-0.5">
                Verify exactly which rows/ids were selected deterministically. Excel columns are displayed side-by-side.
              </p>
            </div>
            
            {/* SEARCH AND FILTERS */}
            <div className="flex flex-wrap gap-2 w-full md:w-auto">
              <div className="relative flex-1 md:flex-initial">
                <Search className="absolute left-3 top-2.5 text-[#8b949e]" size={15} />
                <input
                  type="text"
                  placeholder="Search Excel ID or text..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full md:w-60 bg-[#0d1117] border border-[#21262d] rounded-lg pl-9 pr-3 py-1.5 text-xs focus:border-[#58a6ff] focus:outline-none"
                />
              </div>
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="bg-[#0d1117] border border-[#21262d] rounded-lg px-3 py-1.5 text-xs focus:outline-none"
              >
                <option value="ALL">All Types</option>
                <option value="VICTIM">VICTIM</option>
                <option value="NEAR-MISS">NEAR-MISS</option>
                <option value="THIRD-PARTY">THIRD-PARTY</option>
              </select>
            </div>
          </div>

          {/* EXCEL-LIKE DATAGRID */}
          <div className="overflow-x-auto border border-[#21262d] rounded-lg max-h-[400px]">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-[#0d1117] border-b border-[#21262d] text-[#8b949e]">
                  <th className="p-3 font-semibold border-r border-[#21262d]">Unique ID</th>
                  <th className="p-3 font-semibold border-r border-[#21262d]">Narrative Type</th>
                  <th className="p-3 font-semibold border-r border-[#21262d]">Source</th>
                  <th className="p-3 font-semibold border-r border-[#21262d]">Title / Headline</th>
                  <th className="p-3 font-semibold border-r border-[#21262d]">Category</th>
                  <th className="p-3 font-semibold">Notes / Text Chunk Excerpt</th>
                  <th className="p-3 font-semibold text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#21262d]">
                {filteredChunks.map((c, idx) => (
                  <tr key={idx} className="hover:bg-[#161b22] transition-colors">
                    <td className="p-3 border-r border-[#21262d] font-mono text-[#bc8cff] font-semibold">{c.id}</td>
                    <td className="p-3 border-r border-[#21262d]">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        c.narrative_type === "VICTIM" ? "bg-[#ff7b72]/15 text-[#ff7b72]" :
                        c.narrative_type === "NEAR-MISS" ? "bg-[#58a6ff]/15 text-[#58a6ff]" :
                        "bg-[#bc8cff]/15 text-[#bc8cff]"
                      }`}>
                        {c.narrative_type}
                      </span>
                    </td>
                    <td className="p-3 border-r border-[#21262d] text-[#8b949e]">{c.source}</td>
                    <td className="p-3 border-r border-[#21262d] font-medium max-w-[200px] truncate">{c.title || "N/A"}</td>
                    <td className="p-3 border-r border-[#21262d] text-[#8b949e] truncate max-w-[150px]">{c.fraud_category}</td>
                    <td className="p-3 border-r border-[#21262d] text-[#8b949e] max-w-sm truncate">{c.text}</td>
                    <td className="p-3 text-center">
                      <button
                        onClick={() => setSelectedChunk(c)}
                        className="text-[#58a6ff] hover:underline flex items-center gap-1 mx-auto"
                      >
                        <Eye size={12} /> View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* PANEL 4: ACADEMIC FINDINGS & RESULTS DISPLAY (MATCHING FULL GIOIA AGENT PATTERN) */}
      {results && (
        <div className="space-y-6">
          <div className="pb-2 border-b border-[#21262d]">
            <h2 className="text-xl font-semibold text-[#bc8cff] flex items-center gap-2">
              <Network size={20} /> Qualitative Coding Results & Theoretical Dimensions
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
                  {results.dimensions?.map((dim, dIdx) => {
                    const dimThemes = results.second_order?.filter(t => dim.themes.includes(t.theme_name)) || [];
                    return (
                      <div key={dIdx} className="border border-[#21262d] bg-[#111622]/40 rounded-xl flex flex-col md:flex-row shadow">
                        
                        {/* Codes & Themes Column */}
                        <div className="flex-1 flex flex-col border-r border-[#21262d]">
                          {dimThemes.map((theme, tIdx) => (
                            <div key={tIdx} className="flex border-b border-[#21262d] last:border-b-0">
                              {/* Codes sub-column */}
                              <div className="flex-1 p-4 flex flex-col gap-2 bg-[#0d1117]/30 border-r border-[#21262d]">
                                <div className="text-[10px] text-[#8b949e] font-semibold mb-1 uppercase tracking-wider">
                                  First-Order Concepts
                                </div>
                                {theme.codes?.map((codeItem, cIdx) => {
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
                                <span className="text-[10px] text-[#8b949e] leading-relaxed">
                                  {theme.theme_description || theme.description}
                                </span>
                              </div>
                            </div>
                          ))}
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
                <Layers size={16} /> Panel 2 — Second Order Themes Explorer (with Evidence)
              </span>
              {expandedPanels.themes ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            {expandedPanels.themes && (
              <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                {results.second_order?.map((theme, idx) => (
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
                            {theme.codes?.map((codeItem, cIdx) => {
                              const codeStr = typeof codeItem === "object" ? codeItem.code : codeItem;
                              const codeObj = typeof codeItem === "object" ? codeItem : results.first_order?.find(fo => fo.code === codeStr);
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
                {results.dimensions?.map((dim, idx) => (
                  <div key={idx} className="bg-[#0d1117] border border-[#21262d] rounded-lg p-4 flex flex-col justify-between">
                    <div>
                      <h4 className="font-bold text-sm text-[#58a6ff] mb-2">{dim.dimension_name}</h4>
                      <p className="text-xs text-[#c9d1d9] leading-relaxed mb-4 italic">{dim.theoretical_explanation}</p>
                      
                      <div className="border-t border-[#21262d] pt-3">
                        <span className="block text-[10px] font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                          Themes in this Dimension:
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {dim.themes?.map((tName, tIdx) => (
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
                  {(typeof results.narrative === "string" ? results.narrative : 
                    `${results.narrative?.methods_paragraph || ""}\n\n${results.narrative?.findings_section || ""}`
                  ).split("\n\n").map((para, idx) => (
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
                <Beaker size={16} /> Panel 5 — Query Gioia Standalone Agent (Interactive Q&A & Workflow Trace)
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

      {/* CHUNK DETAIL MODAL */}
      {selectedChunk && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-[#161b22] border border-[#30363d] rounded-xl max-w-2xl w-full p-6 shadow-2xl relative">
            <div className="flex justify-between items-start mb-4 border-b border-[#21262d] pb-3">
              <div>
                <span className="font-mono text-xs text-[#bc8cff] font-bold block mb-1">{selectedChunk.id}</span>
                <h3 className="text-lg font-bold text-[#c9d1d9]">{selectedChunk.title || "No Title"}</h3>
              </div>
              <button 
                onClick={() => setSelectedChunk(null)}
                className="text-[#8b949e] hover:text-[#c9d1d9] text-xl font-bold font-mono"
              >
                ×
              </button>
            </div>
            
            <div className="grid grid-cols-2 gap-4 mb-4 text-xs bg-[#0d1117] p-3 rounded-lg border border-[#21262d]">
              <div>
                <span className="block text-[#8b949e] font-semibold mb-1">Narrative Type:</span>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  selectedChunk.narrative_type === "VICTIM" ? "bg-[#ff7b72]/15 text-[#ff7b72]" :
                  selectedChunk.narrative_type === "NEAR-MISS" ? "bg-[#58a6ff]/15 text-[#58a6ff]" :
                  "bg-[#bc8cff]/15 text-[#bc8cff]"
                }`}>
                  {selectedChunk.narrative_type}
                </span>
              </div>
              <div>
                <span className="block text-[#8b949e] font-semibold mb-1">Source Dataset:</span>
                <span className="text-[#c9d1d9]">{selectedChunk.source === "web_scraping" ? "Stream A Scraped Media" : "ProQuest News Database"}</span>
              </div>
              <div className="col-span-2">
                <span className="block text-[#8b949e] font-semibold mb-1">Detected Fraud Category:</span>
                <span className="text-[#c9d1d9]">{selectedChunk.fraud_category}</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">
                Raw Text Chunk / Narrative
              </label>
              <div className="bg-[#0d1117] border border-[#21262d] rounded-lg p-4 text-xs text-[#c9d1d9] leading-relaxed max-h-[250px] overflow-y-auto font-mono whitespace-pre-line">
                {selectedChunk.text}
              </div>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setSelectedChunk(null)}
                className="px-4 py-2 bg-[#21262d] hover:bg-[#30363d] border border-[#30363d] rounded-lg text-xs font-semibold transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
