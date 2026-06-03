import type { Metadata } from "next";
import {
  Instrument_Serif,
  DM_Sans,
  Scheherazade_New,
  Amiri,
  Noto_Naskh_Arabic,
} from "next/font/google";
import { cookies } from "next/headers";
import PaperShader from "@/components/PaperShader";
import { PreferencesProvider } from "@/components/preferences/PreferencesProvider";
import { PREFERENCES_COOKIE, parsePreferencesCookie } from "@/lib/preferences/cookie";
import "./globals.css";

const instrumentSerif = Instrument_Serif({
  weight: ["400"],
  style: ["normal", "italic"],
  variable: "--font-instrument-serif",
  display: "swap",
  subsets: ["latin"],
});

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  display: "swap",
  subsets: ["latin"],
});

const scheherazade = Scheherazade_New({
  weight: ["400", "700"],
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-scheherazade",
});

// Alternate Arabic reading faces, selectable in preferences. Activated via the
// --font-arabic override under [data-arabic-font] in globals.css.
const amiri = Amiri({
  weight: ["400", "700"],
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-amiri",
});

const notoNaskh = Noto_Naskh_Arabic({
  weight: ["400", "700"],
  subsets: ["arabic"],
  display: "swap",
  variable: "--font-noto-naskh",
});

export const metadata: Metadata = {
  title: "Suhuf — Your Arabic readalong companion",
  description:
    "Read any classical Arabic text aloud. Suhuf listens, catches your grammar mistakes in real time, and explains why. Tap any word for instant grammar and translation.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Read preferences from the cookie so the theme + reading attributes are on
  // <html> at first paint (no flash). This opts the app into dynamic rendering.
  const raw = (await cookies()).get(PREFERENCES_COOKIE)?.value;
  const prefs = parsePreferencesCookie(raw);

  const fontVars = `${instrumentSerif.variable} ${dmSans.variable} ${scheherazade.variable} ${amiri.variable} ${notoNaskh.variable}`;

  return (
    <html
      lang="en"
      className={`h-full antialiased ${fontVars}`}
      data-app-theme={prefs.theme}
      data-text-size={prefs.textSize}
      data-line-spacing={prefs.lineSpacing}
      data-arabic-font={prefs.arabicFont}
    >
      <body className="min-h-full flex flex-col">
        <PaperShader style={{ position: "fixed", zIndex: -1 }} />
        <PreferencesProvider initial={prefs}>{children}</PreferencesProvider>
      </body>
    </html>
  );
}
