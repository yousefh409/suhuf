"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowUp, Mic, BookOpen, Languages, ChevronRight, X } from "lucide-react";

const fadeUp = {
  hidden: { opacity: 0, y: 32 },
  visible: { opacity: 1, y: 0 },
};

const staggerContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1 } },
};

const upcomingFeatures = [
  {
    id: "lecture-notes",
    status: "In Progress",
    statusColor: "text-green-700 bg-green-700/10",
    title: "Integrated notes",
    description:
      "Notes built for Arabic \u2014 write alongside any text with full Apple Pencil support.",
  },
  {
    id: "auto-review",
    status: "Planned",
    statusColor: "text-ink/50 bg-ink/5",
    title: "Automatic review sessions",
    description:
      "Duolingo-style AI-powered reviews for everything you\u2019ve learned \u2014 so you never forget.",
  },
  {
    id: "memorization",
    status: "Planned",
    statusColor: "text-ink/50 bg-ink/5",
    title: "Memorization review",
    description:
      "Review poems and hadiths you\u2019ve memorized \u2014 recite aloud and get error detection on every word.",
  },
  {
    id: "upload-books",
    status: "Under Review",
    statusColor: "text-gold bg-gold/10",
    title: "Upload your own books",
    description: "Bring any Arabic text \u2014 upload your own PDF or paste text to read with full suhuf features.",
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
  const [modalError, setModalError] = useState("");
  const [pendingFeatureId, setPendingFeatureId] = useState<string | null>(null);
  const [suggestSent, setSuggestSent] = useState(false);

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
    setModalError("");
    try {
      const referrerCode = getReferralFromCookie();
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: modalEmail,
          signup_source: "feature_vote",
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
        const feature = upcomingFeatures.find((f) => f.id === pendingFeatureId);
        const featureParam = feature
          ? `&feature=${encodeURIComponent(feature.title + " — " + feature.description)}`
          : "";
        window.location.href = `/welcome?id=${data.id}&position=${data.position}&referralCode=${data.referral_code}${data.is_existing ? "&existing=true" : ""}${featureParam}`;
      } else {
        setModalError(data.error || "Something went wrong. Please try again.");
      }
    } catch {
      setModalError("Could not connect. Please check your internet and try again.");
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
    setSuggestSent(true);
    setTimeout(() => setSuggestSent(false), 3000);
  }

  return (
    <section id="features" className="w-full flex flex-col items-center px-6 md:px-[60px] py-16 md:py-24 gap-12">
      {/* Section header */}
      <motion.div
        variants={fadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.5 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="flex flex-col items-center gap-4"
      >
        <span className="text-[13px] uppercase tracking-[0.12em] font-semibold text-gold">
          Features
        </span>
        <h2 className="font-serif text-[36px] md:text-[48px] text-ink text-center leading-[1.15]">
          Everything you need{"\n"}to master classical Arabic.
        </h2>
      </motion.div>

      {/* Listen Along card */}
      <motion.div
        variants={fadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.15 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-[1320px] rounded-[20px] bg-white p-8 md:p-12 flex flex-col md:flex-row gap-10"
      >
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
            Read any Arabic text aloud. AI catches your mistakes.
          </h3>
          <p className="text-[16px] text-ink/55 leading-[26px] max-w-md">
            Open any classical text and start reading. Suhuf listens in
            real-time, highlights each word as you go, and stops you when
            something needs correcting.
          </p>
        </div>

        {/* Listen Along preview */}
        <div className="flex-1 rounded-[14px] bg-[#F5EEE499] flex flex-col items-center justify-center p-8 gap-4">
          {/* Reading text with highlighted word */}
          <p className="font-arabic text-[18px] text-ink/30 text-center leading-[32px]" dir="rtl">
            بِكُلِّ{" "}
            <span className="text-ink bg-gold/15 rounded px-1 border-b-2 border-gold">طَرِيقٍ</span>
            {" "}فما يزداد إلا توقدا
          </p>

          {/* Error correction banner */}
          <div className="w-full bg-parchment-warm rounded-xl px-4 py-3 flex items-center justify-center gap-4" dir="rtl">
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-[10px] uppercase tracking-wider text-red-500 font-semibold">YOU SAID</span>
              <span className="font-arabic text-[20px] text-red-500">طريقاً</span>
            </div>
            <span className="text-ink/25 text-lg">&rarr;</span>
            <div className="flex flex-col items-center gap-0.5">
              <span className="text-[10px] uppercase tracking-wider text-[#3A7D50] font-semibold">SHOULD BE</span>
              <span className="font-arabic text-[20px] text-[#3A7D50]">طريقٍ</span>
            </div>
          </div>

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
        </div>
      </motion.div>

      {/* Grammar + Translation row */}
      <div className="w-full max-w-[1320px] flex flex-col md:flex-row gap-6">
        {/* Grammar card */}
        <motion.div
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.15 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="flex-1 rounded-[20px] bg-white p-9 flex flex-col gap-5"
        >
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

          {/* Grammar preview — I3rab tab */}
          <div className="flex flex-col rounded-[14px] bg-parchment p-6 gap-4">
            {/* Word */}
            <div className="text-center">
              <p className="font-arabic text-[28px] text-ink leading-tight" dir="rtl">بِالخَفضِ</p>
              <p className="text-[12px] text-ink/40 italic mt-1">bil-khafḍi</p>
            </div>

            {/* I3rab analysis card */}
            <div className="bg-white rounded-[10px] p-4 flex flex-col gap-3">
              <div className="flex gap-6">
                <div>
                  <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">TYPE</p>
                  <p className="text-[14px] text-ink mt-0.5"><span className="font-arabic" dir="rtl">اسم</span> <span className="text-ink/50">noun</span></p>
                </div>
                <div>
                  <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">CASE</p>
                  <p className="text-[14px] text-ink mt-0.5"><span className="font-arabic" dir="rtl">مجرور</span> <span className="text-ink/50">genitive</span></p>
                </div>
              </div>
              <div>
                <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">ROLE</p>
                <p className="text-[14px] text-ink mt-0.5"><span className="font-arabic" dir="rtl">اسم مجرور بحرف الجر</span></p>
                <p className="text-[11px] text-ink/45 mt-0.5">noun governed by preposition</p>
              </div>
              <div>
                <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">MARKER</p>
                <p className="text-[14px] text-ink mt-0.5"><span className="font-arabic" dir="rtl">كسرة</span> <span className="text-ink/50">kasra</span></p>
              </div>
              <div className="flex gap-6">
                <div>
                  <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">ROOT</p>
                  <p className="font-arabic text-[14px] text-ink mt-0.5" dir="rtl">خ ف ض</p>
                  <p className="text-[11px] text-ink/40">to lower</p>
                </div>
                <div>
                  <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">PATTERN</p>
                  <p className="font-arabic text-[14px] text-ink mt-0.5" dir="rtl">فَعْل</p>
                </div>
              </div>
              <div>
                <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">WHY THIS CASE?</p>
                <p className="text-[13px] text-ink/55 leading-snug mt-1">
                  After the preposition بِ, the noun takes jar (kasra). This is one of the core rules of Arabic grammar.
                </p>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Translation card */}
        <motion.div
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.15 }}
          transition={{ duration: 0.6, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
          className="flex-1 rounded-[20px] bg-white p-9 flex flex-col gap-5"
        >
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

          {/* Translation preview — Translation tab */}
          <div className="flex flex-col rounded-[14px] bg-parchment p-6 gap-4">
            {/* Word */}
            <div className="text-center">
              <p className="font-arabic text-[28px] text-ink leading-tight" dir="rtl">الكَلامُ</p>
              <p className="text-[12px] text-ink/40 italic mt-1">al-kalāmu</p>
            </div>

            {/* Translation content card */}
            <div className="bg-white rounded-[10px] p-4 flex flex-col gap-3">
              <div>
                <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">MEANING</p>
                <p className="text-[15px] text-ink mt-0.5">speech, utterance, discourse</p>
              </div>
              <div className="flex gap-6">
                <div>
                  <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">ROOT</p>
                  <p className="font-arabic text-[14px] text-ink mt-0.5" dir="rtl">ك ل م</p>
                  <p className="text-[11px] text-ink/40">to speak</p>
                </div>
                <div>
                  <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">PATTERN</p>
                  <p className="font-arabic text-[14px] text-ink mt-0.5" dir="rtl">فَعَال</p>
                </div>
              </div>
              <div>
                <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">IN THIS SENTENCE</p>
                <p className="text-[12px] text-ink/55 leading-snug mt-0.5">
                  &ldquo;Speech&rdquo; &mdash; the composed utterance that conveys meaning by convention.
                </p>
              </div>
              <div>
                <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">EXPLANATION</p>
                <p className="text-[12px] text-ink/55 leading-snug mt-0.5">
                  In Arabic grammar, <span className="font-medium text-ink/70">al-kalām</span> refers specifically to a complete, meaningful utterance composed of two or more words that conveys an independent meaning. It is one of the first terms introduced in classical grammar texts like the Ājurrūmiyyah, distinguishing purposeful speech from isolated words or incomplete phrases.
                </p>
              </div>
              <div>
                <p className="text-[10px] text-gold uppercase font-semibold tracking-wider">FROM THE SAME ROOT</p>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  <span className="text-[11px] text-ink/60 bg-parchment rounded-full px-2.5 py-0.5"><span className="font-arabic" dir="rtl">كَلِمَة</span> word</span>
                  <span className="text-[11px] text-ink/60 bg-parchment rounded-full px-2.5 py-0.5"><span className="font-arabic" dir="rtl">مُتَكَلِّم</span> speaker</span>
                  <span className="text-[11px] text-ink/60 bg-parchment rounded-full px-2.5 py-0.5"><span className="font-arabic" dir="rtl">تَكَلَّمَ</span> to speak</span>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Upcoming features row */}
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        className="w-full max-w-[1320px] flex gap-3 lg:gap-4 overflow-x-auto pb-2 scrollbar-hide lg:grid lg:grid-cols-4 lg:overflow-visible lg:pb-0"
      >
        {upcomingFeatures.map((f) => (
          <motion.div
            key={f.id}
            variants={fadeUp}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="flex flex-col rounded-xl lg:rounded-2xl p-4 lg:p-6 gap-1.5 lg:gap-2 bg-white/70 border-[1.5px] border-dashed border-ink/12 min-w-[260px] lg:max-w-none shrink-0 lg:min-w-0 lg:shrink"
          >
            <span
              className={`text-[11px] uppercase tracking-[0.1em] font-semibold px-2 py-0.5 rounded-full w-fit ${f.statusColor}`}
            >
              {f.status}
            </span>
            <h4 className="font-serif text-[15px] lg:text-lg text-ink mt-0.5 lg:mt-1">{f.title}</h4>
            <p className="text-[11px] lg:text-xs text-ink/45 leading-[1.5] lg:leading-[1.6] flex-1">
              {f.description}
            </p>
            <button
              onClick={() => handleVote(f.id)}
              className={`flex items-center gap-1 lg:gap-1.5 mt-1.5 lg:mt-2 text-xs lg:text-sm px-2.5 lg:px-3 py-1 lg:py-1.5 rounded-full border w-fit transition-colors ${
                votedFeatures.has(f.id)
                  ? "border-gold/30 bg-gold/5 text-gold"
                  : "border-ink/10 text-ink/40 hover:border-ink/20 hover:text-ink/60"
              }`}
            >
              <ArrowUp className="w-3 h-3 lg:w-3.5 lg:h-3.5" />
              {votedFeatures.has(f.id) ? "Voted" : "Upvote"}
            </button>
          </motion.div>
        ))}
      </motion.div>

      {/* Suggest a feature */}
      <div className="flex flex-col items-center gap-3">
        {suggestSent ? (
          <p className="text-sm text-gold font-medium">Thanks for your suggestion!</p>
        ) : !showSuggest ? (
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
            className="flex items-center gap-2 text-sm font-medium text-gold hover:text-gold/80 transition-colors px-5 py-2.5 rounded-full border border-gold/20 bg-gold/5 hover:bg-gold/10"
          >
            Suggest a feature <ChevronRight className="w-4 h-4" />
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
      <AnimatePresence>
        {modalOpen && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center px-6"
            onClick={() => setModalOpen(false)}
          >
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 bg-ink/50"
            />

            {/* Modal */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
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

              {modalError && (
                <p className="text-[13px] text-red-500 text-center">{modalError}</p>
              )}
              <p className="text-[11px] text-ink/25 text-center">
                Free during beta &middot; No credit card required
              </p>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </section>
  );
}
