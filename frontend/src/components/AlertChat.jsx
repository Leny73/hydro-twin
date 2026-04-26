import { useState, useRef, useEffect } from 'react';

/**
 * AlertChat.jsx — HydroSentry Context-Aware Alert Assistant
 * ===========================================================
 *
 * Drop this component anywhere inside AlertPanel. It sends the user's question
 * plus the current alert JSON to POST /chat-alert, so Claude can answer
 * questions grounded strictly in the live satellite/weather data.
 *
 * Props:
 *   region     – selected region object  { id, name, description, bbox }
 *   assessment – Lambda assessment       { status, confidence, reasoning, ... }
 */

const CHAT_ENDPOINT = (import.meta.env.VITE_API_ENDPOINT ?? '')
  .replace('/assess', '/chat-alert');

const SUGGESTED_QUESTIONS = [
  'Which areas are at highest risk?',
  'What actions should we take now?',
  'How long will this alert last?',
];

export default function AlertChat({ region, assessment, onClose }) {
  const isOverlay = Boolean(onClose);
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: `Hi — I'm **HydroSentry**. I have access to the live satellite and weather data for **${region?.name ?? 'this region'}**. Ask me anything about this alert.`,
    },
  ]);
  const [input,     setInput]     = useState('');
  const [loading,   setLoading]   = useState(false);
  const bottomRef   = useRef(null);
  const inputRef    = useRef(null);

  // Reset conversation when the region changes
  useEffect(() => {
    setMessages([{
      role: 'assistant',
      text: `Hi — I'm **HydroSentry**. I have access to the live satellite and weather data for **${region?.name ?? 'this region'}**. Ask me anything about this alert.`,
    }]);
    setInput('');
    setLoading(false);
  }, [region?.id]);

  // Auto-scroll to the latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const sendMessage = async (text) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: trimmed }]);
    setLoading(true);

    try {
      const res = await fetch(CHAT_ENDPOINT, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_message:  trimmed,
          alert_context: {
            region_id:   region?.id,
            region_name: region?.name,
            status:      assessment?.status,
            confidence:  assessment?.confidence,
            reasoning:   assessment?.reasoning,
          },
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMessages(prev => [...prev, { role: 'assistant', text: data.reply ?? '…' }]);
    } catch (err) {
      console.warn('[AlertChat] fetch failed:', err.message);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', text: '_HydroSentry is temporarily offline. Please retry in a moment._', isError: true },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className={`flex flex-col gap-2 overflow-hidden ${isOverlay ? 'h-full' : 'border border-cyan-900/60 rounded-xl bg-gray-900/60'}`}>

      {/* Header */}
      <div className={`flex items-center gap-2 px-4 ${isOverlay ? 'pt-4 pb-3 border-b border-gray-700/50' : 'px-3 pt-3 pb-1'}`}>
        {isOverlay && (
          <div className="sm:hidden w-full flex justify-center absolute top-2 left-0" aria-hidden="true">
            <div className="w-10 h-1 bg-gray-600 rounded-full" />
          </div>
        )}
        <span className="text-base" aria-hidden="true">💬</span>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] uppercase tracking-widest text-cyan-400 font-semibold">
            Ask HydroAgent
          </p>
          {isOverlay && region?.name && (
            <p className="text-[11px] text-gray-400 truncate mt-0.5">{region.name}</p>
          )}
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center
                       rounded-full bg-gray-800 hover:bg-gray-700 active:scale-90
                       text-gray-400 hover:text-white transition-all duration-150
                       cursor-pointer flex-shrink-0"
            aria-label="Close chat"
          >
            ✕
          </button>
        )}
      </div>

      {/* Message history */}
      <div
        className={`flex flex-col gap-2 px-3 overflow-y-auto ${isOverlay ? 'flex-1' : 'max-h-52'}`}
        role="log"
        aria-live="polite"
        aria-label="Chat history"
      >
        {messages.map((msg, i) => (
          <ChatBubble key={i} role={msg.role} text={msg.text} isError={msg.isError} />
        ))}

        {loading && (
          <div className="flex items-center gap-1.5 text-[11px] text-cyan-400 animate-pulse py-1">
            <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce [animation-delay:300ms]" />
            <span className="ml-1">HydroSentry is analyzing…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggested questions — only shown when chat is empty (just the greeting) */}
      {messages.length === 1 && !loading && (
        <div className="flex flex-wrap gap-1.5 px-3">
          {SUGGESTED_QUESTIONS.map(q => (
            <button
              key={q}
              onClick={() => sendMessage(q)}
              className="text-[10px] px-2.5 py-1 rounded-full
                         bg-cyan-950/60 border border-cyan-800/60 text-cyan-300
                         hover:bg-cyan-900/60 hover:border-cyan-700
                         transition-colors duration-150 cursor-pointer"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input row */}
      <form
        onSubmit={(e) => { e.preventDefault(); sendMessage(input); }}
        className="flex items-center gap-2 px-3 pb-3"
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder="Ask about this alert…"
          aria-label="Ask HydroAgent a question"
          className="flex-1 min-h-[40px] px-3 py-2 rounded-lg text-xs
                     bg-gray-800 border border-gray-700 text-white
                     placeholder-gray-500
                     focus:outline-none focus:border-cyan-600
                     disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          aria-label="Send message"
          className="min-h-[40px] min-w-[40px] flex items-center justify-center
                     rounded-lg bg-cyan-700 hover:bg-cyan-600 active:scale-95
                     text-white text-sm font-bold
                     transition-all duration-150 cursor-pointer
                     disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ↑
        </button>
      </form>
    </div>
  );
}

// ── ChatBubble — renders markdown bold/italic inline without react-markdown ──
function ChatBubble({ role, text, isError }) {
  const isUser = role === 'user';

  // Lightweight inline markdown: **bold**, *italic*, _italic_, `code`
  const renderInline = (raw) => {
    const parts = raw.split(/(\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_|`[^`]+`)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**'))
        return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>;
      if ((part.startsWith('*') && part.endsWith('*')) || (part.startsWith('_') && part.endsWith('_')))
        return <em key={i} className="italic text-gray-300">{part.slice(1, -1)}</em>;
      if (part.startsWith('`') && part.endsWith('`'))
        return <code key={i} className="px-1 bg-gray-900 rounded text-cyan-300 text-[10px]">{part.slice(1, -1)}</code>;
      return part;
    });
  };

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed
          ${isUser
            ? 'bg-cyan-800/70 text-white rounded-br-sm'
            : isError
            ? 'bg-red-950/50 border border-red-800/50 text-red-200 rounded-bl-sm'
            : 'bg-gray-800/80 text-gray-200 rounded-bl-sm'}`}
      >
        {text.split('\n').map((line, i) => (
          <p key={i} className={i > 0 ? 'mt-1' : ''}>{renderInline(line)}</p>
        ))}
      </div>
    </div>
  );
}
