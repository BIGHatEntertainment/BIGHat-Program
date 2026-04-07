/**
 * API Service for BIG Hat Sponsor Portal
 * Handles all communication with the backend
 */

const API_BASE = process.env.REACT_APP_BACKEND_URL;

// Warn if API_BASE is not configured
if (!API_BASE) {
  console.error('[API] WARNING: REACT_APP_BACKEND_URL is not configured!');
} else {
  console.log('[API] Backend URL:', API_BASE);
}

// Helper function for API calls
async function apiCall(endpoint, options = {}) {
  const url = `${API_BASE}/api${endpoint}`;
  
  const defaultHeaders = {
    'Content-Type': 'application/json',
  };
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    });
    
    // Read response body once
    const responseText = await response.text();
    
    if (!response.ok) {
      let errorDetail = 'Request failed';
      try {
        const errorJson = JSON.parse(responseText);
        errorDetail = errorJson.detail || errorJson.message || `API Error: ${response.status}`;
      } catch {
        errorDetail = responseText || `API Error: ${response.status}`;
      }
      throw new Error(errorDetail);
    }
    
    // Parse successful response
    return responseText ? JSON.parse(responseText) : null;
  } catch (error) {
    console.error('[API] Error:', endpoint, error.message);
    throw error;
  }
}

// ============ SPONSORS ============
export const sponsorsApi = {
  getAll: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiCall(`/sponsors${query ? `?${query}` : ''}`);
  },
  
  getById: (id) => apiCall(`/sponsors/${id}`),
  
  getByEmail: (email) => apiCall(`/sponsors/by-email/${encodeURIComponent(email)}`),
  
  create: (data) => apiCall('/sponsors', {
    method: 'POST',
    body: JSON.stringify({
      business_name: data.businessName,
      email: data.email,
      contact_name: data.contactName,
      phone: data.phone,
      website: data.website,
      zip_code: data.zipCode,
      package: data.package,
      status: data.status || 'inactive',
      notes: data.notes,
      logo: data.logo,
      picture: data.picture,
      is_venue_sponsor: data.isVenueSponsor || false,
    }),
  }),
  
  // Create sponsor profile from existing registered account
  createFromAccount: (email) => apiCall(`/sponsors/from-account/${encodeURIComponent(email)}`, {
    method: 'POST',
  }),
  
  update: (id, data) => apiCall(`/sponsors/${id}`, {
    method: 'PUT',
    body: JSON.stringify({
      business_name: data.businessName,
      email: data.email,
      contact_name: data.contactName,
      phone: data.phone,
      website: data.website,
      zip_code: data.zipCode,
      package: data.package,
      status: data.status,
      notes: data.notes,
      logo: data.logo,
      picture: data.picture,
      is_venue_sponsor: data.isVenueSponsor,
    }),
  }),
  
  delete: (id) => apiCall(`/sponsors/${id}`, { method: 'DELETE' }),
};

// ============ LOCATIONS ============
export const locationsApi = {
  getAll: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiCall(`/locations${query ? `?${query}` : ''}`);
  },
  
  getById: (id) => apiCall(`/locations/${id}`),
  
  create: (data) => apiCall('/locations', {
    method: 'POST',
    body: JSON.stringify({
      name: data.name,
      address: data.address,
      city: data.city,
      state: data.state,
      zip_code: data.zip || data.zipCode,
      capacity_tier: data.capacityTier || '> 50',
      status: data.status || 'active',
    }),
  }),
  
  update: (id, data) => apiCall(`/locations/${id}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: data.name,
      address: data.address,
      city: data.city,
      state: data.state,
      zip_code: data.zip || data.zipCode,
      capacity_tier: data.capacityTier,
      status: data.status,
    }),
  }),
  
  delete: (id) => apiCall(`/locations/${id}`, { method: 'DELETE' }),
};

// ============ ASSETS ============
export const assetsApi = {
  getAll: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiCall(`/assets${query ? `?${query}` : ''}`);
  },
  
  getPending: () => apiCall('/assets/pending'),
  
  getUserAssets: (email) => apiCall(`/assets/user/${encodeURIComponent(email)}`),
  
  getById: (id) => apiCall(`/assets/${id}`),
  
  create: (data) => apiCall('/assets', {
    method: 'POST',
    body: JSON.stringify({
      name: data.name,
      type: data.aspectRatio || data.type, // Use aspectRatio (16:9, 1:1) not MIME type
      file_url: data.fileUrl,
      file_data: data.fileData || data.thumbnail, // Support both fileData and thumbnail
      status: data.status || 'pending',
      notes: data.notes,
      sponsor_id: data.sponsorId,
      sponsor_name: data.sponsorName,
      sponsor_email: data.sponsorEmail,
    }),
  }),
  
  update: (id, data) => apiCall(`/assets/${id}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: data.name,
      type: data.type,
      file_url: data.fileUrl,
      status: data.status,
      notes: data.notes,
    }),
  }),
  
  approve: (id) => apiCall(`/assets/${id}/approve`, { method: 'POST' }),
  
  reject: (id) => apiCall(`/assets/${id}/reject`, { method: 'POST' }),
  
  requestRevision: (id, notes) => apiCall(`/assets/${id}/revision?notes=${encodeURIComponent(notes)}`, { method: 'POST' }),
  
  setPreferred: (id) => apiCall(`/assets/${id}/set-preferred`, { method: 'POST' }),
  
  unsetPreferred: (id) => apiCall(`/assets/${id}/unset-preferred`, { method: 'POST' }),
  
  getPreferred: (email) => apiCall(`/assets/preferred/${encodeURIComponent(email)}`),
  
  delete: (id) => apiCall(`/assets/${id}`, { method: 'DELETE' }),
};

