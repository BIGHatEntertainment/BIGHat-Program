import React, { useState, useEffect, useCallback, useRef } from 'react';
import { isTauri, openNativeAudience } from '../../../lib/audienceWindow';
import { X, ChevronLeft, ChevronRight, Monitor, ListOrdered, Pause, Play, Eye, Flag, Loader2, CheckCircle, HelpCircle } from 'lucide-react';
import { Button } from '../../ui/button';
import { toast } from '../../../utils/toastCompat';
import axios from 'axios';
import { needsTiebreaker } from '../../../lib/tiebreaker';
import FinalScoresBoard from '../final/FinalScoresBoard';

// alpha.87: bundled winners videos are stored as a short relative URL
// (/api/native/winners-video/1st). Make it absolute for the backend.
const resolveVideoSrc = (src) =>
  (typeof src === 'string' && src.startsWith('/api/'))
    ? `${process.env.REACT_APP_BACKEND_URL || ''}${src}` : src;


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
  // v32.0.0-alpha.47: BroadcastChannel is the new primary transport to
  // the audience view (which is now a real /trivia/audience route, not
  // an inline HTML blob). We keep window.postMessage in parallel for
  // backwards compatibility during the migration.
  const audienceChannelRef = useRef(null);

  // Init BroadcastChannel once. Also listen for AUDIENCE_READY so we can
  // push the current slide the instant the audience window boots.
  useEffect(() => {
    let bc = null;
    try {
      bc = new BroadcastChannel('bighat-trivia-audience');
      audienceChannelRef.current = bc;
    } catch (e) {
      console.warn('[presenter] BroadcastChannel unsupported:', e);
    }
    return () => {
      if (bc) {
        try { bc.close(); } catch (_e) { /* noop */ }
      }
      audienceChannelRef.current = null;
    };
  }, []);

  // Unified helper: publish to BroadcastChannel AND fall back to the
  // legacy audienceWindow.postMessage (in case a very old audience is
  // still listening).
  const broadcastToAudience = useCallback((message) => {
    if (audienceChannelRef.current) {
      try { audienceChannelRef.current.postMessage(message); }
      catch (_e) { /* noop */ }
    }
    if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
      try { audienceWindowRef.current.postMessage(message, '*'); }
      catch (_e) { /* noop */ }
    }
  }, []);
  
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

  // Answer Helper (host only): for the answer about to be revealed on an answer slide, return the matching
  // QUESTION text, pulled from this round's Review slide, so the host can re-read it aloud before revealing.
  // Only for MC/REG/MISC/MYS rounds (BIG and the tiebreaker are single-question, so they are left out).
  // It never touches the audience view. `revealIndex` is 0-based (the answer about to be revealed).
  const getQuestionForReveal = useCallback((slideIndex, revealIndex) => {
    const slide = slides[slideIndex];
    const md = slide?.metadata;
    const roundType = md?.roundType;
    if (!slide || !['MC', 'REG', 'MISC', 'MYS'].includes(roundType)) return null;
    if (!isAnswerSlide(slideIndex)) return null;   // only ever answer slides (same rule the Reveal button uses)

    const answerRel = md.slideIndexInRound;
    const reviewRel = answerRel - 2; // the .gif slide sits between the review slide and the answers in every round

    // Find THIS round's review slide by walking backward (handles a round type that is used more than once).
    let review = null;
    for (let j = slideIndex - 1; j >= 0 && j >= slideIndex - 6; j--) {
      const s = slides[j];
      if (s?.metadata?.roundType === roundType && s?.metadata?.slideIndexInRound === reviewRel) {
        review = s;
        break;
      }
    }
    if (!review) return null;

    // Answers use the SAME order the audience view reveals them in: text elements sorted by Y only
    // (see TriviaAudienceView renderAnswerSlide). The review slide is sorted the same way.
    const byY = (a, b) => a.y - b.y;
    const answerTexts = (slide.elements || []).filter(e => e.type === 'text').slice().sort(byY);
    const reviewTexts = (review.elements || []).filter(e => e.type === 'text').slice().sort(byY);
    const ansEl = answerTexts[revealIndex];
    if (!ansEl) return null;

    const leadNum = (c) => {
      const m = (c || '').trim().match(/^(\d+)/);
      return m ? parseInt(m[1], 10) : null;
    };
    const stripNum = (c) => (c || '').replace(/^\s*\d+\s*[.)]?\s*/, '').trim();

    // Primary: match by the leading question number (safe against titles and layout changes).
    const ansNum = leadNum(ansEl.content);
    if (ansNum != null) {
      const match = reviewTexts.find(e => leadNum(e.content) === ansNum);
      if (match) return stripNum(match.content);
    }
    // Fallback: line up the end of the review list with the answers (drops any leading title).
    const questions = reviewTexts.slice(Math.max(0, reviewTexts.length - answerTexts.length));
    return questions[revealIndex] ? stripNum(questions[revealIndex].content) : null;
  }, [slides, isAnswerSlide]);

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
      // alpha.63: SPECIAL shows (3..10 rounds) score by their own round types.
      // The Score Tracker saves the exact round types it scored with.
      const _mult = { MC: 1, REG: 1, MISC: 1, MYS: 2, BIG: 3 };
      const specialTypes = Array.isArray(parsed.roundTypes) && parsed.roundTypes.length >= 3 && parsed.roundTypes.length <= 10 && parsed.isSpecial
        ? parsed.roundTypes : null;
      const currentRounds = specialTypes
        ? specialTypes.map(t => ({ label: String(t).toUpperCase(), multiplier: _mult[String(t).toUpperCase()] || 1 }))
        : (roundConfigs[roundMode] || roundConfigs[5]);
      
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

  // alpha.66: location + date shown on the Final Scores board.
  const getBoardHeading = useCallback(() => {
    const presName = localStorage.getItem('currentPresentationName') || '';
    let location = '';
    const m = presName.match(/^(.+?)\s*-\s*\d/);
    if (m) location = m[1].trim();
    if (!location) {
      for (const sl of slides) {
        const loc = sl?.metadata?.location || sl?.metadata?.locationName;
        if (loc) { location = String(loc).replace(/^\d+_/, ''); break; }
      }
    }
    const date = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
    return { location, date };
  }, [slides]);

  // End Presentation: save scores ON THIS PC (Documents + AppData copy) and exit
  const handleEndPresentation = useCallback(async () => {
    const scoresData = getFinalScores();
    if (!scoresData || !scoresData.teams.length) {
      toast({ title: 'No Scores', description: 'No score data to save', variant: 'destructive' });
      return;
    }

    setIsSavingScores(true);
    let locationName = 'Unknown';
    try {
      // Get location name — try multiple sources
      locationName = (() => {
        // Source 0 (alpha.97): the venue the presentation was built for (saved with it)
        const savedVenue = (localStorage.getItem('currentPresentationLocation') || '').trim();
        if (savedVenue) return savedVenue;
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

      const saveRes = await axios.post(`${BACKEND_URL}/api/scores/save`, {
        locationName,
        presentationName: presName,
        presentationDate: dateStr,
        presentationId,
        teams: scoresData.teams,
        rounds: scoresData.rounds
      });

      setScoresSaved(true);
      toast({ title: 'Scores Saved!', description: `Saved on this PC: ${saveRes?.data?.folder || locationName}` });

      // Exit after brief delay
      setTimeout(() => onExit(), 2000);
    } catch (err) {
      console.error('Error saving scores:', err);
      // alpha.97: a failed save is a failed save. The server writes the file BEFORE anything else and only answers an
      // error when the file could not be written, so we never pretend it worked and never leave the show.
      const errMsg = err.response?.data?.detail || err.message || '';
      toast({ title: 'Scores NOT saved', description: errMsg || 'Could not save the scores on this PC. Nothing was lost; try again.', variant: 'destructive' });
    } finally {
      setIsSavingScores(false);
    }
  }, [getFinalScores, slides, presentationId, onExit]);

  // Update audience view helper - NOW safe to use isAnswerSlide and getFinalScores
  const updateAudienceView = useCallback((index) => {
    // v32.0.0-alpha.47: broadcast via BroadcastChannel primary + legacy
    // postMessage fallback. We still gate on audienceWindowRef so we
    // don't spam the BC when nobody's listening; but if EITHER channel
    // has a receiver we publish. `audienceChannelRef` receiver may be
    // in the AudienceView route (different window) OR nowhere yet — the
    // BroadcastChannel API is fire-and-forget, so it's cheap either way.
    const hasLegacyReceiver = audienceWindowRef.current && !audienceWindowRef.current.closed;
    const hasBcReceiver = !!audienceChannelRef.current;
    if (!hasLegacyReceiver && !hasBcReceiver) return;
      try {
        const slide = slides[index];
        const isAnswer = isAnswerSlide(index);
        const revealCount = revealedAnswers[index] || 0;
        
        // Get final scores if this is the final winners slide
        let finalScores = null;
        if (slide?.metadata?.roundType === 'WINNERS' && slide?.metadata?.slideIndexInRound === 4) {
          finalScores = getFinalScores();
          if (finalScores) finalScores = { ...finalScores, ...getBoardHeading() };
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
        
        broadcastToAudience({
          type: 'UPDATE_SLIDE',
          slide: resolvedSlide,
          isAnswerSlide: isAnswer,
          revealedCount: revealCount,
          finalScoresData: finalScores
        });
      } catch (error) {
        console.error('Error updating audience view:', error);
      }
  }, [slides, isAnswerSlide, revealedAnswers, getFinalScores, overlayCache, broadcastToAudience]);

  // alpha.66: the BIG tiebreaker is an IF event. Tiebreaker question + answer
  // slides are skipped (both directions) unless two or more teams share a
  // place in the top 5 in the Score Tracker.
  const tiebreakerNeeded = useCallback(() => {
    const data = getFinalScores();
    return !!(data && needsTiebreaker(data.teams));
  }, [getFinalScores]);

  const stepIndex = useCallback((from, dir) => {
    const list = slidesRef.current || slides;
    let i = from + dir;
    if (i < 0 || i > list.length - 1) return from;
    if (list[i]?.metadata?.isTiebreaker && !tiebreakerNeeded()) {
      while (i >= 0 && i <= list.length - 1 && list[i]?.metadata?.isTiebreaker) i += dir;
      if (i < 0 || i > list.length - 1) return from;
    }
    return i;
  }, [slides, tiebreakerNeeded]);

  // Host navigation - affects audience only if sync is enabled
  const goNext = useCallback(() => {
    setCurrentIndex((prev) => {
      const newIndex = stepIndex(prev, 1);
      // Auto-sync audience if enabled
      if (isSyncEnabled && audienceWindowRef.current && !audienceWindowRef.current.closed) {
        setAudienceIndex(newIndex);
        updateAudienceView(newIndex);
      }
      return newIndex;
    });
  }, [stepIndex, isSyncEnabled, updateAudienceView, audienceWindowRef]);

  const goPrev = useCallback(() => {
    setCurrentIndex((prev) => {
      const newIndex = stepIndex(prev, -1);
      // Auto-sync audience if enabled
      if (isSyncEnabled && audienceWindowRef.current && !audienceWindowRef.current.closed) {
        setAudienceIndex(newIndex);
        updateAudienceView(newIndex);
      }
      return newIndex;
    });
  }, [stepIndex, isSyncEnabled, updateAudienceView, audienceWindowRef]);
  
  // Audience navigation - only called explicitly by host
  const advanceAudience = useCallback(() => {
    setAudienceIndex((prev) => {
      const newIndex = stepIndex(prev, 1);
      updateAudienceView(newIndex);
      return newIndex;
    });
  }, [stepIndex, updateAudienceView]);
  
  const reverseAudience = useCallback(() => {
    setAudienceIndex((prev) => {
      const newIndex = stepIndex(prev, -1);
      updateAudienceView(newIndex);
      return newIndex;
    });
  }, [stepIndex, updateAudienceView]);

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
      broadcastToAudience({
        type: 'REVEAL_ANSWER',
        slideIndex: audienceIndex,
        revealedCount: newRevealed
      });
    }
  }, [audienceIndex, revealedAnswers, getAnswerCount, broadcastToAudience]);
  
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
                  broadcastToAudience({
                    type: 'UPDATE_SLIDE',
                    slide: resolvedSlide,
                    isAnswerSlide: isAnswer,
                    revealedCount: 0
                  });
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

  // v32.0.0-alpha.48: audience view now uses Tauri v2's proper
  // WebviewWindow API via dynamic import of `@tauri-apps/api/webviewWindow`.
  // The `window.__TAURI__` global is NOT injected unless
  // `withGlobalTauri: true` in tauri.conf.json — which is off by
  // default. Dynamic import works whether or not the global is set,
  // and rejects cleanly in browser/preview builds so we fall back to
  // window.open there. Communication is via BroadcastChannel (see
  // broadcastToAudience helper above).
  const audienceHandleRef = useRef(null);
  const openAudienceView = async () => {
    // v32.0.0-alpha.60: TAURI-FIRST. WebView2 blocks `window.open` inside
    // the desktop shell — the merchant hit the "allow pop-ups" toast on
    // every attempt. The capability file already whitelists the
    // 'trivia-audience' window label + core:webview:allow-create-webview-window,
    // so spawn a REAL native window there. Browser/preview builds keep the
    // synchronous window.open fallback (no await happens before it when
    // Tauri isn't detected, so the user-gesture context is preserved).
    if (isTauri()) {
      // Desktop app: NEVER fall back to window.open (WebView2 blocks it).
      try {
        const shim = {
          closed: false,
          close: () => { try { audienceHandleRef.current?.close(); } catch (_e) { /* gone */ } },
          postMessage: () => {}, // BroadcastChannel carries the real traffic
          focus: () => { try { audienceHandleRef.current?.setFocus(); } catch (_e) { /* best-effort */ } },
        };
        const { win, reused } = await openNativeAudience({
          label: 'trivia-audience',
          path: '/trivia/audience',
          title: 'BIG Hat - Audience View',
          onClosed: () => {
            shim.closed = true;
            setAudienceWindow(null);
            audienceWindowRef.current = null;
            audienceHandleRef.current = null;
          },
        });
        audienceHandleRef.current = win;
        audienceWindowRef.current = shim;
        setAudienceWindow(shim);
        if (!reused) {
          const bcTauri = audienceChannelRef.current;
          if (bcTauri) {
            bcTauri.addEventListener('message', (e) => {
              if (e?.data?.type === 'AUDIENCE_READY') updateAudienceView(audienceIndex);
            });
          }
        }
        setTimeout(() => updateAudienceView(audienceIndex), reused ? 300 : 1200);
      } catch (err) {
        console.error('[audience] native window failed:', err);
        toast({
          title: 'Audience view failed to open',
          description: String(err?.message || err),
          variant: 'destructive',
        });
      }
      return;
    }

    const hasSecondScreen = (window.screen?.availLeft || 0) !== 0
      || (window.screen?.availTop || 0) !== 0
      || (window.screenLeft || 0) !== 0
      || (window.screenTop || 0) !== 0;
    const primaryWidth = window.screen?.availWidth || 1920;
    const screenLeft = hasSecondScreen ? primaryWidth : 0;
    const audienceUrl = `${window.location.origin}/trivia/audience`;

    // Sync-first: open a plain window IMMEDIATELY.
    const winFeatures = `width=${window.screen?.availWidth || 1920},`
      + `height=${window.screen?.availHeight || 1080},`
      + `left=${screenLeft},top=0,toolbar=no,location=no,`
      + `directories=no,status=no,menubar=no,scrollbars=no,resizable=yes`;
    const opened = window.open(audienceUrl, 'TriviaAudienceView', winFeatures);

    if (!opened) {
      toast({
        title: 'Audience view blocked',
        description: 'Please allow pop-ups for BIG Hat, then try again.',
        variant: 'destructive',
      });
      return;
    }

    audienceWindowRef.current = opened;
    setAudienceWindow(opened);

    // Reposition to secondary display.
    if (typeof opened.moveTo === 'function') {
      setTimeout(() => {
        try {
          opened.moveTo(screenLeft, 0);
          if (typeof opened.resizeTo === 'function') {
            opened.resizeTo(window.screen?.availWidth || 1920, window.screen?.availHeight || 1080);
          }
          opened.focus?.();
        } catch (_e) { /* window positioning may fail */ }
      }, 100);
    }

    // Push the current slide the instant AUDIENCE_READY arrives on
    // the BroadcastChannel (React /trivia/audience mount signal).
    const bc = audienceChannelRef.current;
    if (bc) {
      const onReady = (e) => {
        if (e?.data?.type === 'AUDIENCE_READY') {
          updateAudienceView(audienceIndex);
        }
      };
      bc.addEventListener('message', onReady);
    }
    // Also fire once after a short delay in case the audience mounts
    // before we start listening.
    setTimeout(() => updateAudienceView(audienceIndex), 800);

    // Poll for window closed. Tauri v2's WebviewWindow.getByLabel is
    // still available if the merchant wants a native window later —
    // but the sync `window.open` is what actually works today.
    if (windowCheckIntervalRef.current) {
      clearInterval(windowCheckIntervalRef.current);
    }
    windowCheckIntervalRef.current = setInterval(() => {
      if (opened.closed) {
        clearInterval(windowCheckIntervalRef.current);
        windowCheckIntervalRef.current = null;
        setAudienceWindow(null);
        audienceWindowRef.current = null;
      }
    }, 1000);
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
      
      if (e.key === 'ArrowRight') {
        goNext();
      } else if (e.key === ' ' || e.key === 'Spacebar') {
        // Spacebar: on an answer slide (audience view open) with answers left, reveal the next answer
        // instead of advancing the slide. Once every answer is revealed, space advances like the right arrow.
        // Left / right arrows are always plain slide navigation.
        e.preventDefault();            // stop the page from scrolling
        if (e.repeat) return;          // ignore held-key auto-repeat so one long press cannot reveal several answers
        const revealActive = audienceWindow && isAnswerSlide(audienceIndex) &&
          (revealedAnswers[audienceIndex] || 0) < getAnswerCount(audienceIndex);
        if (revealActive) {
          revealNextAnswer();
        } else {
          goNext();
        }
      } else if (e.key === 'ArrowLeft') {
        goPrev();
      } else if (e.key === 'Escape') {
        onExit();
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [goNext, goPrev, onExit, isScoreTrackerOpen, audienceWindow, audienceIndex, revealedAnswers, isAnswerSlide, getAnswerCount, revealNextAnswer]);

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
                    src={resolveVideoSrc(element.videoSrc)}
                    className="w-full h-full object-contain"
                    autoPlay
                    loop={element.loop !== false}
                    muted
                    playsInline
                  />
                )}
              </div>
            );
          })}
          
          {/* Answer Helper: HOST-ONLY question reminder, left of the answers. Shows the question for the answer the
              Reveal button is about to show, moves on as answers are revealed, and disappears when all are revealed.
              Follows the AUDIENCE slide (the one Reveal Next Answer works on), so it stays right even with sync off.
              MC/REG/MISC/MYS only. Never sent to the audience window. */}
          {(() => {
            if (!audienceWindow || !isAnswerSlide(audienceIndex)) return null;
            const roundType = slides[audienceIndex]?.metadata?.roundType;
            if (!['MC', 'REG', 'MISC', 'MYS'].includes(roundType)) return null;
            const total = getAnswerCount(audienceIndex);
            const revealed = revealedAnswers[audienceIndex] || 0;
            if (total === 0 || revealed >= total) return null;
            const question = getQuestionForReveal(audienceIndex, revealed);
            if (!question) return null;
            return (
              <div
                className="absolute z-30"
                style={{ left: '1.5%', top: '50%', transform: 'translateY(-50%)', width: '38%', maxWidth: '38%' }}
                data-testid="host-question-reminder"
              >
                <div className="relative bg-slate-900/95 backdrop-blur-sm border-2 border-yellow-400 rounded-2xl shadow-2xl px-5 py-4">
                  <div className="flex items-center gap-2 mb-2">
                    <HelpCircle className="w-5 h-5 text-yellow-400 flex-shrink-0" />
                    <span className="text-yellow-400 font-bold text-sm uppercase tracking-wide" data-testid="host-question-reminder-label">
                      Question {revealed + 1} of {total}
                    </span>
                  </div>
                  <p className="text-white font-semibold leading-snug" style={{ fontSize: 'clamp(14px, 1.5vw, 22px)', maxHeight: '40vh', overflowY: 'auto' }} data-testid="host-question-reminder-text">
                    {question}
                  </p>
                  {/* Arrow pointing right toward the answers */}
                  <div className="absolute" style={{ right: '-14px', top: '50%', transform: 'translateY(-50%)', width: 0, height: 0, borderTop: '12px solid transparent', borderBottom: '12px solid transparent', borderLeft: '14px solid #facc15' }} />
                </div>
              </div>
            );
          })()}

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
                <FinalScoresBoard
                  teams={scoresData.teams}
                  rounds={rounds}
                  {...getBoardHeading()}
                />
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

      {/* Save & Exit — shows ONLY on the final scores slide (Winners slide index 4) */}
      {(
        (currentSlide?.metadata?.roundType === 'WINNERS' && currentSlide?.metadata?.slideIndexInRound === 4)
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