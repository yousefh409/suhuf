import type { FC } from "react";

interface DashboardHeaderProps {
  name?: string;
  userInitials?: string;
}

const DashboardHeader: FC<DashboardHeaderProps> = ({
  name = "Reader",
  userInitials = "YH",
}) => {
  return (
    <div className="flex items-end justify-between">
      <div className="space-y-0.5">
        <p className="font-sans text-sm text-ink/50">Welcome back</p>
        <h1 className="font-serif text-4xl text-ink leading-tight">{name}</h1>
      </div>

      <div className="flex items-center gap-3">
        {/* Avatar */}
        <div className="w-10 h-10 flex items-center justify-center rounded-full bg-cta-dark text-parchment-warm font-sans text-sm font-medium select-none">
          {userInitials}
        </div>
      </div>
    </div>
  );
};

export default DashboardHeader;
