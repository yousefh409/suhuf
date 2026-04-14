"use client";

import { useRef, useEffect, useCallback } from "react";
import {
  motion,
  useMotionValue,
  useSpring,
  useTransform,
  useScroll,
} from "motion/react";

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

/* ---------- 3D Tilt wrapper (desktop only) ---------- */
function TiltDevice({
  children,
  className,
  style,
  parallaxY,
  delay = 0,
  idleSpeed = 0.7,
  idleRadius = 0.5,
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  parallaxY?: import("motion/react").MotionValue<number>;
  delay?: number;
  /** Speed of the idle orbit in radians/sec (default 0.4) */
  idleSpeed?: number;
  /** How far the idle orbit reaches, 0-0.5 (default 0.5) */
  idleRadius?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const hovering = useRef(false);
  const rafId = useRef<number>(0);

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const tiltX = useSpring(useTransform(mouseY, [-0.5, 0.5], [6, -6]), {
    stiffness: 200,
    damping: 30,
  });
  const tiltY = useSpring(useTransform(mouseX, [-0.5, 0.5], [-6, 6]), {
    stiffness: 200,
    damping: 30,
  });

  /* Idle orbit: gently rotate when cursor isn't on the device */
  const startIdle = useCallback(() => {
    let start: number | null = null;
    function tick(ts: number) {
      if (hovering.current) return;
      if (start === null) start = ts;
      const t = ((ts - start) / 1000) * idleSpeed;
      mouseX.set(Math.sin(t) * idleRadius);
      mouseY.set(Math.cos(t * 0.7) * idleRadius);
      rafId.current = requestAnimationFrame(tick);
    }
    rafId.current = requestAnimationFrame(tick);
  }, [idleSpeed, idleRadius, mouseX, mouseY]);

  useEffect(() => {
    startIdle();
    return () => cancelAnimationFrame(rafId.current);
  }, [startIdle]);

  function handleMouse(e: React.MouseEvent) {
    hovering.current = true;
    cancelAnimationFrame(rafId.current);
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    mouseX.set((e.clientX - rect.left) / rect.width - 0.5);
    mouseY.set((e.clientY - rect.top) / rect.height - 0.5);
  }

  function handleLeave() {
    hovering.current = false;
    startIdle();
  }

  /* Parallax drives y; entrance uses only opacity + scale so they don't fight */
  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMouse}
      onMouseLeave={handleLeave}
      initial={{ opacity: 0, scale: 0.92 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.9, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
      style={{
        ...style,
        rotateX: tiltX,
        rotateY: tiltY,
        y: parallaxY,
        transformStyle: "preserve-3d",
      }}
    >
      {children}
    </motion.div>
  );
}

/* ---------- Device Chrome: iPad Frame ---------- */
function IPadFrame({ children, screenHeight }: { children: React.ReactNode; screenHeight: number }) {
  return (
    <div className="relative">
      {/* Front camera */}
      <div
        className="absolute top-[6px] left-1/2 -translate-x-1/2 w-[6px] h-[6px] rounded-full z-10"
        style={{ background: "radial-gradient(circle, #3a3a3c 30%, #1d1d1f 100%)" }}
      />
      {/* Screen with inner shadow */}
      <div
        className="rounded-[16px] overflow-hidden bg-white relative"
        style={{ height: screenHeight }}
      >
        {children}
        {/* Screen glare */}
        <div
          className="pointer-events-none absolute inset-0 rounded-[16px]"
          style={{
            background: "linear-gradient(135deg, rgba(255,255,255,0.12) 0%, transparent 50%)",
          }}
        />
      </div>
    </div>
  );
}

/* ---------- Device Chrome: iPhone Frame ---------- */
function IPhoneFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative w-full h-full">
      {/* Dynamic Island */}
      <div
        className="absolute top-[8px] left-1/2 -translate-x-1/2 w-[72px] h-[20px] rounded-full bg-black z-20"
      />
      {/* Screen */}
      <div className="rounded-[32px] overflow-hidden bg-white w-full h-full relative">
        {children}
        {/* Screen glare */}
        <div
          className="pointer-events-none absolute inset-0 rounded-[32px]"
          style={{
            background: "linear-gradient(135deg, rgba(255,255,255,0.10) 0%, transparent 45%)",
          }}
        />
      </div>
      {/* Home indicator */}
      <div className="absolute bottom-[6px] left-1/2 -translate-x-1/2 w-[100px] h-[4px] rounded-full bg-black/20 z-20" />
    </div>
  );
}

