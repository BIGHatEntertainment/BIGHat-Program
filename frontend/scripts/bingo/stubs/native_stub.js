// test stand-in for NativeContext: counts refreshes on a global so a test can read it
globalThis.__refreshCalls = globalThis.__refreshCalls || { n: 0 };
export function useNative() { return { refresh: async () => { globalThis.__refreshCalls.n += 1; } }; }