// ============ SUBSCRIPTIONS ============
export const subscriptionsApi = {
  getAll: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiCall(`/subscriptions${query ? `?${query}` : ''}`);
  },
  
  getActive: (userId) => apiCall(`/subscriptions/user/${userId}/active`),
  
  getById: (id) => apiCall(`/subscriptions/${id}`),
  
  create: (data) => apiCall('/subscriptions', {
    method: 'POST',
    body: JSON.stringify({
      user_id: data.userId,
      package_id: data.packageId,
      package_name: data.packageName,
      price: data.price,
      status: data.status || 'active',
    }),
  }),
  
  cancel: (id) => apiCall(`/subscriptions/${id}/cancel`, { method: 'POST' }),
};

// ============ ACCOUNTS ============
export const accountsApi = {
  getAll: () => apiCall('/accounts'),
  
  getUnlinked: () => apiCall('/accounts/unlinked'),
  
  getById: (id) => apiCall(`/accounts/${id}`),
  
  register: (data) => apiCall('/accounts', {
    method: 'POST',
    body: JSON.stringify({
      email: data.email,
      business_name: data.businessName,
      contact_name: data.contactName,
      phone: data.phone,
      website: data.website,
      zip_code: data.zipCode,
      password_hash: data.password, // Will be hashed on server
    }),
  }),
  
  login: (email, password) => apiCall(`/accounts/login?email=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`, {
    method: 'POST',
  }),
  
  adminCreate: (data) => apiCall('/accounts/admin-create', {
    method: 'POST',
    body: JSON.stringify({
      email: data.email,
      business_name: data.businessName,
      contact_name: data.contactName,
      phone: data.phone,
      website: data.website,
      zip_code: data.zipCode,
    }),
  }),
  
  updateProfile: (email, data) => apiCall(`/accounts/profile/${encodeURIComponent(email)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  
  getZipStatus: (email) => apiCall(`/accounts/profile/${encodeURIComponent(email)}/zip-status`),
  
  resetPassword: (email, currentPassword, newPassword) => apiCall(
    `/accounts/reset-password?email=${encodeURIComponent(email)}&current_password=${encodeURIComponent(currentPassword)}&new_password=${encodeURIComponent(newPassword)}`,
    { method: 'POST' }
  ),
  
  linkGoogle: (email, googleId) => apiCall(
    `/accounts/link-google?email=${encodeURIComponent(email)}${googleId ? `&google_id=${encodeURIComponent(googleId)}` : ''}`,
    { method: 'POST' }
  ),
  
  checkStatus: (email) => apiCall(`/accounts/check-status/${encodeURIComponent(email)}`),
  
  delete: (id) => apiCall(`/accounts/${id}`, { method: 'DELETE' }),
};

// ============ PROFILE ============
export const profileApi = {
  get: (email) => apiCall(`/profile/${encodeURIComponent(email)}`),
  
  update: (email, data) => apiCall(`/profile/${encodeURIComponent(email)}`, {
    method: 'PUT',
    body: JSON.stringify({
      name: data.name,
      business_name: data.businessName,
      phone: data.phone,
      website: data.website,
      picture: data.picture,
    }),
  }),
  
  updatePicture: (email, picture) => apiCall(`/profile/${encodeURIComponent(email)}/picture`, {
    method: 'PUT',
    body: JSON.stringify({ picture }),
  }),
  
  removePicture: (email) => apiCall(`/profile/${encodeURIComponent(email)}/picture`, {
    method: 'DELETE',
  }),
};

// ============ INIT ============
export const initDatabase = () => apiCall('/init', { method: 'POST' });

// Helper to convert API response to frontend format
export const transformSponsor = (apiSponsor) => ({
  id: apiSponsor.id,
  businessName: apiSponsor.business_name,
  email: apiSponsor.email,
  contactName: apiSponsor.contact_name,
  phone: apiSponsor.phone,
  website: apiSponsor.website,
  zipCode: apiSponsor.zip_code,
  package: apiSponsor.package,
  status: apiSponsor.status,
  notes: apiSponsor.notes,
  logo: apiSponsor.logo,
  picture: apiSponsor.picture,
  isVenueSponsor: apiSponsor.is_venue_sponsor,
  assetsCount: apiSponsor.assets_count,
  joinedAt: apiSponsor.joined_at,
  userId: apiSponsor.user_id,
});

export const transformLocation = (apiLocation) => ({
  id: apiLocation.id,
  name: apiLocation.name,
  address: apiLocation.address,
  city: apiLocation.city,
  state: apiLocation.state,
  zip: apiLocation.zip_code,
  capacityTier: apiLocation.capacity_tier || '> 50',
  status: apiLocation.status,
  dayOfWeek: apiLocation.day_of_week,
  time: apiLocation.time,
  contactName: apiLocation.contact_name,
  contactPhone: apiLocation.contact_phone,
  notes: apiLocation.notes,
});

export const transformAsset = (apiAsset) => ({
  id: apiAsset.id,
  name: apiAsset.name,
  type: apiAsset.type,
  aspectRatio: apiAsset.type, // Map type to aspectRatio for compatibility
  fileUrl: apiAsset.file_url,
  fileData: apiAsset.file_data,
  thumbnail: apiAsset.file_data || apiAsset.thumbnail, // Use file_data as thumbnail
  status: apiAsset.status,
  notes: apiAsset.notes,
  sponsorId: apiAsset.sponsor_id,
  sponsorName: apiAsset.sponsor_name,
  sponsorEmail: apiAsset.sponsor_email,
  uploadedAt: apiAsset.uploaded_at,
  assetName: apiAsset.asset_name || apiAsset.name,
  isPreferred: apiAsset.is_preferred || false,
});

export const transformAccount = (apiAccount) => ({
  id: apiAccount.id,
  email: apiAccount.email,
  businessName: apiAccount.business_name,
  contactName: apiAccount.contact_name,
  phone: apiAccount.phone,
  website: apiAccount.website,
  registeredAt: apiAccount.registered_at,
  userId: apiAccount.user_id,
});

export const transformSubscription = (apiSub) => ({
  id: apiSub.id,
  userId: apiSub.user_id,
  packageId: apiSub.package_id,
  packageName: apiSub.package_name,
  price: apiSub.price,
  status: apiSub.status,
  purchasedAt: apiSub.purchased_at,
  startDate: apiSub.start_date,
  endDate: apiSub.end_date,
});

// ============ CANVA INTEGRATION ============
export const canvaApi = {
  // Get Canva connection status
  getStatus: () => apiCall('/canva/status'),
  
  // Initiate OAuth flow - returns auth_url to redirect to
  // Backend handles callback and redirects back to /admin/settings
  initiateAuth: () => apiCall('/canva/auth'),
  
  // Disconnect Canva integration
  disconnect: () => apiCall('/canva/disconnect', { method: 'POST' }),
  
  // Trigger manual sync
  triggerSync: () => apiCall('/canva/sync', { method: 'POST' }),
  
  // Get sync logs
  getSyncLogs: (limit = 10) => apiCall(`/canva/sync-logs?limit=${limit}`),
  
  // Get count of assets pending sync
  getPendingSyncCount: () => apiCall('/canva/pending-sync-count'),
};

// ============ SPONSOR PLACEMENTS ============
export const placementsApi = {
  // Get all placement types
  getPlacementTypes: () => apiCall('/placements/placement-types'),
  
  // Get full placement matrix for a sponsor
  getMatrix: (sponsorId) => apiCall(`/placements/matrix/${sponsorId}`),
  
  // Update a single placement cell
  updatePlacement: (sponsorId, locationId, placementType, enabled) => 
    apiCall(`/placements/matrix/${sponsorId}?location_id=${locationId}&placement_type=${placementType}&enabled=${enabled}`, {
      method: 'PUT',
    }),
  
  // Bulk update placements
  bulkUpdate: (sponsorId, placements) => 
    apiCall(`/placements/matrix/${sponsorId}/bulk`, {
      method: 'POST',
      body: JSON.stringify(placements),
    }),
  
  // Select all for a location
  selectAllForLocation: (sponsorId, locationId, enabled = true) =>
    apiCall(`/placements/matrix/${sponsorId}/select-all-location/${locationId}?enabled=${enabled}`, {
      method: 'POST',
    }),
  
  // Select all for a placement type
  selectAllForPlacementType: (sponsorId, placementType, enabled = true) =>
    apiCall(`/placements/matrix/${sponsorId}/select-all-placement/${placementType}?enabled=${enabled}`, {
      method: 'POST',
    }),
  
  // Get enabled placements for a sponsor
  getEnabledPlacements: (sponsorId) => apiCall(`/placements/sponsor/${sponsorId}/enabled`),
};

// ============ SHAREPOINT INTEGRATION ============
export const sharePointApi = {
  // Get SharePoint connection status
  getStatus: () => apiCall('/sharepoint/status'),
  
  // Trigger manual sync to SharePoint (all sponsors)
  triggerSync: (syncType = 'all') => apiCall(`/sharepoint/sync?sync_type=${syncType}`, { method: 'POST' }),
  
  // Trigger venue sponsors sync only (slide 2)
  triggerVenueSync: () => apiCall('/sharepoint/sync?sync_type=venue', { method: 'POST' }),
  
  // Trigger advertising sponsors sync only (slide 3)
  triggerAdvertisingSync: () => apiCall('/sharepoint/sync/advertising', { method: 'POST' }),
  
  // Trigger sync for a single sponsor
  triggerSponsorSync: (sponsorId) => apiCall(`/sharepoint/sync/sponsor/${sponsorId}`, { method: 'POST' }),
  
  // Upload a specific asset to SharePoint
  uploadAsset: (assetId) => apiCall(`/sharepoint/upload-asset/${assetId}`, { method: 'POST' }),
  
  // Get sync logs
  getSyncLogs: (limit = 10) => apiCall(`/sharepoint/sync-logs?limit=${limit}`),
  
  // Get location to folder mapping
  getLocationMapping: () => apiCall('/sharepoint/location-mapping'),
  
  // Update location to folder mapping
  updateLocationMapping: (mapping) => apiCall('/sharepoint/location-mapping', {
    method: 'POST',
    body: JSON.stringify(mapping),
  }),
  
  // List SharePoint folder contents
  listFolder: (folderPath) => apiCall(`/sharepoint/folders/${encodeURIComponent(folderPath)}`),
};

// ============ PAYMENTS (STRIPE) ============
export const paymentsApi = {
  // Get Stripe publishable key (never stored in frontend)
  getConfig: () => apiCall('/payments/config'),
  
  // Get available sponsorship packages
  getPackages: () => apiCall('/payments/packages'),
  
  // Create a checkout session for purchasing a package
  createCheckoutSession: (packageId, userEmail, discountCode = null) => apiCall('/payments/checkout/session', {
    method: 'POST',
    body: JSON.stringify({
      package_id: packageId,
      origin_url: window.location.origin,
      user_email: userEmail,
      discount_code: discountCode,
    }),
  }),
  
  // Validate a discount code (includes AZ zip code check for local discounts)
  validateDiscountCode: (code, userEmail = null, packageId = null) => {
    const params = new URLSearchParams({ code });
    if (userEmail) params.append('user_email', userEmail);
    if (packageId) params.append('package_id', packageId);
    return apiCall(`/payments/discount/validate?${params.toString()}`);
  },
  
  // Get checkout session status
  getCheckoutStatus: (sessionId) => apiCall(`/payments/checkout/status/${sessionId}`),
  
  // Get user's active subscription
  getSubscription: (userEmail) => apiCall(`/payments/subscription/${encodeURIComponent(userEmail)}`),
  
  // Upgrade or downgrade subscription
  upgradeDowngrade: (newPackageId, userEmail) => apiCall('/payments/upgrade-downgrade', {
    method: 'POST',
    body: JSON.stringify({
      new_package_id: newPackageId,
      origin_url: window.location.origin,
      user_email: userEmail,
    }),
  }),
  
  // Cancel subscription
  cancelSubscription: (userEmail) => apiCall(`/payments/cancel/${encodeURIComponent(userEmail)}`, {
    method: 'POST',
  }),
  
  // Get payment history
  getPaymentHistory: (userEmail, limit = 10) => 
    apiCall(`/payments/history/${encodeURIComponent(userEmail)}?limit=${limit}`),
};

// ============ ACCOUNT DELETION ============
export const accountDeletionApi = {
  // Request account deletion (sends confirmation email)
  requestDeletion: (email) => apiCall('/account-deletion/request', {
    method: 'POST',
    body: JSON.stringify({ email }),
  }),
  
  // Confirm deletion (called from email link)
  confirmDeletion: (token) => apiCall('/account-deletion/confirm', {
    method: 'POST',
    body: JSON.stringify({ token }),
  }),
  
  // Get deletion request status
  getDeletionStatus: (token) => apiCall(`/account-deletion/status/${token}`),
};
