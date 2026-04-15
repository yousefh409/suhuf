"use client";

import React, { useState, useEffect, useRef } from "react";
import Image from "next/image";
import { motion, AnimatePresence, useScroll, useTransform, useInView } from "motion/react";

function getReferralFromCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/suhuf_ref=([^;]+)/);
  return match ? match[1] : null;
}

/* ─── iPad screen content ─── */

function AppBar({ isListening }: { isListening: boolean }) {
  return (
    <div className="flex items-center justify-between px-4 h-[50px] shrink-0 border-b border-ink/6">
      {/* Left: back arrow + Library */}
      <div className="flex items-center gap-1.5 min-w-[80px]">
        <svg width="8" height="14" viewBox="0 0 8 14" fill="none">
          <path d="M7 1L1 7L7 13" stroke="#B47D3A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-[13px] text-gold">Library</span>
      </div>
      {/* Center: title + subtitle */}
      <div className="flex flex-col items-center">
        <span className="text-[13px] text-ink font-semibold leading-tight">Al-Ajrumiyyah</span>
        <span className="text-[10px] text-ink/40">Chapter 1 &middot; Bab al-Kalam</span>
      </div>
      {/* Right: bookmark + play/listening */}
      <div className="flex items-center gap-2 min-w-[80px] justify-end">
        <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
          <path d="M4 2H14V16L9 12.5L4 16V2Z" stroke="#2A1F17" strokeOpacity="0.3" strokeWidth="1.5" strokeLinejoin="round" />
        </svg>
        <AnimatePresence mode="wait">
          {isListening ? (
            <motion.div
              key="listening"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: [1, 1.15, 1], opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{
                scale: { duration: 1.5, repeat: Infinity, ease: "easeInOut" },
                opacity: { duration: 0.2 },
              }}
              className="w-7 h-7 rounded-full bg-[#3A7D50] flex items-center justify-center"
            >
              <svg width="14" height="10" viewBox="0 0 14 10" fill="none">
                <rect x="0" y="3" width="2" height="4" rx="1" fill="white" />
                <rect x="4" y="1" width="2" height="8" rx="1" fill="white" />
                <rect x="8" y="2" width="2" height="6" rx="1" fill="white" />
                <rect x="12" y="3" width="2" height="4" rx="1" fill="white" />
              </svg>
            </motion.div>
          ) : (
            <motion.div
              key="play"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="w-7 h-7 rounded-full bg-[#3A7D50] flex items-center justify-center"
            >
              <svg width="10" height="12" viewBox="0 0 10 12" fill="none">
                <path d="M1 1L9 6L1 11V1Z" fill="white" />
              </svg>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

const READ_ALONG_WORDS = ["الكَلامُ", "هُوَ", "اللَّفظُ", "المُرَكَّبُ", "المُفِيدُ", "بِالوَضْعِ"];

function BookPage({
  readAlongIndex,
  showError,
  wordHighlighted,
}: {
  readAlongIndex: number;
  showError: boolean;
  wordHighlighted: boolean;
}) {
  return (
    <div
      className="flex-1 overflow-hidden flex flex-col items-center px-5 py-4 font-arabic"
      dir="rtl"
    >
      <h2 className="text-[18px] text-ink font-bold pb-2 mb-3 border-b border-ink/10 w-full text-center">
        بَابُ الكَلامِ
      </h2>

      <div className="text-[16px] leading-[38px] text-ink text-center space-y-0">
        {/* First paragraph: read-along highlights + error on last word */}
        <span className="block">
          {READ_ALONG_WORDS.map((word, i) => {
            const isLast = i === READ_ALONG_WORDS.length - 1;
            const isActive = readAlongIndex === i;

            if (isLast) {
              return (
                <React.Fragment key={i}>
                  {" "}
                  <span className="relative inline-block">
                    <motion.span
                      animate={{
                        backgroundColor: showError
                          ? "rgba(239, 68, 68, 0.1)"
                          : isActive
                            ? "rgba(180, 125, 58, 0.2)"
                            : "rgba(180, 125, 58, 0)",
                        boxShadow: showError
                          ? "inset 0 -2px 0 rgba(239, 68, 68, 0.6)"
                          : "inset 0 0 0 transparent",
                      }}
                      transition={{ duration: 0.3 }}
                      className="rounded px-0.5"
                    >
                      {word}
                    </motion.span>
                    <AnimatePresence>
                      {showError && (
                        <motion.div
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: 4 }}
                          transition={{ duration: 0.3 }}
                          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 bg-red-50 border border-red-200 rounded-md px-2 py-0.5 text-[10px] text-red-600 whitespace-nowrap z-10"
                        >
                          بِالوَضْعِ
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </span>
                </React.Fragment>
              );
            }

            return (
              <React.Fragment key={i}>
                {i > 0 && " "}
                <motion.span
                  animate={{
                    backgroundColor: isActive
                      ? "rgba(180, 125, 58, 0.2)"
                      : "rgba(180, 125, 58, 0)",
                  }}
                  transition={{ duration: 0.2 }}
                  className="rounded px-0.5"
                >
                  {word}
                </motion.span>
              </React.Fragment>
            );
          })}
        </span>

        <p>وَأَقسَامُهُ ثَلاثَةٌ: اسمٌ، وَفِعلٌ، وَحَرفٌ جَاءَ لِمَعنًى</p>
        <p>
          فَالاسمُ يُعرَفُ بِالخَفضِ{" "}
          <motion.span
            animate={{
              backgroundColor: wordHighlighted
                ? "rgba(180, 125, 58, 0.25)"
                : "rgba(180, 125, 58, 0)",
            }}
            transition={{ duration: 0.4 }}
            className="rounded px-0.5"
          >
            وَالتَّنوِينِ
          </motion.span>{" "}
          وَدُخُولِ الأَلِفِ وَاللَّامِ
        </p>
        <p>وَحُرُوفُ الخَفضِ: مِن وَإِلى وَعَن وَعَلى وَفِي وَرُبَّ</p>
        <p>وَالبَاءُ وَالكَافُ وَاللَّامُ وَحُرُوفُ القَسَمِ</p>
        <p>وَهِيَ: الوَاوُ وَالبَاءُ وَالتَّاءُ</p>
      </div>
    </div>
  );
}

function WordPanel() {
  return (
    <div className="w-[155px] shrink-0 border-l border-ink/8 px-3 py-3 flex flex-col gap-1.5 overflow-hidden">
      {/* Word + transliteration */}
      <p className="font-arabic text-[20px] text-ink text-right" dir="rtl">وَالتَّنوِينِ</p>
      <p className="text-[10px] text-ink/40 italic">wat-tanwīni</p>

      {/* Tabs */}
      <div className="flex border-b border-ink/8">
        <span className="text-[9px] text-ink/25 pb-1 px-1">Translation</span>
        <span className="text-[9px] text-gold font-semibold pb-1 border-b border-gold px-1">I&apos;rab</span>
      </div>

      {/* Type + Case */}
      <div className="flex gap-3">
        <div>
          <p className="text-[7px] text-gold uppercase font-semibold tracking-widest mb-0.5">TYPE</p>
          <p className="text-[9px] text-ink"><span className="font-arabic" dir="rtl">اسم</span> noun</p>
        </div>
        <div>
          <p className="text-[7px] text-gold uppercase font-semibold tracking-widest mb-0.5">CASE</p>
          <p className="text-[9px] text-ink"><span className="font-arabic" dir="rtl">مجرور</span> gen.</p>
        </div>
      </div>

      {/* Role (i'rab classification) */}
      <div>
        <p className="text-[7px] text-gold uppercase font-semibold tracking-widest mb-0.5">ROLE</p>
        <p className="font-arabic text-[11px] text-ink" dir="rtl">مَعطُوف</p>
        <p className="text-[8px] text-ink/45">conjuncted noun</p>
      </div>

      {/* Marker */}
      <div>
        <p className="text-[7px] text-gold uppercase font-semibold tracking-widest mb-0.5">MARKER</p>
        <p className="text-[9px] text-ink"><span className="font-arabic" dir="rtl">كسرة</span> kasra</p>
      </div>

      {/* Sarf: Root + Pattern */}
      <div className="flex gap-3">
        <div>
          <p className="text-[7px] text-gold uppercase font-semibold tracking-widest mb-0.5">ROOT</p>
          <p className="font-arabic text-[11px] text-ink" dir="rtl">ن و ن</p>
        </div>
        <div>
          <p className="text-[7px] text-gold uppercase font-semibold tracking-widest mb-0.5">PATTERN</p>
          <p className="font-arabic text-[11px] text-ink" dir="rtl">تَفعِيل</p>
        </div>
      </div>

      {/* Why this case */}
      <div>
        <p className="text-[7px] text-gold uppercase font-semibold tracking-widest mb-0.5">WHY THIS CASE?</p>
        <p className="text-[8px] text-ink/50 leading-snug">
          Conjuncted to بِالخَفضِ via وَ, so it takes the same case (jar/kasra).
        </p>
      </div>
    </div>
  );
}

function BottomBar({ isListening, showError }: { isListening: boolean; showError: boolean }) {
  return (
    <div className="h-[42px] shrink-0 border-t border-ink/8 flex items-center justify-between px-4">
      {/* Tashkeel toggle */}
      <div className="flex items-center gap-1.5">
        <div className="w-[14px] h-[14px] rounded-sm border border-ink/20 flex items-center justify-center">
          <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
            <path d="M1 4L3 6L7 2" stroke="#3A7D50" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <span className="text-[11px] text-ink/60">Tashkeel</span>
      </div>

      {/* Recording indicator */}
      <AnimatePresence>
        {isListening && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="flex items-center gap-1.5"
          >
            <motion.div
              animate={{ opacity: [1, 0.4, 1] }}
              transition={{ duration: 1.5, repeat: Infinity }}
              className="w-[6px] h-[6px] rounded-full bg-red-500"
            />
            <span className="text-[11px] text-ink/50">Recording</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error count + Stop */}
      <div className="flex items-center gap-3">
        <AnimatePresence>
          {showError && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-[11px] text-red-500 font-medium"
            >
              1 error
            </motion.span>
          )}
        </AnimatePresence>
        {isListening && (
          <div className="flex items-center gap-1.5 bg-ink text-white rounded-full px-3 py-1">
            <div className="w-[8px] h-[8px] rounded-sm bg-white" />
            <span className="text-[10px] font-medium">Stop</span>
          </div>
        )}
      </div>
    </div>
  );
}

function IPadMockup() {
  const containerRef = useRef<HTMLDivElement>(null);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start end", "end start"],
  });

  const rotateX = useTransform(scrollYProgress, [0, 0.45, 1], [40, 0, 0]);
  const inView = useInView(containerRef, { amount: 0.3 });

  /* ─── Walkthrough state machine ───
   *  0: idle         (2s)
   *  1: read-along   (3.5s)  — words highlight one-by-one, listening active
   *  2: error shown  (3s)    — last word gets red underline + correction tooltip
   *  3: clear        (0.5s)  — everything resets
   *  4: word tap     (0.8s)  — والتنوينِ highlights gold
   *  5: word panel   (3s)    — WordPanel slides in
   *  6: dismiss      (0.8s)  — panel out, highlight fades
   */
  const [step, setStep] = useState(0);
  const [readAlongIndex, setReadAlongIndex] = useState(-1);

  // Only advance walkthrough when visible in viewport
  useEffect(() => {
    if (!inView) return;
    const delays = [800, 3500, 3500, 300, 500, 5000, 500];
    const timer = setTimeout(() => {
      setStep((s) => (s + 1) % delays.length);
    }, delays[step]);
    return () => clearTimeout(timer);
  }, [step, inView]);

  // Read-along sub-animation during step 1
  useEffect(() => {
    if (step !== 1) {
      setReadAlongIndex(-1);
      return;
    }
    let index = 0;
    setReadAlongIndex(0);
    const interval = setInterval(() => {
      index++;
      if (index >= READ_ALONG_WORDS.length) {
        clearInterval(interval);
        setReadAlongIndex(-1);
      } else {
        setReadAlongIndex(index);
      }
    }, 500);
    return () => clearInterval(interval);
  }, [step]);

  const isListening = step === 1 || step === 2;
  const showError = step === 2;
  const wordHighlighted = step === 4 || step === 5;
  const panelVisible = step === 5;

  // Map internal step → display step index (0-3), -1 for transitions
  const displayStep = step === 1 ? 0 : step === 2 ? 1 : step === 4 ? 2 : step === 5 ? 3 : -1;

  const STEP_CARDS: {
    num: number;
    title: string;
    desc: string;
    side: "left" | "right";
    top: string;
  }[] = [];

  if (step === 1)
    STEP_CARDS.push({
      num: 1,
      title: "Read aloud",
      desc: "suhuf follows along word by word",
      side: "left",
      top: "32%",
    });
  if (step === 2)
    STEP_CARDS.push({
      num: 2,
      title: "Error detected",
      desc: "Tashkeel, i'rab, and pronunciation — caught instantly",
      side: "right",
      top: "22%",
    });
  if (step === 4)
    STEP_CARDS.push({
      num: 3,
      title: "Tap any word",
      desc: "Select for instant details",
      side: "left",
      top: "52%",
    });
  if (step === 5)
    STEP_CARDS.push({
      num: 4,
      title: "Word breakdown",
      desc: "Translation, root, and i'rab",
      side: "right",
      top: "38%",
    });


  return (
    <div
      ref={containerRef}
      className="relative mx-auto w-full max-w-[760px]"
      style={{ perspective: "1000px" }}
    >
      <motion.div
        style={{
          rotateX,
          backgroundImage: "linear-gradient(in oklab 160deg, oklab(46% -.0007 0.011) 0%, oklab(38% .0002 0.009) 100%)",
          boxShadow:
            "inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -1px 0 rgba(0,0,0,0.2), 0 30px 80px rgba(0,0,0,0.25), 0 8px 24px rgba(0,0,0,0.15)",
          willChange: "transform",
          backfaceVisibility: "hidden",
        }}
        className="relative w-full rounded-[16px] md:rounded-[24px] p-[6px] md:p-[10px]"
      >
        {/* Front camera */}
        <div
          className="absolute top-[4px] md:top-[6px] left-1/2 -translate-x-1/2 w-[4px] md:w-[6px] h-[4px] md:h-[6px] rounded-full z-10"
          style={{ background: "radial-gradient(circle, #3a3a3c 30%, #1d1d1f 100%)" }}
        />
        {/* Side buttons */}
        <div className="absolute -right-[1.5px] md:-right-[2px] top-[30px] md:top-[60px] w-[2px] md:w-[3px] h-[18px] md:h-[30px] rounded-r-sm bg-[#2a2a2c]" />
        <div className="absolute -right-[1.5px] md:-right-[2px] top-[55px] md:top-[100px] w-[2px] md:w-[3px] h-[18px] md:h-[30px] rounded-r-sm bg-[#2a2a2c]" />
        <div className="absolute -left-[1.5px] md:-left-[2px] top-[40px] md:top-[80px] w-[2px] md:w-[3px] h-[30px] md:h-[50px] rounded-l-sm bg-[#2a2a2c]" />

        <div
          className="bg-white rounded-[10px] md:rounded-[16px] aspect-[19/12] flex flex-col overflow-hidden relative"
          style={{ contain: "layout paint", backfaceVisibility: "hidden" }}
        >
          {/* Status Bar */}
          <div className="flex items-center justify-between px-4 pt-1.5 pb-0">
            <span className="text-[9px] font-semibold text-ink">9:41</span>
            <div className="flex items-center gap-1">
              <svg width="12" height="9" viewBox="0 0 18 12" fill="none">
                <rect x="0" y="7" width="3" height="5" rx="0.5" fill="#2A1F17" />
                <rect x="4" y="5" width="3" height="7" rx="0.5" fill="#2A1F17" />
                <rect x="8" y="3" width="3" height="9" rx="0.5" fill="#2A1F17" />
                <rect x="12" y="0" width="3" height="12" rx="0.5" fill="#2A1F17" />
              </svg>
              <svg width="11" height="9" viewBox="0 0 16 12" fill="none">
                <path d="M1 3.5C4 0.5 12 0.5 15 3.5" stroke="#2A1F17" strokeWidth="1.5" strokeLinecap="round" />
                <path d="M3.5 6C5.5 4 10.5 4 12.5 6" stroke="#2A1F17" strokeWidth="1.5" strokeLinecap="round" />
                <circle cx="8" cy="9" r="1.5" fill="#2A1F17" />
              </svg>
              <svg width="16" height="8" viewBox="0 0 22 11" fill="none">
                <rect x="0.5" y="0.5" width="18" height="10" rx="2" stroke="#2A1F17" strokeOpacity="0.5" />
                <rect x="2" y="2" width="13" height="7" rx="1" fill="#2A1F17" />
                <rect x="19.5" y="3" width="2" height="5" rx="1" fill="#2A1F17" strokeOpacity="0.3" />
              </svg>
            </div>
          </div>
          <AppBar isListening={isListening} />
          <div className="relative flex flex-1 min-h-0">
            <BookPage
              readAlongIndex={readAlongIndex}
              showError={showError}
              wordHighlighted={wordHighlighted}
            />
            <AnimatePresence>
              {panelVisible && (
                <motion.div
                  key="word-panel"
                  initial={{ x: "100%", opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  exit={{ x: "100%", opacity: 0 }}
                  transition={{ duration: 0.4, ease: "easeOut" }}
                  className="absolute right-0 top-0 bottom-0 z-10 bg-white"
                >
                  <WordPanel />
                </motion.div>
              )}
            </AnimatePresence>

          </div>
          <BottomBar isListening={isListening} showError={showError} />
          {/* Home indicator */}
          <div className="flex justify-center pb-2">
            <div className="w-[100px] h-[3px] rounded-full bg-ink/20" />
          </div>
          {/* Screen glare */}
          <div
            className="pointer-events-none absolute inset-0 rounded-[10px] md:rounded-[16px]"
            style={{
              background: "linear-gradient(135deg, rgba(255,255,255,0.12) 0%, transparent 50%)",
            }}
          />
        </div>
      </motion.div>

      {/* Step indicator */}
      <div className="flex items-center justify-center gap-2 mt-4">
        {[0, 1, 2, 3].map((i) => (
          <motion.div
            key={i}
            animate={{
              backgroundColor: displayStep === i ? "rgba(180, 125, 58, 0.8)" : "rgba(42, 31, 23, 0.1)",
              scale: displayStep === i ? 1.3 : 1,
            }}
            transition={{ duration: 0.3 }}
            className="w-2 h-2 rounded-full"
          />
        ))}
      </div>

      {/* Annotation cards — desktop: positioned outside iPad, mobile: overlaid on iPad */}
      <AnimatePresence>
        {STEP_CARDS.map((card) => (
          <React.Fragment key={card.title}>
            {/* Desktop annotation (hidden on mobile) */}
            <motion.div
              initial={{
                opacity: 0,
                x: card.side === "left" ? -50 : 50,
                y: 20,
                scale: 0.8,
                rotateY: card.side === "left" ? -12 : 12,
              }}
              animate={{
                opacity: 1,
                x: 0,
                y: 0,
                scale: 1,
                rotateY: card.side === "left" ? 5 : -5,
              }}
              exit={{
                opacity: 0,
                x: card.side === "left" ? -30 : 30,
                y: 8,
                scale: 0.88,
                rotateY: card.side === "left" ? -6 : 6,
              }}
              transition={{
                type: "spring",
                stiffness: 160,
                damping: 18,
                mass: 0.7,
              }}
              className={`absolute hidden lg:flex ${
                card.side === "left"
                  ? "right-[calc(100%+16px)] flex-row"
                  : "left-[calc(100%+16px)] flex-row-reverse"
              } items-center`}
              style={{
                top: card.top,
                perspective: "500px",
                transformStyle: "preserve-3d",
                backfaceVisibility: "hidden",
              }}
            >
              <div
                className="bg-white/95 backdrop-blur-sm border border-ink/8 rounded-2xl px-5 py-4 w-[240px]"
                style={{
                  boxShadow:
                    "0 12px 40px rgba(0,0,0,0.12), 0 2px 10px rgba(0,0,0,0.06)",
                }}
              >
                <div className="flex items-center gap-2.5">
                  <span className="w-6 h-6 rounded-full bg-gold/15 text-gold text-[12px] font-bold flex items-center justify-center shrink-0">
                    {card.num}
                  </span>
                  <p className="text-[16px] text-ink font-semibold leading-tight">
                    {card.title}
                  </p>
                </div>
                <p className="text-[14px] text-ink/55 mt-1.5 leading-snug pl-[34px]">
                  {card.desc}
                </p>
              </div>
              <div className="flex items-center">
                <motion.div
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ type: "spring", stiffness: 200, damping: 25, delay: 0.08 }}
                  className="w-6 h-px bg-ink/15 origin-left"
                  style={{ transformOrigin: card.side === "left" ? "right" : "left" }}
                />
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 350, damping: 12, delay: 0.15 }}
                  className="w-2 h-2 rounded-full bg-gold/50 shrink-0"
                />
              </div>
            </motion.div>

            {/* Mobile annotation (overlaid at bottom of iPad) */}
            <motion.div
              initial={{ opacity: 0, y: 24, scale: 0.85 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 14, scale: 0.9 }}
              transition={{
                type: "spring",
                stiffness: 180,
                damping: 18,
              }}
              className="absolute bottom-[-52px] left-1/2 -translate-x-1/2 lg:hidden z-20 w-[calc(100%-32px)] max-w-[360px]"
            >
              <div
                className="bg-white border border-ink/8 rounded-xl px-4 py-2.5 flex items-start gap-2"
                style={{
                  boxShadow:
                    "0 12px 40px rgba(0,0,0,0.12), 0 2px 10px rgba(0,0,0,0.06)",
                }}
              >
                <span className="w-5 h-5 rounded-full bg-gold/15 text-gold text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                  {card.num}
                </span>
                <div className="min-w-0">
                  <p className="text-[13px] text-ink font-semibold leading-tight">
                    {card.title}
                  </p>
                  <p className="text-[12px] text-ink/50 leading-tight mt-0.5">
                    {card.desc}
                  </p>
                </div>
              </div>
            </motion.div>
          </React.Fragment>
        ))}
      </AnimatePresence>
    </div>
  );
}

