import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { ChevronLeft, ChevronRight, X, Loader2 } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TYPE_COLORS = {
  MC:   '#22c55e',
  REG:  '#ef4444',
  MISC: '#3b82f6',
  MYS:  '#a855f7',
  BIG:  '#fbdd68',
};

/**
 * v32.0.0-alpha.40 — native trivia Play view.
 *
 * Reads the assembled slide list from `/api/trivia-viewer/{id}/slides`
 * (built by _assemble_slides_native) and renders each slide type in
 * a full-screen 16:9 layout. Arrow keys / click zones navigate, ESC exits.
 *
 * The prototype's Play surface renders PPTX-converted PNGs. Here we
 * render slides directly from JSON — no image conversion needed, and
 * the layout is fully responsive.
 */
export default function TriviaPlay() {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const presId = search.get('id');

  const [data, setData] = useState(null);
  const [idx, setIdx] = useState(0);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!presId) { setErr('No presentation id in URL'); return; }
    axios.get(`${API}/trivia-viewer/${presId}/slides`)
      .then(res => setData(res.data))
      .catch(e => setErr(e.response?.data?.detail || e.message));
  }, [presId]);

  const total = data?.slides?.length || 0;
  const slide = data?.slides?.[idx] || null;

  const next = useCallback(() => setIdx(i => Math.min(i + 1, total - 1)), [total]);
  const prev = useCallback(() => setIdx(i => Math.max(i - 1, 0)), []);
  const exit = useCallback(() => navigate(`/trivia/present?id=${presId}`), [navigate, presId]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); next(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); prev(); }
      else if (e.key === 'Escape') { e.preventDefault(); exit(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [next, prev, exit]);

  if (err) {
    return (
      <FullScreen>
        <div className="text-center">
          <p className="text-red-400 text-lg mb-4">{err}</p>
          <button onClick={exit} className="px-6 py-2 rounded-lg text-sm font-bold" style={{ backgroundColor: '#fbdd68', color: '#000e2a' }} data-testid="trivia-play-back">Back</button>
        </div>
      </FullScreen>
    );
  }

  if (!data) {
    return (
      <FullScreen>
        <div className="flex items-center gap-3" style={{ color: '#fbdd68' }}>
          <Loader2 className="animate-spin" size={22} />
          <span>Assembling slides…</span>
        </div>
      </FullScreen>
    );
  }

  return (
    <div className="fixed inset-0 flex flex-col" style={{ backgroundColor: '#000e2a' }} data-testid="trivia-play-root">
      {/* Chrome */}
      <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-2" style={{ background: 'linear-gradient(180deg, rgba(0,14,42,0.8), transparent)' }}>
        <div className="text-xs" style={{ color: '#8892b0' }}>
          <span className="font-mono">{data.name}</span>
          <span className="mx-3">·</span>
          <span>Slide {idx + 1} / {total}</span>
        </div>
        <button onClick={exit} className="p-2 rounded-lg hover:bg-white/10" data-testid="trivia-play-exit">
          <X size={20} style={{ color: '#fbdd68' }} />
        </button>
      </div>

      {/* Slide surface (16:9) */}
      <div className="flex-1 flex items-center justify-center p-8 select-none" data-testid="trivia-play-surface" onClick={next}>
        <div className="w-full max-w-6xl aspect-video rounded-2xl overflow-hidden flex items-center justify-center relative" style={{ background: 'linear-gradient(135deg, #0a1940, #141b50)', border: '1px solid rgba(251,221,104,0.15)', boxShadow: '0 0 60px rgba(251,221,104,0.08)' }}>
          <SlideBody slide={slide} />
        </div>
      </div>

      {/* Nav pills */}
      <div className="absolute bottom-4 left-0 right-0 flex items-center justify-center gap-3 z-10">
        <button onClick={(e) => { e.stopPropagation(); prev(); }} disabled={idx === 0} className="p-3 rounded-full disabled:opacity-30" style={{ backgroundColor: 'rgba(251,221,104,0.15)', color: '#fbdd68' }} data-testid="trivia-play-prev">
          <ChevronLeft size={22} />
        </button>
        <div className="text-xs px-4 py-2 rounded-full" style={{ backgroundColor: 'rgba(0,14,42,0.6)', color: '#8892b0' }}>
          Arrow keys · Space · Esc
        </div>
        <button onClick={(e) => { e.stopPropagation(); next(); }} disabled={idx === total - 1} className="p-3 rounded-full disabled:opacity-30" style={{ backgroundColor: 'rgba(251,221,104,0.15)', color: '#fbdd68' }} data-testid="trivia-play-next">
          <ChevronRight size={22} />
        </button>
      </div>
    </div>
  );
}

