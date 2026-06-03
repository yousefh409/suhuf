"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

export default function SignOutMenuItem() {
  const router = useRouter();

  async function handleSignOut() {
    await createClient().auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={handleSignOut}
      className="flex items-center gap-2 text-sm text-ink/70 hover:text-ink transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/25 rounded"
    >
      <LogOut size={15} />
      Sign out
    </button>
  );
}
