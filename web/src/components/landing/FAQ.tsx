"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { motion } from "motion/react";

const faqs = [
  {
    q: "Do I need to already know Arabic?",
    a: "No! Suhuf is designed for all levels. Beginners can start with fully diacritized texts and get real-time feedback on pronunciation. The AI adapts to your level and explains grammar in plain English.",
  },
  {
    q: "What texts are included in the library?",
    a: "We include over 10,000 Arabic books across grammar (like al-Ajrumiyyah), hadith sciences, theology, and more. New texts are added regularly based on user requests.",
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
];

const fadeUp = {
  hidden: { opacity: 0, y: 32 },
  visible: { opacity: 1, y: 0 },
};

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

      <motion.div
        variants={fadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-[720px] flex flex-col rounded-[20px] bg-white p-2 md:p-3"
      >
        {faqs.map((faq, i) => {
          const isOpen = openIndex === i;
          return (
            <div key={i}>
              <button
                onClick={() => setOpenIndex(isOpen ? null : i)}
                className={`w-full flex items-center justify-between px-5 md:px-6 py-5 text-left rounded-[14px] transition-colors ${
                  isOpen ? "bg-parchment" : "hover:bg-parchment/60"
                }`}
              >
                <span className="text-[15px] text-ink font-medium pr-4">
                  {faq.q}
                </span>
                <ChevronDown
                  className={`w-4 h-4 text-ink/30 flex-shrink-0 transition-transform duration-300 ${
                    isOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
              <div className={`faq-answer ${isOpen ? "open" : ""}`}>
                <div>
                  <p className="text-[14px] text-ink/50 leading-[1.7] px-5 md:px-6 pb-4 pt-1">
                    {faq.a}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </motion.div>
    </section>
  );
}
