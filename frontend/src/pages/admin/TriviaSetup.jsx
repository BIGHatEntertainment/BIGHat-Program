/**
 * Trivia Setup tab for Admin Settings (v32.0.0-alpha.22).
 *
 * Lets master_admin + admins manage per-location branding assets that
 * play right after each round's host slide during a trivia presentation.
 * Round count is decided per-event at build time — it's NOT on the
 * location. Between-round sponsor rotations are subscription-gated and
 * tracked separately in the roadmap.
 *
 *   • master_admin: full CRUD over every location + admin assignments
 *   • admin:        edit only locations they're assigned to
 *
 * The component is intentionally one file so it's easy to grep/replace
 * during the inevitable scope expansions ("can we add per-round
 * overlays here?"). When it crosses ~500 lines, split per tab.
 */
import React, { useEffect, useMemo, useState } from 'react';
import api from '../../lib/api';
import {
  MapPin, Plus, Trash2, ImagePlus, Image as ImageIcon,
  UserPlus, GripVertical, X, Save, Loader2, AlertTriangle, Check,
} from 'lucide-react';

const PALETTE = {
  bg: '#000e2a',
  panel: '#141b50',
  panelMuted: 'rgba(20, 27, 80, 0.4)',
  border: 'rgba(251, 221, 104, 0.15)',
  borderHi: 'rgba(251, 221, 104, 0.3)',
  text: '#ffffff',
  textDim: '#8892b0',
  accent: '#fbdd68',
  danger: '#ef4444',
  success: '#22c55e',
};

const isMaster = (u) => u?.role === 'master_admin';

