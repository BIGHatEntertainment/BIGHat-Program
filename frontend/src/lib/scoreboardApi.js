import axios from 'axios';
const API = `${process.env.REACT_APP_BACKEND_URL}/api/scoreboard`;

const api = {
  // SharePoint
  getSharePointFiles: () => axios.get(`${API}/sharepoint/files`).then(r => r.data),
  syncScores: () => axios.post(`${API}/sharepoint/sync`, {}, { timeout: 60000 }).then(r => r.data),
  getScoreFiles: () => axios.get(`${API}/sharepoint/files`, { timeout: 30000 }).then(r => r.data),
  
  // Scores
  getScores: () => axios.get(`${API}/scores`).then(r => r.data),
  getVenueScores: (venue) => axios.get(`${API}/scores/${encodeURIComponent(venue)}`).then(r => r.data),
  getAccumulatedScores: (venue) => axios.get(`${API}/accumulated-scores/${encodeURIComponent(venue)}`).then(r => r.data),
  
  // Presets
  getPresets: () => axios.get(`${API}/presets`).then(r => r.data),
  createPreset: (data) => axios.post(`${API}/presets`, data).then(r => r.data),
  deletePreset: (id) => axios.delete(`${API}/presets/${id}`).then(r => r.data),
  
  // Exports - these return the full axios response (not .data) because the dashboard uses .data
  uploadExport: (formData) => axios.post(`${API}/exports/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000,
  }),
  imageToVideo: (formData, duration = 15) => axios.post(`${API}/exports/image-to-video?duration=${duration}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000,
  }),
  exportImage: (data) => axios.post(`${API}/export-image`, data, { responseType: 'blob', timeout: 60000 }),
};

export default api;
