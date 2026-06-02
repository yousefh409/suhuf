"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Props = { mode: "reader" | "inspector" };

export function ModeToggle({ mode }: Props) {
  const pathname = usePathname();
  const other = mode === "reader" ? "inspector" : "reader";
  const target = pathname.replace(/^\/(reader|inspector)/, `/${other}`);

  const ActiveChip = (
    <span className="px-2 py-1 rounded bg-zinc-900 text-white">
      {mode === "reader" ? "Reader" : "Inspector"}
    </span>
  );
  const InactiveLink = (
    <Link
      href={target}
      className="px-2 py-1 rounded bg-zinc-100 text-zinc-600 hover:bg-zinc-200"
    >
      {mode === "reader" ? "Inspector" : "Reader"}
    </Link>
  );

  return (
    <div className="flex gap-1 text-xs font-mono">
      {/* Order: Reader first, Inspector second */}
      {mode === "reader" ? ActiveChip : InactiveLink}
      {mode === "inspector" ? ActiveChip : InactiveLink}
    </div>
  );
}
