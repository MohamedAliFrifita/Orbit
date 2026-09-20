"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { loginUser, registerUser, saveToken } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function LoginPage() {
  const router = useRouter();
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isRegister) {
        await registerUser(email, password);
        const { access_token } = await loginUser(email, password);
        saveToken(access_token);
        router.push("/dashboard");
      } else {
        const { access_token } = await loginUser(email, password);
        saveToken(access_token);
        router.push("/dashboard");
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Erreur inattendue");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo / titre */}
        <div className="mb-8 text-center">
          <h1 className="text-4xl font-extrabold uppercase tracking-widest text-white">
            ORBIT
          </h1>
          <p className="text-sm text-neutral-400 mt-2 tracking-wide uppercase">
            Centre de commandement
          </p>
        </div>

        {/* Card formulaire */}
        <div className="bg-bg-card border border-border p-8">
          {/* Tabs Connexion / Inscription */}
          <div className="flex border-b border-border mb-6">
            <button
              type="button"
              onClick={() => { setIsRegister(false); setError(null); }}
              className={`flex-1 pb-3 text-sm font-bold uppercase tracking-wider transition-colors ${
                !isRegister
                  ? "border-b-2 border-accent text-accent"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              Connexion
            </button>
            <button
              type="button"
              onClick={() => { setIsRegister(true); setError(null); }}
              className={`flex-1 pb-3 text-sm font-bold uppercase tracking-wider transition-colors ${
                isRegister
                  ? "border-b-2 border-accent text-accent"
                  : "text-neutral-500 hover:text-neutral-300"
              }`}
            >
              Inscription
            </button>
          </div>

          {/* ── #9 : Utilise le composant Input réutilisable ── */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              id="email"
              label="Email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="agent@orbit.io"
            />

            <Input
              id="password"
              label="Mot de passe"
              type="password"
              autoComplete={isRegister ? "new-password" : "current-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />

            {/* Message d'erreur */}
            {error && (
              <p className="text-red-500 text-sm border border-red-500/30 bg-red-500/10 px-3 py-2">
                ⚠ {error}
              </p>
            )}

            <div className="mt-2">
              <Button type="submit" disabled={loading}>
                {loading
                  ? isRegister ? "Création du compte…" : "Connexion…"
                  : isRegister ? "Créer mon compte" : "Se connecter"}
              </Button>
            </div>
          </form>
        </div>

        {/* Lien retour accueil */}
        <p className="text-center text-xs text-neutral-600 mt-4 tracking-wide uppercase">
          <a href="/" className="hover:text-accent transition-colors">
            ← Accueil
          </a>
        </p>
      </div>
    </main>
  );
}
