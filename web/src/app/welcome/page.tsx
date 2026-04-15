"use client";

import { useSearchParams } from "next/navigation";
import { useState, useEffect, Suspense } from "react";
import { Check, Copy, ArrowRight } from "lucide-react";

const interests = [
  "Recitation & pronunciation",
  "Grammar (nahw/sarf)",
  "Classical text reading",
  "Hadith studies",
  "Memorization (hifz)",
  "Teaching Arabic",
];

function WelcomeContent() {
  const params = useSearchParams();
  const paramId = params.get("id") || "";
  const paramPosition = params.get("position") || "";
  const paramReferralCode = params.get("referralCode") || "";
  const paramIsExisting = params.get("existing") === "true";
  const prefillFeature = params.get("feature") || "";

  const [userId, setUserId] = useState(paramId);
  const [position, setPosition] = useState(paramPosition);
  const [referralCode, setReferralCode] = useState(paramReferralCode);
  const [isExisting, setIsExisting] = useState(paramIsExisting);
  const [selectedInterests, setSelectedInterests] = useState<string[]>([]);
  const [featureRequest, setFeatureRequest] = useState(prefillFeature);
  const [submitted, setSubmitted] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loadingUser, setLoadingUser] = useState(!paramId);
  const [origin, setOrigin] = useState("");

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  const referralLink = `${origin}/r/${referralCode}`;

  // If no URL params, try loading from cookie
  useEffect(() => {
    if (paramId) {
      localStorage.setItem("suhuf_waitlist_id", paramId);
      setLoadingUser(false);
      return;
    }
    fetch("/api/waitlist/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.user) {
          setUserId(data.user.id);
          setPosition(String(data.user.position));
          setReferralCode(data.user.referral_code);
          setIsExisting(true);
          localStorage.setItem("suhuf_waitlist_id", data.user.id);
          // Pre-fill saved responses
          if (data.user.interest_areas?.length) {
            setSelectedInterests(data.user.interest_areas);
            setSubmitted(true);
          }
          if (data.user.feature_request) {
            setFeatureRequest(data.user.feature_request);
            setSubmitted(true);
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoadingUser(false));
  }, [paramId]);

  function toggleInterest(interest: string) {
    setSelectedInterests((prev) =>
      prev.includes(interest)
        ? prev.filter((i) => i !== interest)
        : [...prev, interest]
    );
  }

  async function handleSubmit() {
    await fetch("/api/waitlist/update", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: userId,
        interest_areas: selectedInterests,
        feature_request: featureRequest,
      }),
    });
    setSubmitted(true);
  }

  function copyLink() {
    navigator.clipboard.writeText(referralLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loadingUser) {
    return <div className="min-h-screen bg-parchment" />;
  }

  if (!userId && !loadingUser) {
    return (
      <div className="min-h-screen bg-parchment flex items-center justify-center px-6 py-16">
        <div className="text-center">
          <p className="text-ink/45 text-base mb-4">No waitlist signup found.</p>
          <a href="/#waitlist" className="text-sm text-gold hover:text-gold/80 transition-colors">
            Join the waitlist
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-parchment flex items-center justify-center px-6 py-16">
      <div className="w-full max-w-[520px] flex flex-col items-center gap-8">
        <a href="/" className="font-serif italic text-[22px] text-ink">
          suhuf
        </a>

        <div className="text-center">
          <h1 className="font-serif text-[36px] text-ink leading-[1.2] mb-3">
            {isExisting ? "Welcome back!" : `You're #${position}`}
          </h1>
          <p className="text-ink/45 text-base leading-[1.6]">
            {isExisting
              ? "You're already on the waitlist. Share your link to move up!"
              : "You're on the list. We'll notify you when it's your turn."}
          </p>
        </div>

        {/* Interest + feature request form */}
        {!submitted ? (
          <div className="w-full rounded-2xl bg-white p-6 flex flex-col gap-5">
            <div>
              <p className="text-sm font-medium text-ink mb-1">
                What are you most interested in?
              </p>
              <p className="text-xs text-ink/40">Select all that apply</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {interests.map((interest) => (
                <button
                  key={interest}
                  onClick={() => toggleInterest(interest)}
                  className={`text-sm px-4 py-2 rounded-full border transition-colors ${
                    selectedInterests.includes(interest)
                      ? "border-gold bg-gold/10 text-gold"
                      : "border-ink/10 text-ink/50 hover:border-ink/20"
                  }`}
                >
                  {interest}
                </button>
              ))}
            </div>

            <div>
              <p className="text-sm font-medium text-ink mb-2">
                Any feature you'd love to see?
              </p>
              <textarea
                placeholder="Tell us what would make suhuf perfect for you..."
                value={featureRequest}
                onChange={(e) => setFeatureRequest(e.target.value)}
                maxLength={500}
                rows={3}
                className="w-full text-sm px-4 py-3 rounded-xl border border-ink/10 bg-transparent outline-none resize-none placeholder:text-ink/25 focus:border-gold/40"
              />
            </div>

            <button
              onClick={handleSubmit}
              className="flex items-center justify-center gap-2 w-full rounded-xl py-3 bg-ink text-white text-sm font-medium hover:bg-ink/90 transition-colors"
            >
              Submit <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <div className="w-full rounded-2xl bg-white p-6 flex flex-col gap-4">
            <div className="flex items-center gap-2 mb-1">
              <Check className="w-5 h-5 text-gold" />
              <p className="text-sm font-medium text-ink">Your responses</p>
            </div>
            {selectedInterests.length > 0 && (
              <div>
                <p className="text-xs text-ink/40 mb-2">Interests</p>
                <div className="flex flex-wrap gap-1.5">
                  {selectedInterests.map((interest) => (
                    <span key={interest} className="text-xs px-3 py-1.5 rounded-full border border-gold/20 bg-gold/5 text-gold">
                      {interest}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {featureRequest && (
              <div>
                <p className="text-xs text-ink/40 mb-1">Feature request</p>
                <p className="text-sm text-ink/70 leading-relaxed">{featureRequest}</p>
              </div>
            )}
            {!selectedInterests.length && !featureRequest && (
              <p className="text-xs text-ink/40">Your feedback has been saved.</p>
            )}
          </div>
        )}

        {/* Referral link */}
        <div className="w-full rounded-2xl bg-white p-6 flex flex-col gap-3">
          <p className="text-sm font-medium text-ink">
            Share to move up the list
          </p>
          <p className="text-xs text-ink/40 leading-[1.5]">
            Each person who joins through your link moves you closer to the
            front.
          </p>
          <div className="flex items-center gap-2 mt-1">
            <div className="flex-1 rounded-lg bg-parchment px-4 py-2.5 text-sm text-ink/60 truncate">
              {referralLink}
            </div>
            <button
              onClick={copyLink}
              className="flex items-center gap-1.5 rounded-lg px-4 py-2.5 bg-ink text-white text-sm hover:bg-ink/90 transition-colors"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>

        <a
          href="/"
          className="text-sm text-ink/30 hover:text-ink/50 transition-colors"
        >
          Back to home
        </a>
      </div>
    </div>
  );
}

export default function WelcomePage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-parchment" />}>
      <WelcomeContent />
    </Suspense>
  );
}
