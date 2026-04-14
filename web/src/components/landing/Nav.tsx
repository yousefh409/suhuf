"use client";

import { useState } from "react";

export default function Nav() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <nav className="sticky top-0 z-50 flex items-center justify-between w-full px-5 md:px-16 py-5 md:py-7 bg-parchment-light/90 backdrop-blur-md">
      <a href="/" className="font-serif italic text-[22px] text-ink/90">
        suhuf
      </a>

      {/* Desktop links */}
      <div className="hidden md:flex items-center gap-8">
        <a
          href="#waitlist"
          className="flex items-center rounded-full px-6 py-2.5 bg-ink text-white text-sm font-medium hover:bg-ink/90 transition-colors"
        >
          Get Early Access
        </a>
      </div>

      {/* Mobile hamburger */}
      <button
        className="md:hidden flex flex-col gap-1.5"
        onClick={() => setMenuOpen(!menuOpen)}
        aria-label="Toggle menu"
      >
        <span
          className={`w-5 h-0.5 bg-ink transition-transform ${menuOpen ? "rotate-45 translate-y-2" : ""}`}
        />
        <span
          className={`w-5 h-0.5 bg-ink transition-opacity ${menuOpen ? "opacity-0" : ""}`}
        />
        <span
          className={`w-5 h-0.5 bg-ink transition-transform ${menuOpen ? "-rotate-45 -translate-y-2" : ""}`}
        />
      </button>

      {/* Mobile menu */}
      {menuOpen && (
        <div className="absolute top-full left-0 right-0 bg-parchment-light p-6 flex flex-col gap-4 md:hidden border-t border-ink/5">
          <a
            href="#waitlist"
            className="flex items-center justify-center rounded-full px-6 py-2.5 bg-ink text-white text-sm font-medium"
          >
            Get Early Access
          </a>
        </div>
      )}
    </nav>
  );
}
