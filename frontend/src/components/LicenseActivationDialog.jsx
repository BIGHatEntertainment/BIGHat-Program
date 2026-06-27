/**
 * LicenseActivationDialog — modal for entering / re-entering a license
 * key without having to go back through the full SetupWizard.
 *
 * Why this exists (v32.0.0-alpha.18):
 *   A customer who skipped setup, lost their key, or wiped their
 *   `system_config.json` ended up at the locked dashboard with no UI
 *   to enter their key. They'd see "Complete first-run setup to
 *   unlock" with no button. This dialog fixes that by exposing the
 *   same activate endpoint the wizard uses — `/api/native/license/
 *   cloud/activate` — through a one-screen form.
 *
 * Triggered from:
 *   • Dashboard AppCards → "Enter License Key" button on the locked
 *     Trivia card.
 *   • Header user dropdown → "Enter License Key" menu item (always
 *     available, even after activation, so support can re-key in place).
 */
import React, { useState } from 'react';
import axios from 'axios';
import { Loader2, KeyRound, CheckCircle2, AlertCircle } from 'lucide-react';
import { Button } from './ui/button';
import { toast } from 'sonner';
import { useNative } from '../context/NativeContext';

const API = process.env.REACT_APP_BACKEND_URL;

// Matches backend `is_well_formed_license` — five 4-char groups starting
// with BHE-, separated by dashes (e.g. BHE-XXXX-XXXX-XXXX-XXXX).
const KEY_RE = /^BHE-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/i;

export default function LicenseActivationDialog({ open, onClose }) {
  const { refresh, license } = useNative();
  const [key, setKey] = useState('');
  const [email, setEmail] = useState('');
  const [label, setLabel] = useState('This computer');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  if (!open) return null;

  const reset = () => {
    setKey(''); setEmail(''); setLabel('This computer');
    setError(null); setDone(false); setBusy(false);
  };

  const close = () => {
    reset();
    onClose && onClose();
  };

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    const trimmedKey = key.trim().toUpperCase();
    if (!KEY_RE.test(trimmedKey)) {
      setError('That doesn\'t look like a valid license key. They\'re shaped like BHE-XXXX-XXXX-XXXX-XXXX (from your purchase email).');
      return;
    }
    if (!email || !email.includes('@')) {
      setError('Enter the email you used at purchase.');
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/api/native/license/cloud/activate`, {
        license_key: trimmedKey,
        email: email.trim(),
        label: label.trim() || 'This computer',
      });
      setDone(true);
      // Pull the new entitlement state into the React tree so locked
      // cards on the dashboard unlock immediately, no app restart.
      await refresh();
      toast.success('License activated — features unlocked.');
      setTimeout(close, 1400);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      let msg = 'Activation failed. Double-check the key + email and try again.';
      if (typeof detail === 'string') msg = detail;
      else if (detail?.message) msg = detail.message;
      else if (detail?.error) msg = detail.error.replace(/_/g, ' ');
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  const alreadyActive = license?.is_active === true;

  return (
    <div
      data-testid="license-activation-dialog"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={close}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-2xl border bg-[#0a1428] text-white shadow-2xl"
        style={{ borderColor: 'rgba(251, 221, 104, 0.25)' }}
      >
        <div className="flex items-center gap-3 px-6 py-4 border-b" style={{ borderColor: 'rgba(251, 221, 104, 0.15)' }}>
          <div className="p-2 rounded-lg" style={{ backgroundColor: 'rgba(251, 221, 104, 0.12)' }}>
            <KeyRound className="w-5 h-5" style={{ color: '#fbdd68' }} />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-bold" style={{ color: '#fbdd68' }}>
              {alreadyActive ? 'Re-enter License Key' : 'Enter Your License Key'}
            </h2>
            <p className="text-xs" style={{ color: '#8892b0' }}>
              From your purchase email at <span className="font-mono">bighat.live</span>
            </p>
          </div>
        </div>

        {done ? (
          <div data-testid="license-activated" className="p-8 text-center">
            <CheckCircle2 className="w-14 h-14 mx-auto mb-3 text-green-400" />
            <div className="text-xl font-bold">Activated!</div>
            <div className="text-sm mt-1" style={{ color: '#8892b0' }}>Unlocking your features…</div>
          </div>
        ) : (
          <form onSubmit={submit} className="p-6 space-y-4">
            <div>
              <label className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: '#8892b0' }}>License key</label>
              <input
                data-testid="license-key-input"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="BHE-XXXX-XXXX-XXXX-XXXX"
                autoFocus
                spellCheck={false}
                autoCapitalize="characters"
                className="w-full px-3 py-2.5 rounded-lg font-mono text-sm bg-[#0f1d3a] border focus:outline-none focus:ring-2"
                style={{ borderColor: 'rgba(251, 221, 104, 0.2)' }}
              />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: '#8892b0' }}>Email used at purchase</label>
              <input
                data-testid="license-email-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full px-3 py-2.5 rounded-lg text-sm bg-[#0f1d3a] border focus:outline-none focus:ring-2"
                style={{ borderColor: 'rgba(251, 221, 104, 0.2)' }}
              />
            </div>
            <div>
              <label className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: '#8892b0' }}>Label for this computer</label>
              <input
                data-testid="license-label-input"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="Studio iMac, Living-room laptop, …"
                className="w-full px-3 py-2.5 rounded-lg text-sm bg-[#0f1d3a] border focus:outline-none focus:ring-2"
                style={{ borderColor: 'rgba(251, 221, 104, 0.2)' }}
              />
            </div>

            {error && (
              <div data-testid="license-error" className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-200">
                <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" /> <span>{error}</span>
              </div>
            )}

            <div className="flex items-center gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={close}
                disabled={busy}
                className="flex-1 text-white hover:bg-white/10"
                data-testid="license-cancel-btn"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={busy}
                className="flex-1 font-bold"
                style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}
                data-testid="license-submit-btn"
              >
                {busy ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Activating…</> : 'Activate'}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export { LicenseActivationDialog };