/* ─── Hero ─── */

type WaitlistUser = {
  id: string;
  position: number;
  referral_code: string;
};

export default function Hero() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [referrerCode, setReferrerCode] = useState<string | null>(null);
  const [existingUser, setExistingUser] = useState<WaitlistUser | null>(null);
  useEffect(() => {
    setReferrerCode(getReferralFromCookie());
    fetch("/api/waitlist/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.user) setExistingUser(data.user);
      })
      .catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          signup_source: "hero",
          referral_code: referrerCode,
          ...Object.fromEntries(
            ["utm_source", "utm_medium", "utm_campaign"]
              .map((k) => [k, new URLSearchParams(window.location.search).get(k)])
              .filter(([, v]) => v)
          ),
        }),
      });
      const data = await res.json();
      if (res.ok) {
        window.location.href = `/welcome?id=${data.id}&position=${data.position}&referralCode=${data.referral_code}${data.is_existing ? "&existing=true" : ""}`;
      } else {
        setError(data.error || "Something went wrong. Please try again.");
      }
    } catch {
      setError("Could not connect. Please check your internet and try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      id="waitlist"
      className="flex flex-col items-center w-full px-5 md:px-[60px] pt-10 md:pt-[60px] pb-[40px] gap-5"
    >
      <Image src="/logo.png" alt="suhuf" width={40} height={40} className="rounded-xl" />

      <h1 className="font-serif text-[34px] md:text-[50px] font-normal leading-[40px] md:leading-[56px] tracking-[-0.03em] text-ink text-center">
        Your Arabic readalong
        <br />
        companion.
      </h1>

      <p className="text-ink/[0.42] text-base md:text-[20px] font-normal leading-[160%] text-center max-w-[580px]">
        Read any classical Arabic text aloud — suhuf listens, catches your
        grammar mistakes in real time, and explains why. Tap any word for
        instant translation, morphology, and i&apos;rab.
      </p>

      {existingUser ? (
        <a
          href={`/welcome?id=${existingUser.id}&position=${existingUser.position}&referralCode=${existingUser.referral_code}&existing=true`}
          className="flex items-center gap-3 rounded-full py-3 pl-6 pr-4 bg-parchment-warm border border-ink/10 hover:border-gold/30 transition-colors"
        >
          <span className="text-sm text-ink">
            You&apos;re <span className="font-semibold text-gold">#{existingUser.position}</span> on the waitlist
          </span>
          <span className="text-xs text-gold font-medium flex items-center gap-1">
            View my spot
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5.25 3.5L8.75 7L5.25 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </span>
        </a>
      ) : (
        <>
          <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row items-stretch sm:items-center pt-1 w-full sm:w-auto px-2 sm:px-0">
            <div className="flex items-center rounded-full sm:rounded-l-full sm:rounded-r-none py-3.5 px-5 bg-parchment-warm border border-ink/10 sm:border-r-0">
              <input
                type="email"
                required
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full sm:w-[220px] text-sm text-ink bg-transparent outline-none placeholder:text-ink/30"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="rounded-full sm:rounded-l-none sm:rounded-r-full py-3.5 px-7 bg-ink text-white text-sm font-medium hover:bg-ink/90 transition-colors disabled:opacity-70 mt-2 sm:mt-0"
            >
              {loading ? "Joining..." : "Get Early Access"}
            </button>
          </form>

          {error && (
            <p className="text-[13px] text-red-500">{error}</p>
          )}
          <p className="text-[11px] text-ink/[0.22]">
            Free during beta &middot; No credit card required
          </p>
        </>
      )}

      <div className="w-full mb-14 lg:mb-0">
        <IPadMockup />
      </div>
    </section>
  );
}
