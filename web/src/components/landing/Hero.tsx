"use client";

import React, { useState, useEffect, useRef } from "react";
import Image from "next/image";
import { motion, AnimatePresence, useScroll, useTransform } from "motion/react";

function getReferralFromCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/suhuf_ref=([^;]+)/);
  return match ? match[1] : null;
}

/* ─── iPad screen content ─── */

function AppBar({ isListening }: { isListening: boolean }) {
  return (
    <div className="flex items-center justify-between px-4 h-[53px] shrink-0">
      <span className="font-serif italic text-[14px] text-ink">suhuf</span>
      <span className="text-[12px] text-gold">
        Al-Ajrumiyyah — Chapter 1
      </span>
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
  );
}

const READ_ALONG_WORDS = ["الكلامُ", "هو", "اللفظُ", "المركّبُ", "المفيدُ", "بالوضعِ"];

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
        بابُ الكلامِ
      </h2>

      <div className="text-[16px] leading-[38px] text-ink text-center space-y-0">
        {/* First paragraph: read-along highlights + error on last word */}
        <p>
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
                          بالوضعِ not بالوضعَ
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
        </p>

        <p>وأقسامُهُ ثلاثةٌ: اسمٌ، وفعلٌ، وحرفٌ جاءَ لمعنًى</p>
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
            والتنوينِ
          </motion.span>{" "}
          ودخولِ الألفِ واللامِ
        </p>
        <p>وحروفُ الخفضِ: مِن وإلى وعن وعلى وفي ورُبَّ</p>
        <p>والباءُ والكافُ واللامُ وحروفُ القسَمِ</p>
        <p>وهي: الواوُ والباءُ والتاءُ</p>
      </div>
    </div>
  );
}

function WordPanel() {
  return (
    <div className="w-[155px] shrink-0 border-l border-ink/8 px-3 py-4 flex flex-col gap-3 overflow-hidden">
      <p className="font-arabic text-[22px] text-ink text-right" dir="rtl">
        والتنوينِ
      </p>
      <p className="text-[12px] text-gold">and the tanwin</p>
      <div className="text-[10px] text-gold leading-relaxed">
        <p>root: ن و ن</p>
        <p>pattern: تَفعِيل</p>
        <p>ma&apos;tuf &middot; majrur</p>
      </div>
      <div>
        <p className="text-[9px] text-gold uppercase font-semibold tracking-widest mb-1">
          I&apos;RAB
        </p>
        <p className="text-[10px] text-ink/60 leading-snug">
          Conjuncted (ma&apos;tuf) to بِالخَفضِ, takes kasra as it follows a
          preposition.
        </p>
      </div>
    </div>
  );
}

