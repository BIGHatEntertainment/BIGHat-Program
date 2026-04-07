import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Trash2, ArrowUpDown, Send, X } from 'lucide-react';
import { useToast } from '../hooks/use-toast';

const ScoreTrackerModal = ({ isOpen, onClose, defaultRoundMode = 5, onSendScores, presentationId }) => {
  const { toast } = useToast();
  const [roundMode, setRoundMode] = useState(defaultRoundMode);
  const [teams, setTeams] = useState([]);
  const [maxTeams] = useState(20);

  // Round configurations
  const roundConfigs = {
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
  };

  const currentRounds = roundConfigs[roundMode];

  const initializeTeams = () => {
    const initialTeams = Array.from({ length: maxTeams }, (_, i) => ({
      id: i,
      swag: '',
      name: '',
      rounds: Array(6).fill('')
    }));
    setTeams(initialTeams);
  };

  // Initialize teams - ISOLATED PER PRESENTATION
  useEffect(() => {
    if (isOpen && presentationId) {
      // Use presentation-specific key to prevent cross-location interference
      const storageKey = `triviaScoreData_${presentationId}`;
      const savedData = localStorage.getItem(storageKey);
      if (savedData) {
        const parsed = JSON.parse(savedData);
        setTeams(parsed.teams || []);
        setRoundMode(parsed.roundMode || defaultRoundMode);
      } else {
        initializeTeams();
      }
    }
  }, [isOpen, presentationId, defaultRoundMode]);

  // Save to localStorage whenever data changes - ISOLATED PER PRESENTATION
  useEffect(() => {
    if (teams.length > 0 && isOpen && presentationId) {
      // Use presentation-specific key to prevent cross-location interference
      const storageKey = `triviaScoreData_${presentationId}`;
      localStorage.setItem(storageKey, JSON.stringify({ teams, roundMode }));
    }
  }, [teams, roundMode, isOpen, presentationId]);

  // Calculate total for a team
  const calculateTotal = (team) => {
    let total = parseInt(team.swag) || 0;
    currentRounds.forEach((round, index) => {
      const score = parseInt(team.rounds[index]) || 0;
      total += score * round.multiplier;
    });
    return total;
  };

  // Update team data
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

  // Clear all data
  const handleClear = () => {
    if (window.confirm('Are you sure you want to clear all scores? This action cannot be undone.')) {
      initializeTeams();
      toast({
        title: 'Cleared',
        description: 'All scores have been cleared',
      });
    }
  };

  // Sort teams by total score
  const handleSort = () => {
    const sorted = [...teams].sort((a, b) => {
      const totalA = calculateTotal(a);
      const totalB = calculateTotal(b);
      return totalB - totalA;
    });
    setTeams(sorted);
    toast({
      title: 'Sorted',
      description: 'Teams sorted by total score',
    });
  };

  // Send to presentation
  const handleSendToPresentation = () => {
    // Filter out empty teams
    const activeTeams = teams.filter(team => team.name.trim() !== '');
    
    // Prepare data for export
    const exportData = activeTeams.map(team => ({
      name: team.name,
      swag: team.swag,
      rounds: team.rounds.slice(0, roundMode),
      total: calculateTotal(team)
    }));

    // Call parent callback
    if (onSendScores) {
      onSendScores(exportData, roundMode, currentRounds);
    }

    toast({
      title: 'Sent to Presentation',
      description: `${activeTeams.length} teams sent successfully`,
    });
    
    // Close modal after sending
    onClose();
  };

  // Change round mode
  const changeRoundMode = (mode) => {
    if (window.confirm(`Switch to ${mode}-round mode? This will keep your data but adjust the rounds.`)) {
      setRoundMode(mode);
      toast({
        title: 'Mode Changed',
        description: `Switched to ${mode}-round mode`,
      });
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4 overflow-auto">
      <div className="bg-gray-100 rounded-lg w-full max-w-[1600px] max-h-[90vh] overflow-auto">
        <div className="p-6">
          {/* Header */}
          <div className="bg-white rounded-lg shadow-md p-6 mb-4">
            <div className="flex items-center justify-between mb-4">
              <h1 className="text-3xl font-bold text-gray-800">BIG Hat Trivia Score Tracker</h1>
              <div className="flex gap-3 items-center">
                <Button
                  onClick={() => changeRoundMode(3)}
                  variant={roundMode === 3 ? 'default' : 'outline'}
                  className="font-semibold"
                >
                  3 Rounds
                </Button>
                <Button
                  onClick={() => changeRoundMode(5)}
                  variant={roundMode === 5 ? 'default' : 'outline'}
                  className="font-semibold"
                >
                  5 Rounds
                </Button>
                <Button
                  onClick={() => changeRoundMode(6)}
                  variant={roundMode === 6 ? 'default' : 'outline'}
                  className="font-semibold"
                >
                  6 Rounds
                </Button>
                <Button
                  onClick={onClose}
                  variant="ghost"
                  size="sm"
                  className="ml-4"
                >
                  <X className="w-5 h-5" />
                </Button>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3 flex-wrap">
              <Button
                onClick={handleClear}
                variant="destructive"
                className="flex items-center gap-2"
              >
                <Trash2 size={18} />
                Clear
              </Button>
              <Button
                onClick={handleSort}
                className="flex items-center gap-2 bg-yellow-500 hover:bg-yellow-600 text-black"
              >
                <ArrowUpDown size={18} />
                Sort
              </Button>
              <Button
                onClick={handleSendToPresentation}
                className="flex items-center gap-2 bg-green-600 hover:bg-green-700"
              >
                <Send size={18} />
                Send to Presentation
              </Button>
            </div>
          </div>

          {/* Score Table */}
          <div className="bg-white rounded-lg shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-gray-200">
                    <th className="border border-gray-400 p-2 text-sm font-bold w-20">Swag</th>
                    <th className="border border-gray-400 p-2 text-sm font-bold min-w-[250px]">Team Name</th>
                    {currentRounds.map((round, index) => (
                      <th
                        key={index}
                        className="border border-gray-400 p-2 text-sm font-bold w-24"
                        style={{ backgroundColor: round.color, color: 'white' }}
                      >
                        {round.label}
                        {round.multiplier > 1 && (
                          <span className="text-xs ml-1">(x{round.multiplier})</span>
                        )}
                      </th>
                    ))}
                    <th className="border border-gray-400 p-2 text-sm font-bold w-24 bg-blue-600 text-white">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {teams.map((team, teamIndex) => (
                    <tr key={team.id} className={teamIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                      <td className="border border-gray-400 p-1">
                        <Input
                          type="number"
                          value={team.swag}
                          onChange={(e) => updateTeam(team.id, 'swag', e.target.value)}
                          className="w-full text-center border-0 focus-visible:ring-0 bg-transparent"
                          min="0"
                        />
                      </td>
                      <td className="border border-gray-400 p-1">
                        <Input
                          type="text"
                          value={team.name}
                          onChange={(e) => updateTeam(team.id, 'name', e.target.value)}
                          className="w-full border-0 focus-visible:ring-0 bg-blue-800 text-white font-medium placeholder:text-blue-300"
                          placeholder="Enter team name"
                        />
                      </td>
                      {currentRounds.map((round, roundIndex) => (
                        <td key={roundIndex} className="border border-gray-400 p-1">
                          <Input
                            type="number"
                            value={team.rounds[roundIndex]}
                            onChange={(e) => updateTeam(team.id, `round${roundIndex}`, e.target.value)}
                            className="w-full text-center border-0 focus-visible:ring-0 bg-transparent font-medium"
                            min="0"
                          />
                        </td>
                      ))}
                      <td className="border border-gray-400 p-2 text-center font-bold text-lg bg-blue-600 text-white">
                        {calculateTotal(team)}
                      </td>
                    </tr>
                  ))}
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