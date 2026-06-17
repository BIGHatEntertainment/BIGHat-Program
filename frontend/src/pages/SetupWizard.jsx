import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Hash,
  KeyRound,
  Loader2,
  Mail,
  MapPin,
  ShieldCheck,
  UserPlus,
  WifiOff,
  XCircle,
} from 'lucide-react';
import { useNative } from '../context/NativeContext';

const API = process.env.REACT_APP_BACKEND_URL;

const US_STATES = [
  'AK', 'AL', 'AR', 'AZ', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA', 'HI',
  'IA', 'ID', 'IL', 'IN', 'KS', 'KY', 'LA', 'MA', 'MD', 'ME', 'MI', 'MN',
  'MO', 'MS', 'MT', 'NC', 'ND', 'NE', 'NH', 'NJ', 'NM', 'NV', 'NY', 'OH',
  'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VA', 'VT', 'WA',
  'WI', 'WV', 'WY',
];

const LICENSE_RE = /^BHE(?:-[A-Z0-9]{4}){4}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function formatLicenseInput(v) {
  const cleaned = (v || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if (!cleaned) return '';
  let out = '';
  if (cleaned.startsWith('BHE')) {
    out = 'BHE';
    const rest = cleaned.slice(3);
    for (let i = 0; i < rest.length && i < 16; i += 4) {
      out += '-' + rest.slice(i, i + 4);
    }
  } else {
    out = 'BHE';
    for (let i = 0; i < cleaned.length && i < 16; i += 4) {
      out += '-' + cleaned.slice(i, i + 4);
    }
  }
  return out;
}

function Stepper({ step }) {
  const labels = ['License', 'Master Admin', 'Settings'];
  return (
    <div className="flex items-center justify-between mb-8">
      {labels.map((label, i) => {
        const idx = i + 1;
        const active = step === idx;
        const done = step > idx;
        return (
          <div key={label} className="flex-1 flex items-center">
            <div
              className={`flex items-center justify-center w-9 h-9 rounded-full text-sm font-semibold transition-all ${
                done
                  ? 'bg-[#fbdd68] text-[#000e2a]'
                  : active
                    ? 'bg-[#5973F7] text-white ring-4 ring-[#5973F7]/30'
                    : 'bg-white/10 text-white/50'
              }`}
            >
              {done ? <CheckCircle2 className="w-5 h-5" /> : idx}
            </div>
            <span
              className={`ml-3 text-sm font-medium ${
                active ? 'text-white' : done ? 'text-[#fbdd68]' : 'text-white/40'
              }`}
            >
              {label}
            </span>
            {i < labels.length - 1 && (
              <div
                className={`flex-1 h-px mx-3 ${
                  done ? 'bg-[#fbdd68]/60' : 'bg-white/10'
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function Field({ label, hint, error, children, icon: Icon }) {
  return (
    <div className="mb-4">
      <label className="block text-xs uppercase tracking-wider text-[#8892b0] mb-2">
        {label}
      </label>
      <div className="relative">
        {Icon && (
          <Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8892b0] pointer-events-none" />
        )}
        {children}
      </div>
      {hint && !error && (
        <p className="text-xs text-[#8892b0] mt-1.5">{hint}</p>
      )}
      {error && <p className="text-xs text-red-400 mt-1.5">{error}</p>}
    </div>
  );
}

function inputCls(hasIcon = false) {
  return `w-full ${hasIcon ? 'pl-10' : 'pl-3'} pr-3 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-white/30 focus:outline-none focus:border-[#fbdd68]/60 focus:ring-2 focus:ring-[#fbdd68]/20 transition-all text-sm`;
}

// --- Cloud verification status panel (Step 1) ---
function VerificationPanel({ verify }) {
  if (verify.state === 'idle') return null;

  if (verify.state === 'verifying') {
    return (
      <div
        data-testid="license-verify-status-verifying"
        className="mb-4 p-4 rounded-lg bg-[#5973F7]/10 border border-[#5973F7]/30 flex items-center gap-3"
      >
        <Loader2 className="w-5 h-5 text-[#5973F7] animate-spin shrink-0" />
        <div>
          <p className="text-sm text-white font-medium">Verifying with bighat.live…</p>
          <p className="text-xs text-[#8892b0]">Binding this machine to your license</p>
        </div>
      </div>
    );
  }

  if (verify.state === 'success') {
    return (
      <div
        data-testid="license-verify-status-success"
        className="mb-4 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30"
      >
        <div className="flex items-center gap-3 mb-3">
          <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
          <p className="text-sm text-white font-semibold">License activated</p>
        </div>
        <div className="space-y-1.5 text-xs pl-9">
          {verify.ownsStandalone && (
            <div className="flex items-center gap-2 text-emerald-300">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>BIG Hat Entertainment <span className="text-[#8892b0]">— lifetime</span></span>
            </div>
          )}
          <div className="flex items-center gap-2 text-[#8892b0] pt-1">
            <Hash className="w-3.5 h-3.5" />
            <span>This machine is seat {verify.activeSeats} of {verify.maxSeats}</span>
          </div>
        </div>
      </div>
    );
  }

  if (verify.state === 'error') {
    return (
      <div
        data-testid="license-verify-status-error"
        className="mb-4 p-4 rounded-lg bg-red-500/10 border border-red-500/30"
      >
        <div className="flex items-center gap-3 mb-2">
          <XCircle className="w-5 h-5 text-red-400 shrink-0" />
          <p className="text-sm text-white font-semibold">Couldn't verify license</p>
        </div>
        <p className="text-xs text-red-200/90 pl-8">{verify.error}</p>
      </div>
    );
  }

  if (verify.state === 'offline') {
    return (
      <div
        data-testid="license-verify-status-offline"
        className="mb-4 p-4 rounded-lg bg-amber-500/10 border border-amber-500/30"
      >
        <div className="flex items-center gap-3 mb-2">
          <WifiOff className="w-5 h-5 text-amber-400 shrink-0" />
          <p className="text-sm text-white font-semibold">Cloud unreachable</p>
        </div>
        <p className="text-xs text-amber-100/90 pl-8">
          We can't reach bighat.live right now. You can finish setup and we'll
          activate this machine automatically the next time you're online.
        </p>
      </div>
    );
  }

  return null;
}

export default function SetupWizard() {
  const navigate = useNavigate();
  const { refresh, currentHwid } = useNative();

  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');
  const [showPass, setShowPass] = useState(false);
  const [success, setSuccess] = useState(null);

  // Step 1: License + cloud verification
  const [licenseKey, setLicenseKey] = useState('');
  const [purchaseEmail, setPurchaseEmail] = useState('');
  const [verify, setVerify] = useState({ state: 'idle' });

  // Step 2: Master Admin
  const [admin, setAdmin] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    first_name: '',
    last_name: '',
    display_name: '',
    phone: '',
  });

  // Step 3: Settings
  const [settings, setSettings] = useState({
    company_name: 'BIG Hat Entertainment',
    location_name: '',
    city: '',
    state: 'AZ',
    trivia_source: 'local',
  });

  const errors = useMemo(() => {
    const e = {};
    if (step === 1) {
      if (!licenseKey) e.licenseKey = 'License key is required.';
      else if (!LICENSE_RE.test(licenseKey))
        e.licenseKey =
          'Format: BHE-XXXX-XXXX-XXXX-XXXX (4 groups of 4 letters/digits).';
      if (purchaseEmail && !EMAIL_RE.test(purchaseEmail))
        e.purchaseEmail = 'Enter the email you used at checkout, or leave blank.';
    }
    if (step === 2) {
      if (!admin.first_name.trim()) e.first_name = 'First name is required.';
      if (!EMAIL_RE.test(admin.email))
        e.email = 'Enter a valid email (offline-only emails are OK).';
      if (admin.password.length < 6)
        e.password = 'Password must be at least 6 characters.';
      if (admin.password !== admin.confirmPassword)
        e.confirmPassword = 'Passwords do not match.';
    }
    if (step === 3) {
      if (!settings.location_name.trim())
        e.location_name = 'Location name is required.';
    }
    return e;
  }, [step, licenseKey, purchaseEmail, admin, settings]);

  const formCanProceed = Object.keys(errors).length === 0;

  // Step 1 needs cloud verification (or explicit offline opt-in) to advance.
  const step1CanProceed =
    formCanProceed && (verify.state === 'success' || verify.state === 'offline');
  const canProceed = step === 1 ? step1CanProceed : formCanProceed;

  // --- Cloud verification ---
  const handleVerifyLicense = async () => {
    if (!formCanProceed) return;
    setServerError('');
    setVerify({ state: 'verifying' });
    try {
      const { data } = await axios.post(
        `${API}/api/native/license/cloud/activate`,
        {
          license_key: licenseKey,
          email: purchaseEmail || null,
          label: 'Setup Wizard',
        },
      );
      const cloud = data?.cloud || {};
      setVerify({
        state: 'success',
        ownsStandalone: Boolean(cloud.owns_standalone),
        activeSeats: cloud.active_seats ?? 1,
        maxSeats: cloud.max_seats ?? 5,
      });
    } catch (e) {
      const status = e.response?.status;
      const detail = e.response?.data?.detail;
      // 503 from our backend means transport failure to api.bighat.live.
      if (status === 503) {
        setVerify({ state: 'offline' });
        return;
      }
      let msg = 'Verification failed. Double-check the key and try again.';
      if (typeof detail === 'string') msg = detail;
      else if (detail?.error) {
        msg = detail.message || detail.error;
        if (detail.error === 'unknown_key') msg = "We don't recognise that license key.";
        else if (String(detail.error).startsWith('seat_limit'))
          msg = 'All seats on this license are in use. Deactivate one from another machine first.';
        else if (detail.error === 'revoked')
          msg = 'This license has been revoked. Please contact support@bighat.live.';
      }
      setVerify({ state: 'error', error: msg });
    }
  };

  const handleContinueOffline = () => {
    if (!formCanProceed) return;
    setVerify({ state: 'offline' });
  };

  const handleNext = () => {
    if (!canProceed) return;
    setServerError('');
    setStep((s) => Math.min(3, s + 1));
  };

  const handleBack = () => {
    setServerError('');
    setStep((s) => Math.max(1, s - 1));
  };

  const handleSubmit = async () => {
    if (!canProceed) return;
    setSubmitting(true);
    setServerError('');
    try {
      const payload = {
        license_key: licenseKey,
        master_admin: {
          email: admin.email.toLowerCase().trim(),
          password: admin.password,
          first_name: admin.first_name.trim(),
          last_name: admin.last_name.trim(),
          display_name:
            admin.display_name.trim() ||
            `${admin.first_name} ${admin.last_name}`.trim(),
          phone: admin.phone.trim() || null,
        },
        settings,
      };
      const { data } = await axios.post(
        `${API}/api/native/setup/initialize`,
        payload,
      );
      // Carry the cloud verification result forward so the Success screen
      // can show the tier badges (verified state survives the local init).
      setSuccess({ ...data, verify });
    } catch (e) {
      const detail = e.response?.data?.detail;
      let msg = 'Setup failed. Check the form and try again.';
      if (typeof detail === 'string') msg = detail;
      else if (Array.isArray(detail) && detail[0]?.msg) msg = detail[0].msg;
      else if (detail?.message) msg = detail.message;
      setServerError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // ===== Success screen =====
  if (success) {
    const v = success.verify || {};
    return (
      <div
        className="min-h-screen flex items-center justify-center relative overflow-hidden"
        style={{ backgroundColor: '#000e2a' }}
        data-testid="setup-wizard-success"
      >
        <div
          className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full opacity-20 animate-pulse-glow"
          style={{ background: 'radial-gradient(circle, #fbdd68 0%, transparent 70%)' }}
        />
        <div className="relative z-10 w-full max-w-lg mx-4">
          <div className="glass-card rounded-2xl p-8 text-center">
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-[#fbdd68]/10 flex items-center justify-center">
              <ShieldCheck className="w-12 h-12 text-[#fbdd68]" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2 font-['Lemonada']">
              All Set Up!
            </h2>
            <p className="text-sm text-[#8892b0] mb-6">
              Master admin{' '}
              <span className="text-[#fbdd68] font-mono">{success.master_admin_email}</span>{' '}
              created. This computer is registered as seat 1 of 5.
            </p>

            {/* Tier badges (only if cloud verification succeeded) */}
            {v.state === 'success' && (
              <div className="text-left bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-4 mb-4 space-y-2">
                {v.ownsStandalone && (
                  <div className="flex items-center gap-2 text-sm text-emerald-300">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>BIG Hat Entertainment — lifetime</span>
                  </div>
                )}
              </div>
            )}

            {v.state === 'offline' && (
              <div className="text-left bg-amber-500/5 border border-amber-500/20 rounded-lg p-4 mb-4">
                <div className="flex items-center gap-2 text-sm text-amber-200">
                  <WifiOff className="w-4 h-4 shrink-0" />
                  <span>Activated locally. We'll verify online next time you're connected.</span>
                </div>
              </div>
            )}

            <div className="text-left bg-black/30 rounded-lg p-4 mb-6 font-mono text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-[#8892b0]">License:</span>
                <span className="text-white">{success.license?.key_masked || 'set'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#8892b0]">Seats used:</span>
                <span className="text-white">
                  {success.license?.used_seats}/{success.license?.total_seats_allowed}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#8892b0]">HWID:</span>
                <span className="text-white truncate ml-2 max-w-[260px]">
                  {success.hwid?.slice(0, 16)}…
                </span>
              </div>
            </div>
            <button
              data-testid="continue-to-login-btn"
              onClick={async () => {
                await refresh();
                navigate('/login', { replace: true });
              }}
              className="w-full py-3 rounded-lg bg-[#fbdd68] text-[#000e2a] font-semibold hover:bg-[#fbdd68]/90 transition-colors"
            >
              Continue to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ===== Wizard =====
  return (
    <div
      className="min-h-screen flex items-center justify-center relative overflow-hidden py-8"
      style={{ backgroundColor: '#000e2a' }}
    >
      <div
        className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full opacity-20 animate-pulse-glow"
        style={{ background: 'radial-gradient(circle, #fbdd68 0%, transparent 70%)' }}
      />
      <div
        className="absolute bottom-1/4 right-1/4 w-80 h-80 rounded-full opacity-15 animate-pulse-glow"
        style={{
          background: 'radial-gradient(circle, #5973F7 0%, transparent 70%)',
          animationDelay: '2s',
        }}
      />

      <div
        className="relative z-10 w-full max-w-xl mx-4 animate-slide-up"
        data-testid="setup-wizard"
      >
        <div className="text-center mb-6">
          <img
            src="/hat-logo.png"
            alt="BIG Hat"
            className="w-20 h-20 mx-auto mb-3 object-contain"
          />
          <h1 className="text-3xl font-bold font-['Lemonada']" style={{ color: '#fbdd68' }}>
            BIG Hat Entertainment — Setup
          </h1>
          <p className="mt-1 text-sm text-[#8892b0]">
            One-time first-run configuration. Takes &lt; 60 seconds.
          </p>
        </div>

        <div className="glass-card rounded-2xl p-7">
          <Stepper step={step} />

          {/* Step 1: License */}
          {step === 1 && (
            <div data-testid="step-license">
              <h2 className="text-lg font-semibold text-white mb-1">
                Activate your license
              </h2>
              <p className="text-xs text-[#8892b0] mb-5">
                Enter the key we emailed after your purchase. We'll bind this
                machine as seat 1 of 5 and unlock everything you've paid for.
              </p>
              <Field
                label="License Key"
                icon={KeyRound}
                error={errors.licenseKey}
                hint="BHE-XXXX-XXXX-XXXX-XXXX (auto-formatted as you type)"
              >
                <input
                  type="text"
                  className={inputCls(true) + ' font-mono tracking-wider'}
                  value={licenseKey}
                  onChange={(e) => {
                    setLicenseKey(formatLicenseInput(e.target.value));
                    setVerify({ state: 'idle' }); // re-verify if key changes
                  }}
                  placeholder="BHE-XXXX-XXXX-XXXX-XXXX"
                  maxLength={23}
                  spellCheck={false}
                  data-testid="license-input"
                />
              </Field>
              <Field
                label="Email used at checkout (optional)"
                icon={Mail}
                error={errors.purchaseEmail}
                hint="Helps us match this license to your Squarespace order."
              >
                <input
                  type="email"
                  className={inputCls(true)}
                  value={purchaseEmail}
                  onChange={(e) => {
                    setPurchaseEmail(e.target.value);
                    setVerify({ state: 'idle' });
                  }}
                  placeholder="you@example.com"
                  autoComplete="email"
                  spellCheck={false}
                  data-testid="purchase-email-input"
                />
              </Field>
              <Field label="This Machine ID (auto-detected)" icon={Hash}>
                <input
                  type="text"
                  readOnly
                  className={inputCls(true) + ' font-mono text-xs text-[#8892b0]'}
                  value={currentHwid || 'detecting…'}
                  data-testid="hwid-display"
                />
              </Field>

              <VerificationPanel verify={verify} />

              {/* Verify / offline-fallback action row */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 mt-2">
                <button
                  type="button"
                  onClick={handleVerifyLicense}
                  disabled={
                    !!errors.licenseKey ||
                    !!errors.purchaseEmail ||
                    !licenseKey ||
                    verify.state === 'verifying'
                  }
                  data-testid="verify-license-btn"
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-[#5973F7]/15 border border-[#5973F7]/40 text-[#5973F7] text-sm font-semibold hover:bg-[#5973F7]/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {verify.state === 'verifying' ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" /> Verifying…
                    </>
                  ) : verify.state === 'success' ? (
                    <>
                      <CheckCircle2 className="w-4 h-4" /> Re-verify online
                    </>
                  ) : (
                    <>
                      <Cloud className="w-4 h-4" /> Verify online
                    </>
                  )}
                </button>
                {verify.state !== 'success' && verify.state !== 'verifying' && (
                  <button
                    type="button"
                    onClick={handleContinueOffline}
                    disabled={!!errors.licenseKey || !licenseKey}
                    data-testid="continue-offline-btn"
                    className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm text-white/60 hover:text-white hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                    title="Activate later — when this computer is online"
                  >
                    <WifiOff className="w-4 h-4" /> Continue offline
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Step 2: Master Admin */}
          {step === 2 && (
            <div data-testid="step-admin">
              <h2 className="text-lg font-semibold text-white mb-1">
                Create the Master Admin
              </h2>
              <p className="text-xs text-[#8892b0] mb-5">
                The Master Admin is the only role that can create other Admins,
                manage seats and licensing. You can change all of this later.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <Field label="First Name" error={errors.first_name}>
                  <input
                    type="text"
                    className={inputCls()}
                    value={admin.first_name}
                    onChange={(e) => setAdmin({ ...admin, first_name: e.target.value })}
                    placeholder="Jordan"
                    data-testid="admin-first-name-input"
                  />
                </Field>
                <Field label="Last Name">
                  <input
                    type="text"
                    className={inputCls()}
                    value={admin.last_name}
                    onChange={(e) => setAdmin({ ...admin, last_name: e.target.value })}
                    placeholder="Sellards"
                    data-testid="admin-last-name-input"
                  />
                </Field>
              </div>
              <Field label="Email" error={errors.email}>
                <input
                  type="email"
                  className={inputCls()}
                  value={admin.email}
                  onChange={(e) => setAdmin({ ...admin, email: e.target.value })}
                  placeholder="master@bighat.local"
                  autoComplete="username"
                  data-testid="admin-email-input"
                />
              </Field>
              <Field
                label="Password"
                error={errors.password}
                hint="At least 6 characters. Stored locally with bcrypt."
              >
                <input
                  type={showPass ? 'text' : 'password'}
                  className={inputCls()}
                  value={admin.password}
                  onChange={(e) => setAdmin({ ...admin, password: e.target.value })}
                  autoComplete="new-password"
                  data-testid="admin-password-input"
                />
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#8892b0] hover:text-white"
                  data-testid="toggle-password-visibility"
                >
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </Field>
              <Field label="Confirm Password" error={errors.confirmPassword}>
                <input
                  type={showPass ? 'text' : 'password'}
                  className={inputCls()}
                  value={admin.confirmPassword}
                  onChange={(e) =>
                    setAdmin({ ...admin, confirmPassword: e.target.value })
                  }
                  autoComplete="new-password"
                  data-testid="admin-confirm-password-input"
                />
              </Field>
              <Field label="Phone (optional)">
                <input
                  type="tel"
                  className={inputCls()}
                  value={admin.phone}
                  onChange={(e) => setAdmin({ ...admin, phone: e.target.value })}
                  placeholder="555-1234"
                  data-testid="admin-phone-input"
                />
              </Field>
            </div>
          )}

          {/* Step 3: Settings */}
          {step === 3 && (
            <div data-testid="step-settings">
              <h2 className="text-lg font-semibold text-white mb-1">
                Tell us about this location
              </h2>
              <p className="text-xs text-[#8892b0] mb-5">
                These details will appear on schedules, reports, and event listings.
              </p>
              <Field label="Company Name">
                <input
                  type="text"
                  className={inputCls()}
                  value={settings.company_name}
                  onChange={(e) =>
                    setSettings({ ...settings, company_name: e.target.value })
                  }
                  data-testid="company-name-input"
                />
              </Field>
              <Field
                label="Location / Branch Name"
                icon={MapPin}
                error={errors.location_name}
                hint="e.g., 'Phoenix Headquarters' or 'Tempe Office'"
              >
                <input
                  type="text"
                  className={inputCls(true)}
                  value={settings.location_name}
                  onChange={(e) =>
                    setSettings({ ...settings, location_name: e.target.value })
                  }
                  placeholder="Phoenix Headquarters"
                  data-testid="location-name-input"
                />
              </Field>
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <Field label="City">
                    <input
                      type="text"
                      className={inputCls()}
                      value={settings.city}
                      onChange={(e) => setSettings({ ...settings, city: e.target.value })}
                      placeholder="Phoenix"
                      data-testid="city-input"
                    />
                  </Field>
                </div>
                <Field label="State">
                  <select
                    className={inputCls()}
                    value={settings.state}
                    onChange={(e) =>
                      setSettings({ ...settings, state: e.target.value })
                    }
                    data-testid="state-select"
                  >
                    {US_STATES.map((s) => (
                      <option key={s} value={s} className="bg-[#000e2a]">
                        {s}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <Field
                label="Trivia Content Source"
                hint="All trivia content is local — bundled rounds plus any .bighat packs you import."
              >
                <select
                  className={inputCls()}
                  value="local"
                  disabled
                  data-testid="trivia-source-select"
                >
                  <option value="local" className="bg-[#000e2a]">
                    Local (offline)
                  </option>
                </select>
              </Field>
            </div>
          )}

          {serverError && (
            <div
              className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300"
              data-testid="setup-server-error"
            >
              {serverError}
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-between mt-7">
            {step > 1 ? (
              <button
                onClick={handleBack}
                disabled={submitting}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm text-white/70 hover:text-white hover:bg-white/5 transition-colors"
                data-testid="wizard-back"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
            ) : (
              <span />
            )}
            {step < 3 ? (
              <button
                onClick={handleNext}
                disabled={!canProceed}
                data-testid="wizard-next"
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#5973F7] text-white text-sm font-semibold hover:bg-[#5973F7]/90 disabled:bg-white/10 disabled:text-white/40 disabled:cursor-not-allowed transition-colors"
              >
                Next <ArrowRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={!canProceed || submitting}
                data-testid="wizard-submit"
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[#fbdd68] text-[#000e2a] text-sm font-semibold hover:bg-[#fbdd68]/90 disabled:bg-white/20 disabled:text-white/40 disabled:cursor-not-allowed transition-colors"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" /> Initializing…
                  </>
                ) : (
                  <>
                    <UserPlus className="w-4 h-4" /> Complete Setup
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        <p className="text-center text-xs text-[#8892b0] mt-4">
          BIG Hat Entertainment v31 • Native edition • Local-First
        </p>
      </div>
    </div>
  );
}
