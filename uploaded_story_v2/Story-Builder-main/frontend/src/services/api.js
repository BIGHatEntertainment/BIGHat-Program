import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const presentationAPI = {
  // Get all presentations for a user
  getAll: async (userName) => {
    const response = await axios.get(`${API}/presentations`, {
      params: { userName }
    });
    return response.data;
  },

  // Get a specific presentation
  getById: async (id) => {
    const response = await axios.get(`${API}/presentations/${id}`);
    return response.data;
  },

  // Create new presentation
  create: async (data) => {
    const response = await axios.post(`${API}/presentations`, data);
    return response.data;
  },

  // Update presentation
  update: async (id, data) => {
    const response = await axios.put(`${API}/presentations/${id}`, data);
    return response.data;
  },

  // Delete presentation
  delete: async (id) => {
    const response = await axios.delete(`${API}/presentations/${id}`);
    return response.data;
  },

  // Import from trivia app
  importTrivia: async (triviaData) => {
    const response = await axios.post(`${API}/presentations/import-trivia`, triviaData, {
      timeout: 180000  // 3 minute timeout for building presentations with SharePoint
    });
    return response.data;
  },

  // Get all presentations (both regular and trivia)
  getAllCombined: async (userName) => {
    try {
      const [regularPres, triviaPres] = await Promise.all([
        axios.get(`${API}/presentations`, { params: { userName }, timeout: 30000 }).catch(() => ({ data: [] })),
        axios.get(`${API}/trivia-viewer/list`, { params: { userName }, timeout: 30000 }).catch(() => ({ data: [] }))
      ]);
      
      // Filter out trivia-imported presentations from regular list (they're shown in trivia list)
      const regular = regularPres.data
        .filter(p => p.type !== 'trivia-imported')
        .map(p => ({ ...p, type: 'regular' }));
      
      const trivia = triviaPres.data.map(p => ({ ...p, type: 'trivia' }));
      
      return [...trivia, ...regular].sort((a, b) => 
        new Date(b.createdAt) - new Date(a.createdAt)
      );
    } catch (error) {
      console.error('Error fetching presentations:', error);
      return [];
    }
  },

  // Import trivia presentation to regular presentation
  importTriviaToPresentation: async (triviaId) => {
    const response = await axios.post(`${API}/trivia-import/convert/${triviaId}`, {}, {
      timeout: 180000  // 3 minute timeout for conversion
    });
    return response.data;
  },

  // Delete trivia presentation
  deleteTrivia: async (id) => {
    const response = await axios.delete(`${API}/trivia-viewer/delete/${id}`);
    return response.data;
  },

  // Get imported trivia slides
  getImportedTriviaSlides: async (id) => {
    const response = await axios.get(`${API}/trivia-import/slides/${id}`, {
      timeout: 60000  // 60 second timeout
    });
    return response.data;
  },

  // Get a specific chunk of slides
  getSlideChunk: async (presentationId, chunkNumber) => {
    const response = await axios.get(`${API}/trivia-import/chunk/${presentationId}/${chunkNumber}`, {
      timeout: 60000  // 60 second timeout per chunk
    });
    return response.data;
  },

  // Get slides metadata
  getSlidesMetadata: async (id) => {
    const response = await axios.get(`${API}/trivia-import/slides-metadata/${id}`, {
      timeout: 15000
    });
    return response.data;
  },

  // Get list of sections to fetch
  getSectionsList: async (id) => {
    const response = await axios.get(`${API}/slide-fetcher/sections-list/${id}`, {
      timeout: 10000
    });
    return response.data;
  },

  // Fetch a single section (on-demand)
  fetchSection: async (presentationId, sectionName, sectionData = {}) => {
    const response = await axios.post(`${API}/slide-fetcher/fetch-section/${presentationId}/${sectionName}`, {
      roundType: sectionData.roundType,
      roundOrder: sectionData.roundOrder
    }, {
      timeout: 60000  // 60 second timeout per section
    });
    return response.data;
  },

  // Store all slides in GridFS after accumulating
  storeAllSlides: async (presentationId, slides) => {
    const response = await axios.post(`${API}/slide-fetcher/store-all/${presentationId}`, slides, {
      timeout: 60000
    });
    return response.data;
  },

  // Get trivia presentation metadata
  getTriviaPresentation: async (id) => {
    const response = await axios.get(`${API}/trivia-viewer/${id}`, {
      timeout: 15000
    });
    return response.data;
  }
};

