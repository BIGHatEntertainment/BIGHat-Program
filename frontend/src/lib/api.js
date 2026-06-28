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
  listLocations: () =>
    axios.get(`${API}/api/native/locations`, { withCredentials: true, headers: authHeaders() }),  createLocation: (data) =>
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

  // Backup (master_admin only)
  backupStatus: () =>
    axios.get(`${API}/api/native/backup/status`, { withCredentials: true, headers: authHeaders() }),
  runBackup: () =>
    axios.post(`${API}/api/native/backup/run`, {}, { withCredentials: true, headers: authHeaders() }),
};

export default api;
