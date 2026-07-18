"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function TopNav() {
  const pathname = usePathname();

  const navLinks = [
    { label: "Chat", href: "/chat" },
    { label: "Ops Hub", href: "/admin" },
  ];

  return (
    <nav
      style={{ height: "44px" }}
      className="fixed top-0 w-full bg-[#0F172A] border-b border-[#334155] z-50"
    >
      <div className="max-w-screen-xl mx-auto h-full px-4 flex items-center justify-between">
        <span className="text-[13px]">
          <span className="text-slate-100 font-semibold">FlowZint</span>
          <span className="text-slate-600 mx-2">|</span>
          <span className="text-slate-400 font-normal">Sentinel Ops Hub</span>
        </span>
        <div className="flex gap-1">
          {navLinks.map((link) => {
            const isActive =
              pathname === link.href || pathname.startsWith(link.href + "/");
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`text-[12px] px-3 py-1 transition-colors ${
                  isActive
                    ? "text-slate-100 border-b-2 border-indigo-500"
                    : "text-slate-400 hover:text-slate-100"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
