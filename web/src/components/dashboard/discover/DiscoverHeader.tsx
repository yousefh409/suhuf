import Link from "next/link";
import { ChevronLeft } from "lucide-react";

const DiscoverHeader = () => {
  return (
    <div className="relative flex items-center py-4">
      {/* Back link — left side */}
      <Link
        href="/dashboard"
        className="flex items-center gap-0.5 text-sm text-ink/60 hover:text-ink transition-colors z-10 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/25"
      >
        <ChevronLeft size={16} />
        Library
      </Link>

      {/* Centered title — absolute so it ignores back-link width */}
      <h1 className="absolute inset-x-0 text-center font-serif text-2xl text-ink pointer-events-none">
        Discover
      </h1>
    </div>
  );
};

export default DiscoverHeader;
