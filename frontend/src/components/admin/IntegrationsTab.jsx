import React, { useCallback, useEffect, useRef, useState } from 'react';
import api from '../../lib/api';
import { saveBlob } from '../../lib/saveFile';
import { Package, UploadCloud, DownloadCloud, FileDown, FileUp, Loader2, CheckCircle2, AlertTriangle, Mail, HardDrive, Cloud } from 'lucide-react';

const card = { backgroundColor: 'rgba(20, 27, 80, 0.4)', border: '1px solid rgba(251, 221, 104, 0.12)' };
const gold = '#fbdd68';
const muted = '#8892b0';

function msg(err, fallback) {
  const d = err?.response?.data;
  return d?.message || (typeof d?.detail === 'string' ? d.detail : '') || fallback;
}

const LABELS = {
  venues_new: 'new venues', venues_changed: 'venues with different details', pricing_new: 'venues with new pricing', pricing_changed: 'venues with different pricing',
  people_new: 'new people', people_changed: 'people with different details', roles_new: 'new host assignments',
};

function PlanView({ plan }) {
  const rows = Object.keys(LABELS).filter((k) => plan[k]?.length);
  return (
    <div className="text-sm space-y-1" data-testid="pkg-plan">
      {rows.map((k) => (
        <p key={k} style={{ color: '#e5edff' }} data-testid={`pkg-plan-${k}`}>
          {plan[k].length} {LABELS[k]}: <span style={{ color: muted }}>{plan[k].slice(0, 4).join(', ')}{plan[k].length > 4 ? ` and ${plan[k].length - 4} more` : ''}</span>
        </p>
      ))}
      {plan.images_new > 0 && <p style={{ color: '#e5edff' }} data-testid="pkg-plan-images">{plan.images_new} new location pictures</p>}
      {!plan.differs && <p style={{ color: '#4ade80' }} data-testid="pkg-plan-same">This computer already matches. Nothing to change.</p>}
      {(plan.warnings || []).map((w) => <p key={w} className="text-xs" style={{ color: muted }}>{w}</p>)}
    </div>
  );
}

function Btn({ id, busy, onClick, icon: Icon, children, primary, disabled }) {
  return (
    <button onClick={onClick} disabled={!!busy || disabled} data-testid={`pkg-btn-${id}`}
            className="px-4 py-2 rounded-lg font-semibold flex items-center gap-2 text-sm"
            style={{ backgroundColor: primary ? gold : 'rgba(251,221,104,0.12)', color: primary ? '#000e2a' : gold, opacity: busy || disabled ? 0.5 : 1 }}>
      {busy === id ? <Loader2 size={16} className="animate-spin" /> : <Icon size={16} />} {children}
    </button>
  );
}

