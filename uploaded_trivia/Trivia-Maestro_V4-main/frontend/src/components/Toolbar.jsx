import React, { memo, useCallback, useMemo } from 'react';
import { Button } from './ui/button';
import { Separator } from './ui/separator';
import {
  Bold,
  AlignLeft,
  AlignCenter,
  AlignRight,
  Plus,
  Image,
  Type,
  Trash2,
  Play,
  Save,
  Download,
  ListOrdered,
  Wand2
} from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import OverlayManager from './OverlayManager';

// Memoized font size options to prevent recreating on each render
const FONT_SIZES = [12, 14, 16, 18, 20, 24, 28, 32, 36, 42, 48, 56, 64, 72];

/**
 * Toolbar component - memoized to prevent unnecessary re-renders
 */
const Toolbar = memo(({
  onAddSlide,
  onAddText,
  onAddImage,
  onDeleteSlide,
  onStartPresentation,
  onSave,
  onOpenScoreTracker,
  onFixFormatting,
  selectedElement,
  onUpdateElement,
  canDelete,
  presentationId,
  locationName,
  onOverlaysApplied,
  slides
}) => {
  // Memoize handlers to prevent child re-renders
  const handleFontSizeChange = useCallback((value) => {
    if (selectedElement && onUpdateElement) {
      onUpdateElement({ ...selectedElement, fontSize: parseInt(value) });
    }
  }, [selectedElement, onUpdateElement]);

  const handleAlignChange = useCallback((align) => {
    if (selectedElement && onUpdateElement) {
      onUpdateElement({ ...selectedElement, textAlign: align });
    }
  }, [selectedElement, onUpdateElement]);

  const handleBoldToggle = useCallback(() => {
    if (selectedElement && onUpdateElement) {
      const newWeight = selectedElement.fontWeight === 'bold' ? '400' : 'bold';
      onUpdateElement({ ...selectedElement, fontWeight: newWeight });
    }
  }, [selectedElement, onUpdateElement]);

  const handleColorChange = useCallback((e) => {
    if (selectedElement && onUpdateElement) {
      onUpdateElement({ ...selectedElement, color: e.target.value });
    }
  }, [selectedElement, onUpdateElement]);

  const handleFontFamilyChange = useCallback((value) => {
    if (selectedElement && onUpdateElement) {
      const updates = { 
        ...selectedElement, 
        fontFamily: value 
      };
      // If Lemonada is selected, automatically make it bold
      if (value === 'Lemonada, cursive') {
        updates.fontWeight = 'bold';
      }
      onUpdateElement(updates);
    }
  }, [selectedElement, onUpdateElement]);

  const handleAlignLeft = useCallback(() => handleAlignChange('left'), [handleAlignChange]);
  const handleAlignCenter = useCallback(() => handleAlignChange('center'), [handleAlignChange]);
  const handleAlignRight = useCallback(() => handleAlignChange('right'), [handleAlignChange]);

  // Memoize font size select items
  const fontSizeItems = useMemo(() => (
    FONT_SIZES.map((size) => (
      <SelectItem key={size} value={size.toString()}>
        {size}
      </SelectItem>
    ))
  ), []);

  // Memoize text formatting section visibility
  const showTextFormatting = selectedElement && selectedElement.type === 'text';

  return (
    <div className="bg-[#1a1a1a] border-b border-gray-700 px-6 py-3 flex items-center gap-4">
      {/* File Operations */}
      <div className="flex items-center gap-2">
        <Button onClick={onOpenScoreTracker} variant="ghost" size="sm" className="text-white hover:bg-gray-700">
          <ListOrdered className="w-4 h-4 mr-2" />
          Score Tracker
        </Button>
        {/* Fix Formatting button */}
        <Button onClick={onFixFormatting} variant="ghost" size="sm" className="text-white hover:bg-purple-700 bg-purple-900/50">
          <Wand2 className="w-4 h-4 mr-2" />
          Fix Formatting
        </Button>
        {/* Always show Overlays button - will show message if no location */}
        <OverlayManager
          presentationId={presentationId}
          locationName={locationName}
          onOverlaysApplied={onOverlaysApplied}
          slides={slides}
        />
        <Button onClick={onSave} variant="ghost" size="sm" className="text-white hover:bg-gray-700">
          <Save className="w-4 h-4 mr-2" />
          Save
        </Button>
        <Button variant="ghost" size="sm" className="text-white hover:bg-gray-700">
          <Download className="w-4 h-4 mr-2" />
          Export
        </Button>
      </div>

      <Separator orientation="vertical" className="h-8 bg-gray-600" />

      {/* Slide Operations */}
      <div className="flex items-center gap-2">
        <Button onClick={onAddSlide} variant="ghost" size="sm" className="text-white hover:bg-gray-700">
          <Plus className="w-4 h-4 mr-2" />
          New Slide
        </Button>
        <Button
          onClick={onDeleteSlide}
          variant="ghost"
          size="sm"
          disabled={!canDelete}
          className="text-white hover:bg-red-700 disabled:opacity-40"
        >
          <Trash2 className="w-4 h-4 mr-2" />
          Delete
        </Button>
      </div>

      <Separator orientation="vertical" className="h-8 bg-gray-600" />

      {/* Insert Elements */}
      <div className="flex items-center gap-2">
        <Button onClick={onAddText} variant="ghost" size="sm" className="text-white hover:bg-gray-700">
          <Type className="w-4 h-4 mr-2" />
          Text
        </Button>
        <Button onClick={onAddImage} variant="ghost" size="sm" className="text-white hover:bg-gray-700">
          <Image className="w-4 h-4 mr-2" />
          Image
        </Button>
      </div>

      <Separator orientation="vertical" className="h-8 bg-gray-600" />

      {/* Text Formatting - only show when text element is selected */}
      {showTextFormatting && (
        <div className="flex items-center gap-2">
          <Select
            value={selectedElement.fontSize?.toString()}
            onValueChange={handleFontSizeChange}
          >
            <SelectTrigger className="w-20 bg-gray-700 text-white border-gray-600">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {fontSizeItems}
            </SelectContent>
          </Select>

          <Select
            value={selectedElement.fontFamily || 'Montserrat, sans-serif'}
            onValueChange={handleFontFamilyChange}
          >
            <SelectTrigger className="w-[140px] bg-gray-700 text-white border-gray-600">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Montserrat, sans-serif" style={{ fontFamily: 'Montserrat, sans-serif' }}>
                Montserrat
              </SelectItem>
              <SelectItem value="Lemonada, cursive" style={{ fontFamily: 'Lemonada, cursive', fontWeight: 'bold' }}>
                Lemonada Bold
              </SelectItem>
            </SelectContent>
          </Select>

          <Button
            onClick={handleBoldToggle}
            variant="ghost"
            size="sm"
            className={`text-white hover:bg-gray-700 ${selectedElement.fontWeight === 'bold' ? 'bg-gray-700' : ''}`}
          >
            <Bold className="w-4 h-4" />
          </Button>

          <Separator orientation="vertical" className="h-6 bg-gray-600" />

          <Button
            onClick={handleAlignLeft}
            variant="ghost"
            size="sm"
            className={`text-white hover:bg-gray-700 ${selectedElement.textAlign === 'left' ? 'bg-gray-700' : ''}`}
          >
            <AlignLeft className="w-4 h-4" />
          </Button>
          <Button
            onClick={handleAlignCenter}
            variant="ghost"
            size="sm"
            className={`text-white hover:bg-gray-700 ${selectedElement.textAlign === 'center' ? 'bg-gray-700' : ''}`}
          >
            <AlignCenter className="w-4 h-4" />
          </Button>
          <Button
            onClick={handleAlignRight}
            variant="ghost"
            size="sm"
            className={`text-white hover:bg-gray-700 ${selectedElement.textAlign === 'right' ? 'bg-gray-700' : ''}`}
          >
            <AlignRight className="w-4 h-4" />
          </Button>

          <Separator orientation="vertical" className="h-6 bg-gray-600" />

          <input
            type="color"
            value={selectedElement.color}
            onChange={handleColorChange}
            className="w-10 h-8 rounded cursor-pointer bg-gray-700 border border-gray-600"
          />
        </div>
      )}

      <div className="ml-auto">
        <Button
          onClick={onStartPresentation}
          className="bg-[#FFC107] hover:bg-[#FFD54F] text-black font-semibold"
        >
          <Play className="w-4 h-4 mr-2" />
          Start Presentation
        </Button>
      </div>
    </div>
  );
});

Toolbar.displayName = 'Toolbar';

export default Toolbar;
