"use client";

import { useState } from "react";
import { useCreateIdeaSearch } from "@/hooks/useIdeaScout";
import type { IdeaSearchDirection } from "@/api/idea-scout";

interface IdeaSearchFormProps {
  onCreated?: (searchId: number) => void;
}

const IDEA_PROMPTS = [
  "Open source research assistant for compliance teams",
  "B2B workflow tools for RevOps operators",
  "Prediction-market tooling for serious retail traders",
];

function getErrorMessage(error: unknown): string | null {
  if (!error) return null;
  return error instanceof Error ? error.message : "Search creation failed.";
}

export function IdeaSearchForm({ onCreated }: IdeaSearchFormProps) {
  const [ideaText, setIdeaText] = useState("");
  const [direction, setDirection] = useState<IdeaSearchDirection>("backward");
  const createMutation = useCreateIdeaSearch();

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!ideaText.trim()) return;
    try {
      const result = await createMutation.mutateAsync({ idea_text: ideaText.trim(), direction });
      setIdeaText("");
      onCreated?.(result.id);
    } catch {
      // error shown inline
    }
  };

  const errorMessage = getErrorMessage(createMutation.error);

  return (
    <form onSubmit={handleSubmit} className="scout-form">
      <div className="scout-form-header">
        <h2 className="scout-form-title">New Scout Search</h2>
        <span className="scout-form-badge">LLM-assisted</span>
      </div>

      <label className="scout-form-label">What are we scouting?</label>
      <textarea
        value={ideaText}
        onChange={(e) => setIdeaText(e.target.value)}
        placeholder="Describe the market, workflow, or product idea to search for on GitHub"
        rows={4}
        className="scout-form-textarea"
      />

      <div className="scout-form-prompts">
        {IDEA_PROMPTS.map((prompt) => (
          <button key={prompt} type="button" className="scout-form-prompt" onClick={() => setIdeaText(prompt)}>
            {prompt}
          </button>
        ))}
      </div>

      <label className="scout-form-label" style={{ marginTop: 16 }}>Scan mode</label>
      <div className="scout-form-modes">
        <button
          type="button"
          className={`scout-form-mode ${direction === "backward" ? "scout-form-mode-on" : ""}`}
          onClick={() => setDirection("backward")}
        >
          <span className="scout-form-mode-name">Historical scan</span>
          <span className="scout-form-mode-desc">Search existing repos and past creation windows</span>
        </button>
        <button
          type="button"
          className={`scout-form-mode ${direction === "forward" ? "scout-form-mode-on" : ""}`}
          onClick={() => setDirection("forward")}
        >
          <span className="scout-form-mode-name">Forward watch</span>
          <span className="scout-form-mode-desc">Watch for newly created repos over time</span>
        </button>
      </div>

      {errorMessage ? <div className="scout-form-error">{errorMessage}</div> : null}

      <div className="scout-form-footer">
        <button
          type="submit"
          disabled={!ideaText.trim() || createMutation.isPending}
          className="scout-primary-btn"
        >
          {createMutation.isPending ? "Creating…" : "Create search"}
        </button>
      </div>
    </form>
  );
}
