import { Check } from "lucide-react";

const plans = [
  {
    name: "Free",
    price: "$0",
    period: "/month",
    description: "Perfect for getting started with Arabic reading practice.",
    features: [
      "3 reading sessions / day",
      "Basic pronunciation feedback",
      "Limited word lookups",
      "Grammar correction",
      "Smart review",
    ],
    cta: "Get started",
    featured: false,
  },
  {
    name: "Monthly",
    price: "$7.99",
    period: "/month",
    description: "Full access to all features. Cancel anytime.",
    features: [
      "Unlimited reading sessions",
      "Advanced pronunciation AI",
      "Unlimited word lookups",
      "Live grammar correction",
      "Smart review system",
    ],
    cta: "Subscribe now",
    featured: true,
    badge: "Most Popular",
  },
  {
    name: "Annual",
    price: "$59.99",
    period: "/year",
    badge: "Save 37%",
    description:
      "Best value \u2014 everything included at a discount.",
    features: [
      "Everything in Monthly",
      "Priority support",
      "Early access to new features",
    ],
    cta: "Choose annual",
    featured: false,
  },
];

export default function Pricing() {
  return (
    <section
      id="pricing"
      className="w-full flex flex-col items-center px-6 md:px-[60px] py-16 md:py-24 gap-12"
    >
      <div className="flex flex-col items-center gap-3">
        <span className="text-[13px] uppercase tracking-[0.12em] font-medium text-gold">
          Pricing
        </span>
        <h2 className="font-serif text-[32px] md:text-[40px] text-ink text-center leading-[1.2]">
          Simple, transparent pricing.
        </h2>
      </div>

      <div className="flex flex-col md:flex-row gap-5 w-full max-w-[960px]">
        {plans.map((plan) => (
          <div
            key={plan.name}
            className={`flex flex-col flex-1 rounded-2xl p-7 md:p-9 gap-6 bg-white ${
              plan.featured
                ? "border-2 border-gold relative"
                : "border border-ink/6"
            }`}
          >
            {plan.badge && (
              <span
                className={`text-[11px] uppercase tracking-[0.08em] font-semibold px-2.5 py-1 rounded-full w-fit ${
                  plan.featured
                    ? "bg-gold text-white absolute -top-3 right-6"
                    : "bg-gold/10 text-gold"
                }`}
              >
                {plan.badge}
              </span>
            )}

            <div className="flex flex-col gap-1">
              <span className="text-sm text-ink/50 font-medium">
                {plan.name}
              </span>
              <div className="flex items-baseline gap-1">
                <span className="font-serif text-[36px] text-ink">
                  {plan.price}
                </span>
                <span className="text-sm text-ink/35">{plan.period}</span>
              </div>
            </div>

            <p className="text-sm text-ink/45 leading-[1.5]">
              {plan.description}
            </p>

            <ul className="flex flex-col gap-3 flex-1">
              {plan.features.map((f) => (
                <li key={f} className="flex items-start gap-2.5">
                  <Check className="w-4 h-4 text-gold mt-0.5 flex-shrink-0" />
                  <span className="text-sm text-ink/60">{f}</span>
                </li>
              ))}
            </ul>

            <button
              className={`w-full rounded-xl py-3 text-sm font-medium transition-colors ${
                plan.featured
                  ? "bg-gold text-white hover:bg-gold/90"
                  : "bg-ink/5 text-ink/70 hover:bg-ink/10"
              }`}
            >
              {plan.cta}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
