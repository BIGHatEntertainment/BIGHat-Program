import React, { useState, useRef } from 'react';
import { Trash2 } from 'lucide-react';

const SlideCanvas = ({ slide, selectedElement, onSelectElement, onUpdateElement, onDeleteElement, overlayCache }) => {
  const [dragging, setDragging] = useState(null);
  const [resizing, setResizing] = useState(null);
  const canvasRef = useRef(null);
  
  // Scale factor: elements are stored at 1920x1080, canvas displays at 960x540
  const SCALE = 0.5;

  const handleMouseDown = (e, element) => {
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
  };

  const handleMouseMove = (e) => {
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
  };

  const handleMouseUp = () => {
    setDragging(null);
    setResizing(null);
  };

  const handleDoubleClick = (e, element) => {
    e.stopPropagation();
    if (element.type === 'text') {
      const newContent = prompt('Edit text:', element.content);
      if (newContent !== null) {
        onUpdateElement({ ...element, content: newContent });
      }
    }
  };

  const handleResizeStart = (e, element) => {
    e.stopPropagation();
    setResizing({ element });
  };

  const handleCanvasClick = () => {
    onSelectElement(null);
  };
  
  // Helper to resolve overlay source from cache
  const getOverlaySrc = (element) => {
    if (element.type === 'overlay' && element.overlayId && overlayCache?.current) {
      return overlayCache.current[element.overlayId] || '';
    }
    return element.src || '';
  };

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
        <div
          key={element.id}
          className={`absolute cursor-move select-none ${
            selectedElement?.id === element.id ? 'ring-2 ring-[#FFC107]' : ''
          }`}
          style={{
            left: `${element.x * SCALE}px`,
            top: `${element.y * SCALE}px`,
            width: `${element.width * SCALE}px`,
            height: `${element.height * SCALE}px`,
            fontSize: `${(element.fontSize || 16) * SCALE}px`,
            fontWeight: element.fontWeight,
            color: element.color,
            textAlign: element.textAlign,
            fontFamily: element.fontFamily,
            lineHeight: element.lineHeight || 1.5,
            whiteSpace: 'pre-wrap',
            textShadow: element.textShadow || 'none'
          }}
          onMouseDown={(e) => handleMouseDown(e, element)}
          onDoubleClick={(e) => handleDoubleClick(e, element)}
        >
          {element.type === 'text' && (
            <div className="w-full h-full flex items-center justify-center break-words">
              {element.content}
            </div>
          )}
          {element.type === 'image' && (
            <img src={element.src} alt="" className="w-full h-full object-contain" />
          )}
          {/* Overlay type - resolves overlayId from cache */}
          {element.type === 'overlay' && (
            <img src={getOverlaySrc(element)} alt="" className="w-full h-full object-contain" />
          )}

          {selectedElement?.id === element.id && (
            <>
              {/* Resize handle */}
              <div
                className="absolute bottom-0 right-0 w-4 h-4 bg-[#FFC107] cursor-se-resize"
                onMouseDown={(e) => handleResizeStart(e, element)}
              />
              {/* Delete button */}
              <button
                className="absolute -top-8 right-0 bg-red-600 hover:bg-red-700 text-white p-1 rounded"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteElement(element.id);
                }}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      ))}
    </div>
  );
};

export default SlideCanvas;