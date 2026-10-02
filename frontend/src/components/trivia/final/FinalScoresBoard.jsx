import React from 'react';
import { SynthwaveBackdrop } from '../../scoreboard/render/SynthwaveBackdrop';

/**
 * alpha.66: the FINAL SCORES board (last slide of every show).
 * Merge of two things:
 *   - the BIGHat scoreboard tool's look: navy sky, stars, gold horizon,
 *     navy/gold theme, location + date title, round chips
 *   - the show's scrolling team list: every team box scrolls UP the screen
 *     (the background grid stays still).
 * Used by BOTH the audience window and the host window so they always match.
 *
 * props: teams  [{ name, swag, total, roundScores[] }]  (already sorted)
 *        rounds [{ label, multiplier }]
 *        location, date  (strings, optional)
 */

const GOLD = '#fbdd68';
const RANK = [
  { bg: 'linear-gradient(90deg, rgba(251,221,104,0.30), rgba(184,134,11,0.22))', border: '#fbdd68', glow: 'rgba(251,221,104,0.35)', text: '#fbdd68', icon: '🏆' },
  { bg: 'linear-gradient(90deg, rgba(220,226,240,0.22), rgba(140,150,175,0.16))', border: '#d5dbe8', glow: 'rgba(213,219,232,0.25)', text: '#e6eaf5', icon: '🥈' },
  { bg: 'linear-gradient(90deg, rgba(205,127,50,0.26), rgba(120,70,30,0.18))', border: '#cd7f32', glow: 'rgba(205,127,50,0.25)', text: '#e0a064', icon: '🥉' },
];
const REST = { bg: 'rgba(20, 27, 80, 0.72)', border: 'rgba(251,221,104,0.22)', glow: 'rgba(0,0,0,0)', text: 'rgba(251,221,104,0.75)' };

// 5 seconds per team, never faster than 20s, never slower than 150s.
export function scrollSeconds(teamCount) {
  return Math.min(150, Math.max(20, (Number(teamCount) || 0) * 5));
}

