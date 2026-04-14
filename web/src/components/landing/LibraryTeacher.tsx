"use client";

/* ---------- iPad Screen: Library View ---------- */
function IPadScreen() {
  return (
    <div className="bg-white rounded-[16px] overflow-hidden w-full h-full flex flex-col">
      {/* Header */}
      <div className="px-5 pt-5 pb-3">
        <h3 className="font-serif text-[28px] text-ink">Library</h3>
      </div>

      {/* Stats Row */}
      <div className="px-5 flex gap-3">
        <div className="flex-1 border border-ink/10 rounded-xl px-4 py-3">
          <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-gold block mb-1">
            Today
          </span>
          <span className="text-ink text-[22px] font-semibold leading-tight">
            47 pages
          </span>
        </div>
        <div className="flex-1 border border-ink/10 rounded-xl px-4 py-3">
          <span className="text-[10px] uppercase tracking-[0.12em] font-semibold text-gold block mb-1">
            Words Learned
          </span>
          <span className="text-ink text-[22px] font-semibold leading-tight">
            128 this week
          </span>
        </div>
      </div>

      {/* Continue Reading */}
      <div className="px-5 pt-5 pb-2">
        <h4 className="font-serif text-[18px] text-ink">Continue Reading</h4>
      </div>

      {/* Book Cards */}
      <div className="px-5 flex flex-col gap-3 pb-4">
        <BookCard
          coverBg="#6B5B4F"
          arabicTitle="الآجرومية"
          title="Al-Ajrumiyyah"
          subtitle="Ibn Ajurrum · Nahw · Beginner"
          progress={0.35}
        />
        <BookCard
          coverBg="#2C3E50"
          arabicTitle="الأربعين"
          title="Al-Arba'in al-Nawawiyyah"
          subtitle="Imam Nawawi · Hadith"
        />
        <BookCard
          coverBg="#4A3162"
          arabicTitle="الأصول"
          title="Al-Usul min 'Ilm al-Usul"
          subtitle="Ibn Uthaymeen · Usul al-Fiqh"
        />
      </div>

      {/* Status Pills */}
      <div className="px-5 pb-4 flex gap-2 mt-auto">
        <StatusPill color="#22C55E" label="In Progress" count={5} />
        <StatusPill color="#D97706" label="Saved" count={18} />
        <StatusPill color="#44403C" label="Completed" count={7} />
      </div>
    </div>
  );
}