// ---------------------------------------------------------------
// Root: list + selected-editor pane
// ---------------------------------------------------------------
export default function TriviaSetup({ currentUser, allUsers = [], setError, setSuccess }) {
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [showCreate, setShowCreate] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await api.listLocations();
      setLocations(r.data);
      // If the currently-selected one disappeared (delete from another tab),
      // drop the selection so we don't 404 in the editor.
      if (selectedId && !r.data.find((l) => l.id === selectedId)) {
        setSelectedId(null);
      }
    } catch (e) {
      setError?.(e.response?.data?.detail || 'Failed to load locations');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const selected = useMemo(
    () => locations.find((l) => l.id === selectedId) || null,
    [locations, selectedId],
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-[320px_1fr] gap-6" data-testid="trivia-setup">
      {/* ---------- Left: location list ---------- */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide" style={{ color: PALETTE.textDim }}>
            Locations
          </h3>
          {isMaster(currentUser) && (
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition"
              style={{ backgroundColor: PALETTE.panelMuted, color: PALETTE.accent, border: `1px solid ${PALETTE.borderHi}` }}
              data-testid="new-location-btn"
            >
              <Plus size={12} /> New
            </button>
          )}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: PALETTE.textDim }}>
            <Loader2 size={14} className="animate-spin" /> Loading…
          </div>
        ) : locations.length === 0 ? (
          <EmptyLocationsPanel canCreate={isMaster(currentUser)} onCreate={() => setShowCreate(true)} />
        ) : (
          <ul className="space-y-2" data-testid="location-list">
            {locations.map((loc) => (
              <li key={loc.id}>
                <button
                  onClick={() => setSelectedId(loc.id)}
                  className="w-full text-left px-3 py-2.5 rounded-lg transition"
                  style={{
                    backgroundColor: selectedId === loc.id ? 'rgba(251, 221, 104, 0.12)' : PALETTE.panelMuted,
                    border: `1px solid ${selectedId === loc.id ? PALETTE.borderHi : PALETTE.border}`,
                  }}
                  data-testid={`location-card-${loc.slug}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <MapPin size={14} style={{ color: PALETTE.accent }} />
                    <span className="font-semibold text-sm text-white truncate">{loc.name}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs" style={{ color: PALETTE.textDim }}>
                    <span className="flex items-center gap-1">
                      <ImageIcon size={11} /> {loc.branding_images?.length || 0}
                    </span>
                    {isMaster(currentUser) && (
                      <span className="flex items-center gap-1">
                        <UserPlus size={11} /> {loc.assigned_user_ids?.length || 0}
                      </span>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ---------- Right: selected location editor ---------- */}
      <div>
        {selected ? (
          <LocationEditor
            key={selected.id}
            location={selected}
            currentUser={currentUser}
            allUsers={allUsers}
            onChange={refresh}
            onClose={() => setSelectedId(null)}
            onDeleted={() => { setSelectedId(null); refresh(); }}
            setError={setError}
            setSuccess={setSuccess}
          />
        ) : (
          <div className="h-full flex items-center justify-center rounded-xl p-12 text-center"
               style={{ backgroundColor: PALETTE.panelMuted, border: `1px dashed ${PALETTE.border}` }}>
            <div>
              <MapPin size={32} style={{ color: PALETTE.accent }} className="mx-auto mb-3 opacity-50" />
              <p className="text-sm" style={{ color: PALETTE.textDim }}>
                {locations.length === 0
                  ? 'No locations yet. Create your first one to get started.'
                  : 'Pick a location on the left to manage its branding.'}
              </p>
            </div>
          </div>
        )}
      </div>

      {showCreate && (
        <CreateLocationDialog
          onClose={() => setShowCreate(false)}
          onCreated={(loc) => {
            setShowCreate(false);
            setSelectedId(loc.id);
            refresh();
          }}
          setError={setError}
          setSuccess={setSuccess}
        />
      )}
    </div>
  );
}


// ---------------------------------------------------------------
// Empty / create dialog
// ---------------------------------------------------------------
function EmptyLocationsPanel({ canCreate, onCreate }) {
  return (
    <div className="rounded-xl p-6 text-center"
         style={{ backgroundColor: PALETTE.panelMuted, border: `1px dashed ${PALETTE.border}` }}>
      <p className="text-sm mb-3" style={{ color: PALETTE.textDim }}>
        No locations yet.
      </p>
      {canCreate && (
        <button
          onClick={onCreate}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium"
          style={{ backgroundColor: PALETTE.accent, color: PALETTE.bg }}
          data-testid="empty-state-create-btn"
        >
          <Plus size={12} /> Create your first location
        </button>
      )}
    </div>
  );
}


function CreateLocationDialog({ onClose, onCreated, setError, setSuccess }) {
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e?.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const r = await api.createLocation({ name: name.trim() });
      setSuccess?.(`Created location "${r.data.name}"`);
      onCreated(r.data);
    } catch (err) {
      setError?.(err.response?.data?.detail || 'Failed to create location');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
         style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
         onClick={onClose}
         data-testid="create-location-modal">
      <form onSubmit={submit}
            onClick={(e) => e.stopPropagation()}
            className="rounded-xl p-6 w-full max-w-md"
            style={{ backgroundColor: PALETTE.panel, border: `1px solid ${PALETTE.borderHi}` }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white">New Location</h3>
          <button type="button" onClick={onClose} style={{ color: PALETTE.textDim }}>
            <X size={18} />
          </button>
        </div>
        <label className="block text-xs uppercase tracking-wide mb-1.5" style={{ color: PALETTE.textDim }}>
          Display name
        </label>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Chicago Downtown"
          className="w-full px-3 py-2 rounded-md text-sm text-white mb-4"
          style={{ backgroundColor: PALETTE.bg, border: `1px solid ${PALETTE.border}` }}
          data-testid="new-location-name-input"
          maxLength={80}
        />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 rounded-md text-sm"
                  style={{ color: PALETTE.textDim }}>
            Cancel
          </button>
          <button type="submit"
                  disabled={!name.trim() || submitting}
                  className="px-3 py-1.5 rounded-md text-sm font-medium disabled:opacity-50"
                  style={{ backgroundColor: PALETTE.accent, color: PALETTE.bg }}
                  data-testid="create-location-submit">
            {submitting ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  );
}


// ---------------------------------------------------------------
// Editor: rename + image gallery + (master) assignments
// ---------------------------------------------------------------
function LocationEditor({ location, currentUser, allUsers, onChange, onClose, onDeleted, setError, setSuccess }) {
  const [name, setName] = useState(location.name);
  const [savingName, setSavingName] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const master = isMaster(currentUser);

  const saveName = async () => {
    if (!name.trim() || name.trim() === location.name) return;
    setSavingName(true);
    try {
      await api.updateLocation(location.id, { name: name.trim() });
      setSuccess?.('Location renamed');
      onChange();
    } catch (e) {
      setError?.(e.response?.data?.detail || 'Failed to rename');
    } finally {
      setSavingName(false);
    }
  };

  const handleFiles = async (files) => {
    if (!files || !files.length) return;
    setUploading(true);
    try {
      for (const f of files) {
        await api.uploadLocationImage(location.id, f);
      }
      setSuccess?.(`Uploaded ${files.length} image${files.length === 1 ? '' : 's'}`);
      onChange();
    } catch (e) {
      setError?.(e.response?.data?.detail || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="rounded-xl p-5 space-y-5"
         style={{ backgroundColor: PALETTE.panelMuted, border: `1px solid ${PALETTE.border}` }}
         data-testid="location-editor">
      {/* Header: name editor + delete (master) */}
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <label className="block text-xs uppercase tracking-wide mb-1.5" style={{ color: PALETTE.textDim }}>
            Display name
          </label>
          <div className="flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="flex-1 px-3 py-2 rounded-md text-sm text-white"
              style={{ backgroundColor: PALETTE.bg, border: `1px solid ${PALETTE.border}` }}
              data-testid="location-name-input"
              maxLength={80}
            />
            <button
              onClick={saveName}
              disabled={savingName || !name.trim() || name.trim() === location.name}
              className="px-3 py-2 rounded-md text-sm font-medium disabled:opacity-40"
              style={{ backgroundColor: PALETTE.accent, color: PALETTE.bg }}
              data-testid="save-location-name-btn"
            >
              {savingName ? '…' : <Save size={14} />}
            </button>
          </div>
          <p className="text-xs mt-1.5" style={{ color: PALETTE.textDim }}>
            Slug:&nbsp;<code style={{ color: PALETTE.accent }}>{location.slug}</code>
          </p>
        </div>
        {master && (
          <button
            onClick={() => setShowDelete(true)}
            className="px-3 py-2 rounded-md text-sm flex items-center gap-1.5"
            style={{ color: PALETTE.danger, border: `1px solid ${PALETTE.danger}33` }}
            title="Delete location"
            data-testid="delete-location-btn"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>

      {/* Branding images */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h4 className="text-sm font-semibold text-white">Branding images</h4>
            <p className="text-xs" style={{ color: PALETTE.textDim }}>
              Plays right after the host slide. Drag to reorder.
            </p>
          </div>
          <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium cursor-pointer transition"
                 style={{ backgroundColor: PALETTE.accent, color: PALETTE.bg, opacity: uploading ? 0.5 : 1 }}
                 data-testid="upload-branding-btn">
            {uploading ? <Loader2 size={12} className="animate-spin" /> : <ImagePlus size={12} />}
            {uploading ? 'Uploading…' : 'Upload'}
            <input type="file"
                   multiple
                   accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
                   className="hidden"
                   disabled={uploading}
                   onChange={(e) => { handleFiles(Array.from(e.target.files || [])); e.target.value = ''; }}
                   data-testid="upload-branding-input"
            />
          </label>
        </div>
        <ImageGrid
          locationId={location.id}
          images={location.branding_images || []}
          onChange={onChange}
          setError={setError}
          setSuccess={setSuccess}
        />
      </div>

      {/* Admin assignments (master_admin only) */}
      {master && (
        <AdminAssignments
          location={location}
          allUsers={allUsers}
          onChange={onChange}
          setError={setError}
          setSuccess={setSuccess}
        />
      )}

      {showDelete && (
        <ConfirmDelete
          locationName={location.name}
          onClose={() => setShowDelete(false)}
          onConfirm={async () => {
            try {
              await api.deleteLocation(location.id);
              setSuccess?.(`Deleted "${location.name}"`);
              setShowDelete(false);
              onDeleted();
            } catch (e) {
              setError?.(e.response?.data?.detail || 'Failed to delete');
            }
          }}
        />
      )}
    </div>
  );
}


// ---------------------------------------------------------------
// Image grid with drag-to-reorder + per-image delete
// ---------------------------------------------------------------
function ImageGrid({ locationId, images, onChange, setError, setSuccess }) {
  // We track the visual order locally during drag so the UI is snappy;
  // commit to the server on drop. Re-syncs from `images` prop after the
  // parent refreshes.
  const [order, setOrder] = useState(images.map((i) => i.id));
  useEffect(() => { setOrder(images.map((i) => i.id)); }, [images]);

  const [draggedId, setDraggedId] = useState(null);
  const byId = useMemo(
    () => Object.fromEntries(images.map((i) => [i.id, i])),
    [images],
  );

  const onDragStart = (id) => () => setDraggedId(id);
  const onDragOver = (overId) => (e) => {
    e.preventDefault();
    if (!draggedId || draggedId === overId) return;
    setOrder((cur) => {
      const next = cur.filter((x) => x !== draggedId);
      const idx = next.indexOf(overId);
      next.splice(idx, 0, draggedId);
      return next;
    });
  };
  const onDragEnd = async () => {
    const before = images.map((i) => i.id);
    if (JSON.stringify(before) === JSON.stringify(order)) {
      setDraggedId(null);
      return;
    }
    setDraggedId(null);
    try {
      await api.reorderLocationImages(locationId, order);
      setSuccess?.('Reordered');
      onChange();
    } catch (e) {
      setError?.(e.response?.data?.detail || 'Reorder failed');
      // Reset to server truth on failure.
      setOrder(before);
    }
  };

  const removeImage = async (imgId) => {
    try {
      await api.deleteLocationImage(locationId, imgId);
      onChange();
    } catch (e) {
      setError?.(e.response?.data?.detail || 'Delete failed');
    }
  };

  if (!images.length) {
    return (
      <div data-testid="branding-grid" className="grid grid-cols-1">
        <div className="rounded-lg p-6 text-center text-sm"
             style={{ backgroundColor: PALETTE.bg, border: `1px dashed ${PALETTE.border}`, color: PALETTE.textDim }}
             data-testid="branding-empty">
          No branding images yet. Drop PNG / JPG / GIF / WEBP files using the Upload button above.
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3"
         data-testid="branding-grid">
      {order.map((id) => {
        const img = byId[id];
        if (!img) return null;
        return (
          <div
            key={id}
            draggable
            onDragStart={onDragStart(id)}
            onDragOver={onDragOver(id)}
            onDragEnd={onDragEnd}
            onDrop={onDragEnd}
            className="group relative rounded-lg overflow-hidden cursor-grab active:cursor-grabbing"
            style={{
              backgroundColor: PALETTE.bg,
              border: `1px solid ${draggedId === id ? PALETTE.accent : PALETTE.border}`,
              opacity: draggedId === id ? 0.5 : 1,
            }}
            data-testid={`branding-image-${id}`}
          >
            <img
              src={api.locationImageRawUrl(locationId, id)}
              alt={img.filename}
              className="block w-full h-32 object-cover"
              draggable={false}
            />
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors">
              <div className="absolute top-1 left-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <GripVertical size={14} style={{ color: PALETTE.accent }} />
              </div>
              <button
                onClick={() => removeImage(id)}
                className="absolute top-1 right-1 p-1 rounded-md opacity-0 group-hover:opacity-100 transition-opacity"
                style={{ backgroundColor: 'rgba(239, 68, 68, 0.9)', color: '#fff' }}
                title="Remove"
                data-testid={`branding-delete-${id}`}
              >
                <Trash2 size={12} />
              </button>
              <div className="absolute bottom-0 left-0 right-0 px-2 py-1 text-[10px] truncate"
                   style={{ backgroundColor: 'rgba(0,0,0,0.6)', color: '#fff' }}>
                {img.filename}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}


// ---------------------------------------------------------------
// Admin assignments (master_admin only)
// ---------------------------------------------------------------
function AdminAssignments({ location, allUsers, onChange, setError, setSuccess }) {
  // `_id` is the canonical identifier coming back from `/api/users` —
  // we always prefer it over `id` so legacy webapp users (Mongo ObjectId)
  // and native users (UUID) interop cleanly.
  const adminPool = useMemo(
    () => (allUsers || []).filter((u) => u.role === 'admin'),
    [allUsers],
  );
  const assigned = new Set(location.assigned_user_ids || []);

  const toggle = async (userKey) => {
    const next = new Set(assigned);
    if (next.has(userKey)) next.delete(userKey); else next.add(userKey);
    try {
      await api.setLocationAdmins(location.id, Array.from(next));
      setSuccess?.('Assignments updated');
      onChange();
    } catch (e) {
      setError?.(e.response?.data?.detail || 'Assignment update failed');
    }
  };

  return (
    <div>
      <h4 className="text-sm font-semibold text-white mb-1">Assigned admins</h4>
      <p className="text-xs mb-3" style={{ color: PALETTE.textDim }}>
        Admins ticked here can edit this location&apos;s branding. Master admins always see every location.
      </p>
      {adminPool.length === 0 ? (
        <p className="text-xs italic" style={{ color: PALETTE.textDim }}>
          No regular admins exist yet. Add one in the User Management tab.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2" data-testid="admin-assignments">
          {adminPool.map((u) => {
            const key = u._id || u.id;
            const on = assigned.has(key);
            return (
              <button
                key={key}
                onClick={() => toggle(key)}
                className="px-2.5 py-1.5 rounded-md text-xs font-medium flex items-center gap-1.5 transition"
                style={{
                  backgroundColor: on ? 'rgba(34, 197, 94, 0.15)' : PALETTE.bg,
                  color: on ? PALETTE.success : PALETTE.textDim,
                  border: `1px solid ${on ? `${PALETTE.success}55` : PALETTE.border}`,
                }}
                data-testid={`assign-toggle-${key}`}
              >
                {on && <Check size={11} />}
                {u.display_name || u.name || u.first_name || u.email}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ---------------------------------------------------------------
// Confirm-delete modal
// ---------------------------------------------------------------
function ConfirmDelete({ locationName, onClose, onConfirm }) {
  const [busy, setBusy] = useState(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
         style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
         onClick={onClose}
         data-testid="confirm-delete-location">
      <div onClick={(e) => e.stopPropagation()}
           className="rounded-xl p-6 w-full max-w-md"
           style={{ backgroundColor: PALETTE.panel, border: `1px solid ${PALETTE.danger}55` }}>
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle size={20} style={{ color: PALETTE.danger }} />
          <h3 className="text-lg font-bold text-white">Delete this location?</h3>
        </div>
        <p className="text-sm mb-5" style={{ color: PALETTE.textDim }}>
          <strong>{locationName}</strong> and all of its branding images will be permanently removed.
          Trivia presentations already built for this location won&apos;t be affected, but new builds
          referencing it will need a replacement.
        </p>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 rounded-md text-sm"
                  style={{ color: PALETTE.textDim }}>Cancel</button>
          <button
            onClick={async () => { setBusy(true); await onConfirm(); setBusy(false); }}
            disabled={busy}
            className="px-3 py-1.5 rounded-md text-sm font-medium text-white"
            style={{ backgroundColor: PALETTE.danger }}
            data-testid="confirm-delete-location-btn"
          >
            {busy ? 'Deleting…' : 'Delete location'}
          </button>
        </div>
      </div>
    </div>
  );
}