export const triviaAPI = {
  // Get available hosts
  getHosts: async () => {
    const response = await axios.get(`${API}/trivia/hosts`);
    return response.data;
  },

  // Get available locations
  getLocations: async () => {
    const response = await axios.get(`${API}/trivia/locations`);
    return response.data;
  },

  // Get Multiple Choice rounds
  getMCRounds: async () => {
    const response = await axios.get(`${API}/trivia/rounds/mc`);
    return response.data;
  },

  // Get General (REG) rounds
  getREGRounds: async () => {
    const response = await axios.get(`${API}/trivia/rounds/reg`);
    return response.data;
  },

  // Get Specific (MISC) rounds
  getMISCRounds: async () => {
    const response = await axios.get(`${API}/trivia/rounds/misc`);
    return response.data;
  },

  // Get Mystery (MYS) rounds
  getMYSRounds: async () => {
    const response = await axios.get(`${API}/trivia/rounds/mys`);
    return response.data;
  },

  // Get BIG Question rounds
  getBIGRounds: async () => {
    const response = await axios.get(`${API}/trivia/rounds/big`);
    return response.data;
  },

  // Get individual files for a round type (filtered by location usage)
  getRoundFilesByType: async (roundType, location = null) => {
    const params = location ? { location } : {};
    const response = await axios.get(`${API}/trivia/round-files/${roundType}`, { params });
    return response.data;
  },

  // Get sponsors
  getSponsors: async () => {
    const response = await axios.get(`${API}/trivia/sponsors`);
    return response.data;
  },

  // Get files in a specific round folder
  getRoundFiles: async (folderPath) => {
    const response = await axios.get(`${API}/trivia/round-files`, {
      params: { folder_path: folderPath }
    });
    return response.data;
  }
};

export const adminAPI = {
  // Get all round usage records
  getRoundUsage: async () => {
    const response = await axios.get(`${API}/admin/round-usage`);
    return response.data;
  },

  // Release a specific round back into selection pool
  releaseRound: async (usageId) => {
    const response = await axios.delete(`${API}/admin/round-usage/${usageId}`);
    return response.data;
  },

  // Release all rounds from a presentation
  releasePresentationRounds: async (presentationId) => {
    const response = await axios.delete(`${API}/admin/round-usage/by-presentation/${presentationId}`);
    return response.data;
  },

  // Cleanup expired round usage records
  cleanupExpired: async () => {
    const response = await axios.post(`${API}/admin/cleanup-expired`);
    return response.data;
  },

  // Release all round usage records
  releaseAll: async () => {
    const response = await axios.post(`${API}/admin/round-usage/release-all`);
    return response.data;
  },

  // Get admin statistics
  getStats: async () => {
    const response = await axios.get(`${API}/admin/stats`);
    return response.data;
  }
};

// Story Generator API
export const storyGeneratorAPI = {
  // Get presentations available for story generation
  getPresentations: async (userName = null) => {
    const params = userName ? { userName: userName.toLowerCase() } : {};
    const response = await axios.get(`${API}/story-generator/presentations`, { params });
    return response.data;
  },

  // Get presentation details for story preview
  getPresentation: async (presentationId) => {
    const response = await axios.get(`${API}/story-generator/presentation/${presentationId}`);
    return response.data;
  },

  // Get available assets (location images, host GIFs, backgrounds)
  getAssets: async (refresh = false) => {
    const params = refresh ? { refresh: true } : {};
    const response = await axios.get(`${API}/story-generator/assets`, { params });
    return response.data;
  },

  // Refresh assets from SharePoint (clears cache)
  refreshAssets: async () => {
    const response = await axios.post(`${API}/story-generator/refresh-assets`);
    return response.data;
  },

  // Generate preview (without creating video)
  generatePreview: async (presentationId) => {
    const response = await axios.post(`${API}/story-generator/preview/${presentationId}`);
    return response.data;
  },

  // Generate story video
  generateVideo: async (presentationId) => {
    const response = await axios.post(`${API}/story-generator/generate/${presentationId}`, {}, {
      timeout: 120000  // 2 minute timeout for video generation
    });
    return response.data;
  },

  // Get download URL
  getDownloadUrl: (filename) => {
    return `${API}/story-generator/download/${filename}`;
  },

  // Upload asset
  uploadAsset: async (file, assetType, name = null) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('asset_type', assetType);
    if (name) {
      formData.append('name', name);
    }
    const response = await axios.post(`${API}/story-generator/upload-asset`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },

  // Delete asset
  deleteAsset: async (assetType, assetId) => {
    const response = await axios.delete(`${API}/story-generator/asset/${assetType}/${assetId}`);
    return response.data;
  }
};