const FinalScoresBoard = ({ teams = [], rounds = [], location = '', date = '' }) => {
  const list = Array.isArray(teams) ? teams.filter(Boolean) : [];
  const dur = scrollSeconds(list.length);
  // A short list does not need to scroll: it just sits centred.
  const needsScroll = list.length > 5;

  return (
    <div data-testid="audience-final-scores" style={{ position: 'absolute', inset: 0, overflow: 'hidden', zIndex: 100 }}>
      <SynthwaveBackdrop still />
      <style>{`
        @keyframes finalBoardScroll {
          0%   { transform: translateY(var(--board-start, 62vh)); }
          100% { transform: translateY(-100%); }
        }
        .final-board-track { animation: finalBoardScroll ${dur}s linear infinite; will-change: transform; }
        .final-board-track:hover { animation-play-state: paused; }
      `}</style>

      <div style={{ position: 'relative', zIndex: 10, display: 'flex', flexDirection: 'column', height: '100%', padding: '3.5% 6% 2.5% 6%', boxSizing: 'border-box' }}>
        {/* Title */}
        <div style={{ flex: '0 0 auto', textAlign: 'center', paddingBottom: '1.2vh' }}>
          <p style={{ color: GOLD, fontSize: '1.5vh', letterSpacing: '0.35em', textTransform: 'uppercase', fontWeight: 700, margin: 0, textShadow: '0 0 10px rgba(251,221,104,0.45)' }}>
            BIG Hat Trivia
          </p>
          <h2 style={{ color: '#fff', fontSize: '6.6vh', fontWeight: 800, margin: '0.6vh 0 0 0', lineHeight: 1.05, fontFamily: 'Lemonada, cursive', textShadow: '0 0 22px rgba(255,255,255,0.28), 0 0 44px rgba(89,115,247,0.35)' }}>
            {location || 'Final Scores'}
          </h2>
          <p style={{ color: GOLD, fontSize: '2.4vh', margin: '0.8vh 0 0 0', fontWeight: 600 }}>
            🏆 Final Scores{date ? `  ·  ${date}` : ''}
          </p>
          {rounds.length > 0 && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap', marginTop: '1.2vh' }}>
              {rounds.map((r, i) => (
                <span key={i} style={{
                  fontSize: '1.7vh', padding: '2px 10px', borderRadius: 6, fontWeight: 700, fontFamily: 'monospace',
                  background: r.multiplier > 1 ? 'rgba(251,221,104,0.16)' : 'rgba(255,255,255,0.07)',
                  color: r.multiplier > 1 ? GOLD : 'rgba(210,215,255,0.7)',
                  border: r.multiplier > 1 ? '1px solid rgba(251,221,104,0.4)' : '1px solid rgba(255,255,255,0.1)',
                }}>
                  {r.label}{r.multiplier > 1 ? ` x${r.multiplier}` : ''}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Scrolling team boxes */}
        <div style={{
          flex: '1 1 auto', minHeight: 0, position: 'relative', overflow: 'hidden',
          display: needsScroll ? 'block' : 'flex', alignItems: 'center', justifyContent: 'center',
          WebkitMaskImage: 'linear-gradient(to bottom, transparent 0%, #000 6%, #000 94%, transparent 100%)',
          maskImage: 'linear-gradient(to bottom, transparent 0%, #000 6%, #000 94%, transparent 100%)',
        }}>
          <div className={needsScroll ? 'final-board-track' : ''} data-testid="audience-final-scores-scroll" style={{ width: '100%' }}>
            {list.map((team, idx) => {
              const c = idx < 3 ? RANK[idx] : REST;
              const scores = Array.isArray(team.roundScores) ? team.roundScores : [];
              return (
                <div key={team.id || idx} data-testid={`final-team-${idx + 1}`} style={{
                  background: c.bg, border: `2px solid ${c.border}`, borderRadius: 14,
                  padding: '1.6vh 2.2vw', marginBottom: '1.4vh',
                  boxShadow: `0 0 22px ${c.glow}, inset 0 1px 0 rgba(255,255,255,0.1)`,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1.6vw', minWidth: 0 }}>
                      <span style={{ fontSize: '4.4vh', fontWeight: 800, color: c.text, minWidth: '4.2vw', fontFamily: 'monospace' }}>
                        {idx < 3 ? c.icon : `${idx + 1}.`}
                      </span>
                      <div style={{ minWidth: 0 }}>
                        <h3 style={{ margin: 0, fontSize: '3.8vh', fontWeight: 800, color: '#F4F2FF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {team.name || `Team ${idx + 1}`}
                        </h3>
                        {team.swag ? <p style={{ margin: 0, fontSize: '1.9vh', color: 'rgba(244,242,255,0.6)' }}>{team.swag}</p> : null}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', flex: '0 0 auto' }}>
                      <p style={{ margin: 0, fontSize: '6vh', fontWeight: 800, color: '#FFD700', lineHeight: 1, fontFamily: 'monospace', textShadow: '0 0 10px rgba(255,215,0,0.35)' }}>
                        {team.total || 0}
                      </p>
                      <p style={{ margin: '0.4vh 0 0 0', fontSize: '1.6vh', color: 'rgba(244,242,255,0.45)' }}>Total Points</p>
                    </div>
                  </div>
                  {scores.length > 0 && (
                    <div style={{ display: 'flex', gap: 10, marginTop: '1.2vh', flexWrap: 'wrap' }}>
                      {scores.map((sc, ri) => (
                        <div key={ri} style={{ background: 'rgba(0,0,20,0.5)', padding: '0.5vh 1vw', borderRadius: 8 }}>
                          <span style={{ fontSize: '1.7vh', color: 'rgba(244,242,255,0.55)' }}>{rounds[ri]?.label || `R${ri + 1}`}:</span>
                          <span style={{ fontSize: '2.2vh', fontWeight: 700, color: '#fff', marginLeft: 8 }}>{sc || 0}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: 12, paddingTop: '1vh', opacity: 0.55 }}>
          <div style={{ width: 22, height: 22, borderRadius: '50%', background: '#FFD700', boxShadow: '0 0 10px rgba(255,215,0,0.45)' }} />
          <span style={{ color: GOLD, fontSize: '1.8vh', letterSpacing: '0.12em' }}>BIG Hat Entertainment</span>
        </div>
      </div>
    </div>
  );
};

export default FinalScoresBoard;
