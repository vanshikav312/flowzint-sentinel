import type { Metadata } from "next";
import { Space_Grotesk, Plus_Jakarta_Sans, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
});

const plusJakartaSans = Plus_Jakarta_Sans({
  variable: "--font-plus-jakarta-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FlowZint Sentinel",
  description: "Self-healing AI support bot with hybrid RAG, confidence routing, incident detection, and self-learning.",
};

// Top nav is rendered server-side — active link highlighting is handled
// via a client wrapper, but the shell is static to avoid layout shift.
function TopNav() {
  return (
    <nav className="fixed top-0 w-full h-11 bg-[#0F172A] border-b border-[#334155] z-50">
      <div className="max-w-screen-xl mx-auto h-full px-4 flex items-center justify-between">
        <span className="text-[13px] select-none font-sans">
          <span className="text-slate-100 font-semibold tracking-wide">FlowZint</span>
          <span className="text-slate-700 mx-2">|</span>
          <span className="text-indigo-400 font-mono text-[11px] tracking-wider uppercase font-semibold">Sentinel Ops Hub</span>
        </span>
        <div className="flex font-sans">
          <Link
            href="/chat"
            className="text-[12px] px-3 py-2 text-slate-400 hover:text-slate-100 transition-colors font-medium"
          >
            Chat
          </Link>
          <Link
            href="/admin"
            className="text-[12px] px-3 py-2 text-slate-400 hover:text-slate-100 transition-colors font-medium"
          >
            Ops Hub
          </Link>
        </div>
      </div>
    </nav>
  );
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${plusJakartaSans.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="bg-[#0F172A] text-slate-100 min-h-screen flex flex-col font-sans">
        <TopNav />
        <div className="pt-11 flex flex-col flex-1">{children}</div>
      </body>
    </html>
  );
}
