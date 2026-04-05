import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const api = {
  // SharePoint
  getSharePointFiles: () => axios.get(`${API}/sharepoint/files`),
  syncSharePoint: () => axios.post(`${API}/sharepoint/sync`),
  
  // Scores
  getScores: () => axios.get(`${API}/scores`),
  getVenueScores: (venue) => axios.get(`${API}/scores/${encodeURIComponent(venue)}`),
  
  // Presets
  getPresets: () => axios.get(`${API}/presets`),
  getPreset: (id) => axios.get(`${API}/presets/${id}`),
  createPreset: (data) => axios.post(`${API}/presets`, data),
  updatePreset: (id, data) => axios.put(`${API}/presets/${id}`, data),
  deletePreset: (id) => axios.delete(`${API}/presets/${id}`),
  
  // Tournaments
  getTournaments: () => axios.get(`${API}/tournaments`),
  getTournament: (id) => axios.get(`${API}/tournaments/${id}`),
  createTournament: (data) => axios.post(`${API}/tournaments`, data),
  updateTournament: (id, data) => axios.put(`${API}/tournaments/${id}`, data),
  deleteTournament: (id) => axios.delete(`${API}/tournaments/${id}`),
  advanceTournament: (id, data) => axios.post(`${API}/tournaments/${id}/advance`, data),
  
  // Exports
  uploadExport: (formData) => axios.post(`${API}/exports/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  imageToVideo: (formData, duration = 15) => axios.post(`${API}/exports/image-to-video?duration=${duration}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  }),
};

export default api;
