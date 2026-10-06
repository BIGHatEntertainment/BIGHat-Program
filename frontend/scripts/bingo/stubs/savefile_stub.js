// test stand-in for lib/saveFile: records what the screen asked to save (the real one needs the desktop window)
export async function saveBlob(blob, filename) {
  globalThis.__saved = { name: filename, size: blob.size };
  return globalThis.__saveResult || { ok: true, path: 'C:\\Users\\Me\\Downloads\\' + filename };
}
