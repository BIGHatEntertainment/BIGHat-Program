// test stub for lib/audienceWindow: records what the page asks for, and can be made to fail
export const isTauri = () => !!globalThis.__fakeTauri;
export async function openNativeAudience(opts) {
  (globalThis.__nativeOpens ||= []).push(opts);
  if (globalThis.__nativeFails) throw new Error(globalThis.__nativeFails);
  const win = { setFocus() { (globalThis.__nativeFocus ||= []).push(opts.label); }, close() { (globalThis.__nativeClosed ||= []).push(opts.label); } };
  return { win, native: true, reused: false };
}
