'use client';

import { useState } from 'react';
import type { MemorySegmentResponse } from '@/lib/api/memory';

interface MemorySegmentViewerProps {
  segment: MemorySegmentResponse;
  onClose: () => void;
}

export function MemorySegmentViewer({ segment, onClose }: MemorySegmentViewerProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(segment.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const renderContent = () => {
    if (segment.content_type === 'json') {
      try {
        const parsed = JSON.parse(segment.content);
        return <pre className="text-sm overflow-auto">{JSON.stringify(parsed, null, 2)}</pre>;
      } catch {
        return <pre className="text-sm overflow-auto">{segment.content}</pre>;
      }
    }
    return <div className="text-sm whitespace-pre-wrap">{segment.content}</div>;
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-lg p-6 max-w-3xl w-full max-h-[80vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-lg font-semibold">{segment.segment_key}</h3>
            <span className="text-xs bg-gray-200 px-2 py-1 rounded">{segment.content_type}</span>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">✕</button>
        </div>

        <div className="flex-1 overflow-auto border rounded p-4 mb-4 bg-gray-50">
          {renderContent()}
        </div>

        <div className="flex gap-2">
          <button onClick={handleCopy} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
      </div>
    </div>
  );
}
