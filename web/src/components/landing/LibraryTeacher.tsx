"use client";

import { useRef, useEffect, useCallback, useState } from "react";
import {
  motion,
  useMotionValue,
  useSpring,
  useTransform,
  useScroll,
} from "motion/react";

/* ═══════════════════════════════════════════════
   Shared sub-components
   ═══════════════════════════════════════════════ */

// Cover images sourced from Internet Archive's image service:
// https://archive.org/services/img/<identifier> — each is a real Arabic-edition cover.
const BOOKS = {
  ajrumiyyah: { bg: "#5C4A35", arabic: "الآجرومية", title: "Al-Ajrumiyyah", author: "Ibn Ajurrum", category: "Nahw · Beginner", pct: 42, image: "https://archive.org/services/img/ar113lang06" },
  arbain:     { bg: "#1C2B3A", arabic: "الأربعين", title: "Al-Arba'in al-Nawawiyyah", author: "Imam Nawawi", category: "Hadith", pct: 67, image: "https://archive.org/services/img/fahadfirozkhan_live" },
  qatr:       { bg: "#2D1F3D", arabic: "قطر الندى", title: "Qatr al-Nada", author: "Ibn Hisham", category: "Nahw", pct: 18, image: "https://archive.org/services/img/20210914_20210914_1126" },
  riyad:      { bg: "#3A2A1A", arabic: "رياض الصالحين", title: "Riyad al-Salihin", author: "Imam Nawawi", category: "Hadith", pct: 31, image: "https://archive.org/services/img/Riyad-Us-Saliheen-ARABIC.pdf" },
  bulugh:     { bg: "#4D4535", arabic: "بلوغ المرام", title: "Bulugh al-Maram", author: "Ibn Hajar", category: "Fiqh", pct: 8, image: "https://archive.org/services/img/0501BulooghAlQasim" },
} as const;

/* ═══════════════════════════════════════════════
   iPad Screen: Reading Session
   ═══════════════════════════════════════════════ */

