import type { FC } from "react";
import ProfileMenu from "@/components/dashboard/ProfileMenu";

interface DashboardHeaderProps {
  name?: string;
  userInitials?: string;
  email?: string;
}

const DashboardHeader: FC<DashboardHeaderProps> = ({
  name = "Reader",
  userInitials = "YH",
  email,
}) => {
  return (
    <div className="flex items-end justify-between">
      <div className="space-y-0.5">
        <p className="font-sans text-sm text-ink/50">Welcome back</p>
        <h1 className="font-serif text-4xl text-ink leading-tight">{name}</h1>
      </div>

      <div className="flex items-center gap-3">
        <ProfileMenu email={email} initials={userInitials} />
      </div>
    </div>
  );
};

export default DashboardHeader;
