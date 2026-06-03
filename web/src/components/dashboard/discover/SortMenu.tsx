"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpDown, Check } from "lucide-react";
import type { DiscoverSort } from "@/lib/dashboard/types";

interface SortMenuProps {
  value: DiscoverSort;
  options: { value: DiscoverSort; label: string }[];
  onChange: (next: DiscoverSort) => void;
}

const MENU_ID = "discover-sort-menu";

const SortMenu = ({ value, options, onChange }: SortMenuProps) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (!open) return;

    const handleMouseDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  // Move focus into the menu (selected item, else first) when it opens.
  useEffect(() => {
    if (!open) return;
    const selectedIndex = options.findIndex((o) => o.value === value);
    itemRefs.current[selectedIndex >= 0 ? selectedIndex : 0]?.focus();
  }, [open, options, value]);

  const handleSelect = (next: DiscoverSort) => {
    onChange(next);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleMenuKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const items = itemRefs.current.filter(Boolean) as HTMLButtonElement[];
    if (items.length === 0) return;
    const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      items[(currentIndex + 1) % items.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      items[(currentIndex - 1 + items.length) % items.length]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      items[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      items[items.length - 1]?.focus();
    }
  };

  return (
    <div ref={containerRef} className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label="Sort"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? MENU_ID : undefined}
        className="flex items-center justify-center bg-parchment-warm border border-ink/10 rounded-xl p-3 text-ink/60 hover:text-ink/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/20 transition-colors"
      >
        <ArrowUpDown size={16} />
      </button>

      {open && (
        <div
          id={MENU_ID}
          role="menu"
          onKeyDown={handleMenuKeyDown}
          className="absolute right-0 mt-2 z-20 min-w-44 overflow-hidden bg-parchment-warm border border-ink/10 rounded-xl shadow-lg py-1"
        >
          {options.map((opt, i) => (
            <button
              key={opt.value}
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              type="button"
              role="menuitem"
              onClick={() => handleSelect(opt.value)}
              className="flex items-center justify-between w-full px-4 py-2.5 text-sm text-ink hover:bg-ink/5 focus-visible:bg-ink/5 focus-visible:outline-none transition-colors"
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
