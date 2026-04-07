import React from 'react';
import { Plus } from 'lucide-react';
import { Button } from './ui/button';

const SlideThumbnails = ({ slides, currentSlideIndex, onSelectSlide, onAddSlide, onReorderSlides, overlayCache }) => {
  const handleDragStart = (e, index) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', index.toString());
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    return false;
  };

  const handleDrop = (e, dropIndex) => {
    e.preventDefault();
    const dragIndex = parseInt(e.dataTransfer.getData('text/html'));
    if (dragIndex !== dropIndex) {
      onReorderSlides(dragIndex, dropIndex);
    }
  };
  
  // Helper to resolve overlay source from cache
  const getOverlaySrc = (element) => {
    if (element.type === 'overlay' && element.overlayId && overlayCache?.current) {
      return overlayCache.current[element.overlayId] || '';
    }
    return element.src || '';
  };

  return (
    <div className="w-64 bg-[#1a1a1a] border-r border-gray-700 flex flex-col">
      <div className="p-4 border-b border-gray-700">
        <h2 className="text-white font-semibold text-lg">Slides</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {slides.map((slide, index) => (
          <div
            key={slide.id}
            draggable
            onDragStart={(e) => handleDragStart(e, index)}
            onDragOver={handleDragOver}
            onDrop={(e) => handleDrop(e, index)}
            onClick={() => onSelectSlide(index)}
            className={`relative cursor-pointer rounded-lg overflow-hidden transition-all hover:scale-105 ${
              currentSlideIndex === index
                ? 'ring-2 ring-[#FFC107] shadow-lg shadow-[#FFC107]/30'
                : 'ring-1 ring-gray-600 hover:ring-gray-500'
            }`}
          >
            <div className="absolute top-2 left-2 bg-black/70 text-white text-xs px-2 py-1 rounded z-10">
              {index + 1}
            </div>
            <div
              className="w-full aspect-[16/9] relative"
              style={{
                background: slide.background,
                transform: 'scale(0.95)'
              }}
            >
              {slide.elements.map((element) => (
                <div
                  key={element.id}
                  className="absolute"
                  style={{
                    left: `${(element.x / 1920) * 100}%`,
                    top: `${(element.y / 1080) * 100}%`,
                    width: `${(element.width / 1920) * 100}%`,
                    height: `${(element.height / 1080) * 100}%`,
                    fontSize: `${(element.fontSize || 16) * 0.08}px`,
                    fontWeight: element.fontWeight,
                    color: element.color,
                    textAlign: element.textAlign,
                    overflow: 'hidden'
                  }}
                >
                  {element.type === 'text' && (
                    <div className="truncate text-[6px]">{element.content}</div>
                  )}
                  {element.type === 'image' && (
                    <img src={element.src} alt="" className="w-full h-full object-contain" />
                  )}
                  {/* Overlay type - resolves overlayId from cache */}
                  {element.type === 'overlay' && (
                    <img src={getOverlaySrc(element)} alt="" className="w-full h-full object-contain" />
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
        <Button
          onClick={onAddSlide}
          variant="outline"
          className="w-full border-dashed border-2 border-gray-600 hover:border-[#FFC107] text-gray-400 hover:text-white bg-transparent"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Slide
        </Button>
      </div>
    </div>
  );
};

export default SlideThumbnails;