import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import RenderStage from '../../components/scoreboard/render/RenderStage';
import LeaderboardRender from '../../components/scoreboard/render/LeaderboardRender';
import BracketRender from '../../components/scoreboard/render/BracketRender';
import api from '../../lib/scoreboardApi';

/**
 * Live Render View - Full screen, no chrome.
 * Used for screensharing during live presentations.
 */
const LiveRender = () => {
  const [searchParams] = useSearchParams();
  const mode = searchParams.get('mode') || 'leaderboard';
  const aspect = searchParams.get('aspect') || 'landscape';
  
  const [data, setData] = useState(null);
  const [bracket, setBracket] = useState(null);
  const [teams, setTeams] = useState([]);
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    // Try to get data from localStorage (set by dashboard)
    const storedData = localStorage.getItem('liveRenderData');
    if (storedData) {
      try {
        const parsed = JSON.parse(storedData);
        if (parsed.data) setData(parsed.data);
        if (parsed.bracket) setBracket(parsed.bracket);
        if (parsed.teams) setTeams(parsed.teams);
      } catch (e) {
        console.error('Failed to parse stored data:', e);
      }
    }

    // Also try to fetch latest from API
    const fetchData = async () => {
      try {
        const res = await api.getScores();
        if (res.data.files?.length > 0 && !storedData) {
          setData(res.data.files[0].data);
        }
      } catch (e) {
        console.error('Failed to fetch scores:', e);
      }
    };
    fetchData();
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === '?') setShowHelp(prev => !prev);
      if (e.key === 'Escape') setShowHelp(false);
      if (e.key === 'f' || e.key === 'F') {
        if (document.fullscreenElement) {
          document.exitFullscreen();
        } else {
          document.documentElement.requestFullscreen();
        }
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  return (
    <div 
      className="w-screen h-screen overflow-hidden flex items-center justify-center"
      style={{ background: '#0A0718' }}
    >
      <RenderStage aspectRatio={aspect} isLiveView={false}>
        {mode === 'leaderboard' ? (
          <LeaderboardRender 
            data={data}
            aspectRatio={aspect}
            animationSpeed={1}
            isAnimating={true}
          />
        ) : (
          <BracketRender 
            bracket={bracket}
            teams={teams}
            aspectRatio={aspect}
            animationSpeed={1}
            isAnimating={true}
          />
        )}
      </RenderStage>

      {/* Help overlay */}
      {showHelp && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(10, 7, 24, 0.9)' }}
          onClick={() => setShowHelp(false)}
        >
          <div className="glass-panel rounded-xl p-8 max-w-md">
            <h2 className="font-display text-2xl mb-4" style={{ color: '#F4F2FF' }}>Keyboard Shortcuts</h2>
            <div className="space-y-2 text-sm" style={{ color: 'rgba(244,242,255,0.7)' }}>
              <p><kbd className="px-2 py-0.5 rounded bg-white/10">?</kbd> Toggle help</p>
              <p><kbd className="px-2 py-0.5 rounded bg-white/10">F</kbd> Toggle fullscreen</p>
              <p><kbd className="px-2 py-0.5 rounded bg-white/10">Esc</kbd> Close help</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LiveRender;
