import React, { useState } from "react";
import { MessageSquare, BarChart2, Folder, PlusCircle, ChevronLeft, ChevronRight, Shield, Beaker } from "lucide-react";

export default function Sidebar({ currentPage, setCurrentPage, docCount, isCollapsed, setIsCollapsed }) {
  const navItems = [
    { id: "submit", name: "Submit Experience", icon: PlusCircle },
    { id: "gioia", name: "Gioia Analysis", icon: Beaker },
  ];

  return (
    <div
      className={`h-screen bg-[#111622] border-r border-[#21262d] flex flex-col justify-between transition-all duration-300 ${
        isCollapsed ? "w-16" : "w-64"
      }`}
    >
      <div>
        {/* Header Logo */}
        <div className="p-4 border-b border-[#21262d] flex items-center justify-between">
          <div className="flex items-center gap-2 overflow-hidden">
            <Shield className="text-[#58a6ff] shrink-0" size={24} />
            {!isCollapsed && (
              <span className="font-bold text-lg bg-gradient-to-r from-[#58a6ff] to-[#bc8cff] bg-clip-text text-transparent whitespace-nowrap">
                CyberLens
              </span>
            )}
          </div>
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="text-[#8b949e] hover:text-[#58a6ff] p-1 rounded hover:bg-[#161b22] transition-colors"
          >
            {isCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="mt-4 px-2 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentPage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setCurrentPage(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                  isActive
                    ? "bg-[#161b22] text-[#58a6ff] border border-[#21262d]"
                    : "text-[#8b949e] hover:bg-[#161b22]/50 hover:text-[#c9d1d9]"
                }`}
              >
                <Icon size={18} className={isActive ? "text-[#58a6ff]" : "text-[#8b949e]"} />
                {!isCollapsed && <span className="truncate">{item.name}</span>}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-[#21262d] text-center">
        {!isCollapsed ? (
          <div className="bg-[#161b22] border border-[#21262d] rounded-lg p-2 flex flex-col items-center">
            <span className="text-xs text-[#8b949e] uppercase tracking-wider font-semibold">
              Indexed Documents
            </span>
            <span className="text-sm font-bold text-[#10b981] mt-0.5">
              🟢 {docCount.toLocaleString()}
            </span>
          </div>
        ) : (
          <span className="text-xs font-bold text-[#10b981]" title={`${docCount} documents indexed`}>
            🟢
          </span>
        )}
      </div>
    </div>
  );
}
