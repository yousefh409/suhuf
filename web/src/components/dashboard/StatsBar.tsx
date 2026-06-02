import type { FC } from "react";
import type { DashboardStats } from "@/lib/dashboard/types";

interface StatCardProps {
  label: string;
  value: string;
  unit?: string;
}

const StatCard: FC<StatCardProps> = ({ label, value, unit }) => (
  <div className="bg-parchment-warm rounded-2xl border border-ink/8 p-6 flex flex-col items-center gap-1">
    <span className="text-[11px] tracking-wider uppercase text-ink/50 font-sans">
      {label}
    </span>
    <div className="flex items-baseline gap-1">
      <span className="font-serif text-3xl text-ink">{value}</span>
      {unit && (
        <span className="text-sm text-ink/50 font-sans font-normal">{unit}</span>
      )}
    </div>
  </div>
);

function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${m}m`;
}

interface StatsBarProps {
  stats: DashboardStats;
}

const StatsBar: FC<StatsBarProps> = ({ stats }) => {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard label="Today" value={String(stats.pagesToday)} unit="pages" />
      <StatCard
        label="Words Learned"
        value={String(stats.wordsLearnedThisWeek)}
        unit="this week"
      />
      <StatCard label="Streak" value={String(stats.streakDays)} unit="days" />
      <StatCard label="Time Read" value={formatTime(stats.timeReadMinutes)} />
    </div>
  );
};

export default StatsBar;
