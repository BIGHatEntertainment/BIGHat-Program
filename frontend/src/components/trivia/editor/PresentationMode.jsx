import React, { useState, useEffect, useCallback, useRef } from 'react';
import { X, ChevronLeft, ChevronRight, Monitor, ListOrdered, Pause, Play, Eye, Flag, Loader2, CheckCircle } from 'lucide-react';
import { Button } from '../../ui/button';
import { toast } from '../../../utils/toastCompat';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const PresentationMode = ({ slides, onExit, onOpenScoreTracker, presentationId, isScoreTrackerOpen = false, overlayCache, overlayCacheVersion }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [audienceIndex, setAudienceIndex] = useState(0);
  const [audienceWindow, setAudienceWindow] = useState(null);
  const [isSyncEnabled, setIsSyncEnabled] = useState(true);
  const [timeRemaining, setTimeRemaining] = useState(null);
  const [isTimerActive, setIsTimerActive] = useState(false);
  const [revealedAnswers, setRevealedAnswers] = useState({});
  const [presenterScale, setPresenterScale] = useState(1);
  const [isSavingScores, setIsSavingScores] = useState(false);
  const [scoresSaved, setScoresSaved] = useState(false);
  const audienceWindowRef = useRef(null);
  const timerRef = useRef(null);
  const slidesRef = useRef(slides); // Keep latest slides in ref to avoid stale closure
  const isAutoAdvancingRef = useRef(false); // Prevent race condition with keyboard
  const isSyncEnabledRef = useRef(isSyncEnabled); // Keep sync state without causing timer restarts
  const windowCheckIntervalRef = useRef(null); // MEMORY FIX: Track window closed check interval
  
  // Calculate scale factor based on viewport width relative to 1920px (standard resolution)
  useEffect(() => {
    const calculateScale = () => {
      const viewportWidth = window.innerWidth;
      const baseWidth = 1920;
      // Scale proportionally - smaller viewports get smaller text
      const scale = Math.min(1, viewportWidth / baseWidth);
      setPresenterScale(scale);
    };
    
    calculateScale();
    window.addEventListener('resize', calculateScale);
    return () => window.removeEventListener('resize', calculateScale);
  }, []);
  
  // Update refs whenever values change
  useEffect(() => {
    slidesRef.current = slides;
    isSyncEnabledRef.current = isSyncEnabled;
  }, [slides, isSyncEnabled]);
  
  const currentSlide = slides[currentIndex];
  const audienceSlide = slides[audienceIndex];

  // Determine auto-advance time based on slide position and round type
  // CRITICAL: Define helper functions FIRST before any functions that depend on them
  // This ensures proper initialization order and prevents "before initialization" errors
  
  // Answer reveal helper functions - MUST be defined before updateAudienceView
  const isAnswerSlide = useCallback((slideIndex) => {
    const slide = slides[slideIndex];
    const metadata = slide?.metadata;
    const roundType = metadata?.roundType;
    const relativeIndex = metadata?.slideIndexInRound;
    
    if (!roundType || relativeIndex === undefined) return false;
    
    // Answer slides are at EXACT positions (0-indexed slideIndexInRound)
    // MC/REG/MISC: 0=title, 1-10=questions, 11=review, 12=.gif, 13=answers
    // MYS: 0=title, 1-9=questions, 10=review, 11=.gif, 12=answers
    // BIG: 0=title, 1=question, 2=.gif, 3=review, 4=answers, 5-6=tiebreaker
    if (roundType === 'MC' && relativeIndex === 13) return true;
    if ((roundType === 'REG' || roundType === 'MISC') && relativeIndex === 13) return true;
    if (roundType === 'MYS' && relativeIndex === 12) return true;
    if (roundType === 'BIG' && relativeIndex === 4) return true;
    
    return false;
  }, [slides]);

  const getAnswerCount = useCallback((slideIndex) => {
    const slide = slides[slideIndex];
    if (!slide || !slide.elements) return 0;
    
    // CRITICAL FIX: Answer slides have NO title - ALL text elements are answers
    const textElements = slide.elements.filter(el => el.type === 'text');
    return textElements.length;  // Return full count, no -1 since there's no title
  }, [slides]);

  const getAutoAdvanceTime = useCallback((slideIndex) => {
    const slide = slides[slideIndex];
    const metadata = slide?.metadata;
    const roundType = metadata?.roundType;
    const relativeIndex = metadata?.slideIndexInRound;
    
    if (!roundType || relativeIndex === undefined) {
      return null; // No auto-advance for non-round slides
    }
    
    // Title slide (index 0) - no auto-advance
    if (relativeIndex === 0) {
      return null;
    }
    
    // SLIDE STRUCTURE (0-indexed slideIndexInRound):
    // MC/REG/MISC: 0=title, 1-10=questions, 11=review, 12=.gif(STOP), 13=answers(manual)
    // MYS: 0=title, 1-9=questions, 10=review, 11=.gif(STOP), 12=answers(manual)
    // BIG: 0=title, 1=question, 2=.gif(STOP), 3=review, 4=answers(manual), 5-6=tiebreaker(manual)
    
    // MC Round
    if (roundType === 'MC') {
      if (relativeIndex >= 1 && relativeIndex <= 10) return 45; // Questions 1-10: 45s
      if (relativeIndex === 11) return 120; // Review slide: 2min
      return null; // .gif (12) and answers (13) - manual progression
    }
    
    // REG/MISC Rounds
    if (roundType === 'REG' || roundType === 'MISC') {
      if (relativeIndex >= 1 && relativeIndex <= 10) return 45; // Questions 1-10: 45s
      if (relativeIndex === 11) return 120; // Review slide: 2min
      return null; // .gif (12) and answers (13) - manual progression
    }
    
    // MYS Round
    if (roundType === 'MYS') {
      if (relativeIndex >= 1 && relativeIndex <= 9) return 45; // Questions 1-9: 45s
      if (relativeIndex === 10) return 180; // Review slide: 3min
      return null; // .gif (11) and answers (12) - manual progression
    }
    
    // BIG Round
    if (roundType === 'BIG') {
      if (relativeIndex === 1) return 300; // Question (slide 2): 5min
      return null; // .gif (2), review (3), answers (4), tiebreaker (5-6) - all manual
    }
    
    return null;
  }, [slides]);

  // Get final scores from localStorage - MUST be defined before updateAudienceView
  const getFinalScores = useCallback(() => {
    if (!presentationId) return null;
    
    const storageKey = `triviaScoreData_${presentationId}`;
    const savedData = localStorage.getItem(storageKey);
    
    if (!savedData) return null;
    
    try {
      const parsed = JSON.parse(savedData);
      const { teams, roundMode } = parsed;
      
      // CRASH FIX: Validate data structure before processing
      if (!teams || !Array.isArray(teams)) {
        console.error('getFinalScores: Invalid teams data');
        return null;
      }
      
      // Round configurations (matching ScoreTrackerModal)
      const roundConfigs = {
        3: [
          { label: 'REG', multiplier: 1 },
          { label: 'MISC', multiplier: 1 },
          { label: 'BIG', multiplier: 3 }
        ],
        5: [
          { label: 'MC', multiplier: 1 },
          { label: 'REG', multiplier: 1 },
          { label: 'MISC', multiplier: 1 },
          { label: 'MYS', multiplier: 2 },
          { label: 'BIG', multiplier: 3 }
        ],
        6: [
          { label: 'MC', multiplier: 1 },
          { label: 'REG', multiplier: 1 },
          { label: 'REG', multiplier: 1 },
          { label: 'MISC', multiplier: 1 },
          { label: 'MYS', multiplier: 2 },
          { label: 'BIG', multiplier: 3 }
        ]
      };
      
      // CRASH FIX: Validate roundMode exists in config, default to 5 if not
      const currentRounds = roundConfigs[roundMode] || roundConfigs[5];
      
      if (!currentRounds) {
        console.error('getFinalScores: No valid round configuration');
        return null;
      }
      
      // Calculate totals and filter non-empty teams
      const teamsWithScores = teams
        .filter(team => team && team.name && team.name.trim() !== '')
        .map(team => {
          // CRASH FIX: Ensure team.rounds exists and is an array
          const teamRounds = Array.isArray(team.rounds) ? team.rounds : [];
          const roundScores = teamRounds.slice(0, currentRounds.length).map((score, idx) => {
            const points = parseInt(score) || 0;
            // CRASH FIX: Bounds check before accessing multiplier
            const multiplier = currentRounds[idx]?.multiplier || 1;
            return points * multiplier;
          });
          const roundTotal = roundScores.reduce((sum, score) => sum + score, 0);
          const swagPoints = parseInt(team.swag) || 0;
          const total = roundTotal + swagPoints;
          
          return {
            name: team.name,
            swag: team.swag || '',
            roundScores,
            total
          };
        })
        .sort((a, b) => b.total - a.total); // Sort by total descending
      
      return {
        teams: teamsWithScores,
        rounds: currentRounds
      };
    } catch (error) {
      console.error('Error parsing scores:', error);
      return null;
    }
  }, [presentationId]);

  // End Presentation: save scores to SharePoint and exit
  const handleEndPresentation = useCallback(async () => {
    const scoresData = getFinalScores();
    if (!scoresData || !scoresData.teams.length) {
      toast({ title: 'No Scores', description: 'No score data to save', variant: 'destructive' });
      return;
    }

    setIsSavingScores(true);
    try {
      // Get location name — try multiple sources
      const locationName = (() => {
        // Source 1: Presentation name pattern (e.g., "WP Gilbert - 2/5/2026" or "Monkey Pants - 2/9/2026")
        const presName = localStorage.getItem('currentPresentationName') || '';
        const nameMatch = presName.match(/^(.+?)\s*-\s*\d/);
        if (nameMatch) return nameMatch[1].trim();
        
        // Source 2: Slide metadata
        for (const s of slides) {
          const loc = s?.metadata?.location || s?.metadata?.locationName;
          if (loc) return loc.replace(/^\d+_/, '');
        }
        
        return presName || 'Unknown';
      })();

      const presName = localStorage.getItem('currentPresentationName') || `Trivia ${new Date().toLocaleDateString()}`;
      const dateStr = new Date().toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' });

      await axios.post(`${BACKEND_URL}/api/scores/save`, {
        locationName,
        presentationName: presName,
        presentationDate: dateStr,
        presentationId,
        teams: scoresData.teams,
        rounds: scoresData.rounds
      });

      setScoresSaved(true);
      toast({ title: 'Scores Saved!', description: `Saved to SharePoint: ${locationName}` });

      // Exit after brief delay
      setTimeout(() => onExit(), 2000);
    } catch (err) {
      console.error('Error saving scores:', err);
      // Check if it's just a DB warning but SharePoint saved OK
      const errMsg = err.response?.data?.detail || '';
      if (errMsg.includes('truth value') || errMsg.includes('database')) {
        // This is a non-critical DB warning — the file DID save to SharePoint
        setScoresSaved(true);
        toast({ title: 'Scores Saved!', description: `Saved to SharePoint: ${locationName}` });
        setTimeout(() => onExit(), 2000);
      } else {
        toast({ title: 'Error', description: errMsg || 'Failed to save scores', variant: 'destructive' });
      }
    } finally {
      setIsSavingScores(false);
    }
  }, [getFinalScores, slides, presentationId, onExit]);

  // Update audience view helper - NOW safe to use isAnswerSlide and getFinalScores
  const updateAudienceView = useCallback((index) => {
    if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
      try {
        const slide = slides[index];
        const isAnswer = isAnswerSlide(index);
        const revealCount = revealedAnswers[index] || 0;
        
        // Get final scores if this is the final winners slide
        let finalScores = null;
        if (slide?.metadata?.roundType === 'WINNERS' && slide?.metadata?.slideIndexInRound === 4) {
          finalScores = getFinalScores();
        }
        
        // Resolve overlay references to actual image data for the audience window.
        // All overlays (including BIG.gif) are cached and sent to audience.
        let resolvedSlide = slide;
        if (slide?.elements && overlayCache?.current) {
          resolvedSlide = {
            ...slide,
            elements: slide.elements.map(el => {
              if (el.type === 'overlay' && el.overlayId && overlayCache.current[el.overlayId]) {
                return {
                  ...el,
                  type: 'image',
                  src: overlayCache.current[el.overlayId]
                };
              }
              // Drop overlay elements that aren't in cache (too large) rather than sending empty refs
              if (el.type === 'overlay' && !overlayCache.current?.[el.overlayId]) {
                return null;
              }
              return el;
            }).filter(Boolean)
          };
        }
        
        audienceWindowRef.current.postMessage({
          type: 'UPDATE_SLIDE',
          slide: resolvedSlide,
          isAnswerSlide: isAnswer,
          revealedCount: revealCount,
          finalScoresData: finalScores
        }, '*');
      } catch (error) {
        console.error('Error updating audience view:', error);
      }
    }
  }, [slides, isAnswerSlide, revealedAnswers, audienceWindowRef, getFinalScores, overlayCache]);

  // Host navigation - affects audience only if sync is enabled
  const goNext = useCallback(() => {
    setCurrentIndex((prev) => {
      const newIndex = prev < slides.length - 1 ? prev + 1 : prev;
      // Auto-sync audience if enabled
      if (isSyncEnabled && audienceWindowRef.current && !audienceWindowRef.current.closed) {
        setAudienceIndex(newIndex);
        updateAudienceView(newIndex);
      }
      return newIndex;
    });
  }, [slides.length, isSyncEnabled, updateAudienceView, audienceWindowRef]);

  const goPrev = useCallback(() => {
    setCurrentIndex((prev) => {
      const newIndex = prev > 0 ? prev - 1 : prev;
      // Auto-sync audience if enabled
      if (isSyncEnabled && audienceWindowRef.current && !audienceWindowRef.current.closed) {
        setAudienceIndex(newIndex);
        updateAudienceView(newIndex);
      }
      return newIndex;
    });
  }, [isSyncEnabled, updateAudienceView, audienceWindowRef]);
  
  // Audience navigation - only called explicitly by host
  const advanceAudience = useCallback(() => {
    setAudienceIndex((prev) => {
      const newIndex = prev < slides.length - 1 ? prev + 1 : prev;
      updateAudienceView(newIndex);
      return newIndex;
    });
  }, [slides.length, updateAudienceView]);
  
  const reverseAudience = useCallback(() => {
    setAudienceIndex((prev) => {
      const newIndex = prev > 0 ? prev - 1 : prev;
      updateAudienceView(newIndex);
      return newIndex;
    });
  }, [updateAudienceView]);

  const revealNextAnswer = useCallback(() => {
    const currentRevealed = revealedAnswers[audienceIndex] || 0;
    const totalAnswers = getAnswerCount(audienceIndex);
    
    if (currentRevealed < totalAnswers) {
      const newRevealed = currentRevealed + 1;
      setRevealedAnswers(prev => ({
        ...prev,
        [audienceIndex]: newRevealed
      }));
      
      // Send reveal message to audience
      if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
        audienceWindowRef.current.postMessage({
          type: 'REVEAL_ANSWER',
          slideIndex: audienceIndex,
          revealedCount: newRevealed
        }, '*');
      }
    }
  }, [audienceIndex, revealedAnswers, getAnswerCount]);
  
  const syncAudienceToHost = useCallback(() => {
    setAudienceIndex(currentIndex);
    updateAudienceView(currentIndex);
  }, [currentIndex, updateAudienceView]);

  const toggleSync = useCallback(() => {
    setIsSyncEnabled(prev => !prev);
  }, []);

  // Auto-advance timer system
  useEffect(() => {
    // Clear any existing timer
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    
    // Get auto-advance time for current slide
    const advanceTime = getAutoAdvanceTime(currentIndex);
    const slide = slides[currentIndex];
    const metadata = slide?.metadata;
    
    if (advanceTime) {
      // Start timer ONLY if we have a valid advance time
      setTimeRemaining(advanceTime);
      setIsTimerActive(true);
      
      // Countdown every second
      const intervalId = setInterval(() => {
        setTimeRemaining((prev) => {
          if (prev <= 1) {
            // CRITICAL: Check if this is still the active interval (prevent stale callbacks)
            if (timerRef.current !== intervalId) {
              return prev; // Stale callback, do nothing
            }
            
            // Time's up - advance to next slide
            clearInterval(intervalId);
            timerRef.current = null;
            setIsTimerActive(false);
            
            // CRITICAL: Set lock to prevent keyboard race condition
            isAutoAdvancingRef.current = true;
            
            // CRITICAL FIX: Use setCurrentIndex directly with updater function
            // This avoids stale closure issues with goNext callback
            setCurrentIndex((prevIndex) => {
              const currentSlides = slidesRef.current; // Get latest slides from ref
              const newIndex = prevIndex < currentSlides.length - 1 ? prevIndex + 1 : prevIndex;
              
              // Auto-sync audience if enabled (use ref to avoid dependency)
              if (isSyncEnabledRef.current && audienceWindowRef.current && !audienceWindowRef.current.closed) {
                setAudienceIndex(newIndex);
                // Update audience view - using the NEW index
                const nextSlide = currentSlides[newIndex];
                const nextMetadata = nextSlide?.metadata;
                const isAnswer = (
                  (nextMetadata?.roundType === 'MC' && nextMetadata?.slideIndexInRound === 13) ||
                  ((nextMetadata?.roundType === 'REG' || nextMetadata?.roundType === 'MISC') && nextMetadata?.slideIndexInRound === 13) ||
                  (nextMetadata?.roundType === 'MYS' && nextMetadata?.slideIndexInRound === 12) ||
                  (nextMetadata?.roundType === 'BIG' && nextMetadata?.slideIndexInRound === 4)
                );
                
                // CRITICAL: Resolve overlay references before sending to audience
                // This ensures overlays display correctly on auto-advance
                let resolvedSlide = nextSlide;
                if (nextSlide?.elements && overlayCache?.current) {
                  resolvedSlide = {
                    ...nextSlide,
                    elements: nextSlide.elements.map(el => {
                      if (el.type === 'overlay' && el.overlayId) {
                        return {
                          ...el,
                          type: 'image',
                          src: overlayCache.current[el.overlayId] || ''
                        };
                      }
                      return el;
                    })
                  };
                }
                
                if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
                  audienceWindowRef.current.postMessage({
                    type: 'UPDATE_SLIDE',
                    slide: resolvedSlide,
                    isAnswerSlide: isAnswer,
                    revealedCount: 0
                  }, '*');
                }
              }
              
              return newIndex;
            });
            
            // Release lock after brief delay (prevents double-advance from key press)
            setTimeout(() => {
              isAutoAdvancingRef.current = false;
            }, 200);
            
            // DON'T return 0! This would set timeRemaining to 0 for the next slide
            // Just return prev and let the useEffect cleanup handle it
            return prev;
          }
          return prev - 1;
        });
      }, 1000);
      
      timerRef.current = intervalId; // Store the interval ID
    } else {
      // No timer for this slide - STOP auto-advance
      setTimeRemaining(null);
      setIsTimerActive(false);
    }
    
    // Cleanup on unmount or slide change
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [currentIndex]); // CRITICAL: Only currentIndex - getAutoAdvanceTime caused race condition

  const openAudienceView = () => {
    // Detect if there's a secondary screen
    const hasSecondScreen = window.screen.availLeft !== 0 || window.screen.availTop !== 0 || 
                           window.screenLeft !== 0 || window.screenTop !== 0;
    
    // Calculate position for extended display
    // If main screen is at 0,0 and is 1920px wide, secondary screen starts at 1920,0
    const primaryWidth = window.screen.availWidth;
    const screenLeft = hasSecondScreen ? primaryWidth : 0;
    
    // Open window with MAXIMUM chrome-less settings for clean TV display
    const newWindow = window.open(
      'about:blank',
      'AudienceView',
      `width=${window.screen.availWidth},height=${window.screen.availHeight},left=${screenLeft},top=0,fullscreen=yes,toolbar=no,location=no,directories=no,status=no,menubar=no,scrollbars=no,resizable=no,titlebar=no`
    );

    if (newWindow) {
      audienceWindowRef.current = newWindow;
      
      // Write the audience view HTML - starts with audience's current slide
      const initialSlide = slides[audienceIndex];
      const initialIsAnswerSlide = isAnswerSlide(audienceIndex);
      const initialRevealCount = revealedAnswers[audienceIndex] || 0;
      newWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>Audience View</title>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <style>
            * { 
              margin: 0; 
              padding: 0; 
              box-sizing: border-box; 
            }
            html, body { 
              width: 100%;
              height: 100%;
              background: black; 
              overflow: hidden;
              font-family: Inter, system-ui, -apple-system, sans-serif;
            }
            #fullscreen-prompt {
              position: fixed;
              top: 50%;
              left: 50%;
              transform: translate(-50%, -50%);
              background: rgba(255, 215, 0, 0.95);
              color: black;
              padding: 40px 60px;
              border-radius: 12px;
              font-size: 28px;
              font-weight: bold;
              cursor: pointer;
              z-index: 99999;
              text-align: center;
              box-shadow: 0 8px 32px rgba(0,0,0,0.5);
              display: none;
            }
            #fullscreen-prompt:hover {
              background: rgba(255, 215, 0, 1);
              transform: translate(-50%, -50%) scale(1.05);
            }
            body:-webkit-full-screen {
              width: 100%;
              height: 100%;
            }
            body:-moz-full-screen {
              width: 100%;
              height: 100%;
            }
            body:-ms-fullscreen {
              width: 100%;
              height: 100%;
            }
            body:fullscreen {
              width: 100%;
              height: 100%;
            }
            #slide-container {
              width: 100vw;
              height: 100vh;
              display: flex;
              align-items: center;
              justify-content: center;
              position: fixed;
              top: 0;
              left: 0;
              background: black;
            }
            #slide {
              width: 100%;
              height: 100%;
              position: relative;
            }
            .element {
              position: absolute;
              white-space: pre-wrap;
              display: flex;
              align-items: center;
              background: transparent;
            }
            .element img {
              width: 100%;
              height: 100%;
              object-fit: contain;
              pointer-events: none;
              background: transparent;
            }
          </style>
        </head>
        <body>
          <div id="fullscreen-prompt" onclick="goFullscreen()">
            🖥️ Click to Enter Fullscreen<br>
            <span style="font-size: 18px; font-weight: normal;">Remove all bars and borders</span>
          </div>
          <div id="slide-container">
            <div id="slide"></div>
          </div>
          <script>
            // AGGRESSIVE FULLSCREEN MODE - Maximum chrome-less display
            function enterFullscreen() {
              const docEl = document.documentElement;
              const body = document.body;
              
              // Method 1: Standard Fullscreen API with all options
              const fullscreenOptions = {
                navigationUI: 'hide'  // Hide all browser UI
              };
              
              if (docEl.requestFullscreen) {
                docEl.requestFullscreen(fullscreenOptions).catch(err => {
                  docEl.requestFullscreen().catch(err2 => {
                    // Fullscreen failed silently
                  });
                });
              } else if (docEl.webkitRequestFullscreen) {
                docEl.webkitRequestFullscreen(Element.ALLOW_KEYBOARD_INPUT);
              } else if (docEl.mozRequestFullScreen) {
                docEl.mozRequestFullScreen();
              } else if (docEl.msRequestFullscreen) {
                docEl.msRequestFullscreen();
              }
              
              // Method 2: Force window to maximize (fallback)
              try {
                window.moveTo(0, 0);
                window.resizeTo(screen.width, screen.height);
              } catch (e) {
                // Window resize failed silently
              }
            }
            
            // Try multiple times to ensure fullscreen
            window.addEventListener('load', function() {
              enterFullscreen();
              setTimeout(enterFullscreen, 100);
              setTimeout(enterFullscreen, 500);
              setTimeout(enterFullscreen, 1000);
            });
            
            // Immediately try as well
            enterFullscreen();
            
            // Prevent exiting fullscreen - re-enter automatically
            ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(function(eventName) {
              document.addEventListener(eventName, function() {
                if (!document.fullscreenElement && !document.webkitFullscreenElement && 
                    !document.mozFullScreenElement && !document.msFullscreenElement) {
                  // Re-enter fullscreen if user accidentally exits
                  setTimeout(enterFullscreen, 300);
                }
              });
            });
            
            // F11 key handler - enter/exit fullscreen
            document.addEventListener('keydown', function(e) {
              if (e.key === 'F11') {
                e.preventDefault();
                enterFullscreen();
              }
            });
            
            // Keep cursor visible for hosts to click buttons
            // document.body.style.cursor = 'none'; // Removed - hosts need to see cursor
            document.addEventListener('contextmenu', function(e) {
              e.preventDefault();
              return false;
            });
            
            function renderSlide(slide, revealedCount = 0, isAnswerSlide = false, finalScoresData = null) {
              if (!slide) return;
              
              // HTML escape utility to prevent XSS from user-entered content
              function esc(str) {
                if (str == null) return '';
                return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
              }
              
              const slideEl = document.getElementById('slide');
              slideEl.style.background = slide.background || 'black';
              
              // Clear existing elements
              slideEl.innerHTML = '';
              
              // CHECK IF THIS IS THE FINAL SCORES SLIDE (Winners slide 5)
              const isFinalScoresSlide = slide.metadata?.roundType === 'WINNERS' && slide.metadata?.slideIndexInRound === 4;
              if (isFinalScoresSlide && finalScoresData && finalScoresData.teams.length > 0) {
                // MEMORY OPTIMIZED: Render final scores with controlled animation
                // - Uses CSS transforms with will-change for GPU acceleration
                // - Animation duration based on team count for smooth scrolling
                // - Removed duplicate DOM elements for memory efficiency
                const teamCount = finalScoresData.teams.length;
                // Dynamic duration: 4 seconds per team, minimum 20s, max 120s
                const scrollDuration = Math.min(120, Math.max(20, teamCount * 4));
                // Only enable scrolling if more than 5 teams (won't fit on screen)
                const needsScrolling = teamCount > 5;
                
                const scoresHTML = \`
                  <style>
                    @keyframes smoothScroll {
                      0% { transform: translateY(0); }
                      100% { transform: translateY(calc(-100% + 70vh)); }
                    }
                    .scroll-container {
                      position: absolute;
                      inset: 0;
                      overflow: hidden;
                      display: flex;
                      flex-direction: column;
                      z-index: 100;
                      background: rgba(0,0,0,0.9);
                      aspect-ratio: 16/9;
                      width: 100%;
                      height: 100%;
                      padding: 0 5%;
                      box-sizing: border-box;
                    }
                    .scroll-header {
                      flex-shrink: 0;
                      padding: 1.5rem 0;
                    }
                    .scroll-content-wrapper {
                      flex: 1;
                      overflow: hidden;
                      position: relative;
                      padding: 0;
                    }
                    .scroll-content {
                      \${needsScrolling ? \`animation: smoothScroll \${scrollDuration}s linear infinite;\` : ''}
                      will-change: transform;
                    }
                    .scroll-content:hover {
                      animation-play-state: paused;
                    }
                    .team-card {
                      border-radius: 12px;
                      padding: 1rem 1.5rem;
                      margin-bottom: 0.75rem;
                      will-change: auto;
                    }
                    .team-info {
                      display: flex;
                      align-items: center;
                      justify-content: space-between;
                    }
                    .team-rank {
                      font-size: 2.5rem;
                      font-weight: bold;
                      color: white;
                      min-width: 60px;
                    }
                    .team-name {
                      font-size: 2rem;
                      font-weight: bold;
                      color: white;
                    }
                    .team-total {
                      font-size: 3rem;
                      font-weight: bold;
                      color: #FFD700;
                      font-family: Lemonada, cursive;
                    }
                    .round-scores {
                      display: flex;
                      gap: 0.75rem;
                      margin-top: 0.5rem;
                      flex-wrap: wrap;
                    }
                    .round-score {
                      background: rgba(0,0,0,0.5);
                      padding: 0.5rem 1rem;
                      border-radius: 6px;
                    }
                    .round-label {
                      font-size: 0.9rem;
                      color: #999;
                    }
                    .round-value {
                      font-size: 1.1rem;
                      font-weight: bold;
                      color: white;
                      margin-left: 0.5rem;
                    }
                  </style>
                  <div class="scroll-container">
                    <div class="scroll-header">
                      <h2 style="font-size: 3.5rem; font-weight: bold; color: #FFD700; text-align: center; font-family: Lemonada, cursive;">
                        🏆 Final Scores 🏆
                      </h2>
                    </div>
                    <div class="scroll-content-wrapper">
                      <div class="scroll-content">
                        \${finalScoresData.teams.map((team, idx) => \`
                          <div class="team-card" style="background: linear-gradient(to right, \${idx === 0 ? 'rgba(255,215,0,0.35), rgba(255,165,0,0.35)' : idx === 1 ? 'rgba(192,192,192,0.35), rgba(169,169,169,0.35)' : idx === 2 ? 'rgba(205,127,50,0.35), rgba(160,82,45,0.35)' : 'rgba(0,0,139,0.35), rgba(0,0,70,0.35)'}); border: 2px solid \${idx === 0 ? '#FFD700' : idx === 1 ? '#C0C0C0' : idx === 2 ? '#CD7F32' : '#0066CC'};">
                            <div class="team-info">
                              <div style="display: flex; align-items: center; gap: 1.5rem;">
                                <span class="team-rank">\${idx + 1}.</span>
                                <div>
                                  <h3 class="team-name">\${esc(team.name)}</h3>
                                  \${team.swag ? \`<p style="font-size: 1rem; color: #ccc;">\${esc(team.swag)}</p>\` : ''}
                                </div>
                              </div>
                              <div style="text-align: right;">
                                <p class="team-total">\${esc(team.total)}</p>
                                <p style="font-size: 0.9rem; color: #999;">Total Points</p>
                              </div>
                            </div>
                            <div class="round-scores">
                              \${team.roundScores.map((score, roundIdx) => \`
                                <div class="round-score">
                                  <span class="round-label">\${esc(finalScoresData.rounds[roundIdx].label)}:</span>
                                  <span class="round-value">\${esc(score)}</span>
                                </div>
                              \`).join('')}
                            </div>
                          </div>
                        \`).join('')}
                      </div>
                    </div>
                  </div>
                \`;
                slideEl.innerHTML = scoresHTML;
                return; // Don't render normal slide elements
              }
              
              // Render elements
              if (slide.elements) {
                // CALCULATE FONT MULTIPLIER based on round type and slide position
                // This creates viewport-scaled fonts that work across all TV sizes
                const roundType = slide.metadata?.roundType;
                const slideIndex = slide.metadata?.slideIndexInRound || 0;
                const isWinnersSlide = roundType === 'WINNERS';
                const isAnswerSlideType = slide.metadata?.isAnswerSlide;
                
                // Determine the font multiplier based on requirements:
                // 1) MC questions: +10% (1.10)
                // 2) REG, MISC, MYS questions: +15% (1.15)
                // 3) BIG Question (slide 1) and BIG review (slide 3): +10% (1.10)
                // 4) All review slides (except BIG): +15% (1.15)
                // 5) All answer slides: +10% (1.10)
                // 6) Winners slides: no change (1.0)
                
                let fontMultiplier = 1.0;
                
                if (isWinnersSlide) {
                  fontMultiplier = 1.0; // No change for winners
                } else if (isAnswerSlide || isAnswerSlideType) {
                  fontMultiplier = 1.10; // Answer slides: +10%
                } else if (roundType === 'MC') {
                  // MC questions: +10%
                  fontMultiplier = 1.10;
                } else if (roundType === 'REG' || roundType === 'MISC' || roundType === 'MYS') {
                  // REG, MISC, MYS: Check if it's a question or review slide
                  // Question slides are typically 1-10, review slides are near the end
                  // REG/MISC have 14 slides total, MYS has 13 slides
                  // Question slides: index 1-10, Review slide: second to last (before answer)
                  const isReviewSlide = (roundType === 'MYS' && slideIndex === 10) || 
                                        ((roundType === 'REG' || roundType === 'MISC') && slideIndex === 11);
                  if (isReviewSlide) {
                    fontMultiplier = 1.15; // Review slides (except BIG): +15%
                  } else {
                    fontMultiplier = 1.15; // REG, MISC, MYS questions: +15%
                  }
                } else if (roundType === 'BIG') {
                  // BIG structure: 0=title, 1=question, 2=.gif, 3=review, 4=answers, 5-6=tiebreaker
                  // BIG has question at index 1 and review at index 3
                  if (slideIndex === 1 || slideIndex === 3) {
                    fontMultiplier = 1.10; // BIG question and review: +10%
                  } else {
                    fontMultiplier = 1.10; // Other BIG slides: +10%
                  }
                } else if (roundType === 'SPONSOR' || roundType === 'SCORE') {
                  fontMultiplier = 1.10; // Sponsor/Score slides: +10%
                } else {
                  fontMultiplier = 1.10; // Default: +10%
                }
                
                if (isAnswerSlide) {
                  // ANSWER SLIDE LOGIC - Apply reveal
                  // CRITICAL: Answer slides have NO TITLE - all text elements are answers
                  const textElements = slide.elements.filter(el => el.type === 'text');
                  const imageElements = slide.elements.filter(el => el.type === 'image');
                  
                  // Sort text by Y position (all are answers, no title)
                  const sortedText = [...textElements].sort((a, b) => a.y - b.y);
                  
                  sortedText.forEach((element, idx) => {
                    const el = document.createElement('div');
                    el.className = 'element';
                    el.style.position = 'absolute';
                    el.style.left = ((element.x / 1920) * 100) + '%';
                    el.style.top = ((element.y / 1080) * 100) + '%';
                    el.style.width = ((element.width / 1920) * 100) + '%';
                    el.style.height = ((element.height / 1080) * 100) + '%';
                    
                    // VIEWPORT-BASED FONT SCALING for readability across all displays
                    // Uses the pre-calculated fontMultiplier (1.10 for answer slides)
                    const baseFontSize = (element.fontSize || 16) * fontMultiplier;
                    const vwSize = (baseFontSize / 1920) * 100;
                    const minSize = Math.max(baseFontSize * 0.7, 14); // Min 70% of scaled size or 14px
                    const maxSize = baseFontSize * 1.5; // Max 150% of scaled size
                    el.style.fontSize = \`clamp(\${minSize}px, \${vwSize}vw, \${maxSize}px)\`;
                    
                    // Respect whiteSpace property from element (nowrap prevents unwanted wrapping)
                    if (element.whiteSpace) {
                      el.style.whiteSpace = element.whiteSpace;
                    }
                    
                    el.style.fontWeight = element.fontWeight || 'normal';
                    el.style.color = element.color || '#000000';
                    el.style.textAlign = element.textAlign || 'left';
                    el.style.fontFamily = element.fontFamily || 'Inter, sans-serif';
                    el.style.lineHeight = element.lineHeight || 1.5;
                    el.style.display = 'flex';
                    el.style.alignItems = 'center';
                    el.style.justifyContent = element.textAlign === 'center' ? 'center' : element.textAlign === 'right' ? 'flex-end' : 'flex-start';
                    el.textContent = element.content || '';
                    
                    // CRITICAL FIX: Hide ALL answers that haven't been revealed yet
                    // Since there's NO title, idx 0 is the first answer
                    // Hide answer if its index is >= revealCount (0-indexed)
                    if (idx >= revealedCount) {
                      el.style.visibility = 'hidden';
                    }
                    
                    slideEl.appendChild(el);
                  });
                  
                  // Render images/overlays (always visible)
                  imageElements.forEach(element => {
                    const el = document.createElement('div');
                    el.className = 'element';
                    el.style.position = 'absolute';
                    el.style.left = ((element.x / 1920) * 100) + '%';
                    el.style.top = ((element.y / 1080) * 100) + '%';
                    el.style.width = ((element.width / 1920) * 100) + '%';
                    el.style.height = ((element.height / 1080) * 100) + '%';
                    el.style.background = 'transparent'; // Ensure overlay transparency
                    const img = document.createElement('img');
                    img.src = element.src || '';
                    img.style.width = '100%';
                    img.style.height = '100%';
                    img.style.objectFit = 'contain';
                    img.style.background = 'transparent'; // Preserve PNG transparency
                    el.appendChild(img);
                    slideEl.appendChild(el);
                  });
                } else {
                  // NORMAL SLIDE LOGIC - Render everything normally
                  // Uses the pre-calculated fontMultiplier based on round type and slide position
                  
                  slide.elements.forEach(element => {
                    const el = document.createElement('div');
                    el.className = 'element';
                    el.style.position = 'absolute';
                    el.style.left = ((element.x / 1920) * 100) + '%';
                    el.style.top = ((element.y / 1080) * 100) + '%';
                    el.style.width = ((element.width / 1920) * 100) + '%';
                    el.style.height = ((element.height / 1080) * 100) + '%';
                    
                    // VIEWPORT-BASED FONT SCALING for text elements
                    // Uses the pre-calculated fontMultiplier based on round type
                    if (element.type === 'text') {
                      const baseFontSize = (element.fontSize || 16) * fontMultiplier;
                      const vwSize = (baseFontSize / 1920) * 100;
                      const minSize = Math.max(baseFontSize * 0.7, 14);
                      const maxSize = baseFontSize * 1.5;
                      el.style.fontSize = \`clamp(\${minSize}px, \${vwSize}vw, \${maxSize}px)\`;
                      
                      // Respect whiteSpace property from element (nowrap prevents unwanted wrapping)
                      if (element.whiteSpace) {
                        el.style.whiteSpace = element.whiteSpace;
                      }
                    }
                    
                    el.style.fontWeight = element.fontWeight || 'normal';
                    el.style.color = element.color || '#000000';
                    el.style.textAlign = element.textAlign || 'left';
                    el.style.fontFamily = element.fontFamily || 'Inter, sans-serif';
                    el.style.lineHeight = element.lineHeight || 1.5;
                    el.style.display = 'flex';
                    el.style.alignItems = 'center';
                    el.style.justifyContent = element.textAlign === 'center' ? 'center' : element.textAlign === 'right' ? 'flex-end' : 'flex-start';
                    
                    if (element.type === 'text') {
                      el.textContent = element.content || '';
                    } else if (element.type === 'image') {
                      el.style.background = 'transparent'; // Ensure overlay transparency
                      const img = document.createElement('img');
                      img.src = element.src || '';
                      img.style.width = '100%';
                      img.style.height = '100%';
                      img.style.objectFit = 'contain';
                      img.style.background = 'transparent'; // Preserve PNG transparency
                      el.appendChild(img);
                    } else if (element.type === 'video' && element.videoSrc) {
                      // Video with AUDIO enabled on audience view
                      const vid = document.createElement('video');
                      vid.src = element.videoSrc;
                      vid.style.width = '100%';
                      vid.style.height = '100%';
                      vid.style.objectFit = 'contain';
                      vid.autoplay = true;
                      vid.loop = true;
                      vid.playsInline = true;
                      vid.muted = false; // Audio ON for audience
                      el.appendChild(vid);
                    }
                    
                    slideEl.appendChild(el);
                  });
                }
              }
            }
            
            // Listen for slide updates and reveals
            let currentSlideData = null;
            let currentRevealCount = 0;
            
            window.addEventListener('message', function(event) {
              if (event.data.type === 'UPDATE_SLIDE') {
                currentSlideData = event.data.slide;
                currentRevealCount = event.data.revealedCount || 0;
                renderSlide(event.data.slide, currentRevealCount, event.data.isAnswerSlide, event.data.finalScoresData);
              } else if (event.data.type === 'REVEAL_ANSWER') {
                currentRevealCount = event.data.revealedCount;
                if (currentSlideData) {
                  renderSlide(currentSlideData, currentRevealCount, true);
                }
              }
            });
            
            // FULLSCREEN FUNCTION - Make truly borderless, chrome-less display
            function goFullscreen() {
              const elem = document.documentElement;
              const prompt = document.getElementById('fullscreen-prompt');
              
              if (elem.requestFullscreen) {
                elem.requestFullscreen().then(function() {
                  prompt.style.display = 'none';
                }).catch(function() {
                  // Keep prompt visible if fullscreen fails
                });
              } else if (elem.webkitRequestFullscreen) { // Safari
                elem.webkitRequestFullscreen();
                prompt.style.display = 'none';
              } else if (elem.msRequestFullscreen) { // IE11
                elem.msRequestFullscreen();
                prompt.style.display = 'none';
              } else if (elem.mozRequestFullScreen) { // Firefox
                elem.mozRequestFullScreen();
                prompt.style.display = 'none';
              }
            }
            
            // Initial render
            renderSlide(${JSON.stringify(initialSlide)}, ${initialRevealCount}, ${initialIsAnswerSlide}, null);
            
            // AUTOMATIC FULLSCREEN - Try to enter fullscreen immediately
            setTimeout(function() {
              goFullscreen();
            }, 300);
            
            // Show prompt if not in fullscreen after 2 seconds
            setTimeout(function() {
              if (!document.fullscreenElement && !document.webkitFullscreenElement && !document.mozFullScreenElement && !document.msFullscreenElement) {
                document.getElementById('fullscreen-prompt').style.display = 'block';
              }
            }, 2000);
            
            // Keep in fullscreen - prevent accidental exit
            document.addEventListener('fullscreenchange', function() {
              const prompt = document.getElementById('fullscreen-prompt');
              if (!document.fullscreenElement) {
                // Exited fullscreen - show prompt to re-enter
                prompt.style.display = 'block';
              } else {
                prompt.style.display = 'none';
              }
            });
            
            // Prevent F11 and ESC from exiting (show prompt instead)
            document.addEventListener('keydown', function(e) {
              if (e.key === 'Escape' || e.key === 'F11') {
                e.preventDefault();
                if (!document.fullscreenElement) {
                  document.getElementById('fullscreen-prompt').style.display = 'block';
                }
              }
            });
          </script>
        </body>
        </html>
      `);
      newWindow.document.close();
      
      // FORCE MOVE TO RIGHT DISPLAY - Enhanced positioning
      // Use screen.availWidth to calculate right display position
      setTimeout(() => {
        try {
          // Move window to the right display (primary width = left edge of second screen)
          const rightDisplayX = window.screen.availWidth;
          newWindow.moveTo(rightDisplayX, 0);
          
          // Resize to fill the screen (in case moveTo didn't work perfectly)
          newWindow.resizeTo(window.screen.availWidth, window.screen.availHeight);
          
          // Focus the window to ensure it's active for fullscreen
          newWindow.focus();
        } catch (error) {
          // Window positioning may fail on some browsers/displays
        }
      }, 100);
      
      setAudienceWindow(newWindow);
      
      // MEMORY FIX: Clear any existing interval before creating new one
      if (windowCheckIntervalRef.current) {
        clearInterval(windowCheckIntervalRef.current);
      }
      
      // Clean up on window close - store in ref for cleanup
      windowCheckIntervalRef.current = setInterval(() => {
        if (newWindow.closed) {
          clearInterval(windowCheckIntervalRef.current);
          windowCheckIntervalRef.current = null;
          setAudienceWindow(null);
          audienceWindowRef.current = null;
        }
      }, 1000);
    }
  };

  const closeAudienceView = () => {
    // MEMORY FIX: Clear the window check interval
    if (windowCheckIntervalRef.current) {
      clearInterval(windowCheckIntervalRef.current);
      windowCheckIntervalRef.current = null;
    }
    if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
      audienceWindowRef.current.close();
      setAudienceWindow(null);
      audienceWindowRef.current = null;
    }
  };

  // Cleanup on unmount - MEMORY FIX: Clean ALL resources
  useEffect(() => {
    return () => {
      // Clear timer interval
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      // Clear window check interval
      if (windowCheckIntervalRef.current) {
        clearInterval(windowCheckIntervalRef.current);
        windowCheckIntervalRef.current = null;
      }
      // Close audience window
      closeAudienceView();
    };
  }, []);

  useEffect(() => {
    const handleKeyPress = (e) => {
      // CRITICAL: Prevent keyboard navigation during auto-advance to avoid race condition
      if (isAutoAdvancingRef.current) {
        return;
      }
      
      // CRITICAL: Prevent spacebar navigation when Score Tracker is open
      // This allows hosts to enter team names with spaces without advancing slides
      if (isScoreTrackerOpen) {
        // Only allow Escape key to exit presentation when Score Tracker is open
        if (e.key === 'Escape') {
          onExit();
        }
        return;
      }
      
      // CRITICAL: Prevent keyboard navigation when typing in input fields
      // This prevents spacebar in any input/textarea from advancing slides
      const target = e.target;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }
      
      if (e.key === 'ArrowRight' || e.key === ' ') {
        goNext();
      } else if (e.key === 'ArrowLeft') {
        goPrev();
      } else if (e.key === 'Escape') {
        onExit();
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [goNext, goPrev, onExit, isScoreTrackerOpen]);

  return (
    <div className="fixed inset-0 z-50 bg-black">
      {/* Exit and Navigation Controls */}
      <div className="absolute top-4 right-4 z-10 flex gap-2">
        {onOpenScoreTracker && (
          <Button
            onClick={onOpenScoreTracker}
            variant="ghost"
            size="sm"
            className="bg-yellow-600/80 hover:bg-yellow-700 text-white"
          >
            <ListOrdered className="w-5 h-5 mr-2" />
            Score Tracker
          </Button>
        )}
        {audienceWindow ? (
          <Button
            onClick={closeAudienceView}
            variant="ghost"
            size="sm"
            className="bg-green-600/80 hover:bg-green-700 text-white"
          >
            <Monitor className="w-5 h-5 mr-2" />
            Close Audience View
          </Button>
        ) : (
          <Button
            onClick={openAudienceView}
            variant="ghost"
            size="sm"
            className="bg-blue-600/80 hover:bg-blue-700 text-white"
          >
            <Monitor className="w-5 h-5 mr-2" />
            Open Audience View
          </Button>
        )}
        <Button
          onClick={onExit}
          variant="ghost"
          size="sm"
          className="bg-black/50 hover:bg-black/70 text-white"
        >
          <X className="w-5 h-5" />
        </Button>
      </div>

      {/* Slide Content */}
      <div className="w-full h-full flex items-center justify-center p-8">
        <div
          className="relative w-full h-full max-w-[90vw] max-h-[95vh] overflow-y-auto"
          style={{
            background: currentSlide.background,
            aspectRatio: '16/9'
          }}
        >
          {currentSlide.elements.map((element) => {
            // Calculate font size scaled to match 1920x1080 appearance
            // Apply 10% reduction + resolution-based scaling for presenter view
            const baseFontSize = (element.fontSize || 16) * 0.9; // 10% reduction
            const scaledFontSize = baseFontSize * presenterScale; // Scale based on viewport vs 1920px
            
            return (
              <div
                key={element.id}
                className="absolute"
                style={{
                  left: `${(element.x / 1920) * 100}%`,
                  top: `${(element.y / 1080) * 100}%`,
                  width: `${(element.width / 1920) * 100}%`,
                  height: `${(element.height / 1080) * 100}%`,
                  fontSize: `${scaledFontSize}px`,
                  fontWeight: element.fontWeight,
                  color: element.color,
                  textAlign: element.textAlign,
                  fontFamily: element.fontFamily,
                  lineHeight: element.lineHeight || 1.5,
                  whiteSpace: element.whiteSpace || 'pre-wrap',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: element.textAlign === 'center' ? 'center' : element.textAlign === 'right' ? 'flex-end' : 'flex-start'
                }}
              >
                {element.type === 'text' && element.content}
                {element.type === 'image' && (
                  <img src={element.src} alt="" className="w-full h-full object-contain" style={{ background: 'transparent' }} />
                )}
                {/* Overlay type - resolves overlayId from cache */}
                {element.type === 'overlay' && overlayCache?.current && overlayCache.current[element.overlayId] && (
                  <img src={overlayCache.current[element.overlayId]} alt="" className="w-full h-full object-contain" style={{ background: 'transparent' }} />
                )}
                {element.type === 'overlay' && (!overlayCache?.current || !overlayCache.current[element.overlayId]) && (
                  <div className="w-full h-full flex items-center justify-center bg-yellow-500/20 text-yellow-500 text-sm">
                    Loading overlay...
                  </div>
                )}
                {/* Video element — muted on host view, audio plays on audience view */}
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
              </div>
            );
          })}
          
          {/* Auto-Advance Timer - Only visible to host when active */}
          {isTimerActive && timeRemaining !== null && (
            <div className="absolute top-4 right-4 bg-orange-600/90 text-white px-6 py-3 rounded-lg font-bold text-3xl border-2 border-orange-400">
              ⏱️ {Math.floor(timeRemaining / 60)}:{String(timeRemaining % 60).padStart(2, '0')}
            </div>
          )}
          
          {/* Score Slide Indicator - Only visible to host */}
          {currentSlide.metadata?.isScoreSlide && (
            <div className="absolute top-4 left-4 bg-yellow-500/90 text-black px-4 py-2 rounded-lg font-semibold text-sm">
              📊 Score Slide - Click &quot;Edit&quot; to add scores
            </div>
          )}
          
          {/* Reveal Answer Button - Only visible when audience is on an answer slide */}
          {audienceWindow && isAnswerSlide(audienceIndex) && (revealedAnswers[audienceIndex] || 0) < getAnswerCount(audienceIndex) && (
            <div className="absolute top-20 left-1/2 transform -translate-x-1/2 z-20">
              <Button
                onClick={revealNextAnswer}
                variant="ghost"
                size="lg"
                className="bg-yellow-600/95 hover:bg-yellow-700 text-white font-semibold text-lg px-8 py-6 border-2 border-yellow-400 shadow-lg"
              >
                <Eye className="w-6 h-6 mr-2" />
                Reveal Next Answer ({(revealedAnswers[audienceIndex] || 0)}/{getAnswerCount(audienceIndex)})
              </Button>
            </div>
          )}
          
          {/* Pre-Answer Slide Notification - Remind host to grade and add scores */}
          {/* MC/REG/MISC: Show on .gif slide (12) before answers (13) */}
          {/* MYS: Show on .gif slide (11) before answers (12) */}
          {(() => {
            const roundType = currentSlide?.metadata?.roundType;
            const slideIndex = currentSlide?.metadata?.slideIndexInRound;
            
            // Check if this is the .gif slide before answers for MC/REG/MISC/MYS rounds
            const isPreAnswerSlide = 
              ((roundType === 'MC' || roundType === 'REG' || roundType === 'MISC') && slideIndex === 12) ||
              (roundType === 'MYS' && slideIndex === 11);
            
            if (!isPreAnswerSlide) return null;
            
            return (
              <div className="absolute top-20 left-1/2 transform -translate-x-1/2 z-20 bg-yellow-600/95 backdrop-blur-sm px-8 py-4 rounded-lg border-2 border-yellow-400 shadow-lg max-w-lg">
                <p className="text-white font-bold text-xl mb-3">📝 Time to Grade & Score!</p>
                <div className="text-white text-sm space-y-2">
                  <p>1️⃣ <strong>Un-sync</strong> from audience view</p>
                  <p>2️⃣ <strong>Grade</strong> the answers on the next slide</p>
                  <p>3️⃣ <strong>Add scores</strong> to the Score Tracker</p>
                  <p>4️⃣ <strong>Re-sync</strong> and reveal answers to audience</p>
                </div>
              </div>
            );
          })()}
          
          {/* Winners Slide Notifications */}
          {currentSlide?.metadata?.roundType === 'WINNERS' && currentSlide?.metadata?.slideIndexInRound === 0 && (
            <div className="absolute top-20 left-1/2 transform -translate-x-1/2 z-20 bg-yellow-600/95 backdrop-blur-sm px-8 py-4 rounded-lg border-2 border-yellow-400 shadow-lg">
              <p className="text-white font-bold text-xl mb-3">📊 Time to Add Final Scores!</p>
              <p className="text-white text-sm mb-4">Click &quot;Score Tracker&quot; to add final round scores before showing the winners.</p>
            </div>
          )}
          
          {/* Final Scores Display - Winners Slide 5 (Full Leaderboard) - 16:9 Fullscreen */}
          {currentSlide?.metadata?.roundType === 'WINNERS' && currentSlide?.metadata?.slideIndexInRound === 4 && (() => {
            try {
              const scoresData = getFinalScores();
              if (!scoresData || !scoresData.teams || scoresData.teams.length === 0) {
                console.log('No scores data available for Final Scores slide');
                return null;
              }
              
              // BULLETPROOF: Validate rounds array exists
              const rounds = scoresData.rounds || [];
              
              return (
                <div className="absolute inset-0 flex items-center justify-center z-20" style={{ aspectRatio: '16/9', padding: '0 5%' }}>
                  <div className="bg-black/85 backdrop-blur-md w-full h-full p-6 flex flex-col overflow-hidden">
                    <h2 className="text-5xl font-bold text-yellow-400 text-center mb-6 flex-shrink-0" style={{ fontFamily: 'Lemonada, cursive' }}>
                      🏆 Final Scores 🏆
                    </h2>
                    
                    <div className="flex-1 min-h-0 overflow-y-auto space-y-3">
                      {scoresData.teams.map((team, idx) => {
                        // BULLETPROOF: Validate team object
                        if (!team) return null;
                        const teamName = team.name || `Team ${idx + 1}`;
                        const teamTotal = team.total || 0;
                        const teamSwag = team.swag || '';
                        const teamRoundScores = Array.isArray(team.roundScores) ? team.roundScores : [];
                        
                        return (
                          <div key={idx} className={`bg-gradient-to-r ${idx === 0 ? 'from-yellow-600/40 to-yellow-800/40 border-yellow-400' : idx === 1 ? 'from-gray-400/40 to-gray-600/40 border-gray-400' : idx === 2 ? 'from-amber-700/40 to-amber-900/40 border-amber-600' : 'from-blue-900/40 to-blue-950/40 border-blue-700'} border-2 rounded-lg p-4`}>
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-6">
                                <span className="text-4xl font-bold text-white min-w-[60px]">{idx + 1}.</span>
                                <div>
                                  <h3 className="text-3xl font-bold text-white">{teamName}</h3>
                                  {teamSwag && <p className="text-lg text-gray-300">{teamSwag}</p>}
                                </div>
                              </div>
                              <div className="text-right">
                                <p className="text-5xl font-bold text-yellow-400" style={{ fontFamily: 'Lemonada, cursive' }}>{teamTotal}</p>
                                <p className="text-sm text-gray-400">Total Points</p>
                              </div>
                            </div>
                            
                            {/* Round-by-round scores */}
                            {teamRoundScores.length > 0 && (
                              <div className="flex gap-3 mt-4 flex-wrap">
                                {teamRoundScores.map((score, roundIdx) => {
                                  // BULLETPROOF: Safe access to rounds array
                                  const roundLabel = rounds[roundIdx]?.label || `R${roundIdx + 1}`;
                                  const safeScore = score || 0;
                                  return (
                                    <div key={roundIdx} className="bg-black/50 px-4 py-2 rounded-lg">
                                      <span className="text-sm text-gray-400">{roundLabel}:</span>
                                      <span className="text-lg font-bold text-white ml-2">{safeScore}</span>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            } catch (err) {
              console.error('Error rendering Final Scores:', err);
              return null;
            }
          })()}
        </div>
      </div>

      {/* Host Navigation Arrows */}
      <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 flex items-center gap-4">
        <Button
          onClick={goPrev}
          disabled={currentIndex === 0}
          variant="ghost"
          size="lg"
          className="bg-black/50 hover:bg-black/70 text-white disabled:opacity-40"
        >
          <ChevronLeft className="w-6 h-6" />
        </Button>
        <span className="text-white font-semibold bg-black/50 px-4 py-2 rounded">
          Host: {currentIndex + 1} / {slides.length}
        </span>
        <Button
          onClick={goNext}
          disabled={currentIndex === slides.length - 1}
          variant="ghost"
          size="lg"
          className="bg-black/50 hover:bg-black/70 text-white disabled:opacity-40"
        >
          <ChevronRight className="w-6 h-4" />
        </Button>
      </div>

      {/* Save & Exit — shows on the last few slides with WINNERS/SCORES type, or the very last slide regardless */}
      {(
        (currentSlide?.metadata?.roundType === 'WINNERS') ||
        (currentSlide?.metadata?.roundType === 'SCORES') ||
        (currentSlide?.metadata?.roundType === 'TOTAL') ||
        (currentIndex >= slides.length - 3 && currentSlide?.metadata?.roundType !== 'MC' && currentSlide?.metadata?.roundType !== 'REG' && currentSlide?.metadata?.roundType !== 'MISC' && currentSlide?.metadata?.roundType !== 'MYS' && currentSlide?.metadata?.roundType !== 'BIG') ||
        (currentIndex === slides.length - 1)
      ) && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-[200]">
          <Button
            onClick={handleEndPresentation}
            disabled={isSavingScores || scoresSaved}
            size="lg"
            className={`font-black px-14 py-7 text-xl shadow-2xl rounded-2xl transition-all ${scoresSaved 
              ? 'bg-emerald-600 hover:bg-emerald-600 text-white' 
              : 'bg-gradient-to-r from-yellow-500 to-yellow-400 hover:from-yellow-400 hover:to-yellow-300 text-black animate-pulse'}`}
            style={!scoresSaved ? { boxShadow: '0 0 30px rgba(251, 221, 104, 0.6), 0 0 60px rgba(251, 221, 104, 0.3)' } : {}}
          >
            {isSavingScores ? (
              <><Loader2 className="w-6 h-6 mr-3 animate-spin" /> Saving Scores...</>
            ) : scoresSaved ? (
              <><CheckCircle className="w-6 h-6 mr-3" /> Saved! Click to Exit</>
            ) : (
              <><Flag className="w-6 h-6 mr-3" /> SAVE & EXIT</>
            )}
          </Button>
        </div>
      )}

      {/* Audience Control Panel - Only show if audience window is open */}
      {audienceWindow && (
        <div className="absolute bottom-16 left-1/2 transform -translate-x-1/2 bg-blue-900/90 backdrop-blur-sm px-6 py-3 rounded-lg border-2 border-blue-500">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between mb-1">
              <div className="text-white text-sm font-semibold">
                Audience Control
              </div>
              <Button
                onClick={toggleSync}
                variant="ghost"
                size="sm"
                className={`${isSyncEnabled ? 'bg-green-700 hover:bg-green-600' : 'bg-orange-700 hover:bg-orange-600'} text-white text-xs`}
                title={isSyncEnabled ? 'Pause auto-sync to grade answers' : 'Resume auto-sync with host'}
              >
                {isSyncEnabled ? (
                  <>
                    <Pause className="w-3 h-3 mr-1" />
                    Auto-Sync ON
                  </>
                ) : (
                  <>
                    <Play className="w-3 h-3 mr-1" />
                    Auto-Sync OFF
                  </>
                )}
              </Button>
            </div>
            <div className="flex items-center gap-3">
              <Button
                onClick={reverseAudience}
                disabled={audienceIndex === 0 || isSyncEnabled}
                variant="ghost"
                size="sm"
                className="bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-40"
                title={isSyncEnabled ? "Disabled during auto-sync" : "Move audience back"}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-white font-semibold text-sm min-w-[80px] text-center">
                Audience: {audienceIndex + 1}
              </span>
              <Button
                onClick={advanceAudience}
                disabled={audienceIndex === slides.length - 1 || isSyncEnabled}
                variant="ghost"
                size="sm"
                className="bg-blue-700 hover:bg-blue-600 text-white disabled:opacity-40"
                title={isSyncEnabled ? "Disabled during auto-sync" : "Move audience forward"}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
              <div className="w-px h-6 bg-blue-500 mx-2"></div>
              <Button
                onClick={syncAudienceToHost}
                variant="ghost"
                size="sm"
                className="bg-green-700 hover:bg-green-600 text-white"
                title="Jump audience to your current slide"
              >
                Sync Now
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PresentationMode;