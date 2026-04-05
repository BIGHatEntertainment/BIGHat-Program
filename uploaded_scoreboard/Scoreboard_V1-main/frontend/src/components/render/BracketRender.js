import React, { useState, useEffect, useMemo } from 'react';
import { DesertBackdrop } from './DesertBackdrop';
import { Trophy } from 'lucide-react';

const BracketRender = ({ 
  bracket, 
  teams = [], 
  tournamentName = 'THE BIG TRIVIA TOURNAMENT',
  tournamentYear = '',
  aspectRatio = 'landscape',
  animationSpeed = 1,
  isAnimating = true 
}) => {
  const [showTitle, setShowTitle] = useState(false);
  const [showBracket, setShowBracket] = useState(false);
  const [showChampion, setShowChampion] = useState(false);
  const [showTrophy, setShowTrophy] = useState(false);

  const isPortrait = aspectRatio === 'portrait';

  useEffect(() => {
    if (!isAnimating) {
      setShowTitle(true);
      setShowBracket(true);
      setShowChampion(true);
      setShowTrophy(true);
      return;
    }
    setShowTitle(false);
    setShowBracket(false);
    setShowChampion(false);
    setShowTrophy(false);

    const t1 = setTimeout(() => setShowTitle(true), 100);
    const t2 = setTimeout(() => setShowBracket(true), 500 / animationSpeed);
    const t3 = setTimeout(() => setShowChampion(true), 2000 / animationSpeed);
    const t4 = setTimeout(() => setShowTrophy(true), 800 / animationSpeed);

    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); clearTimeout(t4); };
  }, [isAnimating, animationSpeed]);

  const rounds = bracket?.rounds || [];
  const matches = bracket?.matches || {};
  const champion = bracket?.champion;
  const totalRounds = rounds.length;

  const stageW = isPortrait ? 1080 : 1920;
  const stageH = isPortrait ? 1920 : 1080;

  const roundColors = ['#FCAF45', '#F77737', '#E1306C', '#C13584', '#833AB4', '#5851DB'];

  // ============ LANDSCAPE LAYOUT ============
  const lTrophyW = 220;
  const lMargin = { top: 90, bottom: 50, left: 50, right: 50 };
  const lBracketW = stageW - lMargin.left - lMargin.right - lTrophyW;
  const lUsableH = stageH - lMargin.top - lMargin.bottom;
  const lCardW = Math.min(320, (lBracketW - 80) / (totalRounds || 1));
  const lCardH = 81; // 54 * 1.5
  const lRoundSpacing = totalRounds > 0 ? lBracketW / totalRounds : lBracketW;

  const getLandscapePos = (roundIdx, matchIdx, matchCount) => {
    const x = lMargin.left + lRoundSpacing * roundIdx;
    const evenY = lMargin.top + (lUsableH / (matchCount + 1)) * (matchIdx + 1) - lCardH;
    return { x, y: evenY };
  };

  // ============ PORTRAIT LAYOUT ============
  const pTitleH = 90;
  const pTrophyH = 320; // bigger trophy area
  const pMargin = { top: pTitleH, bottom: pTrophyH, left: 20, right: 20 };
  const pUsableW = stageW - pMargin.left - pMargin.right;
  const pUsableH = stageH - pMargin.top - pMargin.bottom;
  const pRoundH = totalRounds > 0 ? pUsableH / totalRounds : pUsableH;
  const pCardH = 108; // 72 * 1.5

  const getPortraitPos = (roundIdx, matchIdx, matchCount) => {
    const cardW = Math.min(345, (pUsableW - (matchCount - 1) * 14) / matchCount);
    const totalRowW = matchCount * cardW + (matchCount - 1) * 14;
    const startX = (stageW - totalRowW) / 2;
    const x = startX + matchIdx * (cardW + 14);
    const y = pMargin.top + roundIdx * pRoundH + 10;
    return { x, y, cardW };
  };

  const getPortraitCardW = (matchCount) => {
    return Math.min(345, (pUsableW - (matchCount - 1) * 14) / matchCount);
  };

  // Font sizes - 50% bigger
  // Font sizes - 25% bigger than previous
  const seedFont = isPortrait ? '19px' : '20px';
  const nameFont = isPortrait ? '20px' : '22px';
  const scoreFont = isPortrait ? '20px' : '22px';
  const labelFont = isPortrait ? '14px' : '16px';
  const cardPadY = isPortrait ? '10px 14px' : '10px 16px';

  // Render a match card
  const renderMatchCard = (matchId, mIdx, round, rIdx, pos, cardW, cardH) => {
    const match = matches[matchId];
    if (!match) return null;
    const teamA = match.teamA;
    const teamB = match.teamB;
    const teamAName = teamA?.name || 'TBD';
    const teamBName = teamB?.name || 'TBD';
    const teamASeed = teamA?.seed;
    const teamBSeed = teamB?.seed;
    const isWinnerA = match.completed && match.winner_seed === teamASeed;
    const isWinnerB = match.completed && match.winner_seed === teamBSeed;
    const roundColor = roundColors[rIdx % roundColors.length];

    return (
      <div
        key={matchId}
        data-testid={`match-card-r${round.round}-m${mIdx}`}
        className={`absolute glass-panel rounded-lg overflow-hidden ${showBracket ? 'animate-fade-in' : 'opacity-0'}`}
        style={{
          left: pos.x, top: pos.y, width: cardW,
          animationDelay: `${rIdx * 300 + mIdx * 150}ms`,
          boxShadow: `0 0 20px ${roundColor}25`,
        }}
      >
        <div 
          className="text-center py-1 font-semibold uppercase tracking-wider font-mono"
          style={{ background: `${roundColor}18`, color: `${roundColor}CC`, fontSize: labelFont }}
        >
          {round.label}
        </div>
        <div 
          className="flex items-center gap-2"
          style={{ 
            padding: cardPadY,
            background: isWinnerA ? 'rgba(252, 175, 69, 0.15)' : 'transparent',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          {teamASeed && (
            <span className="font-mono-score font-bold w-6 text-center" style={{ color: '#FCAF45', fontSize: seedFont }}>{teamASeed}</span>
          )}
          <span className="flex-1 truncate font-semibold" style={{ color: isWinnerA ? '#F4F2FF' : teamA ? 'rgba(244,242,255,0.85)' : 'rgba(244,242,255,0.3)', fontSize: nameFont }}>
            {teamAName}
          </span>
          {match.score_a != null && (
            <span className="font-mono-score font-bold" style={{ color: isWinnerA ? '#FCAF45' : 'rgba(244,242,255,0.4)', fontSize: scoreFont }}>{match.score_a}</span>
          )}
        </div>
        <div 
          className="flex items-center gap-2"
          style={{ padding: cardPadY, background: isWinnerB ? 'rgba(252, 175, 69, 0.15)' : 'transparent' }}
        >
          {teamBSeed && (
            <span className="font-mono-score font-bold w-6 text-center" style={{ color: '#FCAF45', fontSize: seedFont }}>{teamBSeed}</span>
          )}
          <span className="flex-1 truncate font-semibold" style={{ color: isWinnerB ? '#F4F2FF' : teamB ? 'rgba(244,242,255,0.85)' : 'rgba(244,242,255,0.3)', fontSize: nameFont }}>
            {teamBName}
          </span>
          {match.score_b != null && (
            <span className="font-mono-score font-bold" style={{ color: isWinnerB ? '#FCAF45' : 'rgba(244,242,255,0.4)', fontSize: scoreFont }}>{match.score_b}</span>
          )}
        </div>
      </div>
    );
  };

  // Use explicit year prop first, then try to extract from name, then current year
  const displayYear = tournamentYear || (() => {
    const m = tournamentName.match(/\b(20\d{2})\b/);
    return m ? m[1] : new Date().getFullYear().toString();
  })();

  // Trophy component - explicitly pixel-centered on stage
  const TrophyDisplay = ({ size, centerX, className = '' }) => (
    <div className={`flex flex-col items-center ${className}`}
      style={{ position: 'absolute', left: centerX - size * 0.75, width: size * 1.5, top: 0 }}
    >
      <div className="absolute rounded-full"
        style={{
          width: size * 3, height: size * 3,
          top: -size * 0.6, left: '50%', transform: 'translateX(-50%)',
          background: 'radial-gradient(circle, rgba(252,175,69,0.35) 0%, rgba(225,48,108,0.18) 35%, transparent 65%)',
          filter: 'blur(30px)',
        }}
      />
      <Trophy size={size} className="trophy-glow relative z-10" style={{ color: '#FCAF45' }} />
      <div className="relative z-10 text-center mt-3">
        <div className="font-cyber tracking-wider"
          style={{ color: '#FCAF45', fontSize: size * 0.35, textShadow: '0 0 20px rgba(252,175,69,0.6)' }}>
          {displayYear}
        </div>
        <div className="font-cyber tracking-wider glow-text" style={{ fontSize: size * 0.28 }}>
          Champions
        </div>
      </div>
    </div>
  );

  return (
    <div className="absolute inset-0" data-testid="bracket-render">
      <DesertBackdrop />
      <div className="relative z-10 h-full w-full">

        {/* CENTERED TITLE */}
        <div className={`absolute text-center ${showTitle ? 'animate-slide-down' : 'opacity-0'}`}
          style={{ top: isPortrait ? '12px' : '8px', left: 0, right: 0 }}>
          <p className="font-semibold uppercase tracking-[0.3em] font-mono"
            style={{ color: 'rgba(225, 48, 108, 0.7)', fontSize: isPortrait ? '11px' : '12px' }}>
            BIG Hat Entertainment Presents
          </p>
          <h1 className="font-cyber text-white leading-none mt-1 tracking-wider mx-auto"
            style={{ fontSize: isPortrait ? '30px' : '42px', textShadow: '0 0 20px rgba(252,175,69,0.4), 0 0 40px rgba(225,48,108,0.2)', maxWidth: '90%' }}>
            {tournamentName}
          </h1>
        </div>

        {/* ======== PORTRAIT ======== */}
        {isPortrait && (
          <>
            <svg className="absolute inset-0" width={stageW} height={stageH}
              style={{ opacity: showBracket ? 1 : 0, transition: 'opacity 0.5s' }}>
              <defs>
                <linearGradient id="vLine" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#FCAF45" stopOpacity="0.4" />
                  <stop offset="50%" stopColor="#E1306C" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#833AB4" stopOpacity="0.4" />
                </linearGradient>
              </defs>
              {rounds.map((round, rIdx) => {
                if (rIdx === 0) return null;
                const prev = rounds[rIdx - 1];
                return round.matchIds.map((matchId, mIdx) => {
                  const cW = getPortraitCardW(round.matchIds.length);
                  const pW = getPortraitCardW(prev.matchIds.length);
                  const curr = getPortraitPos(rIdx, mIdx, round.matchIds.length);
                  const lines = [];
                  [mIdx * 2, mIdx * 2 + 1].forEach((pi, li) => {
                    if (pi < prev.matchIds.length) {
                      const p = getPortraitPos(rIdx - 1, pi, prev.matchIds.length);
                      const x1 = p.x + pW / 2, y1 = p.y + pCardH;
                      const x2 = curr.x + cW / 2, y2 = curr.y;
                      const midY = (y1 + y2) / 2;
                      lines.push(
                        <path key={`${matchId}-l${li}`}
                          d={`M ${x1} ${y1} V ${midY} H ${x2} V ${y2}`}
                          stroke="url(#vLine)" strokeWidth="2.5" fill="none"
                          className={isAnimating ? 'animate-draw-line' : ''}
                          style={{ animationDelay: `${rIdx * 400 + li * 200}ms` }} />
                      );
                    }
                  });
                  return lines;
                });
              })}
            </svg>

            {rounds.map((round, rIdx) => {
              const mc = round.matchIds.length;
              const cw = getPortraitCardW(mc);
              return round.matchIds.map((matchId, mIdx) => {
                const pos = getPortraitPos(rIdx, mIdx, mc);
                return renderMatchCard(matchId, mIdx, round, rIdx, pos, cw, pCardH);
              });
            })}

            {/* TROPHY - pixel-centered at bottom of 1080px stage */}
            {showTrophy && (
              <div style={{ position: 'absolute', top: stageH - pTrophyH + 10, left: 540 - 120, width: 240, display: 'flex', flexDirection: 'column', alignItems: 'center' }}
                className={isAnimating ? 'animate-blur-in' : ''}>
                <div className="absolute rounded-full"
                  style={{ width: 450, height: 450, top: -100, left: '50%', transform: 'translateX(-50%)',
                    background: 'radial-gradient(circle, rgba(252,175,69,0.35) 0%, rgba(225,48,108,0.18) 35%, transparent 65%)', filter: 'blur(30px)' }} />
                <Trophy size={140} className="trophy-glow relative z-10" style={{ color: '#FCAF45' }} />
                <div className="relative z-10 text-center mt-3">
                  <div className="font-cyber tracking-wider" style={{ color: '#FCAF45', fontSize: '49px', textShadow: '0 0 20px rgba(252,175,69,0.6)' }}>{displayYear}</div>
                  <div className="font-cyber tracking-wider glow-text" style={{ fontSize: '39px' }}>Champions</div>
                </div>
              </div>
            )}

            {champion && showChampion && (
              <div className="absolute animate-blur-in" style={{ left: '50%', transform: 'translateX(-50%)', bottom: 20, textAlign: 'center' }}>
                <div className="glass-panel rounded-xl px-6 py-3 text-center sheen-effect animated-border">
                  <p className="font-bold text-xl" style={{ color: '#F4F2FF' }}>{champion.name}</p>
                  <p className="font-mono-score text-sm mt-1" style={{ color: '#FCAF45' }}>Seed #{champion.seed}</p>
                </div>
              </div>
            )}
          </>
        )}

        {/* ======== LANDSCAPE ======== */}
        {!isPortrait && (
          <>
            <svg className="absolute inset-0" width={stageW} height={stageH}
              style={{ opacity: showBracket ? 1 : 0, transition: 'opacity 0.5s' }}>
              <defs>
                <linearGradient id="hLine" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#FCAF45" stopOpacity="0.5" />
                  <stop offset="50%" stopColor="#E1306C" stopOpacity="0.5" />
                  <stop offset="100%" stopColor="#833AB4" stopOpacity="0.5" />
                </linearGradient>
              </defs>
              {rounds.map((round, rIdx) => {
                if (rIdx === 0) return null;
                const prev = rounds[rIdx - 1];
                return round.matchIds.map((matchId, mIdx) => {
                  const curr = getLandscapePos(rIdx, mIdx, round.matchIds.length);
                  const lines = [];
                  [mIdx * 2, mIdx * 2 + 1].forEach((pi, li) => {
                    if (pi < prev.matchIds.length) {
                      const p = getLandscapePos(rIdx - 1, pi, prev.matchIds.length);
                      const x1 = p.x + lCardW, y1 = p.y + lCardH * (li === 0 ? 1 : 1);
                      const x2 = curr.x, y2 = curr.y + lCardH * (li === 0 ? 0.4 : 0.6);
                      const midX = (x1 + x2) / 2;
                      lines.push(
                        <path key={`${matchId}-l${li}`}
                          d={`M ${x1} ${y1} H ${midX} V ${y2} H ${x2}`}
                          stroke="url(#hLine)" strokeWidth="3" fill="none"
                          className={isAnimating ? 'animate-draw-line' : ''}
                          style={{ animationDelay: `${rIdx * 400 + li * 200}ms` }} />
                      );
                    }
                  });
                  return lines;
                });
              })}
            </svg>

            {rounds.map((round, rIdx) => {
              const mc = round.matchIds.length;
              return round.matchIds.map((matchId, mIdx) => {
                const pos = getLandscapePos(rIdx, mIdx, mc);
                return renderMatchCard(matchId, mIdx, round, rIdx, pos, lCardW, lCardH);
              });
            })}

            {/* TROPHY - centered in right column, shifted 50px left */}
            {showTrophy && !champion && (
              <div style={{ position: 'absolute', right: 50, top: 0, bottom: 0, width: lTrophyW + lMargin.right, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div className={`flex flex-col items-center ${isAnimating ? 'animate-blur-in' : ''}`}>
                  <div className="absolute rounded-full"
                    style={{ width: 480, height: 480, top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
                      background: 'radial-gradient(circle, rgba(252,175,69,0.35) 0%, rgba(225,48,108,0.18) 35%, transparent 65%)', filter: 'blur(30px)' }} />
                  <Trophy size={160} className="trophy-glow relative z-10" style={{ color: '#FCAF45' }} />
                  <div className="relative z-10 text-center mt-3">
                    <div className="font-cyber tracking-wider" style={{ color: '#FCAF45', fontSize: '56px', textShadow: '0 0 20px rgba(252,175,69,0.6)' }}>{displayYear}</div>
                    <div className="font-cyber tracking-wider glow-text" style={{ fontSize: '44px' }}>Champions</div>
                  </div>
                </div>
              </div>
            )}

            {champion && showChampion && (
              <div className="absolute animate-blur-in flex flex-col items-center"
                style={{ right: lMargin.right + 50, top: '50%', transform: 'translateY(-50%)', width: lTrophyW, textAlign: 'center' }}>
                <Trophy size={160} className="trophy-glow mb-3" style={{ color: '#FCAF45' }} />
                <div className="font-cyber tracking-wider" style={{ color: '#FCAF45', fontSize: '32px', textShadow: '0 0 15px rgba(252,175,69,0.5)' }}>{displayYear}</div>
                <div className="font-cyber tracking-wider glow-text" style={{ fontSize: '26px' }}>Champions</div>
                <div className="glass-panel rounded-xl px-6 py-4 mt-3 text-center sheen-effect animated-border">
                  <p className="font-bold text-xl" style={{ color: '#F4F2FF' }}>{champion.name}</p>
                  <p className="font-mono-score text-sm mt-1" style={{ color: '#FCAF45' }}>Seed #{champion.seed}</p>
                </div>
              </div>
            )}
          </>
        )}

        {/* Footer */}
        <div className="absolute left-1/2 transform -translate-x-1/2 flex items-center gap-3"
          style={{ opacity: showBracket ? 0.5 : 0, bottom: isPortrait ? '6px' : '4px' }}>
          <div className="w-4 h-4 rounded-full ig-gradient" />
          <span className="font-cyber tracking-wider" style={{ color: 'rgba(244,242,255,0.4)', fontSize: '10px' }}>BIG Hat Entertainment</span>
        </div>
      </div>
    </div>
  );
};

export { BracketRender };
export default BracketRender;
