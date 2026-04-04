import React, { useState, useRef, useCallback, memo } from 'react';
import { Trash2 } from 'lucide-react';

/**
 * Individual canvas element - memoized to prevent re-renders
 */
const CanvasElement = memo(({ 
  element, 
  isSelected, 
  scale,
  onMouseDown, 
  onDoubleClick,
  onResizeStart,
  onDelete,
  getOverlaySrc
}) => {
  const handleMouseDown = useCallback((e) => {
    onMouseDown(e, element);
  }, [onMouseDown, element]);

  const handleDoubleClick = useCallback((e) => {
    onDoubleClick(e, element);
  }, [onDoubleClick, element]);

  const handleResizeStart = useCallback((e) => {
    onResizeStart(e, element);
  }, [onResizeStart, element]);

  const handleDelete = useCallback((e) => {
    e.stopPropagation();
    onDelete(element.id);
  }, [onDelete, element.id]);

  const imageSrc = element.type === 'overlay' ? getOverlaySrc(element) : element.src;

  return (
    <div
      className={`absolute cursor-move select-none ${
        isSelected ? 'ring-2 ring-[#FFC107]' : ''
      }`}
      style={{
        left: `${element.x * scale}px`,
        top: `${element.y * scale}px`,
        width: `${element.width * scale}px`,
        height: `${element.height * scale}px`,
        fontSize: `${(element.fontSize || 16) * scale}px`,
        fontWeight: element.fontWeight,
        color: element.color,
        textAlign: element.textAlign,
        fontFamily: element.fontFamily,
        lineHeight: element.lineHeight || 1.5,
        whiteSpace: 'pre-wrap',
        textShadow: element.textShadow || 'none'
      }}
      onMouseDown={handleMouseDown}
      onDoubleClick={handleDoubleClick}
    >
      {element.type === 'text' && (
        <div 
          className={`w-full h-full flex break-words ${
            element.verticalAlign === 'top' ? 'items-start' : 'items-center'
          } ${
            element.textAlign === 'left' ? 'justify-start' : 
            element.textAlign === 'right' ? 'justify-end' : 'justify-center'
          }`}
          style={{
            overflow: element.overflow || 'visible',
            textOverflow: element.overflow === 'hidden' ? 'ellipsis' : 'clip'
          }}
        >
          {element.content}
        </div>
      )}
      {element.type === 'image' && (
        <img src={element.src} alt="" className="w-full h-full object-contain" />
      )}
      {element.type === 'overlay' && imageSrc && (
        <img src={imageSrc} alt="" className="w-full h-full object-contain" />
      )}
      {element.type === 'overlay' && !imageSrc && (
        <div className="w-full h-full flex items-center justify-center bg-yellow-500/20 border-2 border-dashed border-yellow-500">
          <span className="text-yellow-500 text-sm">Loading overlay...</span>
        </div>
      )}
      {element.type === 'video' && element.videoSrc && (
        <video 
          src={element.videoSrc}
          className="w-full h-full object-contain"
          autoPlay
          loop
          muted
          playsInline
        />
      )}

      {isSelected && (
        <>
          {/* Resize handle */}
          <div
            className="absolute bottom-0 right-0 w-4 h-4 bg-[#FFC107] cursor-se-resize"
            onMouseDown={handleResizeStart}
          />
          {/* Delete button */}
          <button
            className="absolute -top-8 right-0 bg-red-600 hover:bg-red-700 text-white p-1 rounded"
            onClick={handleDelete}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </>
      )}
    </div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison - re-render if these specific props change
  // IMPORTANT: For overlay elements, we need to check if the overlay src changed
  if (prevProps.element.type === 'overlay' && nextProps.element.type === 'overlay') {
    const prevSrc = prevProps.getOverlaySrc(prevProps.element);
    const nextSrc = nextProps.getOverlaySrc(nextProps.element);
    if (prevSrc !== nextSrc) {
      return false; // Force re-render
    }
  }
  
  return (
    prevProps.element === nextProps.element &&
    prevProps.isSelected === nextProps.isSelected &&
    prevProps.scale === nextProps.scale
  );
});

CanvasElement.displayName = 'CanvasElement';

/**
 * Slide canvas - memoized with optimized element rendering
 */
const SlideCanvas = memo(({ 
  slide, 
  selectedElement, 
  onSelectElement, 
  onUpdateElement, 
  onDeleteElement, 
  overlayCache,
  overlayCacheVersion // Used to trigger re-render when overlay cache is populated
}) => {
  const [dragging, setDragging] = useState(null);
  const [resizing, setResizing] = useState(null);
  const canvasRef = useRef(null);
  
  // Scale factor: elements are stored at 1920x1080, canvas displays at 960x540
  const SCALE = 0.5;

  const handleMouseDown = useCallback((e, element) => {
    e.stopPropagation();
    onSelectElement(element);

    const rect = canvasRef.current.getBoundingClientRect();
    const startX = e.clientX - rect.left;
    const startY = e.clientY - rect.top;

    setDragging({
      element,
      offsetX: startX - (element.x * SCALE),
      offsetY: startY - (element.y * SCALE)
    });
  }, [onSelectElement]);

  const handleMouseMove = useCallback((e) => {
    if (dragging) {
      const rect = canvasRef.current.getBoundingClientRect();
      const x = (e.clientX - rect.left - dragging.offsetX) / SCALE;
      const y = (e.clientY - rect.top - dragging.offsetY) / SCALE;

      onUpdateElement({
        ...dragging.element,
        x: Math.max(0, Math.min(x, 1920 - dragging.element.width)),
        y: Math.max(0, Math.min(y, 1080 - dragging.element.height))
      });
    } else if (resizing) {
      const rect = canvasRef.current.getBoundingClientRect();
      const x = (e.clientX - rect.left) / SCALE;
      const y = (e.clientY - rect.top) / SCALE;

      const newWidth = Math.max(50, x - resizing.element.x);
      const newHeight = Math.max(20, y - resizing.element.y);

      onUpdateElement({
        ...resizing.element,
        width: newWidth,
        height: newHeight
      });
    }
  }, [dragging, resizing, onUpdateElement]);

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    setResizing(null);
  }, []);

  const handleDoubleClick = useCallback((e, element) => {
    e.stopPropagation();
    if (element.type === 'text') {
      const newContent = prompt('Edit text:', element.content);
      if (newContent !== null) {
        onUpdateElement({ ...element, content: newContent });
      }
    }
  }, [onUpdateElement]);

  const handleResizeStart = useCallback((e, element) => {
    e.stopPropagation();
    setResizing({ element });
  }, []);

  const handleCanvasClick = useCallback(() => {
    onSelectElement(null);
  }, [onSelectElement]);
  
  // Memoize overlay source getter - depends on overlayCacheVersion to re-compute when cache updates
  const getOverlaySrc = useCallback((element) => {
    if (element.type === 'overlay' && element.overlayId && overlayCache?.current) {
      return overlayCache.current[element.overlayId] || '';
    }
    return element.src || '';
  }, [overlayCache, overlayCacheVersion]);

  return (
    <div
      ref={canvasRef}
      className="relative w-[960px] h-[540px] mx-auto rounded-lg shadow-2xl overflow-hidden cursor-default"
      style={{ background: slide?.background || '#191919' }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onClick={handleCanvasClick}
    >
      {(slide?.elements || []).map((element) => (
        <CanvasElement
          key={element.id}
          element={element}
          isSelected={selectedElement?.id === element.id}
          scale={SCALE}
          onMouseDown={handleMouseDown}
          onDoubleClick={handleDoubleClick}
          onResizeStart={handleResizeStart}
          onDelete={onDeleteElement}
          getOverlaySrc={getOverlaySrc}
        />
      ))}
    </div>
  );
});

SlideCanvas.displayName = 'SlideCanvas';

export default SlideCanvas;
