import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Toolbar from '../../components/trivia/editor/Toolbar';
import SlideCanvas from '../../components/trivia/editor/SlideCanvas';
import SlideThumbnails from '../../components/trivia/editor/SlideThumbnails';
import PresentationMode from '../../components/trivia/editor/PresentationMode';
import { createNewSlide, createNewTextElement } from '../../utils/mockData';
import { toast } from '../../utils/toastCompat';
import { ArrowLeft, Loader2, ListOrdered } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { presentationAPI, storyBuildsAPI } from '../../services/triviaApi';

import ScoreTrackerModal from '../../components/trivia/editor/ScoreTrackerModal';

// HOST CONTROL BOX: The Audience Control panel's blue border top edge
// Based on user feedback, moving options closer - approximately y=930 in 1080p coordinates
// Elements should have bottom edge 25px above this
const AUDIENCE_CONTROL_TOP = 930;
const ELEMENT_BOTTOM_MARGIN = 25;
const MAX_ELEMENT_BOTTOM = AUDIENCE_CONTROL_TOP - ELEMENT_BOTTOM_MARGIN; // 905

const Editor = () => {
  const navigate = useNavigate();
  const [presentation, setPresentation] = useState(null);
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);
  const [selectedElement, setSelectedElement] = useState(null);
  const [isPresentationMode, setIsPresentationMode] = useState(false);
  const [isScoreTrackerOpen, setIsScoreTrackerOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [shouldAutoInitOverlays, setShouldAutoInitOverlays] = useState(false);
  const [shouldAutoFormat, setShouldAutoFormat] = useState(false);
  // Atomic state machine: prevents concurrent formatting/overlay operations
  const [slideOp, setSlideOp] = useState('idle'); // 'idle' | 'formatting' | 'overlaying'
  // Track overlay cache version to force re-render when cache is populated
  const [overlayCacheVersion, setOverlayCacheVersion] = useState(0);
  
  // MEMORY OPTIMIZATION: Store overlay images in a ref (not state) to avoid duplicating in slides
  // Slides only store overlayId references, not the full base64 data
  const overlayCache = useRef({});

  const currentSlide = presentation?.slides[currentSlideIndex];

  useEffect(() => {
    loadPresentation();
  }, []);

  // Single useEffect for ALL slide operations — atomic state machine prevents races
  useEffect(() => {
    if (!presentation?.id || loading || slideOp !== 'idle') return;
    
    if (shouldAutoFormat) {
      setSlideOp('formatting');
      const run = async () => {
        try {
          await applyFormatting();
          // After formatting, apply overlays if needed
          if (shouldAutoInitOverlays) {
            await new Promise(r => setTimeout(r, 300));
            await triggerAutoOverlays();
          }
        } finally {
          setSlideOp('idle');
        }
      };
      run();
    } else if (shouldAutoInitOverlays) {
      setSlideOp('overlaying');
      triggerAutoOverlays().finally(() => setSlideOp('idle'));
    }
  }, [presentation?.id, loading, slideOp, shouldAutoFormat, shouldAutoInitOverlays]);

  const loadPresentation = async () => {
    try {
      setLoading(true);
      const presentationId = localStorage.getItem('currentPresentationId');
      
      if (presentationId) {
        const data = await presentationAPI.getById(presentationId);
        
        // Check if it's a chunked presentation (slides stored in batches)
        if (data.type === 'trivia-chunked') {
          const totalChunks = data.totalChunks || 1;
          const totalSlides = data.totalSlides || 0;
          let allSlides = [];
          
          toast({ 
            title: 'Loading Slides...', 
            description: `Loading ${totalSlides} slides in ${totalChunks} batches...`, 
            variant: 'default' 
          });
          
          try {
            // Load chunks progressively
            for (let i = 1; i <= totalChunks; i++) {
              const chunkData = await presentationAPI.getSlideChunk(presentationId, i);
              allSlides = allSlides.concat(chunkData.slides);
              
              // Update progress
              toast({ 
                title: 'Loading...', 
                description: `Loaded ${allSlides.length}/${totalSlides} slides (batch ${i}/${totalChunks})`, 
                variant: 'default' 
              });
            }
            
            data.slides = allSlides;
            toast({ 
              title: 'Success!', 
              description: `All ${allSlides.length} slides loaded!`, 
              variant: 'default' 
            });
          } catch (error) {
            console.error('Error loading chunked slides:', error);
            toast.error('Failed to load slides');
            navigate('/');
            return;
          }
        }
        // Check if it's a trivia-imported presentation (needs on-demand slide loading)
        else if (data.type === 'trivia-imported') {
          const startTime = Date.now();
          
          try {
            // STEP 1: Try to load from cache first (fast path)
            let slidesLoaded = false;
            
            try {
              const metadata = await presentationAPI.getSlidesMetadata(presentationId);
              if (metadata?.hasGridFSSlides && metadata?.totalChunks > 0) {
                toast('From cache');
                
                let allSlides = [];
                for (let i = 0; i < metadata.totalChunks; i++) {
                  const chunkData = await presentationAPI.getSlideChunk(presentationId, i);
                  if (chunkData?.slides) {
                    allSlides = allSlides.concat(chunkData.slides);
                  }
                }
                
                if (allSlides.length > 0) {
                  data.slides = allSlides;
                  slidesLoaded = true;
                }
              }
            } catch (cacheErr) {
              // Cache unavailable - will fetch fresh
            }
            
            // STEP 2: If cache failed, fetch from SharePoint section by section
            if (!slidesLoaded) {
              toast('From SharePoint');
              
              const sectionsData = await presentationAPI.getSectionsList(presentationId);
              const sections = sectionsData?.sections || [];
              
              if (sections.length === 0) {
                throw new Error('No sections found');
              }
              
              let allSlides = [];
              let slideOrder = 0;
              const failedSections = [];
              
              // Helper function to fetch a section with retry logic
              const fetchSectionWithRetry = async (section, maxRetries = 3) => {
                let lastError = null;
                
                for (let attempt = 1; attempt <= maxRetries; attempt++) {
                  try {
                    console.log(`📦 Fetching section '${section.name}' (attempt ${attempt}/${maxRetries})`);
                    
                    const sectionData = await presentationAPI.fetchSection(presentationId, section.name, {
                      roundType: section.roundType,
                      roundOrder: section.roundOrder
                    });
                    
                    const sectionSlides = sectionData?.slides || [];
                    
                    if (sectionSlides.length === 0) {
                      console.warn(`⚠️ Section '${section.name}' returned 0 slides`);
                    } else {
                      console.log(`✅ Section '${section.name}' loaded: ${sectionSlides.length} slides`);
                    }
                    
                    return sectionSlides;
                    
                  } catch (err) {
                    lastError = err;
                    console.error(`❌ Section '${section.name}' attempt ${attempt} failed:`, err.message || err);
                    
                    if (attempt < maxRetries) {
                      // Exponential backoff: 1s, 2s, 4s
                      const delay = Math.pow(2, attempt - 1) * 1000;
                      console.log(`⏳ Retrying in ${delay}ms...`);
                      await new Promise(resolve => setTimeout(resolve, delay));
                    }
                  }
                }
                
                // All retries failed
                throw lastError || new Error(`Failed to load section '${section.name}' after ${maxRetries} attempts`);
              };
              
              for (let i = 0; i < sections.length; i++) {
                const section = sections[i];
                toast({ 
                  title: `Loading ${section.name}`, 
                  description: `${i + 1}/${sections.length}`, 
                  variant: 'default' 
                });
                
                try {
                  const sectionSlides = await fetchSectionWithRetry(section);
                  
                  for (const slide of sectionSlides) {
                    slide.order = slideOrder++;
                    allSlides.push(slide);
                  }
                  
                } catch (sectionErr) {
                  console.error(`🚨 Section '${section.name}' FAILED after all retries:`, sectionErr);
                  failedSections.push({
                    name: section.name,
                    type: section.type,
                    error: sectionErr.message || 'Unknown error'
                  });
                  
                  // Show warning toast for failed section
                  toast({ 
                    title: `⚠️ Failed: ${section.name}`, 
                    description: 'Continuing with other sections...', 
                    variant: 'destructive' 
                  });
                }
              }
              
              // VALIDATION: Check if any sections failed
              if (failedSections.length > 0) {
                console.error(`🚨 ${failedSections.length} sections failed to load:`, failedSections);
                toast({
                  title: `⚠️ ${failedSections.length} section(s) failed`,
                  description: `Failed: ${failedSections.map(s => s.name).join(', ')}. Try reloading.`,
                  variant: 'destructive'
                });
              }
              
              if (allSlides.length === 0) {
                throw new Error('No slides loaded');
              }
              
              // Log final summary
              console.log(`📊 SECTION LOADING COMPLETE:`);
              console.log(`   Total slides loaded: ${allSlides.length}`);
              console.log(`   Sections loaded: ${sections.length - failedSections.length}/${sections.length}`);
              if (failedSections.length > 0) {
                console.log(`   Failed sections: ${failedSections.map(s => s.name).join(', ')}`);
              }
              
              // DEBUG: Verify metadata is present after loading
              const roundTitlesFound = allSlides.filter(s => s.metadata?.isRoundTitle);
              console.log(`📊 VERIFICATION AFTER LOAD: Found ${roundTitlesFound.length} round titles in ${allSlides.length} slides`);
              roundTitlesFound.forEach((s, idx) => {
                console.log(`  Round title ${idx + 1}: slideIndex=${allSlides.indexOf(s)}, round=${s.metadata?.roundNumber}, type=${s.metadata?.roundType}`);
              });
              
              data.slides = allSlides;
              
              // Cache in background for next time
              presentationAPI.storeAllSlides(presentationId, allSlides).catch(() => {});
            }
            
            // STEP 3: Get location metadata AND round configuration from trivia presentation
            // FIRST: Use location from the main presentation response (now included for trivia-imported)
            if (data.location) {
              console.log(`[Editor] Location from main presentation data: "${data.location}"`);
            }
            
            try {
              const triviaData = await presentationAPI.getTriviaPresentation(presentationId);
              if (triviaData?.location) {
                data.location = triviaData.location;
                console.log(`[Editor] Location from trivia data: "${triviaData.location}"`);
              }
              // Store round configuration for Score Tracker
              if (triviaData?.numRounds) {
                data.numRounds = triviaData.numRounds;
                console.log(`[Editor] Loaded numRounds from trivia data: ${triviaData.numRounds}`);
              }
              if (triviaData?.roundTypes?.length > 0) {
                data.roundTypes = triviaData.roundTypes;
                console.log(`[Editor] Loaded roundTypes from trivia data: ${triviaData.roundTypes.join(', ')}`);
              }
              if (triviaData?.roundNames?.length > 0) {
                data.roundNames = triviaData.roundNames;
              }
              
              // FALLBACK: If no round config found in trivia data, try fetching from story-builds JSON
              if (!data.numRounds && triviaData?.locationFolder) {
                try {
                  // List available builds and find matching one
                  const buildsResponse = await storyBuildsAPI.listBuilds();
                  const builds = buildsResponse?.builds || [];
                  
                  // Find a build matching this location
                  const matchingBuild = builds.find(b => 
                    b.locationFolder === triviaData.locationFolder ||
                    b.location === data.location?.split('/').pop()
                  );
                  
                  if (matchingBuild) {
                    // Fetch the full build JSON
                    const buildData = await storyBuildsAPI.getBuild(
                      matchingBuild.locationFolder || matchingBuild.location,
                      matchingBuild.filename
                    );
                    
                    if (buildData) {
                      if (buildData.numRounds && !data.numRounds) {
                        data.numRounds = buildData.numRounds;
                        console.log(`[Editor] Loaded numRounds from story-builds JSON: ${buildData.numRounds}`);
                      }
                      if (buildData.roundTypes?.length > 0 && !data.roundTypes?.length) {
                        data.roundTypes = buildData.roundTypes;
                        console.log(`[Editor] Loaded roundTypes from story-builds JSON: ${buildData.roundTypes.join(', ')}`);
                      }
                      if (buildData.roundNames?.length > 0 && !data.roundNames?.length) {
                        data.roundNames = buildData.roundNames;
                      }
                    }
                  }
                } catch (buildErr) {
                  console.log('Could not load from story-builds:', buildErr.message);
                }
              }
            } catch (locErr) {
              console.log('Could not load trivia metadata:', locErr.message);
              // Location may still be available from the main presentation data (set above)
            }
            
            // FINAL LOCATION LOG - confirm what location will be used for overlays
            console.log(`[Editor] FINAL location for overlays: "${data.location || 'NONE'}"`);
            if (!data.location) {
              console.warn('[Editor] WARNING: No location available - overlays will NOT be loaded');
            }
            
            const loadTime = ((Date.now() - startTime) / 1000).toFixed(1);
            toast({ title: '✅ Loaded!', description: `${data.slides.length} slides (${loadTime}s)`, variant: 'default' });
            
            // STEP 4: ALWAYS auto-format on load to ensure latest formatting rules are applied.
            // Then apply/hydrate overlays.
            setShouldAutoFormat(true);
            
            if (data.location) {
              const hasOverlays = data.slides.some(s => s.elements?.some(e => e.zIndex === 1000 || e.type === 'overlay'));
              console.log(`[Editor] Overlay check - hasOverlays: ${hasOverlays}`);
              
              if (!hasOverlays) {
                console.log(`[Editor] No overlays found - will auto-init overlays after formatting`);
                setShouldAutoInitOverlays(true);
              } else {
                // HYDRATE OVERLAY CACHE - overlays exist but cache is empty
                const overlayPaths = new Set();
                for (const slide of data.slides) {
                  for (const el of (slide.elements || [])) {
                    if (el.type === 'overlay' && el.overlayId && !overlayCache.current[el.overlayId]) {
                      overlayPaths.add(el.overlayId);
                    }
                  }
                }
                
                if (overlayPaths.size > 0) {
                  console.log(`Hydrating overlay cache with ${overlayPaths.size} images...`);
                  toast({ title: '🎨 Loading Overlays...', description: `Loading ${overlayPaths.size} overlay images`, variant: 'default' });
                  
                  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
                  const API = `${BACKEND_URL}/api`;
                  
                  // MEMORY OPTIMIZATION: Load overlay images SEQUENTIALLY to prevent memory spikes
                  // Previously used Promise.all which loaded all images simultaneously,
                  // causing 100-300MB of concurrent memory usage
                  const pathsArray = Array.from(overlayPaths);
                  let loadedCount = 0;
                  
                  for (let i = 0; i < pathsArray.length; i++) {
                    const path = pathsArray[i];
                    try {
                      const imageResponse = await fetch(`${API}/overlays/image?path=${encodeURIComponent(path)}`);
                      if (imageResponse.ok) {
                        const imageData = await imageResponse.json();
                        if (imageData.success && imageData.dataUrl) {
                          overlayCache.current[path] = imageData.dataUrl;
                          loadedCount++;
                          
                          // Update progress toast
                          toast({ 
                            title: '🎨 Loading Overlays...', 
                            description: `Loaded ${loadedCount}/${pathsArray.length} overlay images`, 
                            variant: 'default' 
                          });
                        }
                      }
                    } catch (e) {
                      console.warn(`Failed to hydrate overlay: ${path}`, e);
                    }
                  }
                  
                  console.log(`Hydrated ${loadedCount}/${overlayPaths.size} overlays`);
                  if (loadedCount > 0) {
                    toast({ title: '✨ Overlays Ready!', description: `Loaded ${loadedCount} overlay images` });
                    // CRITICAL: Increment cache version to force re-render after hydration
                    // This ensures SlideCanvas components re-read the updated overlayCache
                    setOverlayCacheVersion(prev => prev + 1);
                    console.log(`[Editor] Overlay cache version incremented, cache has ${Object.keys(overlayCache.current).length} entries`);
                  } else {
                    console.warn(`[Editor] No overlays could be loaded from API`);
                  }
                } else {
                  console.log(`[Editor] No overlay paths to hydrate (overlays may already be in cache)`);
                }
              }
            }
            
          } catch (error) {
            console.error('Error loading trivia slides:', error);
            const errorMessage = error.response?.data?.detail || error.message || 'Unknown error';
            toast({ title: 'Error', description: `Failed to load: ${errorMessage}`, variant: 'destructive' });
            navigate('/');
            return;
          }
        }
        
        setPresentation(data);
        
        // Store presentation name for score saving
        if (data.name) {
          localStorage.setItem('currentPresentationName', data.name);
        }
        // Only trigger auto-init overlays if they weren't already applied during loading
        // This prevents double-application of overlays
        // Note: For trivia presentations, overlays are now applied inline during section loading
      } else {
        // Create new presentation if no ID found
        const userName = localStorage.getItem('userName') || 'Guest';
        const newPresentation = await presentationAPI.create({
          name: `New Presentation - ${new Date().toLocaleDateString()}`,
          createdBy: userName
        });
        setPresentation(newPresentation);
        localStorage.setItem('currentPresentationId', newPresentation.id);
      }
    } catch (error) {
      console.error('Error loading presentation:', error);
      toast.error('Failed to load presentation');
      navigate('/');
    } finally {
      setLoading(false);
    }
  };

  const handleAddSlide = useCallback(() => {
    const newSlide = createNewSlide(presentation.slides.length);
    setPresentation({
      ...presentation,
      slides: [...presentation.slides, newSlide]
    });
    setCurrentSlideIndex(presentation.slides.length);
    toast('New slide created successfully');
  }, [presentation]);

  const handleDeleteSlide = useCallback(() => {
    if (presentation.slides.length <= 1) {
      toast.error('Presentation must have at least one slide');
      return;
    }
    const newSlides = presentation.slides.filter((_, index) => index !== currentSlideIndex);
    setPresentation({ ...presentation, slides: newSlides });
    setCurrentSlideIndex(Math.max(0, currentSlideIndex - 1));
    toast('Slide removed successfully');
  }, [presentation, currentSlideIndex]);

  const handleAddText = useCallback(() => {
    const newElement = createNewTextElement(100, 100);
    const updatedSlides = [...presentation.slides];
    updatedSlides[currentSlideIndex] = {
      ...currentSlide,
      elements: [...currentSlide.elements, newElement]
    };
    setPresentation({ ...presentation, slides: updatedSlides });
    setSelectedElement(newElement);
  }, [presentation, currentSlideIndex, currentSlide]);

  const handleAddImage = useCallback(() => {
    const url = prompt('Enter image URL:');
    if (url) {
      const newElement = {
        id: `elem-${Date.now()}`,
        type: 'image',
        src: url,
        x: 100,
        y: 100,
        width: 300,
        height: 200
      };
      const updatedSlides = [...presentation.slides];
      updatedSlides[currentSlideIndex] = {
        ...currentSlide,
        elements: [...currentSlide.elements, newElement]
      };
      setPresentation({ ...presentation, slides: updatedSlides });
    }
  }, [presentation, currentSlideIndex, currentSlide]);

  const handleUpdateElement = useCallback((updatedElement) => {
    setPresentation(prev => {
      const updatedSlides = [...prev.slides];
      const slide = updatedSlides[currentSlideIndex];
      updatedSlides[currentSlideIndex] = {
        ...slide,
        elements: slide.elements.map((el) =>
          el.id === updatedElement.id ? updatedElement : el
        )
      };
      return { ...prev, slides: updatedSlides };
    });
    setSelectedElement(updatedElement);
  }, [currentSlideIndex]);

  const handleDeleteElement = useCallback((elementId) => {
    setPresentation(prev => {
      const updatedSlides = [...prev.slides];
      const slide = updatedSlides[currentSlideIndex];
      updatedSlides[currentSlideIndex] = {
        ...slide,
        elements: slide.elements.filter((el) => el.id !== elementId)
      };
      return { ...prev, slides: updatedSlides };
    });
    setSelectedElement(null);
  }, [currentSlideIndex]);

  const handleReorderSlides = useCallback((fromIndex, toIndex) => {
    setPresentation(prev => {
      const newSlides = [...prev.slides];
      const [removed] = newSlides.splice(fromIndex, 1);
      newSlides.splice(toIndex, 0, removed);
      
      // Update order property
      newSlides.forEach((slide, index) => {
        slide.order = index;
      });
      
      return { ...prev, slides: newSlides };
    });
    setCurrentSlideIndex(toIndex);
  }, []);

  const handleOpenScoreTracker = useCallback(() => {
    setIsScoreTrackerOpen(true);
  }, []);

  const handleCloseScoreTracker = useCallback(() => {
    setIsScoreTrackerOpen(false);
  }, []);

  // Helper function to calculate dynamic font size based on team name length
  // BULLETPROOF: Calculate dynamic font size with full validation
  const calculateDynamicFontSize = (teamName, baseFontSize, maxWidth) => {
    // CRASH FIX: Validate all inputs
    if (!teamName || typeof teamName !== 'string') {
      console.warn('calculateDynamicFontSize: Invalid teamName, using base font size');
      return baseFontSize || 48;
    }
    if (!baseFontSize || typeof baseFontSize !== 'number' || baseFontSize <= 0) {
      baseFontSize = 48; // Safe default
    }
    if (!maxWidth || typeof maxWidth !== 'number' || maxWidth <= 0) {
      maxWidth = 1200; // Safe default
    }
    
    const nameLength = teamName.length;
    
    // Approximate character width ratios for Lemonada font (decorative, wider than normal)
    // Lemonada is ~0.65x wider than standard fonts due to its cursive style
    const charWidthRatio = 0.65;
    
    // Calculate approximate text width at base font size
    const estimatedWidth = nameLength * (baseFontSize * charWidthRatio);
    
    // If text fits comfortably, use base font size
    if (estimatedWidth <= maxWidth) {
      return baseFontSize;
    }
    
    // Calculate reduced font size to fit within maxWidth
    // Add 10% padding to ensure comfortable fit
    const scaleFactor = (maxWidth * 0.9) / estimatedWidth;
    const adjustedFontSize = Math.floor(baseFontSize * scaleFactor);
    
    // Set minimum font size to maintain readability
    const minFontSize = baseFontSize * 0.4; // Don't go below 40% of base size
    
    return Math.max(minFontSize, adjustedFontSize);
  };

  const sendingScoresRef = useRef(false);
  const handleSendScores = async (teams, roundMode, rounds) => {
    // Prevent double-click race condition
    if (sendingScoresRef.current) return;
    sendingScoresRef.current = true;
    try {
      console.log('=== handleSendScores called ===');
      console.log('Teams:', teams?.length, 'Round Mode:', roundMode, 'Rounds:', rounds?.length);
      
      // CRASH FIX: Validate input parameters
      if (!teams || !Array.isArray(teams)) {
        console.error('handleSendScores: Invalid teams array');
        toast({ 
          title: 'Error', 
          description: 'Invalid team data received', 
          variant: 'destructive' 
        });
        return;
      }
      
      if (!rounds || !Array.isArray(rounds) || rounds.length === 0) {
        console.error('handleSendScores: Invalid rounds configuration');
        toast({ 
          title: 'Error', 
          description: 'Invalid round configuration', 
          variant: 'destructive' 
        });
        return;
      }
      
      if (!presentation?.slides || !Array.isArray(presentation.slides)) {
        console.error('handleSendScores: No presentation slides available');
        toast({ 
          title: 'Error', 
          description: 'Presentation not loaded correctly', 
          variant: 'destructive' 
        });
        return;
      }
      
      // Calculate top 3 teams with total scores - with robust null checks
      const teamsWithTotals = teams
        .filter(team => team && team.name && team.name.trim() !== '')
        .map(team => {
          // CRASH FIX: Ensure team.rounds exists and is an array
          const teamRounds = Array.isArray(team.rounds) ? team.rounds : [];
          const roundScores = teamRounds.slice(0, rounds.length).map((score, idx) => {
            const points = parseInt(score) || 0;
            // CRASH FIX: Bounds check before accessing multiplier
            const multiplier = rounds[idx]?.multiplier || 1;
            return points * multiplier;
          });
          const roundTotal = roundScores.reduce((sum, score) => sum + score, 0);
          const swagPoints = parseInt(team.swag) || 0;
          const total = roundTotal + swagPoints;
          
          return {
            name: team.name,
            swag: team.swag || '',
            total,
            roundScores // Keep round scores for debugging
          };
        })
        .sort((a, b) => b.total - a.total); // Sort descending
      
      const top3 = teamsWithTotals.slice(0, 3);
      console.log('Top 3 teams:', top3);
      
      // Find ALL score slides by checking metadata
      const scoreSlideIndices = [];
      presentation.slides.forEach((slide, index) => {
        if (slide?.metadata?.isScoreSlide) {
          scoreSlideIndices.push(index);
          console.log(`Found score slide at index ${index}, round: ${slide.metadata?.roundNumber}`);
        }
      });

      if (scoreSlideIndices.length === 0) {
        console.error('No score slides found in presentation');
        toast({ 
          title: 'No Score Slide', 
          description: 'No score slide found in presentation. Score slides may not have loaded correctly.', 
          variant: 'destructive' 
        });
        return;
      }
      
      console.log(`Found ${scoreSlideIndices.length} score slides:`, scoreSlideIndices);

      // Find the next UNFILLED score slide
      // A slide is "unfilled" if it has no text elements with score content
      let scoreSlideIndex = -1;
      for (const index of scoreSlideIndices) {
        const slide = presentation.slides[index];
        const hasScoreContent = slide.elements?.some(el => 
          el.type === 'text' && (el.id?.startsWith('score-') || el.id?.startsWith('rank-'))
        );
        
        if (!hasScoreContent) {
          scoreSlideIndex = index;
          console.log(`Using unfilled score slide at index ${index}`);
          break;
        }
      }

      // If all score slides are filled, use the last one
      if (scoreSlideIndex === -1) {
        scoreSlideIndex = scoreSlideIndices[scoreSlideIndices.length - 1];
        console.log(`All score slides filled, using last one at index ${scoreSlideIndex}`);
        toast({ 
          title: 'All Score Slides Filled', 
          description: 'Updating the last score slide', 
        });
      }

      // Generate score table as text elements with round info
      const scoreElements = generateScoreElements(teams, rounds);
      console.log(`Generated ${scoreElements.length} score elements`);

      // Update the score slide
      const updatedSlides = [...presentation.slides];
      updatedSlides[scoreSlideIndex] = {
        ...updatedSlides[scoreSlideIndex],
        elements: scoreElements
      };
      
      // Count filled score slides AFTER this update
      const filledScoreSlides = scoreSlideIndices.filter(index => {
        const slide = updatedSlides[index];
        // Check for our specific score elements
        return slide.elements?.some(el => 
          el.type === 'text' && (el.id?.startsWith('score-') || el.id?.startsWith('rank-'))
        );
      }).length;
      
      const totalRounds = scoreSlideIndices.length;
      const allRoundsComplete = filledScoreSlides >= totalRounds;
      
      console.log(`Filled score slides: ${filledScoreSlides}/${totalRounds}, All complete: ${allRoundsComplete}`);
      
      // POPULATE WINNERS SLIDES when ALL rounds are complete
      if (allRoundsComplete) {
        console.log('=== Populating winners slides ===');
        
        // Find all WINNERS slides
        const winnerSlideIndices = [];
        updatedSlides.forEach((slide, index) => {
          if (slide?.metadata?.roundType === 'WINNERS') {
            winnerSlideIndices.push({ 
              index, 
              slideIndexInRound: slide.metadata?.slideIndexInRound 
            });
            console.log(`Found WINNERS slide at index ${index}, slideIndexInRound: ${slide.metadata?.slideIndexInRound}`);
          }
        });
        
        console.log(`Found ${winnerSlideIndices.length} winner slides`);
        
        // BULLETPROOF: Wrap each winner slide update in try-catch
        // 3rd Place - Winners slide 2 (slideIndexInRound: 1)
        try {
          if (top3[2] && top3[2].name) {
            const thirdPlaceSlide = winnerSlideIndices.find(item => item.slideIndexInRound === 1);
            console.log(`3rd place slide:`, thirdPlaceSlide, 'Team:', top3[2].name);
            
            if (thirdPlaceSlide && thirdPlaceSlide.index < updatedSlides.length) {
              // Remove any existing winner elements before adding new ones
              const existingElements = updatedSlides[thirdPlaceSlide.index]?.elements || [];
              const cleanedElements = existingElements.filter(
                el => el && !el.id?.startsWith('winner-')
              );
              
              // Calculate dynamic font size for team name
              const nameFontSize = calculateDynamicFontSize(top3[2].name, 64, 1200);
              
              updatedSlides[thirdPlaceSlide.index] = {
                ...updatedSlides[thirdPlaceSlide.index],
                elements: [
                  ...cleanedElements,
                  {
                    id: 'winner-3rd-name',
                    type: 'text',
                    content: top3[2].name || 'Team 3',
                    x: 360,
                    y: 100,
                    width: 1200,
                    height: 100,
                    fontSize: nameFontSize,
                    fontWeight: 'bold',
                    color: '#FFFFFF',
                    textAlign: 'center',
                    fontFamily: 'Lemonada, cursive',
                    textShadow: '4px 4px 12px rgba(0,0,0,0.9), -2px -2px 8px rgba(0,0,0,0.7)'
                  },
                  {
                    id: 'winner-3rd-score',
                    type: 'text',
                    content: `${top3[2].total || 0} Points`,
                    x: 360,
                    y: 210,
                    width: 1200,
                    height: 80,
                    fontSize: 48,
                    fontWeight: 'bold',
                    color: '#FFD700',
                    textAlign: 'center',
                    fontFamily: 'Inter, sans-serif',
                    textShadow: '4px 4px 12px rgba(0,0,0,0.9), -2px -2px 8px rgba(0,0,0,0.7)'
                  }
                ]
              };
              console.log(`✓ Added 3rd place: ${top3[2].name}`);
            } else {
              console.warn('Could not find 3rd place slide (slideIndexInRound: 1)');
            }
          }
        } catch (err) {
          console.error('Error populating 3rd place slide:', err);
        }
        
        // 2nd Place - Winners slide 3 (slideIndexInRound: 2)
        try {
          if (top3[1] && top3[1].name) {
            const secondPlaceSlide = winnerSlideIndices.find(item => item.slideIndexInRound === 2);
            console.log(`2nd place slide:`, secondPlaceSlide, 'Team:', top3[1].name);
            
            if (secondPlaceSlide && secondPlaceSlide.index < updatedSlides.length) {
              // Remove any existing winner elements before adding new ones
              const existingElements = updatedSlides[secondPlaceSlide.index]?.elements || [];
              const cleanedElements = existingElements.filter(
                el => el && !el.id?.startsWith('winner-')
              );
              
              // Calculate dynamic font size for team name
              const nameFontSize = calculateDynamicFontSize(top3[1].name, 64, 1200);
              
              updatedSlides[secondPlaceSlide.index] = {
                ...updatedSlides[secondPlaceSlide.index],
                elements: [
                  ...cleanedElements,
                  {
                    id: 'winner-2nd-name',
                    type: 'text',
                    content: top3[1].name || 'Team 2',
                    x: 360,
                    y: 100,
                    width: 1200,
                    height: 100,
                    fontSize: nameFontSize,
                    fontWeight: 'bold',
                    color: '#FFFFFF',
                    textAlign: 'center',
                    fontFamily: 'Lemonada, cursive',
                    textShadow: '4px 4px 12px rgba(0,0,0,0.9), -2px -2px 8px rgba(0,0,0,0.7)'
                  },
                  {
                    id: 'winner-2nd-score',
                    type: 'text',
                    content: `${top3[1].total || 0} Points`,
                    x: 360,
                    y: 210,
                    width: 1200,
                    height: 80,
                    fontSize: 48,
                    fontWeight: 'bold',
                    color: '#FFD700',
                    textAlign: 'center',
                    fontFamily: 'Inter, sans-serif',
                    textShadow: '4px 4px 12px rgba(0,0,0,0.9), -2px -2px 8px rgba(0,0,0,0.7)'
                  }
                ]
              };
              console.log(`✓ Added 2nd place: ${top3[1].name}`);
            } else {
              console.warn('Could not find 2nd place slide (slideIndexInRound: 2)');
            }
          }
        } catch (err) {
          console.error('Error populating 2nd place slide:', err);
        }
        
        // 1st Place - Winners slide 4 (slideIndexInRound: 3)
        try {
          if (top3[0] && top3[0].name) {
            const firstPlaceSlide = winnerSlideIndices.find(item => item.slideIndexInRound === 3);
            console.log(`1st place slide:`, firstPlaceSlide, 'Team:', top3[0].name);
            
            if (firstPlaceSlide && firstPlaceSlide.index < updatedSlides.length) {
              // Remove any existing winner elements before adding new ones
              const existingElements = updatedSlides[firstPlaceSlide.index]?.elements || [];
              const cleanedElements = existingElements.filter(
                el => el && !el.id?.startsWith('winner-')
              );
              
              // Calculate dynamic font size for team name (1st place has larger base size)
              const nameFontSize = calculateDynamicFontSize(top3[0].name, 72, 1200);
              
              updatedSlides[firstPlaceSlide.index] = {
                ...updatedSlides[firstPlaceSlide.index],
                elements: [
                  ...cleanedElements,
                  {
                    id: 'winner-1st-name',
                    type: 'text',
                    content: top3[0].name || 'Winner',
                    x: 360,
                    y: 100,
                    width: 1200,
                    height: 120,
                    fontSize: nameFontSize,
                    fontWeight: 'bold',
                    color: '#FFD700',
                    textAlign: 'center',
                    fontFamily: 'Lemonada, cursive',
                    textShadow: '4px 4px 12px rgba(0,0,0,0.9), -2px -2px 8px rgba(0,0,0,0.7)'
                  },
                  {
                    id: 'winner-1st-score',
                    type: 'text',
                    content: `${top3[0].total || 0} Points`,
                    x: 360,
                    y: 230,
                    width: 1200,
                    height: 80,
                    fontSize: 56,
                    fontWeight: 'bold',
                    color: '#FFD700',
                    textAlign: 'center',
                    fontFamily: 'Inter, sans-serif',
                    textShadow: '4px 4px 12px rgba(0,0,0,0.9), -2px -2px 8px rgba(0,0,0,0.7)'
                  }
                ]
              };
              console.log(`✓ Added 1st place: ${top3[0].name}`);
            } else {
              console.warn('Could not find 1st place slide (slideIndexInRound: 3)');
            }
          }
        } catch (err) {
          console.error('Error populating 1st place slide:', err);
        }
      } // End of allRoundsComplete check

      setPresentation({
        ...presentation,
        slides: updatedSlides
      });

      // Force navigate to the score slide and re-render
      setCurrentSlideIndex(prev => {
        // If already on the score slide, toggle away and back to force re-render
        if (prev === scoreSlideIndex) {
          setTimeout(() => setCurrentSlideIndex(scoreSlideIndex), 50);
          return Math.max(0, scoreSlideIndex - 1);
        }
        return scoreSlideIndex;
      });

      // Get round info for better feedback
      const roundNumber = scoreSlideIndices.indexOf(scoreSlideIndex) + 1;
      
      if (allRoundsComplete) {
        const winnerCount = top3.length;
        toast({ 
          title: '🏆 Game Complete!', 
          description: `All ${totalRounds} rounds scored! Winners populated: ${winnerCount} teams` 
        });
      } else {
        toast({ 
          title: 'Round Scored', 
          description: `Round ${roundNumber}/${totalRounds} complete. ${totalRounds - filledScoreSlides} rounds remaining` 
        });
      }

      // Skip auto-save during score updates to prevent Out of Memory crashes.
      // Serializing 80+ slides with overlay data to JSON on every round score is too expensive.
      // Scores are stored in localStorage and slides are saved when user clicks "Save" or "End Presentation".
      console.log('[ScoreTracker] Score update applied to slides (auto-save deferred to prevent OOM)');

    } catch (error) {
      console.error('Error sending scores:', error);
      toast({ 
        title: 'Error', 
        description: `Failed to update score slide: ${error.message || 'Unknown error'}`, 
        variant: 'destructive' 
      });
    } finally {
      sendingScoresRef.current = false;
    }
  };

  const generateScoreElements = (teams, rounds) => {
    // Create a title - centered on the X axis (slide width = 1920px)
    const titleWidth = 1100;
    const elements = [{
      id: 'score-title',
      type: 'text',
      content: 'CURRENT STANDINGS',
      x: (1920 - titleWidth) / 2,  // Center horizontally: (1920 - 1100) / 2 = 410
      y: 100,
      width: titleWidth,
      height: 70,
      fontSize: 48,
      fontWeight: 'bold',
      color: '#FFD700',
      textAlign: 'center',
      fontFamily: 'Lemonada, cursive'
    }];

    // Add round headers - more space below title
    const headerY = 200;
    const roundStartX = 800;
    const roundWidth = 100;
    
    rounds.forEach((round, idx) => {
      elements.push({
        id: `header-${idx}`,
        type: 'text',
        content: round.label,
        x: roundStartX + (idx * roundWidth),
        y: headerY,
        width: roundWidth,
        height: 40,
        fontSize: 24,
        fontWeight: 'bold',
        color: '#FFD700',
        textAlign: 'center',
        fontFamily: 'Inter, sans-serif'
      });
    });
    
    // Total header
    elements.push({
      id: 'header-total',
      type: 'text',
      content: 'TOTAL',
      x: roundStartX + (rounds.length * roundWidth),
      y: headerY,
      width: 120,
      height: 40,
      fontSize: 24,
      fontWeight: 'bold',
      color: '#00FF00',
      textAlign: 'center',
      fontFamily: 'Inter, sans-serif'
    });

    // Add ALL team scores - dynamically adjust spacing to fit
    const allTeams = teams; // Include all teams, not just top 10
    const startY = 270;
    const availableHeight = 1080 - startY - 50; // Screen height minus used space and bottom margin
    const maxRowHeight = 62;
    const minRowHeight = 35;
    // Calculate row height based on number of teams
    const calculatedRowHeight = Math.max(minRowHeight, Math.min(maxRowHeight, availableHeight / allTeams.length));
    const rowHeight = calculatedRowHeight;

    // Dynamic font sizes based on row height
    const rankFontSize = Math.max(20, Math.min(32, rowHeight * 0.6));
    const nameFontSize = Math.max(18, Math.min(28, rowHeight * 0.5));
    const roundFontSize = Math.max(16, Math.min(24, rowHeight * 0.45));
    const totalFontSize = Math.max(20, Math.min(32, rowHeight * 0.6));
    
    allTeams.forEach((team, index) => {
      // CRASH FIX: Skip invalid team entries
      if (!team || !team.name) return;
      
      const currentY = startY + (index * rowHeight);
      const elementHeight = Math.max(30, rowHeight - 10);
      
      // Rank
      elements.push({
        id: `rank-${index}`,
        type: 'text',
        content: `${index + 1}.`,
        x: 100,
        y: currentY,
        width: 60,
        height: elementHeight,
        fontSize: rankFontSize,
        fontWeight: 'bold',
        color: '#FFD700',
        textAlign: 'right',
        fontFamily: 'Inter, sans-serif'
      });

      // Team Name
      elements.push({
        id: `name-${index}`,
        type: 'text',
        content: team.name || '',
        x: 180,
        y: currentY,
        width: 580,
        height: elementHeight,
        fontSize: nameFontSize,
        fontWeight: 'normal',
        color: '#FFFFFF',
        textAlign: 'left',
        fontFamily: 'Inter, sans-serif'
      });
      
      // Round scores - with bounds checking
      const teamRounds = Array.isArray(team.rounds) ? team.rounds : [];
      teamRounds.slice(0, rounds.length).forEach((score, roundIdx) => {
        const points = parseInt(score) || 0;
        // CRASH FIX: Bounds check before accessing multiplier
        const multiplier = rounds[roundIdx]?.multiplier || 1;
        const multipliedScore = points * multiplier;
        
        elements.push({
          id: `round-${index}-${roundIdx}`,
          type: 'text',
          content: String(multipliedScore),
          x: roundStartX + (roundIdx * roundWidth),
          y: currentY,
          width: roundWidth,
          height: 50,
          fontSize: 24,
          fontWeight: 'normal',
          color: '#FFFFFF',
          textAlign: 'center',
          fontFamily: 'Inter, sans-serif'
        });
      });

      // Total Score
      elements.push({
        id: `total-${index}`,
        type: 'text',
        content: String(team.total),
        x: roundStartX + (rounds.length * roundWidth),
        y: currentY,
        width: 120,
        height: 50,
        fontSize: 32,
        fontWeight: 'bold',
        color: '#00FF00',
        textAlign: 'center',
        fontFamily: 'Inter, sans-serif'
      });
      
      // Bottom separator line - extends from team name area to total score
      // Using a thin text element as a visual line divider
      elements.push({
        id: `separator-${index}`,
        type: 'text',
        content: '─'.repeat(120), // Extended to cover full width
        x: 100,
        y: currentY + rowHeight - 8, // Position just below the row content
        width: 1720, // Full width from rank to beyond total
        height: 10,
        fontSize: 12,
        fontWeight: 'normal',
        color: 'rgba(255, 255, 255, 0.25)', // 5% more white - increased from ~17% to ~25% opacity
        textAlign: 'left',
        fontFamily: 'monospace'
      });
    });

    return elements;
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      
      // For trivia-imported presentations, use GridFS storage
      if (presentation.type === 'trivia-imported') {
        presentationAPI.storeAllSlides(presentation.id, presentation.slides).catch(() => {});
        toast('Presentation saved to GridFS successfully');
      } else {
        // Regular presentations use direct MongoDB update
        await presentationAPI.update(presentation.id, {
          slides: presentation.slides,
          name: presentation.name
        });
        toast('Presentation saved successfully');
      }
    } catch (error) {
      console.error('Error saving presentation:', error);
      toast.error('Failed to save presentation');
    } finally {
      setSaving(false);
    }
  };

  const triggerAutoOverlays = async () => {
    if (!presentation?.location || !presentation?.slides || slideOp === 'overlaying') {
      console.log(`Skipping auto-overlays - location: "${presentation?.location}", slides: ${presentation?.slides?.length || 0}, op: ${slideOp}`);
      return;
    }

    try {
      setShouldAutoInitOverlays(false);
      
      console.log('=== TRIGGER AUTO OVERLAYS START (MEMORY OPTIMIZED) ===');
      console.log(`Location: "${presentation.location}"`);
      console.log(`Working with ${presentation.slides.length} slides`);
      
      toast('Fetching overlay metadata');

      const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
      const API = `${BACKEND_URL}/api`;
      
      // Extract location name - handle both full SharePoint paths and clean names
      // Full path: "01_Trivia/Web App/00_Builder/02_Locations/04_WP Gilbert" -> "04_WP Gilbert"
      // Clean name: "WP Gilbert" -> "WP Gilbert"
      // Strip numeric prefix for API call: "04_WP Gilbert" -> "WP Gilbert"
      let locationName = presentation.location.split('/').pop();
      // Remove numeric prefix if present (e.g., "04_WP Gilbert" -> "WP Gilbert")
      const cleanLocationName = locationName.replace(/^\d+_/, '');
      console.log(`Overlay lookup: raw="${locationName}", clean="${cleanLocationName}"`);
      
      // STEP 1: Get overlay METADATA (lightweight - no image downloads)
      // Try clean name first, fall back to raw name
      let metadataResponse = await fetch(`${API}/overlays/metadata/${encodeURIComponent(cleanLocationName)}`);
      let metadataResult = metadataResponse.ok ? await metadataResponse.json() : null;
      
      // If clean name returned no overlays, try the raw name (with prefix)
      if ((!metadataResult?.overlays?.length) && cleanLocationName !== locationName) {
        console.log(`No overlays for clean name "${cleanLocationName}", trying raw "${locationName}"`);
        metadataResponse = await fetch(`${API}/overlays/metadata/${encodeURIComponent(locationName)}`);
        metadataResult = metadataResponse.ok ? await metadataResponse.json() : null;
      }
      
      if (!metadataResult || !metadataResponse.ok) {
        throw new Error('Failed to fetch overlay metadata');
      }
      
      const overlayMetadata = metadataResult.overlays || [];
      
      if (overlayMetadata.length === 0) {
        toast('No overlays available for this location');
        return;
      }
      
      // Create lookup maps from metadata
      const overlayByRound = {};
      let answerOverlayMeta = null;
      let sponsorOverlayMeta = null;
      
      for (const overlay of overlayMetadata) {
        if (overlay.name.toLowerCase().includes('answer')) {
          answerOverlayMeta = overlay;
        } else if (overlay.name.includes('99_Sponsor')) {
          sponsorOverlayMeta = overlay;
        } else if (overlay.roundNumber) {
          overlayByRound[overlay.roundNumber] = overlay;
        }
      }
      
      // STEP 2: Identify which overlays we need and which slides need them
      // MEMORY OPTIMIZATION: Build a sparse map of slideIndex -> overlayPath instead of copying array
      const neededOverlayPaths = new Set();
      const slideOverlayMap = new Map(); // slideIndex -> overlayPath
      
      // Single pass through slides to identify needs
      for (let i = 0; i < presentation.slides.length; i++) {
        const metadata = presentation.slides[i].metadata || {};
        
        if (metadata.isRoundTitle) {
          const roundNum = metadata.roundNumber;
          const roundType = metadata.roundType;
          const roundOverlayMeta = overlayByRound[roundNum];
          
          if (roundOverlayMeta) {
            neededOverlayPaths.add(roundOverlayMeta.path);
            
            // Map slides that need this overlay
            if (roundType === 'MC' || roundType === 'REG' || roundType === 'MISC') {
              for (let j = 1; j <= 10; j++) slideOverlayMap.set(i + j, roundOverlayMeta.path);
              if (answerOverlayMeta) {
                neededOverlayPaths.add(answerOverlayMeta.path);
                slideOverlayMap.set(i + 13, answerOverlayMeta.path);
              }
            } else if (roundType === 'MYS') {
              for (let j = 1; j <= 9; j++) slideOverlayMap.set(i + j, roundOverlayMeta.path);
              if (answerOverlayMeta) {
                neededOverlayPaths.add(answerOverlayMeta.path);
                slideOverlayMap.set(i + 12, answerOverlayMeta.path);
              }
            } else if (roundType === 'BIG') {
              slideOverlayMap.set(i + 1, roundOverlayMeta.path);
              for (let j = 3; j <= 6; j++) slideOverlayMap.set(i + j, roundOverlayMeta.path);
            }
          }
        }
        
        // Sponsor slides
        if (metadata.roundType === 'SPONSOR' && sponsorOverlayMeta) {
          neededOverlayPaths.add(sponsorOverlayMeta.path);
        }
      }
      
      // Handle sponsor overlay (second-to-last sponsor slide)
      if (sponsorOverlayMeta) {
        const sponsorIndices = [];
        for (let i = 0; i < presentation.slides.length; i++) {
          if (presentation.slides[i].metadata?.roundType === 'SPONSOR') {
            sponsorIndices.push(i);
          }
        }
        if (sponsorIndices.length >= 2) {
          slideOverlayMap.set(sponsorIndices[sponsorIndices.length - 2], sponsorOverlayMeta.path);
        } else if (sponsorIndices.length === 1) {
          slideOverlayMap.set(sponsorIndices[0], sponsorOverlayMeta.path);
        }
      }
      
      console.log(`Need ${neededOverlayPaths.size} overlays for ${slideOverlayMap.size} slides`);
      toast({ title: '🎨 Downloading...', description: `Loading ${neededOverlayPaths.size} overlays`, variant: 'default' });
      
      // STEP 3: Download needed overlays sequentially
      let loadedCount = 0;
      for (const path of neededOverlayPaths) {
        if (overlayCache.current[path]) {
          loadedCount++;
          continue;
        }
        
        try {
          const imageResponse = await fetch(`${API}/overlays/image?path=${encodeURIComponent(path)}`);
          if (imageResponse.ok) {
            const imageData = await imageResponse.json();
            if (imageData.success && imageData.dataUrl) {
              overlayCache.current[path] = imageData.dataUrl;
              loadedCount++;
              toast({ 
                title: '🎨 Downloading...', 
                description: `Loaded ${loadedCount}/${neededOverlayPaths.size} overlays`, 
                variant: 'default' 
              });
            }
          }
        } catch (e) {
          console.warn(`Failed to load overlay: ${path}`, e);
        }
      }
      
      toast({ title: '🎨 Applying...', description: `Applying overlays to slides`, variant: 'default' });
      
      // STEP 4: Apply overlays using BATCHED state updates
      // MEMORY OPTIMIZATION: Use functional setState and only modify slides that need changes
      const BATCH_SIZE = 20;
      const slideIndicesToUpdate = Array.from(slideOverlayMap.keys()).filter(idx => 
        idx >= 0 && idx < presentation.slides.length && overlayCache.current[slideOverlayMap.get(idx)]
      );
      
      let appliedCount = 0;
      
      // Process in batches to prevent memory spikes
      for (let batchStart = 0; batchStart < slideIndicesToUpdate.length; batchStart += BATCH_SIZE) {
        const batchEnd = Math.min(batchStart + BATCH_SIZE, slideIndicesToUpdate.length);
        const batchIndices = slideIndicesToUpdate.slice(batchStart, batchEnd);
        // React 18 auto-batches state updates — no manual delay needed
        
        // MEMORY OPTIMIZATION: Functional state update with targeted mutations
        setPresentation(prev => {
          // Create shallow copy of slides array
          const newSlides = [...prev.slides];
          
          // Only modify slides in this batch
          for (const slideIndex of batchIndices) {
            const overlayPath = slideOverlayMap.get(slideIndex);
            if (!overlayPath || !overlayCache.current[overlayPath]) continue;
            
            // Clone only this specific slide
            const oldSlide = newSlides[slideIndex];
            const newElements = (oldSlide.elements || []).filter(e => e.zIndex !== 1000);
            
            // Add overlay reference
            newElements.push({
              id: `overlay-${slideIndex}-${Date.now()}`,
              type: 'overlay',
              overlayId: overlayPath,
              x: 0,
              y: 0,
              width: 1920,
              height: 1080,
              zIndex: 1000
            });
            
            // Replace slide with updated version
            newSlides[slideIndex] = { ...oldSlide, elements: newElements };
            appliedCount++;
          }
          
          return { ...prev, slides: newSlides };
        });
        
        // Update progress
        toast({ 
          title: '🎨 Applying...', 
          description: `Applied ${Math.min(batchEnd, slideIndicesToUpdate.length)}/${slideIndicesToUpdate.length} overlays`, 
          variant: 'default' 
        });
      }
      
      // ============================================================
      // POST-OVERLAY REVIEW FORMATTING PASS
      // After ALL overlays are applied, re-format review slides in ONE atomic state update.
      // This guarantees review formatting is NEVER overwritten by overlays.
      // ============================================================
      setPresentation(prev => {
        const SLIDE_W = 1920;
        const SLIDE_H = 1080;
        const NINE_SIXTEEN_W = Math.round(SLIDE_H * 9 / 16);
        const NINE_SIXTEEN_X = Math.floor((SLIDE_W - NINE_SIXTEEN_W) / 2);
        const CONTENT_W = NINE_SIXTEEN_W - 100;
        const CONTENT_X = NINE_SIXTEEN_X + 50;
        const MAX_BOTTOM = 905;
        
        const newSlides = [...prev.slides];
        let reviewCount = 0;
        
        for (let i = 0; i < newSlides.length; i++) {
          const slide = newSlides[i];
          const meta = slide?.metadata || {};
          const rt = meta.roundType || '';
          const pos = meta.slideIndexInRound != null ? Number(meta.slideIndexInRound) : -1;
          
          // ONLY use posInRound for review detection — no content guessing
          // This prevents false positives on answer slides
          const isReview = (['MC', 'REG', 'MISC'].includes(rt) && pos === 11) || (rt === 'MYS' && pos === 10);
          
          if (isReview) {
            // Clone slide and re-format
            const cloned = { ...slide, elements: slide.elements.map(e => ({ ...e })) };
            const texts = cloned.elements.filter(e => e.type === 'text');
            const sorted = [...texts].sort((a, b) => a.y - b.y);
            
            if (sorted.length < 2) continue;
            
            // Title
            const title = sorted[0];
            title.x = CONTENT_X; title.width = CONTENT_W;
            title.y = 30; title.height = 80;
            title.textAlign = 'center'; title.color = '#FFD700';
            title.fontFamily = 'Lemonada, cursive'; title.fontWeight = 'bold'; title.fontSize = 48;
            
            // Questions
            const questions = sorted.slice(1);
            const GAP = 50;
            const FIRST_Y = 160;
            const BASE_FONT = 36;
            const LINE_H = 1.35;
            const itemH = Math.ceil(BASE_FONT * LINE_H);
            const totalNeeded = (questions.length * itemH) + ((questions.length - 1) * GAP);
            const available = MAX_BOTTOM - FIRST_Y;
            const actualGap = totalNeeded > available
              ? Math.max(5, Math.floor((available - questions.length * itemH) / Math.max(questions.length - 1, 1)))
              : GAP;
            
            const RX = 25;
            const RW = SLIDE_W - 50;
            const CHAR_R = 0.55;
            
            questions.forEach((el, qi) => {
              const len = (el.content || '').length;
              const fits = len * BASE_FONT * CHAR_R <= RW;
              el.x = RX; el.width = RW;
              el.y = FIRST_Y + (qi * (itemH + actualGap));
              el.height = itemH;
              el.textAlign = 'left'; el.color = '#FFFFFF';
              el.fontSize = fits ? BASE_FONT : Math.max(16, Math.floor(RW / (len * CHAR_R)));
              el.fontWeight = 'normal'; el.fontFamily = 'Inter, sans-serif';
              el.lineHeight = LINE_H; el.overflow = 'hidden';
            });
            
            // MYS: last item is "Theme?" — centered yellow
            if (rt === 'MYS' && questions.length > 0) {
              const theme = questions[questions.length - 1];
              const lastQ = questions.length > 1 ? questions[questions.length - 2] : null;
              const qBottom = lastQ ? (lastQ.y + lastQ.height) : FIRST_Y;
              theme.x = NINE_SIXTEEN_X; theme.width = NINE_SIXTEEN_W;
              theme.y = Math.max(Math.round(SLIDE_H / 2) - 25, qBottom + 25);
              theme.height = 50; theme.textAlign = 'center'; theme.color = '#FFD700';
              theme.fontFamily = 'Lemonada, cursive'; theme.fontWeight = 'bold'; theme.fontSize = 36;
            }
            
            newSlides[i] = cloned;
            reviewCount++;
          }
        }
        
        if (reviewCount > 0) {
          console.log(`[Overlays] Post-overlay review formatting: fixed ${reviewCount} review slides`);
        }
        return { ...prev, slides: newSlides };
      });
      
      // Trigger re-render
      setOverlayCacheVersion(prev => prev + 1);
      
      toast({ 
        title: '✨ Overlays Applied!', 
        description: `Applied ${appliedCount} overlays` 
      });
      console.log(`Applied ${appliedCount} overlays (memory optimized)`);
      
    } catch (error) {
      console.error('Error in auto-overlay application:', error);
      toast({ 
        title: '⚠️ Overlay Error', 
        description: error.message || 'Failed to apply overlays', 
        variant: 'destructive' 
      });
    } finally {
      // slideOp reset is handled by the useEffect caller
    }
  };

  /**
   * Apply formatting rules to all slides
   * 
   * RULES:
   * 1. 9:16 centered area (608px wide) with 50px internal buffer = 508px content width
   * 2. All question text within this buffered 9:16 area (excluding review, winners, final scores)
   * 3. BIG Question answers: Centered block, left-aligned text, same left edge for all items
   * 4. MC options: Yellow, left-aligned within 9:16 area
   * 5. Review slides: Title yellow Lemonada, items white left-aligned
   * 
   * MEMORY OPTIMIZATION: Uses batched processing with UI breathing room
   */
  const applyFormatting = async () => {
    if (!presentation?.slides || slideOp === 'formatting') return;
    
    try {
      setShouldAutoFormat(false);
      
      toast('Applying layout rules');
      
      // ========== CONSTANTS ==========
      const SLIDE_W = 1920;
      const SLIDE_H = 1080;
      const NINE_SIXTEEN_W = Math.round(SLIDE_H * 9 / 16); // 608px (exact 9:16 of height)
      const NINE_SIXTEEN_X = Math.floor((SLIDE_W - NINE_SIXTEEN_W) / 2); // 656px - left edge of 9:16 area
      
      // Universal 50px buffer on left and right of 9:16 area for ALL questions and answers
      const BUFFER = 50;
      const CONTENT_W = NINE_SIXTEEN_W - (BUFFER * 2); // 508px
      const CONTENT_X = NINE_SIXTEEN_X + BUFFER; // 706px
      
      // Answer X position: 175px to the right of 9:16 left side (for options and answers)
      const ANSWER_X = NINE_SIXTEEN_X + 175; // 831px
      
      // Question top edges by round type
      const MC_QUESTION_TOP = 150;      // MC questions start at y=150
      const REG_QUESTION_TOP = 250;     // REG/MISC/MYS questions start at y=250
      
      // Answer reveal slides (same for MC, REG, MISC, MYS)
      const ANSWER_TOP = 150;           // First answer at y=150
      const ANSWER_SPACING = 75;        // 75px between answers
      
      // BIG question slides
      const BIG_QUESTION_TOP = 250;     // BIG question/review title starts at y=250
      const BIG_SPACING = 100;          // 100px spacing between BIG question text boxes
      
      // BIG answer slides
      const BIG_ANSWER_TOP = 225;       // BIG answer slide starts at y=225 (no title)
      // Note: BIG answers use CONTENT_X + 50 offset and 68px spacing (defined inline)
      
      const CONTROL_TOP = 930; // Audience control panel top
      const MAX_BOTTOM = CONTROL_TOP - 25; // 905px - elements must end above this
      
      // ========== HELPER FUNCTIONS ==========
      const dynamicFontSize = (textLen, base = 36, min = 22) => {
        if (textLen > 250) return min;
        if (textLen > 180) return min + 4;
        if (textLen > 120) return min + 8;
        if (textLen > 60) return base - 4;
        return base;
      };
      
      /**
       * REVIEW SLIDE FORMATTER
       * Unified formatting for all review slides (MC, REG, MISC, MYS).
       * Rules:
       * 1. 50px buffer from left/right of 9:16 area (CONTENT_X, CONTENT_W)
       * 2. 25px gap between each text box (top & bottom)
       * 3. 25px gap from title bottom to first question
       * 4. All questions fit on one line — font size reduced as needed
       */
      const formatReviewSlide = (titleEl, questionEls, options = {}) => {
        const { lastItemSpecial = false } = options;
        
        // ---- TITLE ----
        const TITLE_Y = 30;
        const TITLE_H = 80;
        if (titleEl) {
          titleEl.x = CONTENT_X;
          titleEl.width = CONTENT_W;
          titleEl.y = TITLE_Y;
          titleEl.height = TITLE_H;
          titleEl.textAlign = 'center';
          titleEl.color = '#FFD700';
          titleEl.fontFamily = 'Lemonada, cursive';
          titleEl.fontWeight = 'bold';
          titleEl.fontSize = 48;
        }
        
        if (!questionEls || questionEls.length === 0) return;
        
        // ---- QUESTIONS ----
        // Text boxes span the full slide width with 25px buffer on each side
        const REVIEW_BUFFER = 25;
        const REVIEW_X = REVIEW_BUFFER;                     // 25px from left edge
        const REVIEW_W = SLIDE_W - (REVIEW_BUFFER * 2);     // 1920 - 50 = 1870px wide
        
        const GAP = 50;
        const FIRST_Q_TOP = TITLE_Y + TITLE_H + GAP; // 30 + 80 + 50 = 160
        const maxAvailableHeight = MAX_BOTTOM - FIRST_Q_TOP; // 905 - 160 = 745
        
        // Base font size: 33px + 10% = 36px
        const BASE_FONT = 36;
        const LINE_HEIGHT = 1.35;
        const CHAR_WIDTH_RATIO = 0.55; // Approximate for Inter font
        const itemHeight = Math.ceil(BASE_FONT * LINE_HEIGHT); // 41px
        
        // Verify all items fit vertically with gaps
        const totalNeeded = (questionEls.length * itemHeight) + ((questionEls.length - 1) * GAP);
        let actualGap = GAP;
        
        if (totalNeeded > maxAvailableHeight) {
          actualGap = Math.max(5, Math.floor((maxAvailableHeight - (questionEls.length * itemHeight)) / Math.max(questionEls.length - 1, 1)));
        }
        
        questionEls.forEach((el, i) => {
          // Per-question font: use base size, but shrink ONLY this question if it overflows
          const textLen = (el.content || '').length;
          const fitsAtBase = textLen * BASE_FONT * CHAR_WIDTH_RATIO <= REVIEW_W;
          let qFontSize = BASE_FONT;
          if (!fitsAtBase && textLen > 0) {
            qFontSize = Math.max(16, Math.floor(REVIEW_W / (textLen * CHAR_WIDTH_RATIO)));
          }
          
          el.x = REVIEW_X;
          el.width = REVIEW_W;
          el.y = FIRST_Q_TOP + (i * (itemHeight + actualGap));
          el.height = itemHeight;
          el.textAlign = 'left';
          el.color = '#FFFFFF';
          el.fontSize = qFontSize;
          el.fontWeight = 'normal';
          el.fontFamily = 'Inter, sans-serif';
          el.lineHeight = LINE_HEIGHT;
          el.overflow = 'hidden';
        });
      };
      
      // MEMORY OPTIMIZATION: Function to format a single slide (returns null if no changes needed)
      const formatSlide = (slide, slideIdx) => {
        const meta = slide.metadata || {};
        const roundType = meta.roundType || '';
        const rawPos = meta.slideIndexInRound;
        const posInRound = rawPos != null ? Number(rawPos) : -1;
        
        // Skip non-trivia slides
        if (['WINNERS', 'SCORES', 'SPONSOR', 'TOTAL'].includes(roundType)) {
          return null;
        }
        
        const hasTextElements = slide.elements?.some(el => el.type === 'text');
        if (!hasTextElements) return null;
        
        const newSlide = { ...slide, elements: slide.elements.map(el => ({ ...el })) };
        const texts = newSlide.elements.filter(el => el.type === 'text');
        if (!texts.length) return null;
        
        // ============================================================
        // REVIEW SLIDE HANDLER — MC/REG/MISC (posInRound 11), MYS (posInRound 10)
        // ============================================================
        const isReviewPos = (
          (['MC', 'REG', 'MISC'].includes(roundType) && posInRound === 11) ||
          (roundType === 'MYS' && posInRound === 10)
        );
        
        if (isReviewPos) {
          const sorted = [...texts].sort((a, b) => a.y - b.y);
          
          if (roundType === 'MYS') {
            // MYS review: title + questions 1-9 standard, question 10 centered yellow
            const regularItems = sorted.slice(1, -1);
            const themeItem = sorted[sorted.length - 1];
            formatReviewSlide(sorted[0], regularItems);
            
            if (themeItem) {
              const lastRegular = regularItems.length > 0 ? regularItems[regularItems.length - 1] : null;
              const q9Bottom = lastRegular ? (lastRegular.y + lastRegular.height) : 160;
              const screenCenterY = Math.round(SLIDE_H / 2) - 25;
              themeItem.x = NINE_SIXTEEN_X;
              themeItem.width = NINE_SIXTEEN_W;
              themeItem.y = Math.max(screenCenterY, q9Bottom + 25);
              themeItem.height = 50;
              themeItem.textAlign = 'center';
              themeItem.color = '#FFD700';
              themeItem.fontFamily = 'Lemonada, cursive';
              themeItem.fontWeight = 'bold';
              themeItem.fontSize = 36;
            }
          } else {
            // MC/REG/MISC review: title + 10 questions
            formatReviewSlide(sorted[0], sorted.slice(1));
          }
          return newSlide;
        }
        
        // Detect slide characteristics
        const isMC = roundType === 'MC';
        const isREG = roundType === 'REG';
        const isMISC = roundType === 'MISC';
        const isMYS = roundType === 'MYS';
        const isBIG = roundType === 'BIG';
        
        // ============================================
        // BIG ROUND ONLY (check roundType strictly)
        // BIG structure: 0=title, 1=question, 2=.gif, 3=review, 4=answers, 5=tiebreaker Q, 6=tiebreaker A
        // ============================================
        if (isBIG) {
          const sorted = [...texts].sort((a, b) => a.y - b.y);
          const count = sorted.length;
          const MAX_BOTTOM = 930;
          
          // BIG round: detect slide type by CONTENT, not posInRound
          // This handles PPTX files with slides in any order
          const hasGifImage = newSlide.elements.some(el => 
            el.type === 'image' && el.src && 
            (el.src.startsWith('data:image/gif') || (el.src || '').toLowerCase().includes('.gif'))
          );
          
          // GIF slide (typically posInRound 2) — no text formatting needed
          if (hasGifImage && count <= 1) {
            return null;
          }
          
          // Detect answer-like slides: many short numbered items (e.g., "1. Paris", "2. Blue")
          const numberedItems = sorted.filter(el => /^\d{1,2}[\.\)]/.test((el.content || '').trim()));
          const avgContentLen = sorted.reduce((s, el) => s + (el.content || '').length, 0) / Math.max(count, 1);
          const isAnswerSlide = numberedItems.length >= 4 && avgContentLen < 40;
          
          // Detect question/review slides: fewer items with longer text
          const isQuestionSlide = count <= 5 && avgContentLen > 30;
          
          if (isAnswerSlide) {
            // BIG ANSWERS: left-aligned within 9:16 area
            const GAP = 68;
            let textH = 50;
            if (count > 10) textH = 35;
            else if (count > 8) textH = 40;
            else if (count > 6) textH = 45;
            
            let actualGap = GAP;
            const totalNeeded = (count * textH) + ((count - 1) * actualGap);
            if (totalNeeded > MAX_BOTTOM - BIG_ANSWER_TOP && count > 1) {
              actualGap = Math.max(5, Math.floor((MAX_BOTTOM - BIG_ANSWER_TOP - count * textH) / (count - 1)));
            }
            
            let fontSize = 30;
            if (count > 12) fontSize = 22;
            else if (count > 10) fontSize = 24;
            else if (count > 8) fontSize = 26;
            
            sorted.forEach((el, i) => {
              el.x = CONTENT_X + 50;
              el.width = CONTENT_W - 50;
              el.y = BIG_ANSWER_TOP + (i * (textH + actualGap));
              el.height = textH;
              el.textAlign = 'left';
              el.verticalAlign = 'top';
              el.color = '#FFFFFF';
              el.fontSize = fontSize;
              el.fontWeight = 'normal';
              el.fontFamily = 'Inter, sans-serif';
              el.lineHeight = 1.2;
            });
          } else {
            // BIG QUESTIONS / REVIEW: 3 text boxes in specific order
            // 1. Yellow instruction text ("3 Points each. No order.") — top + 50px
            // 2. Question text (longest content) — 100px below #1
            // 3. Points text ("For 30 Points") — 100px below #2
            // Also handles tiebreaker slides (fewer elements, different content)
            
            // Classify each text element by content
            let instructionEl = null; // "X Points each" / "No order"
            let pointsEl = null;      // "For XX Points"
            let questionEl = null;    // The actual question (longest text)
            const otherEls = [];
            
            sorted.forEach(el => {
              const c = (el.content || '').trim();
              const cLower = c.toLowerCase();
              
              if (cLower.includes('points each') || cLower.includes('no order')) {
                instructionEl = el;
              } else if (/^for\s+\d+\s+points?$/i.test(c)) {
                pointsEl = el;
              } else {
                otherEls.push(el);
              }
            });
            
            // The question is the remaining element with the most text
            if (otherEls.length > 0) {
              otherEls.sort((a, b) => (b.content || '').length - (a.content || '').length);
              questionEl = otherEls[0];
            }
            
            const textH = 80;
            const BIG_GAP = 100;
            let currentY = BIG_QUESTION_TOP + 50; // Start 50px below BIG_QUESTION_TOP
            
            // 1. Yellow instruction text at top
            if (instructionEl) {
              instructionEl.x = CONTENT_X;
              instructionEl.width = CONTENT_W;
              instructionEl.y = currentY;
              instructionEl.height = textH;
              instructionEl.textAlign = 'center';
              instructionEl.color = '#FFD700';
              instructionEl.fontSize = 30;
              instructionEl.fontWeight = 'normal';
              instructionEl.fontFamily = 'Inter, sans-serif';
              currentY += textH + BIG_GAP;
            }
            
            // 2. Question text (main question, largest text)
            if (questionEl) {
              questionEl.x = CONTENT_X;
              questionEl.width = CONTENT_W;
              questionEl.y = currentY;
              questionEl.height = textH;
              questionEl.textAlign = 'center';
              questionEl.color = '#FFFFFF';
              questionEl.fontSize = dynamicFontSize((questionEl.content || '').length, 36, 24);
              questionEl.fontWeight = 'normal';
              questionEl.fontFamily = 'Inter, sans-serif';
              currentY += textH + BIG_GAP;
            }
            
            // 3. Points text ("For 30 Points")
            if (pointsEl) {
              pointsEl.x = CONTENT_X;
              pointsEl.width = CONTENT_W;
              pointsEl.y = currentY;
              pointsEl.height = textH;
              pointsEl.textAlign = 'center';
              pointsEl.color = '#FFFFFF';
              pointsEl.fontSize = 30;
              pointsEl.fontWeight = 'normal';
              pointsEl.fontFamily = 'Inter, sans-serif';
              currentY += textH + BIG_GAP;
            }
            
            // Handle any remaining elements (tiebreaker slides may have extra text)
            otherEls.slice(1).forEach(el => {
              el.x = CONTENT_X;
              el.width = CONTENT_W;
              el.y = currentY;
              el.height = textH;
              el.textAlign = 'center';
              el.color = '#FFFFFF';
              el.fontSize = dynamicFontSize((el.content || '').length, 36, 24);
              el.fontWeight = 'normal';
              el.fontFamily = 'Inter, sans-serif';
              currentY += textH + BIG_GAP;
            });
          }
          
          return newSlide;
        }
        
        // ============================================
        // MC ROUND
        // ============================================
        if (isMC) {
          const sorted = [...texts].sort((a, b) => a.y - b.y);
          
          // Question slides (1-10)
          if (posInRound >= 1 && posInRound <= 10) {
            // Separate question text from options (yellow A, B, C, D)
            const optionPattern = /^[A-D]\)/i;
            const questionElements = [];
            const options = [];
            
            sorted.forEach(el => {
              const content = (el.content || '').trim();
              if (optionPattern.test(content)) {
                options.push(el);
              } else {
                questionElements.push(el);
              }
            });
            
            // Format MC question text - 9:16 area with 50px buffer, top edge at Y=150
            const totalQLen = questionElements.reduce((sum, el) => sum + (el.content || '').length, 0);
            const qFontSize = dynamicFontSize(totalQLen, 34, 24);
            
            if (questionElements.length === 1) {
              const q = questionElements[0];
              q.x = CONTENT_X;           // 50px buffer from 9:16 left edge (706px)
              q.width = CONTENT_W;       // 508px
              q.y = MC_QUESTION_TOP;     // Fixed top edge at 150
              q.height = 350;
              q.textAlign = 'center';
              q.color = '#FFFFFF';
              q.fontSize = qFontSize;
              q.fontWeight = 'normal';
              q.fontFamily = 'Inter, sans-serif';
            } else if (questionElements.length > 1) {
              // Stack multiple question elements starting at Y=150
              const spacing = Math.floor(300 / questionElements.length);
              questionElements.forEach((q, i) => {
                q.x = CONTENT_X;
                q.width = CONTENT_W;
                q.y = Math.max(MC_QUESTION_TOP + (i * spacing), MC_QUESTION_TOP); // Never < 150
                q.height = spacing;
                q.textAlign = 'center';
                q.color = '#FFFFFF';
                q.fontSize = qFontSize;
                q.fontWeight = 'normal';
                q.fontFamily = 'Inter, sans-serif';
              });
            }
            
            // Options: 175px to the right of 9:16 left side
            if (options.length >= 4) {
              const optH = 55;
              const optDY = MAX_BOTTOM - optH;
              const optSpacing = 71;
              const optFontSize = 31;
              
              options.sort((a, b) => (a.content || '').charAt(0).localeCompare((b.content || '').charAt(0)));
              
              const avgCharWidth = 22;
              const paddingBuffer = 80;
              let maxWidth = Math.max(...options.map(opt => 
                ((opt.content || '').length * avgCharWidth) + paddingBuffer
              ), 300);
              
              options.forEach((opt, i) => {
                opt.x = ANSWER_X;  // 175px from 9:16 left = 831px
                opt.width = maxWidth;
                opt.y = optDY - ((3 - i) * optSpacing);
                opt.height = optH;
                opt.textAlign = 'left';
                opt.color = '#FFD700';
                opt.fontSize = optFontSize;
                opt.fontFamily = 'Inter, sans-serif';
                opt.whiteSpace = 'nowrap';
              });
            }
            return newSlide;
          }
          
          // Answer slide (13) - First answer at Y=130, 50px spacing between answers
          if (posInRound === 13) {
            // Check if first element is "Answers" title
            const firstContent = (sorted[0]?.content || '').toLowerCase();
            const hasTitle = firstContent.includes('answer') || firstContent.includes('reveal');
            
            const title = hasTitle ? sorted[0] : null;
            const answers = hasTitle ? sorted.slice(1) : sorted;
            
            // Format title if present - yellow, Lemonada, centered at top
            if (title) {
              title.x = 0; title.width = 1920; title.y = 30; title.height = 80;
              title.textAlign = 'center'; title.color = '#FFD700';
              title.fontFamily = 'Lemonada, cursive'; title.fontWeight = 'bold'; title.fontSize = 48;
            }
            
            // Format answers - first at Y=150, 75px spacing, 175px from 9:16 left
            const h = 55;
            
            answers.forEach((el, i) => {
              el.x = ANSWER_X;  // 175px from 9:16 left = 831px
              el.width = CONTENT_W;
              el.y = ANSWER_TOP + (i * ANSWER_SPACING); // 150 + (i * 75)
              el.height = h;
              el.textAlign = 'left';
              el.color = '#FFFFFF';
              el.fontSize = 30;
              el.fontFamily = 'Inter, sans-serif';
              el.fontWeight = 'normal';
            });
            return newSlide;
          }
        }
        
        // ============================================
        // REG/MISC ROUND
        // ============================================
        if (isREG) {
          const sorted = [...texts].sort((a, b) => a.y - b.y);
          
          // Question slides (1-10) - top edge at Y=250
          if (posInRound >= 1 && posInRound <= 10) {
            const totalLen = sorted.reduce((sum, el) => sum + (el.content || '').length, 0);
            const fontSize = dynamicFontSize(totalLen, 40, 26);
            const availableHeight = MAX_BOTTOM - REG_QUESTION_TOP; // From 250 to 905
            const spacing = Math.floor(availableHeight / Math.max(sorted.length, 1));
            
            sorted.forEach((el, i) => {
              el.x = CONTENT_X;
              el.width = CONTENT_W;
              el.y = Math.max(REG_QUESTION_TOP + (i * spacing), REG_QUESTION_TOP); // Never < 250
              el.height = Math.floor(spacing * 0.85);
              el.textAlign = 'center';
              el.color = '#FFFFFF';
              el.fontSize = i === 0 ? fontSize + 4 : fontSize;
              el.fontWeight = i === 0 ? 'bold' : 'normal';
              el.fontFamily = 'Inter, sans-serif';
            });
            return newSlide;
          }
          
          // Answer slide (13) - first at Y=150, 75px spacing, 175px from 9:16 left
          if (posInRound === 13) {
            const firstContent = (sorted[0]?.content || '').toLowerCase();
            const hasTitle = firstContent.includes('answer') || firstContent.includes('reveal');
            
            const title = hasTitle ? sorted[0] : null;
            const answers = hasTitle ? sorted.slice(1) : sorted;
            
            if (title) {
              title.x = 0; title.width = 1920; title.y = 30; title.height = 80;
              title.textAlign = 'center'; title.color = '#FFD700';
              title.fontFamily = 'Lemonada, cursive'; title.fontWeight = 'bold'; title.fontSize = 48;
            }
            
            const h = 55;
            answers.forEach((el, i) => {
              el.x = ANSWER_X;  // 175px from 9:16 left = 831px
              el.width = CONTENT_W;
              el.y = ANSWER_TOP + (i * ANSWER_SPACING); // 150 + (i * 75)
              el.height = h;
              el.textAlign = 'left';
              el.color = '#FFFFFF';
              el.fontSize = 30;
              el.fontFamily = 'Inter, sans-serif';
              el.fontWeight = 'normal';
            });
            return newSlide;
          }
        }
        
        // ============================================
        // MISC ROUND - GIF-aware text positioning
        // If a .gif is present:
        // 1. Move text down 100px from standard position (350 instead of 250)
        // 2. Keep GIF where it is
        // 3. If text overlaps GIF at new position, reduce font size by 5% until it fits
        // ============================================
        if (isMISC) {
          const sorted = [...texts].sort((a, b) => a.y - b.y);
          
          // Question slides (1-10)
          if (posInRound >= 1 && posInRound <= 10) {
            // Check if this slide has a GIF image
            const gifElements = newSlide.elements.filter(el => 
              el.type === 'image' && el.src && 
              (el.src.startsWith('data:image/gif') || (el.src || '').toLowerCase().includes('.gif'))
            );
            
            // MISC with GIF starts 100px lower than standard (350 instead of 250)
            const MISC_GIF_QUESTION_TOP = REG_QUESTION_TOP + 100; // 350px
            
            // Calculate max bottom Y for text based on GIF presence
            let textMaxBottom = MAX_BOTTOM;
            
            if (gifElements.length > 0) {
              // Find the topmost GIF's Y position
              const gifTopY = Math.min(...gifElements.map(el => el.y));
              // Leave a 20px gap between text and GIF
              textMaxBottom = gifTopY - 20;
              console.log(`MISC slide ${slideIdx}: GIF found at y=${gifTopY}, text max bottom=${textMaxBottom}`);
            }
            
            const totalLen = sorted.reduce((sum, el) => sum + (el.content || '').length, 0);
            let baseFontSize = dynamicFontSize(totalLen, 40, 26);
            
            if (gifElements.length > 0 && sorted.length > 0) {
              // GIF present - start text at Y=350 (100px lower)
              const startY = MISC_GIF_QUESTION_TOP;
              const availableHeight = textMaxBottom - startY;
              
              // Base text height and spacing
              let textHeightPerElement = 80;
              let spacingBetween = 20;
              
              // Calculate total space needed
              let totalNeeded = (sorted.length * textHeightPerElement) + ((sorted.length - 1) * spacingBetween);
              
              // If text doesn't fit, reduce font size by 5% increments until it does
              let currentFontSize = baseFontSize;
              let reductionCount = 0;
              const maxReductions = 10; // Safety limit - max 50% reduction
              
              while (totalNeeded > availableHeight && reductionCount < maxReductions) {
                // Reduce font size by 5%
                currentFontSize = Math.floor(currentFontSize * 0.95);
                // Also reduce text height proportionally
                textHeightPerElement = Math.floor(textHeightPerElement * 0.95);
                spacingBetween = Math.floor(spacingBetween * 0.95);
                // Recalculate total needed
                totalNeeded = (sorted.length * textHeightPerElement) + ((sorted.length - 1) * spacingBetween);
                reductionCount++;
              }
              
              // Ensure minimum values
              currentFontSize = Math.max(currentFontSize, 18);
              textHeightPerElement = Math.max(textHeightPerElement, 40);
              spacingBetween = Math.max(spacingBetween, 5);
              
              // Position text elements starting at Y=350
              sorted.forEach((el, i) => {
                el.x = CONTENT_X;
                el.width = CONTENT_W;
                el.y = startY + (i * (textHeightPerElement + spacingBetween));
                el.height = textHeightPerElement;
                el.textAlign = 'center';
                el.color = '#FFFFFF';
                el.fontSize = currentFontSize;
                el.fontWeight = 'normal';
                el.fontFamily = 'Inter, sans-serif';
              });
              
              if (reductionCount > 0) {
                console.log(`MISC slide ${slideIdx}: GIF-aware, Y=350, font reduced ${reductionCount * 5}% to ${currentFontSize}px`);
              } else {
                console.log(`MISC slide ${slideIdx}: GIF-aware, Y=350, font=${currentFontSize}px`);
              }
            } else {
              // No GIF - use standard REG/MISC layout starting at Y=250
              const availableHeight = MAX_BOTTOM - REG_QUESTION_TOP;
              const spacing = Math.floor(availableHeight / Math.max(sorted.length, 1));
              
              sorted.forEach((el, i) => {
                el.x = CONTENT_X;
                el.width = CONTENT_W;
                el.y = Math.max(REG_QUESTION_TOP + (i * spacing), REG_QUESTION_TOP);
                el.height = Math.floor(spacing * 0.85);
                el.textAlign = 'center';
                el.color = '#FFFFFF';
                el.fontSize = i === 0 ? baseFontSize + 4 : baseFontSize;
                el.fontWeight = i === 0 ? 'bold' : 'normal';
                el.fontFamily = 'Inter, sans-serif';
              });
            }
            return newSlide;
          }
          
          // Answer slide (13)
          if (posInRound === 13) {
            const firstContent = (sorted[0]?.content || '').toLowerCase();
            const hasTitle = firstContent.includes('answer') || firstContent.includes('reveal');
            
            const title = hasTitle ? sorted[0] : null;
            const answers = hasTitle ? sorted.slice(1) : sorted;
            
            if (title) {
              title.x = 0; title.width = 1920; title.y = 30; title.height = 80;
              title.textAlign = 'center'; title.color = '#FFD700';
              title.fontFamily = 'Lemonada, cursive'; title.fontWeight = 'bold'; title.fontSize = 48;
            }
            
            const h = 55;
            answers.forEach((el, i) => {
              el.x = ANSWER_X;
              el.width = CONTENT_W;
              el.y = ANSWER_TOP + (i * ANSWER_SPACING);
              el.height = h;
              el.textAlign = 'left';
              el.color = '#FFFFFF';
              el.fontSize = 30;
              el.fontFamily = 'Inter, sans-serif';
              el.fontWeight = 'normal';
            });
            return newSlide;
          }
        }
        
        // ============================================
        // MYS (Mystery) ROUND
        // ============================================
        if (isMYS) {
          const sorted = [...texts].sort((a, b) => a.y - b.y);
          
          // Question slides (1-9) - top edge at Y=250
          if (posInRound >= 1 && posInRound <= 9) {
            const totalLen = sorted.reduce((sum, el) => sum + (el.content || '').length, 0);
            const fontSize = dynamicFontSize(totalLen, 40, 26);
            const availableHeight = MAX_BOTTOM - REG_QUESTION_TOP; // From 250 to 905
            const spacing = Math.floor(availableHeight / Math.max(sorted.length, 1));
            
            sorted.forEach((el, i) => {
              el.x = CONTENT_X;
              el.width = CONTENT_W;
              el.y = Math.max(REG_QUESTION_TOP + (i * spacing), REG_QUESTION_TOP); // Never < 250
              el.height = Math.floor(spacing * 0.85);
              el.textAlign = 'center';
              el.color = '#FFFFFF';
              el.fontSize = i === 0 ? fontSize + 4 : fontSize;
              el.fontWeight = i === 0 ? 'bold' : 'normal';
              el.fontFamily = 'Inter, sans-serif';
            });
            return newSlide;
          }
          
          // Answer slide (12) - Mystery Theme? is PERMANENT (always visible), prevent overlap
          if (posInRound === 12) {
            let mysteryLabel = null, answer10 = null;
            const regular = [];
            
            sorted.forEach(el => {
              const c = (el.content || '').toLowerCase();
              if (c.includes('mystery theme') || c.includes('mysterytheme')) mysteryLabel = el;
              else if (/^10\./.test(el.content || '')) answer10 = el;
              else regular.push(el);
            });
            
            // Fixed positions - Mystery Theme? centered on page, Answer 10 below it
            const mysteryLabelY = 780;
            const answer10Y = 850;
            
            // Answers 1-9: first at Y=150, 75px spacing, 175px from 9:16 left
            const h = 48;
            
            regular.forEach((el, i) => {
              el.x = ANSWER_X;  // 175px from 9:16 left = 831px
              el.width = CONTENT_W;
              el.y = ANSWER_TOP + (i * ANSWER_SPACING); // 150 + (i * 75)
              el.height = h; 
              el.textAlign = 'left';
              el.color = '#FFFFFF'; 
              el.fontSize = 28;
              el.fontFamily = 'Inter, sans-serif';
            });
            
            // Mystery Theme? - YELLOW, LEMONADA BOLD, CENTERED on full page width
            if (mysteryLabel) {
              mysteryLabel.x = 0;
              mysteryLabel.width = 1920;
              mysteryLabel.y = mysteryLabelY; 
              mysteryLabel.height = 55;
              mysteryLabel.textAlign = 'center'; 
              mysteryLabel.color = '#FFD700';
              mysteryLabel.fontFamily = 'Lemonada, cursive'; 
              mysteryLabel.fontWeight = 'bold'; 
              mysteryLabel.fontSize = 36;
            }
            
            // Answer 10 - centered below Mystery Theme label
            if (answer10) {
              answer10.x = 0; answer10.width = 1920;
              answer10.y = answer10Y; answer10.height = 55;
              answer10.textAlign = 'center'; answer10.color = '#FFFFFF';
              answer10.fontWeight = 'bold'; answer10.fontSize = 38;
              answer10.fontFamily = 'Inter, sans-serif';
            }
            return newSlide;
          }
        }
        
        return newSlide;
      }; // End of formatSlide function
      
      // ========== BATCHED PROCESSING ==========
      // MEMORY OPTIMIZATION: Process slides in batches to prevent memory spikes
      const BATCH_SIZE = 25;
      const totalSlides = presentation.slides.length;
      let formattedCount = 0;
      
      console.log(`Starting batched formatting of ${totalSlides} slides...`);
      
      for (let batchStart = 0; batchStart < totalSlides; batchStart += BATCH_SIZE) {
        const batchEnd = Math.min(batchStart + BATCH_SIZE, totalSlides);
        
        // React 18 auto-batches state updates — no manual delay needed
        
        // MEMORY OPTIMIZATION: Functional state update with targeted mutations
        setPresentation(prev => {
          // Create shallow copy of slides array
          const newSlides = [...prev.slides];
          
          // Only process and modify slides in this batch
          for (let i = batchStart; i < batchEnd; i++) {
            const formattedSlide = formatSlide(newSlides[i], i);
            if (formattedSlide !== null) {
              newSlides[i] = formattedSlide;
              formattedCount++;
            }
          }
          
          return { ...prev, slides: newSlides };
        });
        
        // Update progress toast
        const progress = Math.round((batchEnd / totalSlides) * 100);
        toast({ 
          title: '🎨 Formatting...', 
          description: `${progress}% complete (${batchEnd}/${totalSlides} slides)`, 
          variant: 'default' 
        });
      }
      
      // Get final slides for saving
      // Use a ref or callback to get the latest state
      const finalSlides = await new Promise(resolve => {
        setPresentation(prev => {
          resolve(prev.slides);
          return prev;
        });
      });
      
      // SAVE TO DATABASE - Use GridFS for trivia-imported presentations
      try {
        if (presentation.type === 'trivia-imported') {
          // Use GridFS for trivia presentations to avoid MongoDB 16MB limit
          presentationAPI.storeAllSlides(presentation.id, finalSlides).catch(() => {});
          toast({ title: '✅ Formatting Complete & Saved!', description: `${finalSlides.length} slides formatted and saved to GridFS` });
        } else {
          // Regular presentations use direct MongoDB update
          await presentationAPI.update(presentation.id, {
            slides: finalSlides,
            updatedAt: new Date().toISOString()
          });
          toast({ title: '✅ Formatting Complete & Saved!', description: `${finalSlides.length} slides formatted and saved` });
        }
      } catch (saveError) {
        console.warn('Auto-save after formatting failed:', saveError);
        toast({ title: '✅ Formatting Complete', description: `${finalSlides.length} slides formatted (save pending)`, variant: 'default' });
      }
      
    } catch (error) {
      console.error('Formatting error:', error);
      toast({ title: '⚠️ Error', description: error.message || 'Formatting failed', variant: 'destructive' });
    } finally {
      // slideOp reset is handled by the useEffect caller
    }
  };
  
  const handleOverlaysApplied = useCallback(async (result) => {
    try {
      // Only show toast if overlays were actually applied
      if (result.overlaysApplied > 0) {
        toast({ 
          title: 'Overlays Applied!', 
          description: `Successfully applied ${result.overlaysApplied} overlays. Reloading presentation...` 
        });
      }
      
      // Reload the presentation to show the overlays
      await loadPresentation();
      
      // Reset auto-init flag to prevent re-triggering
      setShouldAutoInitOverlays(false);
    } catch (error) {
      console.error('Error reloading presentation after overlays:', error);
      toast({ 
        title: 'Warning', 
        description: 'Overlays applied but failed to reload. Please refresh the page.', 
        variant: 'destructive' 
      });
    }
  }, []);

  // Memoize the select slide handler for SlideThumbnails
  const handleSelectSlide = useCallback((index) => {
    setCurrentSlideIndex(index);
    setSelectedElement(null);
  }, []);

  // Memoize slides array reference for child components
  const slides = useMemo(() => presentation?.slides || [], [presentation?.slides]);

  // Smart round count detection: numRounds > roundTypes.length > count from slides > default (5)
  const detectedRoundCount = useMemo(() => {
    // First priority: explicit numRounds
    if (presentation?.numRounds && [3, 5, 6].includes(presentation.numRounds)) {
      return presentation.numRounds;
    }
    
    // Second priority: roundTypes array length
    if (presentation?.roundTypes?.length > 0 && [3, 5, 6].includes(presentation.roundTypes.length)) {
      return presentation.roundTypes.length;
    }
    
    // Third priority: count round title slides from the presentation
    if (presentation?.slides?.length > 0) {
      const roundTitles = presentation.slides.filter(s => s?.metadata?.isRoundTitle);
      // Exclude special rounds like WINNERS, SCORES, SPONSOR
      const gameRounds = roundTitles.filter(s => 
        !['WINNERS', 'SCORES', 'SPONSOR', 'TOTAL'].includes(s?.metadata?.roundType)
      );
      const count = gameRounds.length;
      if ([3, 5, 6].includes(count)) {
        return count;
      }
    }
    
    // Default to 5 rounds
    return 5;
  }, [presentation?.numRounds, presentation?.roundTypes, presentation?.slides]);

  // Extract round types from slides if not available from presentation
  const detectedRoundTypes = useMemo(() => {
    // First priority: explicit roundTypes from presentation
    if (presentation?.roundTypes?.length > 0) {
      return presentation.roundTypes;
    }
    
    // Second priority: extract from slide metadata
    if (presentation?.slides?.length > 0) {
      const roundTitles = presentation.slides
        .filter(s => s?.metadata?.isRoundTitle)
        .filter(s => !['WINNERS', 'SCORES', 'SPONSOR', 'TOTAL'].includes(s?.metadata?.roundType))
        .sort((a, b) => (a.metadata?.roundNumber || 0) - (b.metadata?.roundNumber || 0));
      
      if (roundTitles.length > 0) {
        return roundTitles.map(s => s.metadata?.roundType || 'REG');
      }
    }
    
    return [];
  }, [presentation?.roundTypes, presentation?.slides]);

  // Memoize start presentation handler
  const handleStartPresentation = useCallback(() => {
    setIsPresentationMode(true);
  }, []);

  // Memoize exit presentation handler
  const handleExitPresentation = useCallback(() => {
    setIsPresentationMode(false);
  }, []);


  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#0f0f10]">
        <div className="text-center">
          <Loader2 className="w-16 h-16 text-[#FFC107] mx-auto mb-4 animate-spin" />
          <p className="text-white text-lg">Loading presentation...</p>
        </div>
      </div>
    );
  }

  if (!presentation) {
    return null;
  }

  return (
    <div className="h-screen flex flex-col bg-[#0f0f10]">
      {/* Formatting Loading Indicator */}
      {slideOp === 'formatting' && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center">
          <div className="bg-[#1a1a1a] border border-gray-700 rounded-lg p-8 text-center">
            <Loader2 className="w-16 h-16 text-purple-500 mx-auto mb-4 animate-spin" />
            <p className="text-white text-lg font-semibold mb-2">Applying Formatting...</p>
            <p className="text-gray-400 text-sm">Fixing slide layouts and styles</p>
          </div>
        </div>
      )}

      {/* Overlay Application Loading Indicator */}
      {slideOp === 'overlaying' && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center">
          <div className="bg-[#1a1a1a] border border-gray-700 rounded-lg p-8 text-center">
            <Loader2 className="w-16 h-16 text-[#FFC107] mx-auto mb-4 animate-spin" />
            <p className="text-white text-lg font-semibold mb-2">Applying Location Overlays...</p>
            <p className="text-gray-400 text-sm">This will only take a moment</p>
          </div>
        </div>
      )}

      {!isPresentationMode && (
        <>
          {/* Header */}
          <div className="bg-[#1a1a1a] border-b border-gray-700 px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                onClick={() => navigate('/')}
                variant="ghost"
                size="sm"
                className="text-white hover:bg-gray-700"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back
              </Button>
              <h1 className="text-white text-xl font-bold">{presentation.name}</h1>
              {saving && (
                <span className="text-gray-400 text-sm flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </span>
              )}
            </div>
            <div className="text-gray-400 text-sm">
              Editing as: {presentation.createdBy}
            </div>
          </div>

          {/* Toolbar */}
          <Toolbar
            onAddSlide={handleAddSlide}
            onAddText={handleAddText}
            onAddImage={handleAddImage}
            onDeleteSlide={handleDeleteSlide}
            onStartPresentation={handleStartPresentation}
            onSave={handleSave}
            onOpenScoreTracker={handleOpenScoreTracker}
            onFixFormatting={applyFormatting}
            selectedElement={selectedElement}
            onUpdateElement={handleUpdateElement}
            canDelete={presentation.slides.length > 1}
            presentationId={presentation.id}
            locationName={presentation.location ? presentation.location.split('/').pop() : null}
            onOverlaysApplied={handleOverlaysApplied}
            slides={slides}
          />

          {/* Main Content */}
          <div className="flex-1 flex overflow-hidden">
            <SlideThumbnails
              slides={slides}
              currentSlideIndex={currentSlideIndex}
              onSelectSlide={handleSelectSlide}
              onAddSlide={handleAddSlide}
              onReorderSlides={handleReorderSlides}
              overlayCache={overlayCache}
              overlayCacheVersion={overlayCacheVersion}
            />
            <div className="flex-1 flex items-center justify-center bg-[#2a2a2a] p-8 overflow-auto relative">
              <SlideCanvas
                slide={currentSlide}
                selectedElement={selectedElement}
                onSelectElement={setSelectedElement}
                onUpdateElement={handleUpdateElement}
                onDeleteElement={handleDeleteElement}
                overlayCache={overlayCache}
                overlayCacheVersion={overlayCacheVersion}
              />
              
              {/* Score Slide Overlay Button */}
              {currentSlide?.metadata?.isScoreSlide && (
                <div className="absolute bottom-8 right-8">
                  <Button
                    onClick={handleOpenScoreTracker}
                    className="bg-yellow-600 hover:bg-yellow-700 text-white shadow-lg"
                    size="lg"
                  >
                    <ListOrdered className="w-5 h-5 mr-2" />
                    Open Score Tracker
                  </Button>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {isPresentationMode && (
        <PresentationMode
          slides={slides}
          onExit={handleExitPresentation}
          onOpenScoreTracker={handleOpenScoreTracker}
          presentationId={presentation.id}
          isScoreTrackerOpen={isScoreTrackerOpen}
          overlayCache={overlayCache}
          overlayCacheVersion={overlayCacheVersion}
        />
      )}

      {/* Score Tracker Modal */}
      <ScoreTrackerModal
        isOpen={isScoreTrackerOpen}
        onClose={handleCloseScoreTracker}
        defaultRoundMode={detectedRoundCount}
        onSendScores={handleSendScores}
        presentationId={presentation?.id}
        roundTypes={detectedRoundTypes}
      />
    </div>
  );
};

export default Editor;