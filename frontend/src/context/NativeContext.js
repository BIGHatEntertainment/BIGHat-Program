import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const NativeContext = createContext(null);

/**
 * Provides native-standalone runtime info to the rest of the app:
 *  - native_mode: env-flagged on the backend
 *  - setup_complete: false on first boot → forces SetupWizard
 *  - license: { is_active, used_seats, seats_remaining, current_hwid_registered, key_masked }
 *  - subscription: { active, tier, sharepoint_enabled, story_generator_enabled, cloud_sync_enabled }
 *  - settings, paths, current_hwid, instance_id
 *
 * `refresh()` re-fetches /api/native/info; call after setup-init or subscription change.
 */
export function NativeProvider({ children }) {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/api/native/info`);
      setInfo(data);
      setError(null);
      return data;
    } catch (e) {
      setError(e.message || 'Failed to load native info');
      // Fail-open: behave as non-native webapp if endpoint is unreachable.
      setInfo({ native_mode: false, setup_complete: true, license: {}, subscription: {} });
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const isPremiumActive = useCallback(
    (feature) => {
      const sub = info?.subscription;
      if (!sub?.active) return false;
      if (!feature) return true;
      return Boolean(sub[feature]);
    },
    [info],
  );

  const value = {
    info,
    loading,
    error,
    refresh,
    isPremiumActive,
    nativeMode: Boolean(info?.native_mode),
    setupComplete: info ? Boolean(info.setup_complete) : true,
    license: info?.license || {},
    subscription: info?.subscription || {},
    settings: info?.settings || {},
    currentHwid: info?.current_hwid || '',
  };

  return <NativeContext.Provider value={value}>{children}</NativeContext.Provider>;
}

export function useNative() {
  const ctx = useContext(NativeContext);
  if (!ctx) throw new Error('useNative must be inside NativeProvider');
  return ctx;
}
