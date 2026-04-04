import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Download, Loader2, CheckCircle, AlertCircle, RefreshCw, Video } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Progress } from '../../../components/ui/progress';
import { SECTION_DURATIONS } from './VideoPreview';
import StyledQRCode from './StyledQRCode';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';
const VIDEO_WIDTH = 1080;
const VIDEO_HEIGHT = 1920;

export const VideoEncoder = ({ event, onComplete, onError }) => {
  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [qrDownloadUrl, setQrDownloadUrl] = useState(null);

  const loadImage = (src) => {
    if (!src) return Promise.resolve(null);
    return new Promise(resolve => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = src;
    });
  };

  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  const generateVideo = async () => {
    if (!event) return;

    try {
      setStatus('encoding');

      // ===== STEP 1: Fetch assets =====
      setMessage('Fetching images...');
      setProgress(5);

      let assets = {};
      try {
        const res = await axios.post(`${API_URL}/api/story-generator/build-asset-urls`, {
          location: event.venue || event.location?.name || '',
          locationFolder: event.location?.folder || '',
          host: event.host?.name || '',
          numRounds: event.rounds?.length || 5
        }, { timeout: 30000 });
        assets = res.data?.assets || {};
      } catch (e) {
        console.warn('[VideoEncoder] Asset fetch failed:', e.message);
      }

      // Pre-load all images
      const [locImg, hostImg, bgImg] = await Promise.all([
        loadImage(assets.locationUrl),
        loadImage(assets.hostUrl),
        loadImage(assets.backgroundUrl)
      ]);
      setProgress(15);

      // ===== STEP 2: Setup canvas + recorder =====
      setMessage('Starting recording...');
      const canvas = document.createElement('canvas');
      canvas.width = VIDEO_WIDTH;
      canvas.height = VIDEO_HEIGHT;
      const ctx = canvas.getContext('2d');

      const stream = canvas.captureStream(0);
      const videoTrack = stream.getVideoTracks()[0];
      const chunks = [];
      const mimeTypes = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
      let mime = 'video/webm';
      for (const m of mimeTypes) { if (MediaRecorder.isTypeSupported(m)) { mime = m; break; } }

      const recorder = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 4000000 });
      recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };

      const recordingDone = new Promise(resolve => { recorder.onstop = () => resolve(); });
      recorder.start(500);

      // Force 30fps frame capture — requestFrame tells the browser "this is a new frame"
      const frameInterval = setInterval(() => {
        if (videoTrack.requestFrame) videoTrack.requestFrame();
      }, 33);

      // ===== STEP 3: Draw Location (3s) =====
      setMessage('Recording location (3s)...');
      setProgress(20);
      if (locImg) {
        ctx.drawImage(locImg, 0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);
      } else {
        ctx.fillStyle = '#0a1e3d';
        ctx.fillRect(0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);
        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 48px Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(event.venue || 'Location', VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2);
      }
      await wait(SECTION_DURATIONS.location * 1000);
      setProgress(35);
      setMessage('✓ Location done');

      // ===== STEP 4: Draw Host (3s) =====
      setMessage('Recording host (3s)...');
      setProgress(40);
      if (hostImg) {
        ctx.drawImage(hostImg, 0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);
      } else {
        ctx.fillStyle = '#0a0a2e';
        ctx.fillRect(0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);
        ctx.fillStyle = '#FFFFFF';
        ctx.font = 'bold 48px Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(event.host?.name || 'Host', VIDEO_WIDTH / 2, VIDEO_HEIGHT / 2);
      }
      await wait(SECTION_DURATIONS.host * 1000);
      setProgress(55);
      setMessage('✓ Host done');

      // ===== STEP 5: Draw Rounds (19s) =====
      setMessage('Recording rounds (19s)...');
      setProgress(58);

      // Background
      if (bgImg) {
        ctx.drawImage(bgImg, 0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);
      } else {
        const grad = ctx.createLinearGradient(0, 0, 0, VIDEO_HEIGHT);
        grad.addColorStop(0, '#0a1e3d');
        grad.addColorStop(0.5, '#1a0a3d');
        grad.addColorStop(1, '#0a1e3d');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);
      }
      ctx.fillStyle = 'rgba(0,0,0,0.5)';
      ctx.fillRect(0, 0, VIDEO_WIDTH, VIDEO_HEIGHT);

      // Round boxes
      const rounds = event.rounds || [];
      const boxW = 600, boxH = 70;
      const gap = rounds.length >= 6 ? 80 : 120;
      const boxX = (VIDEO_WIDTH - boxW) / 2;
      const totalH = rounds.length * boxH + (rounds.length - 1) * gap;
      const startY = (VIDEO_HEIGHT - totalH) / 2 + 50;

      ctx.font = 'bold 42px Arial, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      rounds.forEach((round, i) => {
        const y = startY + i * (boxH + gap);
        const r = 12;
        ctx.fillStyle = round.color || '#FF6B6B';
        ctx.beginPath();
        ctx.moveTo(boxX + r, y);
        ctx.lineTo(boxX + boxW - r, y);
        ctx.quadraticCurveTo(boxX + boxW, y, boxX + boxW, y + r);
        ctx.lineTo(boxX + boxW, y + boxH - r);
        ctx.quadraticCurveTo(boxX + boxW, y + boxH, boxX + boxW - r, y + boxH);
        ctx.lineTo(boxX + r, y + boxH);
        ctx.quadraticCurveTo(boxX, y + boxH, boxX, y + boxH - r);
        ctx.lineTo(boxX, y + r);
        ctx.quadraticCurveTo(boxX, y, boxX + r, y);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = '#000000';
        ctx.fillText(round.name, VIDEO_WIDTH / 2, y + boxH / 2);
      });

      await wait(SECTION_DURATIONS.rounds * 1000);
      setProgress(80);
      setMessage('✓ All sections recorded');

      // ===== STEP 6: Stop recorder =====
      clearInterval(frameInterval);
      recorder.stop();
      await recordingDone;
      
      const webmBlob = new Blob(chunks, { type: mime });
      console.log(`[VideoEncoder] WebM: ${(webmBlob.size / 1024 / 1024).toFixed(1)}MB`);

      // ===== STEP 7: Convert to MP4 on server =====
      setMessage('Converting to MP4...');
      setProgress(82);

      const webmBase64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(webmBlob);
      });

      setProgress(85);

      const convertRes = await axios.post(`${API_URL}/api/story-generator/convert-webm`, {
        video_data: webmBase64,
        filename: `story_${Date.now()}`
      }, { timeout: 120000, maxContentLength: Infinity, maxBodyLength: Infinity });

      if (!convertRes.data.success) throw new Error(convertRes.data.detail || 'Conversion failed');

      setProgress(95);
      setMessage('Preparing download...');

      const mp4Base64 = convertRes.data.video_data;
      const mp4Resp = await fetch(mp4Base64);
      const mp4Blob = await mp4Resp.blob();
      const mp4Url = URL.createObjectURL(mp4Blob);

      // QR store
      try {
        const storeRes = await axios.post(`${API_URL}/api/story-generator/store-temp`, {
          video_data: mp4Base64,
          filename: convertRes.data.filename?.replace('.mp4', '') || `story_${Date.now()}`
        }, { timeout: 30000 });
        if (storeRes.data.success) {
          setQrDownloadUrl(`${API_URL}/api/story-generator/qr-download/${storeRes.data.file_id}`);
        }
      } catch (qrErr) {
        console.warn('[VideoEncoder] QR store failed:', qrErr);
      }

      setProgress(100);
      setMessage('MP4 video ready for download! ✓');
      setDownloadUrl({ url: mp4Url, type: 'video/mp4', filename: convertRes.data.filename });
      setStatus('complete');
      if (onComplete) onComplete(mp4Url);

    } catch (error) {
      console.error('Video generation error:', error);
      setStatus('error');
      setMessage(error.response?.data?.detail || error.message || 'Failed to generate video');
      if (onError) onError(error);
    }
  };

  const handleDownload = () => {
    if (!downloadUrl) return;
    const a = document.createElement('a');
    a.href = downloadUrl.url;
    a.download = `${event.name.replace(/[^a-z0-9]/gi, '_')}_story.mp4`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const resetState = () => {
    if (downloadUrl) URL.revokeObjectURL(downloadUrl.url);
    setStatus('idle');
    setDownloadUrl(null);
    setQrDownloadUrl(null);
    setProgress(0);
    setMessage('');
  };

  return (
    <div className="space-y-4" data-testid="video-encoder">
      {status === 'idle' && (
        <Button onClick={generateVideo} disabled={!event}
          className="w-full rounded-full font-sans font-medium py-6 bg-yellow-500 hover:bg-yellow-600 text-black">
          <Video className="h-5 w-5 mr-2" /> Generate Video
        </Button>
      )}

      {(status === 'loading' || status === 'capturing' || status === 'encoding') && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
          <div className="flex items-center gap-3">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="font-sans text-sm text-white">{message}</span>
          </div>
          <Progress value={progress} className="h-3" />
          <div className="flex justify-between text-xs font-mono">
            <span className="text-white/60">Encoding</span>
            <span className="text-yellow-400">{progress}%</span>
          </div>
        </motion.div>
      )}

      {status === 'complete' && (
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="space-y-3">
          <div className="flex items-center gap-3 text-emerald-400">
            <CheckCircle className="h-5 w-5" />
            <span className="font-sans text-sm">{message}</span>
          </div>
          <div className="flex gap-3 items-start">
            {downloadUrl && (
              <div className="flex-1 rounded-lg overflow-hidden bg-black/50 p-2">
                <video src={downloadUrl.url} controls className="w-full max-h-[200px] rounded" />
              </div>
            )}
            {qrDownloadUrl && (
              <div className="flex-shrink-0"><StyledQRCode url={qrDownloadUrl} size={180} /></div>
            )}
          </div>
          <Button onClick={handleDownload}
            className="w-full rounded-full bg-emerald-500 hover:bg-emerald-600 font-sans font-medium py-6">
            <Download className="h-5 w-5 mr-2" /> Download Video
          </Button>
        </motion.div>
      )}

      {status === 'error' && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
          <div className="flex items-center gap-3 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span className="font-sans text-sm">{message}</span>
          </div>
          <Button variant="outline" onClick={resetState} className="w-full rounded-full">
            <RefreshCw className="h-4 w-4 mr-2" /> Try Again
          </Button>
        </motion.div>
      )}

      <p className="text-xs text-muted-foreground text-center font-sans">
        MP4 format for Instagram Stories. ~25s video.
      </p>
    </div>
  );
};

export default VideoEncoder;