function BookCard({
  coverBg,
  arabicTitle,
  title,
  subtitle,
  progress,
}: {
  coverBg: string;
  arabicTitle: string;
  title: string;
  subtitle: string;
  progress?: number;
}) {
  return (
    <div className="flex items-center gap-3">
      {/* Cover Thumbnail */}
      <div
        className="w-[50px] h-[65px] rounded-lg flex items-center justify-center shrink-0"
        style={{ backgroundColor: coverBg }}
      >
        <span className="font-arabic text-white text-[14px] leading-tight text-center px-1">
          {arabicTitle}
        </span>
      </div>
      {/* Info */}
      <div className="flex flex-col min-w-0">
        <span className="text-ink text-[14px] font-medium truncate">{title}</span>
        <span className="text-ink/50 text-[12px] truncate">{subtitle}</span>
        {progress !== undefined && (
          <div className="w-full h-1 bg-ink/10 rounded-full mt-1.5">
            <div
              className="h-full bg-gold rounded-full"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function StatusPill({
  color,
  label,
  count,
}: {
  color: string;
  label: string;
  count: number;
}) {
  return (
    <div className="flex items-center gap-1.5 bg-ink/5 rounded-full px-3 py-1.5">
      <span
        className="w-2 h-2 rounded-full shrink-0"
        style={{ backgroundColor: color }}
      />
      <span className="text-ink/70 text-[11px] whitespace-nowrap">
        {label} {count}
      </span>
    </div>
  );
}

/* ---------- iPhone Screen: Word Detail ---------- */
function IPhoneScreen() {
  return (
    <div className="bg-white rounded-[32px] overflow-hidden w-full h-full flex flex-col">
      {/* Handle Bar */}
      <div className="flex justify-center pt-3 pb-2">
        <div className="w-10 h-1 rounded-full bg-ink/15" />
      </div>

      {/* Word Display */}
      <div className="flex flex-col items-center pt-4 pb-3 px-5">
        <span className="font-arabic text-[36px] text-ink leading-tight">
          طَرِيقٍ
        </span>
        <span className="text-ink/40 text-[14px] mt-1">ṭarīqin</span>
      </div>

      {/* Tab Bar */}
      <div className="flex px-5 border-b border-ink/10">
        <button className="px-4 py-2 text-[13px] text-ink/40">Translation</button>
        <button className="px-4 py-2 text-[13px] text-ink border-b-2 border-gold font-medium">
          I3rab
        </button>
      </div>

      {/* I3rab Content */}
      <div className="flex flex-col gap-4 px-5 pt-4 pb-4 overflow-y-auto flex-1">
        <IrabRow label="Type" arabic="اسم" english="noun" />
        <IrabRow label="Case" arabic="مجرور" english="genitive" />
        <IrabRow label="Role" arabic="مضاف إليه" english="second part of idafa" />
        <IrabRow
          label="Marker"
          arabic="كسرة مع تنوين"
          english="tanween kasra"
        />

        {/* Why This Case */}
        <div>
          <span className="text-[9px] uppercase tracking-[0.12em] font-semibold text-gold block mb-1.5">
            Why This Case?
          </span>
          <p className="text-ink/45 text-[12px] leading-[1.6]">
            In an{" "}
            <span className="font-arabic text-ink/60">إضافة</span>{" "}
            (idafa) construction, the second noun is always in the genitive case
            (majrur). Here, &quot;tariq&quot; is the mudaf ilayhi.
          </p>
        </div>
      </div>

      {/* Ask AI Button */}
      <div className="px-5 pb-5 pt-2">
        <div className="bg-dark text-parchment rounded-full px-5 py-2.5 flex items-center justify-center gap-2 text-[13px] font-medium">
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            className="shrink-0"
          >
            <path
              d="M8 0L9.5 6.5L16 8L9.5 9.5L8 16L6.5 9.5L0 8L6.5 6.5L8 0Z"
              fill="currentColor"
            />
          </svg>
          Ask AI
        </div>
      </div>
    </div>
  );
}

function IrabRow({
  label,
  arabic,
  english,
}: {
  label: string;
  arabic: string;
  english: string;
}) {
  return (
    <div>
      <span className="text-[9px] uppercase tracking-[0.12em] font-semibold text-gold block mb-1">
        {label}
      </span>
      <span className="font-arabic text-[18px] text-ink block leading-tight">
        {arabic}
      </span>
      <span className="text-ink/45 text-[12px]">{english}</span>
    </div>
  );
}

/* ---------- Main Component ---------- */
export default function LibraryTeacher() {
  return (
    <section className="w-full flex flex-col items-center px-6 md:px-[60px] pt-[100px] pb-10 gap-14 overflow-hidden">
      {/* Text Area */}
      <div className="flex flex-col items-center gap-4 max-w-[680px] text-center">
        <span className="text-[13px] uppercase tracking-[0.12em] font-semibold text-gold">
          Suhuf
        </span>
        <h2 className="font-serif text-[36px] md:text-[48px] text-ink leading-[1.15]">
          A library and teacher right at your fingertips.
        </h2>
        <p className="text-[#7A6E62] text-[17px] leading-[1.6] max-w-[680px]">
          Dozens of classical texts. Real-time pronunciation feedback. Grammar
          explained in plain English. All in one app.
        </p>
      </div>

      {/* Device Stack */}
      <div className="relative w-full max-w-[900px] h-[500px] md:h-[740px] hidden md:block">
        {/* iPad Device */}
        <div
          className="absolute left-[40px] top-[20px] w-[620px] rounded-[24px] p-2"
          style={{
            backgroundImage: "linear-gradient(in oklab 145deg, oklab(45.3% -.0007 0.011) 0%, oklab(40.2% .0002 0.009) 100%)",
            boxShadow:
              "#FFFFFF14 0px 1px 0px inset, #00000033 0px 30px 80px, #0000001A 0px 8px 24px",
            transform: "rotate(-6deg)",
            transformOrigin: "0% 0%",
          }}
        >
          <div className="rounded-[16px] overflow-hidden bg-white" style={{ height: 520 }}>
            <IPadScreen />
          </div>
        </div>

        {/* iPhone Device */}
        <div
          className="absolute right-[30px] top-[50px] w-[290px] h-[600px] rounded-[40px] p-2"
          style={{
            backgroundImage: "linear-gradient(in oklab 145deg, oklab(34.5% -.0001 0.005) 0%, oklab(29.7% .0004 0.004) 100%)",
            boxShadow:
              "#FFFFFF1A 0px 1px 0px inset, #00000059 0px 40px 100px, #00000033 0px 10px 30px",
            transform: "rotate(6deg)",
            transformOrigin: "0% 0%",
          }}
        >
          <IPhoneScreen />
        </div>
      </div>

      {/* Mobile fallback: show text only, devices hidden via hidden md:block above */}
    </section>
  );
}