function TabBar() {
  return (
    <div className="h-[45px] shrink-0 border-t border-ink/8 flex items-center justify-around px-4">
      <div className="flex flex-col items-center gap-0.5">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <path
            d="M2 7L9 2L16 7V15C16 15.55 15.55 16 15 16H3C2.45 16 2 15.55 2 15V7Z"
            stroke="#B47D3A"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path d="M7 16V9H11V16" stroke="#B47D3A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="text-[10px] text-gold">Read</span>
      </div>
      <div className="flex flex-col items-center gap-0.5">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <rect x="3" y="2" width="12" height="14" rx="1.5" stroke="#2A1F17" strokeOpacity="0.4" strokeWidth="1.5" />
          <path d="M6 5H12M6 8H12M6 11H9" stroke="#2A1F17" strokeOpacity="0.4" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span className="text-[10px] text-ink/40">Library</span>
      </div>
      <div className="flex flex-col items-center gap-0.5">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <circle cx="9" cy="9" r="6.5" stroke="#2A1F17" strokeOpacity="0.4" strokeWidth="1.5" />
        </svg>
        <span className="text-[10px] text-ink/40">Review</span>
      </div>
      <div className="flex flex-col items-center gap-0.5">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <circle cx="9" cy="6" r="3" stroke="#2A1F17" strokeOpacity="0.4" strokeWidth="1.5" />
          <path d="M3 16C3 13 5.5 11 9 11C12.5 11 15 13 15 16" stroke="#2A1F17" strokeOpacity="0.4" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span className="text-[10px] text-ink/40">Profile</span>
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

  const rotateX = useTransform(scrollYProgress, [0, 0.3, 1], [15, 0, 0]);

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

  useEffect(() => {
    const delays = [2000, 3500, 3000, 500, 800, 3000, 800];
    const timer = setTimeout(() => {
      setStep((s) => (s + 1) % delays.length);
    }, delays[step]);
    return () => clearTimeout(timer);
  }, [step]);

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

  const STEP_CARDS: {
    title: string;
    desc: string;
    side: "left" | "right";
    top: string;
  }[] = [];

  if (step === 1)
    STEP_CARDS.push({
      title: "Read aloud",
      desc: "suhuf follows along word by word",
      side: "left",
      top: "32%",
    });
  if (step === 2)
    STEP_CARDS.push({
      title: "Error detected",
      desc: "Caught and explained instantly",
      side: "right",
      top: "22%",
    });
  if (step === 4)
    STEP_CARDS.push({
      title: "Tap any word",
      desc: "Select for instant details",
      side: "left",
      top: "52%",
    });
  if (step === 5)
    STEP_CARDS.push({
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
          background: "linear-gradient(145deg, #3a3538 0%, #2a2628 100%)",
          boxShadow:
            "inset 0 1px 0 #FFFFFF14, 0 25px 80px #0000002E, 0 4px 16px #0000001A",
        }}
        className="w-full rounded-[22px] p-2"
      >
        {/* Screen */}
        <div className="bg-white rounded-[14px] aspect-[19/12] flex flex-col overflow-hidden">
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
          <TabBar />
          {/* Home indicator */}
          <div className="flex justify-center pb-2">
            <div className="w-[100px] h-[3px] rounded-full bg-ink/20" />
          </div>
        </div>
      </motion.div>

      {/* Annotation cards */}
      <AnimatePresence>
        {STEP_CARDS.map((card) => (
          <motion.div
            key={card.title}
            initial={{
              opacity: 0,
              x: card.side === "left" ? -16 : 16,
            }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className={`absolute ${
              card.side === "left"
                ? "right-[calc(100%+16px)] flex-row"
                : "left-[calc(100%+16px)] flex-row-reverse"
            } flex items-center`}
            style={{ top: card.top }}
          >
            <div className="bg-white border border-ink/8 rounded-2xl px-5 py-4 shadow-[0_4px_20px_rgba(0,0,0,0.08)] w-[240px]">
              <p className="text-[15px] text-ink font-semibold leading-tight">
                {card.title}
              </p>
              <p className="text-[13px] text-ink/40 mt-1.5 leading-snug">
                {card.desc}
              </p>
            </div>
            <div className="flex items-center">
              <div className="w-6 h-px bg-ink/15" />
              <div className="w-2 h-2 rounded-full bg-gold/50 shrink-0" />
            </div>
          </motion.div>
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
  const [referrerCode, setReferrerCode] = useState<string | null>(null);
  const [existingUser, setExistingUser] = useState<WaitlistUser | null>(null);
  const [checkingCookie, setCheckingCookie] = useState(true);

  useEffect(() => {
    setReferrerCode(getReferralFromCookie());
    fetch("/api/waitlist/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.user) setExistingUser(data.user);
      })
      .catch(() => {})
      .finally(() => setCheckingCookie(false));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          signup_source: "hero",
          referral_code: referrerCode,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        window.location.href = `/welcome?id=${data.id}&position=${data.position}&referralCode=${data.referral_code}${data.is_existing ? "&existing=true" : ""}`;
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <section
      id="waitlist"
      className="flex flex-col items-center w-full px-[60px] pt-[60px] pb-[40px] gap-5"
      style={{
        boxShadow: "#00000033 0px 2px 3px inset, #00000033 0px 2px 3px",
      }}
    >
      <Image src="/logo.png" alt="suhuf" width={40} height={40} className="rounded-xl" />

      <h1 className="font-serif text-[50px] font-normal leading-[56px] tracking-[-0.03em] text-ink text-center">
        Your Arabic readalong
        <br />
        companion.
      </h1>

      <p className="text-ink/[0.42] text-[20px] font-normal leading-[160%] text-center max-w-[580px]">
        Read any classical Arabic text aloud — suhuf listens, catches your
        grammar mistakes in real time, and explains why. Tap any word for
        instant translation, morphology, and i&apos;rab.
      </p>

      {!checkingCookie && existingUser ? (
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
      ) : !checkingCookie ? (
        <>
          <form onSubmit={handleSubmit} className="flex items-center pt-1">
            <div className="flex items-center rounded-l-full py-3.5 px-5 bg-parchment-warm border border-ink/10 border-r-0">
              <input
                type="email"
                required
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-[220px] text-sm text-ink bg-transparent outline-none placeholder:text-ink/30"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="rounded-r-full py-3.5 px-7 bg-ink text-white text-sm font-medium hover:bg-ink/90 transition-colors disabled:opacity-70"
            >
              {loading ? "Joining..." : "Get Early Access"}
            </button>
          </form>

          <p className="text-[11px] text-ink/[0.22]">
            Free during beta &middot; No credit card required
          </p>
        </>
      ) : null}

      <IPadMockup />
    </section>
  );
}
