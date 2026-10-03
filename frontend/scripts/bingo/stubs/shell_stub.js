export async function open(url) {
  if (globalThis.__shellFail) throw new Error('plugin not available');
  (globalThis.__shellCalls = globalThis.__shellCalls || []).push(url);
}
