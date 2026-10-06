export const toast = (...a) => { (globalThis.__toasts ||= []).push(a); };
