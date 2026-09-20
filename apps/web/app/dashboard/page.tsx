"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { getToken, removeToken, authFetch, getMe } from "@/lib/api";


// ── Clé localStorage pour persistance du run_id entre les refreshs ────────────
const RUN_ID_KEY = "orbit_current_run_id";

// ── Types ─────────────────────────────────────────────────────────────────────

type Objective = "find_clients" | "find_partners" | "competitive_intel";

const OBJECTIVE_LABELS: Record<Objective, string> = {
  find_clients: "Identifier des clients",
  find_partners: "Identifier des partenaires",
  competitive_intel: "Renseignement concurrentiel",
};

interface MissionForm {
  sector: string;
  region: string;
  targetClientProfile: string;
  objectives: Objective[];
}

const EMPTY_FORM: MissionForm = {
  sector: "",
  region: "",
  targetClientProfile: "",
  objectives: [],
};

interface RunInput {
  sector: string;
  region: string;
  icp: {
    target_client_profile: string;
    objectives: string[];
  };
}

interface ItineraryStop {
  order: number;
  exhibitor_id: string;
  exhibitor_name: string;
  booth: string | null;
  time_slot: string | null;
  objective: string;
  justification: string;
}

interface EventCandidate {
  name: string;
  dates: string;
  location: string;
  exhibitor_count: number | null;
  source_url: string | null;
  relevance_note: string | null;
}

interface SelectedEvent {
  name: string;
  dates: string;
  location: string;
  exhibitor_count: number | null;
  source_url: string | null;
}

