import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const presentationAPI = {
  getAll: async (userName) => {
    const response = await axios.get(`${API}/presentations`, { params: { userName } });
    return response.data;
  },
  getById: async (id) => {
    const response = await axios.get(`${API}/presentations/${id}`);
    return response.data;
  },
  create: async (data) => {
    const response = await axios.post(`${API}/presentations`, data);
    return response.data;
  },
  update: async (id, data) => {
    const response = await axios.put(`${API}/presentations/${id}`, data);
    return response.data;
  },
  delete: async (id) => {
    const response = await axios.delete(`${API}/presentations/${id}`);
    return response.data;
  },
  importTrivia: async (triviaData) => {
    const response = await axios.post(`${API}/presentations/import-trivia`, triviaData, { timeout: 180000 });
    return response.data;
  },
  getAllCombined: async (userName, viewAll = false) => {
    try {
      const [regularPres, triviaPres] = await Promise.all([
        axios.get(`${API}/presentations`, { params: { userName, viewAll }, timeout: 30000 }).catch(() => ({ data: [] })),
        axios.get(`${API}/trivia-viewer/list`, { params: { userName, viewAll }, timeout: 30000 }).catch(() => ({ data: [] }))
      ]);
      const regular = regularPres.data.filter(p => p.type !== 'trivia-imported').map(p => ({ ...p, type: 'regular' }));
      const trivia = triviaPres.data.map(p => ({ ...p, type: 'trivia' }));
      return [...trivia, ...regular].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
    } catch (error) {
      console.error('Error fetching presentations:', error);
      return [];
    }
  },
  deleteTrivia: async (id) => {
    const response = await axios.delete(`${API}/trivia-viewer/delete/${id}`);
    return response.data;
  },
  getImportedTriviaSlides: async (id) => {
    const response = await axios.get(`${API}/trivia-import/slides/${id}`, { timeout: 60000 });
    return response.data;
  },
  getSlideChunk: async (presentationId, chunkNumber) => {
    const response = await axios.get(`${API}/trivia-import/chunk/${presentationId}/${chunkNumber}`, { timeout: 60000 });
    return response.data;
  },
  getSlidesMetadata: async (id) => {
    const response = await axios.get(`${API}/trivia-import/slides-metadata/${id}`, { timeout: 15000 });
    return response.data;
  },
  getSectionsList: async (id) => {
    const response = await axios.get(`${API}/slide-fetcher/sections-list/${id}`, { timeout: 10000 });
    return response.data;
  },
  fetchSection: async (presentationId, sectionName, sectionData = {}) => {
    const response = await axios.post(`${API}/slide-fetcher/fetch-section/${presentationId}/${sectionName}`, {
      roundType: sectionData.roundType,
      roundOrder: sectionData.roundOrder
    }, { timeout: 120000 });
    return response.data;
  },
  storeAllSlides: async (presentationId, slides) => {
    const response = await axios.post(`${API}/slide-fetcher/store-all/${presentationId}`, slides, { timeout: 60000 });
    return response.data;
  },
  getTriviaPresentation: async (id) => {
    const response = await axios.get(`${API}/trivia-viewer/${id}`, { timeout: 15000 });
    return response.data;
  }
};

export const triviaAPI = {
  getHosts: async () => {
    const response = await axios.get(`${API}/trivia/hosts`);
    return response.data;
  },
  getLocations: async () => {
    const response = await axios.get(`${API}/trivia/locations`);
    return response.data;
  },
  getRoundFilesByType: async (roundType, location = null) => {
    const params = location ? { location } : {};
    const response = await axios.get(`${API}/trivia/round-files/${roundType}`, { params });
    return response.data;
  },
};

export const adminAPI = {
  _getUserName: () => localStorage.getItem('userName') || '',
  getRoundUsage: async () => {
    const response = await axios.get(`${API}/trivia/round-usage`);
    return response.data;
  },
};

export const storyBuildsAPI = {
  saveBuild: async (buildData) => {
    const response = await axios.post(`${API}/story-builds/save`, buildData, { timeout: 30000 });
    return response.data;
  },
  listBuilds: async () => {
    const response = await axios.get(`${API}/story-builds/list`, { timeout: 30000 });
    return response.data;
  },
};

// Story Generator API
const STORY_API = `${process.env.REACT_APP_BACKEND_URL}/api/story-generator`;

export const storyGeneratorAPI = {
  getPresentations: async (userName = null) => {
    const params = userName ? { userName: userName.toLowerCase() } : {};
    const response = await axios.get(`${STORY_API}/presentations`, { params });
    return response.data;
  },
  getPresentation: async (id) => {
    const response = await axios.get(`${STORY_API}/presentation/${id}`);
    return response.data;
  },
  getAssets: async (refresh = false) => {
    const response = await axios.get(`${STORY_API}/assets`, { params: { refresh } });
    return response.data;
  },
  refreshAssets: async () => {
    const response = await axios.post(`${STORY_API}/refresh-assets`);
    return response.data;
  },
  generatePreview: async (presentationId) => {
    const response = await axios.post(`${STORY_API}/preview/${presentationId}`, {}, { timeout: 60000 });
    return response.data;
  },
  generateVideo: async (presentationId) => {
    const response = await axios.post(`${STORY_API}/generate/${presentationId}`, {}, { timeout: 300000 });
    return response.data;
  },
  getDownloadUrl: (filename) => `${STORY_API}/download/${filename}`,
  uploadAsset: async (file, assetType) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('asset_type', assetType);
    const response = await axios.post(`${STORY_API}/upload-asset`, formData, { timeout: 60000 });
    return response.data;
  },
  deleteAsset: async (assetType, assetId) => {
    const response = await axios.delete(`${STORY_API}/assets/${assetType}/${assetId}`);
    return response.data;
  },
};
