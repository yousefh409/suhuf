import Nav from "@/components/landing/Nav";
import Hero from "@/components/landing/Hero";
import SocialProof from "@/components/landing/SocialProof";
import Features from "@/components/landing/Features";
import LibraryTeacher from "@/components/landing/LibraryTeacher";
import DarkCTA from "@/components/landing/DarkCTA";
import FAQ from "@/components/landing/FAQ";
import Footer from "@/components/landing/Footer";

export default function Home() {
  return (
    // Marketing landing is designed light (white cards, light device mockups);
    // keep it on the paper palette regardless of the user's app theme.
    <main
      data-app-theme="paper"
      className="flex flex-col items-center w-full min-h-screen bg-parchment text-ink"
    >
      <Nav />
      <Hero />
      <Features />
      <LibraryTeacher />
      <SocialProof />
      <DarkCTA />
      <FAQ />
      <Footer />
    </main>
  );
}
