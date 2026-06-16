import React, { useState, useEffect } from "react";
import axios from "axios";
import Sidebar from "./components/Sidebar";
import Chat from "./pages/Chat";
import Insights from "./pages/Insights";
import Explorer from "./pages/Explorer";
import Submit from "./pages/Submit";
import GioiaAnalysis from "./pages/GioiaAnalysis";

export default function App() {
  const [currentPage, setCurrentPage] = useState("submit");
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [stats, setStats] = useState({
    total_document_count: 0,
    stream_breakdown: { "Stream A": 0, "Stream B": 0 },
    top_5_fraud_categories: {},
    date_range: { start_year: 2013, end_year: 2026 }
  });
  const [allDocs, setAllDocs] = useState([]);
  const [cats, setCats] = useState([]);
  const [platforms, setPlatforms] = useState([]);
  const [narrativeTypes, setNarrativeTypes] = useState([]);

  // Fetch live stats from API
  const fetchStats = async () => {
    try {
      const res = await axios.get("/api/stats");
      setStats(res.data);
    } catch (err) {
      console.error("Failed to fetch statistics:", err);
    }
  };

  useEffect(() => {
    fetchStats();
    
    // Fetch all document records (cache on client side for explorer virtual list and chart breakdowns)
    const loadAllDocs = async () => {
      try {
        const response = await axios.get("/api/documents?page=1&page_size=20000");
        const docs = response.data.documents || [];
        setAllDocs(docs);
        
        // Dynamically compute unique lists for filter selectors
        const uniqueCats = sortedUnique(docs.map((d) => d.fraud_category));
        const uniquePlats = sortedUnique(docs.map((d) => d.source_platform));
        const uniqueTypes = sortedUnique(docs.map((d) => d.narrative_type));
        
        // If empty, fall back to standard hardcoded lists
        setCats(uniqueCats.length > 0 ? uniqueCats : [
          "General Cybercrime / Cyber Fraud Terms",
          "UPI and Digital Payment Fraud",
          "OTP and Authentication Fraud",
          "Digital Arrest Scam",
          "Phishing, Vishing, and Smishing",
          "Online Lending and Loan App Fraud",
          "Investment and Trading Fraud",
          "Identity Theft and Data Breach",
          "Social Engineering and Romance/Sextortion",
          "E-Commerce and Delivery Fraud",
          "Ransomware and Malware",
          "Emerging and Miscellaneous Fraud Types",
          "Unknown"
        ]);
        setPlatforms(uniquePlats.length > 0 ? uniquePlats : ["The Print", "Cyberportal", "NCRB", "CERT-In", "RBI"]);
        setNarrativeTypes(uniqueTypes.length > 0 ? uniqueTypes : ["VICTIM", "NEWS", "OFFICIAL", "STATISTICS"]);
      } catch (error) {
        console.error("Failed to load documents:", error);
      }
    };
    
    loadAllDocs();
  }, []);

  const sortedUnique = (arr) => {
    return Array.from(new Set(arr.filter(Boolean))).sort();
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-darkBg text-textMain">
      {/* Sidebar Layout Navigation */}
      <Sidebar
        currentPage={currentPage}
        setCurrentPage={setCurrentPage}
        docCount={stats.total_document_count}
        isCollapsed={isCollapsed}
        setIsCollapsed={setIsCollapsed}
      />

      {/* Main Panel Viewport */}
      <main className="flex-1 h-screen overflow-hidden relative">
        {currentPage === "submit" && (
          <Submit
            cats={cats}
            refreshStats={fetchStats}
          />
        )}
        {currentPage === "gioia" && (
          <GioiaAnalysis
            cats={cats}
          />
        )}
      </main>
    </div>
  );
}
