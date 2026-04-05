import React, { useState, useEffect, useRef, useCallback } from 'react';
import { SynthwaveBackdrop } from './SynthwaveBackdrop';
import { Trophy, Medal, Award } from 'lucide-react';

/**
 * AutoShrinkText: Renders text that dynamically shrinks if it overflows.
 * Starts at `maxSize` and reduces until it fits within the container.
 */
const AutoShrinkText = ({ text, maxSize, minSize = 12, className = '', style = {} }) => {
  const ref = useRef(null);
  const [fontSize, setFontSize] = useState(maxSize);

  useEffect(() => {
    setFontSize(maxSize);
  }, [text, maxSize]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Check if text overflows
    if (el.scrollWidth > el.clientWidth && fontSize > minSize) {
      setFontSize(prev => Math.max(prev - 1, minSize));
    }
  }, [fontSize, text, minSize]);

  return (
    <span
      ref={ref}
      className={className}
      style={{
        ...style,
        fontSize: `${fontSize}px`,
        display: 'block',
        overflow: 'hidden',
        whiteSpace: 'nowrap',
        textOverflow: 'ellipsis',
      }}
    >
      {text}
    </span>
  );
};

/**
 * Leaderboard renderer - IG gradient playful theme.
 * Top 3 get spotlight treatment, rest animate in as list.
 */
