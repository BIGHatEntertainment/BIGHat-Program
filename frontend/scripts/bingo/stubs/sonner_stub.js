// test stub for "sonner": records every toast so a check can read what the host was told
const push = (kind) => (...a) => { (globalThis.__toasts ||= []).push([...a, kind]); };
export const toast = Object.assign(push('info'), { error: push('error'), success: push('success'), info: push('info'), warning: push('warning'), message: push('info') });
export const Toaster = () => null;
