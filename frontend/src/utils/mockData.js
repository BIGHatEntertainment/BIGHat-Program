// Utility functions for creating new slides and elements

export const defaultSlideBackground = 'radial-gradient(circle at center, #1657E8 5%, #1F5EE9 20%, #191919 90%)';

export const createNewSlide = (order) => ({
  id: `slide-${Date.now()}`,
  order,
  background: defaultSlideBackground,
  elements: [
    {
      id: `elem-${Date.now()}`,
      type: 'text',
      content: 'Click to edit',
      x: 50,
      y: 100,
      width: 600,
      height: 80,
      fontSize: 48,
      fontWeight: '600',
      color: '#ffffff',
      textAlign: 'center',
      fontFamily: 'Inter, sans-serif'
    }
  ]
});

export const createNewTextElement = (x = 100, y = 100) => ({
  id: `elem-${Date.now()}`,
  type: 'text',
  content: 'New Text',
  x,
  y,
  width: 400,
  height: 60,
  fontSize: 24,
  fontWeight: '400',
  color: '#ffffff',
  textAlign: 'left',
  fontFamily: 'Inter, sans-serif'
});