export default function Footer() {
  const links = {
    Product: [
      { label: "Features", href: "#features" },
      { label: "Pricing", href: "#pricing" },
      { label: "Roadmap", href: "#features" },
    ],
    Company: [
      { label: "About", href: "#" },
      { label: "Blog", href: "#" },
      { label: "Contact", href: "#" },
    ],
    Legal: [
      { label: "Privacy", href: "#" },
      { label: "Terms", href: "#" },
    ],
  };

  return (
    <footer className="w-full bg-dark px-6 md:px-[60px] pt-[60px] pb-10">
      <div className="max-w-[1320px] mx-auto flex flex-col gap-12">
        {/* Top row */}
        <div className="flex flex-col md:flex-row justify-between gap-10">
          {/* Brand */}
          <div className="flex flex-col gap-3 max-w-[280px]">
            <span className="font-serif italic text-[22px] text-white/90">
              suhuf
            </span>
            <p className="text-sm text-white/35 leading-[1.6]">
              Your AI-powered Arabic readalong companion. Built for students of
              knowledge.
            </p>
          </div>

          {/* Link columns */}
          <div className="flex gap-10 md:gap-16">
            {Object.entries(links).map(([heading, items]) => (
              <div key={heading} className="flex flex-col gap-4">
                <span className="text-xs text-white/25 uppercase tracking-[0.1em] font-medium">
                  {heading}
                </span>
                {items.map((link) => (
                  <a
                    key={link.label}
                    href={link.href}
                    className="text-sm text-white/50 hover:text-white/70 transition-colors"
                  >
                    {link.label}
                  </a>
                ))}
              </div>
            ))}
          </div>
        </div>

        {/* Bottom */}
        <div className="flex items-center justify-between pt-8 border-t border-white/8">
          <span className="text-xs text-white/25">
            2025 suhuf.ai. All rights reserved.
          </span>
          <div className="flex items-center gap-4">
            {/* X / Twitter */}
            <a href="#" className="text-white/25 hover:text-white/40">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
              </svg>
            </a>
            {/* Instagram */}
            <a href="#" className="text-white/25 hover:text-white/40">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="2" width="20" height="20" rx="5" />
                <circle cx="12" cy="12" r="5" />
                <circle cx="17.5" cy="6.5" r="1.5" fill="currentColor" stroke="none" />
              </svg>
            </a>
            {/* YouTube */}
            <a href="#" className="text-white/25 hover:text-white/40">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
              </svg>
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
