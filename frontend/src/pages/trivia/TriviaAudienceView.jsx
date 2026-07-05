/**
 * v32.0.0-alpha.47 — Trivia Audience View
 *
 * Second-monitor mirror of the host's slide. Meant to be dragged onto
 * the bar TV. Always renders in a 1920×1080 stage, uniformly scaled to
 * fit the actual monitor's resolution (min of vw/1920, vh/1080) so
 * every TV in every bar shows the SAME layout regardless of physical
 * pixel dimensions. No host chrome, no timer, no controls — just the
 * slide.
 *
 * Receives state from the host via:
 *   1. BroadcastChannel("bighat-trivia-audience") — primary
 *   2. postMessage — legacy fallback for the old window.open() flow
 *
 * Message shape (both channels):
 *   { type: 'UPDATE_SLIDE', slide, isAnswerSlide, revealedCount, finalScoresData }
 *   { type: 'REVEAL_ANSWER', slideIndex, revealedCount }
 *   { type: 'CLOSE' }               // host is closing audience
 *   { type: 'PING' }                // heartbeat
 *
 * Host publishes to BOTH channels; audience reads from BOTH.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Maximize } from 'lucide-react';

// Fixed stage — every slide is designed at 1920×1080. Scaling keeps
// aspect ratio identical across a 32" monitor and a 65" TV.
const STAGE_W = 1920;
const STAGE_H = 1080;

const BC_NAME = 'bighat-trivia-audience';

export default function TriviaAudienceView() {
  const [slide, setSlide] = useState(null);
  const [isAnswer, setIsAnswer] = useState(false);
  const [revealCount, setRevealCount] = useState(0);
  const [finalScores, setFinalScores] = useState(null);
  const [stageScale, setStageScale] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showFullscreenPrompt, setShowFullscreenPrompt] = useState(true);
  const [lastMessageAt, setLastMessageAt] = useState(null);

  const bcRef = useRef(null);

  // --- Uniform viewport scaling (1920×1080 → whatever the TV is) --------
  useEffect(() => {
    const computeScale = () => {
      const s = Math.min(window.innerWidth / STAGE_W, window.innerHeight / STAGE_H);
      setStageScale(s);
    };
    computeScale();
    window.addEventListener('resize', computeScale);
    window.addEventListener('orientationchange', computeScale);
    return () => {
      window.removeEventListener('resize', computeScale);
      window.removeEventListener('orientationchange', computeScale);
    };
  }, []);

  // --- Fullscreen state tracking ---------------------------------------
  useEffect(() => {
    const onFsChange = () => {
      const fs = !!document.fullscreenElement;
      setIsFullscreen(fs);
      if (fs) setShowFullscreenPrompt(false);
    };
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, []);

  const enterFullscreen = useCallback(async () => {
    try {
      if (document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
    } catch (e) {
      console.warn('[audience] fullscreen request denied:', e);
    }
    setShowFullscreenPrompt(false);
  }, []);

  // --- Message handler (both channels) ---------------------------------
  const handleMessage = useCallback((payload) => {
    if (!payload || typeof payload !== 'object') return;
    setLastMessageAt(Date.now());
    switch (payload.type) {
      case 'UPDATE_SLIDE':
        setSlide(payload.slide || null);
        setIsAnswer(!!payload.isAnswerSlide);
        setRevealCount(payload.revealedCount || 0);
        setFinalScores(payload.finalScoresData || null);
        break;
      case 'REVEAL_ANSWER':
        setRevealCount(payload.revealedCount || 0);
        break;
      case 'CLOSE':
        window.close();
        break;
      case 'PING':
        // Respond so host knows we're alive
        if (bcRef.current) bcRef.current.postMessage({ type: 'PONG', at: Date.now() });
        break;
      default:
        break;
    }
  }, []);

  useEffect(() => {
    // BroadcastChannel — primary
    let bc = null;
    try {
      bc = new BroadcastChannel(BC_NAME);
      bcRef.current = bc;
      bc.onmessage = (e) => handleMessage(e.data);
      // Announce ready so host can push current state
      bc.postMessage({ type: 'AUDIENCE_READY', at: Date.now() });
    } catch (e) {
      console.warn('[audience] BroadcastChannel unsupported:', e);
    }

    // window.postMessage — legacy fallback
    const onMsg = (e) => handleMessage(e.data);
    window.addEventListener('message', onMsg);

    return () => {
      window.removeEventListener('message', onMsg);
      if (bc) {
        try { bc.close(); } catch (_e) { /* noop */ }
      }
    };
  }, [handleMessage]);

  // --- Progressive reveal: hide questions past revealCount on answer
  //     slides (matches host's answer-reveal UX).
  const renderElement = (element, idx) => {
    if (!element) return null;

    // Determine if this element should be hidden on progressive reveal.
    // Elements tagged with `id` starting with "answer-N" (or metadata
    // `answerIndex`) get hidden if idx >= revealCount on answer slides.
    if (isAnswer) {
      const answerIdx = element.answerIndex ?? (
        typeof element.id === 'string' && element.id.startsWith('answer-')
          ? parseInt(element.id.split('-')[1], 10)
          : null
      );
      if (answerIdx !== null && !Number.isNaN(answerIdx) && answerIdx >= revealCount) {
        return null;
      }
    }

    const style = {
      position: 'absolute',
      left: (element.x / STAGE_W) * 100 + '%',
      top: (element.y / STAGE_H) * 100 + '%',
      width: (element.width / STAGE_W) * 100 + '%',
      height: (element.height / STAGE_H) * 100 + '%',
      fontSize: element.fontSize ? element.fontSize + 'px' : undefined,
      fontWeight: element.fontWeight,
      color: element.color,
      textAlign: element.textAlign,
      fontFamily: element.fontFamily,
      lineHeight: element.lineHeight || 1.2,
      whiteSpace: element.whiteSpace || 'pre-wrap',
      display: 'flex',
      alignItems: element.verticalAlign === 'top'
        ? 'flex-start'
        : element.verticalAlign === 'bottom' ? 'flex-end' : 'center',
      justifyContent: element.textAlign === 'center'
        ? 'center'
        : element.textAlign === 'right' ? 'flex-end' : 'flex-start',
      zIndex: element.zIndex ?? undefined,
      overflow: element.overflow || 'hidden',
    };

    if (element.type === 'text') {
      return <div key={element.id || idx} style={style}>{element.content}</div>;
    }
    if (element.type === 'image' && element.src) {
      return (
        <div key={element.id || idx} style={style}>
          <img
            src={element.src}
            alt=""
            style={{ width: '100%', height: '100%', objectFit: 'contain', background: 'transparent' }}
          />
        </div>
      );
    }
    if (element.type === 'video' && element.videoSrc) {
      return (
        <div key={element.id || idx} style={style}>
          <video
            src={element.videoSrc}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            autoPlay
            loop
            playsInline
          />
        </div>
      );
    }
    // Note: overlay elements should have been resolved to `image` by the
    // host before broadcast — see PresentationMode.updateAudienceView.
    return null;
  };

  // --- Final-scores WINNERS slide (leaderboard) — CSS-scrolling render.
  // v32.0.0-alpha.48: per merchant spec, the final scores slide is
  // ALWAYS the last slide and animates from bottom-to-top like end credits.
  const renderFinalScores = () => {
    if (!finalScores) return null;
    const teams = Array.isArray(finalScores?.teams) ? finalScores.teams : [];
    // Duration scales with roster size — enough time to read every team.
    const scrollSeconds = Math.max(18, teams.length * 2);
    return (
      <div
        data-testid="audience-final-scores"
        style={{
          position: 'absolute', inset: 0, overflow: 'hidden',
          color: '#fff', background: 'transparent',
        }}
      >
        {/* Sticky header — stays put */}
        <div
          style={{
            position: 'absolute', top: 40, left: 0, right: 0,
            textAlign: 'center', pointerEvents: 'none', zIndex: 2,
            background: 'linear-gradient(180deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.6) 60%, transparent 100%)',
            padding: '20px 0 40px 0',
          }}
        >
          <div style={{
            fontSize: 120, fontWeight: 800, color: '#F4C430',
            letterSpacing: '-1px', lineHeight: 1,
          }}>
            Final Scores
          </div>
        </div>

        {/* Scrolling leaderboard */}
        <div
          data-testid="audience-final-scores-scroll"
          style={{
            position: 'absolute', left: 0, right: 0,
            top: STAGE_H,          // start below the visible frame
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', gap: 16,
            padding: '0 100px',
            animation: `bighat-scroll-credits ${scrollSeconds}s linear infinite`,
          }}
        >
          {teams.map((t, i) => (
            <div
              key={t.id || i}
              style={{
                width: '100%', maxWidth: 1400,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '18px 40px',
                background: i === 0
                  ? 'linear-gradient(90deg, #F4C430 0%, #B8860B 100%)'
                  : i === 1
                    ? 'rgba(192, 192, 192, 0.18)'
                    : i === 2
                      ? 'rgba(205, 127, 50, 0.18)'
                      : 'rgba(255,255,255,0.06)',
                border: i === 0 ? '2px solid #F4C430' : '1px solid rgba(255,255,255,0.14)',
                borderRadius: 14,
                fontSize: i === 0 ? 60 : 44,
                fontWeight: i === 0 ? 800 : 600,
                color: i === 0 ? '#111' : '#fff',
              }}
            >
              <span>{i + 1}. {t.name || `Team ${i + 1}`}</span>
              <span>{t.total ?? 0}</span>
            </div>
          ))}
          {/* Sponsor / "thanks for playing" tail */}
          <div style={{
            marginTop: 60, padding: '20px 40px',
            fontSize: 44, color: '#F4C430', fontWeight: 700,
            textAlign: 'center',
          }}>
            Thanks for playing!
          </div>
        </div>

        {/* Inline keyframes so the audience view is self-contained */}
        <style>{`
          @keyframes bighat-scroll-credits {
            0% { transform: translateY(0); }
            100% { transform: translateY(-${(teams.length + 1) * 90 + 200}px); }
          }
        `}</style>
      </div>
    );
  };

  // --- Stage transform for the 1920×1080 → viewport uniform scaling ------
  const stageStyle = {
    position: 'absolute',
    left: '50%',
    top: '50%',
    width: STAGE_W,
    height: STAGE_H,
    transform: `translate(-50%, -50%) scale(${stageScale})`,
    transformOrigin: 'center center',
    background: slide?.background || '#000',
    overflow: 'hidden',
  };

  const isWinnersFinal = slide?.metadata?.roundType === 'WINNERS'
    && slide?.metadata?.slideIndexInRound === 4;

  return (
    <div
      data-testid="trivia-audience-view"
      style={{
        position: 'fixed', inset: 0, background: '#000',
        cursor: isFullscreen ? 'none' : 'default',
        overflow: 'hidden',
      }}
      onDoubleClick={enterFullscreen}
    >
      <div style={stageStyle} data-testid="audience-stage">
        {slide && !isWinnersFinal && Array.isArray(slide.elements) && (
          slide.elements.map(renderElement)
        )}
        {slide && isWinnersFinal && renderFinalScores()}

        {/* Waiting state — no slide yet */}
        {!slide && (
          <div
            data-testid="audience-waiting"
            style={{
              position: 'absolute', inset: 0,
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center',
              color: '#666', fontFamily: 'Inter, system-ui, sans-serif',
            }}
          >
            <div style={{ fontSize: 96, fontWeight: 800, color: '#F4C430', marginBottom: 20 }}>
              BIG Hat
            </div>
            <div style={{ fontSize: 44 }}>Waiting for the host…</div>
          </div>
        )}
      </div>

      {/* Fullscreen prompt — click to go fullscreen (best on TVs) */}
      {showFullscreenPrompt && !isFullscreen && (
        <div
          data-testid="audience-fullscreen-prompt"
          onClick={enterFullscreen}
          style={{
            position: 'fixed', bottom: 20, right: 20,
            background: 'rgba(244, 196, 48, 0.95)', color: '#111',
            padding: '12px 20px', borderRadius: 10, fontWeight: 700,
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8,
            fontFamily: 'Inter, system-ui, sans-serif', fontSize: 16,
            boxShadow: '0 10px 30px rgba(0,0,0,0.4)',
          }}
        >
          <Maximize size={18} />
          Click to enter fullscreen
        </div>
      )}

      {/* Disconnect indicator — subtle, bottom-left, only after we've
          heard from the host at least once and then gone quiet >10s. */}
      {lastMessageAt && (Date.now() - lastMessageAt > 10000) && (
        <div
          data-testid="audience-disconnected"
          style={{
            position: 'fixed', bottom: 20, left: 20,
            width: 12, height: 12, borderRadius: '50%',
            background: '#e53e3e', opacity: 0.6,
          }}
          title="Disconnected from host"
        />
      )}
    </div>
  );
}
