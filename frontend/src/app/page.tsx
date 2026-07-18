"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { MessageSquare, LayoutDashboard, ArrowRight } from "lucide-react";

// Interactive Text Scrambler Component
function ScramblerText({ text }: { text: string }) {
  const [displayText, setDisplayText] = useState(text);
  const chars = "!<>-_\\/[]{}—=+*^?#_010101001";

  const triggerScramble = () => {
    let iteration = 0;
    const interval = setInterval(() => {
      setDisplayText(
        text
          .split("")
          .map((char, index) => {
            if (char === " ") return " ";
            if (index < iteration) {
              return text[index];
            }
            return chars[Math.floor(Math.random() * chars.length)];
          })
          .join("")
      );
      iteration += 1 / 2; // Decrypt speed modifier
      if (iteration >= text.length) {
        clearInterval(interval);
        setDisplayText(text);
      }
    }, 30); // Frame refresh interval
  };

  useEffect(() => {
    triggerScramble();
  }, [text]);

  return (
    <span 
      onMouseEnter={triggerScramble} 
      className="cursor-default select-none transition-colors duration-300 hover:text-indigo-300"
    >
      {displayText}
    </span>
  );
}

export default function Home() {
  return (
    <main className="min-h-[90vh] flex flex-col items-center justify-center px-4 sm:px-6 lg:px-8 relative overflow-hidden select-none">
      
      {/* Background Glowing Heatmaps */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.16)_0%,transparent_60%)] pointer-events-none filter blur-3xl" />
      <div className="absolute top-1/4 left-1/4 w-[400px] h-[400px] bg-[radial-gradient(circle_at_center,rgba(139,92,246,0.1)_0%,transparent_60%)] pointer-events-none filter blur-3xl" />
      
      {/* Grid Pattern overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#334155_1px,transparent_1px),linear-gradient(to_bottom,#334155_1px,transparent_1px)] bg-[size:4rem_4rem] opacity-[0.05] pointer-events-none" />

      {/* SVG ANIMATED DATA PIPELINE CIRCUITS */}
      <svg 
        className="absolute inset-0 w-full h-full pointer-events-none opacity-30 z-0" 
        viewBox="0 0 1000 800" 
        preserveAspectRatio="none" 
        fill="none" 
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="laserGrad1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366F1" stopOpacity="0" />
            <stop offset="50%" stopColor="#818CF8" stopOpacity="1" />
            <stop offset="100%" stopColor="#6366F1" stopOpacity="0" />
          </linearGradient>
        </defs>
        
        {/* Left Circuit Path */}
        <path d="M 80 0 L 80 220 L 260 380 L 260 550" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" />
        <path className="animate-laser" d="M 80 0 L 80 220 L 260 380 L 260 550" stroke="url(#laserGrad1)" strokeWidth="1.5" />

        {/* Right Circuit Path */}
        <path d="M 920 0 L 920 220 L 740 380 L 740 550" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" />
        <path className="animate-laser" d="M 920 0 L 920 220 L 740 380 L 740 550" stroke="url(#laserGrad1)" strokeWidth="1.5" />

        {/* Bottom Loop Connector */}
        <path d="M 120 720 L 320 570 L 680 570 L 880 720" stroke="#334155" strokeWidth="1" strokeDasharray="4 4" />
        <path className="animate-laser" d="M 120 720 L 320 570 L 680 570 L 880 720" stroke="url(#laserGrad1)" strokeWidth="1.5" />
      </svg>

      <div className="max-w-3xl w-full text-center space-y-12 z-10">
        
        {/* Animated Title & Subtitle Block */}
        <header className="space-y-4">

          {/* FlowZint Sentinel Title with slide-reveal and gradient shift */}
          <h1 className="font-display text-5xl sm:text-7xl font-bold tracking-tight text-white leading-none animate-reveal-up">
            <span className="bg-gradient-to-r from-white via-indigo-300 to-indigo-500 bg-clip-text text-transparent animate-gradient-shift">
              FlowZint Sentinel
            </span>
          </h1>

          {/* Subtitle with dynamic Scrambler decryption animation */}
          <div className="font-mono text-sm sm:text-base tracking-wider text-slate-400 min-h-[24px] animate-fade-in-delayed">
            <ScramblerText text="AI Support Intelligence Agent" />
          </div>

        </header>

        {/* Center Primary Action Buttons */}
        <section 
          aria-label="Navigation entry options"
          className="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-2xl mx-auto w-full pt-4 animate-cards-reveal"
        >
          
          {/* Link 1: Chat Support */}
          <Link
            href="/chat"
            id="link-customer-chat"
            className="relative group bg-[#1E293B]/50 hover:bg-[#1E293B]/80 border border-[#334155] hover:border-indigo-500 rounded-2xl p-6 transition-all duration-300 flex flex-col justify-between items-start h-40 overflow-hidden focus:outline-none focus:ring-2 focus:ring-indigo-500 hover:shadow-[0_0_30px_rgba(99,102,241,0.15)]"
            aria-label="Launch live chat support module"
          >
            {/* Hover Laser Scan Line Overlay */}
            <div className="absolute inset-0 w-full h-full overflow-hidden pointer-events-none rounded-2xl">
              <div className="absolute top-0 bottom-0 w-[3px] bg-gradient-to-r from-transparent via-indigo-400 to-transparent opacity-0 group-hover:opacity-100 animate-sweep" />
            </div>

            {/* Corner Tech Decor */}
            <span className="absolute top-0 right-0 w-3.5 h-3.5 border-t border-r border-[#334155] group-hover:border-indigo-400/60 rounded-tr-xl transition-all" />
            <span className="absolute bottom-0 left-0 w-3.5 h-3.5 border-b border-l border-[#334155] group-hover:border-indigo-400/60 rounded-bl-xl transition-all" />

            <div className="w-12 h-12 rounded-xl bg-[#0F172A] border border-[#334155] group-hover:border-indigo-500 flex items-center justify-center transition-all duration-300 group-hover:shadow-[0_0_15px_rgba(129,138,248,0.2)]">
              <MessageSquare className="w-6 h-6 text-indigo-400" />
            </div>

            <div className="w-full text-left">
              <h2 className="font-display font-bold text-base text-white tracking-wide flex items-center justify-between">
                <span>Chat Support</span>
                <ArrowRight className="w-4 h-4 text-slate-500 group-hover:translate-x-1 group-hover:text-indigo-400 transition-all duration-300" />
              </h2>
              <p className="text-xs text-slate-500 mt-1 font-sans">
                Access the RAG-powered payments assistant.
              </p>
            </div>
          </Link>

          {/* Link 2: Admin Dashboard */}
          <Link
            href="/admin"
            id="link-ops-hub"
            className="relative group bg-[#1E293B]/50 hover:bg-[#1E293B]/80 border border-[#334155] hover:border-indigo-500 rounded-2xl p-6 transition-all duration-300 flex flex-col justify-between items-start h-40 overflow-hidden focus:outline-none focus:ring-2 focus:ring-indigo-500 hover:shadow-[0_0_30px_rgba(99,102,241,0.15)]"
            aria-label="Launch admin management dashboard console"
          >
            {/* Hover Laser Scan Line Overlay */}
            <div className="absolute inset-0 w-full h-full overflow-hidden pointer-events-none rounded-2xl">
              <div className="absolute top-0 bottom-0 w-[3px] bg-gradient-to-r from-transparent via-indigo-400 to-transparent opacity-0 group-hover:opacity-100 animate-sweep" />
            </div>

            {/* Corner Tech Decor */}
            <span className="absolute top-0 right-0 w-3.5 h-3.5 border-t border-r border-[#334155] group-hover:border-indigo-400/60 rounded-tr-xl transition-all" />
            <span className="absolute bottom-0 left-0 w-3.5 h-3.5 border-b border-l border-[#334155] group-hover:border-indigo-400/60 rounded-bl-xl transition-all" />

            <div className="w-12 h-12 rounded-xl bg-[#0F172A] border border-[#334155] group-hover:border-indigo-500 flex items-center justify-center transition-all duration-300 group-hover:shadow-[0_0_15px_rgba(129,138,248,0.2)]">
              <LayoutDashboard className="w-6 h-6 text-indigo-400" />
            </div>

            <div className="w-full text-left">
              <h2 className="font-display font-bold text-base text-white tracking-wide flex items-center justify-between">
                <span>Admin Dashboard</span>
                <ArrowRight className="w-4 h-4 text-slate-500 group-hover:translate-x-1 group-hover:text-indigo-400 transition-all duration-300" />
              </h2>
              <p className="text-xs text-slate-500 mt-1 font-sans">
                Manage tickets, KB loop, and configurations.
              </p>
            </div>
          </Link>

        </section>

      </div>
    </main>
  );
}
