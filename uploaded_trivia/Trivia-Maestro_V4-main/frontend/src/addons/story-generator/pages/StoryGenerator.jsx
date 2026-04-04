import React, { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Settings, Video, Calendar, MapPin, User, ListChecks, Cpu, Zap, Home, Loader2, AlertCircle } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Card } from '../../../components/ui/card';
import { ScrollArea } from '../../../components/ui/scroll-area';
import { VideoPreview } from '../components/VideoPreview';
import { Timeline } from '../components/Timeline';
import { VideoEncoder } from '../components/VideoEncoder';
import { storyBuildsAPI } from '../../../services/api';
import { toast } from 'sonner';
import { IGGradientDef } from '../components/IGGradient';

// Round type colors - updated for new theme
const ROUND_COLORS = {
  'MC': '#22c55e',    // Green
  'REG': '#ef4444',   // Red
  'MISC': '#3b82f6',  // Blue
  'MYS': '#a855f7',   // Purple
  'BIG': '#fbdd68',   // Gold (theme accent)
};

// Default round colors (using gold theme palette)
const DEFAULT_ROUND_COLORS = [
  '#fbdd68', // Gold
  '#fee16b', // Light Gold
  '#f5d050', // Dark Gold
  '#22c55e', // Green
  '#3b82f6', // Blue
  '#a855f7', // Purple
];

const StoryGeneratorPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const previewRef = useRef(null);

  // Get presentation data from navigation state
  const presentationFromState = location.state?.presentation;

  const [loading, setLoading] = useState(true);
  const [loadingStep, setLoadingStep] = useState('');
  const [error, setError] = useState(null);
  const [presentationData, setPresentationData] = useState(null);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [currentSection, setCurrentSection] = useState('location');
  const [isPlaying, setIsPlaying] = useState(false);

  // Load presentation data on mount
  useEffect(() => {
    if (presentationFromState) {
      loadPresentationData(presentationFromState);
    } else {
      // No presentation selected, redirect to dashboard
      setLoading(false);
      setError('No presentation selected. Please select a presentation from the dashboard.');
    }
  }, [presentationFromState]);

  const loadPresentationData = async (presentation) => {
    try {
      setLoading(true);
      setError(null);
      setLoadingStep('Finding build file...');
      
      // Store basic presentation info
      setPresentationData(presentation);
      
      // Step 1: Find and fetch the JSON from SharePoint
      let jsonData = null;
      
      if (presentation.locationFolder || presentation.location) {
        try {
          setLoadingStep('Searching SharePoint for build...');
          // Try to find the matching build file in SharePoint
          const builds = await storyBuildsAPI.listBuilds();
          
          // Get presentation info for matching
          const presLocationFolder = presentation.locationFolder || presentation.location;
          const presDate = presentation.createdAt ? new Date(presentation.createdAt) : null;
          const presName = presentation.name || '';
          
          // Clean the presentation name for matching
          const presNameClean = presName
            .replace(/^\d+_/, '')  // Remove leading number prefix
            .toLowerCase()
            .trim();
          
          // Extract date from presentation name if present (format: "Location - M/D/YYYY")
          const dateMatch = presName.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
          let presDateFromName = null;
          if (dateMatch) {
            presDateFromName = new Date(parseInt(dateMatch[3]), parseInt(dateMatch[1]) - 1, parseInt(dateMatch[2]));
          }
          
          console.log('[StoryGenerator] Looking for build matching:', {
            name: presName,
            nameClean: presNameClean,
            locationFolder: presLocationFolder,
            createdAt: presDate?.toISOString(),
            dateFromName: presDateFromName?.toISOString()
          });
          
          // Find builds for this location
          const locationBuilds = builds.filter(b => b.locationFolder === presLocationFolder);
          console.log(`[StoryGenerator] Found ${locationBuilds.length} builds in ${presLocationFolder}`);
          
          let matchingBuild = null;
          
          // Method 1: EXACT presentation name match (highest priority)
          // This ensures "Monkey Pants - Test" doesn't match "Monkey Pants - 2/5/2025"
          if (locationBuilds.length > 0) {
            for (const build of locationBuilds) {
              // The build name format is like "Monkey Pants - Monkey_Pants_-_Test_20260205_..."
              // Extract the presentation part before the timestamp
              const buildNameParts = build.name.split('_');
              // Find where the date starts (8 consecutive digits like 20260205)
              const dateIndex = buildNameParts.findIndex(part => /^\d{8}$/.test(part));
              const buildPresName = dateIndex > 0 
                ? buildNameParts.slice(0, dateIndex).join('_').replace(/_/g, ' ').toLowerCase()
                : build.name.toLowerCase();
              
              // Check if presentation names match closely
              if (buildPresName.includes(presNameClean) || presNameClean.includes(buildPresName)) {
                // Additional check: if both have dates, they should match
                if (presDateFromName) {
                  const buildDateMatch = build.filename.match(/(\d{8})/);
                  if (buildDateMatch) {
                    const buildDateStr = buildDateMatch[1];
                    const buildDate = new Date(
                      parseInt(buildDateStr.substring(0, 4)),
                      parseInt(buildDateStr.substring(4, 6)) - 1,
                      parseInt(buildDateStr.substring(6, 8))
                    );
                    const dayDiff = Math.abs(buildDate - presDateFromName) / (1000 * 60 * 60 * 24);
                    if (dayDiff < 1) {
                      matchingBuild = build;
                      console.log('[StoryGenerator] Method 1a: Exact name + date match');
                      break;
                    }
                  }
                } else {
                  matchingBuild = build;
                  console.log('[StoryGenerator] Method 1b: Exact name match (no date in pres name)');
                  break;
                }
              }
            }
          }
          
          // Method 2: Match by location + closest creation date (within 1 hour)
          if (!matchingBuild && locationBuilds.length > 0 && presDate) {
            const sortedByDate = [...locationBuilds].sort((a, b) => {
              const dateA = new Date(a.lastModified);
              const dateB = new Date(b.lastModified);
              return Math.abs(dateA - presDate) - Math.abs(dateB - presDate);
            });
            
            const closest = sortedByDate[0];
            const closestDate = new Date(closest.lastModified);
            const hoursDiff = Math.abs(closestDate - presDate) / (1000 * 60 * 60);
            
            // Only match if within 1 hour (stricter than before)
            if (hoursDiff < 1) {
              matchingBuild = closest;
              console.log(`[StoryGenerator] Method 2: Matched by location + creation time (${hoursDiff.toFixed(2)} hours diff)`);
            }
          }
          
          // Method 3: If presentation name contains "Test", look for Test builds specifically
          if (!matchingBuild && locationBuilds.length > 0 && presNameClean.includes('test')) {
            for (const build of locationBuilds) {
              if (build.name.toLowerCase().includes('test')) {
                matchingBuild = build;
                console.log('[StoryGenerator] Method 3: Matched Test presentation to Test build');
                break;
              }
            }
          }
          
          // Method 4: If only one build for this location and no Test/special naming, use it
          if (!matchingBuild && locationBuilds.length === 1 && !presNameClean.includes('test')) {
            matchingBuild = locationBuilds[0];
            console.log('[StoryGenerator] Method 4: Only one build for this location');
          }
          
          // Method 5: Last resort - find newest build for this location
          if (!matchingBuild && locationBuilds.length > 0) {
            const newestBuild = [...locationBuilds].sort((a, b) => 
              new Date(b.lastModified) - new Date(a.lastModified)
            )[0];
            matchingBuild = newestBuild;
            console.log('[StoryGenerator] Method 5: Using newest build for this location');
          }
          
          if (matchingBuild) {
            setLoadingStep('Loading build data...');
            console.log('[StoryGenerator] Found matching build:', matchingBuild.filename);
            const response = await storyBuildsAPI.getBuild(matchingBuild.locationFolder, matchingBuild.filename);
            if (response.success) {
              jsonData = response.data;
              console.log('[StoryGenerator] Loaded JSON data from SharePoint:', jsonData);
            }
          } else {
            console.warn('[StoryGenerator] No matching build found in SharePoint for:', presentation.name);
            console.warn('[StoryGenerator] Available builds:', builds.map(b => `${b.locationFolder}/${b.name}`));
            toast.warning('No matching build data found for this presentation. Some story details may be missing.');
          }
        } catch (fetchError) {
          console.warn('[StoryGenerator] Could not fetch JSON from SharePoint:', fetchError);
          // Continue with presentation data from MongoDB
        }
      }
      
      // Use jsonData if available, otherwise fall back to presentation data
      const buildData = jsonData || presentation;
      
      // Step 2: NO asset pre-fetching needed — the server-side video generator
      // fetches assets directly from SharePoint. This prevents mobile crashes from
      // loading ~10MB of base64 images into browser memory.
      
      setLoadingStep('Preparing preview...');
      
      // Build the event object — server fetches actual images during video generation
      const eventData = {
        id: presentation.id,
        name: presentation.name,
        venue: (buildData.location || presentation.location || presentation.locationFolder || 'Trivia Night').replace(/^\d+_/, ''),
        date: presentation.createdAt ? new Date(presentation.createdAt).toISOString().split('T')[0] : new Date().toISOString().split('T')[0],
        time: '7:00 PM',
        host: {
          name: buildData.host || presentation.host || 'Host',
        },
        location: {
          name: (buildData.location || presentation.location || '').replace(/^\d+_/, ''),
          folder: buildData.locationFolder || presentation.locationFolder || '',
        },
        // Build rounds from JSON data or presentation data
        // MC rounds always show "Multiple Choice", MYS rounds always show "Mystery"
        // Clean up names: remove version suffixes (_1, _2) and BIG_ prefix
        rounds: (buildData.roundNames || presentation.roundNames || []).map((name, idx) => {
          const roundType = buildData.roundTypes?.[idx] || presentation.roundTypes?.[idx] || '';
          let displayName = name;
          
          // Override display names for specific round types
          if (roundType === 'MC') {
            displayName = 'Multiple Choice';
          } else if (roundType === 'MYS') {
            displayName = 'Mystery';
          } else {
            // Clean up the display name
            // 1. Remove BIG_ prefix for BIG rounds
            if (roundType === 'BIG' && displayName.startsWith('BIG_')) {
              displayName = displayName.replace(/^BIG_/, '');
            }
            
            // 2. Remove version suffixes like _1, _2, _3, etc. at the end
            displayName = displayName.replace(/_\d+$/, '');
            
            // 3. Split CamelCase into separate words (e.g., "CollegeFootball" -> "College Football")
            displayName = displayName.replace(/([a-z])([A-Z])/g, '$1 $2');
            
            // 4. Replace underscores with spaces for readability
            displayName = displayName.replace(/_/g, ' ');
            
            // 5. Clean up any extra spaces
            displayName = displayName.replace(/\s+/g, ' ').trim();
            
            // 6. Capitalize first letter of each word (Title Case)
            displayName = displayName
              .split(' ')
              .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
              .join(' ');
          }
          
          return {
            name: displayName,
            color: ROUND_COLORS[roundType] || DEFAULT_ROUND_COLORS[idx % DEFAULT_ROUND_COLORS.length]
          };
        }),
        status: 'published',
        createdAt: presentation.createdAt,
        // Additional data for reference
        numRounds: buildData.numRounds || presentation.numRounds || presentation.roundTypes?.length || 5,
        roundTypes: buildData.roundTypes || presentation.roundTypes || [],
        roundNames: buildData.roundNames || presentation.roundNames || [],
        locationFolder: buildData.locationFolder || presentation.locationFolder,
      };
      
      // If no rounds data, create placeholder rounds
      if (eventData.rounds.length === 0) {
        const numRounds = eventData.numRounds || 5;
        eventData.rounds = Array.from({ length: numRounds }, (_, idx) => ({
          name: `Round ${idx + 1}`,
          color: DEFAULT_ROUND_COLORS[idx % DEFAULT_ROUND_COLORS.length]
        }));
      }
      
      setSelectedEvent(eventData);
      
    } catch (error) {
      console.error('[StoryGenerator] Error loading presentation:', error);
      setError('Failed to load presentation data');
    } finally {
      setLoading(false);
      setLoadingStep('');
    }
  };

  const handleVideoComplete = (url) => {
    toast.success('Video generated successfully!');
  };

  const handleVideoError = (error) => {
    toast.error(`Failed to generate video: ${error.message}`);
  };

  // Format date for display
  const formatEventDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      weekday: 'short', 
      month: 'short', 
      day: 'numeric' 
    });
  };

  return (
    <div className="min-h-screen bg-[#000e2a] flex flex-col" data-testid="story-generator-page">
      {/* SVG Gradient Definitions */}
      <IGGradientDef />
      
      {/* Ambient lighting effects */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <motion.div 
          className="absolute -top-40 -left-40 w-96 h-96 bg-[#141b50] rounded-full blur-[120px] opacity-40"
          animate={{ scale: [1, 1.1, 1], opacity: [0.3, 0.4, 0.3] }}
          transition={{ duration: 10, repeat: Infinity }}
        />
        <motion.div 
          className="absolute -bottom-40 -right-40 w-96 h-96 bg-[#fbdd68] rounded-full blur-[150px] opacity-10"
          animate={{ scale: [1.1, 1, 1.1], opacity: [0.08, 0.12, 0.08] }}
          transition={{ duration: 10, repeat: Infinity, delay: 5 }}
        />
      </div>

      {/* Header */}
      <header className="border-b border-[#fbdd68]/20 bg-[#000e2a]/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <motion.div 
            className="flex items-center gap-4"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            {/* Back Button */}
            <Button
              variant="outline"
              onClick={() => navigate('/story-generator')}
              className="rounded-lg border-[#fbdd68]/30 bg-[#141b50]/60 hover:bg-[#141b50] text-white transition-all duration-300 gap-2"
              data-testid="back-btn"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            
            {/* Exit Button */}
            <Button
              variant="outline"
              onClick={() => navigate('/')}
              className="rounded-lg border-[#fbdd68]/30 bg-[#141b50]/60 hover:bg-[#fbdd68] hover:text-[#000e2a] text-[#fbdd68] transition-all duration-300 gap-2"
              data-testid="exit-btn"
            >
              <Home className="h-4 w-4" />
              Exit
            </Button>
            
            <div className="h-px w-6 bg-gradient-to-r from-transparent via-[#fbdd68]/30 to-transparent" />
            
            <div>
              <h1 className="font-bold text-xl tracking-wide text-white">
                STORY GENERATOR
              </h1>
              <p className="text-xs text-[#fbdd68]/80 font-mono tracking-wider">
                // CREATE YOUR TRIVIA STORY
              </p>
            </div>
          </motion.div>

          <motion.div 
            className="flex items-center gap-3"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#141b50]/60 border border-[#fbdd68]/20">
              <Settings className="h-3.5 w-3.5 text-[#8892b0] animate-spin" style={{ animationDuration: '8s' }} />
              <span className="text-xs text-[#8892b0] font-mono">9:16</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#141b50]/60 border border-[#fbdd68]/20">
              <Cpu className="h-3.5 w-3.5 text-[#fbdd68]" />
              <span className="text-xs text-[#fbdd68] font-mono">CLIENT-SIDE</span>
            </div>
          </motion.div>
        </div>
      </header>

      {/* Loading State */}
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center"
          >
            <div className="h-20 w-20 rounded-2xl bg-[#141b50]/50 border border-[#fbdd68]/20 flex items-center justify-center mx-auto mb-6">
              <Loader2 className="h-10 w-10 text-[#fbdd68] animate-spin" />
            </div>
            <h3 className="text-2xl font-bold text-white tracking-wide">
              Loading Presentation
            </h3>
            <p className="text-[#8892b0] mt-2">
              {loadingStep || 'Fetching details from SharePoint...'}
            </p>
          </motion.div>
        </div>
      )}

      {/* Error State */}
      {error && !loading && (
        <div className="flex-1 flex items-center justify-center">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center"
          >
            <div className="h-20 w-20 rounded-2xl bg-red-500/20 border border-red-500/30 flex items-center justify-center mx-auto mb-6">
              <AlertCircle className="h-10 w-10 text-red-400" />
            </div>
            <h3 className="text-2xl font-bold text-white tracking-wide">
              Error
            </h3>
            <p className="text-[#8892b0] mt-2 mb-6">
              {error}
            </p>
            <Button
              onClick={() => navigate('/story-generator')}
              className="rounded-lg bg-[#fbdd68] hover:bg-[#fee16b] text-[#000e2a] font-semibold"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Dashboard
            </Button>
          </motion.div>
        </div>
      )}

      {/* Main Content - Split Layout */}
      {!loading && !error && selectedEvent && (
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden relative z-10">
          {/* Left Panel - Controls */}
          <motion.div 
            className="w-full lg:w-[420px] border-r border-[#fbdd68]/10 bg-[#0a1940]/80 backdrop-blur-sm"
            initial={{ opacity: 0, x: -40 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
          >
            <ScrollArea className="h-full">
              <div className="p-6 space-y-6">
                {/* Event Details */}
                <Card className="bg-[#141b50]/50 border border-[#fbdd68]/30 rounded-xl p-5 space-y-4">
                  <h3 className="font-bold text-lg tracking-wide text-white">
                    {selectedEvent.name}
                  </h3>
                  
                  <div className="space-y-3 text-sm">
                    <div className="flex items-center gap-3 group">
                      <div className="h-8 w-8 rounded-lg bg-[#fbdd68]/20 flex items-center justify-center group-hover:bg-[#fbdd68]/30 transition-colors">
                        <MapPin className="h-4 w-4 text-[#fbdd68]" />
                      </div>
                      <span className="text-white">{selectedEvent.venue}</span>
                    </div>
                    <div className="flex items-center gap-3 group">
                      <div className="h-8 w-8 rounded-lg bg-[#fbdd68]/10 flex items-center justify-center group-hover:bg-[#fbdd68]/20 transition-colors">
                        <Calendar className="h-4 w-4 text-[#fbdd68]/80" />
                      </div>
                      <span className="text-white">
                        {formatEventDate(selectedEvent.date)} at {selectedEvent.time}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 group">
                      <div className="h-8 w-8 rounded-lg bg-green-500/20 flex items-center justify-center group-hover:bg-green-500/30 transition-colors">
                        <User className="h-4 w-4 text-green-400" />
                      </div>
                      <span className="text-white">{selectedEvent.host.name}</span>
                    </div>
                  </div>
                </Card>

                {/* Rounds List */}
                <div className="bg-[#141b50]/50 border border-[#fbdd68]/30 rounded-xl p-5 space-y-3">
                  <div className="flex items-center gap-2">
                    <ListChecks className="h-4 w-4 text-[#fbdd68]" />
                    <span className="font-mono text-xs text-[#fbdd68] uppercase tracking-[0.2em]">
                      Tonight&apos;s Rounds ({selectedEvent.rounds.length})
                    </span>
                  </div>
                  <div className="space-y-2">
                    {selectedEvent.rounds.map((round, index) => (
                      <motion.div
                        key={index}
                        className="flex items-center gap-3 p-3 rounded-lg bg-[#000e2a]/60 border border-[#fbdd68]/20 hover:border-[#fbdd68]/50 transition-all duration-300 group"
                        whileHover={{ x: 4 }}
                      >
                        <motion.div
                          className="h-4 w-4 rounded-full border border-white/20"
                          style={{ backgroundColor: round.color }}
                          whileHover={{ scale: 1.3 }}
                          transition={{ duration: 0.2 }}
                        />
                        <span className="text-sm text-white">
                          {round.name}
                        </span>
                        <span className="ml-auto font-mono text-[10px] text-[#fbdd68]/60 opacity-0 group-hover:opacity-100 transition-opacity">
                          #{String(index + 1).padStart(2, '0')}
                        </span>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </div>
            </ScrollArea>
          </motion.div>

          {/* Center Panel - Preview & Controls */}
          <div className="flex-1 bg-[#000e2a] flex flex-col items-center justify-center p-8 relative overflow-hidden">
            {/* Grid pattern */}
            <div className="absolute inset-0 opacity-10">
              <div 
                className="w-full h-full"
                style={{
                  backgroundImage: `
                    linear-gradient(rgba(251, 221, 104, 0.1) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(251, 221, 104, 0.1) 1px, transparent 1px)
                  `,
                  backgroundSize: '50px 50px'
                }}
              />
            </div>
            
            {/* Corner decorations */}
            <div className="absolute top-4 left-4 w-16 h-16 border-l-2 border-t-2 border-[#fbdd68]/40" />
            <div className="absolute top-4 right-4 w-16 h-16 border-r-2 border-t-2 border-[#fbdd68]/40" />
            <div className="absolute bottom-4 left-4 w-16 h-16 border-l-2 border-b-2 border-[#fbdd68]/40" />
            <div className="absolute bottom-4 right-4 w-16 h-16 border-r-2 border-b-2 border-[#fbdd68]/40" />

            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="relative flex flex-col items-center gap-6"
            >
              {/* Glow behind preview */}
              <div className="absolute -inset-8 bg-gradient-to-br from-[#fbdd68]/10 via-transparent to-[#fbdd68]/10 rounded-3xl blur-2xl" />
              
              <VideoPreview
                event={selectedEvent}
                currentSection={currentSection}
                onSectionChange={setCurrentSection}
                isPlaying={isPlaying}
                onPlayPause={setIsPlaying}
                previewRef={previewRef}
              />
              
              {/* Timeline & Generate - Below Preview */}
              <div className="relative z-10 w-full max-w-md space-y-4">
                {/* Video Timeline */}
                <div className="space-y-3 bg-[#141b50]/60 backdrop-blur-sm rounded-xl p-4 border border-[#fbdd68]/30">
                  <span className="font-mono text-xs text-[#fbdd68] uppercase tracking-[0.2em] flex items-center gap-2">
                    <Video className="h-3 w-3 text-[#fbdd68]" />
                    Video Timeline
                  </span>
                  <Timeline
                    currentSection={currentSection}
                    onSelect={setCurrentSection}
                  />
                </div>

                {/* Generate Button */}
                <VideoEncoder
                  event={selectedEvent}
                  onComplete={handleVideoComplete}
                  onError={handleVideoError}
                />
              </div>
            </motion.div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StoryGeneratorPage;
