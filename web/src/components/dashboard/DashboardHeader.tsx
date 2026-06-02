import type { FC } from "react";
import { Search } from "lucide-react";

interface DashboardHeaderProps {
  userInitials?: string;
}

const DashboardHeader: FC<DashboardHeaderProps> = ({ userInitials = "YH" }) => {
  return (
    <div className="flex items-center justify-between">
      <h1 className="font-serif text-4xl text-ink">Library</h1>

      <div className="flex items-center gap-3">
        {/* Search button */}
        <button
          type="button"
          aria-label="Search"
          className="w-10 h-10 flex items-center justify-center rounded-full bg-parchment-warm border border-ink/10"
        >
          <Search size={18} className="text-ink/60" />
        </button>

        {/* Avatar */}
        <div className="w-10 h-10 flex items-center justify-center rounded-full bg-cta-dark text-parchment-warm font-sans text-sm font-medium select-none">
          {userInitials}
        </div>
      </div>
    </div>
  );
};

export default DashboardHeader;
