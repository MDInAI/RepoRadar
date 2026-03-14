"use client";

import { FamilyListSidebar } from "@/components/ideas/FamilyListSidebar";
import { FamilyDetailView } from "@/components/ideas/FamilyDetailView";
import { FamilyFormDialog } from "@/components/ideas/FamilyFormDialog";
import { RepositorySelectorDialog } from "@/components/ideas/RepositorySelectorDialog";
import { SynthesisControlDock } from "@/components/ideas/SynthesisControlDock";
import { SynthesisRunsList } from "@/components/ideas/SynthesisRunsList";
import { SynthesisRunDetailDialog } from "@/components/ideas/SynthesisRunDetailDialog";
import { SynthesisHistoryPanel } from "@/components/ideas/SynthesisHistoryPanel";
import { SynthesisAnalyticsSummary } from "@/components/ideas/SynthesisAnalyticsSummary";
import { ObsessionContextPanel } from "@/components/ideas/ObsessionContextPanel";
import { ObsessionContextList } from "@/components/ideas/ObsessionContextList";
import { useIdeaFamily, useDeleteIdeaFamily } from "@/hooks/useIdeaFamilies";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, Suspense } from "react";

function IdeasPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const familyIdParam = searchParams.get("family");
  const parsedId = familyIdParam ? parseInt(familyIdParam, 10) : null;
  const selectedFamilyId = parsedId && !isNaN(parsedId) && parsedId > 0 ? parsedId : null;

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isRepoSelectorOpen, setIsRepoSelectorOpen] = useState(false);
  const [editingFamily, setEditingFamily] = useState<number | null>(null);
  const [viewingRunId, setViewingRunId] = useState<number | null>(null);
  const [showCompleted, setShowCompleted] = useState(true);

  const { data: selectedFamily } = useIdeaFamily(selectedFamilyId);
  const deleteMutation = useDeleteIdeaFamily();

  const handleSelectFamily = (familyId: number) => {
    router.push(`/ideas?family=${familyId}`);
  };

  const handleCreateFamily = () => {
    setEditingFamily(null);
    setIsFormOpen(true);
  };

  const handleEditFamily = () => {
    if (selectedFamilyId) {
      setEditingFamily(selectedFamilyId);
      setIsFormOpen(true);
    }
  };

  const handleDeleteFamily = async () => {
    if (selectedFamilyId && confirm("Are you sure you want to delete this family?")) {
      await deleteMutation.mutateAsync(selectedFamilyId);
      router.push("/ideas");
    }
  };

  const handleCloseForm = () => {
    setIsFormOpen(false);
    setEditingFamily(null);
  };

  return (
    <main className="flex h-screen">
      <FamilyListSidebar
        selectedFamilyId={selectedFamilyId}
        onSelectFamily={handleSelectFamily}
        onCreateFamily={handleCreateFamily}
      />

      {selectedFamilyId && selectedFamily ? (
        <div className="flex-1 flex flex-col">
          <FamilyDetailView
            familyId={selectedFamilyId}
            onEditFamily={handleEditFamily}
            onDeleteFamily={handleDeleteFamily}
            onAddRepositories={() => setIsRepoSelectorOpen(true)}
          />
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <SynthesisAnalyticsSummary familyId={selectedFamilyId} />
            <div>
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-lg font-semibold">Obsession Contexts</h3>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={showCompleted}
                    onChange={(e) => setShowCompleted(e.target.checked)}
                  />
                  Show completed
                </label>
              </div>
              <ObsessionContextList ideaFamilyId={selectedFamilyId} showCompleted={showCompleted} />
            </div>
            <ObsessionContextPanel ideaFamilyId={selectedFamilyId} />
            <SynthesisHistoryPanel familyId={selectedFamilyId} />
          </div>
          <SynthesisControlDock
            familyId={selectedFamilyId}
            memberCount={selectedFamily.member_count}
            onRunCreated={(runId) => setViewingRunId(runId)}
          />
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <h1 className="text-2xl font-bold mb-2">Ideas</h1>
          <p className="text-neutral-400">Select a family to view details</p>
        </div>
      )}

      <FamilyFormDialog
        isOpen={isFormOpen}
        onClose={handleCloseForm}
        family={editingFamily ? selectedFamily : null}
      />

      {selectedFamilyId && (
        <RepositorySelectorDialog
          isOpen={isRepoSelectorOpen}
          onClose={() => setIsRepoSelectorOpen(false)}
          familyId={selectedFamilyId}
          existingRepoIds={selectedFamily?.member_repository_ids || []}
        />
      )}

      {viewingRunId && (
        <SynthesisRunDetailDialog
          runId={viewingRunId}
          onClose={() => setViewingRunId(null)}
        />
      )}
    </main>
  );
}

export default function IdeasPage() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center">Loading...</div>}>
      <IdeasPageContent />
    </Suspense>
  );
}
