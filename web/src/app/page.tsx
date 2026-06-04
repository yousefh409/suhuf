import { createClient } from "@/lib/supabase/server";
import Nav from "@/components/landing/Nav";
import Hero from "@/components/landing/Hero";
import SocialProof from "@/components/landing/SocialProof";
import Features from "@/components/landing/Features";
import LibraryTeacher from "@/components/landing/LibraryTeacher";
import DarkCTA from "@/components/landing/DarkCTA";
import FAQ from "@/components/landing/FAQ";
import Footer from "@/components/landing/Footer";

export default async function Home() {
  // Decide the nav's auth entry point. Guarded so the public landing never
  // breaks if auth is unreachable — fall back to the signed-out "Log in" link.
  let signedIn = false;
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    signedIn = !!user;
  } catch {
    signedIn = false;
  }

  return (
    // Marketing landing is designed light (white cards, light device mockups);
    // keep it on the paper palette regardless of the user's app theme.
    <main
      data-app-theme="paper"
      className="flex flex-col items-center w-full min-h-screen text-ink"
    >
      {/* Paper base behind the fixed PaperShader (layout.tsx, z-index -1). Kept
          transparent on <main> so the shader shows through; this layer supplies
          the light parchment so the landing stays light under sepia/night. */}
      <div aria-hidden className="fixed inset-0 bg-parchment" style={{ zIndex: -2 }} />
      <Nav signedIn={signedIn} />
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