export default function IntegrationsTab({ isMaster, setError, setSuccess }) {
  const [check, setCheck] = useState(null);
  const [busy, setBusy] = useState('');
  const [preview, setPreview] = useState(null);       // { plan, source: 'cloud'|'file', file? }
  const [overwrite, setOverwrite] = useState(false);
  const [result, setResult] = useState(null);         // what the last pull added (temporary passwords shown once)
  const [xfer, setXfer] = useState({ open: false, email: '', code: '', sent: false });
  const working = useRef(false);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    try { setCheck((await api.pkgCheck()).data); } catch (e) { setCheck({ ok: false, message: msg(e, 'Could not check the setup.') }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = async (name, fn) => {
    if (working.current) return;
    working.current = true; setBusy(name); setError(''); setSuccess('');
    try { await fn(); } catch (e) { setError(msg(e, 'That did not work. Check the internet connection and try again.')); }
    finally { working.current = false; setBusy(''); }
  };

  const publish = () => run('publish', async () => {
    const r = (await api.pkgPublish()).data;
    if (!r.ok) { setError(r.message); return; }
    setSuccess(`Setup published (version ${r.version}). Your other computers can now pull it.`);
    load();
  });

  const startPull = () => run('pull', async () => {
    const r = (await api.pkgPull(false, false)).data;
    if (!r.ok) { setError(r.message); return; }
    setResult(null); setPreview({ plan: r.plan, source: 'cloud' });
  });

  const chooseFile = (e) => {
    const f = e.target.files?.[0]; e.target.value = '';
    if (!f) return;
    run('import', async () => {
      const r = (await api.pkgImport(f, false, false)).data;
      if (!r.ok) { setError(r.message); return; }
      setResult(null); setPreview({ plan: r.plan, source: 'file', file: f });
    });
  };

  const apply = () => run('apply', async () => {
    const r = (preview.source === 'cloud' ? (await api.pkgPull(true, overwrite)) : (await api.pkgImport(preview.file, true, overwrite))).data;
    if (!r.ok) { setError(r.message); return; }
    setResult(r.result); setPreview(null); setOverwrite(false);
    setSuccess('Setup applied.');
    load();
  });

  const exportFile = () => run('export', async () => {
    const res = await api.pkgExport();
    // saveBlob (not a hand-made download link) because the desktop window ignores <a download>; it saves into the PC's Downloads folder
    const saved = await saveBlob(res.data, `bighat-setup-${new Date().toISOString().slice(0, 10)}.bighatsetup`);
    if (!saved.ok) { setError(`The file could not be saved. ${saved.error || ''}`.trim()); return; }
    setSuccess(saved.path ? `Setup file saved: ${saved.path}` : 'Setup file saved to your Downloads folder.');
  });

  const sendCode = () => run('xfer-send', async () => {
    const r = (await api.pkgTransferStart(xfer.email.trim())).data;
    if (!r.ok) { setError(r.message); return; }
    setXfer((x) => ({ ...x, sent: true })); setSuccess(`A confirmation code was sent to ${r.sent_to}.`);
  });
  const confirmMove = () => run('xfer-confirm', async () => {
    const r = (await api.pkgTransferConfirm(xfer.code.trim())).data;
    if (!r.ok) { setError(r.message); return; }
    setXfer({ open: false, email: '', code: '', sent: false }); setSuccess(`Setup moved to ${r.moved_to}.`); load();
  });


  return (
    <div className="space-y-6" data-testid="integrations-tab">
      {/* ---- Setup Package (top) ---- */}
      <div className="rounded-xl p-5 space-y-4" style={card} data-testid="pkg-card">
        <h3 className="text-lg font-bold text-white flex items-center gap-2"><Package size={18} style={{ color: gold }} /> Setup Package</h3>
        <p className="text-sm" style={{ color: muted }}>
          Your venues, venue pricing, master admin, admins, hosts and location pictures, saved once under your master admin email. Your other computers pull it instead of re-typing everything. Passwords are never included.
        </p>

        {!check ? <p className="text-sm" style={{ color: muted }}>Checking...</p> : check.ok === false ? (
          <p className="text-sm flex items-center gap-2" style={{ color: '#fbdd68' }} data-testid="pkg-unreachable"><AlertTriangle size={16} /> {check.message} You can still use the file option below.</p>
        ) : !check.exists ? (
          <p className="text-sm" style={{ color: '#e5edff' }} data-testid="pkg-none">{isMaster ? 'No setup has been published yet. On the computer that is set up correctly, click Publish.' : 'No setup has been published yet. Ask the master admin to publish it.'}</p>
        ) : (
          <div className="text-sm space-y-1" data-testid="pkg-status">
            <p style={{ color: '#e5edff' }}>Latest setup: version {check.version}{check.published_at ? `, published ${new Date(check.published_at).toLocaleString()}` : ''}{check.published_by ? ` from ${check.published_by}` : ''}.</p>
            {check.counts && <p style={{ color: muted }}>{check.counts.venues} venues, {check.counts.people} people, {check.counts.locations} locations with pictures.</p>}
            {check.differs === false && <p className="flex items-center gap-2" style={{ color: '#4ade80' }} data-testid="pkg-matches"><CheckCircle2 size={16} /> This computer matches the latest setup.</p>}
            {check.differs === true && (
              <p className="flex items-start gap-2" style={{ color: gold }} data-testid="pkg-differs"><AlertTriangle size={16} className="mt-0.5 shrink-0" />
                {isMaster ? 'This computer does not match the latest setup. Click "Pull setup" to review and update it.' : 'This computer does not match the latest setup. Please call your master admin and ask them to update it.'}
              </p>
            )}
          </div>
        )}

        {isMaster && (
          <div className="flex flex-wrap gap-2">
            <Btn busy={busy} id="publish" onClick={publish} icon={UploadCloud} primary>Publish setup from this computer</Btn>
            <Btn busy={busy} id="pull" onClick={startPull} icon={DownloadCloud}>Pull setup</Btn>
            <Btn busy={busy} id="export" onClick={exportFile} icon={FileDown}>Save as a file</Btn>
            <Btn busy={busy} id="import" onClick={() => fileRef.current?.click()} icon={FileUp}>Load from a file</Btn>
            <input ref={fileRef} type="file" accept=".bighatsetup,.zip" className="hidden" onChange={chooseFile} data-testid="pkg-file-input" />
          </div>
        )}

        {preview && (
          <div className="rounded-lg p-4 space-y-3" style={{ backgroundColor: 'rgba(0,14,42,0.6)', border: `1px solid ${gold}55` }} data-testid="pkg-preview">
            <p className="font-semibold text-white">Here is what will change on this computer:</p>
            <PlanView plan={preview.plan} />
            {(preview.plan.venues_changed?.length > 0 || preview.plan.pricing_changed?.length > 0 || preview.plan.people_changed?.length > 0) && (
              <label className="flex items-center gap-2 text-sm" style={{ color: '#e5edff' }}>
                <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} data-testid="pkg-overwrite" />
                Replace the details that are different with the published ones
              </label>
            )}
            <div className="flex gap-2">
              <Btn busy={busy} id="apply" onClick={apply} icon={CheckCircle2} primary disabled={!preview.plan.differs}>Apply to this computer</Btn>
              <button onClick={() => setPreview(null)} disabled={!!busy} className="px-4 py-2 rounded-lg text-sm" style={{ color: muted }} data-testid="pkg-cancel">Cancel</button>
            </div>
          </div>
        )}

        {result && (
          <div className="rounded-lg p-4 space-y-2" style={{ backgroundColor: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.3)' }} data-testid="pkg-result">
            <p className="font-semibold text-white">Done. {result.venues_added} venues, {result.people_added.length} people, {result.roles_added} assignments, {result.images_added} pictures added.</p>
            {result.people_added.length > 0 && (
              <div data-testid="pkg-temp-passwords">
                <p className="text-sm" style={{ color: gold }}>Write these down now. They are shown only once. Each person should change their password after signing in.</p>
                <table className="text-sm mt-1" style={{ color: '#e5edff' }}><tbody>
                  {result.people_added.map((p) => <tr key={p.email}><td className="pr-4">{p.name} ({p.role})</td><td className="pr-4">{p.email}</td><td className="font-mono" data-testid={`pkg-temp-${p.email}`}>{p.temp_password}</td></tr>)}
                </tbody></table>
              </div>
            )}
            {result.skipped.length > 0 && <div className="text-xs" style={{ color: gold }} data-testid="pkg-skipped"><p>Some things were not added:</p>{result.skipped.map((s) => <p key={s}>- {s}</p>)}</div>}
          </div>
        )}

        {isMaster && (
          <div className="pt-2 border-t" style={{ borderColor: 'rgba(251,221,104,0.1)' }}>
            {!xfer.open ? (
              <button onClick={() => setXfer({ ...xfer, open: true })} className="text-sm underline" style={{ color: muted }} data-testid="pkg-transfer-open">Move this setup to a different email address</button>
            ) : (
              <div className="space-y-2" data-testid="pkg-transfer">
                <p className="text-sm" style={{ color: '#e5edff' }}>This moves your published setup to another email. We send a confirmation code to your current email first.</p>
                <div className="flex gap-2 flex-wrap">
                  <input value={xfer.email} onChange={(e) => setXfer({ ...xfer, email: e.target.value })} placeholder="new-email@example.com" className="px-3 py-2 rounded-lg text-white text-sm" style={{ backgroundColor: '#000e2a', border: '1px solid rgba(251,221,104,0.2)' }} data-testid="pkg-transfer-email" />
                  <Btn busy={busy} id="xfer-send" onClick={sendCode} icon={Mail} disabled={!xfer.email.includes('@')}>Send code</Btn>
                </div>
                {xfer.sent && (
                  <div className="flex gap-2 flex-wrap">
                    <input value={xfer.code} onChange={(e) => setXfer({ ...xfer, code: e.target.value })} placeholder="6-digit code" maxLength={6} className="px-3 py-2 rounded-lg text-white text-sm w-40" style={{ backgroundColor: '#000e2a', border: '1px solid rgba(251,221,104,0.2)' }} data-testid="pkg-transfer-code" />
                    <Btn busy={busy} id="xfer-confirm" onClick={confirmMove} icon={CheckCircle2} primary disabled={xfer.code.trim().length !== 6}>Move it</Btn>
                  </div>
                )}
                <button onClick={() => setXfer({ open: false, email: '', code: '', sent: false })} className="text-xs" style={{ color: muted }}>Cancel</button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ---- Other integrations (coming next) ---- */}
      {[['Google Drive', Cloud], ['SharePoint', HardDrive]].map(([name, Icon]) => (
        <div key={name} className="rounded-xl p-5 flex items-center justify-between" style={{ ...card, opacity: 0.7 }} data-testid={`integration-${name.replace(' ', '').toLowerCase()}`}>
          <div className="flex items-center gap-3"><Icon size={18} style={{ color: muted }} /><div><p className="text-white font-semibold">{name}</p><p className="text-xs" style={{ color: muted }}>Save your setup and files to {name}.</p></div></div>
          <span className="text-xs px-2 py-1 rounded" style={{ backgroundColor: 'rgba(251,221,104,0.12)', color: gold }}>Coming next</span>
        </div>
      ))}
    </div>
  );
}
