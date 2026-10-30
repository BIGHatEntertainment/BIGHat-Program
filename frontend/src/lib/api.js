import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

function authHeaders() {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const api = {
  // Auth
  login: (email, password) =>
    axios.post(`${API}/api/auth/login`, { email, password }, { withCredentials: true }),
  logout: () =>
    axios.post(`${API}/api/auth/logout`, {}, { withCredentials: true }),
  me: () =>
    axios.get(`${API}/api/auth/me`, { withCredentials: true, headers: authHeaders() }),
  register: (data) =>
    axios.post(`${API}/api/auth/register`, data, { withCredentials: true, headers: authHeaders() }),

  // Product keys (master admin)
  getProductKeys: () =>
    axios.get(`${API}/api/native/license/product-keys`, { withCredentials: true, headers: authHeaders() }),
  addProductKey: (productKey) =>
    axios.post(`${API}/api/native/license/product-key`, { product_key: productKey }, { withCredentials: true, headers: authHeaders() }),

  // BIG Hat Cloud link (Admin > Integrations). The access key never reaches the browser.
  cloudLinkStatus: () => axios.get(`${API}/api/native/system/cloud-link/status`, { withCredentials: true, headers: authHeaders() }),
  cloudLinkCheck: () => axios.post(`${API}/api/native/system/cloud-link/check`, {}, { withCredentials: true, headers: authHeaders(), timeout: 30000 }),

  // BIG Hat Cloud sync (Phase 3): status, sync now, approve the first merge, one-time temporary passwords
  cloudSyncStatus: () => axios.get(`${API}/api/native/system/cloud-link/sync-status`, { withCredentials: true, headers: authHeaders() }),
  cloudSyncNow: () => axios.post(`${API}/api/native/system/cloud-link/sync-now`, {}, { withCredentials: true, headers: authHeaders(), timeout: 120000 }),
  cloudFilesStatus: () => axios.get(`${API}/api/native/system/cloud-link/files-status`, { withCredentials: true, headers: authHeaders() }),
  cloudSyncApprove: () => axios.post(`${API}/api/native/system/cloud-link/sync-approve`, {}, { withCredentials: true, headers: authHeaders(), timeout: 120000 }),
  // Cloud shows (v32.2.6): trivia shows built in the Cloud wizard, pulled onto this PC
  cloudShows: () => axios.get(`${API}/api/native/system/cloud-link/shows`, { withCredentials: true, headers: authHeaders() }),
  cloudShowImport: (planId, allowLocked = false) =>
    axios.post(`${API}/api/native/system/cloud-link/shows/${encodeURIComponent(planId)}/import`, {}, { params: { allow_locked: allowLocked }, withCredentials: true, headers: authHeaders() }),
  cloudSyncNewLogins: () => axios.post(`${API}/api/native/system/cloud-link/new-logins`, {}, { withCredentials: true, headers: authHeaders() }),

  // Setup Package (Admin > Integrations)
  pkgCheck: () => axios.get(`${API}/api/native/setup-package/check`, { withCredentials: true, headers: authHeaders() }),
  pkgPublish: () => axios.post(`${API}/api/native/setup-package/publish`, {}, { withCredentials: true, headers: authHeaders(), timeout: 150000 }),
  pkgPull: (apply, overwrite) =>
    axios.post(`${API}/api/native/setup-package/pull?apply=${apply ? 'true' : 'false'}&overwrite_changed=${overwrite ? 'true' : 'false'}`, {}, { withCredentials: true, headers: authHeaders(), timeout: 150000 }),
  pkgExportUrl: () => `${API}/api/native/setup-package/export`,
  pkgExport: () => axios.get(`${API}/api/native/setup-package/export`, { withCredentials: true, headers: authHeaders(), responseType: 'blob', timeout: 150000 }),
  pkgImport: (file, apply, overwrite) => {
    const f = new FormData(); f.append('file', file);
    return axios.post(`${API}/api/native/setup-package/import?apply=${apply ? 'true' : 'false'}&overwrite_changed=${overwrite ? 'true' : 'false'}`, f, { withCredentials: true, headers: authHeaders(), timeout: 150000 });
  },
  pkgTransferStart: (toEmail) => axios.post(`${API}/api/native/setup-package/transfer/start`, { to_email: toEmail }, { withCredentials: true, headers: authHeaders() }),
  pkgTransferConfirm: (code) => axios.post(`${API}/api/native/setup-package/transfer/confirm`, { code }, { withCredentials: true, headers: authHeaders() }),

  // Users
  getUsers: () =>
    axios.get(`${API}/api/users`, { withCredentials: true, headers: authHeaders() }),
  updateUser: (id, data) =>
    axios.put(`${API}/api/users/${id}`, data, { withCredentials: true, headers: authHeaders() }),
  deleteUser: (id) =>
    axios.delete(`${API}/api/users/${id}`, { withCredentials: true, headers: authHeaders() }),

  // Events
  getEvents: () =>
    axios.get(`${API}/api/events`, { withCredentials: true, headers: authHeaders() }),
  getUnclaimedEvents: () =>
    axios.get(`${API}/api/events/unclaimed`, { withCredentials: true, headers: authHeaders() }),
  createEvent: (data) =>
    axios.post(`${API}/api/events`, data, { withCredentials: true, headers: authHeaders() }),
  updateEvent: (id, data) =>
    axios.put(`${API}/api/events/${id}`, data, { withCredentials: true, headers: authHeaders() }),
  claimEvent: (id) =>
    axios.post(`${API}/api/events/${id}/claim`, {}, { withCredentials: true, headers: authHeaders() }),
  deleteEvent: (id) =>
    axios.delete(`${API}/api/events/${id}`, { withCredentials: true, headers: authHeaders() }),

  // Changelog
  getChangelog: () =>
    axios.get(`${API}/api/changelog`, { withCredentials: true, headers: authHeaders() }),

  // Trivia Setup (Locations)
  // game: 'trivia' | 'bingo' | 'karaoke' shows only places whose Schedule price for that game is above $0; leave empty for every place
  listLocations: (game) =>
    axios.get(`${API}/api/native/locations${game ? `?game=${game}` : ''}`, { withCredentials: true, headers: authHeaders() }),  createLocation: (data) =>
    axios.post(`${API}/api/native/locations`, data, { withCredentials: true, headers: authHeaders() }),
  getLocation: (id) =>
    axios.get(`${API}/api/native/locations/${id}`, { withCredentials: true, headers: authHeaders() }),
  updateLocation: (id, data) =>
    axios.patch(`${API}/api/native/locations/${id}`, data, { withCredentials: true, headers: authHeaders() }),
  deleteLocation: (id) =>
    axios.delete(`${API}/api/native/locations/${id}`, { withCredentials: true, headers: authHeaders() }),
  uploadLocationImage: (id, file) => {
    const form = new FormData();
    form.append('file', file);
    return axios.post(`${API}/api/native/locations/${id}/images`, form, {
      withCredentials: true,
      headers: { ...authHeaders() },
    });
  },
  deleteLocationImage: (id, imageId) =>
    axios.delete(`${API}/api/native/locations/${id}/images/${imageId}`, { withCredentials: true, headers: authHeaders() }),
  reorderLocationImages: (id, imageIds) =>
    axios.patch(`${API}/api/native/locations/${id}/images/order`, { image_ids: imageIds }, { withCredentials: true, headers: authHeaders() }),
  setLocationAdmins: (id, userIds) =>
    axios.patch(`${API}/api/native/locations/${id}/admins`, { assigned_user_ids: userIds }, { withCredentials: true, headers: authHeaders() }),
  locationImageRawUrl: (id, imageId) =>
    `${API}/api/native/locations/${id}/images/${imageId}/raw`,
  // Overlay images — alpha.33: parallel API to branding images
  uploadLocationOverlay: (id, file) => {
    const form = new FormData();
    form.append('file', file);
    return axios.post(`${API}/api/native/locations/${id}/overlays`, form, {
      withCredentials: true,
      headers: { ...authHeaders() },
    });
  },
  deleteLocationOverlay: (id, imageId) =>
    axios.delete(`${API}/api/native/locations/${id}/overlays/${imageId}`, { withCredentials: true, headers: authHeaders() }),
  reorderLocationOverlays: (id, imageIds) =>
    axios.patch(`${API}/api/native/locations/${id}/overlays/order`, { image_ids: imageIds }, { withCredentials: true, headers: authHeaders() }),
  tagLocationOverlay: (id, imageId, roundTypes) =>
    axios.patch(`${API}/api/native/locations/${id}/overlays/${imageId}/tags`, { applies_to_round_types: roundTypes }, { withCredentials: true, headers: authHeaders() }),
  locationOverlayRawUrl: (id, imageId) =>
    `${API}/api/native/locations/${id}/overlays/${imageId}/raw`,

  // Sponsor slide image — alpha.88: ONE per location (a new upload replaces the old one)
  uploadLocationSponsor: (id, file) => {
    const form = new FormData();
    form.append('file', file);
    return axios.post(`${API}/api/native/locations/${id}/sponsor`, form, {
      withCredentials: true,
      headers: { ...authHeaders() },
    });
  },
  deleteLocationSponsor: (id) =>
    axios.delete(`${API}/api/native/locations/${id}/sponsor`, { withCredentials: true, headers: authHeaders() }),
  locationSponsorRawUrl: (id, imageId) =>
    `${API}/api/native/locations/${id}/sponsor/raw?v=${imageId || ''}`,

  // Backup (master_admin only)
  backupStatus: () =>
    axios.get(`${API}/api/native/backup/status`, { withCredentials: true, headers: authHeaders() }),
  runBackup: () =>
    axios.post(`${API}/api/native/backup/run`, {}, { withCredentials: true, headers: authHeaders() }),
};

export default api;
