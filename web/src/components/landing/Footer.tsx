export default function Footer() {
  return (
    <footer className="w-full bg-dark px-6 md:px-[60px] pt-16 pb-10">
      <div className="max-w-[1320px] mx-auto flex flex-col gap-10">
        {/* Main row: brand left, links right */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div className="flex flex-col gap-2">
            <span className="font-serif italic text-[22px] text-white/90">
              suhuf
            </span>
            <p className="text-sm text-white/35 leading-[1.6] max-w-[300px]">
              Your AI-powered Arabic readalong companion. Built for students of
              knowledge.
            </p>
          </div>

          <div className="flex items-center gap-6">
            <a
              href="mailto:help@suhuf.ai"
              className="text-sm text-white/40 hover:text-white/60 transition-colors"
            >
              help@suhuf.ai
            </a>
            <span className="w-px h-4 bg-white/10" />
            <a
              href="https://instagram.com/suhufai"
              target="_blank"
              rel="noopener noreferrer"
              className="text-white/40 hover:text-white/60 transition-colors"
              aria-label="Instagram"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="2" width="20" height="20" rx="5" />
                <circle cx="12" cy="12" r="5" />
                <circle cx="17.5" cy="6.5" r="1.5" fill="currentColor" stroke="none" />
              </svg>
            </a>
          </div>
        </div>

        {/* Divider + copyright */}
        <div className="border-t border-white/8 pt-6">
          <span className="text-xs text-white/25">
            2025 suhuf.ai. All rights reserved.
          </span>
        </div>
      </div>
    </footer>
  );
}
