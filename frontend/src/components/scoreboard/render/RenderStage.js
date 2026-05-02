import React, { useRef, useEffect, useState } from 'react';
import html2canvas from 'html2canvas';

/**
 * RenderStage: Fixed-pixel container that scales to fit preview,
 * but renders at exact pixel size for export.
 * 
 * KEY: Before export, we temporarily remove CSS scale so html2canvas
 * captures the full-size 1080x1920 (or 1920x1080) content.
 */
const RenderStage = ({ 
  aspectRatio = 'landscape', 
  children, 
  isLiveView = false,
  className = ''
}) => {
  const stageRef = useRef(null);
  const containerRef = useRef(null);
  const [scale, setScale] = useState(1);

  const dimensions = aspectRatio === 'portrait' 
    ? { width: 1080, height: 1920 } 
    : { width: 1920, height: 1080 };

  useEffect(() => {
    if (isLiveView) { setScale(1); return; }
    const updateScale = () => {
      if (!containerRef.current) return;
      const r = containerRef.current.getBoundingClientRect();
      setScale(Math.min(r.width / dimensions.width, r.height / dimensions.height, 1));
    };
    updateScale();
    window.addEventListener('resize', updateScale);
    return () => window.removeEventListener('resize', updateScale);
  }, [dimensions.width, dimensions.height, isLiveView]);

  /**
   * Temporarily unscale the stage, capture to canvas, then restore.
   * This ensures we capture at FULL 1080x1920 resolution.
   */
  const captureToCanvas = async () => {
    const el = stageRef.current;
    if (!el) return null;
    
    // Save current transform — unscale to full size but keep in DOM flow
    const origTransform = el.style.transform;
    const origTransformOrigin = el.style.transformOrigin;
    
    // Set to scale(1) so html2canvas captures at full resolution
    // Keep element in its container (visible) — moving offscreen causes blank captures
    el.style.transform = 'none';
    el.style.transformOrigin = 'top left';
    
    // Wait for repaint
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    
    try {
      const canvas = await html2canvas(el, {
        width: dimensions.width,
        height: dimensions.height,
        scale: 1,
        useCORS: true,
        allowTaint: true,
        backgroundColor: '#07070E',
        logging: false,
        windowWidth: dimensions.width,
        windowHeight: dimensions.height,
      });
      return canvas;
    } finally {
      // Restore original styles
      el.style.transform = origTransform;
      el.style.transformOrigin = origTransformOrigin;
    }
  };

  /**
   * Export as high-res PNG. Captures at full resolution.
   */
  const exportAsPng = async () => {
    const canvas = await captureToCanvas();
    if (!canvas) return null;
    return canvas.toDataURL('image/png');
  };

  /**
   * Export as video. 
   * Strategy: capture frames using html2canvas at ~4-5fps,
   * record canvas stream at 30fps (repeats last frame between captures),
   * then server ffmpeg converts to smooth MP4.
   */
  const exportAsVideo = async (durationMs = 15000) => {
    const el = stageRef.current;
    if (!el) return null;
    
    const W = dimensions.width;
    const H = dimensions.height;
    
    // Create recording canvas at full resolution
    const recCanvas = document.createElement('canvas');
    recCanvas.width = W;
    recCanvas.height = H;
    const recCtx = recCanvas.getContext('2d');
    recCtx.fillStyle = '#07070E';
    recCtx.fillRect(0, 0, W, H);
    
    // Save original styles
    const origTransform = el.style.transform;
    const origPosition = el.style.position;
    const origLeft = el.style.left;
    const origTop = el.style.top;
    
    // Move offscreen at full size for capture
    el.style.transform = 'none';
    el.style.position = 'fixed';
    el.style.left = '-9999px';
    el.style.top = '0px';
    
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    
    try {
      // Start recording at 30fps
      const stream = recCanvas.captureStream(30);
      const recorder = new MediaRecorder(stream, {
        mimeType: 'video/webm;codecs=vp9',
        videoBitsPerSecond: 10000000,
      });
      const chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      
      // Capture first frame
      const firstCanvas = await html2canvas(el, {
        width: W, height: H, scale: 1,
        useCORS: true, allowTaint: true,
        backgroundColor: '#07070E', logging: false,
      });
      recCtx.drawImage(firstCanvas, 0, 0, W, H);
      
      return new Promise((resolve) => {
        recorder.onstop = () => {
          // Restore styles
          el.style.transform = origTransform;
          el.style.position = origPosition;
          el.style.left = origLeft;
          el.style.top = origTop;
          
          const blob = new Blob(chunks, { type: 'video/webm' });
          resolve(URL.createObjectURL(blob));
        };
        
        recorder.start(50); // collect data every 50ms
        const startTime = Date.now();
        
        const captureLoop = async () => {
          const elapsed = Date.now() - startTime;
          if (elapsed >= durationMs) {
            recorder.stop();
            return;
          }
          
          try {
            const frameCanvas = await html2canvas(el, {
              width: W, height: H, scale: 1,
              useCORS: true, allowTaint: true,
              backgroundColor: '#07070E', logging: false,
            });
            recCtx.clearRect(0, 0, W, H);
            recCtx.drawImage(frameCanvas, 0, 0, W, H);
          } catch (e) {
            // Skip frame on error
          }
          
          // Schedule next frame capture immediately (as fast as html2canvas can go)
          setTimeout(captureLoop, 50);
        };
        
        captureLoop();
      });
    } catch (err) {
      // Restore on error
      el.style.transform = origTransform;
      el.style.position = origPosition;
      el.style.left = origLeft;
      el.style.top = origTop;
      console.error('Video export failed:', err);
      return null;
    }
  };

  // Attach to window for Dashboard access
  useEffect(() => {
    window.__renderStage = { exportAsPng, exportAsVideo, stageRef };
    return () => { delete window.__renderStage; };
  });

  if (isLiveView) {
    return (
      <div ref={stageRef} data-testid="render-stage"
        className={`render-stage ${className}`}
        style={{ width: dimensions.width, height: dimensions.height, position: 'relative' }}>
        {children}
      </div>
    );
  }

  return (
    <div ref={containerRef}
      className="relative w-full flex items-center justify-center overflow-hidden bg-gray-900 rounded-xl"
      style={{ aspectRatio: aspectRatio === 'portrait' ? '9/16' : '16/9', maxHeight: '70vh' }}>
      <div ref={stageRef} data-testid="render-stage"
        className={`render-stage export-frame ${className}`}
        style={{
          width: dimensions.width, height: dimensions.height,
          transform: `scale(${scale})`, transformOrigin: 'center center',
          position: 'absolute',
        }}>
        {children}
      </div>
    </div>
  );
};

export { RenderStage };
export default RenderStage;
