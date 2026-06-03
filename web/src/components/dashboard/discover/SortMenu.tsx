"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpDown, Check } from "lucide-react";
import type { DiscoverSort } from "@/lib/dashboard/types";

interface SortMenuProps {
  value: DiscoverSort;
  options: { value: DiscoverSort; label: string }[];
  onChange: (v: DiscoverSort) => void;
}

const SortMenu = ({ value, options, onChange }: SortMenuProps) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const handleMouseDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const handleSelect = (v: DiscoverSort) => {
    onChange(v);
    setOpen(false);
  };

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label="Sort"
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center justify-center bg-parchment-warm border border-ink/10 rounded-xl p-3 text-ink/60 hover:text-ink/80 transition-colors"
      >
        <ArrowUpDown size={16} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 z-20 min-w-44 bg-parchment-warm border border-ink/10 rounded-xl shadow-lg py-1"
        >
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="menuitem"
              onClick={() => handleSelect(opt.value)}
              className="flex items-center justify-between w-full px-4 py-2.5 text-sm text-ink hover:bg-ink/5 rounded transition-colors"
            >
              <span className={value === opt.value ? "font-medium" : ""}>{opt.label}</span>
              {value === opt.value && <Check size={14} className="text-ink/60 shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default SortMenu;