/* ---------- Main Component ---------- */
export default function LibraryTeacher() {
  const sectionRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "end start"],
  });

  // Devices float gently as user scrolls
  const ipadY = useTransform(scrollYProgress, [0, 1], [60, -30]);
  const iphoneY = useTransform(scrollYProgress, [0, 1], [90, -20]);

  return (
    <section
      ref={sectionRef}
      className="w-full flex flex-col items-center px-6 md:px-[60px] pt-16 md:pt-[100px] pb-10 gap-10 md:gap-14 overflow-hidden"
      style={{ perspective: 1200 }}
    >
      {/* Text Area */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.5 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="flex flex-col items-center gap-4 max-w-[680px] text-center"
      >
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
      </motion.div>

      {/* Device Stack — Desktop */}
      <div className="relative w-full max-w-[900px] h-[740px] hidden md:block" style={{ perspective: 1200 }}>
        {/* iPad Device */}
        <TiltDevice
          parallaxY={ipadY}
          className="absolute left-[40px] top-[20px] w-[620px] rounded-[24px] p-[10px]"
          style={{
            backgroundImage: "linear-gradient(in oklab 160deg, oklab(46% -.0007 0.011) 0%, oklab(38% .0002 0.009) 100%)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -1px 0 rgba(0,0,0,0.2), 0 30px 80px rgba(0,0,0,0.25), 0 8px 24px rgba(0,0,0,0.15)",
            rotate: "-6deg",
          }}
        >
          {/* Side button accents */}
          <div className="absolute -right-[2px] top-[60px] w-[3px] h-[30px] rounded-r-sm bg-[#2a2a2c]" />
          <div className="absolute -right-[2px] top-[100px] w-[3px] h-[30px] rounded-r-sm bg-[#2a2a2c]" />
          <div className="absolute -left-[2px] top-[80px] w-[3px] h-[50px] rounded-l-sm bg-[#2a2a2c]" />
          <IPadFrame screenHeight={520}>
            <IPadScreen />
          </IPadFrame>
        </TiltDevice>

        {/* iPhone Device */}
        <TiltDevice
          parallaxY={iphoneY}
          delay={0.15}
          className="absolute right-[30px] top-[50px] w-[290px] h-[600px] rounded-[44px] p-[10px]"
          style={{
            backgroundImage: "linear-gradient(in oklab 160deg, oklab(32% -.0001 0.005) 0%, oklab(24% .0004 0.004) 100%)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,0.1), inset 0 -1px 0 rgba(0,0,0,0.3), 0 40px 100px rgba(0,0,0,0.4), 0 10px 30px rgba(0,0,0,0.25)",
            rotate: "6deg",
          }}
        >
          {/* Side buttons */}
          <div className="absolute -right-[2px] top-[120px] w-[3px] h-[40px] rounded-r-sm bg-[#1a1a1c]" />
          <div className="absolute -left-[2px] top-[90px] w-[3px] h-[24px] rounded-l-sm bg-[#1a1a1c]" />
          <div className="absolute -left-[2px] top-[125px] w-[3px] h-[40px] rounded-l-sm bg-[#1a1a1c]" />
          <div className="absolute -left-[2px] top-[175px] w-[3px] h-[40px] rounded-l-sm bg-[#1a1a1c]" />
          <IPhoneFrame>
            <IPhoneScreen />
          </IPhoneFrame>
        </TiltDevice>
      </div>

      {/* Device Stack — Mobile (overlapping like desktop) */}
      <div className="relative w-full max-w-[400px] mx-auto md:hidden" style={{ height: 520, perspective: 1200 }}>
        {/* iPad Device — back layer */}
        <TiltDevice
          className="absolute left-0 top-0 w-[300px] rounded-[18px] p-[6px]"
          style={{
            backgroundImage: "linear-gradient(in oklab 160deg, oklab(46% -.0007 0.011) 0%, oklab(38% .0002 0.009) 100%)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,0.08), 0 16px 48px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.1)",
            rotate: "-4deg",
            transformOrigin: "0% 0%",
          }}
        >
          {/* Camera dot */}
          <div
            className="absolute top-[4px] left-1/2 -translate-x-1/2 w-[4px] h-[4px] rounded-full z-10"
            style={{ background: "radial-gradient(circle, #3a3a3c 30%, #1d1d1f 100%)" }}
          />
          {/* Side buttons */}
          <div className="absolute -right-[1.5px] top-[40px] w-[2px] h-[20px] rounded-r-sm bg-[#2a2a2c]" />
          <div className="absolute -left-[1.5px] top-[50px] w-[2px] h-[32px] rounded-l-sm bg-[#2a2a2c]" />
          <div className="rounded-[12px] overflow-hidden bg-white relative" style={{ height: 380 }}>
            <IPadScreen />
            <div
              className="pointer-events-none absolute inset-0 rounded-[12px]"
              style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.1) 0%, transparent 50%)" }}
            />
          </div>
        </TiltDevice>

        {/* iPhone Device — front layer, overlapping */}
        <TiltDevice
          delay={0.12}
          className="absolute right-0 top-[30px] w-[175px] h-[370px] rounded-[30px] p-[6px] z-10"
          style={{
            backgroundImage: "linear-gradient(in oklab 160deg, oklab(32% -.0001 0.005) 0%, oklab(24% .0004 0.004) 100%)",
            boxShadow:
              "inset 0 1px 0 rgba(255,255,255,0.1), 0 20px 60px rgba(0,0,0,0.35), 0 6px 18px rgba(0,0,0,0.2)",
            rotate: "4deg",
            transformOrigin: "0% 0%",
          }}
        >
          {/* Dynamic Island */}
          <div className="absolute top-[8px] left-1/2 -translate-x-1/2 w-[44px] h-[12px] rounded-full bg-black z-20" />
          {/* Side buttons */}
          <div className="absolute -right-[1.5px] top-[70px] w-[2px] h-[24px] rounded-r-sm bg-[#1a1a1c]" />
          <div className="absolute -left-[1.5px] top-[55px] w-[2px] h-[16px] rounded-l-sm bg-[#1a1a1c]" />
          <div className="absolute -left-[1.5px] top-[78px] w-[2px] h-[24px] rounded-l-sm bg-[#1a1a1c]" />
          <div className="rounded-[24px] overflow-hidden bg-white w-full h-full relative">
            <IPhoneScreen />
            <div
              className="pointer-events-none absolute inset-0 rounded-[24px]"
              style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.08) 0%, transparent 45%)" }}
            />
          </div>
          {/* Home indicator */}
          <div className="absolute bottom-[4px] left-1/2 -translate-x-1/2 w-[60px] h-[3px] rounded-full bg-black/20 z-20" />
        </TiltDevice>
      </div>
    </section>
  );
}
