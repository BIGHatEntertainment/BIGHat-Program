// Story Generator Add-on - Main Export File

// Pages
export { default as StoryGeneratorDashboard } from './pages/Dashboard';
export { default as StoryGeneratorPage } from './pages/StoryGenerator';

// Components
export { VideoPreview, SECTION_DURATIONS, VIDEO_WIDTH, VIDEO_HEIGHT } from './components/VideoPreview';
export { VideoEncoder } from './components/VideoEncoder';
export { Timeline } from './components/Timeline';
export { IGGradientDef } from './components/IGGradient';

// Configuration (hardcoded values)
export const StoryGeneratorConfig = {
  routes: {
    dashboard: '/story-generator',
    create: '/story-generator/create',
  },
  videoDurations: {
    location: 5,
    host: 5,
    rounds: 15,
    total: 25,
  },
  videoDimensions: {
    width: 1080,
    height: 1920,
    aspectRatio: '9:16',
  },
  roundsConfig: {
    minRounds: 5,
    maxRounds: 6,
    defaultColors: [
      '#FCAF45', // Yellow
      '#F77737', // Orange
      '#E1306C', // Pink
      '#C13584', // Magenta
      '#833AB4', // Purple
      '#5851DB', // Blue-violet
    ],
  },
};
