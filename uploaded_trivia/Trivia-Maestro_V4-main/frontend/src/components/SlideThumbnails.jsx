import React, { memo, useCallback, useMemo } from 'react';
import { Plus } from 'lucide-react';
import { Button } from './ui/button';

/**
 * Individual slide thumbnail - memoized to prevent re-renders when other slides change
 */
const SlideThumbnail = memo(({ 
  slide, 
  index, 
  isSelected, 
  onSelect, 
  onDragStart, 
  onDragOver, 
  onDrop,
  getOverlaySrc 
}) => {
  const handleClick = useCallback(() => {
    onSelect(index);
  }, [onSelect, index]);

  const handleDragStart = useCallback((e) => {
    onDragStart(e, index);
  }, [onDragStart, index]);

  const handleDrop = useCallback((e) => {
    onDrop(e, index);
  }, [onDrop, index]);

  // Memoize the element rendering to avoid recalculating styles
  const renderedElements = useMemo(() => {
    return slide.elements.map((element) => (
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
          <img src={element.src} alt="" className="w-full h-full object-contain" loading="lazy" />
        )}
        {element.type === 'overlay' && getOverlaySrc(element) && (
          <img src={getOverlaySrc(element)} alt="" className="w-full h-full object-contain" loading="lazy" />
        )}
        {element.type === 'overlay' && !getOverlaySrc(element) && (
          <div className="w-full h-full bg-yellow-500/20 border border-dashed border-yellow-500" />
        )}
      </div>
    ));
  }, [slide.elements, getOverlaySrc]);

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      onDragOver={onDragOver}
      onDrop={handleDrop}
      onClick={handleClick}
      className={`relative cursor-pointer rounded-lg overflow-hidden transition-all hover:scale-105 ${
        isSelected
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
        {renderedElements}
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // Custom comparison - only re-render if these specific props change
  return (
    prevProps.slide === nextProps.slide &&
    prevProps.index === nextProps.index &&
    prevProps.isSelected === nextProps.isSelected
  );
});

SlideThumbnail.displayName = 'SlideThumbnail';

/**
 * Slide thumbnails container - memoized with optimized child rendering
 */
const SlideThumbnails = memo(({ 
  slides, 
  currentSlideIndex, 
  onSelectSlide, 
  onAddSlide, 
  onReorderSlides, 
  overlayCache,
  overlayCacheVersion // Used to trigger re-render when overlay cache is populated
}) => {
  // Memoize drag handlers
  const handleDragStart = useCallback((e, index) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', index.toString());
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    return false;
  }, []);

  const handleDrop = useCallback((e, dropIndex) => {
    e.preventDefault();
    const dragIndex = parseInt(e.dataTransfer.getData('text/html'));
    if (dragIndex !== dropIndex) {
      onReorderSlides(dragIndex, dropIndex);
    }
  }, [onReorderSlides]);

  // Memoize overlay source getter - depends on overlayCacheVersion to re-compute when cache updates
  const getOverlaySrc = useCallback((element) => {
    if (element.type === 'overlay' && element.overlayId && overlayCache?.current) {
      return overlayCache.current[element.overlayId] || '';
    }
    return element.src || '';
  }, [overlayCache, overlayCacheVersion]);

  // Memoize the slides list to prevent unnecessary re-renders
  const slidesList = useMemo(() => {
    return slides.map((slide, index) => (
      <SlideThumbnail
        key={slide.id}
        slide={slide}
        index={index}
        isSelected={currentSlideIndex === index}
        onSelect={onSelectSlide}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        getOverlaySrc={getOverlaySrc}
      />
    ));
  }, [slides, currentSlideIndex, onSelectSlide, handleDragStart, handleDragOver, handleDrop, getOverlaySrc]);

  return (
    <div className="w-64 bg-[#1a1a1a] border-r border-gray-700 flex flex-col">
      <div className="p-4 border-b border-gray-700">
        <h2 className="text-white font-semibold text-lg">Slides</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {slidesList}
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
});

SlideThumbnails.displayName = 'SlideThumbnails';

export default SlideThumbnails;
