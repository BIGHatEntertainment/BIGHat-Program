/**
 * v32.0.0-alpha.55 — Trivia Audience View
 *
 * VERBATIM PORT of the v30 prototype's audience-window `renderSlide()`
 * (see _reference/standalone_v30 .. PresentationMode.jsx). Every visual
 * decision here — the per-round-type font multipliers, the clamp()
 * viewport font scaling, the Y-sorted answer reveal with
 * `visibility:hidden`, the final-scores credit scroll — comes straight
 * from the prototype. DO NOT invent layouts.
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
 */
import FinalScoresBoard from '../../components/trivia/final/FinalScoresBoard';
import React, { useEffect, useRef, useState, useCallback } from 'react';

const BC_NAME = 'bighat-trivia-audience';

// _verified_from_prototype: PresentationMode.jsx renderSlide() fontMultiplier
// 1) MC questions: +10% (1.10)
// 2) REG, MISC, MYS questions: +15% (1.15)
// 3) BIG Question (slide 1) and BIG review (slide 3): +10% (1.10)
// 4) All review slides (except BIG): +15% (1.15)
// 5) All answer slides: +10% (1.10)
// 6) Winners slides: no change (1.0)
function getFontMultiplier(slide, isAnswerSlide) {
  const roundType = slide.metadata?.roundType;
  const isWinnersSlide = roundType === 'WINNERS';
  const isAnswerSlideType = slide.metadata?.isAnswerSlide;
  if (isWinnersSlide) return 1.0;
  if (isAnswerSlide || isAnswerSlideType) return 1.10;
  if (roundType === 'MC') return 1.10;
  if (roundType === 'REG' || roundType === 'MISC' || roundType === 'MYS') return 1.15;
  // BIG, SPONSOR, SCORE, default: +10%
  return 1.10;
}

// _verified_from_prototype: VIEWPORT-BASED FONT SCALING
// clamp(max(base*0.7,14)px, (base/1920*100)vw, base*1.5px)
function clampFontSize(element, fontMultiplier) {
  const baseFontSize = (element.fontSize || 16) * fontMultiplier;
  const vwSize = (baseFontSize / 1920) * 100;
  const minSize = Math.max(baseFontSize * 0.7, 14);
  const maxSize = baseFontSize * 1.5;
  return `clamp(${minSize}px, ${vwSize}vw, ${maxSize}px)`;
}

// _verified_from_prototype: `.element` positioning is %-based against the
// full-viewport slide, coordinates authored at 1920×1080.
function positionStyle(element) {
  return {
    position: 'absolute',
    left: (element.x / 1920) * 100 + '%',
    top: (element.y / 1080) * 100 + '%',
    width: (element.width / 1920) * 100 + '%',
    height: (element.height / 1080) * 100 + '%',
  };
}

function textStyle(element, fontMultiplier) {
  return {
    ...positionStyle(element),
    fontSize: clampFontSize(element, fontMultiplier),
    // `.element` class default is pre-wrap; element.whiteSpace overrides.
    whiteSpace: element.whiteSpace || 'pre-wrap',
    fontWeight: element.fontWeight || 'normal',
    color: element.color || '#000000',
    textAlign: element.textAlign || 'left',
    fontFamily: element.fontFamily || 'Inter, sans-serif',
    lineHeight: element.lineHeight || 1.5,
    display: 'flex',
    alignItems: 'center',
    justifyContent: element.textAlign === 'center'
      ? 'center'
      : element.textAlign === 'right' ? 'flex-end' : 'flex-start',
    background: 'transparent',
  };
}

const IMG_STYLE = {
  width: '100%',
  height: '100%',
  objectFit: 'contain',
  pointerEvents: 'none',
  background: 'transparent',
};

