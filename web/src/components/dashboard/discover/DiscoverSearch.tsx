"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams, usePathname, useRouter } from "next/navigation";
import { Search } from "lucide-react";
import type { DiscoverSort } from "@/lib/dashboard/types";
import SortMenu from "./SortMenu";

interface DiscoverSearchProps {
  totalCount: number;
}

const SORT_OPTIONS: { value: DiscoverSort; label: string }[] = [
  { value: "relevance", label: "Relevance" },
  { value: "title", label: "Title" },
  { value: "popularity", label: "Most popular" },
];

const DiscoverSearch = ({ totalCount }: DiscoverSearchProps) => {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const [inputValue, setInputValue] = useState(searchParams.get("q") ?? "");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const currentSort = (searchParams.get("sort") as DiscoverSort) ?? "relevance";

  // Clean up debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const updateParam = (key: string, value: string | null) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInputValue(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateParam("q", value || null);
    }, 300);
  };

  return (
    <div className="flex gap-3 items-center">
      {/* Search input */}
      <div className="relative flex-1">
        <Search
          size={18}
          className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink/40 pointer-events-none"
        />
        <input
          type="text"
          value={inputValue}
          onChange={handleSearchChange}
          placeholder={`Search ${totalCount.toLocaleString()} Arabic texts…`}
          className="w-full bg-parchment-warm border border-ink/10 rounded-xl pl-11 pr-4 py-3 text-ink placeholder:text-ink/40 text-sm focus:outline-none focus:border-ink/25 transition-colors"
        />
      </div>

      {/* Sort control */}
      <SortMenu
        value={currentSort}
        options={SORT_OPTIONS}
        onChange={(v) => updateParam("sort", v === "relevance" ? null : v)}
      />
    </div>
  );
};

export default DiscoverSearch;