const LeaderboardRender = ({ 
  data, 
  aspectRatio = 'landscape',
  animationSpeed = 1,
  isAnimating = true 
}) => {
  const [showTitle, setShowTitle] = useState(false);
  const [showPodium, setShowPodium] = useState(false);
  const [showList, setShowList] = useState(false);
  const [visibleRows, setVisibleRows] = useState(0);

  const teams = data?.teams || [];
  const location = data?.location || data?.presentationName || 'BIG Hat Trivia';
  const date = data?.date || '';
  const rounds = data?.rounds || [];

  const top3 = teams.slice(0, 3);
  const rest = teams.slice(3);

  const baseDelay = 280 / animationSpeed;

  useEffect(() => {
    if (!isAnimating) {
      setShowTitle(true);
      setShowPodium(true);
      setShowList(true);
      setVisibleRows(rest.length);
      return;
    }

    setShowTitle(false);
    setShowPodium(false);
    setShowList(false);
    setVisibleRows(0);

    const t1 = setTimeout(() => setShowTitle(true), 100);
    const t2 = setTimeout(() => setShowPodium(true), baseDelay + 200);
    const t3 = setTimeout(() => setShowList(true), baseDelay + 800);

    const rowTimers = rest.map((_, i) =>
      setTimeout(() => setVisibleRows(i + 1), baseDelay + 900 + (i * 70 / animationSpeed))
    );

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      rowTimers.forEach(clearTimeout);
    };
  }, [isAnimating, animationSpeed, rest.length, baseDelay]);

  const isPortrait = aspectRatio === 'portrait';
  const podiumOrder = [0, 1, 2]; // 1st, 2nd, 3rd — top team on top

  // Synthwave neon color scheme
  const rankColors = [
    { bg: 'rgba(255, 215, 0, 0.15)', border: '#FFD700', text: '#FFD700', glow: 'rgba(255, 215, 0, 0.4)', icon: Trophy },
    { bg: 'rgba(0, 212, 255, 0.12)', border: '#00d4ff', text: '#00d4ff', glow: 'rgba(0, 212, 255, 0.3)', icon: Medal },
    { bg: 'rgba(255, 0, 255, 0.1)', border: '#ff00ff', text: '#ff00ff', glow: 'rgba(255, 0, 255, 0.25)', icon: Award },
  ];

  // Font sizes - 10% bigger, portrait optimized for phone readability
  const titleSize = isPortrait ? 70 : 72;
  const podiumNameSize1st = isPortrait ? 30 : 28;
  const podiumNameSize = isPortrait ? 24 : 22;
  const podiumScoreSize1st = isPortrait ? 52 : 46;
  const podiumScoreSize = isPortrait ? 40 : 36;
  const podiumRankSize1st = isPortrait ? 28 : 26;
  const podiumRankSize = isPortrait ? 22 : 20;
  const listNameSize = isPortrait ? 22 : 18;
  const listScoreSize = isPortrait ? 24 : 20;
  const listRankSize = isPortrait ? 18 : 16;

  return (
    <div className="absolute inset-0" data-testid="leaderboard-render">
      <SynthwaveBackdrop />
      
      {/* Content layer */}
      <div className="relative z-10 flex flex-col h-full" style={{ padding: isPortrait ? '50px 44px 50px 36px' : '40px 60px' }}>
        
        {/* Title bar */}
        <div 
          className={`${showTitle ? 'animate-slide-down' : 'opacity-0'} mb-4`}
          style={{ opacity: showTitle ? 1 : 0 }}
        >
          <div className="flex items-center gap-3 mb-1">
            <div className="w-8 h-1 rounded-full" style={{ background: '#FFD700', boxShadow: '0 0 8px rgba(255,215,0,0.5)' }} />
            <p className="font-semibold uppercase tracking-widest font-cyber" style={{ color: '#FFD700', fontSize: isPortrait ? '14px' : '14px', textShadow: '0 0 10px rgba(255,215,0,0.4)' }}>
              BIG Hat Trivia
            </p>
          </div>
          <h1 
            className="font-cyber text-white leading-none tracking-wider"
            style={{ fontSize: `${titleSize}px`, textShadow: '0 0 20px rgba(255,255,255,0.3), 0 0 40px rgba(0,212,255,0.2)' }}
          >
            {location}
          </h1>
          {date && (
            <p className="mt-1 font-mono" style={{ color: '#00d4ff', fontSize: isPortrait ? '20px' : '18px', textShadow: '0 0 8px rgba(0,212,255,0.4)' }}>
              {date}
            </p>
          )}
          {rounds.length > 0 && (
            <div className="flex gap-2 mt-2 flex-wrap">
              {rounds.map((r, i) => (
                <span 
                  key={i}
                  className="px-2 py-0.5 rounded font-semibold font-mono"
                  style={{ 
                    fontSize: isPortrait ? '14px' : '12px',
                    background: r.multiplier > 1 ? 'rgba(255, 215, 0, 0.15)' : 'rgba(255,255,255,0.06)',
                    color: r.multiplier > 1 ? '#FFD700' : 'rgba(200,200,255,0.5)',
                    border: r.multiplier > 1 ? '1px solid rgba(255, 215, 0, 0.3)' : '1px solid rgba(255,255,255,0.06)',
                  }}
                >
                  {r.label}{r.multiplier > 1 ? ` x${r.multiplier}` : ''}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Podium - Top 3 */}
        <div 
          className={`flex ${isPortrait ? 'flex-col gap-4' : 'gap-5 items-end'} mb-5 ${showPodium ? '' : 'opacity-0'}`}
          style={{ flex: '0 0 auto' }}
        >
          {podiumOrder.map((idx, displayIdx) => {
            const team = top3[idx];
            if (!team) return null;
            const rank = rankColors[idx];
            const IconComp = rank.icon;
            const isFirst = idx === 0;

            return (
              <div
                key={idx}
                data-testid={`leaderboard-row-${idx + 1}`}
                className={`glass-panel rounded-xl relative ${
                  showPodium ? 'animate-pop-in' : 'opacity-0'
                } ${isFirst ? 'sheen-effect' : ''}`}
                style={{
                  animationDelay: `${displayIdx * 120}ms`,
                  flex: isPortrait ? '0 0 auto' : isFirst ? '1.3' : '1',
                  borderColor: rank.border,
                  borderWidth: '2px',
                  padding: isPortrait ? '16px 28px 16px 20px' : isFirst ? '22px 32px 22px 28px' : '16px 28px 16px 20px',
                  boxShadow: `0 0 20px ${rank.glow}, inset 0 1px 0 rgba(255,255,255,0.1)`,
                  overflow: 'visible',
                }}
              >
                <div className="flex items-center gap-4">
                  <div 
                    className="flex items-center justify-center rounded-lg shrink-0"
                    style={{ 
                      background: rank.bg,
                      width: isFirst ? '60px' : '48px',
                      height: isFirst ? '60px' : '48px',
                    }}
                  >
                    <IconComp size={isFirst ? 30 : 24} style={{ color: rank.text }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <span 
                      className="font-cyber leading-none" 
                      style={{ fontSize: `${isFirst ? podiumRankSize1st : podiumRankSize}px`, color: rank.text }}
                    >
                      #{idx + 1}
                    </span>
                    <AutoShrinkText
                      text={team.name}
                      maxSize={isFirst ? podiumNameSize1st : podiumNameSize}
                      minSize={14}
                      className="font-semibold mt-0.5"
                      style={{ color: '#F4F2FF' }}
                    />
                  </div>
                  <div className="text-right shrink-0 pl-3" style={{ minWidth: isPortrait ? '80px' : '70px' }}>
                    <p 
                      className="font-mono-score font-bold leading-none" 
                      style={{ color: rank.text, fontSize: `${isFirst ? podiumScoreSize1st : podiumScoreSize}px` }}
                    >
                      {team.total}
                    </p>
                    <p className="mt-1 font-mono" style={{ color: 'rgba(244,242,255,0.4)', fontSize: '13px' }}>pts</p>
                  </div>
                </div>
                {team.roundScores && (
                  <div className="flex gap-2 mt-2">
                    {team.roundScores.map((s, si) => (
                      <span 
                        key={si} 
                        className="font-mono-score px-2 py-0.5 rounded"
                        style={{ fontSize: isPortrait ? '14px' : '12px', background: 'rgba(255,255,255,0.06)', color: 'rgba(244,242,255,0.5)' }}
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Remaining teams list */}
        {showList && rest.length > 0 && (
          <div className="flex-1 overflow-hidden">
            <div className="space-y-1.5">
              {rest.map((team, i) => (
                <div
                  key={i}
                  data-testid={`leaderboard-row-${i + 4}`}
                  className={`flex items-center gap-3 rounded-lg ${
                    i < visibleRows ? 'animate-slide-left' : 'opacity-0'
                  }`}
                  style={{
                    padding: isPortrait ? '8px 20px 8px 16px' : '6px 20px 6px 16px',
                    background: 'rgba(10, 0, 40, 0.6)',
                    border: '1px solid rgba(0, 212, 255, 0.1)',
                    animationDelay: `${i * 70}ms`,
                  }}
                >
                  <span 
                    className="font-mono-score font-semibold text-center shrink-0"
                    style={{ color: 'rgba(0, 212, 255, 0.5)', fontSize: `${listRankSize}px`, width: isPortrait ? '36px' : '32px' }}
                  >
                    {team.rank || i + 4}
                  </span>
                  <AutoShrinkText
                    text={team.name}
                    maxSize={listNameSize}
                    minSize={13}
                    className="flex-1 font-semibold"
                    style={{ color: '#F4F2FF' }}
                  />
                  {team.roundScores && !isPortrait && (
                    <div className="flex gap-1 shrink-0">
                      {team.roundScores.map((s, si) => (
                        <span key={si} className="font-mono-score" style={{ color: 'rgba(244,242,255,0.3)', fontSize: '12px' }}>
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                  <span 
                    className="font-mono-score font-bold text-right shrink-0" 
                    style={{ color: '#FFD700', fontSize: `${listScoreSize}px`, minWidth: isPortrait ? '50px' : '45px', textShadow: '0 0 6px rgba(255,215,0,0.3)' }}
                  >
                    {team.total}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer branding */}
        <div className="mt-auto pt-3 flex items-center gap-3" style={{ opacity: showList ? 1 : 0 }}>
          <div className="w-6 h-6 rounded-full" style={{ background: '#FFD700', boxShadow: '0 0 10px rgba(255,215,0,0.4)' }} />
          <span className="font-cyber text-sm tracking-wider" style={{ color: 'rgba(0, 212, 255, 0.4)' }}>
            BIG Hat Entertainment
          </span>
        </div>
      </div>
    </div>
  );
};

export { LeaderboardRender };
export default LeaderboardRender;
