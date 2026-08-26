"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

// --- Types ---
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

interface RunState {
  run_id: string;
  client_id: string;
  stage: string;
  raw_exhibitor_count: number;
  exhibitors: unknown[];
  itinerary: ItineraryStop[];
  candidate_events: EventCandidate[];
  error: string | null;
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

// --- Composant principal ---
export default function DashboardPage() {
  const [runState, setRunState] = useState<RunState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<MissionForm>(EMPTY_FORM);

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

  async function lancerRun() {
    if (!formValide) return;
    setLoading(true);
    setError(null);

    const payload: RunInput = {
      sector: form.sector.trim(),
      region: form.region.trim(),
      icp: {
        target_client_profile: form.targetClientProfile.trim(),
        objectives: form.objectives,
      },
    };

    try {
      const res = await fetch(`${API_BASE}/runs?client_id=demo-client`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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

  // Fait avancer le run d'un stage
  async function avancerRun() {
    if (!runState) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/runs/${runState.run_id}/advance`, {
        method: "POST",
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

  // Rafraîchit l'état du run depuis l'API
  async function rafraichir() {
    if (!runState) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/runs/${runState.run_id}`);
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const state: RunState = await res.json();
      setRunState(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }
  // Sélectionne un événement parmi ceux proposés par le Scout
  async function selectionnerEvenement(candidate: EventCandidate) {
    if (!runState) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/runs/${runState.run_id}/select-event`, {
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

  const stageActuel = runState?.stage ?? null;
  const pipelineTermine = stageActuel === "done" || stageActuel === "failed";

  return (
    <main className="p-8 max-w-6xl mx-auto">
      {/* Header */}
      <header className="mb-8 flex justify-between items-center border-b border-border pb-4">
        <h1 className="text-3xl font-bold uppercase tracking-widest">
          Centre de Commandement
        </h1>
        <div className="flex gap-3">
          {runState && (
            <Button onClick={rafraichir} disabled={loading}>
              Actualiser les statuts
            </Button>
          )}
        </div>
      </header>

      {/* Erreur API */}
      {error && (
        <div className="mb-6 border border-accent bg-bg-card p-4 text-accent font-mono text-sm">
          ⚠ {error}
        </div>
      )}
      {!runState && (
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
                  className="w-full bg-bg border border-border px-4 py-2 text-white focus:outline-none focus:border-accent"
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
                  className="w-full bg-bg border border-border px-4 py-2 text-white focus:outline-none focus:border-accent"
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
                  className="w-full bg-bg border border-border px-4 py-2 text-white focus:outline-none focus:border-accent resize-none"
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
                {loading ? "Initialisation…" : "Lancer la mission"}
              </Button>
            </div>
          </Card>
        </div>
      )}

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
                {runState?.raw_exhibitor_count ?? "—"}
              </span>
            </div>
            <div className="flex justify-between items-center border-b border-border pb-2">
              <span className="font-semibold uppercase text-sm">Cibles qualifiées</span>
              <span className="text-accent font-mono text-xl">
                {runState ? runState.exhibitors.length : "—"}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-semibold uppercase text-sm">Statut du pipeline</span>
              <span className="text-accent font-bold uppercase text-sm">
                {stageActuel ? (STAGE_LABELS[stageActuel] ?? stageActuel) : "Inactif"}
              </span>
            </div>
          </div>

          {/* Bouton avancer si run en cours et non terminé */}
          {runState &&
            !pipelineTermine &&
            stageActuel !== "awaiting_selection" && (
              <div className="mt-6">
                <Button onClick={avancerRun} disabled={loading}>
                  {loading ? "Exécution…" : "Avancer le pipeline"}
                </Button>
              </div>
            )}
        </Card>

        {/* Checkpoints */}
        <Card title="Checkpoints">
          <ul className="list-none space-y-3 font-semibold">
            {STAGE_ORDER.map((stage) => {
              const stageIndex = STAGE_ORDER.indexOf(stage);
              const currentIndex = stageActuel
                ? STAGE_ORDER.indexOf(stageActuel)
                : -1;
              const done = currentIndex > stageIndex ||
                (stageActuel === "done" && stageIndex <= 4);
              const active = stageActuel === stage;

              return (
                <li key={stage} className="flex items-center gap-3">
                  <span
                    className={
                      done
                        ? "text-accent font-bold"
                        : active
                        ? "text-accent font-bold animate-pulse"
                        : "text-border text-lg font-bold"
                    }
                  >
                    {done ? "✓" : active ? "▶" : "○"}
                  </span>
                  <span className={active ? "text-white" : done ? "text-white" : "text-border"}>
                    {STAGE_LABELS[stage] ?? stage}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>
      {/* Sélection d'événement — checkpoint humain */}
      {stageActuel === "awaiting_selection" && runState.candidate_events.length > 0 && (
        <div className="mt-8">
          <Card title="Sélectionner l'événement cible">
            <div className="space-y-4">
              {runState.candidate_events.map((candidate) => (
                <div
                  key={candidate.name}
                  className="border border-border p-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between"
                >
                  <div>
                    <p className="font-bold uppercase tracking-wide">{candidate.name}</p>
                    <p className="text-sm text-white/70">
                      {candidate.dates} — {candidate.location}
                    </p>
                    {candidate.exhibitor_count !== null && (
                      <p className="text-xs text-accent font-mono mt-1">
                        ~{candidate.exhibitor_count} exposants estimés
                      </p>
                    )}
                    {candidate.relevance_note && (
                      <p className="text-xs text-white/50 italic mt-1">
                        {candidate.relevance_note}
                      </p>
                    )}
                  </div>
                  <Button onClick={() => selectionnerEvenement(candidate)} disabled={loading}>
                    Choisir cet événement
                  </Button>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Itinéraire — affiché quand le run est DONE */}
      {runState?.itinerary && runState.itinerary.length > 0 && (
        <div className="mt-8">
          <Card title="Itinéraire de Mission">
            <div className="space-y-4">
              {runState.itinerary.map((stop) => (
                <div
                  key={stop.exhibitor_id}
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
                  <p className="font-bold uppercase tracking-wide">
                    {stop.exhibitor_name}
                  </p>
                  <p className="text-sm text-white/70">{stop.objective}</p>
                  {stop.justification && (
                    <p className="text-xs text-white/50 italic mt-1">
                      {stop.justification}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Message erreur du run */}
      {runState?.error && (
        <div className="mt-6 border border-border bg-bg-card p-4">
          <p className="text-accent font-bold uppercase text-sm mb-1">
            Erreur pipeline
          </p>
          <p className="text-white/70 text-sm font-mono">{runState.error}</p>
        </div>
      )}
    </main>
  );
}
