import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Toolbar from '../components/Toolbar';
import SlideCanvas from '../components/SlideCanvas';
import SlideThumbnails from '../components/SlideThumbnails';
import PresentationMode from '../components/PresentationMode';
import { createNewSlide, createNewTextElement } from '../utils/mockData';
import { toast } from '../hooks/use-toast';
import { ArrowLeft, Loader2, ListOrdered } from 'lucide-react';
import { Button } from '../components/ui/button';
import { presentationAPI } from '../services/api';

import ScoreTrackerModal from '../components/ScoreTrackerModal';

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
  const [isApplyingOverlays, setIsApplyingOverlays] = useState(false);
  
  // MEMORY OPTIMIZATION: Store overlay images in a ref (not state) to avoid duplicating in slides
  // Slides only store overlayId references, not the full base64 data
  const overlayCache = useRef({});

  const currentSlide = presentation?.slides[currentSlideIndex];

  useEffect(() => {
    loadPresentation();
  }, []);

  // Trigger overlay auto-init after presentation is fully loaded
  useEffect(() => {
    if (presentation?.id && !loading && shouldAutoInitOverlays && !isApplyingOverlays) {
      console.log('Triggering auto-overlay initialization for:', presentation.id);
      console.log('Location:', presentation.location);
      triggerAutoOverlays();
    }
  }, [presentation?.id, loading, shouldAutoInitOverlays]);

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
            toast({ title: 'Error', description: 'Failed to load slides', variant: 'destructive' });
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
                toast({ title: '⚡ Loading...', description: 'From cache', variant: 'default' });
                
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
                  console.log(`Loaded ${allSlides.length} slides from cache`);
                }
              }
            } catch (cacheErr) {
              console.log('Cache unavailable, fetching fresh:', cacheErr.message);
            }
            
            // STEP 2: If cache failed, fetch from SharePoint section by section
            if (!slidesLoaded) {
              toast({ title: '📡 Fetching...', description: 'From SharePoint', variant: 'default' });
              
              const sectionsData = await presentationAPI.getSectionsList(presentationId);
              const sections = sectionsData?.sections || [];
              
              if (sections.length === 0) {
                throw new Error('No sections found');
              }
              
              let allSlides = [];
              let slideOrder = 0;
              
              for (let i = 0; i < sections.length; i++) {
                const section = sections[i];
                toast({ 
                  title: `Loading ${section.name}`, 
                  description: `${i + 1}/${sections.length}`, 
                  variant: 'default' 
                });
                
                try {
                  const sectionData = await presentationAPI.fetchSection(presentationId, section.name, {
                    roundType: section.roundType,
                    roundOrder: section.roundOrder
                  });
                  
                  const sectionSlides = sectionData?.slides || [];
                  for (const slide of sectionSlides) {
                    slide.order = slideOrder++;
                    allSlides.push(slide);
                  }
                } catch (sectionErr) {
                  console.error(`Section ${section.name} error:`, sectionErr);
                }
              }
              
              if (allSlides.length === 0) {
                throw new Error('No slides loaded');
              }
              
              data.slides = allSlides;
              
              // Cache in background for next time
              presentationAPI.storeAllSlides(presentationId, allSlides).catch(() => {});
            }
            
            // STEP 3: Get location metadata
            try {
              const triviaData = await presentationAPI.getTriviaPresentation(presentationId);
              if (triviaData?.location) {
                data.location = triviaData.location;
              }
            } catch (locErr) {
              console.log('Could not load location:', locErr.message);
            }
            
            const loadTime = ((Date.now() - startTime) / 1000).toFixed(1);
            toast({ title: '✅ Loaded!', description: `${data.slides.length} slides (${loadTime}s)`, variant: 'default' });
            
            // STEP 4: Mark for overlay application AFTER presentation displays
            if (data.location) {
              // Check if overlays already applied
              const hasOverlays = data.slides.some(s => s.elements?.some(e => e.zIndex === 1000));
              if (!hasOverlays) {
                setShouldAutoInitOverlays(true);
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
      toast({ title: 'Error', description: 'Failed to load presentation', variant: 'destructive' });
      navigate('/');
    } finally {
      setLoading(false);
    }
  };

  const handleAddSlide = () => {
    const newSlide = createNewSlide(presentation.slides.length);
    setPresentation({
      ...presentation,
      slides: [...presentation.slides, newSlide]
    });
    setCurrentSlideIndex(presentation.slides.length);
    toast({ title: 'Slide added', description: 'New slide created successfully' });
  };

  const handleDeleteSlide = () => {
    if (presentation.slides.length <= 1) {
      toast({ title: 'Cannot delete', description: 'Presentation must have at least one slide', variant: 'destructive' });
      return;
    }
    const newSlides = presentation.slides.filter((_, index) => index !== currentSlideIndex);
    setPresentation({ ...presentation, slides: newSlides });
    setCurrentSlideIndex(Math.max(0, currentSlideIndex - 1));
    toast({ title: 'Slide deleted', description: 'Slide removed successfully' });
  };

  const handleAddText = () => {
    const newElement = createNewTextElement(100, 100);
    const updatedSlides = [...presentation.slides];
    updatedSlides[currentSlideIndex] = {
      ...currentSlide,
      elements: [...currentSlide.elements, newElement]
    };
    setPresentation({ ...presentation, slides: updatedSlides });
    setSelectedElement(newElement);
  };

  const handleAddImage = () => {
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
  };

  const handleUpdateElement = (updatedElement) => {
    const updatedSlides = [...presentation.slides];
    updatedSlides[currentSlideIndex] = {
      ...currentSlide,
      elements: currentSlide.elements.map((el) =>
        el.id === updatedElement.id ? updatedElement : el
      )
    };
    setPresentation({ ...presentation, slides: updatedSlides });
    setSelectedElement(updatedElement);
  };

  const handleDeleteElement = (elementId) => {
    const updatedSlides = [...presentation.slides];
    updatedSlides[currentSlideIndex] = {
      ...currentSlide,
      elements: currentSlide.elements.filter((el) => el.id !== elementId)
    };
    setPresentation({ ...presentation, slides: updatedSlides });
    setSelectedElement(null);
  };

  const handleReorderSlides = (fromIndex, toIndex) => {
    const newSlides = [...presentation.slides];
    const [removed] = newSlides.splice(fromIndex, 1);
    newSlides.splice(toIndex, 0, removed);
    
    // Update order property
    newSlides.forEach((slide, index) => {
      slide.order = index;
    });
    
    setPresentation({ ...presentation, slides: newSlides });
    setCurrentSlideIndex(toIndex);
  };

  const handleOpenScoreTracker = () => {
    setIsScoreTrackerOpen(true);
  };

  const handleCloseScoreTracker = () => {
    setIsScoreTrackerOpen(false);
  };

  // Helper function to calculate dynamic font size based on team name length
  const calculateDynamicFontSize = (teamName, baseFontSize, maxWidth) => {
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

  const handleSendScores = async (teams, roundMode, rounds) => {
    try {
      console.log('=== handleSendScores called ===');
      console.log('Teams:', teams.length, 'Round Mode:', roundMode, 'Rounds:', rounds.length);
      
      // Calculate top 3 teams with total scores
      const teamsWithTotals = teams
        .filter(team => team.name.trim() !== '')
        .map(team => {
          const roundScores = team.rounds.slice(0, rounds.length).map((score, idx) => {
            const points = parseInt(score) || 0;
            return points * rounds[idx].multiplier;
          });
          const roundTotal = roundScores.reduce((sum, score) => sum + score, 0);
          const swagPoints = parseInt(team.swag) || 0;
          const total = roundTotal + swagPoints;
          
          return {
            name: team.name,
            swag: team.swag,
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
        if (slide.metadata?.isScoreSlide) {
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
          el.type === 'text' && el.id?.startsWith('score-') || el.id?.startsWith('rank-')
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
          if (slide.metadata?.roundType === 'WINNERS') {
            winnerSlideIndices.push({ 
              index, 
              slideIndexInRound: slide.metadata?.slideIndexInRound 
            });
            console.log(`Found WINNERS slide at index ${index}, slideIndexInRound: ${slide.metadata?.slideIndexInRound}`);
          }
        });
        
        console.log(`Found ${winnerSlideIndices.length} winner slides`);
      
        // 3rd Place - Winners slide 2 (slideIndexInRound: 1)
        if (top3[2]) {
          const thirdPlaceSlide = winnerSlideIndices.find(item => item.slideIndexInRound === 1);
          console.log(`3rd place slide:`, thirdPlaceSlide, 'Team:', top3[2].name);
          
          if (thirdPlaceSlide) {
            // Remove any existing winner elements before adding new ones
            const cleanedElements = (updatedSlides[thirdPlaceSlide.index].elements || []).filter(
              el => !el.id?.startsWith('winner-')
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
                  content: top3[2].name,
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
                  content: `${top3[2].total} Points`,
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
        
        // 2nd Place - Winners slide 3 (slideIndexInRound: 2)
        if (top3[1]) {
          const secondPlaceSlide = winnerSlideIndices.find(item => item.slideIndexInRound === 2);
          console.log(`2nd place slide:`, secondPlaceSlide, 'Team:', top3[1].name);
          
          if (secondPlaceSlide) {
            // Remove any existing winner elements before adding new ones
            const cleanedElements = (updatedSlides[secondPlaceSlide.index].elements || []).filter(
              el => !el.id?.startsWith('winner-')
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
                  content: top3[1].name,
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
                  content: `${top3[1].total} Points`,
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
        
        // 1st Place - Winners slide 4 (slideIndexInRound: 3)
        if (top3[0]) {
          const firstPlaceSlide = winnerSlideIndices.find(item => item.slideIndexInRound === 3);
          console.log(`1st place slide:`, firstPlaceSlide, 'Team:', top3[0].name);
          
          if (firstPlaceSlide) {
            // Remove any existing winner elements before adding new ones
            const cleanedElements = (updatedSlides[firstPlaceSlide.index].elements || []).filter(
              el => !el.id?.startsWith('winner-')
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
                  content: top3[0].name,
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
                  content: `${top3[0].total} Points`,
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
      } // End of allRoundsComplete check

      setPresentation({
        ...presentation,
        slides: updatedSlides
      });

      // Navigate to the updated score slide so host can see it
      setCurrentSlideIndex(scoreSlideIndex);

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

      // Auto-save in background (non-blocking)
      presentationAPI.update(presentation.id, {
        slides: updatedSlides,
        name: presentation.name
      }).catch(saveError => {
        console.warn('Auto-save failed (scores displayed correctly):', saveError);
        // Only show warning if auto-save fails - scores are already displayed
        toast({ 
          title: 'Auto-save Warning', 
          description: 'Scores displayed but auto-save failed. Click Save to persist changes.',
        });
      });

    } catch (error) {
      console.error('Error sending scores:', error);
      toast({ 
        title: 'Error', 
        description: `Failed to update score slide: ${error.message || 'Unknown error'}`, 
        variant: 'destructive' 
      });
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
        content: team.name,
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
      
      // Round scores
      team.rounds.slice(0, rounds.length).forEach((score, roundIdx) => {
        const points = parseInt(score) || 0;
        const multipliedScore = points * rounds[roundIdx].multiplier;
        
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
      await presentationAPI.update(presentation.id, {
        slides: presentation.slides,
        name: presentation.name
      });
      toast({ title: 'Saved', description: 'Presentation saved successfully' });
    } catch (error) {
      console.error('Error saving presentation:', error);
      toast({ title: 'Error', description: 'Failed to save presentation', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const triggerAutoOverlays = async () => {
    if (!presentation?.location || !presentation?.slides || isApplyingOverlays) {
      console.log('Skipping auto-overlays - no location/slides or already applying');
      return;
    }

    try {
      setIsApplyingOverlays(true);
      setShouldAutoInitOverlays(false);
      
      toast({ title: '🎨 Loading Overlays...', description: 'Fetching overlay metadata', variant: 'default' });
      console.log('Auto-applying overlays for location:', presentation.location);

      const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
      const API = `${BACKEND_URL}/api`;
      
      // Extract location name from path
      const locationName = presentation.location.split('/').pop();
      console.log('Location name:', locationName);
      
      // STEP 1: Get overlay METADATA (lightweight - no image downloads)
      const metadataResponse = await fetch(`${API}/overlays/metadata/${encodeURIComponent(locationName)}`);
      
      if (!metadataResponse.ok) {
        throw new Error('Failed to fetch overlay metadata');
      }
      
      const metadataResult = await metadataResponse.json();
      const overlayMetadata = metadataResult.overlays || [];
      
      if (overlayMetadata.length === 0) {
        toast({ title: 'No Overlays', description: 'No overlays available for this location' });
        return;
      }
      
      console.log(`Found ${overlayMetadata.length} overlays, loading images...`);
      
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
      
      // STEP 2: Identify which overlays we actually need based on slides
      const neededOverlayPaths = new Set();
      const updatedSlides = [...presentation.slides];
      
      // Scan slides to find needed overlays
      for (let i = 0; i < updatedSlides.length; i++) {
        const slide = updatedSlides[i];
        const metadata = slide.metadata || {};
        
        if (metadata.isRoundTitle) {
          const roundNum = metadata.roundNumber;
          const roundType = metadata.roundType;
          const roundOverlayMeta = overlayByRound[roundNum];
          
          if (roundOverlayMeta) {
            neededOverlayPaths.add(roundOverlayMeta.path);
          }
          
          // Answer overlay needed for most rounds
          if (answerOverlayMeta && ['MC', 'REG', 'MISC', 'MYS'].includes(roundType)) {
            neededOverlayPaths.add(answerOverlayMeta.path);
          }
        }
        
        // Check for sponsor slides
        if (metadata.roundType === 'SPONSOR' && sponsorOverlayMeta) {
          neededOverlayPaths.add(sponsorOverlayMeta.path);
        }
      }
      
      console.log(`Need to load ${neededOverlayPaths.size} unique overlays`);
      toast({ title: '🎨 Downloading...', description: `Loading ${neededOverlayPaths.size} overlays`, variant: 'default' });
      
      // STEP 3: Download needed overlays ONE AT A TIME (lazy loading)
      // MEMORY OPTIMIZATION: Store in ref cache, not duplicated in each slide
      let loadedCount = 0;
      
      for (const path of neededOverlayPaths) {
        try {
          // Skip if already cached
          if (overlayCache.current[path]) {
            loadedCount++;
            continue;
          }
          
          const imageResponse = await fetch(`${API}/overlays/image?path=${encodeURIComponent(path)}`);
          if (imageResponse.ok) {
            const imageData = await imageResponse.json();
            if (imageData.success && imageData.dataUrl) {
              // Store in ref cache (not in slide state)
              overlayCache.current[path] = imageData.dataUrl;
              loadedCount++;
              
              // Update progress toast
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
      
      console.log(`Downloaded ${loadedCount} overlay images to cache`);
      toast({ title: '🎨 Applying...', description: `Applying overlays to slides`, variant: 'default' });
      
      // STEP 4: Apply overlays to slides
      // MEMORY OPTIMIZATION: Store only overlayId reference, not full base64 data
      let appliedCount = 0;
      
      // Helper function to apply an overlay to a slide
      const applyOverlayToSlide = (slideIndex, overlayPath) => {
        if (slideIndex >= 0 && slideIndex < updatedSlides.length && overlayCache.current[overlayPath]) {
          // Remove existing overlays
          updatedSlides[slideIndex].elements = (updatedSlides[slideIndex].elements || [])
            .filter(e => e.zIndex !== 1000);
          
          // Add overlay element with REFERENCE to cache, not the actual data
          // The rendering component will resolve overlayId -> actual base64
          updatedSlides[slideIndex].elements.push({
            type: 'overlay',
            overlayId: overlayPath, // Reference to cache key
            x: 0,
            y: 0,
            width: 1920,
            height: 1080,
            zIndex: 1000
          });
          appliedCount++;
        }
      };
      
      // Apply overlays based on round type rules
      for (let i = 0; i < updatedSlides.length; i++) {
        const slide = updatedSlides[i];
        const metadata = slide.metadata || {};
        
        if (metadata.isRoundTitle) {
          const roundNum = metadata.roundNumber;
          const roundType = metadata.roundType;
          const roundOverlayMeta = overlayByRound[roundNum];
          
          if (roundOverlayMeta) {
            // Apply based on round type
            if (roundType === 'MC' || roundType === 'REG' || roundType === 'MISC') {
              // Slides 2-11 (questions), slide 14 (answer)
              for (let j = 1; j <= 10; j++) applyOverlayToSlide(i + j, roundOverlayMeta.path);
              if (answerOverlayMeta) applyOverlayToSlide(i + 13, answerOverlayMeta.path);
            } else if (roundType === 'MYS') {
              // Slides 2-10, slide 13 (answer)
              for (let j = 1; j <= 9; j++) applyOverlayToSlide(i + j, roundOverlayMeta.path);
              if (answerOverlayMeta) applyOverlayToSlide(i + 12, answerOverlayMeta.path);
            } else if (roundType === 'BIG') {
              // Slide 2, slides 4-7
              applyOverlayToSlide(i + 1, roundOverlayMeta.path);
              for (let j = 3; j <= 6; j++) applyOverlayToSlide(i + j, roundOverlayMeta.path);
            }
          }
        }
      }
      
      // Apply sponsor overlay to second-to-last SPONSOR slide
      if (sponsorOverlayMeta && overlayCache.current[sponsorOverlayMeta.path]) {
        const sponsorSlideIndices = [];
        for (let i = 0; i < updatedSlides.length; i++) {
          const metadata = updatedSlides[i].metadata || {};
          if (metadata.roundType === 'SPONSOR') {
            sponsorSlideIndices.push(i);
          }
        }
        
        if (sponsorSlideIndices.length >= 2) {
          applyOverlayToSlide(sponsorSlideIndices[sponsorSlideIndices.length - 2], sponsorOverlayMeta.path);
        } else if (sponsorSlideIndices.length === 1) {
          applyOverlayToSlide(sponsorSlideIndices[0], sponsorOverlayMeta.path);
        }
      }
      
      // STEP 5: Update presentation state with overlaid slides
      if (appliedCount > 0) {
        setPresentation(prev => ({
          ...prev,
          slides: updatedSlides
        }));
        
        toast({ 
          title: '✨ Overlays Applied!', 
          description: `Applied ${appliedCount} overlays` 
        });
        console.log(`Applied ${appliedCount} overlays client-side`);
      } else {
        toast({ 
          title: 'No Overlays Applied', 
          description: 'Could not match overlays to slides' 
        });
      }
      
    } catch (error) {
      console.error('Error in auto-overlay application:', error);
      toast({ 
        title: '⚠️ Overlay Error', 
        description: error.message || 'Failed to apply overlays', 
        variant: 'destructive' 
      });
    } finally {
      setIsApplyingOverlays(false);
    }
  };

  const handleOverlaysApplied = async (result) => {
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
  };


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
      {/* Overlay Application Loading Indicator */}
      {isApplyingOverlays && (
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
            onStartPresentation={() => setIsPresentationMode(true)}
            onSave={handleSave}
            onOpenScoreTracker={handleOpenScoreTracker}
            selectedElement={selectedElement}
            onUpdateElement={handleUpdateElement}
            canDelete={presentation.slides.length > 1}
            presentationId={presentation.id}
            locationName={presentation.location ? presentation.location.split('/').pop() : null}
            onOverlaysApplied={handleOverlaysApplied}
            slides={presentation.slides}
          />

          {/* Main Content */}
          <div className="flex-1 flex overflow-hidden">
            <SlideThumbnails
              slides={presentation.slides}
              currentSlideIndex={currentSlideIndex}
              onSelectSlide={setCurrentSlideIndex}
              onAddSlide={handleAddSlide}
              onReorderSlides={handleReorderSlides}
              overlayCache={overlayCache}
            />
            <div className="flex-1 flex items-center justify-center bg-[#2a2a2a] p-8 overflow-auto relative">
              <SlideCanvas
                slide={currentSlide}
                selectedElement={selectedElement}
                onSelectElement={setSelectedElement}
                onUpdateElement={handleUpdateElement}
                onDeleteElement={handleDeleteElement}
                overlayCache={overlayCache}
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
          slides={presentation.slides}
          onExit={() => setIsPresentationMode(false)}
          onOpenScoreTracker={handleOpenScoreTracker}
          presentationId={presentation.id}
          isScoreTrackerOpen={isScoreTrackerOpen}
          overlayCache={overlayCache}
        />
      )}

      {/* Score Tracker Modal */}
      <ScoreTrackerModal
        isOpen={isScoreTrackerOpen}
        onClose={handleCloseScoreTracker}
        defaultRoundMode={presentation?.numRounds || 5}
        onSendScores={handleSendScores}
        presentationId={presentation?.id}
      />
    </div>
  );
};

export default Editor;