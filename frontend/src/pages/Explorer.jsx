import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Search, Filter, X, Download, FileText, Calendar, MapPin, Tag } from "lucide-react";

export default function Explorer({ cats, platforms, narrativeTypes }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  
  // Filters State
  const [streamFilter, setStreamFilter] = useState("All");
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [typeFilter, setTypeFilter] = useState("All");
  
  // Drawer State
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [docText, setDocText] = useState("");
  const [loadingText, setLoadingText] = useState(false);

  // Load all documents on mount for client-side search and virtual list
  useEffect(() => {
    const fetchAllDocs = async () => {
      try {
        const response = await axios.get("/api/documents?page=1&page_size=20000");
        setDocuments(response.data.documents || []);
        setLoading(false);
      } catch (error) {
        console.error(error);
        setLoading(false);
      }
    };
    fetchAllDocs();
  }, []);

  // Fetch full text when document is selected in drawer
  useEffect(() => {
    if (!selectedDoc) return;
    
    if (selectedDoc.stream === "A") {
      setLoadingText(true);
      setDocText("");
      axios.get(`/txt/${selectedDoc.doc_id}.txt`)
        .then(res => {
          setDocText(res.data);
          setLoadingText(false);
        })
        .catch(err => {
          console.error(err);
          setDocText(`⚠️ Failed to load raw text file from server for ${selectedDoc.doc_id}.`);
          setLoadingText(false);
        });
    } else {
      setDocText("");
    }
  }, [selectedDoc]);

  // Apply filters in real time
  const filteredDocs = documents.filter((doc) => {
    const matchesSearch =
      doc.title.toLowerCase().includes(search.toLowerCase()) ||
      doc.doc_id.toLowerCase().includes(search.toLowerCase());
    
    const matchesStream =
      streamFilter === "All" || doc.stream === streamFilter;
      
    const matchesCategory =
      categoryFilter === "All" || doc.fraud_category === categoryFilter;
      
    const matchesType =
      typeFilter === "All" || doc.narrative_type === typeFilter;
      
    return matchesSearch && matchesStream && matchesCategory && matchesType;
  });

  // Export as CSV
  const handleExportCSV = () => {
    const headers = ["doc_id", "title", "source_platform", "original_date", "fraud_category", "narrative_type", "stream"];
    const rows = filteredDocs.map((doc) => [
      doc.doc_id,
      `"${doc.title.replace(/"/g, '""')}"`,
      `"${(doc.source_platform || "").replace(/"/g, '""')}"`,
      doc.original_date || "",
      `"${(doc.fraud_category || "").replace(/"/g, '""')}"`,
      `"${(doc.narrative_type || "").replace(/"/g, '""')}"`,
      doc.stream
    ]);
    
    const csvContent = "data:text/csv;charset=utf-8," 
      + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
      
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "cyberlens_explorer_export.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Virtual Scroll setup
  const parentRef = useRef(null);
  const rowVirtualizer = useVirtualizer({
    count: filteredDocs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 50,
    overscan: 10,
  });

  return (
    <div className="flex h-full bg-darkBg text-textMain relative overflow-hidden">
      {/* Table Section */}
      <div className="flex-1 flex flex-col p-6 overflow-hidden">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-darkBorder pb-4 mb-4 gap-4">
          <div>
            <h1 className="text-2xl font-bold text-[#58a6ff]">Document Explorer</h1>
            <p className="text-sm text-textMuted mt-1">
              Search and filter indices. Click a row to slide out detailed views.
            </p>
          </div>
          <button
            onClick={handleExportCSV}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#161b22] border border-darkBorder hover:border-[#58a6ff] hover:text-[#58a6ff] text-xs font-semibold transition-all focus:outline-none shrink-0"
          >
            <Download size={14} />
            <span>Export CSV</span>
          </button>
        </div>

        {/* Filter Controls Row */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
          <div className="relative">
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-textMuted">
              <Search size={16} />
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by title or ID..."
              className="w-full bg-[#161b22] border border-darkBorder rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
            />
          </div>

          <select
            value={streamFilter}
            onChange={(e) => setStreamFilter(e.target.value)}
            className="bg-[#161b22] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
          >
            <option value="All">All Streams</option>
            <option value="A">Stream A (Narratives)</option>
            <option value="B">Stream B (Government)</option>
          </select>

          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="bg-[#161b22] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain max-w-xs truncate"
          >
            <option value="All">All Categories</option>
            {cats.map(cat => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>

          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="bg-[#161b22] border border-darkBorder rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#58a6ff] text-textMain"
          >
            <option value="All">All Narrative Types</option>
            {narrativeTypes.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        </div>

        {/* Virtualized Table Grid */}
        <div className="flex-1 border border-darkBorder rounded-xl bg-[#161b22]/30 overflow-hidden flex flex-col">
          {/* Table Headers */}
          <div className="grid grid-cols-12 gap-4 bg-[#111622] px-4 py-3 border-b border-darkBorder text-xs uppercase font-bold tracking-wider text-textMuted text-left select-none">
            <div className="col-span-1">ID</div>
            <div className="col-span-4">Title</div>
            <div className="col-span-2">Source</div>
            <div className="col-span-1">Date</div>
            <div className="col-span-3">Category</div>
            <div className="col-span-1 text-center">Stream</div>
          </div>

          {/* Table Body */}
          <div className="flex-1 overflow-y-auto relative" ref={parentRef}>
            {loading ? (
              <div className="h-full flex items-center justify-center text-sm text-textMuted">
                Loading academic document indices...
              </div>
            ) : filteredDocs.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-textMuted">
                No matching document logs found.
              </div>
            ) : (
              <div
                style={{
                  height: `${rowVirtualizer.getTotalSize()}px`,
                  width: "100%",
                  position: "relative",
                }}
              >
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const doc = filteredDocs[virtualRow.index];
                  const isSelected = selectedDoc?.doc_id === doc.doc_id;
                  return (
                    <div
                      key={virtualRow.key}
                      onClick={() => setSelectedDoc(doc)}
                      className={`absolute left-0 w-full grid grid-cols-12 gap-4 px-4 items-center border-b border-darkBorder/50 hover:bg-[#1f242c]/50 cursor-pointer text-xs select-none transition-colors ${
                        isSelected ? "bg-[#1f242c] border-l-2 border-l-[#58a6ff]" : ""
                      }`}
                      style={{
                        top: 0,
                        height: `${virtualRow.size}px`,
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                    >
                      <div className="col-span-1 font-bold text-[#58a6ff]">{doc.doc_id}</div>
                      <div className="col-span-4 truncate font-medium text-textMain" title={doc.title}>
                        {doc.title}
                      </div>
                      <div className="col-span-2 truncate text-textMuted" title={doc.source_platform}>
                        {doc.source_platform}
                      </div>
                      <div className="col-span-1 text-textMuted">{doc.original_date || "-"}</div>
                      <div className="col-span-3 truncate text-textMuted" title={doc.fraud_category}>
                        {doc.fraud_category}
                      </div>
                      <div className="col-span-1 text-center">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            doc.stream === "A"
                              ? "bg-[#bc8cff]/10 text-[#bc8cff] border border-[#bc8cff]/20"
                              : "bg-[#ff7b72]/10 text-[#ff7b72] border border-[#ff7b72]/20"
                          }`}
                        >
                          {doc.stream}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Slide-out Drawer */}
      <div
        className={`fixed inset-y-0 right-0 w-full md:w-[600px] bg-[#111622] border-l border-darkBorder shadow-2xl z-50 flex flex-col transition-transform duration-300 transform ${
          selectedDoc ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {selectedDoc && (
          <>
            {/* Drawer Header */}
            <div className="p-4 border-b border-darkBorder flex items-center justify-between bg-[#161b22]">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold px-2 py-0.5 rounded bg-[#58a6ff]/10 text-[#58a6ff] border border-[#58a6ff]/20">
                  {selectedDoc.doc_id}
                </span>
                <span className="text-xs text-textMuted uppercase font-semibold">Metadata View</span>
              </div>
              <button
                onClick={() => setSelectedDoc(null)}
                className="text-textMuted hover:text-[#ff7b72] p-1 rounded hover:bg-[#1f242c] transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Drawer Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Title */}
              <div>
                <h2 className="text-lg font-bold text-textMain leading-tight">{selectedDoc.title}</h2>
              </div>

              {/* Metadata Cards */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-[#161b22] border border-darkBorder rounded-lg p-3 flex items-center gap-3">
                  <FileText size={18} className="text-[#bc8cff]" />
                  <div>
                    <span className="text-[10px] text-textMuted uppercase block">Source Platform</span>
                    <span className="text-xs font-bold text-textMain truncate block max-w-[180px]">
                      {selectedDoc.source_platform || "Unknown"}
                    </span>
                  </div>
                </div>
                <div className="bg-[#161b22] border border-darkBorder rounded-lg p-3 flex items-center gap-3">
                  <Calendar size={18} className="text-[#7ee787]" />
                  <div>
                    <span className="text-[10px] text-textMuted uppercase block">Original Date</span>
                    <span className="text-xs font-bold text-textMain">{selectedDoc.original_date || "Unknown"}</span>
                  </div>
                </div>
                <div className="bg-[#161b22] border border-darkBorder rounded-lg p-3 flex items-center gap-3">
                  <Tag size={18} className="text-[#58a6ff]" />
                  <div>
                    <span className="text-[10px] text-textMuted uppercase block">Category</span>
                    <span className="text-xs font-bold text-textMain truncate block max-w-[180px]" title={selectedDoc.fraud_category}>
                      {selectedDoc.fraud_category || "Unknown"}
                    </span>
                  </div>
                </div>
                <div className="bg-[#161b22] border border-darkBorder rounded-lg p-3 flex items-center gap-3">
                  <MapPin size={18} className="text-[#ff7b72]" />
                  <div>
                    <span className="text-[10px] text-textMuted uppercase block">Type / Schema</span>
                    <span className="text-xs font-bold text-textMain truncate block max-w-[180px]">
                      {selectedDoc.narrative_type || "Unknown"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Document Text */}
              <div>
                <h3 className="text-sm font-semibold text-[#58a6ff] mb-2">Raw Document Text</h3>
                {selectedDoc.stream === "A" ? (
                  loadingText ? (
                    <div className="text-xs text-textMuted animate-pulse py-8 text-center bg-[#0b0f17] rounded-lg border border-darkBorder">
                      Loading raw document txt file...
                    </div>
                  ) : (
                    <pre className="bg-[#0b0f17] border border-darkBorder rounded-lg p-4 text-xs font-mono whitespace-pre-wrap overflow-y-auto max-h-96 leading-relaxed select-text text-textMain">
                      {docText}
                    </pre>
                  )
                ) : (
                  <div className="bg-[#0b0f17] border border-darkBorder rounded-lg p-4 text-xs leading-relaxed text-textMain">
                    <p className="font-semibold text-textMuted mb-2">Government Stats Document Row Content:</p>
                    <div className="space-y-1">
                      <div><b>Title:</b> {selectedDoc.title}</div>
                      <div><b>Category:</b> {selectedDoc.fraud_category}</div>
                      <div><b>Organisation:</b> {selectedDoc.source_platform}</div>
                      <div><b>Date/Year:</b> {selectedDoc.original_date}</div>
                      <div><b>Data Type:</b> {selectedDoc.narrative_type}</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
