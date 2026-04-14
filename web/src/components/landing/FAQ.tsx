"use client";

import { useState } from "react";
import { Plus, Minus } from "lucide-react";

const faqs = [
  {
    q: "Do I need to already know Arabic?",
    a: "No! Suhuf is designed for all levels. Beginners can start with fully diacritized texts and get real-time feedback on pronunciation. The AI adapts to your level and explains grammar in plain English.",
  },
  {
    q: "What texts are included in the library?",
    a: "We include dozens of classical Arabic texts across grammar (like al-Ajrumiyyah), hadith sciences, theology, and more. New texts are added regularly based on user requests.",
  },
  {
    q: "How does the AI pronunciation feedback work?",
    a: "As you read aloud, our AI listens in real-time using advanced speech recognition. It highlights each word as you read and flags any pronunciation or grammar errors, explaining exactly what went wrong and why.",
  },
  {
    q: "Is suhuf available on iPad, iPhone, and Android?",
    a: "Suhuf is launching first on iPad, optimized for the reading experience. iPhone support follows shortly after. Android is on our roadmap \u2014 vote for it in our feature tracker!",
  },
  {
    q: "Can I add my own texts or just use the library?",
    a: "During the initial launch, you\u2019ll have access to our curated library. Custom text uploads are on our roadmap and will be available in a future update.",
  },
  {
    q: "What\u2019s included in the free plan?",
    a: "The free plan includes 3 reading sessions per day, basic pronunciation feedback, limited word lookups, and access to grammar corrections. Upgrade for unlimited sessions and advanced features.",
  },
];

export default function FAQ() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <section className="w-full flex flex-col items-center px-6 md:px-[60px] py-16 md:py-24 gap-12">
      <div className="flex flex-col items-center gap-3">
        <span className="text-[13px] uppercase tracking-[0.12em] font-semibold text-gold">
          FAQ
        </span>
        <h2 className="font-serif text-[36px] md:text-[48px] text-ink text-center leading-[1.15]">
          Common questions.
        </h2>
      </div>

      <div className="w-full max-w-[720px] flex flex-col">
        {faqs.map((faq, i) => (
          <div
            key={i}
            className="border-b border-ink/10 last:border-b-0"
          >
            <button
              onClick={() => setOpenIndex(openIndex === i ? null : i)}
              className="w-full flex items-center justify-between py-7 text-left"
            >
              <span className="text-base text-ink font-medium pr-4">
                {faq.q}
              </span>
              {openIndex === i ? (
                <Minus className="w-4 h-4 text-ink/30 flex-shrink-0" />
              ) : (
                <Plus className="w-4 h-4 text-ink/30 flex-shrink-0" />
              )}
            </button>
            <div
              className={`faq-answer ${openIndex === i ? "open" : ""}`}
            >
              <div>
                <p className="text-sm text-ink/50 leading-[1.7] pb-7">
                  {faq.a}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
