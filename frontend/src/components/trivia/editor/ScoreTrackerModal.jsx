import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Button } from '../../ui/button';
import { Input } from '../../ui/input';
import { Trash2, ArrowUpDown, Send, X } from 'lucide-react';
import { toast } from '../../../utils/toastCompat';

const ScoreTrackerModal = ({ isOpen, onClose, defaultRoundMode = 5, onSendScores, presentationId, roundTypes = [] }) => {
  const [roundMode, setRoundMode] = useState(defaultRoundMode);
  const [teams, setTeams] = useState([]);
  const maxTeams = 20;
  const [focusedInput, setFocusedInput] = useState(null);

  const prevOpenRef = useRef(false);
  const prevPresentationIdRef = useRef(null);

  const roundColorMap = useMemo(() => ({
    'MC': '#22c55e',
    'REG': '#ef4444',
    'MISC': '#3b82f6',
    'MYS': '#a855f7',
    'BIG': '#eab308'
  }), []);

  const roundMultiplierMap = useMemo(() => ({
    'MC': 1,
    'REG': 1,
    'MISC': 1,
    'MYS': 2,
    'BIG': 3
  }), []);

  const baseRoundConfigs = useMemo(() => ({
    3: [
      { label: 'REG', color: '#ef4444', multiplier: 1 },
      { label: 'MISC', color: '#3b82f6', multiplier: 1 },
      { label: 'BIG', color: '#eab308', multiplier: 3 }
    ],
    5: [
      { label: 'MC', color: '#22c55e', multiplier: 1 },
      { label: 'REG', color: '#ef4444', multiplier: 1 },
      { label: 'MISC', color: '#3b82f6', multiplier: 1 },
      { label: 'MYS', color: '#a855f7', multiplier: 2 },
      { label: 'BIG', color: '#eab308', multiplier: 3 }
    ],
    6: [
      { label: 'MC', color: '#22c55e', multiplier: 1 },
      { label: 'REG', color: '#ef4444', multiplier: 1 },
      { label: 'REG', color: '#ef4444', multiplier: 1 },
      { label: 'MISC', color: '#3b82f6', multiplier: 1 },
      { label: 'MYS', color: '#a855f7', multiplier: 2 },
      { label: 'BIG', color: '#eab308', multiplier: 3 }
    ]
  }), []);

  const currentRounds = useMemo(() => {
    if (roundTypes && roundTypes.length > 0 && roundTypes.length === roundMode) {
      return roundTypes.map(type => {
        const upperType = (type || 'REG').toUpperCase();
        return {
          label: upperType,
          color: roundColorMap[upperType] || '#ef4444',
          multiplier: roundMultiplierMap[upperType] || 1
        };
      });
    }
    return baseRoundConfigs[roundMode] || baseRoundConfigs[5];
  }, [roundMode, roundTypes, roundColorMap, roundMultiplierMap, baseRoundConfigs]);

  const initializeTeams = useCallback(() => {
    const initialTeams = Array.from({ length: maxTeams }, (_, i) => ({
      id: i,
      swag: '',
      name: '',
      rounds: Array(6).fill('')
    }));
    return initialTeams;
  }, [maxTeams]);

  useEffect(() => {
    const justOpened = isOpen && !prevOpenRef.current;
    const presentationChanged = presentationId !== prevPresentationIdRef.current;

    if (isOpen && (justOpened || presentationChanged)) {
      let detectedRoundMode = defaultRoundMode;
      if (roundTypes && roundTypes.length > 0 && [3, 5, 6].includes(roundTypes.length)) {
        detectedRoundMode = roundTypes.length;
      }
      if ([3, 5, 6].includes(detectedRoundMode)) {
        setRoundMode(detectedRoundMode);
      }

      if (presentationId && presentationId !== 'undefined') {
        const storageKey = `triviaScoreData_${presentationId}`;
        const savedData = localStorage.getItem(storageKey);
        if (savedData) {
          const parsed = JSON.parse(savedData);
          setTeams(parsed.teams || initializeTeams());
          if (detectedRoundMode === 5 && parsed.roundMode && [3, 5, 6].includes(parsed.roundMode)) {
            setRoundMode(parsed.roundMode);
          }
        } else {
          setTeams(initializeTeams());
        }
      } else {
        setTeams(initializeTeams());
      }
    }

    prevOpenRef.current = isOpen;
    prevPresentationIdRef.current = presentationId;
  }, [isOpen, presentationId, defaultRoundMode, roundTypes, initializeTeams]);

  useEffect(() => {
    if (isOpen && roundTypes?.length > 0 && [3, 5, 6].includes(roundTypes.length) && roundMode !== roundTypes.length) {
      const newLen = roundTypes.length;
      const timer = setTimeout(() => {
        setRoundMode(newLen);
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [roundTypes, isOpen, roundMode]);

  const saveTimerRef = useRef(null);
  useEffect(() => {
    if (teams.length > 0 && isOpen && presentationId) {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        const storageKey = `triviaScoreData_${presentationId}`;
        localStorage.setItem(storageKey, JSON.stringify({ teams, roundMode }));
      }, 300);
    }
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current); };
  }, [teams, roundMode, isOpen, presentationId]);

  const calculateTotal = (team) => {
    if (!team) return 0;
    let total = parseInt(team.swag) || 0;
    const teamRounds = Array.isArray(team.rounds) ? team.rounds : [];
    currentRounds.forEach((round, index) => {
      const score = parseInt(teamRounds[index]) || 0;
      const multiplier = round?.multiplier || 1;
      total += score * multiplier;
    });
    return total;
  };

  const updateTeam = (teamId, field, value) => {
    setTeams(prev => prev.map(team => {
      if (team.id === teamId) {
        if (field === 'swag' || field === 'name') {
          return { ...team, [field]: value };
        } else if (field.startsWith('round')) {
          const roundIndex = parseInt(field.replace('round', ''));
          const newRounds = [...team.rounds];
          newRounds[roundIndex] = value;
          return { ...team, rounds: newRounds };
        }
      }
      return team;
    }));
  };

  const handleClear = () => {
    if (window.confirm('Are you sure you want to clear all scores? This action cannot be undone.')) {
      setTeams(initializeTeams());
      toast({ title: 'Cleared', description: 'All scores have been cleared' });
    }
  };

  const handleSort = () => {
    const sorted = [...teams].sort((a, b) => calculateTotal(b) - calculateTotal(a));
    setTeams(sorted);
    toast({ title: 'Sorted', description: 'Teams sorted by total score' });
  };

  const handleSendToPresentation = () => {
    const activeTeams = teams.filter(team => team && team.name && team.name.trim() !== '');
    if (activeTeams.length === 0) {
      toast({ title: 'No Teams', description: 'Please add at least one team with a name', variant: 'destructive' });
      return;
    }
    const exportData = activeTeams.map(team => ({
      name: team.name || '',
      swag: team.swag || '',
      rounds: Array.isArray(team.rounds) ? team.rounds.slice(0, roundMode) : [],
      total: calculateTotal(team)
    }));
    if (onSendScores) {
      onSendScores(exportData, roundMode, currentRounds);
    }
    toast({ title: 'Sent to Presentation', description: `${activeTeams.length} teams sent successfully` });
    onClose();
  };

  const changeRoundMode = (mode) => {
    if (window.confirm(`Switch to ${mode}-round mode? This will keep your data but adjust the rounds.`)) {
      setRoundMode(mode);
      toast({ title: 'Mode Changed', description: `Switched to ${mode}-round mode` });
    }
  };

  if (!isOpen) return null;

  const handleKeyDown = (e, teamIndex, fieldType) => {
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      const direction = e.key === 'ArrowUp' ? -1 : 1;
      const newIndex = teamIndex + direction;
      if (newIndex >= 0 && newIndex < teams.length) {
        let selector;
        if (fieldType === 'swag') {
          selector = `[data-testid="swag-input-${newIndex}"]`;
        } else if (fieldType === 'name') {
          selector = `[data-testid="team-name-input-${newIndex}"]`;
        } else if (fieldType.startsWith('round')) {
          const roundIdx = fieldType.replace('round', '');
          selector = `[data-testid="round-${roundIdx}-input-${newIndex}"]`;
        }
        if (selector) {
          const nextInput = document.querySelector(selector);
          if (nextInput) nextInput.focus();
        }
      }
    }
  };

  return (
    <div className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4 overflow-auto">
      <div className="bg-gray-100 rounded-lg w-full max-w-[1600px] max-h-[90vh] overflow-auto">
        <div className="p-6">
          {/* Header */}
          <div className="bg-white rounded-lg shadow-md p-6 mb-4">
            <div className="flex items-center justify-between mb-4">
              <h1 className="text-3xl font-bold text-gray-800">BIG Hat Trivia Score Tracker</h1>
              <div className="flex gap-3 items-center">
                {[3, 5, 6].map(mode => (
                  <Button
                    key={mode}
                    onClick={() => changeRoundMode(mode)}
                    className={`font-semibold ${roundMode === mode ? 'bg-green-500 hover:bg-green-600 text-white' : 'bg-yellow-400 hover:bg-yellow-500 text-black'}`}
                  >
                    {mode} Rounds
                  </Button>
                ))}
                <Button onClick={onClose} variant="ghost" size="sm" className="ml-4 bg-red-500 hover:bg-red-600 text-white">
                  <X className="w-5 h-5" />
                </Button>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3 flex-wrap">
              <Button onClick={handleClear} variant="destructive" className="flex items-center gap-2 bg-black hover:bg-gray-800 text-white border border-white">
                <Trash2 size={18} /> Clear
              </Button>
              <Button onClick={handleSort} className="flex items-center gap-2 bg-yellow-500 hover:bg-yellow-600 text-black">
                <ArrowUpDown size={18} /> Sort
              </Button>
              <Button onClick={handleSendToPresentation} className="flex items-center gap-2 bg-green-600 hover:bg-green-700">
                <Send size={18} /> Send to Presentation
              </Button>
            </div>
          </div>

          {/* Score Table */}
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-gray-200">
                    <th className="border border-gray-400 p-2 text-sm font-bold w-20 bg-gray-600 text-white">Swag</th>
                    <th className="border border-gray-400 p-2 text-sm font-bold min-w-[250px] bg-gray-600 text-white">Team Name</th>
                    {currentRounds.map((round, index) => (
                      <th key={index} className="border border-gray-400 p-2 text-sm font-bold w-24" style={{ backgroundColor: round.color, color: 'white' }}>
                        {round.label}
                        {round.multiplier > 1 && <span className="text-xs ml-1">(x{round.multiplier})</span>}
                      </th>
                    ))}
                    <th className="border border-gray-400 p-2 text-sm font-bold w-24 bg-blue-600 text-white">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {teams.map((team, teamIndex) => {
                    const isTeamHighlighted = focusedInput?.teamId === team.id && focusedInput?.type === 'score';
                    return (
                      <tr key={team.id} className={teamIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="border border-gray-400 p-1">
                          <Input
                            type="number"
                            value={team.swag}
                            onChange={(e) => updateTeam(team.id, 'swag', e.target.value)}
                            onFocus={() => setFocusedInput({ teamId: team.id, type: 'score' })}
                            onBlur={() => setFocusedInput(null)}
                            onKeyDown={(e) => handleKeyDown(e, teamIndex, 'swag')}
                            className="w-full text-center border-0 focus-visible:ring-0 bg-transparent text-black font-medium"
                            min="0"
                            data-testid={`swag-input-${teamIndex}`}
                          />
                        </td>
                        <td className={`border border-gray-400 p-1 transition-all duration-200 ${isTeamHighlighted ? 'ring-4 ring-yellow-400 ring-inset bg-yellow-100' : ''}`}>
                          <Input
                            type="text"
                            value={team.name}
                            onChange={(e) => updateTeam(team.id, 'name', e.target.value)}
                            onKeyDown={(e) => handleKeyDown(e, teamIndex, 'name')}
                            className={`w-full border-0 focus-visible:ring-0 font-medium placeholder:text-blue-300 transition-all duration-200 ${isTeamHighlighted ? 'bg-yellow-400 text-black font-bold' : 'bg-blue-800 text-white'}`}
                            placeholder="Enter team name"
                            data-testid={`team-name-input-${teamIndex}`}
                          />
                        </td>
                        {currentRounds.map((round, roundIndex) => (
                          <td key={roundIndex} className="border border-gray-400 p-1">
                            <Input
                              type="number"
                              value={team.rounds[roundIndex]}
                              onChange={(e) => updateTeam(team.id, `round${roundIndex}`, e.target.value)}
                              onFocus={() => setFocusedInput({ teamId: team.id, type: 'score', roundIndex })}
                              onBlur={() => setFocusedInput(null)}
                              onKeyDown={(e) => handleKeyDown(e, teamIndex, `round${roundIndex}`)}
                              className="w-full text-center border-0 focus-visible:ring-0 bg-transparent text-black font-medium"
                              min="0"
                              data-testid={`round-${roundIndex}-input-${teamIndex}`}
                            />
                          </td>
                        ))}
                        <td className="border border-gray-400 p-2 text-center font-bold text-lg bg-blue-600 text-white">
                          {calculateTotal(team)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Instructions */}
          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-green-100 border-2 border-green-600 rounded-lg p-4">
              <h3 className="font-bold text-green-800 mb-2">1) Enter team names and points for swag</h3>
            </div>
            <div className="bg-green-100 border-2 border-green-600 rounded-lg p-4">
              <h3 className="font-bold text-green-800 mb-2">2) Enter each rounds points as they appear</h3>
            </div>
            <div className="bg-green-100 border-2 border-green-600 rounded-lg p-4">
              <h3 className="font-bold text-green-800 mb-2">3) Sort & Send after each round</h3>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScoreTrackerModal;
