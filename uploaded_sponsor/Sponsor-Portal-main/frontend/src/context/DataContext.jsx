import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  sponsorsApi, locationsApi, assetsApi, subscriptionsApi, accountsApi,
  transformSponsor, transformLocation, transformAsset, transformAccount, transformSubscription,
  initDatabase
} from '../services/api';

const DataContext = createContext();

export const useData = () => {
  const context = useContext(DataContext);
  if (!context) {
    throw new Error('useData must be used within a DataProvider');
  }
  return context;
};

// Helper to get initial data from localStorage
const getLocalData = (key, defaultValue) => {
  try {
    const stored = localStorage.getItem(key);
    if (stored) {
      let data = JSON.parse(stored);
      // Fix any stale "Top Tier" references to "Star Tier"
      if (data && typeof data === 'object') {
        let needsSave = false;
        const fixTopTier = (obj) => {
          if (obj.sponsorPackage && typeof obj.sponsorPackage === 'string' && obj.sponsorPackage.toLowerCase().includes('top tier')) {
            obj.sponsorPackage = obj.sponsorPackage.replace(/top tier/gi, 'Star Tier');
            needsSave = true;
          }
          if (obj.packageName && typeof obj.packageName === 'string' && obj.packageName.toLowerCase().includes('top tier')) {
            obj.packageName = obj.packageName.replace(/top tier/gi, 'Star Tier');
            needsSave = true;
          }
          return obj;
        };
        
        if (Array.isArray(data)) {
          data = data.map(item => fixTopTier(item));
        } else {
          data = fixTopTier(data);
          
          // CRITICAL FIX: Clean stale isVenueSponsor flags from user profile
          // If isVenueSponsor is true but there's no sponsorId/sponsorTier to back it up,
          // this is corrupted data that should be reset
          if (key === 'bh_user_profile' && data.isVenueSponsor === true && !data.sponsorId && !data.sponsorTier) {
            data.isVenueSponsor = false;
            needsSave = true;
          }
        }
        
        // Clear stale location data that contains mock location IDs
        // Real location IDs from DB start with "loc_" followed by a hex string
        if (key === 'bh_locations' && Array.isArray(data)) {
          const hasMockData = data.some(loc => 
            loc.id && (loc.id === 'loc_001' || loc.id === 'loc_002' || loc.id === 'loc_003')
          );
          if (hasMockData) {
            // Clear stale mock data - will be refreshed from API
            localStorage.removeItem(key);
            return defaultValue;
          }
        }
        
        // Save the fixed data back
        if (needsSave) {
          localStorage.setItem(key, JSON.stringify(data));
        }
      }
      return data;
    }
  } catch (e) {
    console.error(`Error loading ${key}:`, e);
  }
  return defaultValue;
};

// Helper to save to localStorage
const setLocalData = (key, data) => {
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch (e) {
    console.error(`Error saving ${key}:`, e);
  }
};

