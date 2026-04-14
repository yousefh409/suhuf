"use client";

import { useState, useEffect } from "react";
import PaperShader from "@/components/PaperShader";

function getReferralFromCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/suhuf_ref=([^;]+)/);
  return match ? match[1] : null;
}


type WaitlistUser = {
  id: string;
  position: number;
  referral_code: string;
};

export default function DarkCTA() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
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
    setError("");
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          signup_source: "cta",
          referral_code: referrerCode,
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
    <section className="relative w-full flex flex-col items-center px-6 md:px-[60px] pt-[120px] pb-[80px] gap-7 bg-gold overflow-hidden">
      {/* Paper texture overlay */}
      <PaperShader />

      <h2 className="font-serif text-[40px] md:text-[56px] text-[#FFF8F0] text-center leading-[1.15] relative z-10">
        Start reading with{"\n"}confidence today.
      </h2>
      <p className="text-[#FFF8F0]/65 text-base md:text-[18px] text-center leading-7 max-w-[415px] relative z-10">
        Join hundreds of students already improving their classical Arabic with
        suhuf.
      </p>

      {!checkingCookie && existingUser ? (
        <a
          href={`/welcome?id=${existingUser.id}&position=${existingUser.position}&referralCode=${existingUser.referral_code}&existing=true`}
          className="flex items-center gap-3 relative z-10 rounded-full py-3 pl-6 pr-4 bg-white/15 border border-white/20 hover:bg-white/20 transition-colors"
        >
          <span className="text-sm text-[#FFF8F0]">
            You&apos;re <span className="font-semibold text-white">#{existingUser.position}</span> on the waitlist
          </span>
          <span className="text-xs text-white/80 font-medium flex items-center gap-1">
            View my spot
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M5.25 3.5L8.75 7L5.25 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </span>
        </a>
      ) : !checkingCookie ? (
        <>
          <form
            onSubmit={handleSubmit}
            className="flex items-center relative z-10 rounded-full py-1.5 pr-1.5 pl-7 gap-3 bg-white/15 border border-white/20"
          >
            <input
              type="email"
              required
              placeholder="Enter your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="text-base text-[#FFF8F0] bg-transparent outline-none placeholder:text-[#FFF8F0]/50 w-[160px] md:w-[200px]"
            />
            <button
              type="submit"
              disabled={loading}
              className="rounded-full px-6 py-3 bg-ink text-white text-sm font-medium hover:bg-ink/90 transition-colors disabled:opacity-70"
            >
              {loading ? "Joining..." : "Get Early Access"}
            </button>
          </form>

          {error && (
            <p className="text-red-300 text-[13px] relative z-10">{error}</p>
          )}
          <p className="text-white/50 text-[13px] relative z-10 mt-1">
            Free during beta &mdash; no credit card required.
          </p>
        </>
      ) : null}
    </section>
  );
}