function SlideBody({ slide }) {
  if (!slide) return null;
  const rt = slide.roundType;
  const roundColor = TYPE_COLORS[rt] || '#fbdd68';

  switch (slide.type) {
    case 'host':
      return (
        <Center>
          <Tag color="#5973F7">TONIGHT&apos;S HOST</Tag>
          <h1 className="text-6xl font-bold text-white mt-6">{slide.subtitle || '—'}</h1>
        </Center>
      );

    case 'location':
      return (
        <Center>
          <Tag color="#fbdd68">WELCOME TO</Tag>
          <h1 className="text-6xl font-bold text-white mt-6">{slide.subtitle || '—'}</h1>
        </Center>
      );

    case 'round_cover':
      return (
        <Center>
          <Tag color={roundColor}>{rt || 'ROUND'} · ROUND {slide.roundOrder || ''}</Tag>
          <h1 className="text-6xl font-bold text-white mt-6 max-w-3xl">{slide.title}</h1>
          {slide.subtitle && <p className="text-lg mt-4" style={{ color: '#8892b0' }}>{slide.subtitle}</p>}
        </Center>
      );

    case 'question':
      return (
        <div className="w-full h-full flex flex-col p-14">
          <div className="flex items-center gap-3 mb-6">
            <Tag color={roundColor}>{rt} · Q{slide.number}</Tag>
          </div>
          <div className="flex-1 flex items-center justify-center">
            <p className="text-4xl leading-snug text-white text-center max-w-4xl">{slide.question}</p>
          </div>
          {slide.options && (
            <div className="grid grid-cols-2 gap-4 mt-8">
              {slide.options.map((opt, i) => (
                <div key={i} className="px-5 py-4 rounded-lg text-lg" style={{ backgroundColor: 'rgba(20,27,80,0.6)', border: '1px solid rgba(251,221,104,0.15)', color: '#e8ecff' }}>
                  <span className="font-bold mr-3" style={{ color: '#fbdd68' }}>{String.fromCharCode(65 + i)}.</span>
                  {opt}
                </div>
              ))}
            </div>
          )}
        </div>
      );

    case 'big_question':
      return (
        <div className="w-full h-full flex flex-col p-14">
          <div className="flex items-center gap-3 mb-6">
            <Tag color={roundColor}>THE BIG QUESTION</Tag>
            {slide.answerCount ? <Tag color="#22c55e">{slide.answerCount} ANSWERS</Tag> : null}
          </div>
          <div className="flex-1 flex items-center justify-center">
            <p className="text-3xl leading-snug text-white text-center max-w-4xl">{slide.question}</p>
          </div>
        </div>
      );

    case 'big_answers':
      return (
        <div className="w-full h-full flex flex-col p-14 overflow-hidden">
          <Tag color={roundColor}>{slide.title}</Tag>
          <p className="text-sm mt-3 mb-6" style={{ color: '#8892b0' }}>{slide.question}</p>
          <div className="flex-1 grid grid-cols-2 gap-x-8 gap-y-2 overflow-hidden">
            {(slide.answers || []).map((ans, i) => (
              <div key={i} className="flex gap-3 items-baseline text-white">
                <span className="font-bold shrink-0" style={{ color: roundColor }}>{i + 1}.</span>
                <span className="text-lg leading-tight">{ans}</span>
              </div>
            ))}
          </div>
        </div>
      );

    case 'tiebreaker':
      return (
        <div className="w-full h-full flex flex-col p-14">
          <Tag color="#a855f7">TIEBREAKER</Tag>
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-6">
            <p className="text-3xl leading-snug text-white max-w-4xl">{slide.question}</p>
            {slide.answer ? (
              <div className="text-xl font-bold px-6 py-3 rounded-xl" style={{ backgroundColor: 'rgba(34,197,94,0.15)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)' }}>
                Answer: {slide.answer}
              </div>
            ) : null}
          </div>
        </div>
      );

    case 'review':
      return (
        <div className="w-full h-full flex flex-col p-14">
          <Tag color={roundColor}>{slide.title}</Tag>
          <div className="grid grid-cols-2 gap-x-8 gap-y-3 mt-6 overflow-hidden">
            {(slide.questions || []).map((q) => (
              <div key={q.number} className="flex gap-3 text-white">
                <span className="font-bold" style={{ color: roundColor }}>{q.number}.</span>
                <span className="text-sm leading-tight">{q.question}</span>
              </div>
            ))}
          </div>
        </div>
      );

    case 'answers':
      return (
        <div className="w-full h-full flex flex-col p-14">
          <Tag color={roundColor}>{slide.title}</Tag>
          <div className="grid grid-cols-2 gap-x-8 gap-y-3 mt-6 overflow-hidden">
            {(slide.questions || []).map((q) => (
              <div key={q.number} className="text-white">
                <div className="flex gap-3 items-baseline">
                  <span className="font-bold shrink-0" style={{ color: roundColor }}>{q.number}.</span>
                  <span className="text-sm leading-tight">{q.question}</span>
                </div>
                <div className="mt-1 ml-6 text-sm font-bold" style={{ color: '#22c55e' }}>→ {q.answer}</div>
              </div>
            ))}
          </div>
        </div>
      );

    case 'sponsor':
      return (
        <Center>
          <Tag color="#a855f7">{slide.title}</Tag>
          <p className="text-xl mt-6" style={{ color: '#8892b0' }}>Sponsored by</p>
        </Center>
      );

    case 'final_scores':
      return (
        <Center>
          <Tag color="#fbdd68">FINAL SCORES</Tag>
          <h1 className="text-6xl font-bold text-white mt-6">Thanks for playing!</h1>
        </Center>
      );

    default:
      return <Center><p className="text-white">Unknown slide type: {slide.type}</p></Center>;
  }
}

function Center({ children }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8">
      {children}
    </div>
  );
}

function Tag({ children, color }) {
  return (
    <span className="text-xs font-bold uppercase tracking-widest px-4 py-1.5 rounded-full" style={{ backgroundColor: `${color}20`, color, border: `1px solid ${color}40` }}>
      {children}
    </span>
  );
}

function FullScreen({ children }) {
  return <div className="fixed inset-0 flex items-center justify-center" style={{ backgroundColor: '#000e2a' }}>{children}</div>;
}
