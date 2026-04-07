import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const SponsorContext = createContext(null);

const API_BASE = process.env.REACT_APP_BACKEND_URL;

async function apiFetch(endpoint, options = {}) {
  const token = localStorage.getItem('sponsor_token');
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/sponsor${endpoint}`, { ...options, headers });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function SponsorProvider({ children }) {
  const [userProfile, setUserProfile] = useState(null);
  const [locations, setLocations] = useState([]);
  const [sponsors, setSponsors] = useState([]);
  const [loading, setLoading] = useState(true);

  const initializeUserProfile = useCallback(async (profileData) => {
    setUserProfile(profileData);
    localStorage.setItem('sponsor_user', JSON.stringify(profileData));
  }, []);

  const getActiveSubscription = useCallback(() => {
    return userProfile?.subscription || null;
  }, [userProfile]);

  const loadLocations = useCallback(async () => {
    try {
      const data = await apiFetch('/locations');
      setLocations(data);
      return data;
    } catch { return []; }
  }, []);

  const loadSponsors = useCallback(async () => {
    try {
      const data = await apiFetch('/sponsors');
      setSponsors(data);
      return data;
    } catch { return []; }
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem('sponsor_user');
    if (stored) {
      try { setUserProfile(JSON.parse(stored)); } catch {}
    }
    setLoading(false);
  }, []);

  return (
    <SponsorContext.Provider value={{
      userProfile, setUserProfile, initializeUserProfile,
      locations, loadLocations, sponsors, loadSponsors,
      getActiveSubscription, loading,
    }}>
      {children}
    </SponsorContext.Provider>
  );
}

export function useData() {
  const ctx = useContext(SponsorContext);
  if (!ctx) return {
    userProfile: null, locations: [], sponsors: [], loading: false,
    initializeUserProfile: () => {}, getActiveSubscription: () => null,
    loadLocations: async () => [], loadSponsors: async () => [],
  };
  return ctx;
}

export { SponsorContext };
export default SponsorContext;
