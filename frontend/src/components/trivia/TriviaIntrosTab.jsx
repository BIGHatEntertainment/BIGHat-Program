/**
 * v32.0.0-alpha.53 — Trivia Intro Slides tab.
 *
 * Per merchant spec (2026-02-06, spec answer 2): "another tab in the trivia
 * admin. this way there is one set of global trivia intro material that all
 * the presentations will pull from on that account".
 *
 * Uses these backend endpoints (see native/router.py):
 *   GET    /api/native/intros              — list packs
 *   POST   /api/native/intros              — create pack {name, slides}
 *   GET    /api/native/intros/{id}         — read pack
 *   DELETE /api/native/intros/{id}         — delete pack
 *
 * Slide model matches the Editor's slide shape (background + elements[]).
 * The user selects one intro pack when building a presentation; the
 * assembly pipeline injects its slides AFTER the location section and
 * BEFORE round 1 (spec step 15).
 */
import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Plus, Trash2, RefreshCw } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function TriviaIntrosTab() {
  const [packs, setPacks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    setErr('');
    try {
      const r = await axios.get(`${API}/native/intros`);
      setPacks(r.data.packs || []);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      // Create an empty pack — the merchant can add slides via the
      // slide-editor in a follow-up UI. This shipping alpha keeps the
      // model minimal (pack + name); slides can be populated by
      // uploading a slide JSON in a later release.
      await axios.post(`${API}/native/intros`, {
        name: newName.trim(),
        slides: [],
      });
      setNewName('');
      await load();
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    } finally {
      setCreating(false);
    }
  };

  const remove = async (id, name) => {
    if (!window.confirm(`Delete intro pack "${name}"?`)) return;
    try {
      await axios.delete(`${API}/native/intros/${id}`);
      await load();
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div data-testid="trivia-intros-tab" className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">Trivia Intro Slides</h3>
        <p className="text-sm" style={{ color: '#8892b0' }}>
          Global welcome / rules / house-band pack injected after location slides
          and before round 1 in every presentation.
        </p>
      </div>

      {/* Create new pack */}
      <div className="glass-card rounded-xl p-4">
        <div className="flex gap-2">
          <input
            data-testid="new-intro-pack-name"
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Pack name (e.g. 'Regular Show Intros')"
            className="flex-1 px-3 py-2 rounded-lg text-sm bg-transparent text-white"
            style={{ border: '1px solid rgba(251, 221, 104, 0.2)' }}
            onKeyDown={(e) => { if (e.key === 'Enter') create(); }}
          />
          <button
            data-testid="new-intro-pack-create"
            onClick={create}
            disabled={creating || !newName.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
            style={{ backgroundColor: 'rgba(251, 221, 104, 0.15)', color: '#fbdd68',
                     border: '1px solid rgba(251, 221, 104, 0.3)' }}
          >
            <Plus size={14} /> {creating ? 'Creating…' : 'Create Pack'}
          </button>
        </div>
      </div>

      {/* Refresh + errors */}
      <div className="flex items-center justify-between">
        <button
          data-testid="intros-refresh"
          onClick={load}
          className="flex items-center gap-2 text-sm"
          style={{ color: '#8892b0' }}
        >
          <RefreshCw size={12} /> Refresh
        </button>
        {err && (
          <div data-testid="intros-error" className="text-xs px-3 py-1 rounded"
               style={{ color: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.08)' }}>
            {err}
          </div>
        )}
      </div>

      {/* List */}
      {loading ? (
        <div style={{ color: '#8892b0' }} className="text-sm">Loading intro packs…</div>
      ) : packs.length === 0 ? (
        <div data-testid="intros-empty" style={{ color: '#8892b0' }} className="text-sm">
          No intro packs yet. Create your first one above.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {packs.map((p) => (
            <div key={p.id} data-testid={`intro-pack-${p.id}`}
                 className="glass-card rounded-xl p-4 flex flex-col justify-between">
              <div>
                <div className="text-sm font-semibold text-white truncate mb-1">{p.name}</div>
                <div className="text-xs" style={{ color: '#8892b0' }}>
                  {p.num_slides} slide{p.num_slides === 1 ? '' : 's'}
                </div>
              </div>
              <div className="flex justify-end mt-3">
                <button
                  data-testid={`intro-pack-delete-${p.id}`}
                  onClick={() => remove(p.id, p.name)}
                  className="p-1.5 rounded-lg"
                  style={{ backgroundColor: 'rgba(239, 68, 68, 0.10)' }}
                >
                  <Trash2 size={14} style={{ color: '#ef4444' }} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="text-xs" style={{ color: '#8892b0' }}>
        Note: this shipping alpha creates empty packs (name only). Slide
        editing lands in a follow-up release — you can already delete /
        create packs and the presentation build wizard will list them
        for selection.
      </div>
    </div>
  );
}
