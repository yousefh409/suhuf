"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

type Mode = "login" | "signup";
type Step = "credentials" | "verify";

const inputClass =
  "w-full rounded-lg border border-ink/10 bg-parchment px-4 py-2.5 text-sm text-ink placeholder:text-ink/30 outline-none transition-colors focus:border-gold/40";
const primaryButtonClass =
  "w-full rounded-lg bg-ink px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-ink/90 disabled:opacity-50";

function CardShell({ subtitle, children }: { subtitle: string; children: ReactNode }) {
  return (
    <div className="w-full max-w-sm rounded-xl border border-ink/10 bg-parchment-warm p-7 shadow-[0_12px_40px_rgba(42,31,23,0.08)]">
      <div className="mb-6 flex flex-col items-center text-center">
        <Image src="/logo.png" alt="suhuf" width={40} height={40} className="rounded-xl" />
        <h1 className="mt-3 font-serif text-2xl leading-none text-ink">suhuf</h1>
        <p className="mt-1.5 text-sm text-ink/45">{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

export function LoginForm({ redirectTo }: { redirectTo: string }) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("credentials");
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function done() {
    router.push(redirectTo);
    router.refresh();
  }

  async function onSubmitCredentials(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setPending(true);
    const supabase = createClient();
    if (mode === "login") {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      setPending(false);
      if (error) return setError(error.message);
      done();
      return;
    }
    // signup
    const { data, error } = await supabase.auth.signUp({ email, password });
    setPending(false);
    if (error) return setError(error.message);
    if (data.session) {
      // Confirmation disabled — session issued immediately.
      done();
      return;
    }
    // Confirmation required — move to code entry.
    setStep("verify");
    setInfo(`We emailed a 6-digit code to ${email}.`);
  }

  async function onVerify(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    setPending(true);
    const supabase = createClient();
    const { error } = await supabase.auth.verifyOtp({
      email,
      token: code.trim(),
      type: "email",
    });
    setPending(false);
    if (error) return setError(error.message);
    done();
  }

  async function onResend() {
    setError(null);
    setInfo(null);
    setPending(true);
    const supabase = createClient();
    const { error } = await supabase.auth.resend({ type: "signup", email });
    setPending(false);
    if (error) return setError(error.message);
    setInfo("Code sent. Check your email.");
  }

  if (step === "verify") {
    return (
      <CardShell subtitle={`We emailed a 6-digit code to ${email}.`}>
        <form onSubmit={onVerify} className="space-y-3">
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            placeholder="123456"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className={`${inputClass} text-center tracking-[0.4em]`}
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          {info && <p className="text-sm text-gold">{info}</p>}
          <button type="submit" disabled={pending} className={primaryButtonClass}>
            {pending ? "…" : "Verify"}
          </button>
        </form>
        <div className="mt-4 flex items-center justify-between text-xs">
          <button
            type="button"
            onClick={onResend}
            disabled={pending}
            className="text-ink/50 transition-colors hover:text-gold disabled:opacity-50"
          >
            Resend code
          </button>
          <button
            type="button"
            onClick={() => {
              setStep("credentials");
              setError(null);
              setInfo(null);
              setCode("");
            }}
            className="text-ink/50 transition-colors hover:text-gold"
          >
            Back
          </button>
        </div>
      </CardShell>
    );
  }

  return (
    <CardShell subtitle={mode === "login" ? "Welcome back" : "Create your account"}>
      <div className="mb-4 flex gap-1 rounded-lg bg-ink/[0.04] p-1 text-sm font-medium">
        <button
          type="button"
          onClick={() => {
            setMode("login");
            setError(null);
          }}
          className={`flex-1 rounded-md px-3 py-1.5 transition-colors ${mode === "login" ? "bg-ink text-white" : "text-ink/60 hover:text-ink"}`}
        >
          Log in
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("signup");
            setError(null);
          }}
          className={`flex-1 rounded-md px-3 py-1.5 transition-colors ${mode === "signup" ? "bg-ink text-white" : "text-ink/60 hover:text-ink"}`}
        >
          Sign up
        </button>
      </div>

      <form onSubmit={onSubmitCredentials} className="space-y-3">
        <input
          type="email"
          required
          autoComplete="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={inputClass}
        />
        <input
          type="password"
          required
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={inputClass}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button type="submit" disabled={pending} className={primaryButtonClass}>
          {pending ? "…" : mode === "login" ? "Log in" : "Sign up"}
        </button>
      </form>
    </CardShell>
  );
}
