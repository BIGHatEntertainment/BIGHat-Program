// Mock presentation data
export const mockPresentations = [
  {
    id: '1',
    name: 'BIG Hat Trivia Night',
    createdBy: 'Host',
    createdAt: new Date().toISOString(),
    slides: [
      {
        id: 'slide-1',
        order: 0,
        background: 'radial-gradient(circle at center, #1657E8 5%, #1F5EE9 20%, #191919 90%)',
        elements: [
          {
            id: 'elem-1',
            type: 'text',
            content: 'BIG Hat Trivia',
            x: 50,
            y: 30,
            width: 600,
            height: 100,
            fontSize: 72,
            fontWeight: 'bold',
            color: '#FFC107',
            textAlign: 'center',
            fontFamily: 'Inter, sans-serif'
          },
          {
            id: 'elem-2',
            type: 'text',
            content: 'Multiple Choice Round',
            x: 50,
            y: 150,
            width: 600,
            height: 60,
            fontSize: 36,
            fontWeight: '600',
            color: '#ffffff',
            textAlign: 'center',
            fontFamily: 'Inter, sans-serif'
          }
        ]
      },
      {
        id: 'slide-2',
        order: 1,
        background: 'radial-gradient(circle at center, #1657E8 5%, #1F5EE9 20%, #191919 90%)',
        elements: [
          {
            id: 'elem-3',
            type: 'text',
            content: 'Question 1',
            x: 50,
            y: 40,
            width: 600,
            height: 80,
            fontSize: 48,
            fontWeight: 'bold',
            color: '#FFC107',
            textAlign: 'center',
            fontFamily: 'Inter, sans-serif'
          },
          {
            id: 'elem-4',
            type: 'text',
            content: 'What is the capital of Arizona?',
            x: 50,
            y: 140,
            width: 600,
            height: 100,
            fontSize: 32,
            fontWeight: '500',
            color: '#ffffff',
            textAlign: 'center',
            fontFamily: 'Inter, sans-serif'
          },
          {
            id: 'elem-5',
            type: 'text',
            content: 'A) Phoenix\nB) Tucson\nC) Flagstaff\nD) Mesa',
            x: 100,
            y: 260,
            width: 500,
            height: 200,
            fontSize: 28,
            fontWeight: '400',
            color: '#FFC107',
            textAlign: 'left',
            fontFamily: 'Inter, sans-serif',
            lineHeight: 1.8
          }
        ]
      }
    ]
  }
];

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