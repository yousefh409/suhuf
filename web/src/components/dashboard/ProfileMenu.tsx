"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Settings, LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { usePreferences } from "@/components/preferences/PreferencesProvider";
import { THEMES, type Theme } from "@/lib/preferences/types";

const MENU_ID = "profile-menu";

const THEME_COLORS: Record<Theme, string> = {
  paper: "#F5EEE4",
  sepia: "#E8D6B3",
  night: "#14110D",
};

interface ProfileMenuProps {
  email?: string;
  initials?: string;
}

const ProfileMenu = ({ email, initials = "?" }: ProfileMenuProps) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLElement | null)[]>([]);
  const router = useRouter();
  const { prefs, setPref } = usePreferences();

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

  // Focus first item when menu opens
  useEffect(() => {
    if (!open) return;
    const items = itemRefs.current.filter(Boolean) as HTMLElement[];
    items[0]?.focus();
  }, [open]);

  const handleMenuKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const items = itemRefs.current.filter(Boolean) as HTMLElement[];
    if (items.length === 0) return;
    const currentIndex = items.indexOf(document.activeElement as HTMLElement);
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

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  async function handleSignOut() {
    close();
    await createClient().auth.signOut();
    router.push("/login");
    router.refresh();
  }

  // Item refs: 0=settings link, 1=sign out btn (skip theme swatches — not focusable menu items)
  let itemIdx = 0;

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label="Account menu"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? MENU_ID : undefined}
        className="w-10 h-10 flex items-center justify-center rounded-full bg-cta-dark text-parchment-warm font-sans text-sm font-medium select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/60 transition-opacity hover:opacity-90"
      >
        {initials}
      </button>

      {open && (
        <div
          id={MENU_ID}
          role="menu"
          onKeyDown={handleMenuKeyDown}
          className="absolute right-0 mt-2 z-30 min-w-56 bg-parchment-warm border border-ink/10 rounded-xl shadow-lg overflow-hidden"
        >
          {/* Header */}
          <div className="px-4 py-3">
            <p className="text-[10px] tracking-wider uppercase text-ink/40 mb-0.5">
              Signed in
            </p>
            <p className="text-sm text-ink truncate">{email}</p>
          </div>

          <div className="border-t border-ink/8" />

          {/* Theme quick-switch */}
          <div className="px-4 py-3 flex items-center gap-3">
            <span className="text-xs text-ink/50">Theme</span>
            <div className="flex gap-1.5">
              {THEMES.map((theme) => {
                const isActive = prefs.theme === theme;
                return (
                  <button
                    key={theme}
                    type="button"
                    onClick={() => setPref("theme", theme)}
                    aria-label={`Switch to ${theme} theme`}
                    className={[
                      "rounded-full transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/25",
                      isActive ? "ring-2 ring-gold" : "ring-1 ring-ink/20 hover:ring-ink/40",
                    ].join(" ")}
                    style={{
                      width: 22,
                      height: 22,
                      background: THEME_COLORS[theme],
                    }}
                  />
                );
              })}
            </div>
          </div>

          <div className="border-t border-ink/8" />

          {/* Settings link */}
          <Link
            href="/settings"
            role="menuitem"
            ref={(el) => {
              itemRefs.current[itemIdx++] = el;
            }}
            onClick={close}
            className="flex items-center gap-2 px-4 py-2.5 text-sm text-ink hover:bg-ink/5 w-full focus-visible:bg-ink/5 focus-visible:outline-none"
          >
            <Settings size={15} className="shrink-0" />
            Settings
          </Link>

          {/* Sign out */}
          <button
            type="button"
            role="menuitem"
            ref={(el) => {
              itemRefs.current[itemIdx] = el;
            }}
            onClick={handleSignOut}
            className="flex items-center gap-2 px-4 py-2.5 text-sm text-ink hover:bg-ink/5 w-full focus-visible:bg-ink/5 focus-visible:outline-none"
          >
            <LogOut size={15} className="shrink-0" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
};

export default ProfileMenu;
