import axios from 'axios';
const API = `${process.env.REACT_APP_BACKEND_URL}/api/scoreboard`;
const api = {
  getPresets: () => axios.get(`${API}/presets`).then(r => r.data),
  createPreset: (data) => axios.post(`${API}/presets`, data).then(r => r.data),
  deletePreset: (id) => axios.delete(`${API}/presets/${id}`).then(r => r.data),
  syncScores: () => axios.post(`${API}/sync-scores`).then(r => r.data),
  getScoreFiles: () => axios.get(`${API}/score-files`).then(r => r.data),
  getScoreFile: (location, filename) => axios.get(`${API}/score-files/${encodeURIComponent(location)}/${encodeURIComponent(filename)}`).then(r => r.data),
  getAccumulatedScores: (venue) => axios.get(`${API}/accumulated-scores/${encodeURIComponent(venue)}`).then(r => r.data),
  exportImage: (data) => axios.post(`${API}/export-image`, data, { responseType: 'blob', timeout: 60000 }),
};
export default api;
