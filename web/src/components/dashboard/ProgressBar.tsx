import type { FC } from "react";

interface ProgressBarProps {
  percent: number;
  showLabel?: boolean;
}

const ProgressBar: FC<ProgressBarProps> = ({ percent, showLabel = true }) => {
  const clamped = Math.min(100, Math.max(0, percent));

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 rounded-full bg-ink/8 h-[6px] overflow-hidden">
        <div
          className="h-full rounded-full bg-gold transition-all"
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showLabel && (
        <span className="shrink-0 text-xs text-ink/50">{Math.round(clamped)}%</span>
      )}
    </div>
  );
};

export default ProgressBar;
