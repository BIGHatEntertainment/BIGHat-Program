import React, { useState, useEffect, useRef } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Label } from '../ui/label';
import { Checkbox } from '../ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Sparkles, Trophy, Play, Loader2, Monitor, ChevronRight, ChevronLeft } from 'lucide-react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const SlotMachineRandomizer = ({ open, onClose, onComplete, locations = [] }) => {
  const [phase, setPhase] = useState('location-selection');
  const [selectedLocation, setSelectedLocation] = useState('');
  const [selectedLocationPath, setSelectedLocationPath] = useState('');
  const [isLiveStreamShow, setIsLiveStreamShow] = useState(false);
  const [availableRounds, setAvailableRounds] = useState({ REG: [], MISC: [], BIG: [] });
  const [selectedOptions, setSelectedOptions] = useState({ REG: [], MISC: [], BIG: [] });
  const [spinning, setSpinning] = useState([false, false, false]);
  const [selectedRounds, setSelectedRounds] = useState({});
  const [selectedRoundPaths, setSelectedRoundPaths] = useState({});
  const [wheelPositions, setWheelPositions] = useState([0, 0, 0]);
  const [error, setError] = useState(null);
  
  // Build Phase State (for non-Live Stream)
  const [buildStep, setBuildStep] = useState(0);
  const [hosts, setHosts] = useState([]);
  const [selectedHost, setSelectedHost] = useState('');
  const [numRounds, setNumRounds] = useState(5);
  const [extraType, setExtraType] = useState('reg');
  const [selectedExtra, setSelectedExtra] = useState('');
  const [mcRounds, setMcRounds] = useState([]);
  const [mysRounds, setMysRounds] = useState([]);
  const [autoSelectedMC, setAutoSelectedMC] = useState(null);
  const [autoSelectedMYS, setAutoSelectedMYS] = useState(null);
  const [building, setBuilding] = useState(false);
  
  // Audience View State
  const [audienceWindow, setAudienceWindow] = useState(null);
  const audienceWindowRef = useRef(null);
  const windowCheckIntervalRef = useRef(null); // MEMORY FIX: Track window closed check interval

  // Animation & Audio refs
  const animationFrames = useRef([]);
  const spinStartTime = useRef([]);
  const spinningRef = useRef([false, false, false]);
  const audioContextRef = useRef(null);
  const spinningOscillatorsRef = useRef([]);

  // Initialize Web Audio API
  useEffect(() => {
    audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    return () => {
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, []);

  // Sound effect functions using Web Audio API
  const playSpinningSound = (wheelIndex) => {
    if (!audioContextRef.current) return;
    
    const audioContext = audioContextRef.current;
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    const baseFreq = 261.63;
    oscillator.frequency.value = baseFreq + (wheelIndex * 10);
    oscillator.type = 'sine';
    gainNode.gain.value = 0.08;
    
    const lfo = audioContext.createOscillator();
    const lfoGain = audioContext.createGain();
    lfo.frequency.value = 6;
    lfoGain.gain.value = 0.02;
    
    lfo.connect(lfoGain);
    lfoGain.connect(gainNode.gain);
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.start();
    lfo.start();
    
    spinningOscillatorsRef.current[wheelIndex] = { oscillator, lfo, gainNode };
  };

  const stopSpinningSound = (wheelIndex) => {
    if (spinningOscillatorsRef.current[wheelIndex]) {
      const { oscillator, lfo, gainNode } = spinningOscillatorsRef.current[wheelIndex];
      gainNode.gain.exponentialRampToValueAtTime(0.001, audioContextRef.current.currentTime + 0.1);
      setTimeout(() => {
        oscillator.stop();
        lfo.stop();
      }, 150);
      spinningOscillatorsRef.current[wheelIndex] = null;
    }
  };

  const playStopSound = (wheelIndex) => {
    if (!audioContextRef.current) return;
    
    const audioContext = audioContextRef.current;
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();
    
    const frequencies = [523.25, 659.25, 783.99];
    oscillator.frequency.value = frequencies[wheelIndex];
    oscillator.type = 'triangle';
    
    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.3);
    
    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);
    
    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.3);
  };

  const playJackpotSound = () => {
    if (!audioContextRef.current) return;
    
    const audioContext = audioContextRef.current;
    const frequencies = [1046.50, 1174.66, 1318.51, 1567.98, 2093.00];
    const timings = [0, 0.15, 0.3, 0.45, 0.6];
    
    frequencies.forEach((freq, idx) => {
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.frequency.value = freq;
      oscillator.type = 'sine';
      
      const startTime = audioContext.currentTime + timings[idx];
      gainNode.gain.setValueAtTime(0.4, startTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + 0.4);
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      oscillator.start(startTime);
      oscillator.stop(startTime + 0.4);
    });
  };

  // Audience View Functions
  const openAudienceView = () => {
    const hasSecondScreen = window.screen.availLeft !== 0 || window.screen.availTop !== 0 || 
                           window.screenLeft !== 0 || window.screenTop !== 0;
    const primaryWidth = window.screen.availWidth;
    const screenLeft = hasSecondScreen ? primaryWidth : 0;
    
    const newWindow = window.open(
      'about:blank',
      'RouletteAudienceView',
      `width=${window.screen.availWidth},height=${window.screen.availHeight},left=${screenLeft},top=0,fullscreen=yes,toolbar=no,location=no,directories=no,status=no,menubar=no,scrollbars=no,resizable=no,titlebar=no`
    );

    if (newWindow) {
      audienceWindowRef.current = newWindow;
      initializeAudienceWindow(newWindow);
      setAudienceWindow(newWindow);
      
      // MEMORY FIX: Clear existing interval before creating new one
      if (windowCheckIntervalRef.current) {
        clearInterval(windowCheckIntervalRef.current);
      }
      
      // Store in ref for cleanup
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
    // MEMORY FIX: Clear window check interval
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

  const initializeAudienceWindow = (win) => {
    win.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Round Roulette - Audience View</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
          * { margin: 0; padding: 0; box-sizing: border-box; }
          html, body { width: 100%; height: 100%; background: #0a0a0f; overflow: hidden; font-family: Inter, system-ui, sans-serif; }
          #content { width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; padding: 0.3rem; }
          .container { width: 100%; height: 100%; max-width: 1400px; display: flex; flex-direction: column; }
          .title { font-size: clamp(1.2rem, 2vw, 1.8rem); font-weight: bold; color: #FFC107; text-align: center; margin-bottom: 0.2rem; }
          .subtitle { font-size: clamp(0.7rem, 1vw, 0.9rem); color: #888; text-align: center; margin-bottom: 0.3rem; }
          .category-highlight { color: #FFC107; font-weight: bold; }
          
          /* Single category display for selection phase */
          .selection-container { display: flex; flex-direction: column; flex: 1; min-height: 0; padding: 0.5rem; }
          .selection-header { text-align: center; margin-bottom: 0.5rem; }
          .selection-category { font-size: clamp(1rem, 2vw, 1.5rem); font-weight: bold; margin-bottom: 0.25rem; }
          .selection-category.reg { color: #3b82f6; }
          .selection-category.misc { color: #FFC107; }
          .selection-category.big { color: #22c55e; }
          .selection-progress { font-size: clamp(0.7rem, 1vw, 0.9rem); color: #888; }
          .selection-progress-bar { width: 200px; max-width: 60%; height: 12px; background: #333; border-radius: 6px; margin: 0.3rem auto; overflow: hidden; }
          .selection-progress-fill { height: 100%; border-radius: 6px; transition: width 0.3s ease; }
          .selection-progress-fill.reg { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
          .selection-progress-fill.misc { background: linear-gradient(90deg, #FFC107, #FFD54F); }
          .selection-progress-fill.big { background: linear-gradient(90deg, #22c55e, #4ade80); }
          
          /* Options grid */
          .options-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 0.8rem; flex: 1; overflow-y: auto; padding: 1rem; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 1rem; border: 2px solid #333; }
          .option-item { background: rgba(255,255,255,0.08); padding: 1.2rem 1rem; border-radius: 0.5rem; font-size: clamp(1.1rem, 1.8vw, 1.5rem); color: white; text-align: center; border: 2px solid transparent; transition: all 0.3s ease; }
          .option-item.selected { border-color: #FFC107; background: rgba(255,193,7,0.2); color: #FFC107; font-weight: bold; }
          .option-item.selected::before { content: '✓ '; }
          
          /* Progress indicators at bottom */
          .progress-row { display: flex; justify-content: center; gap: 2rem; padding: 0.75rem; background: rgba(0,0,0,0.5); border-radius: 0.5rem; margin-top: 0.5rem; }
          .progress-item { text-align: center; }
          .progress-label { font-size: clamp(0.7rem, 1vw, 0.85rem); color: #666; margin-bottom: 0.2rem; }
          .progress-count { font-size: clamp(1rem, 1.5vw, 1.2rem); font-weight: bold; }
          .progress-count.complete { color: #22c55e; }
          .progress-count.active { color: #FFC107; }
          .progress-count.pending { color: #666; }
          
          /* Auto-scroll animation for options during selection */
          @keyframes optionsScroll {
            0% { transform: translateY(0); }
            100% { transform: translateY(-50%); }
          }
          .scroll-wrapper {
            flex: 1;
            overflow: hidden;
            position: relative;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 1rem;
            border: 2px solid #333;
          }
          .scroll-content {
            animation: optionsScroll 40s linear infinite;
          }
          .options-scroll-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1rem;
            padding: 1.2rem;
          }
          
          /* Ready to spin view */
          .ready-container { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; }
          .ready-title { font-size: clamp(2rem, 4vw, 3.5rem); font-weight: bold; color: #FFC107; margin-bottom: 2rem; text-shadow: 0 0 20px rgba(255, 193, 7, 0.5); animation: pulse 2s ease-in-out infinite; }
          @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
          .ready-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; max-width: 1000px; width: 100%; }
          .ready-card { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 1rem; padding: 1.5rem; border: 2px solid #FFC107; }
          .ready-card-title { font-size: clamp(1.2rem, 2vw, 1.6rem); font-weight: bold; color: #FFC107; text-align: center; margin-bottom: 1rem; }
          .ready-card-items { display: flex; flex-direction: column; gap: 0.5rem; }
          .ready-card-item { background: rgba(255,255,255,0.05); padding: 0.5rem 1rem; border-radius: 0.3rem; font-size: clamp(0.9rem, 1.3vw, 1.1rem); color: white; text-align: center; }
          
          /* Spinning phase styles */
          .wheel-container { display: flex; justify-content: center; align-items: center; gap: 1.5rem; height: calc(100vh - 5rem); max-height: 85vh; padding: 0.5rem 0; }
          .wheel { width: clamp(220px, 22vw, 280px); height: clamp(380px, 55vh, 480px); background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border: 3px solid #FFC107; border-radius: 0.8rem; position: relative; overflow: hidden; }
          .wheel-title { font-size: clamp(1rem, 1.6vw, 1.4rem); font-weight: bold; color: #FFC107; text-align: center; padding: 0.6rem; background: rgba(255,193,7,0.1); }
          .blur-background { position: absolute; top: 50px; left: 6px; right: 6px; bottom: 70px; overflow: hidden; border-radius: 0.4rem; }
          .blur-items { position: absolute; width: 100%; animation: blurScroll 0.3s linear infinite; opacity: 0.3; filter: blur(3px); will-change: transform; }
          .blur-item { height: 80px; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; color: white; padding: 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.2); }
          @keyframes blurScroll { 0% { transform: translateY(0); } 100% { transform: translateY(-80px); } }
          .flash-display { position: absolute; top: 50px; left: 6px; right: 6px; bottom: 70px; display: flex; align-items: center; justify-content: center; font-size: clamp(1.2rem, 2vw, 1.8rem); color: white; font-weight: bold; text-align: center; word-break: break-word; padding: 1rem; background: rgba(0,0,0,0.5); border-radius: 0.4rem; z-index: 5; }
          .selector-line { position: absolute; left: 0; right: 0; top: 50%; transform: translateY(-50%); height: 3px; background: #FFC107; box-shadow: 0 0 15px #FFC107; z-index: 10; pointer-events: none; }
          .winner-box { position: absolute; bottom: 6px; left: 6px; right: 6px; background: #FFC107; color: #000; font-size: clamp(0.85rem, 1.2vw, 1.1rem); font-weight: bold; padding: 0.6rem 0.4rem; text-align: center; border-radius: 0.4rem; min-height: 55px; display: flex; align-items: center; justify-content: center; word-break: break-word; }
          
          /* Result phase styles */
          .result-container { display: flex; flex-direction: column; height: 100%; justify-content: center; padding: 1.5rem; }
          .result-title { font-size: clamp(2rem, 4vw, 3rem); font-weight: bold; color: #FFC107; margin-bottom: 2rem; text-align: center; text-shadow: 0 0 20px rgba(255, 193, 7, 0.8); animation: pulse 2s ease-in-out infinite; will-change: transform; }
          .result-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; max-width: 1200px; margin: 0 auto; width: 100%; }
          .result-card { border-radius: 1rem; padding: 1.5rem; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3); animation: cardPop 0.5s ease-out forwards; position: relative; overflow: hidden; }
          .result-card::before { content: ''; position: absolute; top: -50%; left: -50%; width: 200%; height: 200%; background: linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent); animation: shine 3s infinite; pointer-events: none; }
          @keyframes cardPop { 0% { transform: scale(0.8); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
          @keyframes shine { 0% { transform: translate(-100%, -100%); } 100% { transform: translate(100%, 100%); } }
          .result-card-red { background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); border: 3px solid #fca5a5; box-shadow: 0 0 30px rgba(220, 38, 38, 0.5); }
          .result-card-blue { background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); border: 3px solid #93c5fd; box-shadow: 0 0 30px rgba(37, 99, 235, 0.5); }
          .result-card-yellow { background: linear-gradient(135deg, #f59e0b 0%, #b45309 100%); border: 3px solid #fde047; box-shadow: 0 0 30px rgba(245, 158, 11, 0.5); }
          .result-category { font-size: clamp(1.3rem, 2vw, 1.8rem); font-weight: bold; color: white; margin-bottom: 1rem; text-align: center; text-transform: uppercase; letter-spacing: 0.1rem; text-shadow: 0 2px 8px rgba(0, 0, 0, 0.5); }
          .result-round { font-size: clamp(1.2rem, 1.8vw, 1.6rem); color: white; font-weight: bold; text-align: center; word-break: break-word; background: rgba(0,0,0,0.3); padding: 1rem; border-radius: 0.5rem; text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5); }
        </style>
      </head>
      <body>
        <div id="content"></div>
        <script>
          let currentState = { phase: 'input', selectedOptions: {}, spinning: [false, false, false], selectedRounds: {}, wheelPositions: [0, 0, 0], availableRounds: {}, currentCategory: 'REG' };
          let lastPhase = 'input';
          let flashIntervals = [null, null, null];
          
          window.addEventListener('message', function(event) {
            if (event.data.type === 'UPDATE_STATE') {
              const newState = event.data.state;
              const phaseChanged = newState.phase !== lastPhase;
              
              currentState = newState;
              
              // Always re-render during input phase to show selections updating
              if (phaseChanged || newState.phase === 'input' || newState.phase === 'result') {
                lastPhase = newState.phase;
                
                if (newState.phase !== 'spinning') {
                  flashIntervals.forEach(interval => interval && clearInterval(interval));
                  flashIntervals = [null, null, null];
                }
                
                renderContent();
                
                if (newState.phase === 'spinning') {
                  startFlashing();
                }
              }
            }
          });
          
          function startFlashing() {
            const categories = ['REG', 'MISC', 'BIG'];
            
            categories.forEach((cat, idx) => {
              const options = currentState.selectedOptions[cat] || [];
              const displayElement = document.getElementById(\`flash-display-\${idx}\`);
              
              if (displayElement && options.length > 0) {
                if (flashIntervals[idx]) clearInterval(flashIntervals[idx]);
                
                flashIntervals[idx] = setInterval(() => {
                  if (currentState.selectedRounds[cat]) {
                    clearInterval(flashIntervals[idx]);
                    flashIntervals[idx] = null;
                    displayElement.textContent = currentState.selectedRounds[cat];
                    displayElement.style.fontSize = 'clamp(1.5rem, 3vw, 2.5rem)';
                    displayElement.style.color = '#FFC107';
                  } else {
                    const randomOption = options[Math.floor(Math.random() * options.length)];
                    displayElement.textContent = randomOption;
                  }
                }, 100);
              }
            });
          }
          
          function renderContent() {
            const container = document.getElementById('content');
            const { phase, selectedOptions, spinning, selectedRounds, wheelPositions, selectedLocation, availableRounds, currentCategory } = currentState;
            
            if (phase === 'input') {
              // Check if all 3 categories have 5 selections - show "Ready to Spin" view
              const regCount = (selectedOptions.REG || []).length;
              const miscCount = (selectedOptions.MISC || []).length;
              const bigCount = (selectedOptions.BIG || []).length;
              const allComplete = regCount >= 5 && miscCount >= 5 && bigCount >= 5;
              
              if (allComplete) {
                // Show ready to spin view with all selected options
                container.innerHTML = \`
                  <div class="container">
                    <div class="ready-container">
                      <div class="ready-title">🎰 Ready to Spin! 🎰</div>
                      <div class="ready-grid">
                        <div class="ready-card">
                          <div class="ready-card-title" style="color: #3b82f6;">🎯 REG Rounds</div>
                          <div class="ready-card-items">
                            \${(selectedOptions.REG || []).map(r => \`<div class="ready-card-item">\${r}</div>\`).join('')}
                          </div>
                        </div>
                        <div class="ready-card">
                          <div class="ready-card-title" style="color: #FFC107;">✨ MISC Rounds</div>
                          <div class="ready-card-items">
                            \${(selectedOptions.MISC || []).map(r => \`<div class="ready-card-item">\${r}</div>\`).join('')}
                          </div>
                        </div>
                        <div class="ready-card">
                          <div class="ready-card-title" style="color: #22c55e;">💎 BIG Rounds</div>
                          <div class="ready-card-items">
                            \${(selectedOptions.BIG || []).map(r => \`<div class="ready-card-item">\${r}</div>\`).join('')}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                \`;
              } else {
                // Show single category selection view with auto-scrolling options
                const categoryNames = { REG: 'REG - General Rounds', MISC: 'MISC - Specific Rounds', BIG: 'BIG - Final Questions' };
                const categoryEmojis = { REG: '🎯', MISC: '✨', BIG: '💎' };
                const currentCat = currentCategory || 'REG';
                const currentCount = (selectedOptions[currentCat] || []).length;
                const allOptions = (availableRounds[currentCat] || []).map(r => r.name || r);
                const selectedNames = selectedOptions[currentCat] || [];
                
                // Generate options HTML (will be duplicated for seamless scroll)
                const optionsHTML = allOptions.map(option => {
                  const isSelected = selectedNames.includes(option);
                  return \`<div class="option-item \${isSelected ? 'selected' : ''}">\${option}</div>\`;
                }).join('');
                
                container.innerHTML = \`
                  <div class="container">
                    <div class="title">🎰 Round Roulette 🎰</div>
                    <div class="subtitle">Location: \${selectedLocation || ''}</div>
                    
                    <div class="selection-container">
                      <div class="selection-header">
                        <div class="selection-category \${currentCat.toLowerCase()}">\${categoryEmojis[currentCat]} \${categoryNames[currentCat]}</div>
                        <div class="selection-progress">Selecting \${currentCount}/5 rounds</div>
                        <div class="selection-progress-bar">
                          <div class="selection-progress-fill \${currentCat.toLowerCase()}" style="width: \${(currentCount / 5) * 100}%"></div>
                        </div>
                      </div>
                      
                      <div class="scroll-wrapper">
                        <div class="scroll-content">
                          <div class="options-scroll-grid">
                            \${optionsHTML}
                          </div>
                          <!-- Duplicate for seamless loop -->
                          <div class="options-scroll-grid">
                            \${optionsHTML}
                          </div>
                        </div>
                      </div>
                      
                      <div class="progress-row">
                        <div class="progress-item">
                          <div class="progress-label">REG</div>
                          <div class="progress-count \${regCount >= 5 ? 'complete' : currentCat === 'REG' ? 'active' : 'pending'}">\${regCount}/5 \${regCount >= 5 ? '✓' : ''}</div>
                        </div>
                        <div class="progress-item">
                          <div class="progress-label">MISC</div>
                          <div class="progress-count \${miscCount >= 5 ? 'complete' : currentCat === 'MISC' ? 'active' : 'pending'}">\${miscCount}/5 \${miscCount >= 5 ? '✓' : ''}</div>
                        </div>
                        <div class="progress-item">
                          <div class="progress-label">BIG</div>
                          <div class="progress-count \${bigCount >= 5 ? 'complete' : currentCat === 'BIG' ? 'active' : 'pending'}">\${bigCount}/5 \${bigCount >= 5 ? '✓' : ''}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                \`;
              }
            } else if (phase === 'spinning' || phase === 'result') {
              const categories = ['REG', 'MISC', 'BIG'];
              const wheelsHTML = categories.map((cat, idx) => {
                const options = selectedOptions[cat] || [];
                const isSpinning = spinning[idx] && !selectedRounds[cat];
                
                const blurItems = isSpinning ? options.concat(options).concat(options).map(round => \`
                  <div class="blur-item">\${round}</div>
                \`).join('') : '';
                
                return \`
                  <div class="wheel">
                    <div class="wheel-title">\${cat}</div>
                    <div class="selector-line"></div>
                    \${isSpinning ? \`
                      <div class="blur-background">
                        <div class="blur-items">\${blurItems}</div>
                      </div>
                    \` : ''}
                    <div class="flash-display" id="flash-display-\${idx}">
                      \${selectedRounds[cat] || (options[0]) || 'Loading...'}
                    </div>
                    <div class="winner-box">
                      \${selectedRounds[cat] ? \`🎉 \${selectedRounds[cat]} 🎉\` : 'Spinning...'}
                    </div>
                  </div>
                \`;
              }).join('');
              
              if (phase === 'spinning') {
                container.innerHTML = \`
                  <div class="container">
                    <div class="title">🎰 Spinning the Wheels! 🎰</div>
                    <div class="wheel-container">\${wheelsHTML}</div>
                  </div>
                \`;
              } else {
                container.innerHTML = \`
                  <div class="result-container">
                    <div class="result-title">🎉 Your Random Rounds! 🎉</div>
                    <div class="result-grid">
                      <div class="result-card result-card-red">
                        <div class="result-category">🎯 REG Round 🎯</div>
                        <div class="result-round">\${selectedRounds.REG || ''}</div>
                      </div>
                      <div class="result-card result-card-blue">
                        <div class="result-category">✨ MISC Round ✨</div>
                        <div class="result-round">\${selectedRounds.MISC || ''}</div>
                      </div>
                      <div class="result-card result-card-yellow">
                        <div class="result-category">💎 BIG Question 💎</div>
                        <div class="result-round">\${selectedRounds.BIG || ''}</div>
                      </div>
                    </div>
                  </div>
                \`;
              }
            }
          }
          
          renderContent();
        </script>
      </body>
      </html>
    `);
    win.document.close();
  };

  const updateAudienceView = () => {
    if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
      try {
        // Determine which category is currently being selected (first incomplete one)
        let currentCategory = 'REG';
        if (selectedOptions.REG.length >= 5) {
          currentCategory = selectedOptions.MISC.length >= 5 ? 'BIG' : 'MISC';
        }
        
        audienceWindowRef.current.postMessage({
          type: 'UPDATE_STATE',
          state: { 
            phase, 
            selectedOptions, 
            spinning, 
            selectedRounds, 
            wheelPositions, 
            selectedLocation,
            availableRounds, // Pass all available rounds for display
            currentCategory  // Which category is currently being selected
          }
        }, '*');
      } catch (error) {
        console.error('Error updating audience view:', error);
      }
    }
  };

  // Sync state changes to audience view
  useEffect(() => {
    if (audienceWindow) {
      updateAudienceView();
    }
  }, [phase, selectedOptions, spinning, selectedRounds, wheelPositions, selectedLocation, audienceWindow, availableRounds]);

  // MEMORY FIX: Clean up ALL resources on component unmount
  useEffect(() => {
    return () => {
      // Cancel all animation frames
      animationFrames.current.forEach(frame => {
        if (frame) cancelAnimationFrame(frame);
      });
      animationFrames.current = [];
      
      // Stop all spinning sounds
      [0, 1, 2].forEach(idx => stopSpinningSound(idx));
      
      // Clear window check interval
      if (windowCheckIntervalRef.current) {
        clearInterval(windowCheckIntervalRef.current);
        windowCheckIntervalRef.current = null;
      }
      
      // Close audience window
      if (audienceWindowRef.current && !audienceWindowRef.current.closed) {
        audienceWindowRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    if (!open) {
      [0, 1, 2].forEach(idx => stopSpinningSound(idx));
      // Cancel animation frames when closing
      animationFrames.current.forEach(frame => {
        if (frame) cancelAnimationFrame(frame);
      });
      closeAudienceView();
      resetAll();
    }
  }, [open]);

  const resetAll = () => {
    setPhase('location-selection');
    setSelectedLocation('');
    setSelectedLocationPath('');
    setIsLiveStreamShow(false);
    setSelectedOptions({ REG: [], MISC: [], BIG: [] });
    setSpinning([false, false, false]);
    spinningRef.current = [false, false, false];
    setSelectedRounds({});
    setSelectedRoundPaths({});
    setWheelPositions([0, 0, 0]);
    setError(null);
    setBuildStep(0);
    setSelectedHost('');
    setNumRounds(5);
    setExtraType('reg');
    setSelectedExtra('');
    setAutoSelectedMC(null);
    setAutoSelectedMYS(null);
  };

  useEffect(() => {
    if (phase !== 'spinning') return;
    const handleKeyPress = (e) => {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        stopCurrentWheel();
      }
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [phase, spinning]);

  const handleLocationSelect = async (location) => {
    setSelectedLocation(location);
    setPhase('loading');
    
    // Check if it's Live Stream Show
    const isLiveStream = location.includes('Live Stream') || location.includes('99_');
    setIsLiveStreamShow(isLiveStream);
    
    await fetchAvailableRounds(location);
  };

  const fetchAvailableRounds = async (location) => {
    try {
      setError(null);
      
      const locationsResponse = await axios.get(`${API}/trivia/locations`);
      const locationData = locationsResponse.data.find(loc => 
        loc.name.replace(/^\d+_/, '') === location || loc.name === location
      );
      
      if (!locationData) {
        setError(`Location "${location}" not found. Please try again.`);
        setAvailableRounds({ REG: [], MISC: [], BIG: [] });
        setPhase('input');
        return;
      }
      
      const locationPath = locationData.path;
      setSelectedLocationPath(locationPath);
      
      // Fetch all round types including MC and MYS for build phase
      const [regData, miscData, bigData, mcData, mysData, hostsData] = await Promise.all([
        axios.get(`${API}/trivia/round-files/reg?location=${encodeURIComponent(locationPath)}`),
        axios.get(`${API}/trivia/round-files/misc?location=${encodeURIComponent(locationPath)}`),
        axios.get(`${API}/trivia/round-files/big?location=${encodeURIComponent(locationPath)}`),
        axios.get(`${API}/trivia/round-files/mc?location=${encodeURIComponent(locationPath)}`),
        axios.get(`${API}/trivia/round-files/mys?location=${encodeURIComponent(locationPath)}`),
        axios.get(`${API}/trivia/hosts`)
      ]);
      
      const hasData = regData.data.length > 0 || miscData.data.length > 0 || bigData.data.length > 0;
      
      if (!hasData) {
        setError(`No rounds available for ${location}. Please select a different location.`);
        setAvailableRounds({ REG: [], MISC: [], BIG: [] });
      } else {
        setAvailableRounds({
          REG: regData.data.map(round => ({ name: round.name, path: round.path })),
          MISC: miscData.data.map(round => ({ name: round.name, path: round.path })),
          BIG: bigData.data.map(round => ({ name: round.name, path: round.path }))
        });
        setMcRounds(mcData.data);
        setMysRounds(mysData.data);
        setHosts(hostsData.data);
      }
      setPhase('input');
    } catch (err) {
      console.error('Error fetching rounds:', err);
      setError(`Failed to load rounds for ${location}. Please try again or select a different location.`);
      setAvailableRounds({ REG: [], MISC: [], BIG: [] });
      setPhase('input');
    }
  };

  const handleCheckboxChange = (category, roundName, checked) => {
    setSelectedOptions(prev => {
      const currentSelections = prev[category];
      if (checked) {
        if (currentSelections.length < 5) {
          return { ...prev, [category]: [...currentSelections, roundName] };
        }
        return prev;
      } else {
        return { ...prev, [category]: currentSelections.filter(name => name !== roundName) };
      }
    });
  };

  const canStartSpinning = () => {
    return Object.values(selectedOptions).every(selections => selections.length === 5);
  };

  const startSpinning = () => {
    if (!canStartSpinning()) return;
    setPhase('spinning');
    const newSpinning = [true, true, true];
    setSpinning(newSpinning);
    spinningRef.current = [true, true, true];
    const categories = ['REG', 'MISC', 'BIG'];
    categories.forEach((cat, idx) => {
      spinStartTime.current[idx] = Date.now();
      animateWheel(idx, selectedOptions[cat]);
      playSpinningSound(idx);
    });
    setTimeout(() => { if (spinningRef.current[0]) stopWheel(0); }, 10000);
    setTimeout(() => { if (spinningRef.current[1]) stopWheel(1); }, 11000);
    setTimeout(() => { if (spinningRef.current[2]) stopWheel(2); }, 12000);
  };

  const animateWheel = (wheelIndex, options) => {
    let position = 0;
    const itemHeight = 80;
    let speed = 13.5;
    const animate = () => {
      if (!spinningRef.current[wheelIndex]) return;
      
      const elapsed = Date.now() - spinStartTime.current[wheelIndex];
      const timeUntilStop = 10000 - elapsed;
      if (timeUntilStop < 2000 && timeUntilStop > 0) {
        speed = Math.max(2.7, speed * 0.98);
      }
      
      position += speed;
      if (position >= itemHeight * options.length) position = 0;
      setWheelPositions(prev => {
        const newPos = [...prev];
        newPos[wheelIndex] = position;
        return newPos;
      });
      animationFrames.current[wheelIndex] = requestAnimationFrame(animate);
    };
    animate();
  };

  const stopCurrentWheel = () => {
    const wheelToStop = spinningRef.current.findIndex(s => s);
    if (wheelToStop !== -1) stopWheel(wheelToStop);
  };

  const stopWheel = (wheelIndex) => {
    if (!spinningRef.current[wheelIndex]) return;
    const categories = ['REG', 'MISC', 'BIG'];
    const category = categories[wheelIndex];
    const options = selectedOptions[category];
    if (animationFrames.current[wheelIndex]) {
      cancelAnimationFrame(animationFrames.current[wheelIndex]);
    }
    
    stopSpinningSound(wheelIndex);
    playStopSound(wheelIndex);
    
    const randomIndex = Math.floor(Math.random() * options.length);
    const selectedOption = options[randomIndex];
    
    const roundData = availableRounds[category].find(r => r.name === selectedOption);
    
    const itemHeight = 80;
    const containerHeight = 320;
    const centerOffset = containerHeight / 2 - itemHeight / 2;
    const targetRepetition = 4;
    const totalItems = options.length;
    const finalPosition = (targetRepetition * totalItems * itemHeight) + (randomIndex * itemHeight) - centerOffset;
    
    setWheelPositions(prev => {
      const newPos = [...prev];
      newPos[wheelIndex] = finalPosition;
      return newPos;
    });
    
    setTimeout(() => {
      setSelectedRounds(prev => ({ ...prev, [category]: selectedOption }));
      setSelectedRoundPaths(prev => ({ ...prev, [category]: roundData?.path || '' }));
    }, 100);
    
    const newSpinning = [...spinning];
    newSpinning[wheelIndex] = false;
    setSpinning(newSpinning);
    spinningRef.current[wheelIndex] = false;
    if (newSpinning.every(s => !s)) {
      setTimeout(() => {
        setPhase('result');
        setTimeout(() => playJackpotSound(), 100);
      }, 600);
    }
  };

  // Handle "USE THESE ROUNDS" - different behavior for Live Stream vs other locations
  const handleUseRounds = () => {
    if (isLiveStreamShow) {
      // Live Stream Show - auto-build 3-round presentation
      onComplete(selectedRounds, selectedLocation, selectedRoundPaths);
      onClose();
    } else {
      // Other locations - go to build phase
      autoSelectMCAndMystery();
      setPhase('build');
      setBuildStep(1);
    }
  };

  // Auto-select random MC and Mystery rounds
  const autoSelectMCAndMystery = () => {
    if (mcRounds.length > 0) {
      const randomMC = mcRounds[Math.floor(Math.random() * mcRounds.length)];
      setAutoSelectedMC(randomMC);
    }
    if (mysRounds.length > 0) {
      const randomMYS = mysRounds[Math.floor(Math.random() * mysRounds.length)];
      setAutoSelectedMYS(randomMYS);
    }
  };

  // Get available extra rounds (REG or MISC not already selected)
  const getAvailableExtraRounds = () => {
    if (extraType === 'reg') {
      return availableRounds.REG.filter(r => r.path !== selectedRoundPaths.REG);
    } else {
      return availableRounds.MISC.filter(r => r.path !== selectedRoundPaths.MISC);
    }
  };

  // Build the full trivia presentation
  const handleBuildPresentation = async () => {
    try {
      setBuilding(true);
      
      // Build rounds array based on number of rounds
      // Order: MC → REG → (Extra if 6) → MISC → MYS → BIG
      let rounds = [];
      let roundTypes = [];
      let roundNames = [];
      if (numRounds === 5) {
        rounds = [
          autoSelectedMC?.path,
          selectedRoundPaths.REG,
          selectedRoundPaths.MISC,
          autoSelectedMYS?.path,
          selectedRoundPaths.BIG
        ];
        roundTypes = ['MC', 'REG', 'MISC', 'MYS', 'BIG'];
        roundNames = [
          autoSelectedMC?.name || 'MC Round',
          selectedRounds.REG,
          selectedRounds.MISC,
          autoSelectedMYS?.name || 'Mystery Round',
          selectedRounds.BIG
        ];
      } else {
        // 6 rounds: MC, REG, Extra (REG or MISC), MISC, MYS, BIG
        rounds = [
          autoSelectedMC?.path,
          selectedRoundPaths.REG,
          selectedExtra,
          selectedRoundPaths.MISC,
          autoSelectedMYS?.path,
          selectedRoundPaths.BIG
        ];
        // Determine extra round type and name
        const extraRoundType = extraType === 'reg' ? 'REG' : 'MISC';
        const extraRoundName = availableRounds[extraType.toUpperCase()]?.find(r => r.path === selectedExtra)?.name || 'Extra Round';
        roundTypes = ['MC', 'REG', extraRoundType, 'MISC', 'MYS', 'BIG'];
        roundNames = [
          autoSelectedMC?.name || 'MC Round',
          selectedRounds.REG,
          extraRoundName,
          selectedRounds.MISC,
          autoSelectedMYS?.name || 'Mystery Round',
          selectedRounds.BIG
        ];
      }
      
      const userName = localStorage.getItem('userName') || 'Unknown';
      const locationName = selectedLocation.replace(/^\d+_/, '');
      
      const triviaData = {
        userName: userName.toLowerCase(),
        host: selectedHost,
        location: selectedLocationPath,
        numRounds,
        rounds,
        roundTypes, // Include round types for proper metadata
        roundNames, // Include round names for admin tracking
        presentationName: `${locationName} - ${new Date().toLocaleDateString()}`
      };
      
      // Call the same API as the manual wizard
      await axios.post(`${API}/presentations/import-trivia`, triviaData);
      
      // Also save JSON to SharePoint for Story Generator matching
      try {
        const hostName = selectedHost.split('/').pop().replace('.pptx', '');
        await axios.post(`${API}/story-builds/save`, {
          host: hostName,
          location: locationName,
          locationFolder: selectedLocation, // Full folder name (e.g., "01_Monkey Pants")
          numRounds: numRounds,
          roundNames: roundNames,
          roundTypes: roundTypes,
          presentationName: triviaData.presentationName,
          createdBy: userName.toLowerCase()
        });
        console.log('[SlotMachine] Build saved to SharePoint for Story Generator');
      } catch (buildError) {
        console.warn('[SlotMachine] Failed to save build to SharePoint:', buildError);
        // Continue anyway - presentation was still created in MongoDB
      }
      
      // Show success and close
      onComplete(selectedRounds, selectedLocation, selectedRoundPaths, true); // true = built full presentation
      onClose();
      
    } catch (error) {
      console.error('Error building presentation:', error);
      setError('Failed to build presentation. Please try again.');
    } finally {
      setBuilding(false);
    }
  };

  const renderBuildStep = () => {
    switch (buildStep) {
      case 1:
        // Host Selection
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300 text-lg">Select Host</Label>
              <p className="text-sm text-gray-500 mb-3">Choose the host for this trivia show</p>
              <Select value={selectedHost} onValueChange={setSelectedHost}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white">
                  <SelectValue placeholder="Choose a host..." />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-[300px]">
                  {hosts.map((host) => (
                    <SelectItem key={host.id} value={host.path} className="text-white hover:bg-[#3a3a3a]">
                      {host.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        );
      
      case 2:
        // Number of Rounds
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300 text-lg">Number of Rounds</Label>
              <p className="text-sm text-gray-500 mb-3">Choose 5 or 6 rounds for your show</p>
              <Select value={numRounds.toString()} onValueChange={(val) => {
                setNumRounds(parseInt(val));
                setSelectedExtra('');
              }}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600">
                  <SelectItem value="5" className="text-white hover:bg-[#3a3a3a]">5 Rounds</SelectItem>
                  <SelectItem value="6" className="text-white hover:bg-[#3a3a3a]">6 Rounds</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-sm text-gray-500 mt-3">
                {numRounds === 5 
                  ? 'MC → REG → MISC → Mystery → BIG'
                  : 'MC → REG → Extra → MISC → Mystery → BIG'}
              </p>
            </div>
          </div>
        );
      
      case 3:
        // Extra Round Selection (only for 6 rounds)
        if (numRounds === 5) {
          // Skip to summary
          setBuildStep(4);
          return null;
        }
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300 text-lg">Select Extra Round</Label>
              <p className="text-sm text-gray-500 mb-3">Choose an additional REG or MISC round</p>
              
              <Label className="text-gray-400 text-sm mt-4">Round Type</Label>
              <Select value={extraType} onValueChange={(val) => {
                setExtraType(val);
                setSelectedExtra('');
              }}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600">
                  <SelectItem value="reg" className="text-white hover:bg-[#3a3a3a]">General (REG)</SelectItem>
                  <SelectItem value="misc" className="text-white hover:bg-[#3a3a3a]">Specific (MISC)</SelectItem>
                </SelectContent>
              </Select>

              <Label className="text-gray-400 text-sm mt-4">Select Round</Label>
              <Select value={selectedExtra} onValueChange={setSelectedExtra}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-1">
                  <SelectValue placeholder="Choose round..." />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-[250px]">
                  {getAvailableExtraRounds().length === 0 ? (
                    <div className="px-2 py-1 text-gray-400">No available rounds</div>
                  ) : (
                    getAvailableExtraRounds().map((round) => (
                      <SelectItem key={round.path} value={round.path} className="text-white hover:bg-[#3a3a3a]">
                        {round.name}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
        );
      
      case 4:
        // Summary
        return (
          <div className="space-y-4">
            <div className="bg-[#2a2a2a] border border-gray-600 rounded-lg p-4">
              <h4 className="text-[#FFC107] font-semibold mb-3 text-lg">Summary</h4>
              <div className="space-y-2 text-sm text-gray-300">
                <p><span className="text-gray-500">Host:</span> {hosts.find(h => h.path === selectedHost)?.name}</p>
                <p><span className="text-gray-500">Location:</span> {selectedLocation}</p>
                <p><span className="text-gray-500">Total Rounds:</span> {numRounds}</p>
                <div className="mt-3">
                  <span className="text-gray-500">Rounds:</span>
                  <ul className="ml-4 mt-2 space-y-1">
                    <li className="text-blue-400">1. {autoSelectedMC?.name} <span className="text-gray-500">(MC - Auto)</span></li>
                    <li className="text-green-400">2. {selectedRounds.REG} <span className="text-gray-500">(REG - Roulette)</span></li>
                    {numRounds === 6 && (
                      <li className="text-purple-400">3. {getAvailableExtraRounds().find(r => r.path === selectedExtra)?.name || availableRounds[extraType.toUpperCase()]?.find(r => r.path === selectedExtra)?.name} <span className="text-gray-500">({extraType.toUpperCase()} - Selected)</span></li>
                    )}
                    <li className="text-yellow-400">{numRounds === 5 ? '3' : '4'}. {selectedRounds.MISC} <span className="text-gray-500">(MISC - Roulette)</span></li>
                    <li className="text-orange-400">{numRounds === 5 ? '4' : '5'}. {autoSelectedMYS?.name} <span className="text-gray-500">(Mystery - Auto)</span></li>
                    <li className="text-red-400">{numRounds === 5 ? '5' : '6'}. {selectedRounds.BIG} <span className="text-gray-500">(BIG - Roulette)</span></li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        );
      
      default:
        return null;
    }
  };

  const canProceedBuildStep = () => {
    switch (buildStep) {
      case 1: return !!selectedHost;
      case 2: return true;
      case 3: return numRounds === 5 || !!selectedExtra;
      case 4: return true;
      default: return false;
    }
  };

  const handleBuildNext = () => {
    if (buildStep === 2 && numRounds === 5) {
      setBuildStep(4); // Skip extra round selection for 5 rounds
    } else if (buildStep < 4) {
      setBuildStep(buildStep + 1);
    }
  };

  const handleBuildBack = () => {
    if (buildStep === 4 && numRounds === 5) {
      setBuildStep(2); // Skip back over extra round selection for 5 rounds
    } else if (buildStep > 1) {
      setBuildStep(buildStep - 1);
    } else {
      // Go back to result phase
      setPhase('result');
      setBuildStep(0);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50" data-testid="slot-machine-randomizer">
      <div className="bg-gradient-to-br from-[#1a1a2e] to-[#16213e] border-2 border-[#FFC107] rounded-2xl max-w-6xl w-full mx-4 max-h-[90vh] overflow-y-auto shadow-2xl shadow-[#FFC107]/50">
        
        {/* Location Selection Phase */}
        {phase === 'location-selection' && (
          <div className="p-12">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-4xl font-bold text-[#FFC107]">🎰 Round Roulette 🎰</h2>
              <Button variant="ghost" onClick={onClose} className="text-gray-400 hover:text-white">✕</Button>
            </div>
            <div className="text-center mb-8">
              <p className="text-2xl text-gray-300 mb-2">Select Your Location</p>
              <p className="text-gray-400">Choose your trivia venue to see available rounds</p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 max-w-5xl mx-auto">
              {locations.map((location, idx) => (
                <Button
                  key={idx}
                  onClick={() => handleLocationSelect(location)}
                  className="h-24 bg-gradient-to-br from-gray-800 to-gray-900 hover:from-[#1657E8] hover:to-[#1F5EE9] border-2 border-gray-700 hover:border-[#1657E8] text-white font-bold text-lg rounded-xl shadow-lg hover:shadow-2xl hover:shadow-[#1657E8]/50 transform hover:scale-105 transition-all"
                  data-testid={`location-${location.toLowerCase().replace(/\s+/g, '-')}`}
                >
                  <div className="text-center">
                    <div className="text-2xl mb-1">📍</div>
                    <div className="text-sm leading-tight">{location}</div>
                  </div>
                </Button>
              ))}
            </div>
            <div className="mt-8 max-w-md mx-auto">
              <Label className="text-gray-300 text-sm mb-2 block">Or enter a custom location:</Label>
              <div className="flex gap-3">
                <Input
                  placeholder="Enter location name..."
                  className="bg-gray-800 border-gray-600 text-white flex-1"
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && e.target.value.trim()) {
                      handleLocationSelect(e.target.value.trim());
                    }
                  }}
                  data-testid="custom-location-input"
                />
                <Button
                  onClick={(e) => {
                    const input = e.target.closest('div').querySelector('input');
                    if (input && input.value.trim()) {
                      handleLocationSelect(input.value.trim());
                    }
                  }}
                  className="bg-[#FFC107] hover:bg-[#FFD54F] text-black font-bold"
                >
                  Go
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Loading Phase */}
        {phase === 'loading' && (
          <div className="p-16 text-center">
            <Loader2 className="w-16 h-16 text-[#FFC107] mx-auto mb-4 animate-spin" />
            <p className="text-xl text-gray-300 mb-2">Loading available rounds for</p>
            <p className="text-2xl font-bold text-[#FFC107]">{selectedLocation}</p>
          </div>
        )}

        {/* Input Phase - Checkbox Selection */}
        {phase === 'input' && (
          <div className="p-8">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-4">
                <Button
                  variant="outline"
                  onClick={() => {
                    setPhase('location-selection');
                    setSelectedLocation('');
                    setSelectedLocationPath('');
                    setSelectedOptions({ REG: [], MISC: [], BIG: [] });
                  }}
                  className="border-gray-600 text-gray-300 hover:bg-gray-700"
                >
                  ← Change Location
                </Button>
                <div>
                  <h2 className="text-3xl font-bold text-[#FFC107]">🎰 Round Roulette 🎰</h2>
                  <p className="text-sm text-gray-400">Location: <span className="text-[#FFC107] font-semibold">{selectedLocation}</span></p>
                </div>
              </div>
              <div className="flex items-center gap-2">
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
                <Button variant="ghost" onClick={onClose} className="text-gray-400 hover:text-white">✕</Button>
              </div>
            </div>
            
            {error && (
              <div className="bg-yellow-500/20 border border-yellow-500 rounded-lg p-3 mb-6">
                <p className="text-yellow-300 text-sm">{error}</p>
              </div>
            )}

            <p className="text-gray-400 mb-6">
              Select 5 rounds from each category. Then spin the wheels to randomly pick your trivia rounds!
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {['REG', 'MISC', 'BIG'].map((category) => {
                const colorClasses = {
                  REG: { border: 'border-[#1657E8]', bg: 'bg-[#1657E8]/20', text: 'text-[#1657E8]', checkbox: 'border-[#1657E8] data-[state=checked]:bg-[#1657E8]' },
                  MISC: { border: 'border-[#FFC107]', bg: 'bg-[#FFC107]/20', text: 'text-[#FFC107]', checkbox: 'border-[#FFC107] data-[state=checked]:bg-[#FFC107]' },
                  BIG: { border: 'border-green-500', bg: 'bg-green-500/20', text: 'text-green-400', checkbox: 'border-green-500 data-[state=checked]:bg-green-500' }
                };
                const colors = colorClasses[category];
                const categoryNames = { REG: 'REG - General', MISC: 'MISC - Specific', BIG: 'BIG - Final Question' };
                
                return (
                  <Card key={category} className={`${colors.bg} border-2 ${colors.border}`}>
                    <CardHeader>
                      <CardTitle className={`${colors.text} text-xl flex items-center justify-between`}>
                        <span>{categoryNames[category]}</span>
                        <span className="text-sm font-normal">({selectedOptions[category].length}/5)</span>
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-80 overflow-y-auto pr-4 space-y-3">
                        {availableRounds[category].length === 0 ? (
                          <p className="text-gray-500 text-center py-8">Loading rounds...</p>
                        ) : (
                          availableRounds[category].map((round, idx) => {
                            const isSelected = selectedOptions[category].includes(round.name);
                            const isDisabled = !isSelected && selectedOptions[category].length >= 5;
                            return (
                              <div key={idx} className="flex items-center space-x-3">
                                <Checkbox
                                  id={`${category.toLowerCase()}-${idx}`}
                                  checked={isSelected}
                                  disabled={isDisabled}
                                  onCheckedChange={(checked) => handleCheckboxChange(category, round.name, checked)}
                                  className={colors.checkbox}
                                />
                                <label
                                  htmlFor={`${category.toLowerCase()}-${idx}`}
                                  className={`text-sm font-medium cursor-pointer ${
                                    isDisabled ? 'text-gray-600' : 'text-gray-200'
                                  } ${isSelected ? 'text-white font-bold' : ''}`}
                                >
                                  {round.name}
                                </label>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            <div className="mt-8 flex justify-center">
              <Button
                onClick={startSpinning}
                disabled={!canStartSpinning()}
                className="bg-gradient-to-r from-[#FFC107] via-[#FFD54F] to-[#FFC107] hover:from-[#FFD54F] hover:via-[#FFC107] hover:to-[#FFD54F] text-black font-bold text-xl px-16 py-8 rounded-2xl shadow-2xl shadow-[#FFC107]/50 transform hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100 disabled:cursor-not-allowed animate-pulse"
                data-testid="spin-button"
              >
                <Play className="w-8 h-8 mr-3" />
                SPIN THE WHEELS!
              </Button>
            </div>
          </div>
        )}

        {/* Spinning Phase */}
        {phase === 'spinning' && (
          <div className="p-8 bg-gradient-to-br from-[#0a0a1a] via-[#1a1335] to-[#0a0a1a]">
            <div className="text-center mb-8">
              <div className="inline-block bg-gradient-to-r from-[#FFD700] via-[#FFC107] to-[#FFD700] text-black font-black text-4xl px-12 py-4 rounded-full shadow-2xl shadow-[#FFC107]/70 border-4 border-[#FFD700] animate-pulse">
                🎰 ROUND ROULETTE 🎰
              </div>
            </div>

            <div className="bg-gradient-to-b from-gray-900 via-gray-800 to-gray-900 rounded-3xl p-8 border-8 border-gray-700 shadow-2xl relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-2 bg-gradient-to-r from-red-500 via-yellow-500 via-green-500 via-blue-500 to-purple-500 animate-pulse"></div>
              <div className="absolute bottom-0 left-0 right-0 h-2 bg-gradient-to-r from-purple-500 via-blue-500 via-green-500 via-yellow-500 to-red-500 animate-pulse"></div>

              <div className="grid grid-cols-3 gap-8 mb-8">
                {['REG', 'MISC', 'BIG'].map((category, wheelIdx) => {
                  const colors = {
                    REG: { bg: 'from-blue-600 to-blue-400', label: 'from-blue-600 to-blue-400', text: 'text-blue-400' },
                    MISC: { bg: 'from-yellow-600 to-yellow-400', label: 'from-yellow-600 to-yellow-400 text-black', text: 'text-yellow-400' },
                    BIG: { bg: 'from-green-600 to-green-400', label: 'from-green-600 to-green-400', text: 'text-green-400' }
                  };
                  const c = colors[category];
                  
                  return (
                    <div key={category} className="relative">
                      <div className="absolute inset-0 bg-gradient-to-br from-gray-500 via-gray-400 to-gray-600 rounded-2xl -z-10 transform translate-x-2 translate-y-2"></div>
                      <div className="bg-gradient-to-br from-gray-700 via-gray-600 to-gray-800 p-4 rounded-2xl border-4 border-gray-500 shadow-2xl">
                        <div className={`text-center mb-3 text-2xl font-black uppercase tracking-wider px-4 py-2 rounded-lg bg-gradient-to-r ${c.label} text-white shadow-lg`}>
                          {category}
                        </div>
                        
                        <div className="relative h-80 bg-gradient-to-b from-black via-gray-900 to-black rounded-xl overflow-hidden border-4 border-gray-900 shadow-inner">
                          <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-black via-black/80 to-transparent z-10 pointer-events-none"></div>
                          <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-black via-black/80 to-transparent z-10 pointer-events-none"></div>
                          <div className="absolute top-1/2 left-0 right-0 -translate-y-1/2 z-20 pointer-events-none">
                            <div className={`border-t-4 border-[#FFD700] shadow-lg ${spinning[wheelIdx] ? 'shadow-[#FFD700]/90 animate-pulse' : 'shadow-[#FFD700]/70'}`}></div>
                            <div className="border-t-2 border-yellow-300 -mt-1"></div>
                          </div>
                          
                          <div
                            className="absolute inset-0"
                            style={{
                              transform: spinning[wheelIdx] ? `translateY(-${wheelPositions[wheelIdx]}px)` : 'none',
                              transition: spinning[wheelIdx] ? 'none' : 'transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)'
                            }}
                          >
                            {[...selectedOptions[category], ...selectedOptions[category], ...selectedOptions[category], ...selectedOptions[category], ...selectedOptions[category], ...selectedOptions[category]].map((option, idx) => (
                              <div key={idx} className="h-20 flex items-center justify-center px-4 border-b border-gray-700/50 bg-gradient-to-r from-gray-800/30 to-gray-900/30">
                                <span className={`text-xl font-bold text-center transition-all duration-100 ${spinning[wheelIdx] ? 'scale-95 opacity-90' : 'scale-100 opacity-100'} ${c.text} drop-shadow-lg`}>
                                  {option}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="mt-3 text-center">
                          {spinning[wheelIdx] ? (
                            <div className="bg-gradient-to-r from-green-600 to-green-400 text-white font-bold px-4 py-2 rounded-full animate-pulse shadow-lg shadow-green-500/50">
                              ⚡ SPINNING ⚡
                            </div>
                          ) : selectedRounds[category] ? (
                            <div className="bg-gradient-to-r from-[#FFD700] to-[#FFC107] text-black font-bold px-4 py-2 rounded-full shadow-lg">
                              ✓ LOCKED
                            </div>
                          ) : null}
                        </div>
                        
                        {selectedRounds[category] && (
                          <div className="mt-4">
                            <div className={`bg-gradient-to-br ${c.bg} border-4 border-white rounded-xl p-4 shadow-2xl transform scale-105`}>
                              <div className="text-white text-xs font-bold mb-1 uppercase tracking-wider">🏆 WINNER 🏆</div>
                              <div className="text-white text-lg font-black text-center leading-tight">
                                {selectedRounds[category]}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="text-center py-6">
                {spinning.some(s => s) ? (
                  <div className="space-y-3">
                    <div className="inline-block bg-gradient-to-r from-red-600 via-yellow-500 to-green-500 text-white font-black text-2xl px-12 py-4 rounded-full animate-pulse shadow-2xl">
                      🎮 PRESS SPACE OR ENTER TO STOP 🎮
                    </div>
                    <p className="text-gray-400 text-sm">(Auto-stops after 10 seconds)</p>
                  </div>
                ) : (
                  <div className="inline-block bg-gradient-to-r from-green-600 to-green-400 text-white font-black text-2xl px-12 py-4 rounded-full shadow-2xl shadow-green-500/50">
                    🎉 ALL WHEELS STOPPED! 🎉
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Result Phase */}
        {phase === 'result' && (
          <div className="p-8 bg-gradient-to-br from-[#1a1a2e] via-[#2d1b69] to-[#1a1a2e]">
            <div className="text-center mb-12">
              <div className="inline-block animate-bounce mb-4">
                <Trophy className="w-32 h-32 text-[#FFD700] mx-auto drop-shadow-2xl filter drop-shadow-[0_0_30px_rgba(255,215,0,0.8)]" />
              </div>
              <div className="inline-block bg-gradient-to-r from-[#FFD700] via-[#FFC107] to-[#FFD700] text-black font-black text-5xl px-16 py-6 rounded-full shadow-2xl shadow-[#FFD700]/70 border-8 border-yellow-400 mb-4 animate-pulse">
                🎊 JACKPOT! 🎊
              </div>
              <p className="text-3xl font-bold bg-gradient-to-r from-yellow-400 via-red-400 to-pink-400 bg-clip-text text-transparent mt-4 animate-pulse">
                Tonight&apos;s Winning Rounds!
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-12 max-w-6xl mx-auto">
              {[
                { category: 'REG', title: 'REG ROUND', colors: 'from-red-700 via-red-600 to-red-800 border-red-400 shadow-red-500/50' },
                { category: 'MISC', title: 'MISC ROUND', colors: 'from-blue-700 via-blue-600 to-blue-800 border-blue-400 shadow-blue-500/50' },
                { category: 'BIG', title: 'BIG QUESTION', colors: 'from-yellow-700 via-yellow-600 to-yellow-800 border-yellow-400 shadow-yellow-500/50' }
              ].map(({ category, title, colors }) => (
                <div key={category} className="relative group" data-testid={`result-${category.toLowerCase()}`}>
                  <div className={`absolute inset-0 bg-gradient-to-br ${colors} rounded-3xl transform rotate-3 group-hover:rotate-6 transition-transform`}></div>
                  <Card className={`relative bg-gradient-to-br ${colors} border-4 shadow-2xl transform -rotate-1 hover:rotate-0 transition-all`}>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-white text-2xl font-black flex items-center justify-center">
                        <Sparkles className="w-6 h-6 mr-2 animate-pulse" />
                        <span className="drop-shadow-lg">{title}</span>
                        <Sparkles className="w-6 h-6 ml-2 animate-pulse" />
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <div className="bg-white/20 backdrop-blur rounded-2xl p-6 border-2 border-white/30">
                        <p className="text-white text-center text-3xl font-black drop-shadow-lg">
                          {selectedRounds[category]}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              ))}
            </div>

            <div className="flex flex-col items-center gap-4">
              <div className="flex justify-center gap-6">
                <Button
                  onClick={() => {
                    setPhase('input');
                    setSelectedRounds({});
                    setSelectedRoundPaths({});
                    setSelectedOptions({ REG: [], MISC: [], BIG: [] });
                  }}
                  variant="outline"
                  className="border-4 border-gray-500 text-white hover:bg-gray-700 hover:border-gray-400 font-bold text-lg px-8 py-6 rounded-xl"
                  data-testid="spin-again-button"
                >
                  🎰 Spin Again
                </Button>
                <Button
                  onClick={handleUseRounds}
                  className="bg-gradient-to-r from-[#FFD700] via-[#FFC107] to-[#FFD700] hover:from-[#FFC107] hover:via-[#FFD700] hover:to-[#FFC107] text-black font-black text-lg px-12 py-6 rounded-xl shadow-2xl shadow-[#FFD700]/70 border-4 border-yellow-400 transform hover:scale-105 transition-all"
                  data-testid="use-rounds-button"
                >
                  ✨ USE THESE ROUNDS ✨
                </Button>
              </div>
              
              <div className="text-center">
                <p className="text-gray-400 text-sm mb-3">
                  {isLiveStreamShow 
                    ? 'This will build a Live Stream Show presentation with 3 rounds'
                    : 'This will let you build a full presentation with these rounds'}
                </p>
                <Button
                  onClick={onClose}
                  variant="ghost"
                  className="text-gray-400 hover:text-white hover:bg-gray-800 font-semibold text-base px-8 py-4 rounded-lg border-2 border-gray-700 hover:border-gray-500"
                  data-testid="exit-button"
                >
                  Exit & Build Manually
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Build Phase - For Non-Live Stream Locations */}
        {phase === 'build' && (
          <div className="p-8">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-3xl font-bold text-[#FFC107]">🎯 Build Trivia Presentation</h2>
                <p className="text-sm text-gray-400">Step {buildStep} of 4: {
                  buildStep === 1 ? 'Select Host' :
                  buildStep === 2 ? 'Number of Rounds' :
                  buildStep === 3 ? 'Extra Round' :
                  'Review & Build'
                }</p>
              </div>
              <Button variant="ghost" onClick={onClose} className="text-gray-400 hover:text-white">✕</Button>
            </div>

            {/* Auto-selected rounds info */}
            <div className="bg-[#1a1a2e]/50 border border-gray-700 rounded-lg p-4 mb-6">
              <h4 className="text-sm font-semibold text-gray-400 mb-2">Rounds from Roulette:</h4>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div className="text-green-400">REG: {selectedRounds.REG}</div>
                <div className="text-yellow-400">MISC: {selectedRounds.MISC}</div>
                <div className="text-red-400">BIG: {selectedRounds.BIG}</div>
              </div>
              <h4 className="text-sm font-semibold text-gray-400 mt-3 mb-2">Auto-selected:</h4>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-blue-400">MC: {autoSelectedMC?.name || 'Loading...'}</div>
                <div className="text-orange-400">Mystery: {autoSelectedMYS?.name || 'Loading...'}</div>
              </div>
            </div>

            {error && (
              <div className="bg-red-500/20 border border-red-500 rounded-lg p-3 mb-6">
                <p className="text-red-300 text-sm">{error}</p>
              </div>
            )}

            <div className="py-6">
              {renderBuildStep()}
            </div>

            <div className="flex justify-between gap-3 mt-6">
              <Button
                onClick={handleBuildBack}
                variant="outline"
                className="border-gray-600 text-gray-300 hover:bg-[#2a2a2a]"
                disabled={building}
              >
                <ChevronLeft className="w-4 h-4 mr-2" />
                Back
              </Button>
              
              {buildStep < 4 ? (
                <Button
                  onClick={handleBuildNext}
                  disabled={!canProceedBuildStep()}
                  className="bg-[#1657E8] hover:bg-[#1F5EE9] text-white"
                >
                  Next
                  <ChevronRight className="w-4 h-4 ml-2" />
                </Button>
              ) : (
                <Button
                  onClick={handleBuildPresentation}
                  disabled={building || !selectedHost}
                  className="bg-[#FFC107] hover:bg-[#FFD54F] text-black font-semibold"
                >
                  {building ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Building...
                    </>
                  ) : (
                    '✨ Build Presentation'
                  )}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SlotMachineRandomizer;