function IPadScreen() {
  return (
    <div className="bg-[#FAF7F2] overflow-hidden w-full h-full flex flex-col">
      {/* Status Bar */}
      <div className="flex items-center justify-between px-5 pt-2 pb-0.5">
        <span className="text-[10px] font-semibold text-ink">9:41</span>
        <div className="flex items-center gap-1">
          <svg width="14" height="10" viewBox="0 0 18 12" fill="none">
            <rect x="0" y="7" width="3" height="5" rx="0.5" fill="#2A1F17" />
            <rect x="4" y="5" width="3" height="7" rx="0.5" fill="#2A1F17" />
            <rect x="8" y="3" width="3" height="9" rx="0.5" fill="#2A1F17" />
            <rect x="12" y="0" width="3" height="12" rx="0.5" fill="#2A1F17" />
          </svg>
          <svg width="12" height="10" viewBox="0 0 16 12" fill="none">
            <path d="M1 3.5C4 0.5 12 0.5 15 3.5" stroke="#2A1F17" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M3.5 6C5.5 4 10.5 4 12.5 6" stroke="#2A1F17" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="8" cy="9" r="1.5" fill="#2A1F17" />
          </svg>
          <svg width="18" height="9" viewBox="0 0 22 11" fill="none">
            <rect x="0.5" y="0.5" width="18" height="10" rx="2" stroke="#2A1F17" strokeOpacity="0.5" />
            <rect x="2" y="2" width="13" height="7" rx="1" fill="#2A1F17" />
            <rect x="19.5" y="3" width="2" height="5" rx="1" fill="#2A1F17" strokeOpacity="0.3" />
          </svg>
        </div>
      </div>

      {/* Nav Bar */}
      <div className="flex items-center justify-between px-4 h-[40px] shrink-0 border-b border-ink/6">
        <div className="flex items-center gap-1.5 min-w-[70px]">
          <svg width="7" height="12" viewBox="0 0 8 14" fill="none">
            <path d="M7 1L1 7L7 13" stroke="#B47D3A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="text-[12px] text-gold">Library</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-[12px] text-ink font-semibold leading-tight">Al-Da&apos; wal-Dawa&apos;</span>
          <span className="text-[9px] text-ink/40">Chapter 1 &middot; Al-Muqaddima</span>
        </div>
        <div className="flex items-center gap-2 min-w-[70px] justify-end">
          <svg width="14" height="14" viewBox="0 0 18 18" fill="none">
            <path d="M4 2H14V16L9 12.5L4 16V2Z" stroke="#2A1F17" strokeOpacity="0.3" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
          <div className="w-6 h-6 rounded-full bg-[#3A7D50] flex items-center justify-center">
            <svg width="10" height="10" viewBox="0 0 14 10" fill="none">
              <rect x="0" y="3" width="2" height="4" rx="1" fill="white" />
              <rect x="4" y="1" width="2" height="8" rx="1" fill="white" />
              <rect x="8" y="2" width="2" height="6" rx="1" fill="white" />
              <rect x="12" y="3" width="2" height="4" rx="1" fill="white" />
            </svg>
          </div>
        </div>
      </div>

      {/* Reading Content */}
      <div className="flex-1 overflow-hidden px-5 py-4 font-arabic text-right" dir="rtl">
        <p className="text-[13px] text-ink leading-[30px] mb-3">
          الحمد لله أما بعد فقد ثبت في صحيح البخاري من حديث أبي هريرة رضي الله عنه عن النبي صلى الله عليه وسلم أنه قال ما أنزل الله داء إلا أنزل له شفاء وفي صحيح مسلم من حديث جابر بن عبد الله قال قال رسول الله صلى الله عليه وسلم لكل داء دواء فإذا أصيب دواء الداء برأ بإذن الله عز وجل
        </p>
        <p className="text-[13px] text-ink leading-[30px] mb-3">
          فالقرآن هو الشفاء التام من جميع الأدواء القلبية والبدنية وأدواء الدنيا والآخرة وما كل أحد يؤهل ولا يوفق للاستشفاء به وكيف تقاوم الأدواء كلام رب الأرض والسماء الذي لو نزل على الجبال لصدعها فما من مرض من أمراض القلوب والأبدان إلا وفي القرآن سبيل الدلالة على دوائه وسببه والحمية منه لمن رزقه الله فهما في كتابه
        </p>
        <p className="text-[13px] text-ink leading-[30px]">
          وهذا الكتاب الذي بين يدينا من أجل الكتب وأنفعها لله در صاحبه ورحمه الله وأسكنه فسيح جناته وجمعنا به في دار كرامته مع النبيين والصديقين والشهداء والصالحين وحسن أولئك رفيقا وذلك فضل الله يؤتيه من يشاء والله ذو الفضل العظيم
        </p>
      </div>

      {/* Bottom Bar */}
      <div className="h-[34px] shrink-0 border-t border-ink/8 flex items-center justify-between px-4">
        <div className="flex items-center gap-1.5">
          <div className="w-[12px] h-[12px] rounded-sm border border-ink/20 flex items-center justify-center">
            <svg width="7" height="7" viewBox="0 0 8 8" fill="none">
              <path d="M1 4L3 6L7 2" stroke="#3A7D50" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span className="text-[10px] text-ink/60">Tashkeel</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-[5px] h-[5px] rounded-full bg-red-500" />
          <span className="text-[10px] text-ink/50">Recording</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-red-500 font-medium">2 errors</span>
          <div className="flex items-center gap-1 bg-ink text-white rounded-full px-2.5 py-0.5">
            <div className="w-[6px] h-[6px] rounded-sm bg-white" />
            <span className="text-[9px] font-medium">Stop</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ShelfPill({ color, label, count }: { color: string; label: string; count: number }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-[5px] h-[5px] rounded-full shrink-0" style={{ backgroundColor: color }} />
      <span className="text-ink/60 text-[10px] font-medium whitespace-nowrap">{label}</span>
      <span className="text-ink/35 text-[10px]">{count}</span>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   iPhone Screen: Mobile Library View
   ═══════════════════════════════════════════════ */

function IPhoneScreen() {
  return (
    <div className="bg-[#FAF7F2] overflow-hidden w-full h-full flex flex-col">
      {/* Status Bar */}
      <div className="flex items-center justify-between px-4 pt-8 pb-1">
        <span className="text-[10px] font-semibold text-ink">9:41</span>
        <div className="flex items-center gap-1">
          {/* Signal bars */}
          <svg width="14" height="10" viewBox="0 0 18 12" fill="none">
            <rect x="0" y="7" width="3" height="5" rx="0.5" fill="#2A1F17" />
            <rect x="4" y="5" width="3" height="7" rx="0.5" fill="#2A1F17" />
            <rect x="8" y="3" width="3" height="9" rx="0.5" fill="#2A1F17" />
            <rect x="12" y="0" width="3" height="12" rx="0.5" fill="#2A1F17" />
          </svg>
          {/* WiFi */}
          <svg width="12" height="10" viewBox="0 0 16 12" fill="none">
            <path d="M1 3.5C4 0.5 12 0.5 15 3.5" stroke="#2A1F17" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M3.5 6C5.5 4 10.5 4 12.5 6" stroke="#2A1F17" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="8" cy="9" r="1.5" fill="#2A1F17" />
          </svg>
          {/* Battery */}
          <svg width="18" height="9" viewBox="0 0 22 11" fill="none">
            <rect x="0.5" y="0.5" width="18" height="10" rx="2" stroke="#2A1F17" strokeOpacity="0.5" />
            <rect x="2" y="2" width="13" height="7" rx="1" fill="#2A1F17" />
            <rect x="19.5" y="3" width="2" height="5" rx="1" fill="#2A1F17" strokeOpacity="0.3" />
          </svg>
        </div>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between px-4 pb-2">
        <h3 className="font-serif text-[20px] text-ink leading-tight">Library</h3>
        <div className="flex items-center gap-2">
          <svg width="14" height="14" viewBox="0 0 18 18" fill="none">
            <circle cx="7.5" cy="7.5" r="5" stroke="#2A1F17" strokeOpacity="0.6" strokeWidth="1.5" />
            <path d="M11.5 11.5L15.5 15.5" stroke="#2A1F17" strokeOpacity="0.6" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <div className="w-[22px] h-[22px] rounded-full bg-ink flex items-center justify-center">
            <span className="text-[8px] text-white font-medium">YH</span>
          </div>
        </div>
      </div>

      {/* Stats 2x2 */}
      <div className="px-4 flex flex-col gap-1.5">
        <div className="flex gap-1.5">
          {([
            { label: "Today", value: "47", unit: "pages" },
            { label: "Words Learned", value: "128", unit: "this week" },
          ] as const).map((s) => (
            <div key={s.label} className="flex-1 border border-ink/[0.06] rounded-xl bg-white px-2.5 py-2 flex flex-col items-center gap-0.5">
              <span className="text-[7px] uppercase tracking-[0.06em] font-medium text-gold">{s.label}</span>
              <div className="flex items-baseline gap-0.5">
                <span className="text-ink text-[18px] font-bold leading-tight">{s.value}</span>
                <span className="text-[9px] text-gold font-medium">{s.unit}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-1.5">
          {([
            { label: "Streak", value: "12", unit: "days" },
            { label: "Time Read", value: "3h 24m", unit: "" },
          ] as { label: string; value: string; unit: string }[]).map((s) => (
            <div key={s.label} className="flex-1 border border-ink/[0.06] rounded-xl bg-white px-2.5 py-2 flex flex-col items-center gap-0.5">
              <span className="text-[7px] uppercase tracking-[0.06em] font-medium text-gold">{s.label}</span>
              <div className="flex items-baseline gap-0.5">
                <span className="text-ink text-[18px] font-bold leading-tight">{s.value}</span>
                {s.unit && <span className="text-[9px] text-gold font-medium">{s.unit}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Continue Reading */}
      <div className="flex items-center justify-between px-4 pt-3.5 pb-1">
        <h4 className="font-serif text-[14px] text-ink">Continue Reading</h4>
        <span className="text-[9px] text-ink/35">Last opened</span>
      </div>

      {/* Book Rows */}
      <div className="px-4 flex flex-col gap-1.5">
        <MobileBookRow book={BOOKS.ajrumiyyah} showResume />
        <MobileBookRow book={BOOKS.arbain} />
      </div>

      {/* Shelf Tabs */}
      <div className="flex items-center gap-3 px-4 pt-3 pb-1.5">
        <ShelfPill color="#B47D3A" label="In Progress" count={5} />
        <ShelfPill color="#D97706" label="Saved" count={18} />
      </div>

      {/* Book Shelf */}
      <div className="px-4 flex gap-1.5 overflow-hidden pb-2">
        {([BOOKS.ajrumiyyah, BOOKS.arbain, BOOKS.qatr] as const).map((book) => (
          <MobileShelfCard key={book.title} book={book} />
        ))}
      </div>

    </div>
  );
}

function MobileBookRow({
  book,
  showResume,
}: {
  book: (typeof BOOKS)[keyof typeof BOOKS];
  showResume?: boolean;
}) {
  return (
    <div
      className="flex items-center gap-2.5 rounded-xl bg-white border border-ink/[0.06] px-2.5 py-2"
      style={{ boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}
    >
      <div
        className="w-[36px] h-[46px] rounded-md shrink-0 overflow-hidden"
        style={{ backgroundColor: book.bg }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={book.image}
          alt=""
          loading="lazy"
          className="w-full h-full object-cover"
        />
      </div>
      <div className="flex flex-col min-w-0 flex-1">
        <span className="text-ink text-[11px] font-semibold truncate">{book.title}</span>
        <span className="text-ink/45 text-[9px] truncate">{book.author} · {book.category}</span>
        <div className="flex items-center gap-1.5 mt-0.5">
          <div className="flex-1 h-[2px] bg-ink/8 rounded-full overflow-hidden">
            <div className="h-full bg-gold rounded-full" style={{ width: `${book.pct}%` }} />
          </div>
          <span className="text-[8px] text-ink/35 shrink-0">{book.pct}%</span>
        </div>
      </div>
      {showResume && (
        <div className="shrink-0 bg-ink text-white text-[8px] font-medium rounded-full px-2.5 py-1">
          Resume
        </div>
      )}
    </div>
  );
}

function MobileShelfCard({ book }: { book: (typeof BOOKS)[keyof typeof BOOKS] }) {
  return (
    <div className="flex flex-col shrink-0 flex-1 gap-1 rounded-lg border border-ink/[0.06] bg-white p-1 pb-1.5 overflow-hidden">
      <div
        className="w-full h-[50px] rounded relative overflow-hidden"
        style={{ backgroundColor: book.bg }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={book.image}
          alt=""
          loading="lazy"
          className="w-full h-full object-cover"
        />
        <div className="absolute top-0.5 right-0.5 bg-gold text-white text-[7px] font-bold rounded-full w-[22px] h-[12px] flex items-center justify-center">
          {book.pct}%
        </div>
      </div>
      <div className="flex flex-col px-0.5">
        <span className="text-ink text-[9px] font-medium truncate leading-tight">{book.title}</span>
        <span className="text-ink/40 text-[8px] truncate">{book.author}</span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Mobile Device Stack (scaled to fit viewport)
   ═══════════════════════════════════════════════ */

const DESIGN_W = 440;
const DESIGN_H = 460;

function MobileDeviceStack() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setScale(Math.min(1, entry.contentRect.width / DESIGN_W));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={containerRef} className="w-full mx-auto md:hidden">
      <div style={{ height: DESIGN_H * scale }}>
        <div
          className="relative"
          style={{
            width: DESIGN_W,
            height: DESIGN_H,
            transform: `scale(${scale})`,
            transformOrigin: "top center",
            marginLeft: `calc(50% - ${DESIGN_W / 2}px)`,
            perspective: 1200,
          }}
        >
          {/* iPad Device — back layer */}
          <TiltDevice
            idleSpeed={1.4}
            className="absolute left-[30px] top-0 w-[300px] rounded-[18px] p-[6px]"
            style={{
              backgroundImage: "linear-gradient(in oklab 160deg, oklab(46% -.0007 0.011) 0%, oklab(38% .0002 0.009) 100%)",
              boxShadow:
                "inset 0 1px 0 rgba(255,255,255,0.08), 0 16px 48px rgba(0,0,0,0.2), 0 4px 12px rgba(0,0,0,0.1)",
              rotate: "-4deg",
              transformOrigin: "0% 0%",
            }}
          >
            <div
              className="absolute top-[4px] left-1/2 -translate-x-1/2 w-[4px] h-[4px] rounded-full z-10"
              style={{ background: "radial-gradient(circle, #3a3a3c 30%, #1d1d1f 100%)" }}
            />
            <div className="absolute -right-[1.5px] top-[40px] w-[2px] h-[20px] rounded-r-sm bg-[#2a2a2c]" />
            <div className="absolute -left-[1.5px] top-[50px] w-[2px] h-[32px] rounded-l-sm bg-[#2a2a2c]" />
            <div className="rounded-[12px] overflow-hidden bg-white relative" style={{ height: 380 }}>
              <div style={{ transform: "scale(0.65)", transformOrigin: "top left", width: "154%", height: "154%" }}>
                <IPadScreen />
              </div>
              <div
                className="pointer-events-none absolute inset-0 rounded-[12px]"
                style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.1) 0%, transparent 50%)" }}
              />
            </div>
          </TiltDevice>

          {/* iPhone Device — front layer, overlapping */}
          <TiltDevice
            idleSpeed={1.4}
            delay={0.12}
            className="absolute right-[30px] top-[30px] w-[175px] h-[370px] rounded-[30px] p-[6px] z-10"
            style={{
              backgroundImage: "linear-gradient(in oklab 160deg, oklab(32% -.0001 0.005) 0%, oklab(24% .0004 0.004) 100%)",
              boxShadow:
                "inset 0 1px 0 rgba(255,255,255,0.1), 0 20px 60px rgba(0,0,0,0.35), 0 6px 18px rgba(0,0,0,0.2)",
              rotate: "4deg",
              transformOrigin: "0% 0%",
            }}
          >
            <div className="absolute top-[8px] left-1/2 -translate-x-1/2 w-[44px] h-[12px] rounded-full bg-black z-20" />
            <div className="absolute -right-[1.5px] top-[70px] w-[2px] h-[24px] rounded-r-sm bg-[#1a1a1c]" />
            <div className="absolute -left-[1.5px] top-[55px] w-[2px] h-[16px] rounded-l-sm bg-[#1a1a1c]" />
            <div className="absolute -left-[1.5px] top-[78px] w-[2px] h-[24px] rounded-l-sm bg-[#1a1a1c]" />
            <div className="rounded-[24px] overflow-hidden bg-white w-full h-full relative">
              <div style={{ transform: "scale(0.65)", transformOrigin: "top left", width: "154%", height: "154%" }}>
                <IPhoneScreen />
              </div>
              <div
                className="pointer-events-none absolute inset-0 rounded-[24px]"
                style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.08) 0%, transparent 45%)" }}
              />
            </div>
            <div className="absolute bottom-[4px] left-1/2 -translate-x-1/2 w-[60px] h-[3px] rounded-full bg-black/20 z-20" />
          </TiltDevice>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════
   3D Tilt wrapper
   ═══════════════════════════════════════════════ */

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
  idleSpeed?: number;
  idleRadius?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const hovering = useRef(false);
  const visible = useRef(false);
  const rafId = useRef<number>(0);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(pointer: coarse)");
    setIsMobile(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const springConfig = isMobile
    ? { stiffness: 80, damping: 40 }
    : { stiffness: 200, damping: 30 };

  const tiltX = useSpring(useTransform(mouseY, [-0.5, 0.5], [6, -6]), springConfig);
  const tiltY = useSpring(useTransform(mouseX, [-0.5, 0.5], [-6, 6]), springConfig);

  const startIdle = useCallback(() => {
    let start: number | null = null;
    function tick(ts: number) {
      if (hovering.current || !visible.current) return;
      if (start === null) start = ts;
      const t = ((ts - start) / 1000) * idleSpeed;
      mouseX.set(Math.sin(t) * idleRadius);
      mouseY.set(Math.cos(t * 0.7) * idleRadius);
      rafId.current = requestAnimationFrame(tick);
    }
    rafId.current = requestAnimationFrame(tick);
  }, [idleSpeed, idleRadius, mouseX, mouseY]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible.current = entry.isIntersecting;
        if (entry.isIntersecting && !hovering.current) {
          startIdle();
        } else {
          cancelAnimationFrame(rafId.current);
        }
      },
      { rootMargin: "100px" }
    );
    observer.observe(el);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(rafId.current);
    };
  }, [startIdle]);

  function handleMouse(e: React.MouseEvent) {
    if (isMobile) return;
    hovering.current = true;
    cancelAnimationFrame(rafId.current);
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    mouseX.set((e.clientX - rect.left) / rect.width - 0.5);
    mouseY.set((e.clientY - rect.top) / rect.height - 0.5);
  }

  function handleLeave() {
    if (isMobile) return;
    hovering.current = false;
    if (visible.current) startIdle();
  }

  return (
    <motion.div
      ref={ref}
      onMouseMove={isMobile ? undefined : handleMouse}
      onMouseLeave={isMobile ? undefined : handleLeave}
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
        willChange: "transform",
      }}
    >
      {children}
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════
   Device Chrome: iPad Frame
   ═══════════════════════════════════════════════ */

function IPadFrame({ children, screenHeight }: { children: React.ReactNode; screenHeight: number }) {
  return (
    <div className="relative">
      <div
        className="absolute top-[6px] left-1/2 -translate-x-1/2 w-[6px] h-[6px] rounded-full z-10"
        style={{ background: "radial-gradient(circle, #3a3a3c 30%, #1d1d1f 100%)" }}
      />
      <div
        className="rounded-[16px] overflow-hidden bg-white relative"
        style={{ height: screenHeight }}
      >
        {children}
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

/* ═══════════════════════════════════════════════
   Device Chrome: iPhone Frame
   ═══════════════════════════════════════════════ */

function IPhoneFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative w-full h-full">
      <div className="absolute top-[8px] left-1/2 -translate-x-1/2 w-[72px] h-[20px] rounded-full bg-black z-20" />
      <div className="rounded-[32px] overflow-hidden bg-white w-full h-full relative">
        {children}
        <div
          className="pointer-events-none absolute inset-0 rounded-[32px]"
          style={{
            background: "linear-gradient(135deg, rgba(255,255,255,0.10) 0%, transparent 45%)",
          }}
        />
      </div>
      <div className="absolute bottom-[6px] left-1/2 -translate-x-1/2 w-[100px] h-[4px] rounded-full bg-black/20 z-20" />
    </div>
  );
}

/* ═══════════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════════ */

export default function LibraryTeacher() {
  const sectionRef = useRef<HTMLElement>(null);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "end start"],
  });

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
          More than 10,000 Arabic books. Real-time pronunciation feedback. Grammar
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
          <div className="absolute -right-[2px] top-[120px] w-[3px] h-[40px] rounded-r-sm bg-[#1a1a1c]" />
          <div className="absolute -left-[2px] top-[90px] w-[3px] h-[24px] rounded-l-sm bg-[#1a1a1c]" />
          <div className="absolute -left-[2px] top-[125px] w-[3px] h-[40px] rounded-l-sm bg-[#1a1a1c]" />
          <div className="absolute -left-[2px] top-[175px] w-[3px] h-[40px] rounded-l-sm bg-[#1a1a1c]" />
          <IPhoneFrame>
            <IPhoneScreen />
          </IPhoneFrame>
        </TiltDevice>
      </div>

      {/* Device Stack — Mobile (overlapping) */}
      <MobileDeviceStack />
    </section>
  );
}
