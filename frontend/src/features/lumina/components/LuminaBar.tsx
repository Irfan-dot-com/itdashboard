import { useCallback, useEffect, useRef, useState } from 'react';

import { getLuminaAnswer, LUMINA_SUGGESTIONS, type LuminaAnswer } from '@/mocks/fixtures/lumina';
import { cn } from '@/lib/utils/cn';

interface ConversationEntry {
  id: string;
  question: string;
  answer: LuminaAnswer | null;
}

export function LuminaBar() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [conversation, setConversation] = useState<ConversationEntry[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const closePanel = useCallback(() => setOpen(false), []);

  useEffect(() => {
    function handleDocumentClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        closePanel();
      }
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') closePanel();
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    document.addEventListener('mousedown', handleDocumentClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleDocumentClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [closePanel]);

  const ask = useCallback((question: string) => {
    const trimmed = question.trim();
    if (!trimmed) return;
    const id = `${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
    setConversation((prev) => [...prev, { id, question: trimmed, answer: null }]);
    setValue('');
    window.setTimeout(() => {
      const answer = getLuminaAnswer(trimmed);
      setConversation((prev) => prev.map((entry) => (entry.id === id ? { ...entry, answer } : entry)));
    }, 600 + Math.random() * 400);
  }, []);

  const clear = useCallback(() => setConversation([]), []);

  return (
    <div ref={containerRef} className="relative flex-1 max-w-[520px]">
      <div
        className={cn(
          'flex items-center gap-2.5 rounded-[20px] border bg-surface px-3.5 py-1.5 text-xs text-text2 transition-colors',
          open ? 'border-teal shadow-[0_0_0_3px_rgba(62,193,164,0.10)]' : 'border-border hover:border-border3',
        )}
        onClick={() => inputRef.current?.focus()}
      >
        <span className="border-r border-border2 pr-2 text-[9.5px] font-semibold uppercase tracking-wider text-teal">
          Lumina
        </span>
        <svg className="h-3 w-3 text-text3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4}>
          <circle cx="7" cy="7" r="4.5" />
          <path d="M11 11l3 3" />
        </svg>
        <input
          ref={inputRef}
          type="text"
          placeholder="Ask anything about the estate…"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && value.trim()) ask(value);
          }}
          autoComplete="off"
          className="flex-1 border-none bg-transparent text-xs text-text outline-none"
        />
        <span className="rounded-[3px] border border-border2 bg-surface2 px-1.5 py-[2px] font-mono text-[9.5px] text-text3">
          ⌘K
        </span>
      </div>

      {open ? (
        <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-30 flex max-h-[520px] flex-col overflow-hidden rounded-token-lg border border-border2 bg-surface shadow-[0_8px_32px_rgba(0,0,0,0.40)]">
          {conversation.length === 0 ? (
            <div className="p-2">
              <div className="px-2.5 pt-2 pb-1 text-[9px] font-semibold uppercase tracking-widest text-text3">
                Try asking
              </div>
              {LUMINA_SUGGESTIONS.map((suggestion) => (
                <button
                  type="button"
                  key={suggestion.question}
                  onClick={() => ask(suggestion.question)}
                  className="flex w-full items-center gap-2 rounded-[5px] px-2.5 py-1.5 text-left text-xs text-text2 hover:bg-surface2 hover:text-text"
                >
                  <svg className="h-2.5 w-2.5 flex-shrink-0 text-text3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.4}>
                    <path d="M3 11l3-3 3 3 4-5" />
                  </svg>
                  <span className="flex-1">{suggestion.question}</span>
                  <em className="ml-auto text-[10.5px] font-semibold not-italic text-teal">{suggestion.category}</em>
                </button>
              ))}
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto px-4 pt-3.5 scrollbar-thin">
              {conversation.map((entry) => (
                <div key={entry.id} className="mb-3.5">
                  <div className="border-b border-border pb-2.5 text-sm font-semibold text-text">
                    <span className="text-teal">❯ </span>
                    {entry.question}
                  </div>
                  <div className="mt-3 text-[12.5px] leading-relaxed text-text">
                    {entry.answer ? (
                      <>
                        <div className="mb-2 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-widest text-teal">
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-teal" />
                          {entry.answer.source}
                        </div>
                        <p>{entry.answer.paragraph}</p>
                        {entry.answer.rows.length > 0 ? (
                          <div className="mt-2.5 flex flex-col gap-1.5 rounded-token border border-teal-dim bg-teal-bg p-3 font-mono text-[11px]">
                            {entry.answer.rows.map((row) => (
                              <div key={row.label} className="flex justify-between gap-3.5">
                                <span className="text-text2">{row.label}</span>
                                <span>{row.value}</span>
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {entry.answer.followUp ? (
                          <p className="mt-2 text-xs text-text2">{entry.answer.followUp}</p>
                        ) : null}
                      </>
                    ) : (
                      <div className="flex items-center gap-1.5 text-text3">
                        <span className="inline-flex gap-1">
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text3" />
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text3 [animation-delay:0.15s]" />
                          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-text3 [animation-delay:0.30s]" />
                        </span>
                        <span className="text-[11px]">Lumina · thinking</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[10.5px] text-text3">
            <span>Lumina · powered by event spine</span>
            <button type="button" onClick={clear} className="font-medium hover:text-text">
              Clear
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
