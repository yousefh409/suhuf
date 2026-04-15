import Nav from "@/components/landing/Nav";
import Hero from "@/components/landing/Hero";
import SocialProof from "@/components/landing/SocialProof";
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
      <Features />
      <LibraryTeacher />
      <SocialProof />
      <DarkCTA />
      {/* <Pricing /> */}
      <FAQ />
      <Footer />
    </main>
  );
}
