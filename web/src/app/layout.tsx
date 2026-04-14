import type { Metadata } from "next";
import { Instrument_Serif, DM_Sans, Amiri } from "next/font/google";
import PaperShader from "@/components/PaperShader";
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

const amiri = Amiri({
  weight: ["400", "700"],
  style: ["normal", "italic"],
  variable: "--font-amiri",
  display: "swap",
  subsets: ["arabic", "latin"],
});

export const metadata: Metadata = {
  title: "suhuf — Your Arabic readalong companion",
  description:
    "Read any classical Arabic text aloud. Suhuf listens, catches your grammar mistakes in real time, and explains why. Tap any word for instant grammar and translation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`h-full antialiased ${instrumentSerif.variable} ${dmSans.variable} ${amiri.variable}`}>
      <body className="min-h-full flex flex-col">
          <PaperShader
            style={{ position: "fixed", zIndex: -1 }}
          />
          {children}
        </body>
    </html>
  );
}
