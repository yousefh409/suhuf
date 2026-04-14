"use client";

import { useState, useEffect } from "react";

function getReferralFromCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/suhuf_ref=([^;]+)/);
  return match ? match[1] : null;
}

/* ─── iPad screen content ─── */

function AppBar() {
  return (
    <div className="flex items-center justify-between px-4 h-[53px] shrink-0">
      <span className="font-serif italic text-[14px] text-ink">suhuf</span>
      <span className="text-[12px] text-gold">
        Al-Ajrumiyyah — Chapter 1
      </span>
      <div className="w-7 h-7 rounded-full bg-[#3A7D50] flex items-center justify-center">
        <svg width="10" height="12" viewBox="0 0 10 12" fill="none">
          <path d="M1 1L9 6L1 11V1Z" fill="white" />
        </svg>
      </div>
    </div>
  );
}

function BookPage() {
  return (
    <div className="flex-1 overflow-hidden flex flex-col items-center px-5 py-4 font-arabic" dir="rtl">
      {/* Chapter heading */}
      <h2 className="text-[18px] text-ink font-bold pb-2 mb-3 border-b border-ink/10 w-full text-center">
        بابُ الكلامِ
      </h2>

      <div className="text-[16px] leading-[38px] text-ink text-center space-y-0">
        <p>الكلامُ هو اللفظُ المركّبُ المفيدُ بالوضعِ</p>
        <p>وأقسامُهُ ثلاثةٌ: اسمٌ، وفعلٌ، وحرفٌ جاءَ لمعنًى</p>
        <p>
          فَالاسمُ يُعرَفُ بِالخَفضِ{" "}
          <span className="bg-gold/20 rounded px-0.5">والتنوينِ</span>{" "}
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
      {/* Selected word */}
      <p className="font-arabic text-[22px] text-ink text-right" dir="rtl">
        والتنوينِ
      </p>

      {/* Translation */}
      <p className="text-[12px] text-gold">and the tanwin</p>

      {/* Root / pattern info */}
      <div className="text-[10px] text-gold leading-relaxed">
        <p>root: ن و ن</p>
        <p>pattern: تَفعِيل</p>
        <p>ma&apos;tuf &middot; majrur</p>
      </div>

      {/* I'rab section */}
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
      {/* Read (active) */}
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

      {/* Library */}
      <div className="flex flex-col items-center gap-0.5">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <rect x="3" y="2" width="12" height="14" rx="1.5" stroke="#2A1F17" strokeOpacity="0.4" strokeWidth="1.5" />
          <path d="M6 5H12M6 8H12M6 11H9" stroke="#2A1F17" strokeOpacity="0.4" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span className="text-[10px] text-ink/40">Library</span>
      </div>

      {/* Review */}
      <div className="flex flex-col items-center gap-0.5">
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <circle cx="9" cy="9" r="6.5" stroke="#2A1F17" strokeOpacity="0.4" strokeWidth="1.5" />
        </svg>
        <span className="text-[10px] text-ink/40">Review</span>
      </div>

      {/* Profile */}
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
  return (
    <div
      className="w-full max-w-[760px] rounded-[22px] p-2"
      style={{
        background: "linear-gradient(145deg, #3a3538 0%, #2a2628 100%)",
        boxShadow:
          "inset 0 1px 0 #FFFFFF14, 0 25px 80px #0000002E, 0 4px 16px #0000001A",
      }}
    >
      {/* Screen */}
      <div className="bg-white rounded-[14px] h-[480px] flex flex-col overflow-hidden">
        <AppBar />
        <div className="flex flex-1 min-h-0">
          <BookPage />
          <WordPanel />
        </div>
        <TabBar />
        {/* Home indicator */}
        <div className="flex justify-center pb-2">
          <div className="w-[100px] h-[3px] rounded-full bg-ink/20" />
        </div>
      </div>
    </div>
  );
}

/* ─── Hero ─── */

export default function Hero() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [referrerCode, setReferrerCode] = useState<string | null>(null);

  useEffect(() => {
    setReferrerCode(getReferralFromCookie());
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

      <IPadMockup />
    </section>
  );
}
