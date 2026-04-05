import React, { useState, useEffect } from 'react';
import { Wand2, MapPin, User, ChevronRight, ChevronLeft, X, Loader2, Check, HelpCircle } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROUND_TYPE_CONFIG = {
  MC: { label: 'Multiple Choice', color: '#22c55e' },
  REG: { label: 'General Knowledge', color: '#ef4444' },
  MISC: { label: 'Specific Topic', color: '#3b82f6' },
  MYS: { label: 'Mystery', color: '#a855f7' },
  BIG: { label: 'BIG Question', color: '#fbdd68' },
};

export default function TriviaBuilderWizard({ open, onClose, onComplete, locations = [] }) {
  const [step, setStep] = useState(1);
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [selectedHost, setSelectedHost] = useState(null);
  const [numRounds, setNumRounds] = useState(5);
  const [roundSelections, setRoundSelections] = useState({});
  const [availableRounds, setAvailableRounds] = useState({});
  const [hostsList, setHostsList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState('');

  // The 5 standard round slots + optional 6th
  const roundSlots = numRounds === 6
    ? ['MC', 'REG', 'MISC', 'MYS', 'BIG', 'REG']
    : ['MC', 'REG', 'MISC', 'MYS', 'BIG'];

  useEffect(() => {
    if (!open) {
      setStep(1);
      setSelectedLocation(null);
      setSelectedHost(null);
      setNumRounds(5);
      setRoundSelections({});
      setError('');
    }
  }, [open]);

  const loadRoundsForLocation = async (locationName) => {
    setLoading(true);
    try {
      const [regRes, miscRes, bigRes, mcRes, mysRes, hostsRes] = await Promise.all([
        axios.get(`${API}/trivia/round-files/reg`, { params: { location: locationName } }),
        axios.get(`${API}/trivia/round-files/misc`, { params: { location: locationName } }),
        axios.get(`${API}/trivia/round-files/big`, { params: { location: locationName } }),
        axios.get(`${API}/trivia/round-files/mc`, { params: { location: locationName } }),
        axios.get(`${API}/trivia/round-files/mys`, { params: { location: locationName } }),
        axios.get(`${API}/trivia/hosts`),
      ]);
      setAvailableRounds({
        REG: regRes.data, MISC: miscRes.data, BIG: bigRes.data,
        MC: mcRes.data, MYS: mysRes.data,
      });
      setHostsList(hostsRes.data);
    } catch (err) {
      setError('Failed to load round data');
    } finally {
      setLoading(false);
    }
  };

  const handleLocationSelect = (loc) => {
    setSelectedLocation(loc);
    loadRoundsForLocation(loc);
    setStep(2);
  };

  const handleRoundSelect = (slotIndex, round) => {
    setRoundSelections(prev => ({ ...prev, [slotIndex]: round }));
  };

  const allRoundsSelected = roundSlots.every((_, i) => roundSelections[i]);

  const handleBuild = async () => {
    setBuilding(true);
    setError('');
    try {
      const userName = localStorage.getItem('userName') || 'unknown';
      const rounds = roundSlots.map((_, i) => roundSelections[i]?.path || '');
      const roundNames = roundSlots.map((_, i) => roundSelections[i]?.name || '');
      const roundTypes = [...roundSlots];
      const presName = `${selectedLocation} - ${new Date().toLocaleDateString()}`;

      await axios.post(`${API}/presentations/import-trivia`, {
        userName,
        host: selectedHost?.path || '',
        hostName: selectedHost?.name || '',
        location: selectedLocation,
        locationName: selectedLocation,
        numRounds,
        rounds,
        roundTypes,
        roundNames,
        presentationName: presName,
      });

      // Also save as story build
      await axios.post(`${API}/story-builds/save`, {
        host: selectedHost?.name || '',
        location: selectedLocation,
        locationFolder: selectedLocation,
        numRounds,
        roundNames,
        roundTypes,
        presentationName: presName,
        createdBy: userName,
      }).catch(() => {}); // Non-critical

      if (onComplete) onComplete();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to build presentation');
    } finally {
      setBuilding(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center" style={{ backgroundColor: 'rgba(0,0,0,0.85)' }}>
      <div className="relative w-full max-w-3xl mx-4 max-h-[90vh] overflow-y-auto rounded-2xl" style={{ background: 'linear-gradient(135deg, #0a1940 0%, #000e2a 100%)', border: '2px solid rgba(251, 221, 104, 0.3)' }}>
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 rounded-t-2xl" style={{ backgroundColor: 'rgba(0, 14, 42, 0.95)', borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
          <div className="flex items-center gap-3">
            <Wand2 size={24} style={{ color: '#fbdd68' }} />
            <div>
              <h2 className="text-lg font-bold" style={{ color: '#fbdd68' }}>Build Wizard</h2>
              <p className="text-xs" style={{ color: '#8892b0' }}>Step {step} of 5</p>
            </div>
          </div>
          {/* Step indicators */}
          <div className="flex items-center gap-1.5">
            {[1,2,3,4,5].map(s => (
              <div key={s} className="w-8 h-1.5 rounded-full transition-all" style={{ backgroundColor: s <= step ? '#fbdd68' : 'rgba(251, 221, 104, 0.15)' }} />
            ))}
            <button onClick={onClose} className="ml-4 p-1.5 rounded-lg hover:bg-white/10 transition-colors">
              <X size={20} style={{ color: '#8892b0' }} />
            </button>
          </div>
        </div>

        <div className="p-6">
          {error && (
            <div className="mb-4 p-3 rounded-lg text-sm" style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#ef4444' }}>
              {error}
            </div>
          )}

          {/* Step 1: Location */}
          {step === 1 && (
            <div>
              <h3 className="text-white font-semibold mb-1">Select Location</h3>
              <p className="text-xs mb-5" style={{ color: '#8892b0' }}>Choose the venue for this trivia show</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {locations.map(loc => (
                  <button key={loc} onClick={() => handleLocationSelect(loc)} className="p-4 rounded-xl text-left transition-all hover:scale-[1.02]" style={{ background: 'linear-gradient(135deg, #141b50, #0a1940)', border: '1px solid rgba(251, 221, 104, 0.15)' }} data-testid={`wizard-location-${loc}`}>
                    <MapPin size={16} style={{ color: '#fbdd68' }} className="mb-2" />
                    <span className="text-sm font-medium text-white block">{loc}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Host */}
          {step === 2 && (
            <div>
              <h3 className="text-white font-semibold mb-1">Select Host</h3>
              <p className="text-xs mb-5" style={{ color: '#8892b0' }}>Who's hosting at {selectedLocation}?</p>
              {loading ? (
                <div className="text-center py-8">
                  <Loader2 size={24} className="animate-spin mx-auto mb-2" style={{ color: '#fbdd68' }} />
                  <p className="text-sm" style={{ color: '#8892b0' }}>Loading hosts...</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {hostsList.map(host => (
                    <button key={host.name} onClick={() => { setSelectedHost(host); setStep(3); }} className="p-4 rounded-xl text-left transition-all hover:scale-[1.02]" style={{ background: selectedHost?.name === host.name ? 'rgba(251, 221, 104, 0.15)' : 'linear-gradient(135deg, #141b50, #0a1940)', border: `1px solid ${selectedHost?.name === host.name ? 'rgba(251, 221, 104, 0.5)' : 'rgba(251, 221, 104, 0.15)'}` }}>
                      <User size={16} style={{ color: '#fbdd68' }} className="mb-2" />
                      <span className="text-sm font-medium text-white block">{host.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Step 3: Number of Rounds */}
          {step === 3 && (
            <div>
              <h3 className="text-white font-semibold mb-1">Number of Rounds</h3>
              <p className="text-xs mb-5" style={{ color: '#8892b0' }}>Standard is 5 rounds, or 6 for an extended show</p>
              <div className="flex gap-4 justify-center">
                {[5, 6].map(n => (
                  <button key={n} onClick={() => { setNumRounds(n); setStep(4); }} className="w-32 h-32 rounded-2xl flex flex-col items-center justify-center transition-all hover:scale-105" style={{ background: numRounds === n ? 'rgba(251, 221, 104, 0.15)' : 'linear-gradient(135deg, #141b50, #0a1940)', border: `2px solid ${numRounds === n ? '#fbdd68' : 'rgba(251, 221, 104, 0.15)'}` }}>
                    <span className="text-3xl font-bold" style={{ color: '#fbdd68' }}>{n}</span>
                    <span className="text-xs mt-1" style={{ color: '#8892b0' }}>Rounds</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 4: Select Rounds */}
          {step === 4 && (
            <div>
              <h3 className="text-white font-semibold mb-1">Select Your Rounds</h3>
              <p className="text-xs mb-5" style={{ color: '#8892b0' }}>Pick one round for each slot</p>
              <div className="space-y-4">
                {roundSlots.map((type, idx) => {
                  const conf = ROUND_TYPE_CONFIG[type];
                  const rounds = availableRounds[type] || [];
                  const selected = roundSelections[idx];
                  const label = idx === 5 ? `${conf.label} (Extra)` : conf.label;
                  return (
                    <div key={idx} className="rounded-xl p-4" style={{ background: 'rgba(20, 27, 80, 0.4)', border: `1px solid ${selected ? conf.color + '50' : 'rgba(251, 221, 104, 0.08)'}` }}>
                      <div className="flex items-center gap-2 mb-3">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: conf.color }} />
                        <span className="text-xs font-bold uppercase" style={{ color: conf.color }}>Round {idx + 1}: {label}</span>
                        {selected && <Check size={14} style={{ color: '#22c55e' }} />}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {rounds.map(r => (
                          <button key={r.name} onClick={() => handleRoundSelect(idx, r)} className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all" style={{ backgroundColor: selected?.name === r.name ? `${conf.color}25` : 'rgba(0, 14, 42, 0.6)', color: selected?.name === r.name ? conf.color : '#8892b0', border: `1px solid ${selected?.name === r.name ? conf.color + '60' : 'rgba(251, 221, 104, 0.08)'}` }}>
                            {r.name}{r.used ? ' (used)' : ''}
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
              {allRoundsSelected && (
                <button onClick={() => setStep(5)} className="mt-5 w-full py-3 rounded-lg font-bold text-sm transition-all" style={{ backgroundColor: '#fbdd68', color: '#000e2a' }} data-testid="wizard-review-button">
                  Review Build
                </button>
              )}
            </div>
          )}

          {/* Step 5: Review & Build */}
          {step === 5 && (
            <div>
              <h3 className="text-white font-semibold mb-1">Review & Build</h3>
              <p className="text-xs mb-5" style={{ color: '#8892b0' }}>Confirm your trivia show configuration</p>
              
              <div className="space-y-3 mb-6">
                <SummaryRow label="Location" value={selectedLocation} icon={MapPin} />
                <SummaryRow label="Host" value={selectedHost?.name} icon={User} />
                <SummaryRow label="Rounds" value={`${numRounds} rounds`} icon={HelpCircle} />
              </div>

              <div className="rounded-xl p-4 mb-6" style={{ background: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.15)' }}>
                <h4 className="text-xs font-bold uppercase mb-3" style={{ color: '#fbdd68' }}>Round Lineup</h4>
                <div className="space-y-2">
                  {roundSlots.map((type, idx) => {
                    const conf = ROUND_TYPE_CONFIG[type];
                    const sel = roundSelections[idx];
                    return (
                      <div key={idx} className="flex items-center gap-3 py-1.5">
                        <div className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold" style={{ backgroundColor: `${conf.color}20`, color: conf.color }}>{idx + 1}</div>
                        <span className="text-[10px] font-bold uppercase w-12" style={{ color: conf.color }}>{type}</span>
                        <span className="text-sm text-white flex-1">{sel?.name}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <button onClick={handleBuild} disabled={building} className="w-full py-3.5 rounded-lg font-bold text-sm transition-all hover:shadow-lg disabled:opacity-50 flex items-center justify-center gap-2" style={{ backgroundColor: '#fbdd68', color: '#000e2a', boxShadow: '0 0 20px rgba(251, 221, 104, 0.2)' }} data-testid="wizard-build-button">
                {building ? <><Loader2 size={16} className="animate-spin" /> Building...</> : <><Wand2 size={16} /> Build Presentation</>}
              </button>
            </div>
          )}

          {/* Navigation */}
          {step > 1 && step < 5 && (
            <div className="mt-6 flex justify-between">
              <button onClick={() => setStep(Math.max(1, step - 1))} className="flex items-center gap-1 px-4 py-2 rounded-lg text-sm transition-all" style={{ color: '#8892b0', border: '1px solid rgba(251, 221, 104, 0.15)' }}>
                <ChevronLeft size={16} /> Back
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryRow({ label, value, icon: Icon }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-lg" style={{ background: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.08)' }}>
      <Icon size={16} style={{ color: '#fbdd68' }} />
      <span className="text-xs" style={{ color: '#8892b0' }}>{label}:</span>
      <span className="text-sm font-medium text-white">{value}</span>
    </div>
  );
}
