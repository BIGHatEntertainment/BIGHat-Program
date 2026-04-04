import React, { useMemo } from 'react';
import QRCode from 'qrcode';

const DARK = '#0a1e3d';
const MODULE_SIZE = 5;
const QUIET_ZONE = 2; // modules of padding

/**
 * Generate QR matrix (2D boolean array) synchronously.
 */
const getMatrix = (url) => {
  try {
    const qr = QRCode.create(url, { errorCorrectionLevel: 'H' });
    const size = qr.modules.size;
    const data = qr.modules.data;
    const matrix = [];
    for (let r = 0; r < size; r++) {
      const row = [];
      for (let c = 0; c < size; c++) {
        row.push(data[r * size + c] ? 1 : 0);
      }
      matrix.push(row);
    }
    return matrix;
  } catch {
    return [];
  }
};

/**
 * Check if a module is part of a finder pattern (the 3 big corner squares).
 * Finder patterns occupy a 7x7 area in each of the 3 corners.
 */
const isFinderModule = (r, c, size) => {
  // Top-left
  if (r < 7 && c < 7) return true;
  // Top-right
  if (r < 7 && c >= size - 7) return true;
  // Bottom-left
  if (r >= size - 7 && c < 7) return true;
  return false;
};

/**
 * Render a single rounded finder pattern at given origin.
 */
const renderFinder = (ox, oy, m) => {
  const s = m; // module size
  const elements = [];
  // Outer rounded square (7x7) - dark border
  elements.push(
    <rect key={`fo-${ox}-${oy}`}
      x={ox} y={oy} width={7 * s} height={7 * s}
      rx={s * 1.4} ry={s * 1.4} fill={DARK} />
  );
  // Inner white (5x5)
  elements.push(
    <rect key={`fi-${ox}-${oy}`}
      x={ox + s} y={oy + s} width={5 * s} height={5 * s}
      rx={s * 1} ry={s * 1} fill="#FFFFFF" />
  );
  // Center dark (3x3)
  elements.push(
    <rect key={`fc-${ox}-${oy}`}
      x={ox + 2 * s} y={oy + 2 * s} width={3 * s} height={3 * s}
      rx={s * 0.6} ry={s * 0.6} fill={DARK} />
  );
  return elements;
};

/**
 * StyledQRCode — Horizontal bar pattern with rounded finder corners.
 * Produces a scannable QR code similar to Bitly's style.
 */
const StyledQRCode = ({ url, size = 200 }) => {
  const svgContent = useMemo(() => {
    const matrix = getMatrix(url);
    if (!matrix.length) return null;

    const n = matrix.length;
    const m = MODULE_SIZE;
    const pad = QUIET_ZONE * m;
    const totalSize = n * m + pad * 2;
    const r = m * 0.4; // pill corner radius
    const elements = [];

    // 1) Render data modules as horizontal pills (skip finder areas)
    for (let row = 0; row < n; row++) {
      let col = 0;
      while (col < n) {
        // Skip light modules
        if (!matrix[row][col] || isFinderModule(row, col, n)) {
          col++;
          continue;
        }
        // Start of a dark horizontal run
        const startCol = col;
        while (col < n && matrix[row][col] && !isFinderModule(row, col, n)) {
          col++;
        }
        const runLen = col - startCol;
        const x = pad + startCol * m;
        const y = pad + row * m;
        const w = runLen * m;
        const h = m;

        elements.push(
          <rect key={`d-${row}-${startCol}`}
            x={x} y={y + 0.5} width={w} height={h - 1}
            rx={r} ry={r} fill={DARK} />
        );
      }
    }

    // 2) Render finder patterns with rounded corners
    const finders = [
      [pad, pad],                           // top-left
      [pad + (n - 7) * m, pad],            // top-right
      [pad, pad + (n - 7) * m],            // bottom-left
    ];
    const finderEls = finders.flatMap(([fx, fy]) => renderFinder(fx, fy, m));

    return { elements, finderEls, totalSize };
  }, [url]);

  if (!svgContent) return null;

  const { elements, finderEls, totalSize } = svgContent;
  const scale = size / totalSize;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="rounded-2xl border-[3px] border-[#0a1e3d] p-2 bg-white">
        <svg
          viewBox={`0 0 ${totalSize} ${totalSize}`}
          width={size}
          height={size}
          xmlns="http://www.w3.org/2000/svg"
        >
          <rect x="0" y="0" width={totalSize} height={totalSize} fill="#FFFFFF" />
          {elements}
          {finderEls}
          {/* Logo in center */}
          <defs>
            <clipPath id="logoClip">
              <circle cx={totalSize / 2} cy={totalSize / 2} r={totalSize * 0.09} />
            </clipPath>
          </defs>
          <circle cx={totalSize / 2} cy={totalSize / 2} r={totalSize * 0.1} fill="#FFFFFF" />
          <image
            href="/hat-logo.png"
            x={totalSize / 2 - totalSize * 0.08}
            y={totalSize / 2 - totalSize * 0.08}
            width={totalSize * 0.16}
            height={totalSize * 0.16}
            clipPath="url(#logoClip)"
          />
        </svg>
      </div>
      <span className="text-white/60 text-xs font-sans">Scan to download on mobile</span>
    </div>
  );
};

export default StyledQRCode;
