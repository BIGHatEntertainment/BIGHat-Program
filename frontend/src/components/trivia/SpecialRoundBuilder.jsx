import React, { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Loader2, ChevronLeft, ChevronRight, Lock } from 'lucide-react';
import axios from 'axios';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL || ''}/api`;
const TYPES = ['MC', 'REG', 'MISC', 'MYS', 'BIG'];
const MIDDLE_TYPES = ['MC', 'REG', 'MISC', 'MYS']; // BIG is always last
const TYPE_COLOR = { MC: '#22c55e', REG: '#ef4444', MISC: '#3b82f6', MYS: '#a855f7', BIG: '#eab308' };
const authOpts = () => {
  const t = localStorage.getItem('token');
  return { withCredentials: true, headers: t ? { Authorization: `Bearer ${t}` } : {} };
};

/** Default loadout for n rounds: MC first, BIG last, a sensible mix between. */
export function defaultLoadout(n) {
  const mid = ['REG', 'MISC', 'REG', 'MISC', 'MYS', 'REG', 'MISC', 'REG'];
  return ['MC', ...mid.slice(0, n - 2), 'BIG'];
}

/**
 * Admin / Master Admin only. Themed-night shows: 3..10 rounds, slot 1 = MC,
 * last = BIG, rounds come ONLY from Files/Trivia/Special.
 */
export default function SpecialRoundBuilder({ open, onOpenChange, onComplete, userName }) {
  const [step, setStep] = useState(1); // 1 loadout, 2 host+location+name, 3 pick rounds, 4 review
  const [count, setCount] = useState(5);
  const [types, setTypes] = useState(defaultLoadout(5));
  const [hosts, setHosts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [hostPath, setHostPath] = useState('');
  const [locPath, setLocPath] = useState('');
  const [name, setName] = useState('');
  const [pool, setPool] = useState([]);
  const [limits, setLimits] = useState({ min: 3, max: 10 });
  const [picks, setPicks] = useState([]); // file per slot
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStep(1); setCount(5); setTypes(defaultLoadout(5)); setPicks([]);
    setHostPath(''); setLocPath(''); setName('');
    (async () => {
      setLoading(true);
      try {
        const [h, l] = await Promise.all([
          axios.get(`${API}/trivia/hosts`, authOpts()),
          axios.get(`${API}/trivia/locations`, authOpts()),
        ]);
        setHosts(h.data || []); setLocations(l.data || []);
      } catch (e) {
        toast.error('Could not load hosts/locations');
      } finally { setLoading(false); }
    })();
  }, [open]);

  const setRoundCount = (n) => {
    setCount(n);
    setTypes((prev) => {
      const next = defaultLoadout(n);
      // keep the admin's earlier middle choices where they still fit
      for (let i = 1; i < n - 1; i += 1) if (prev[i] && prev[i] !== 'BIG') next[i] = prev[i];
      return next;
    });
    setPicks([]);
  };
  const setSlotType = (i, t) => { setTypes((p) => p.map((x, k) => (k === i ? t : x))); setPicks([]); };

  const host = hosts.find((h) => h.path === hostPath) || {};
  const loc = locations.find((l) => l.path === locPath) || {};

  const loadPool = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/native/special-rounds`, {
        ...authOpts(), params: { location: loc.name || loc.slug || '' },
      });
      setPool(r.data.rounds || []);
      setLimits({ min: r.data.min_rounds, max: r.data.max_rounds });
      return true;
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Could not load the Special folder');
      return false;
    } finally { setLoading(false); }
  };

  const next = async () => {
    if (step === 2) {
      if (!hostPath) return toast.error('Choose a host');
      if (!locPath) return toast.error('Choose a location');
      if (!(await loadPool())) return;
      setPicks(Array(count).fill(''));
    }
    if (step === 3) {
      if (picks.some((p) => !p)) return toast.error('Pick a round for every slot');
    }
    setStep(step + 1);
  };

  // A round can be used once per show; locked ones can't be chosen.
  const optionsFor = (i) => pool.filter((r) => !r.locked && (r.file === picks[i] || !picks.includes(r.file)));

  const build = async () => {
    setBuilding(true);
    try {
      const res = await axios.post(`${API}/native/presentations/build-special`, {
        name: name || `${host.name || 'Special'} — ${new Date().toISOString().slice(0, 10)}`,
        host_id: host.id || host.email || hostPath,
        location_id: loc.id || loc.slug || locPath,
        round_types: types,
        round_files: picks,
      }, authOpts());
      const doc = res.data;
      const roundNames = picks.map((f) => pool.find((r) => r.file === f)?.name || f);
      await onComplete({
        userName, host: hostPath, location: locPath,
        numRounds: types.length, rounds: picks, roundTypes: types, roundNames,
        presentationName: doc.name, hardcodedBuildDoc: doc, isSpecial: true,
        hostName: host.name || 'Unknown',
        locationFolder: loc.name || 'Unknown',
        locationName: (loc.name || 'Unknown').replace(/^\d+_/, ''),
        nativeManifest: { host: { id: host.id || null, name: host.name || null }, location: { id: loc.id || null, name: loc.name || null, slug: loc.slug || null } },
      });
      toast.success('Special show built');
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message || 'Build failed');
    } finally { setBuilding(false); }
  };

  const titles = { 1: 'Loadout: rounds & types', 2: 'Host, location & name', 3: 'Pick the special rounds', 4: 'Review & build' };

  const body = useMemo(() => {
    if (loading) {
      return <div className="text-center py-10"><Loader2 className="w-10 h-10 text-[#FFC107] mx-auto animate-spin" /></div>;
    }
    if (step === 1) {
      return (
        <div className="space-y-5" data-testid="special-step-loadout">
          <div>
            <Label className="text-gray-300">Number of rounds (3 to 10)</Label>
            <Select value={String(count)} onValueChange={(v) => setRoundCount(Number(v))}>
              <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2" data-testid="special-count">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#2a2a2a] border-gray-600">
                {Array.from({ length: 8 }, (_, k) => k + 3).map((n) => (
                  <SelectItem key={n} value={String(n)} className="text-white">{n} Rounds</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label className="text-gray-300">Round types (MC always first, BIG always last)</Label>
            {types.map((t, i) => {
              const fixed = i === 0 || i === types.length - 1;
              return (
                <div key={i} className="flex items-center gap-3" data-testid={`special-slot-${i + 1}`}>
                  <span className="w-16 text-sm text-gray-400">Round {i + 1}</span>
                  {fixed ? (
                    <span className="px-3 py-1.5 rounded-md text-sm font-semibold flex items-center gap-1"
                          style={{ background: `${TYPE_COLOR[t]}22`, color: TYPE_COLOR[t] }}>
                      <Lock size={12} /> {t}
                    </span>
                  ) : (
                    <Select value={t} onValueChange={(v) => setSlotType(i, v)}>
                      <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white w-40"><SelectValue /></SelectTrigger>
                      <SelectContent className="bg-[#2a2a2a] border-gray-600">
                        {MIDDLE_TYPES.map((m) => <SelectItem key={m} value={m} className="text-white">{m}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              );
            })}
          </div>
          <p className="text-xs text-gray-500">{types.join(' → ')}</p>
        </div>
      );
    }
    if (step === 2) {
      return (
        <div className="space-y-4" data-testid="special-step-host">
          <div>
            <Label className="text-gray-300">Host</Label>
            <Select value={hostPath} onValueChange={setHostPath}>
              <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2"><SelectValue placeholder="Choose a host..." /></SelectTrigger>
              <SelectContent className="bg-[#2a2a2a] border-gray-600">
                {hosts.filter((h) => h && h.path).map((h) => (
                  <SelectItem key={h.id || h.path} value={h.path} className="text-white">{h.name || 'Unnamed host'}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-gray-300">Location</Label>
            <Select value={locPath} onValueChange={(v) => {
              setLocPath(v);
              const l = locations.find((x) => x.path === v);
              if (l) setName(`${(l.name || '').replace(/^\d+_/, '')} - Special - ${new Date().toLocaleDateString()}`);
            }}>
              <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2"><SelectValue placeholder="Choose a location..." /></SelectTrigger>
              <SelectContent className="bg-[#2a2a2a] border-gray-600">
                {locations.filter((l) => l && l.path).map((l) => (
                  <SelectItem key={l.id || l.path} value={l.path} className="text-white">{(l.name || '').replace(/^\d+_/, '')}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-gray-300">Presentation name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="bg-[#2a2a2a] border-gray-600 text-white mt-2" />
          </div>
        </div>
      );
    }
    if (step === 3) {
      return (
        <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1" data-testid="special-step-pick">
          {pool.length === 0 && (
            <p className="text-sm text-yellow-400">
              The Special folder is empty. Open the Files tool, choose Trivia, then Special, and upload your themed-night rounds.
            </p>
          )}
          {types.map((t, i) => (
            <div key={i} className="flex items-center gap-3" data-testid={`special-pick-${i + 1}`}>
              <span className="w-24 text-sm font-semibold" style={{ color: TYPE_COLOR[t] }}>{i + 1}. {t}</span>
              <Select value={picks[i] || ''} onValueChange={(v) => setPicks((p) => p.map((x, k) => (k === i ? v : x)))}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white flex-1"><SelectValue placeholder="Choose a special round..." /></SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600">
                  {optionsFor(i).map((r) => (
                    <SelectItem key={r.file} value={r.file} className="text-white">
                      {r.name} ({r.question_count} Q)
                    </SelectItem>
                  ))}
                  {optionsFor(i).length === 0 && <div className="px-3 py-2 text-sm text-gray-400">No unlocked rounds left</div>}
                </SelectContent>
              </Select>
            </div>
          ))}
          {pool.some((r) => r.locked) && (
            <p className="text-xs text-gray-500 flex items-center gap-1"><Lock size={11} /> Rounds used at this location in the last 180 days are hidden. An admin can release them in Trivia Admin.</p>
          )}
        </div>
      );
    }
    return (
      <div className="space-y-2 text-sm" data-testid="special-step-review">
        <p><span className="text-gray-500">Host:</span> {host.name}</p>
        <p><span className="text-gray-500">Location:</span> {(loc.name || '').replace(/^\d+_/, '')}</p>
        <p><span className="text-gray-500">Name:</span> {name}</p>
        <ol className="mt-2 space-y-1">
          {types.map((t, i) => (
            <li key={i}><span className="font-semibold" style={{ color: TYPE_COLOR[t] }}>{i + 1}. {t}</span> — {pool.find((r) => r.file === picks[i])?.name || picks[i]}</li>
          ))}
        </ol>
        <p className="text-xs text-gray-500 pt-2">Scores for this show use the same round types and multipliers (MYS x2, BIG x3).</p>
      </div>
    );
  }, [loading, step, count, types, hosts, locations, hostPath, locPath, name, pool, picks]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-gradient-to-br from-[#1a1a2e] to-[#16213e] border-[#FFC107]/30 text-white max-w-2xl" data-testid="special-builder">
        <DialogHeader>
          <DialogTitle className="text-[#FFC107] text-2xl">Build Special Round Show</DialogTitle>
          <DialogDescription className="text-gray-400">Step {step} of 4: {titles[step]}</DialogDescription>
        </DialogHeader>
        <div className="py-4">{body}</div>
        <DialogFooter className="flex gap-3">
          {step > 1 && (
            <Button variant="outline" className="border-gray-600 text-gray-300" onClick={() => setStep(step - 1)} disabled={building}>
              <ChevronLeft className="w-4 h-4 mr-2" /> Back
            </Button>
          )}
          {step < 4 ? (
            <Button onClick={next} className="bg-[#1657E8] hover:bg-[#1F5EE9] text-white" data-testid="special-next">
              Next <ChevronRight className="w-4 h-4 ml-2" />
            </Button>
          ) : (
            <Button onClick={build} disabled={building} className="bg-[#FFC107] hover:bg-[#FFD54F] text-black font-semibold" data-testid="special-build">
              {building ? (<><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Building...</>) : 'Build Special Show'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
