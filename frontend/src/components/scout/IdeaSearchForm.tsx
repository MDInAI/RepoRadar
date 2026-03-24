"use client";

import { useState } from "react";
import { useCreateIdeaSearch } from "@/hooks/useIdeaScout";
import type { IdeaSearchDirection } from "@/api/idea-scout";

interface IdeaSearchFormProps {
  onCreated?: (searchId: number) => void;
}

export function IdeaSearchForm({ onCreated }: IdeaSearchFormProps) {
  const [ideaText, setIdeaText] = useState("");
  const [direction, setDirection] = useState<IdeaSearchDirection>("backward");
  const createMutation = useCreateIdeaSearch();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ideaText.trim()) return;
    const result = await createMutation.mutateAsync({
      idea_text: ideaText.trim(),
      direction,
    });
    setIdeaText("");
    onCreated?.(result.id);
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 items-end">
      <div className="flex-1">
        <label className="block text-xs text-neutral-400 mb-1">
          Idea or topic to search
        </label>
        <input
          type="text"
          value={ideaText}
          onChange={(e) => setIdeaText(e.target.value)}
          placeholder='e.g. "open source trading bot"'
          className="w-full px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label className="block text-xs text-neutral-400 mb-1">Direction</label>
        <select
          value={direction}
          onChange={(e) => setDirection(e.target.value as IdeaSearchDirection)}
          className="px-3 py-2 bg-neutral-800 border border-neutral-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="backward">Backward (historical)</option>
          <option value="forward">Forward (watch new)</option>
        </select>
      </div>
      <button
        type="submit"
        disabled={!ideaText.trim() || createMutation.isPending}
        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
      >
        {createMutation.isPending ? "Creating..." : "Start Search"}
      </button>
    </form>
  );
}