export const DataProvider = ({ children }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // ============ ADMIN DATA (from API) ============
  const [locations, setLocationsState] = useState([]);
  const [sponsors, setSponsorsState] = useState([]);
  const [assets, setAssetsState] = useState([]);
  const [pendingApprovals, setPendingApprovalsState] = useState([]);
  const [registeredAccounts, setRegisteredAccountsState] = useState([]);

  // ============ USER-SPECIFIC DATA (localStorage for now) ============
  const [userProfile, setUserProfileState] = useState(() => {
    const stored = getLocalData('bh_user_profile', null);
    // Default to clean state - NO venue sponsor, NO tier
    return stored || {
      id: null,
      email: null,
      name: null,
      picture: null,
      businessName: null,
      phone: null,
      website: null,
      sponsorTier: null,
      sponsorPackage: null,
      isVenueSponsor: false,
      joinedAt: null
    };
  });
  const [userSubscriptions, setUserSubscriptionsState] = useState(() => 
    getLocalData('bh_user_subscriptions', [])
  );
  const [userAssets, setUserAssetsState] = useState(() => 
    getLocalData('bh_user_assets', [])
  );
  const [userPlacements, setUserPlacementsState] = useState(() => 
    getLocalData('bh_user_placements', [])
  );

  // ============ FETCH DATA FROM API ============
  const fetchAllData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Initialize database with seed data if empty
      await initDatabase();
      
      // Fetch all data in parallel
      const [locationsData, sponsorsData, assetsData, pendingData, accountsData] = await Promise.all([
        locationsApi.getAll(),
        sponsorsApi.getAll(),
        assetsApi.getAll(),
        assetsApi.getPending(),
        accountsApi.getAll(),
      ]);
      
      setLocationsState(locationsData.map(transformLocation));
      setSponsorsState(sponsorsData.map(transformSponsor));
      setAssetsState(assetsData.map(transformAsset));
      setPendingApprovalsState(pendingData.map(transformAsset));
      setRegisteredAccountsState(accountsData.map(transformAccount));
      
      // Save to localStorage for offline fallback (but API always takes precedence)
      setLocalData('bh_locations', locationsData.map(transformLocation));
      setLocalData('bh_sponsors', sponsorsData.map(transformSponsor));
      
      // Also fetch user-specific data if user is logged in
      if (userProfile?.email) {
        try {
          const userAssetsData = await assetsApi.getUserAssets(userProfile.email);
          setUserAssetsState(userAssetsData.map(transformAsset));
          setLocalData('bh_user_assets', userAssetsData.map(transformAsset));
        } catch (e) {
          // User has no assets yet
        }
        
        try {
          const activeSubData = await subscriptionsApi.getActive(userProfile.email);
          if (activeSubData) {
            setUserSubscriptionsState([transformSubscription(activeSubData)]);
            setLocalData('bh_user_subscriptions', [transformSubscription(activeSubData)]);
          }
        } catch (e) {
          // No active subscription found
        }
      }
      
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError(err.message);
      // Fall back to localStorage data (not mock data)
      // If localStorage is empty, use empty arrays to avoid showing fake data
      setLocationsState(getLocalData('bh_locations', []));
      setSponsorsState(getLocalData('bh_sponsors', []));
    } finally {
      setLoading(false);
    }
  }, [userProfile?.email]);

  // Fetch data on mount
  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  // Persist user-specific data to localStorage
  useEffect(() => {
    setLocalData('bh_user_profile', userProfile);
  }, [userProfile]);

  useEffect(() => {
    setLocalData('bh_user_subscriptions', userSubscriptions);
  }, [userSubscriptions]);

  useEffect(() => {
    setLocalData('bh_user_assets', userAssets);
  }, [userAssets]);

  useEffect(() => {
    setLocalData('bh_user_placements', userPlacements);
  }, [userPlacements]);

  // ============ LOCATION OPERATIONS ============
  const addLocation = async (location) => {
    try {
      const newLocation = await locationsApi.create(location);
      const transformed = transformLocation(newLocation);
      setLocationsState(prev => [...prev, transformed]);
      return transformed;
    } catch (err) {
      console.error('Failed to add location:', err);
      throw err;
    }
  };

  const updateLocation = async (id, updates) => {
    try {
      const updated = await locationsApi.update(id, updates);
      const transformed = transformLocation(updated);
      setLocationsState(prev => 
        prev.map(loc => loc.id === id ? transformed : loc)
      );
      return transformed;
    } catch (err) {
      console.error('Failed to update location:', err);
      throw err;
    }
  };

  const deleteLocation = async (id) => {
    try {
      await locationsApi.delete(id);
      setLocationsState(prev => prev.filter(loc => loc.id !== id));
    } catch (err) {
      console.error('Failed to delete location:', err);
      throw err;
    }
  };

  const getActiveLocations = () => {
    return locations.filter(loc => loc.status === 'active');
  };

  // ============ SPONSOR OPERATIONS ============
  const addSponsor = async (sponsor) => {
    try {
      const newSponsor = await sponsorsApi.create(sponsor);
      const transformed = transformSponsor(newSponsor);
      setSponsorsState(prev => [...prev, transformed]);
      return transformed;
    } catch (err) {
      console.error('Failed to add sponsor:', err);
      throw err;
    }
  };

  const updateSponsor = async (id, updates) => {
    try {
      const updated = await sponsorsApi.update(id, updates);
      const transformed = transformSponsor(updated);
      setSponsorsState(prev => 
        prev.map(s => s.id === id ? transformed : s)
      );
      return transformed;
    } catch (err) {
      console.error('Failed to update sponsor:', err);
      throw err;
    }
  };

  const deleteSponsor = async (id) => {
    try {
      await sponsorsApi.delete(id);
      setSponsorsState(prev => prev.filter(s => s.id !== id));
    } catch (err) {
      console.error('Failed to delete sponsor:', err);
      throw err;
    }
  };

  // ============ ACCOUNT OPERATIONS ============
  const registerAccount = async (accountData) => {
    try {
      const newAccount = await accountsApi.register(accountData);
      const transformed = transformAccount(newAccount);
      setRegisteredAccountsState(prev => [...prev, transformed]);
      return transformed;
    } catch (err) {
      console.error('Failed to register account:', err);
      throw err;
    }
  };

  const getUnlinkedAccounts = () => {
    const sponsorEmails = sponsors.map(s => s.email?.toLowerCase());
    return registeredAccounts.filter(account => 
      !sponsorEmails.includes(account.email?.toLowerCase())
    );
  };

  // ============ USER SUBSCRIPTION OPERATIONS ============
  const purchaseSubscription = async (packageData) => {
    try {
      const subData = {
        userId: userProfile.email,
        packageId: packageData.id,
        packageName: packageData.name,
        price: packageData.price,
      };
      
      const newSub = await subscriptionsApi.create(subData);
      const transformed = transformSubscription(newSub);
      setUserSubscriptionsState(prev => [...prev, transformed]);
      
      // Update sponsor status
      const matchingSponsor = sponsors.find(s => 
        s.email?.toLowerCase() === userProfile.email?.toLowerCase()
      );
      if (matchingSponsor) {
        await updateSponsor(matchingSponsor.id, { 
          status: 'active', 
          package: packageData.name 
        });
      }
      
      return transformed;
    } catch (err) {
      console.error('Failed to purchase subscription:', err);
      throw err;
    }
  };

  const cancelSubscription = async (subscriptionId) => {
    try {
      await subscriptionsApi.cancel(subscriptionId);
      setUserSubscriptionsState(prev => 
        prev.map(sub => sub.id === subscriptionId ? { ...sub, status: 'cancelled' } : sub)
      );
    } catch (err) {
      console.error('Failed to cancel subscription:', err);
      throw err;
    }
  };

  const getActiveSubscription = () => {
    // Only return active subscription if user has EXPLICIT sponsor tier set
    // Do NOT assume venue sponsor status from tier alone - it must be explicitly set
    const sponsorTier = userProfile?.sponsorTier;
    const isVenueSponsor = userProfile?.isVenueSponsor === true;
    
    // Check if user is explicitly marked as a venue sponsor
    if (isVenueSponsor) {
      return {
        packageId: 'star-tier',
        packageName: userProfile?.sponsorPackage || 'Venue Sponsor',
        price: 0,
        status: 'active',
        startDate: '2024-01-01',
        endDate: '2099-12-31',
        isVenueSponsor: true
      };
    }
    
    // Check if user has gold/star tier (but NOT automatically venue sponsor)
    if (sponsorTier === 'gold') {
      return {
        packageId: 'gold',
        packageName: userProfile?.sponsorPackage || 'Gold Sponsor',
        price: 0,
        status: 'active',
        startDate: '2024-01-01',
        endDate: '2099-12-31',
        isVenueSponsor: false
      };
    }
    
    // Check if user has silver tier
    if (sponsorTier === 'silver') {
      return {
        packageId: 'silver',
        packageName: userProfile?.sponsorPackage || 'Silver',
        price: 0,
        status: 'active',
        startDate: '2024-01-01',
        endDate: '2099-12-31',
      };
    }
    
    // Check if user has bronze tier
    if (sponsorTier === 'bronze') {
      return {
        packageId: 'bronze',
        packageName: userProfile?.sponsorPackage || 'Bronze',
        price: 0,
        status: 'active',
        startDate: '2024-01-01',
        endDate: '2099-12-31',
      };
    }
    
    const now = new Date().toISOString().split('T')[0];
    return userSubscriptions.find(sub => 
      sub.status === 'active' && sub.endDate >= now
    );
  };

  // ============ USER ASSET OPERATIONS ============
  const uploadUserAsset = async (assetData) => {
    try {
      const newAssetData = {
        ...assetData,
        sponsorName: userProfile.businessName || userProfile.name,
        sponsorEmail: userProfile.email,
        status: 'pending'
      };
      
      const newAsset = await assetsApi.create(newAssetData);
      const transformed = transformAsset(newAsset);
      
      setUserAssetsState(prev => [...prev, transformed]);
      setPendingApprovalsState(prev => [...prev, transformed]);
      
      return transformed;
    } catch (err) {
      console.error('Failed to upload asset:', err);
      throw err;
    }
  };

  const getUserApprovedAssets = () => {
    return userAssets.filter(a => a.status === 'approved');
  };

  const getUserPendingAssets = () => {
    return userAssets.filter(a => a.status === 'pending');
  };

  // ============ ADMIN ASSET OPERATIONS ============
  const approveAsset = async (id) => {
    try {
      await assetsApi.approve(id);
      const asset = pendingApprovals.find(a => a.id === id);
      if (asset) {
        const approvedAsset = { ...asset, status: 'approved' };
        setAssetsState(prev => [...prev, approvedAsset]);
        setPendingApprovalsState(prev => prev.filter(a => a.id !== id));
        setUserAssetsState(prev => 
          prev.map(a => a.id === id ? { ...a, status: 'approved' } : a)
        );
      }
    } catch (err) {
      console.error('Failed to approve asset:', err);
      throw err;
    }
  };

  const rejectAsset = async (id) => {
    try {
      await assetsApi.reject(id);
      setPendingApprovalsState(prev => prev.filter(a => a.id !== id));
      setUserAssetsState(prev => 
        prev.map(a => a.id === id ? { ...a, status: 'rejected' } : a)
      );
    } catch (err) {
      console.error('Failed to reject asset:', err);
      throw err;
    }
  };

  const requestRevision = async (id, notes) => {
    try {
      await assetsApi.requestRevision(id, notes);
      const asset = pendingApprovals.find(a => a.id === id);
      if (asset) {
        const revisionAsset = { ...asset, status: 'revision_requested', notes };
        setAssetsState(prev => [...prev, revisionAsset]);
        setPendingApprovalsState(prev => prev.filter(a => a.id !== id));
        setUserAssetsState(prev => 
          prev.map(a => a.id === id ? { ...a, status: 'revision_requested', notes } : a)
        );
      }
    } catch (err) {
      console.error('Failed to request revision:', err);
      throw err;
    }
  };

  const deleteAsset = async (id) => {
    try {
      await assetsApi.delete(id);
      setAssetsState(prev => prev.filter(a => a.id !== id));
      setPendingApprovalsState(prev => prev.filter(a => a.id !== id));
      setUserAssetsState(prev => prev.filter(a => a.id !== id));
    } catch (err) {
      console.error('Failed to delete asset:', err);
      throw err;
    }
  };

  const updateAsset = async (id, updates) => {
    try {
      const updated = await assetsApi.update(id, updates);
      const transformed = transformAsset(updated);
      setAssetsState(prev => 
        prev.map(a => a.id === id ? transformed : a)
      );
      setUserAssetsState(prev => 
        prev.map(a => a.id === id ? transformed : a)
      );
      return transformed;
    } catch (err) {
      console.error('Failed to update asset:', err);
      throw err;
    }
  };

  // ============ USER PROFILE OPERATIONS ============
  const updateUserProfile = (updates) => {
    setUserProfileState(prev => ({ ...prev, ...updates }));
  };

  const updateUserPicture = (pictureDataUrl) => {
    setUserProfileState(prev => ({ ...prev, picture: pictureDataUrl }));
  };

  const initializeUserProfile = (userData) => {
    // CRITICAL FIX: On ANY login/auth event, we ALWAYS use backend data as the source of truth
    // for sponsor-related fields. This prevents stale localStorage data from persisting.
    
    // Build a completely fresh profile using ONLY backend data for critical fields
    const freshProfile = {
      // Basic user info
      id: userData.id || null,
      email: userData.email || null,
      name: userData.name || null,
      picture: userData.picture || null,
      role: userData.role || 'sponsor',
      
      // Business info (from backend)
      businessName: userData.businessName || null,
      phone: userData.phone || null,
      website: userData.website || null,
      
      // CRITICAL: Sponsor-related fields MUST come from backend, NEVER from localStorage
      // These are the fields that were causing the bug - stale localStorage was overriding backend
      sponsorTier: userData.sponsorTier || null,
      sponsorPackage: userData.sponsorPackage || null,
      sponsorId: userData.sponsorId || null,
      // ONLY true if backend explicitly says true, otherwise ALWAYS false
      isVenueSponsor: userData.isVenueSponsor === true,
      
      // Non-critical fields can be preserved from previous session
      joinedAt: userData.joinedAt || new Date().toISOString().split('T')[0],
    };
    
    // Get existing profile to check if this is a new user
    const existingProfile = getLocalData('bh_user_profile', null);
    const isNewUser = !existingProfile || existingProfile.email !== userData.email;
    
    // Set the fresh profile - completely replacing old state
    setUserProfileState(freshProfile);
    
    // Clear assets/subscriptions for new users
    if (isNewUser) {
      setUserAssetsState([]);
      setUserSubscriptionsState([]);
      setUserPlacementsState([]);
    }
  };

  // ============ PLACEMENTS OPERATIONS ============
  const generatePlacements = () => {
    const activeSubscription = getActiveSubscription();
    if (!activeSubscription) return [];

    const activeLocations = getActiveLocations();
    const approvedAssets = getUserApprovedAssets();
    
    if (activeLocations.length === 0 || approvedAssets.length === 0) return [];

    const placements = [];
    const startDate = new Date();
    
    for (let week = 0; week < 4; week++) {
      activeLocations.forEach((location, index) => {
        const placementDate = new Date(startDate);
        placementDate.setDate(placementDate.getDate() + (week * 7) + index);
        
        placements.push({
          id: `pl_${Date.now()}_${week}_${index}`,
          date: placementDate.toISOString().split('T')[0],
          venue: `${location.name} - ${location.city}`,
          locationId: location.id,
          placement: getPlacementType(activeSubscription.packageId),
          assetId: approvedAssets[index % approvedAssets.length]?.id
        });
      });
    }

    return placements.sort((a, b) => new Date(a.date) - new Date(b.date));
  };

  const getPlacementType = (packageId) => {
    switch (packageId) {
      case 'star-tier': return 'Presented-by Title';
      case 'gold': return 'Pre-show Mention + Round Overlay';
      case 'silver': return 'Round Sponsor';
      case 'bronze': return 'Thank You Credits';
      default: return 'Sponsor Display';
    }
  };

  // ============ METRICS ============
  const getSponsorMetrics = () => {
    const activeSubscription = getActiveSubscription();
    const activeLocations = getActiveLocations();
    const approvedAssets = getUserApprovedAssets();
    const joinedDate = userProfile.joinedAt ? new Date(userProfile.joinedAt) : null;
    
    const daysAsSponsor = joinedDate 
      ? Math.floor((new Date() - joinedDate) / (1000 * 60 * 60 * 24))
      : 0;

    // Calculate estimated impressions based on capacity tiers
    const getCapacityValue = (tier) => {
      switch(tier) {
        case '< 50': return 35;
        case '> 50': return 75;
        case '100+': return 125;
        default: return 50;
      }
    };
    const avgCapacityPerVenue = activeLocations.reduce((sum, loc) => sum + getCapacityValue(loc.capacityTier), 0) / (activeLocations.length || 1);
    const showsPerMonth = activeLocations.length * 4;
    const estimatedImpressions = activeSubscription ? Math.round(avgCapacityPerVenue * showsPerMonth) : 0;

    return {
      totalShows: activeSubscription ? showsPerMonth : 0,
      estimatedImpressions,
      activeAssets: approvedAssets.length,
      venuesCovered: activeSubscription ? activeLocations.length : 0,
      daysAsSponsor,
      hasActiveSubscription: !!activeSubscription,
      currentTier: activeSubscription?.packageName || null,
      subscriptionEnds: activeSubscription?.endDate || null
    };
  };

  // ============ RESET ============
  const resetAllData = () => {
    localStorage.removeItem('bh_user_profile');
    localStorage.removeItem('bh_user_subscriptions');
    localStorage.removeItem('bh_user_assets');
    localStorage.removeItem('bh_user_placements');
    
    // Reset to clean state - NO venue sponsor, NO tier
    setUserProfileState({
      id: null,
      email: null,
      name: null,
      picture: null,
      businessName: null,
      phone: null,
      website: null,
      sponsorTier: null,
      sponsorPackage: null,
      isVenueSponsor: false,
      joinedAt: null
    });
    setUserSubscriptionsState([]);
    setUserAssetsState([]);
    setUserPlacementsState([]);
    
    // Refetch from API
    fetchAllData();
  };

  const value = {
    // Loading state
    loading,
    error,
    refetch: fetchAllData,
    
    // Data
    locations,
    sponsors,
    assets,
    pendingApprovals,
    userProfile,
    userSubscriptions,
    userAssets,
    userPlacements,
    registeredAccounts,
    
    // Location operations
    addLocation,
    updateLocation,
    deleteLocation,
    getActiveLocations,
    
    // Sponsor operations
    addSponsor,
    updateSponsor,
    deleteSponsor,
    
    // Account operations
    registerAccount,
    getUnlinkedAccounts,
    
    // Subscription operations
    purchaseSubscription,
    cancelSubscription,
    getActiveSubscription,
    
    // User asset operations
    uploadUserAsset,
    getUserApprovedAssets,
    getUserPendingAssets,
    
    // Admin asset operations
    approveAsset,
    rejectAsset,
    requestRevision,
    deleteAsset,
    updateAsset,
    
    // User profile operations
    updateUserProfile,
    updateUserPicture,
    initializeUserProfile,
    
    // Placements
    generatePlacements,
    
    // Metrics
    getSponsorMetrics,
    
    // Utility
    resetAllData
  };

  return (
    <DataContext.Provider value={value}>
      {children}
    </DataContext.Provider>
  );
};

export default DataContext;
