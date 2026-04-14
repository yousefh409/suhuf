import Nav from "@/components/landing/Nav";
import Hero from "@/components/landing/Hero";
import SocialProof from "@/components/landing/SocialProof";
import BoldStatement from "@/components/landing/BoldStatement";
import Features from "@/components/landing/Features";
import LibraryTeacher from "@/components/landing/LibraryTeacher";
import DarkCTA from "@/components/landing/DarkCTA";
import Pricing from "@/components/landing/Pricing";
import FAQ from "@/components/landing/FAQ";
import Footer from "@/components/landing/Footer";

export default function Home() {
  return (
    <main className="flex flex-col items-center w-full">
      <Nav />
      <Hero />
      <SocialProof />
      <BoldStatement />
      <Features />
      <LibraryTeacher />
      <DarkCTA />
      <Pricing />
      <FAQ />
      <Footer />
    </main>
  );
}