interface RunState {
  run_id: string;
  client_id: string;
  stage: string;
  raw_exhibitor_count: number;
  exhibitors: unknown[];
  itinerary: ItineraryStop[];
  candidate_events: EventCandidate[];
  selected_event: SelectedEvent | null;
  error: string | null;
  paused?: boolean;
  paused_at_stage?: string | null;
  paused_at_subphase?: string | null;
  low_confidence?: boolean;
  low_confidence_stages?: string[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STAGE_LABELS: Record<string, string> = {
  scout: "Reconnaissance en cours",
  awaiting_selection: "En attente de sélection",
  analyst: "Analyse des exposants",
  classifier: "Classification ICP",
  planner: "Génération de l'itinéraire",
  done: "Mission accomplie",
  failed: "Échec — voir erreur",
};

const STAGE_ORDER = ["scout", "analyst", "classifier", "planner", "done"];

// ── Helpers localStorage ───────────────────────────────────────────────────────

function saveRunId(runId: string) {
  if (typeof window !== "undefined") localStorage.setItem(RUN_ID_KEY, runId);
}

function getSavedRunId(): string | null {
  if (typeof window !== "undefined") return localStorage.getItem(RUN_ID_KEY);
  return null;
}

function clearRunId() {
  if (typeof window !== "undefined") localStorage.removeItem(RUN_ID_KEY);
}

// ── Composant Principal ────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter();
  const [runState, setRunState] = useState<RunState | null>(null);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<MissionForm>(EMPTY_FORM);
  const [liveLogs, setLiveLogs] = useState<string[]>([]);
  const [currentSubphase, setCurrentSubphase] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  // ── Historique des missions ──────────────────────────────────────────────────
  const [previousRuns, setPreviousRuns] = useState<RunState[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  // ── #11 : email de l'agent connecté ─────────────────────────────────────────
  const [userEmail, setUserEmail] = useState<string | null>(null);
  // ── #12 : détection de SSE bloqué (polling fallback) ─────────────────────────
  const sseLastEventRef = useRef<number>(Date.now());
  // ── Tentatives par événement (max 2 avant retrait de la liste) ───────────────
  const [eventAttempts, setEventAttempts] = useState<Record<string, number>>({});
  // ── Abandon de mission ───────────────────────────────────────────────────────
  const [showAbortConfirm, setShowAbortConfirm] = useState(false);
  const [abortedRunIds, setAbortedRunIds] = useState<Set<string>>(new Set());


  // ── #1 : Auth guard ─────────────────────────────────────────────────────────
  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/login");
    }
  }, [router]);

  // ── #2 + #3 : Restauration du run depuis localStorage au montage ───────────
  useEffect(() => {
    const token = getToken();
    if (!token) return;

    const savedRunId = getSavedRunId();
    if (!savedRunId) {
      setRestoring(false);
      return;
    }

    authFetch(`/runs/${savedRunId}`)
      .then(async (res) => {
        if (!res.ok) {
          clearRunId();
          return;
        }
        const state: RunState = await res.json();
        setRunState(state);
      })
      .catch(() => {
        clearRunId();
      })
      .finally(() => {
        setRestoring(false);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Chargement de l'historique des missions via GET /runs ──────────────────
  async function chargerHistorique() {
    setLoadingHistory(true);
    try {
      const res = await authFetch("/runs");
      if (!res.ok) return;
      const runs: RunState[] = await res.json();
      // Exclure les runs abandonnés + trier du plus récent au plus ancien
      setPreviousRuns(
        runs.reverse().filter((r) => !abortedRunIds.has(r.run_id))
      );
    } catch {
      // Silencieux — l'historique est une fonctionnalité secondaire
    } finally {
      setLoadingHistory(false);
    }
  }


  useEffect(() => {
    const token = getToken();
    if (!token) return;
    chargerHistorique();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── #11 : Chargement de l'email de l'agent via GET /auth/me ─────────────────
  useEffect(() => {
    getMe().then((user) => {
      if (user) setUserEmail(user.email);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── #12 : Polling fallback si le SSE ne reçoit plus d'événements ─────────────
  // Si aucun événement SSE n'arrive depuis >30s et que le run est en cours,
  // on appelle GET /runs/{id} toutes les 8s pour rester synchronisé.
  useEffect(() => {
    const STALE_THRESHOLD_MS = 30_000; // 30s sans événement SSE = considéré bloqué
    const POLL_INTERVAL_MS = 8_000;    // sondage toutes les 8s

    const interval = setInterval(() => {
      if (!runState?.run_id) return;
      // Ne pas sonder si le run est terminal ou en attente de sélection
      const isActive =
        runState.stage !== "done" &&
        runState.stage !== "failed" &&
        runState.stage !== "awaiting_selection" &&
        !runState.paused;

      if (!isActive) return;

      const msSinceLastEvent = Date.now() - sseLastEventRef.current;
      if (msSinceLastEvent > STALE_THRESHOLD_MS) {
        // SSE silencieux depuis trop longtemps — on rafraîchit par polling
        rafraichir();
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [runState?.run_id, runState?.stage, runState?.paused]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Déconnexion ─────────────────────────────────────────────────────────────
  function handleLogout() {
    if (eventSourceRef.current) eventSourceRef.current.close();
    clearRunId();
    removeToken();
    router.replace("/login");
  }

  // ── Démarrer une nouvelle mission depuis zéro ────────────────────────────────
  function nouvelle_mission() {
    if (eventSourceRef.current) eventSourceRef.current.close();
    clearRunId();
    setRunState(null);
    setLiveLogs([]);
    setCurrentSubphase(null);
    setError(null);
    // Rafraîchit l'historique pour que la mission qui vient de se terminer y apparaisse
    chargerHistorique();
  }

  // ── Abandonner la mission en cours (abort) ───────────────────────────────────
  // La mission abandonnée est blacklistée et n'apparaîtra pas dans l'historique.
  function abandonnerMission() {
    if (eventSourceRef.current) eventSourceRef.current.close();

    // Blackliste le run_id pour l'exclure de l'historique
    if (runState?.run_id) {
      setAbortedRunIds((prev) => new Set([...prev, runState.run_id]));
    }

    clearRunId();
    setRunState(null);
    setLiveLogs([]);
    setCurrentSubphase(null);
    setError(null);
    setEventAttempts({});
    setShowAbortConfirm(false);
    // Rafraîchit l'historique (le run avorté sera filtré par abortedRunIds)
    chargerHistorique();
  }

  // ── Ouvrir un run de l'historique ───────────────────────────────────────────
  async function ouvrirRun(runId: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`/runs/${runId}`);
      if (!res.ok) throw new Error("Run introuvable");
      const state: RunState = await res.json();
      saveRunId(state.run_id);
      setRunState(state);
      setLiveLogs([]);
      setCurrentSubphase(null);
      // Scroll vers le haut pour voir le Pipeline Tracker
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  // ── #SSE Stream Listener ────────────────────────────────────────────────────
  useEffect(() => {
    if (!runState?.run_id) return;

    // Fermer l'ancien stream
    if (eventSourceRef.current) eventSourceRef.current.close();

    // Pas de SSE si le run est déjà terminal
    if (runState.stage === "done" || runState.stage === "failed" || runState.paused) {
      return;
    }

    const sseUrl = `${API_BASE}/runs/${runState.run_id}/stream`;
    const es = new EventSource(sseUrl);
    eventSourceRef.current = es;

    es.onmessage = async (msg) => {
      try {
        const payload = JSON.parse(msg.data);
        const timestamp = new Date().toLocaleTimeString();
        // ── #12 : réinitialise le timer anti-stale à chaque événement reçu ──
        sseLastEventRef.current = Date.now();

        if (payload.event === "subphase_started") {

          setCurrentSubphase(
            `${payload.stage} → ${payload.subphase}${payload.attempt ? ` (essai ${payload.attempt})` : ""}`
          );
          setLiveLogs((prev) => [
            `[${timestamp}] ⚙️  Début sous-phase : ${payload.stage} › ${payload.subphase}`,
            ...prev.slice(0, 49),
          ]);
        } else if (payload.event === "subphase_completed") {
          setLiveLogs((prev) => [
            `[${timestamp}] ✓  Sous-phase terminée : ${payload.stage} › ${payload.subphase}`,
            ...prev.slice(0, 49),
          ]);
        } else if (payload.event === "judge_verdict") {
          setLiveLogs((prev) => [
            `[${timestamp}] ⚖️  Juge (${payload.stage}) : ${payload.verdict} · Score ${payload.score}/10 — ${payload.reasoning ?? ""}`,
            ...prev.slice(0, 49),
          ]);
        } else if (payload.event === "rework") {
          setLiveLogs((prev) => [
            `[${timestamp}] 🔁  Rework → ${payload.target_stage}`,
            ...prev.slice(0, 49),
          ]);
        } else if (payload.event === "forced_pass") {
          setLiveLogs((prev) => [
            `[${timestamp}] ⚠️  Validation avec tolérance (low_confidence)`,
            ...prev.slice(0, 49),
          ]);
        } else if (payload.event === "run_paused") {
          setLiveLogs((prev) => [
            `[${timestamp}] ⏸️  Run en pause à l'étape ${payload.stage}`,
            ...prev.slice(0, 49),
          ]);
          rafraichir();
          es.close();
        } else if (payload.event === "run_done") {
          // ── #5 : remettre currentSubphase à null quand le run se termine ──
          setCurrentSubphase(null);
          setLiveLogs((prev) => [
            `[${timestamp}] 🎉  Mission accomplie !`,
            ...prev.slice(0, 49),
          ]);
          rafraichir();
          es.close();
        } else if (payload.event === "stage_error") {
          setLiveLogs((prev) => [
            `[${timestamp}] ❌  Erreur : ${payload.error}`,
            ...prev.slice(0, 49),
          ]);
          rafraichir();
          es.close();
        }

        if (["stage_completed", "run_done", "run_paused", "stage_error"].includes(payload.event)) {
          rafraichir();
        }
      } catch {
        // payload non-JSON ignoré
      }
    };

    es.onerror = () => {
      // Le navigateur gère la reconnexion automatique
    };

    return () => {
      es.close();
    };
  }, [runState?.run_id, runState?.stage, runState?.paused]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Helpers formulaire ───────────────────────────────────────────────────────
  function toggleObjective(obj: Objective) {
    setForm((prev) => ({
      ...prev,
      objectives: prev.objectives.includes(obj)
        ? prev.objectives.filter((o) => o !== obj)
        : [...prev.objectives, obj],
    }));
  }

  const formValide =
    form.sector.trim() !== "" &&
    form.region.trim() !== "" &&
    form.targetClientProfile.trim() !== "" &&
    form.objectives.length > 0;

  // ── Actions API ──────────────────────────────────────────────────────────────

  async function lancerRun() {
    if (!formValide) return;
    setLoading(true);
    setError(null);
    setLiveLogs([]);
    setCurrentSubphase(null);

    const payload: RunInput = {
      sector: form.sector.trim(),
      region: form.region.trim(),
      icp: {
        target_client_profile: form.targetClientProfile.trim(),
        objectives: form.objectives,
      },
    };

    try {
      const res = await authFetch(`/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail.detail ?? `Erreur ${res.status}`);
      }

      const state: RunState = await res.json();
      saveRunId(state.run_id);
      setRunState(state);
      chargerHistorique(); // Met à jour la liste d'historique avec le nouveau run

    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function rafraichir() {
    if (!runState?.run_id) return;
    try {
      const res = await authFetch(`/runs/${runState.run_id}`);
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const state: RunState = await res.json();
      setRunState(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function selectionnerEvenement(candidate: EventCandidate) {
    if (!runState) return;
    setLoading(true);
    setError(null);

    // Enregistrer la tentative — chaque clic compte (même si l'API échoue)
    setEventAttempts((prev) => ({
      ...prev,
      [candidate.name]: (prev[candidate.name] ?? 0) + 1,
    }));

    try {
      const res = await authFetch(`/runs/${runState.run_id}/select-event`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: candidate.name,
          dates: candidate.dates,
          location: candidate.location,
          exhibitor_count: candidate.exhibitor_count,
          source_url: candidate.source_url,
        }),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail.detail ?? `Erreur ${res.status}`);
      }

      const state: RunState = await res.json();
      setRunState(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function mettreEnPause() {
    if (!runState) return;
    setLoading(true);
    try {
      const res = await authFetch(`/runs/${runState.run_id}/pause`, { method: "POST" });
      if (!res.ok) throw new Error("Impossible de mettre en pause");
      const updated = await res.json();
      setRunState(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function reprendreRun() {
    if (!runState) return;
    setLoading(true);
    try {
      const res = await authFetch(`/runs/${runState.run_id}/resume`, { method: "POST" });
      if (!res.ok) throw new Error("Impossible de reprendre le run");
      const updated = await res.json();
      setRunState(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function reessayerStage() {
    if (!runState) return;
    setLoading(true);
    try {
      const res = await authFetch(`/runs/${runState.run_id}/retry-stage`, { method: "POST" });
      if (!res.ok) throw new Error("Impossible de relancer le stage");
      const updated = await res.json();
      setRunState(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function telechargerPDF() {
    if (!runState) return;
    try {
      const res = await authFetch(`/runs/${runState.run_id}/export/pdf`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Erreur de génération PDF" }));
        throw new Error(err.detail ?? "Erreur de téléchargement");
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mission-${runState.run_id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  // ── Computed ─────────────────────────────────────────────────────────────────
  const stageActuel = runState?.stage ?? null;
  const pipelineTermine = stageActuel === "done" || stageActuel === "failed";
  const postSelection = ["analyst", "classifier", "planner", "done"].includes(stageActuel ?? "");

  // ── Rendu de restauration ────────────────────────────────────────────────────
  if (restoring) {
    return (
      <main className="min-h-screen bg-bg flex items-center justify-center">
        <div className="text-center">
          <p className="text-accent font-bold uppercase tracking-widest text-lg animate-pulse">
            Restauration de la mission…
          </p>
          <p className="text-neutral-500 text-sm mt-2">Récupération de l'état en cours</p>
        </div>
      </main>
    );
  }

  // ── Rendu Principal ──────────────────────────────────────────────────────────
  return (
    <main className="p-8 max-w-6xl mx-auto">

      {/* ── Modal de confirmation d'abandon ─────────────────────────────────── */}
      {showAbortConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-bg-card border border-red-500/40 p-8 max-w-md w-full mx-4">
            <h2 className="text-xl font-bold uppercase tracking-widest text-white mb-2">
              Abandonner la mission ?
            </h2>
            <p className="text-red-400 font-semibold text-sm uppercase tracking-wide mb-4">
              ⚠ Cette action est irréversible
            </p>
            <p className="text-white/60 text-sm mb-6 leading-relaxed">
              Toutes les données de la mission en cours seront perdues — exposants extraits, événement sélectionné, itinéraire partiel. La mission <span className="font-mono text-white/80">#{runState?.run_id?.slice(0, 8)}</span> ne sera pas enregistrée dans l'historique.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowAbortConfirm(false)}
                className="text-sm font-bold uppercase tracking-wider border border-border px-5 py-2 hover:border-white/40 hover:text-white transition-colors text-neutral-400"
              >
                Annuler
              </button>
              <button
                onClick={abandonnerMission}
                className="text-sm font-bold uppercase tracking-wider border border-red-500 text-red-400 bg-red-500/10 px-5 py-2 hover:bg-red-500 hover:text-white transition-colors"
              >
                Confirmer l'abandon
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="mb-8 flex justify-between items-start border-b border-border pb-4">
        <div>
          <h1 className="text-3xl font-bold uppercase tracking-widest">
            Centre de Commandement
          </h1>
          {/* ── #11 : Email de l'agent connecté ── */}
          {userEmail && (
            <div className="flex items-center gap-2 mt-2">
              <span className="w-2 h-2 rounded-full bg-accent shrink-0" />
              <span className="text-sm font-semibold text-white tracking-wide">
                {userEmail}
              </span>
            </div>
          )}
        </div>
        <div className="flex gap-3 items-center flex-wrap justify-end">
          {/* ── #13 : Bouton Actualiser visible dès qu'un run existe ── */}
          {runState && (
            <Button onClick={rafraichir} disabled={loading}>
              Actualiser
            </Button>
          )}
          {/* ── Bouton Abandonner — visible uniquement si run actif non terminal ── */}
          {runState && runState.stage !== "done" && (
            <button
              onClick={() => setShowAbortConfirm(true)}
              className="text-xs font-bold uppercase tracking-wider border border-red-500/40 text-red-400 px-4 py-2 hover:bg-red-500/10 transition-colors"
            >
              ✕ Abandonner
            </button>
          )}
          <Button onClick={handleLogout}>Déconnexion</Button>
        </div>
      </header>

      {/* ── Erreur API ──────────────────────────────────────────────────────── */}
      {error && (
        <div className="mb-6 border border-accent bg-bg-card p-4 text-accent font-mono text-sm flex justify-between items-start gap-4">
          <span>⚠ {error}</span>
          <button
            onClick={() => setError(null)}
            className="text-neutral-500 hover:text-white text-xs uppercase tracking-wide shrink-0"
          >
            Fermer
          </button>
        </div>
      )}

      {/* ── #4 : Événement sélectionné (affiché pendant phases post-sélection) */}
      {runState?.selected_event && postSelection && (
        <div className="mb-6 bg-bg-card border border-border p-4 flex flex-col md:flex-row md:items-center gap-3 justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-accent mb-1">
              Événement cible
            </p>
            <p className="font-bold text-white uppercase tracking-wide">
              {runState.selected_event.name}
            </p>
            <p className="text-sm text-white/60 mt-0.5">
              {runState.selected_event.dates} — {runState.selected_event.location}
              {runState.selected_event.exhibitor_count && (
                <span className="ml-2 text-accent font-mono">
                  ~{runState.selected_event.exhibitor_count} exposants
                </span>
              )}
            </p>
          </div>
          {runState.selected_event.source_url && (
            <a
              href={runState.selected_event.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-neutral-500 hover:text-accent transition-colors uppercase tracking-wide shrink-0"
            >
              Source ↗
            </a>
          )}
        </div>
      )}


      {/* ── Historique des missions précédentes ─────────────────────────────── */}
      {!runState && (
        <div className="mb-8">
          <Card title="Mes missions précédentes">
            {loadingHistory ? (
              <p className="text-neutral-500 text-sm animate-pulse">Chargement…</p>
            ) : previousRuns.length === 0 ? (
              <div className="py-4 text-center">
                <p className="text-neutral-500 text-sm">Aucune mission enregistrée pour cette session.</p>
                <p className="text-neutral-600 text-xs mt-1">
                  Les missions sont stockées en mémoire — elles disparaissent si le backend redémarre.
                </p>
                <button
                  onClick={chargerHistorique}
                  disabled={loadingHistory}
                  className="mt-3 text-xs text-neutral-500 hover:text-accent transition-colors uppercase tracking-wide"
                >
                  ↺ Actualiser
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {previousRuns.map((run) => {
                  const isActive = run.run_id === getSavedRunId();
                  const stageBadgeColor =
                    run.stage === "done"
                      ? "text-green-400 border-green-500/30 bg-green-500/10"
                      : run.stage === "failed"
                      ? "text-red-400 border-red-500/30 bg-red-500/10"
                      : run.paused
                      ? "text-amber-400 border-amber-500/30 bg-amber-500/10"
                      : "text-accent border-accent/30 bg-accent/10";

                  return (
                    <div
                      key={run.run_id}
                      className={`border p-4 flex flex-col md:flex-row md:items-center gap-3 justify-between transition-colors ${
                        isActive ? "border-accent" : "border-border hover:border-border/60"
                      }`}
                    >
                      {/* Infos du run */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1 flex-wrap">
                          <span className={`text-xs font-bold uppercase tracking-wider border px-2 py-0.5 ${stageBadgeColor}`}>
                            {run.stage === "done"
                              ? "✓ Terminée"
                              : run.stage === "failed"
                              ? "✗ Échouée"
                              : run.paused
                              ? "⏸ En pause"
                              : STAGE_LABELS[run.stage] ?? run.stage}
                          </span>
                          <span className="text-xs font-mono text-neutral-600">
                            #{run.run_id.slice(0, 8)}
                          </span>
                          {run.low_confidence && (
                            <span className="text-xs text-amber-400">⚠ low confidence</span>
                          )}
                        </div>

                        {run.selected_event ? (
                          <p className="font-bold text-white uppercase tracking-wide text-sm truncate">
                            {run.selected_event.name}
                          </p>
                        ) : (
                          <p className="text-sm text-white/40 italic">Événement non sélectionné</p>
                        )}

                        <p className="text-xs text-neutral-500 mt-0.5">
                          {run.input?.sector} · {run.input?.region}
                          {run.itinerary?.length > 0 && (
                            <span className="ml-2 text-accent font-mono">
                              {run.itinerary.length} arrêts
                            </span>
                          )}
                        </p>
                      </div>

                      {/* Actions */}
                      <div className="flex gap-2 shrink-0 flex-wrap">
                        <button
                          onClick={() => ouvrirRun(run.run_id)}
                          disabled={loading}
                          className="text-xs font-bold uppercase tracking-wider border border-border px-3 py-1.5 hover:border-accent hover:text-accent transition-colors disabled:opacity-40"
                        >
                          Ouvrir
                        </button>
                        {run.stage === "done" && (
                          <button
                            onClick={async () => {
                              try {
                                const res = await authFetch(`/runs/${run.run_id}/export/pdf`);
                                if (!res.ok) throw new Error("Erreur PDF");
                                const blob = await res.blob();
                                const url = window.URL.createObjectURL(blob);
                                const a = document.createElement("a");
                                a.href = url;
                                a.download = `mission-${run.run_id.slice(0, 8)}.pdf`;
                                document.body.appendChild(a);
                                a.click();
                                window.URL.revokeObjectURL(url);
                                document.body.removeChild(a);
                              } catch {
                                setError("Impossible de télécharger le PDF");
                              }
                            }}
                            className="text-xs font-bold uppercase tracking-wider border border-accent/40 text-accent px-3 py-1.5 hover:bg-accent hover:text-white transition-colors"
                          >
                            📄 PDF
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}

                {/* Footer */}
                <div className="mt-4 pt-4 border-t border-border flex justify-between items-center">
                  <span className="text-xs text-neutral-600">
                    {previousRuns.length} mission{previousRuns.length > 1 ? "s" : ""} enregistrée{previousRuns.length > 1 ? "s" : ""}
                  </span>
                  <button
                    onClick={chargerHistorique}
                    disabled={loadingHistory}
                    className="text-xs text-neutral-500 hover:text-accent transition-colors uppercase tracking-wide disabled:opacity-40"
                  >
                    {loadingHistory ? "Actualisation…" : "↺ Actualiser"}
                  </button>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}



      {/* ── #10 : Spinner Scout ─────────────────────────────────────────────
           Affiché dans 2 cas :
           1. loading && !runState : POST /runs en cours (envoi du formulaire)
           2. runState.stage === "scout" : Scout background task en cours
      ──────────────────────────────────────────────────────────────────────── */}
      {(loading && !runState) || runState?.stage === "scout" ? (
        <div className="mb-8 bg-bg-card border border-accent/40 p-6">
          <div className="flex items-center gap-5">
            {/* Cercle pulsant */}
            <span className="relative flex h-6 w-6 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-50" />
              <span className="relative inline-flex rounded-full h-6 w-6 bg-accent" />
            </span>
            <div>
              <p className="text-base font-bold uppercase tracking-widest text-accent">
                {loading && !runState
                  ? "Initialisation du Scout…"
                  : "Le Scout analyse les événements…"}
              </p>
              <p className="text-sm text-neutral-400 mt-1">
                Recherche de salons en cours — cela peut prendre 30 à 60 secondes.
              </p>
            </div>
          </div>

          {/* Barre de progression indéterminée — animation CSS pure */}
          <div className="mt-5 h-1 bg-border rounded overflow-hidden relative">
            <div
              className="absolute top-0 left-0 h-full bg-accent rounded"
              style={{
                width: "35%",
                animation: "scout-slide 1.6s ease-in-out infinite",
              }}
            />
          </div>
        </div>
      ) : (
        /* ── Formulaire Mission (uniquement si pas de run actif) ─────────── */
        !runState && (
          <div className="mb-8">
            <Card title="Paramètres de la mission">
              <div className="space-y-5">
                <div>
                  <label className="block font-semibold uppercase text-sm mb-2">
                    Secteur
                  </label>
                  <input
                    type="text"
                    value={form.sector}
                    onChange={(e) => setForm({ ...form, sector: e.target.value })}
                    placeholder="Ex. Industrie 4.0"
                    className="w-full bg-bg border border-border px-4 py-2 text-white focus:outline-none focus:border-accent transition-colors"
                  />
                </div>

                <div>
                  <label className="block font-semibold uppercase text-sm mb-2">
                    Région
                  </label>
                  <input
                    type="text"
                    value={form.region}
                    onChange={(e) => setForm({ ...form, region: e.target.value })}
                    placeholder="Ex. France"
                    className="w-full bg-bg border border-border px-4 py-2 text-white focus:outline-none focus:border-accent transition-colors"
                  />
                </div>

                <div>
                  <label className="block font-semibold uppercase text-sm mb-2">
                    Profil client cible (ICP)
                  </label>
                  <textarea
                    value={form.targetClientProfile}
                    onChange={(e) =>
                      setForm({ ...form, targetClientProfile: e.target.value })
                    }
                    placeholder="Décrire le profil client à cibler"
                    rows={3}
                    className="w-full bg-bg border border-border px-4 py-2 text-white focus:outline-none focus:border-accent transition-colors resize-none"
                  />
                </div>

                <div>
                  <label className="block font-semibold uppercase text-sm mb-2">
                    Objectifs
                  </label>
                  <div className="flex flex-wrap gap-4">
                    {(Object.keys(OBJECTIVE_LABELS) as Objective[]).map((obj) => (
                      <label key={obj} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.objectives.includes(obj)}
                          onChange={() => toggleObjective(obj)}
                          className="accent-accent w-4 h-4"
                        />
                        <span className="text-sm">{OBJECTIVE_LABELS[obj]}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <Button onClick={lancerRun} disabled={loading || !formValide}>
                  Lancer la mission
                </Button>
              </div>
            </Card>
          </div>
        )
      )}

      {/* ── Grid Pipeline Tracker + Checkpoints ────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Pipeline Tracker */}
        <Card title="Pipeline Tracker">
          <div className="space-y-4">
            <div className="flex justify-between items-center border-b border-border pb-2">
              <span className="font-semibold uppercase text-sm">Run ID</span>
              <span className="text-accent font-mono text-sm truncate max-w-[160px]">
                {runState?.run_id ?? "—"}
              </span>
            </div>
            <div className="flex justify-between items-center border-b border-border pb-2">
              <span className="font-semibold uppercase text-sm">Exposants détectés</span>
              <span className="text-accent font-mono text-xl">
                {runState ? runState.raw_exhibitor_count : "—"}
              </span>
            </div>
            <div className="flex justify-between items-center border-b border-border pb-2">
              <span className="font-semibold uppercase text-sm">Cibles qualifiées</span>
              <span className="text-accent font-mono text-xl">
                {runState ? runState.exhibitors.length : "—"}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-semibold uppercase text-sm">Statut</span>
              <span className={`font-bold uppercase text-sm ${stageActuel === "failed" ? "text-red-500" : "text-accent"}`}>
                {stageActuel ? (STAGE_LABELS[stageActuel] ?? stageActuel) : "Inactif"}
              </span>
            </div>
          </div>

          {/* ── Contrôles ────────────────────────────────────────────────── */}
          {runState && (
            <div className="mt-6 flex flex-wrap gap-3 pt-4 border-t border-border">

              {/* Pause — visible si pipeline en cours et pas en pause */}
              {!pipelineTermine && !runState.paused && stageActuel !== "awaiting_selection" && (
                <Button onClick={mettreEnPause} disabled={loading}>
                  ⏸ Mettre en pause
                </Button>
              )}

              {/* Reprendre + Relancer l'étape — visibles en pause */}
              {runState.paused && (
                <>
                  <Button onClick={reprendreRun} disabled={loading}>
                    ▶ Reprendre
                  </Button>
                  <Button onClick={reessayerStage} disabled={loading}>
                    🔄 Relancer l'étape
                  </Button>
                </>
              )}

              {/* Export PDF — visible seulement si DONE */}
              {stageActuel === "done" && (
                <Button onClick={telechargerPDF} disabled={loading}>
                  📄 Télécharger l'itinéraire (PDF)
                </Button>
              )}

              {/* ── #6 : Bouton "Nouvelle mission" si FAILED ─────────────── */}
              {stageActuel === "failed" && (
                <Button onClick={nouvelle_mission}>
                  🔁 Relancer depuis le début
                </Button>
              )}

              {/* Bouton Nouvelle mission aussi sur DONE, pour relancer proprement */}
              {stageActuel === "done" && (
                <button
                  onClick={nouvelle_mission}
                  className="text-xs text-neutral-500 hover:text-accent transition-colors uppercase tracking-wide underline-offset-2 hover:underline"
                >
                  Nouvelle mission
                </button>
              )}
            </div>
          )}

          {/* Sous-phase active */}
          {currentSubphase && !pipelineTermine && (
            <div className="mt-4 text-xs font-mono text-accent border-t border-border pt-3">
              Phase active : <span className="text-white">{currentSubphase}</span>
            </div>
          )}

          {/* Avertissement low_confidence */}
          {runState?.low_confidence && (
            <div className="mt-3 text-xs text-amber-400 border border-amber-500/30 bg-amber-500/10 p-2">
              ⚠ Validé avec tolérance sur certains critères qualité.
              {runState.low_confidence_stages && runState.low_confidence_stages.length > 0 && (
                <span className="ml-1 text-amber-500/70">
                  ({runState.low_confidence_stages.join(", ")})
                </span>
              )}
            </div>
          )}
        </Card>

        {/* Checkpoints */}
        <Card title="Checkpoints">
          <ul className="list-none space-y-3 font-semibold">
            {STAGE_ORDER.map((stage) => {
              const stageIndex = STAGE_ORDER.indexOf(stage);
              const currentIndex = stageActuel ? STAGE_ORDER.indexOf(stageActuel) : -1;
              const done =
                currentIndex > stageIndex ||
                (stageActuel === "done" && stageIndex <= 4);
              const active = stageActuel === stage;

              return (
                <li key={stage} className="flex items-center gap-3">
                  <span
                    className={
                      done
                        ? "text-accent font-bold text-lg w-4"
                        : active
                        ? "text-accent font-bold animate-pulse text-lg w-4"
                        : "text-border text-lg font-bold w-4"
                    }
                  >
                    {done ? "✓" : active ? "▶" : "○"}
                  </span>
                  <span className={active ? "text-white" : done ? "text-white/80" : "text-border"}>
                    {STAGE_LABELS[stage] ?? stage}
                  </span>
                </li>
              );
            })}
          </ul>

          {/* Message FAILED dans les checkpoints */}
          {stageActuel === "failed" && (
            <div className="mt-4 border border-red-500/30 bg-red-500/10 p-3">
              <p className="text-red-400 font-bold uppercase text-xs mb-1">Pipeline échoué</p>
              <p className="text-white/60 text-xs font-mono">
                {runState?.error ?? "Erreur inconnue"}
              </p>
            </div>
          )}
        </Card>
      </div>

      {/* ── Console SSE en direct ───────────────────────────────────────────── */}
      {liveLogs.length > 0 && (
        <div className="mt-8">
          <Card title="Journal d'exécution en direct">
            <div className="bg-black/70 p-4 border border-border font-mono text-xs text-neutral-300 max-h-64 overflow-y-auto space-y-1.5">
              {liveLogs.map((log, idx) => (
                <div key={idx} className="leading-relaxed">
                  {log}
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* ── Sélection d'événement (checkpoint humain) ──────────────────────── */}
      {stageActuel === "awaiting_selection" && (runState?.candidate_events?.length ?? 0) > 0 && (() => {
        const MAX_ATTEMPTS = 2;

        // Événements définitivement retirés (≥ MAX_ATTEMPTS tentatives)
        const candidatesFiltres = (runState?.candidate_events ?? []).filter(
          (c) => (eventAttempts[c.name] ?? 0) < MAX_ATTEMPTS
        );

        // Nom de l'événement qui a échoué et qui reste en 2ème chance (1 tentative)
        const failedOnce = (runState?.candidate_events ?? []).filter(
          (c) => (eventAttempts[c.name] ?? 0) === 1
        ).map((c) => c.name);

        // Événements définitivement exclus (pour affichage d'info)
        const definitivelyRemoved = (runState?.candidate_events ?? []).filter(
          (c) => (eventAttempts[c.name] ?? 0) >= MAX_ATTEMPTS
        );

        return (
          <div className="mt-8">
            <Card title="Sélectionner l'événement cible">
              <p className="text-sm text-white/50 mb-4 italic">
                Le Scout a identifié les événements suivants. Choisissez celui qui correspond le mieux à votre mission.
              </p>

              {/* ── Bannière : événements définitivement retirés ── */}
              {definitivelyRemoved.length > 0 && (
                <div className="mb-5 border border-red-500/30 bg-red-500/10 p-3 flex gap-3 items-start">
                  <span className="text-red-400 text-lg shrink-0">✗</span>
                  <div>
                    <p className="text-red-400 font-bold uppercase text-xs tracking-wider">
                      Événement{definitivelyRemoved.length > 1 ? "s" : ""} retiré{definitivelyRemoved.length > 1 ? "s" : ""} — 2 tentatives échouées
                    </p>
                    <p className="text-white/60 text-xs mt-1">
                      {definitivelyRemoved.map((c) => (
                        <span key={c.name} className="font-semibold text-white/80 mr-1">{c.name}</span>
                      ))}
                      — l'analyse n'a pas pu extraire les exposants après 2 essais.
                    </p>
                  </div>
                </div>
              )}

              {candidatesFiltres.length === 0 ? (
                <div className="py-6 text-center border border-border">
                  <p className="text-white/40 text-sm italic">
                    Aucun autre événement disponible. Relancez le Scout avec des paramètres différents.
                  </p>
                  <button
                    onClick={nouvelle_mission}
                    className="mt-4 text-xs font-bold uppercase tracking-wider border border-border px-4 py-2 hover:border-accent hover:text-accent transition-colors"
                  >
                    🔁 Nouvelle mission
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  {candidatesFiltres.map((candidate, idx) => {
                    const attempts = eventAttempts[candidate.name] ?? 0;
                    const hasFailedOnce = failedOnce.includes(candidate.name);

                    return (
                      <div
                        key={`${candidate.name}-${idx}`}
                        className={`border p-4 flex flex-col gap-2 md:flex-row md:items-start md:justify-between transition-colors ${
                          hasFailedOnce
                            ? "border-amber-500/40 hover:border-amber-500/70"
                            : "border-border hover:border-accent/50"
                        }`}
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <p className="font-bold uppercase tracking-wide">{candidate.name}</p>
                            {/* Badge 2ème chance */}
                            {hasFailedOnce && (
                              <span className="text-xs font-bold uppercase tracking-wider border border-amber-500/40 text-amber-400 bg-amber-500/10 px-2 py-0.5">
                                ⚠ 2ème chance — 1 tentative échouée
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-white/70">
                            {candidate.dates} — {candidate.location}
                          </p>
                          {candidate.exhibitor_count !== null && (
                            <p className="text-xs text-accent font-mono mt-1">
                              ~{candidate.exhibitor_count} exposants estimés
                            </p>
                          )}
                          {candidate.relevance_note && (
                            <p className="text-xs text-white/40 italic mt-1">
                              {candidate.relevance_note}
                            </p>
                          )}
                          {hasFailedOnce && (
                            <p className="text-xs text-amber-400/70 mt-1">
                              Dernier retrait : impossible d'extraire les exposants. Un 2ème échec retirera cet événement définitivement.
                            </p>
                          )}
                          {candidate.source_url && (
                            <a
                              href={candidate.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-neutral-600 hover:text-accent transition-colors mt-1 inline-block"
                            >
                              Voir la source ↗
                            </a>
                          )}
                        </div>
                        <div className="shrink-0">
                          <Button
                            onClick={() => selectionnerEvenement(candidate)}
                            disabled={loading}
                          >
                            {hasFailedOnce ? "Réessayer" : "Choisir cet événement"}
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          </div>
        );
      })()}


      {/* ── Itinéraire final (DONE) ─────────────────────────────────────────── */}
      {runState?.itinerary && runState.itinerary.length > 0 && (
        <div className="mt-8">
          <Card title={`Itinéraire de Mission — ${runState.itinerary.length} arrêts`}>
            <div className="space-y-4">
              {runState.itinerary.map((stop) => (
                <div
                  key={stop.exhibitor_id ?? stop.order}
                  className="border border-border p-4 flex flex-col gap-1"
                >
                  <div className="flex justify-between items-center">
                    <span className="text-accent font-bold font-mono">
                      #{stop.order} — {stop.time_slot ?? "Horaire à définir"}
                    </span>
                    <span className="text-border text-xs font-mono uppercase">
                      {stop.booth ? `Stand ${stop.booth}` : "Stand inconnu"}
                    </span>
                  </div>
                  <p className="font-bold uppercase tracking-wide">{stop.exhibitor_name}</p>
                  <p className="text-sm text-white/70">{stop.objective}</p>
                  {stop.justification && (
                    <p className="text-xs text-white/40 italic mt-1">{stop.justification}</p>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </main>
  );
}
