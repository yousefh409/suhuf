"use client";

import { useState, useEffect } from "react";
import { ArrowUp, Mic, BookOpen, Languages, ChevronRight, X } from "lucide-react";

const upcomingFeatures = [
  {
    id: "lecture-notes",
    status: "In Progress",
    statusColor: "text-green-700 bg-green-700/10",
    title: "Integrated lecture notes",
    description:
      "Read the sharh alongside the matn, with linked commentary.",
  },
  {
    id: "memorization",
    status: "Planned",
    statusColor: "text-ink/50 bg-ink/5",
    title: "Memorization review",
    description:
      "Spaced repetition for hifz \u2014 review what you\u2019ve memorized.",
  },
  {
    id: "hadith-chain",
    status: "Planned",
    statusColor: "text-ink/50 bg-ink/5",
    title: "Hadith chain visualizer",
    description: "Interactive isnad explorer \u2014 trace narration chains.",
  },
  {
    id: "learning-paths",
    status: "Under Review",
    statusColor: "text-gold bg-gold/10",
    title: "Structured learning paths",
    description: "Guided curricula from beginner to advanced.",
  },
];

function getReferralFromCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/suhuf_ref=([^;]+)/);
  return match ? match[1] : null;
}

export default function Features() {
  const [votedFeatures, setVotedFeatures] = useState<Set<string>>(new Set());
  const [showSuggest, setShowSuggest] = useState(false);
  const [suggestion, setSuggestion] = useState("");

  // Email modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalEmail, setModalEmail] = useState("");
  const [modalLoading, setModalLoading] = useState(false);
  const [pendingFeatureId, setPendingFeatureId] = useState<string | null>(null);

  // Close modal on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setModalOpen(false);
    }
    if (modalOpen) document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [modalOpen]);

  function handleVote(featureId: string) {
    const waitlistId = localStorage.getItem("suhuf_waitlist_id");
    if (!waitlistId) {
      setPendingFeatureId(featureId);
      setModalOpen(true);
      return;
    }

    if (votedFeatures.has(featureId)) return;

    setVotedFeatures((prev) => new Set([...prev, featureId]));

    fetch("/api/features/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        feature_id: featureId,
        waitlist_id: waitlistId,
      }),
    }).catch(() => {});
  }

  async function handleModalSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!modalEmail) return;
    setModalLoading(true);
    try {
      const referrerCode = getReferralFromCookie();
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: modalEmail,
          signup_source: "feature_vote",
          referral_code: referrerCode,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        // Find the feature they wanted to vote on and pre-fill it
        const feature = upcomingFeatures.find((f) => f.id === pendingFeatureId);
        const featureParam = feature
          ? `&feature=${encodeURIComponent(feature.title + " — " + feature.description)}`
          : "";
        window.location.href = `/welcome?id=${data.id}&position=${data.position}&referralCode=${data.referral_code}${data.is_existing ? "&existing=true" : ""}${featureParam}`;
      }
    } finally {
      setModalLoading(false);
    }
  }

  async function handleSuggest(e: React.FormEvent) {
    e.preventDefault();
    if (!suggestion.trim()) return;
    const waitlistId = localStorage.getItem("suhuf_waitlist_id");
    if (!waitlistId) {
      setPendingFeatureId(null);
      setModalOpen(true);
      return;
    }
    await fetch("/api/features/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        suggestion: suggestion.trim(),
        waitlist_id: waitlistId,
      }),
    });
    setSuggestion("");
    setShowSuggest(false);
  }

  return (
    <section id="features" className="w-full flex flex-col items-center px-6 md:px-[60px] py-16 md:py-24 gap-12">
      {/* Section header */}
      <div className="flex flex-col items-center gap-4">
        <span className="text-[13px] uppercase tracking-[0.12em] font-semibold text-gold">
          Features
        </span>
        <h2 className="font-serif text-[36px] md:text-[48px] text-ink text-center leading-[1.15]">
          Everything you need{"\n"}to master classical Arabic.
        </h2>
      </div>

      {/* Listen Along card */}
      <div className="w-full max-w-[1320px] rounded-[20px] bg-white p-8 md:p-12 flex flex-col md:flex-row gap-10">
        <div className="flex flex-col gap-4 flex-1">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gold/15 flex items-center justify-center shrink-0">
              <Mic className="w-4 h-4 text-gold" />
            </div>
            <span className="text-[13px] uppercase tracking-[0.12em] font-semibold text-gold">
              Listen Along
            </span>
          </div>
          <h3 className="font-serif text-[28px] md:text-[36px] text-ink leading-[1.2]">
            Read any Arabic text aloud. AI follows along.
          </h3>
          <p className="text-[16px] text-ink/55 leading-[26px] max-w-md">
            Open any classical text and start reading. Suhuf listens in
            real-time, highlights each word as you go, and stops you when
            something needs correcting.
          </p>
        </div>

        {/* Listen Along preview */}
        <div className="flex-1 rounded-[14px] bg-[#F5EEE499] flex flex-col items-center justify-center p-8 gap-5">
          {/* Chapter heading */}
          <p className="font-arabic text-[18px] text-ink text-center leading-[22px]" dir="rtl">
            بابُ الكلامِ
          </p>

          {/* Main Arabic text line */}
          <p className="font-arabic text-[20px] text-ink/30 text-center leading-[32px]" dir="rtl">
            المُفِيدُ بِالوَضعِ وأقسامُهُ ثلاثةٌ
          </p>

          {/* Listening pill */}
          <div className="flex items-center gap-2 rounded-[20px] bg-[#3A7D501A] px-4 py-2">
            <span className="w-[6px] h-[6px] rounded-full bg-[#C4A060] shrink-0" />
            <span className="text-[12px] text-[#3A7D50] leading-[16px]">
              Listening...
            </span>
            <span className="text-[11px] text-[#3A7D5080] tracking-[2px] leading-[14px]">
              ▎▌▎▍▎▌▎
            </span>
          </div>

          {/* Faded final line */}
          <p className="font-arabic text-[16px] text-ink/15 text-center leading-[20px]" dir="rtl">
            اسمٌ وفعلٌ وحرفٌ جاءَ لمعنىً
          </p>
        </div>
      </div>

      {/* Grammar + Translation row */}
      <div className="w-full max-w-[1320px] flex flex-col md:flex-row gap-6">
        {/* Grammar card */}
        <div className="flex-1 rounded-[20px] bg-white p-9 flex flex-col gap-5">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#F0EBE3] flex items-center justify-center shrink-0">
              <BookOpen className="w-4 h-4 text-ink/70" />
            </div>
            <span className="text-[13px] uppercase tracking-[0.12em] font-semibold text-gold">
              Grammar
            </span>
          </div>
          <h3 className="font-serif text-[24px] md:text-[28px] text-ink leading-[1.2]">
            I&apos;rab &amp; grammar{"\n"}for every word
          </h3>
          <p className="text-[14px] text-ink/55 leading-[20px]">
            Tap any word to see its full grammatical role &mdash; case, reason,
            and the rule behind it explained in plain English.
          </p>

          {/* Grammar preview */}
          <div className="flex flex-col rounded-[14px] bg-parchment p-6 gap-4">
            {/* Arabic text */}
            <p className="font-arabic text-[22px] text-ink text-center leading-[180%]" dir="rtl">
              فَالاسمُ يُعرَفُ بِالخَفضِ والتَنوينِ
            </p>

            {/* Error correction row */}
            <div className="flex items-center justify-center gap-3" dir="rtl">
              {/* Wrong pill */}
              <span className="font-arabic text-[18px] leading-[22px] text-[#D4483B] bg-[#D4483B22] border border-[#D4483B44] rounded-lg px-3 py-1">
                بِالخَفضَ
              </span>
              {/* Arrow */}
              <span className="text-[14px] text-[#7A6E62] leading-[18px]">
                &rarr;
              </span>
              {/* Correct pill */}
              <span className="font-arabic text-[18px] leading-[22px] text-[#5C7A54] bg-[#5C7A5422] border border-[#5C7A5444] rounded-lg px-3 py-1">
                بِالخَفضِ
              </span>
            </div>

            {/* Explanation callout */}
            <div className="flex items-start gap-2 bg-white rounded-[10px] px-4 py-3">
              <div className="w-[3px] min-h-[20px] self-stretch bg-[#D4483B] rounded-[2px] shrink-0" />
              <p className="text-[13px] leading-[160%] text-[#5A4F44]">
                After بِ, the noun takes kasra (خَفْضِ). You read it with fatha instead.
              </p>
            </div>
          </div>
        </div>

        {/* Translation card */}
        <div className="flex-1 rounded-[20px] bg-white p-9 flex flex-col gap-5">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#F0EBE3] flex items-center justify-center shrink-0">
              <Languages className="w-4 h-4 text-ink/70" />
            </div>
            <span className="text-[13px] uppercase tracking-[0.12em] font-semibold text-gold">
              Translation
            </span>
          </div>
          <h3 className="font-serif text-[24px] md:text-[28px] text-ink leading-[1.2]">
            Instant meaning{"\n"}for every word
          </h3>
          <p className="text-[14px] text-ink/55 leading-[20px]">
            Tap any word for its meaning, root letters, morphological pattern,
            and contextual translation.
          </p>

          {/* Translation preview */}
          <div className="flex flex-col rounded-[14px] bg-parchment p-6 gap-4">
            {/* Arabic text */}
            <p className="font-arabic text-[22px] text-ink text-center leading-[180%]" dir="rtl">
              الكَلامُ هوَ اللَّفظُ المُرَكَّبُ
            </p>

            {/* Word card */}
            <div className="flex flex-col bg-white rounded-[10px] p-4 gap-1">
              {/* Top row */}
              <div className="flex items-baseline gap-3" dir="rtl">
                <span className="font-arabic text-[24px] font-bold text-ink leading-[30px]">
                  الكَلامُ
                </span>
                <span className="text-[14px] text-[#7A6E62] leading-[18px]">
                  &mdash;
                </span>
                <span className="text-[16px] font-semibold text-ink leading-[20px]">
                  speech, utterance
                </span>
              </div>
              {/* Info line */}
              <p className="text-[12px] leading-[160%] text-[#7A6E62]" dir="rtl">
                Root: ك ل م &middot; Pattern: فَعَال &middot; Mubtada&apos; (marfu&apos;)
              </p>
            </div>

            {/* Translation quote */}
            <div className="bg-white rounded-[10px] px-4 py-3">
              <p className="text-[13px] italic leading-[160%] text-[#5A4F44]">
                &ldquo;Speech is the composed utterance...&rdquo;
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Upcoming features row */}
      <div className="w-full max-w-[1320px] grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {upcomingFeatures.map((f) => (
          <div
            key={f.id}
            className="flex flex-col rounded-2xl p-6 gap-2 bg-white/70 border-[1.5px] border-dashed border-ink/12"
          >
            <span
              className={`text-[11px] uppercase tracking-[0.1em] font-semibold px-2 py-0.5 rounded-full w-fit ${f.statusColor}`}
            >
              {f.status}
            </span>
            <h4 className="font-serif text-lg text-ink mt-1">{f.title}</h4>
            <p className="text-xs text-ink/45 leading-[1.6] flex-1">
              {f.description}
            </p>
            <button
              onClick={() => handleVote(f.id)}
              className={`flex items-center gap-1.5 mt-2 text-sm px-3 py-1.5 rounded-full border w-fit transition-colors ${
                votedFeatures.has(f.id)
                  ? "border-gold/30 bg-gold/5 text-gold"
                  : "border-ink/10 text-ink/40 hover:border-ink/20 hover:text-ink/60"
              }`}
            >
              <ArrowUp className="w-3.5 h-3.5" />
              {votedFeatures.has(f.id) ? "Voted" : "Upvote"}
            </button>
          </div>
        ))}
      </div>

      {/* Suggest a feature */}
      <div className="flex flex-col items-center gap-3">
        {!showSuggest ? (
          <button
            onClick={() => {
              const waitlistId = localStorage.getItem("suhuf_waitlist_id");
              if (!waitlistId) {
                setPendingFeatureId(null);
                setModalOpen(true);
              } else {
                setShowSuggest(true);
              }
            }}
            className="flex items-center gap-1 text-sm text-ink/40 hover:text-ink/60 transition-colors"
          >
            Suggest a feature <ChevronRight className="w-3.5 h-3.5" />
          </button>
        ) : (
          <form
            onSubmit={handleSuggest}
            className="flex items-center gap-2"
          >
            <input
              autoFocus
              type="text"
              maxLength={200}
              placeholder="What would you like to see?"
              value={suggestion}
              onChange={(e) => setSuggestion(e.target.value)}
              className="text-sm px-4 py-2 rounded-full border border-ink/10 bg-white/60 w-[280px] outline-none focus:border-gold/40"
            />
            <button
              type="submit"
              className="text-sm px-4 py-2 rounded-full bg-ink text-white hover:bg-ink/90"
            >
              Submit
            </button>
          </form>
        )}
      </div>

      {/* Email modal for non-waitlisted users */}
      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center px-6"
          onClick={() => setModalOpen(false)}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" />

          {/* Modal */}
          <div
            className="relative w-full max-w-[400px] rounded-2xl bg-white p-6 flex flex-col gap-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setModalOpen(false)}
              className="absolute top-4 right-4 text-ink/30 hover:text-ink/60 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>

            <div>
              <h3 className="font-serif text-[22px] text-ink leading-[1.2]">
                Join the waitlist to vote
              </h3>
              <p className="text-sm text-ink/45 mt-1.5 leading-[1.5]">
                Enter your email to get early access and have your voice heard.
              </p>
            </div>

            <form onSubmit={handleModalSubmit} className="flex flex-col gap-3">
              <input
                autoFocus
                type="email"
                required
                placeholder="Enter your email"
                value={modalEmail}
                onChange={(e) => setModalEmail(e.target.value)}
                className="w-full text-sm px-4 py-3 rounded-xl border border-ink/10 bg-parchment outline-none placeholder:text-ink/30 focus:border-gold/40"
              />
              <button
                type="submit"
                disabled={modalLoading}
                className="w-full rounded-xl py-3 bg-ink text-white text-sm font-medium hover:bg-ink/90 transition-colors disabled:opacity-70"
              >
                {modalLoading ? "Joining..." : "Get Early Access"}
              </button>
            </form>

            <p className="text-[11px] text-ink/25 text-center">
              Free during beta &middot; No credit card required
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
