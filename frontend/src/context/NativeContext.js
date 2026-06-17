import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

// Native install builds compile with REACT_APP_BACKEND_URL="" so all API
// calls are relative to the page origin (127.0.0.1:8001). When this is
// empty we KNOW we're inside a desktop install — see v31.0.10 fix.
const IS_NATIVE_BUILD = !API;

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
    // Retry up to 5x with linear backoff. Desktop launcher takes ~2-3s to
    // start the backend so the first React fetch can race the listener.
    let lastErr = null;
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        const { data } = await axios.get(`${API}/api/native/info`, { timeout: 4000 });
        setInfo(data);
        setError(null);
        setLoading(false);
        return data;
      } catch (e) {
        lastErr = e;
        if (attempt < 4) {
          await new Promise((res) => setTimeout(res, 500 + attempt * 500));
        }
      }
    }
    // v31.0.10 hardening: never fail-open in a way that skips Setup.
    // Two distinct failure modes:
    //  1. Native install (relative-URL build) and backend really is down →
    //     user MUST see a connection error, not be dropped at /login.
    //  2. Webapp build hitting the cloud API → fall back to non-native mode
    //     (this is the original cloud-only behaviour for api.bighat.live).
    setError(lastErr?.message || 'Failed to load native info');
    if (IS_NATIVE_BUILD) {
      // Stay in `loading: true` + `error: set`. NativeGate will render the
      // backend-connection error screen instead of redirecting anywhere.
      setLoading(true);
    } else {
      setInfo({ native_mode: false, setup_complete: true, license: {}, subscription: {} });
      setLoading(false);
    }
    return null;
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
    // Exposed so NativeGate can render a connection-error screen distinct
    // from the normal "starting up" loading state.
    isNativeBuild: IS_NATIVE_BUILD,
  };

  return <NativeContext.Provider value={value}>{children}</NativeContext.Provider>;
}

export function useNative() {
  const ctx = useContext(NativeContext);
  if (!ctx) throw new Error('useNative must be inside NativeProvider');
  return ctx;
}