export default function TriviaAudienceView() {
  const [slide, setSlide] = useState(null);
  const [isAnswer, setIsAnswer] = useState(false);
  const [revealCount, setRevealCount] = useState(0);
  const [finalScores, setFinalScores] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showFullscreenPrompt, setShowFullscreenPrompt] = useState(true);
  const [lastMessageAt, setLastMessageAt] = useState(null);

  const bcRef = useRef(null);

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
        await document.documentElement.requestFullscreen({ navigationUI: 'hide' });
      }
    } catch (e) {
      try {
        await document.documentElement.requestFullscreen();
      } catch (e2) {
        console.warn('[audience] fullscreen request denied:', e2);
      }
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
        (async () => {
          try {
            if ('__TAURI_INTERNALS__' in window) {
              const { getCurrentWebviewWindow } = await import('@tauri-apps/api/webviewWindow');
              await getCurrentWebviewWindow().close();
              return;
            }
          } catch (_e) { /* fall through to window.close */ }
          window.close();
        })();
        break;
      case 'PING':
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

  const fontMultiplier = slide ? getFontMultiplier(slide, isAnswer) : 1.0;

  // --- ANSWER SLIDE LOGIC — _verified_from_prototype -------------------
  // CRITICAL: Answer slides have NO TITLE - all text elements are answers.
  // Sort text by Y position; hide answer if its index >= revealCount via
  // `visibility: hidden` (element keeps its slot — no reflow).
  const renderAnswerSlide = () => {
    const elements = Array.isArray(slide.elements) ? slide.elements : [];
    const textElements = elements.filter((el) => el.type === 'text');
    const imageElements = elements.filter((el) => el.type === 'image');
    const sortedText = [...textElements].sort((a, b) => a.y - b.y);
    return (
      <>
        {sortedText.map((element, idx) => (
          <div
            key={element.id || `answer-${idx}`}
            style={{
              ...textStyle(element, fontMultiplier),
              visibility: idx >= revealCount ? 'hidden' : 'visible',
            }}
          >
            {element.content || ''}
          </div>
        ))}
        {imageElements.map((element, idx) => (
          <div key={element.id || `img-${idx}`} style={{ ...positionStyle(element), background: 'transparent' }}>
            <img src={element.src || ''} alt="" style={IMG_STYLE} />
          </div>
        ))}
      </>
    );
  };

  // --- NORMAL SLIDE LOGIC — _verified_from_prototype --------------------
  const renderNormalSlide = () => {
    const elements = Array.isArray(slide.elements) ? slide.elements : [];
    return elements.map((element, idx) => {
      if (element.type === 'text') {
        return (
          <div key={element.id || idx} style={textStyle(element, fontMultiplier)}>
            {element.content || ''}
          </div>
        );
      }
      if (element.type === 'image') {
        return (
          <div key={element.id || idx} style={{ ...positionStyle(element), background: 'transparent' }}>
            <img src={element.src || ''} alt="" style={IMG_STYLE} />
          </div>
        );
      }
      if (element.type === 'video' && element.videoSrc) {
        return (
          <div key={element.id || idx} style={positionStyle(element)}>
            {/* Video with AUDIO enabled on audience view */}
            <video
              src={element.videoSrc}
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              autoPlay
              loop
              playsInline
              muted={false}
            />
          </div>
        );
      }
      return null;
    });
  };

  // --- FINAL SCORES (alpha.66) -------------------------------------------
  // Shared board: scoreboard-tool background + navy/gold theme, team boxes
  // scroll up the screen. Same component the host window uses.
  const renderFinalScores = () => (
    <FinalScoresBoard
      teams={Array.isArray(finalScores?.teams) ? finalScores.teams : []}
      rounds={Array.isArray(finalScores?.rounds) ? finalScores.rounds : []}
      location={finalScores?.location || ''}
      date={finalScores?.date || ''}
    />
  );

  // CHECK IF THIS IS THE FINAL SCORES SLIDE (Winners slide 5)
  const isFinalScoresSlide = slide?.metadata?.roundType === 'WINNERS'
    && slide?.metadata?.slideIndexInRound === 4;
  const showFinalScores = isFinalScoresSlide && finalScores
    && Array.isArray(finalScores.teams) && finalScores.teams.length > 0;

  return (
    <div
      data-testid="trivia-audience-view"
      style={{
        position: 'fixed', inset: 0, background: 'black',
        overflow: 'hidden',
        fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
      }}
      onDoubleClick={enterFullscreen}
    >
      {/* _verified_from_prototype: #slide-container (100vw×100vh flex-center)
          wrapping #slide (100%×100%, slide.background). */}
      <div
        style={{
          width: '100vw', height: '100vh',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          position: 'fixed', top: 0, left: 0, background: 'black',
        }}
      >
        <div
          data-testid="audience-stage"
          style={{
            width: '100%', height: '100%', position: 'relative',
            background: slide?.background || 'black',
          }}
        >
          {slide && showFinalScores && renderFinalScores()}
          {slide && !showFinalScores && (isAnswer ? renderAnswerSlide() : renderNormalSlide())}

          {/* Waiting state — no slide yet */}
          {!slide && (
            <div
              data-testid="audience-waiting"
              style={{
                position: 'absolute', inset: 0,
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                color: '#666',
              }}
            >
              <div style={{ fontSize: 96, fontWeight: 800, color: '#F4C430', marginBottom: 20 }}>
                BIG Hat
              </div>
              <div style={{ fontSize: 44 }}>Waiting for the host…</div>
            </div>
          )}
        </div>
      </div>

      {/* _verified_from_prototype: #fullscreen-prompt — centered gold pill */}
      {showFullscreenPrompt && !isFullscreen && (
        <div
          data-testid="audience-fullscreen-prompt"
          onClick={enterFullscreen}
          style={{
            position: 'fixed', top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            background: 'rgba(255, 215, 0, 0.95)', color: 'black',
            padding: '40px 60px', borderRadius: 12,
            fontSize: 28, fontWeight: 'bold', cursor: 'pointer',
            zIndex: 99999, textAlign: 'center',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          }}
        >
          🖥️ Click to Enter Fullscreen<br />
          <span style={{ fontSize: 18, fontWeight: 'normal' }}>Remove all bars and borders</span>
        </div>
      )}

      {/* Disconnect indicator — only after host has gone quiet >10s. */}
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
