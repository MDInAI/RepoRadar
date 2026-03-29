"use client";

import { useTriggerCombiner, useTriggerDeepSynthesis } from "@/hooks/useSynthesis";
import { useState } from "react";
import { ObsessionContextFormDialog } from "./ObsessionContextFormDialog";

interface SynthesisControlDockProps {
  familyId: number | null;
  memberCount: number;
  onRunCreated?: (runId: number) => void;
}

export function SynthesisControlDock({ familyId, memberCount, onRunCreated }: SynthesisControlDockProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [showDeepConfirm, setShowDeepConfirm] = useState(false);
  const [showObsessionForm, setShowObsessionForm] = useState(false);
  const [successRunId, setSuccessRunId] = useState<number | null>(null);
  const [successContextId, setSuccessContextId] = useState<number | null>(null);
  const triggerCombiner = useTriggerCombiner();
  const triggerDeepSynthesis = useTriggerDeepSynthesis();

  const canTrigger = familyId !== null && memberCount >= 2 && memberCount <= 3;
  const canDeepSynthesize = familyId !== null && memberCount >= 1;
  const canSpawnObsession = familyId !== null && memberCount >= 1;

  const handleDeepSynthesis = () => {
    if (!familyId) return;
    triggerDeepSynthesis.mutate(familyId, {
      onSuccess: (data) => {
        setShowDeepConfirm(false);
        setSuccessRunId(data.id);
        setTimeout(() => setSuccessRunId(null), 5000);
        onRunCreated?.(data.id);
      },
      onError: (error) => {
        alert(`Failed to trigger deep synthesis: ${error.message}`);
      },
    });
  };

  const handleTrigger = () => {
    if (!familyId) return;
    triggerCombiner.mutate(
      { idea_family_id: familyId },
      {
        onSuccess: (data) => {
          setShowConfirm(false);
          setSuccessRunId(data.id);
          setTimeout(() => setSuccessRunId(null), 5000);
          onRunCreated?.(data.id);
        },
        onError: (error) => {
          alert(`Failed to trigger combiner: ${error.message}`);
        },
      }
    );
  };

  return (
    <div className="border-t border-neutral-800 p-4 bg-neutral-900/50">
      <h3 className="text-sm font-semibold mb-3">Synthesis Actions</h3>

      {successRunId && (
        <div className="mb-3 p-3 bg-green-900/20 border border-green-800 rounded-lg text-sm">
          <span className="text-green-400">Combiner synthesis started! Run #{successRunId}</span>
        </div>
      )}

      {successContextId && (
        <div className="mb-3 p-3 bg-green-900/20 border border-green-800 rounded-lg text-sm">
          <span className="text-green-400">Obsession Agent created! </span>
          <button
            onClick={() => {
              const event = new CustomEvent('view-obsession-context', { detail: { contextId: successContextId } });
              window.dispatchEvent(event);
              setSuccessContextId(null);
            }}
            className="text-green-300 underline hover:text-green-200"
          >
            View details
          </button>
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <button
          disabled={!canTrigger || triggerCombiner.isPending}
          onClick={() => setShowConfirm(true)}
          title={!canTrigger ? "Family must have 2-3 repositories" : "Trigger Combiner synthesis"}
          className={`px-4 py-2 rounded-lg text-sm ${
            canTrigger && !triggerCombiner.isPending
              ? "bg-blue-600 hover:bg-blue-700 text-white"
              : "bg-neutral-800 text-neutral-500 cursor-not-allowed"
          }`}
        >
          {triggerCombiner.isPending ? "Starting..." : "Trigger Combiner"}
        </button>
        <button
          disabled={!canDeepSynthesize || triggerDeepSynthesis.isPending}
          onClick={() => setShowDeepConfirm(true)}
          title={!canDeepSynthesize ? "Select a family with repositories" : "Run deep synthesis with Claude Opus + extended thinking"}
          className={`px-4 py-2 rounded-lg text-sm ${
            canDeepSynthesize && !triggerDeepSynthesis.isPending
              ? "bg-indigo-600 hover:bg-indigo-700 text-white"
              : "bg-neutral-800 text-neutral-500 cursor-not-allowed"
          }`}
        >
          {triggerDeepSynthesis.isPending ? "Starting..." : "Deep Synthesis"}
        </button>
        <button
          disabled={!canSpawnObsession}
          onClick={() => setShowObsessionForm(true)}
          title={!canSpawnObsession ? "Select a family with repositories" : "Spawn Obsession Agent"}
          className={`px-4 py-2 rounded-lg text-sm ${
            canSpawnObsession
              ? "bg-purple-600 hover:bg-purple-700 text-white"
              : "bg-neutral-800 text-neutral-500 cursor-not-allowed"
          }`}
        >
          Spawn Obsession Agent
        </button>
      </div>

      {showConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 max-w-md">
            <h3 className="text-lg font-semibold mb-2">Trigger Combiner?</h3>
            <p className="text-sm text-neutral-400 mb-4">
              This will analyze {memberCount} repositories and generate a composite business opportunity.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowConfirm(false)}
                className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded-lg text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleTrigger}
                disabled={triggerCombiner.isPending}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {showDeepConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-6 max-w-md">
            <h3 className="text-lg font-semibold mb-2">Run Deep Synthesis?</h3>
            <p className="text-sm text-neutral-400 mb-4">
              This will run Claude Opus with extended thinking to produce a comprehensive strategic analysis of all {memberCount} repositories in this family.
              This may take several minutes and will use significant API credits.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowDeepConfirm(false)}
                className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded-lg text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleDeepSynthesis}
                disabled={triggerDeepSynthesis.isPending}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-sm"
              >
                {triggerDeepSynthesis.isPending ? "Starting..." : "Run Deep Synthesis"}
              </button>
            </div>
          </div>
        </div>
      )}

      {showObsessionForm && familyId && (
        <ObsessionContextFormDialog
          ideaFamilyId={familyId}
          onClose={() => setShowObsessionForm(false)}
          onSuccess={(contextId) => {
            setShowObsessionForm(false);
            setSuccessContextId(contextId);
            setTimeout(() => setSuccessContextId(null), 10000);
          }}
        />
      )}
    </div>
  );
}
