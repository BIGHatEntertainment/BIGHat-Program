import axios from 'axios';

// alpha.82: a phone can't open the PC's own address, so the stored video is put on the QR relay
// (api.bighat.live) and the QR points at that link.
// Returns { url, message }: url is the link for the QR, or null with a plain reason for the host.
export async function publishStoryQr(API, fileId) {
  try {
    const r = await axios.post(`${API}/story-generator/qr-publish/${fileId}`, {}, { timeout: 180000 });
    if (r.data && r.data.success && r.data.url) return { url: r.data.url, message: null };
    return { url: null, message: (r.data && r.data.message) || 'The QR code is not available right now.' };
  } catch (e) {
    return { url: null, message: 'The QR code is not available right now.' };
  }
}
