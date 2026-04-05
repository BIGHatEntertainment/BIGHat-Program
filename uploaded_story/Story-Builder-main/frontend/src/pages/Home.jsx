import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { FileText, Plus, Play, Trash2, Loader2, Wand2, Settings, Dices, Video } from 'lucide-react';
import { toast } from '../hooks/use-toast';
import { presentationAPI } from '../services/api';
import TriviaBuilderWizard from '../components/TriviaBuilderWizard_v2';
import SlotMachineRandomizer from '../components/SlotMachineRandomizer';
import StoryGenerator from '../components/StoryGenerator';

const Home = () => {
  const navigate = useNavigate();
  const [userName, setUserName] = useState('');
  const [showNameDialog, setShowNameDialog] = useState(false);
  const [showTriviaWizard, setShowTriviaWizard] = useState(false);
  const [showSlotMachine, setShowSlotMachine] = useState(false);
  const [showStoryGenerator, setShowStoryGenerator] = useState(false);
  const [presentations, setPresentations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [locations, setLocations] = useState([]);

  useEffect(() => {
    const savedName = localStorage.getItem('userName');
    if (!savedName) {
      setShowNameDialog(true);
    } else {
      setUserName(savedName);
      loadPresentations(savedName);
      loadLocations();
    }
  }, []);

  const loadLocations = async () => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/trivia/locations`);
      const data = await response.json();
      // Extract location names and remove numeric prefixes (e.g., "01_", "02_")
      const locationNames = data.map(loc => {
        // Remove prefix pattern like "01_", "02_", etc.
        return loc.name.replace(/^\d+_/, '');
      });
      setLocations(locationNames);
    } catch (error) {
      console.error('Error loading locations:', error);
      // Fallback to default locations if API fails
      setLocations([
        'Bristol\'s Mesa', 'Denver', 'Colorado Springs', 'Boulder', 
        'Fort Collins', 'Aurora', 'Lakewood', 'Thornton'
      ]);
    }
  };

  const loadPresentations = async (name) => {
    try {
      setLoading(true);
      // Normalize username to lowercase for consistency
      const data = await presentationAPI.getAllCombined(name.toLowerCase());
      // Filter to only show trivia presentations (with yellow badge)
      // Hide trivia-imported duplicates that don't have the badge
      const filteredData = data.filter(pres => pres.type === 'trivia');
      setPresentations(filteredData);
    } catch (error) {
      console.error('Error loading presentations:', error);
      toast({ title: 'Error', description: 'Failed to load presentations', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleNameSubmit = () => {
    if (userName.trim()) {
      localStorage.setItem('userName', userName);
      setShowNameDialog(false);
      toast({ title: 'Welcome!', description: `Hello, ${userName}!` });
      loadPresentations(userName);
      loadLocations(); // Load locations for Round Roulette
    }
  };

  const handleCreatePresentation = async () => {
    try {
      const newPresentation = await presentationAPI.create({
        name: `New Presentation - ${new Date().toLocaleDateString()}`,
        createdBy: userName
      });
      localStorage.setItem('currentPresentationId', newPresentation.id);
      navigate('/editor');
    } catch (error) {
      console.error('Error creating presentation:', error);
      toast({ title: 'Error', description: 'Failed to create presentation', variant: 'destructive' });
    }
  };

  const handleBuildTrivia = async (triviaData) => {
    try {
      setLoading(true);
      // Ensure username is lowercase for consistency
      const normalizedData = { ...triviaData, userName: triviaData.userName.toLowerCase() };
      const presentation = await presentationAPI.importTrivia(normalizedData);
      toast({ title: 'Success!', description: 'Trivia presentation built successfully!' });
      await loadPresentations(userName.toLowerCase());
    } catch (error) {
      console.error('Error building trivia:', error);
      toast({ title: 'Error', description: 'Failed to build trivia presentation', variant: 'destructive' });
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const handleSlotMachineComplete = async (selectedRounds, selectedLocation, roundPaths, builtFullPresentation = false) => {
    // If the SlotMachineRandomizer already built a full presentation (non-Live Stream locations)
    // just reload the presentations list and show success
    if (builtFullPresentation) {
      toast({ 
        title: '🎉 Trivia Presentation Built!', 
        description: `Created presentation for ${selectedLocation}`,
        duration: 6000
      });
      await loadPresentations(userName.toLowerCase());
      return;
    }
    
    // For Live Stream Show - build the 3-round presentation
    try {
      setLoading(true);
      
      // Get the full location path for "99_Live Stream Show"
      const locationsResponse = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/trivia/locations`);
      const locationsData = await locationsResponse.json();
      const liveStreamLocation = locationsData.find(loc => loc.name.includes('99_Live Stream Show'));
      
      if (!liveStreamLocation) {
        throw new Error('Live Stream Show location not found in SharePoint');
      }
      
      // Build trivia presentation for "99_Live Stream Show" with the selected rounds
      // API expects: { userName, host, location, numRounds, rounds: [file paths] }
      // For Live Stream Show, we pass empty host to skip host slides
      const triviaData = {
        userName: userName.toLowerCase(),
        host: '', // Empty host - skip host slides for Live Stream Show
        location: liveStreamLocation.path,
        numRounds: 3, // Only 3 rounds for Live Stream
        rounds: [
          roundPaths.REG,
          roundPaths.MISC,
          roundPaths.BIG
        ],
        roundTypes: ['REG', 'MISC', 'BIG'], // Explicit round types for metadata
        roundNames: [selectedRounds.REG, selectedRounds.MISC, selectedRounds.BIG], // Round display names
        presentationName: `Live Stream - ${new Date().toLocaleDateString()}`
      };
      
      await handleBuildTrivia(triviaData);
      
      toast({ 
        title: '🎉 Live Stream Trivia Created!', 
        description: `REG: ${selectedRounds.REG}, MISC: ${selectedRounds.MISC}, BIG: ${selectedRounds.BIG}`,
        duration: 6000
      });
    } catch (error) {
      console.error('Error creating Live Stream trivia:', error);
      toast({ 
        title: 'Error', 
        description: error.message || 'Failed to create Live Stream trivia presentation', 
        variant: 'destructive' 
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDeletePresentation = async (id, type, e) => {
    e.stopPropagation();
    if (window.confirm('Are you sure you want to delete this presentation?')) {
      try {
        setLoading(true);
        
        // Delete from backend
        if (type === 'trivia' || type === 'trivia-imported') {
          await presentationAPI.deleteTrivia(id);
        } else {
          await presentationAPI.delete(id);
        }
        
        // IMMEDIATELY update local state to remove the presentation from UI
        setPresentations(prevPresentations => 
          prevPresentations.filter(p => p.id !== id)
        );
        
        // Show success toast
        toast({ 
          title: 'Deleted', 
          description: 'Presentation deleted successfully',
          variant: 'default'
        });
        
        // Reload presentations list from server to ensure sync
        // Use setTimeout to avoid race condition with state update
        setTimeout(() => {
          loadPresentations(userName.toLowerCase());
        }, 500);
        
      } catch (error) {
        console.error('Error deleting presentation:', error);
        
        // Check if it's a 404 (already deleted)
        if (error.response?.status === 404) {
          // Remove from UI since it's already gone from backend
          setPresentations(prevPresentations => 
            prevPresentations.filter(p => p.id !== id)
          );
          
          toast({ 
            title: 'Already deleted', 
            description: 'This presentation has already been removed', 
            variant: 'default' 
          });
        } else {
          toast({ 
            title: 'Error', 
            description: error.response?.data?.detail || 'Failed to delete presentation', 
            variant: 'destructive' 
          });
        }
      } finally {
        setLoading(false);
      }
    }
  };

  const handleOpenPresentation = async (id, type) => {
    if (type === 'trivia' || type === 'trivia-imported') {
      // Open trivia presentation directly - slides load on-demand
      try {
        setLoading(true);
        toast({ 
          title: 'Opening...', 
          description: 'Loading presentation editor...', 
          variant: 'default' 
        });
        
        // Just open directly - editor will load slides on-demand
        localStorage.setItem('currentPresentationId', id);
        navigate('/editor');
      } catch (error) {
        console.error('Error opening trivia:', error);
        toast({ 
          title: 'Error', 
          description: 'Failed to open trivia presentation', 
          variant: 'destructive' 
        });
      } finally {
        setLoading(false);
      }
    } else {
      localStorage.setItem('currentPresentationId', id);
      navigate('/editor');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0a0a1a] via-[#1a1a2e] to-[#16213e] flex flex-col relative overflow-hidden">
      {/* Animated Background Elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 w-96 h-96 bg-[#1657E8] rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse"></div>
        <div className="absolute top-40 right-20 w-96 h-96 bg-[#FFC107] rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse" style={{animationDelay: '2s'}}></div>
        <div className="absolute bottom-20 left-1/3 w-96 h-96 bg-[#1F5EE9] rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse" style={{animationDelay: '4s'}}></div>
      </div>
      
      {/* Header */}
      <header className="bg-gradient-to-r from-[#191919] via-[#1a1a2e] to-[#191919] border-b border-[#FFC107]/20 px-8 py-6 relative z-10">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold text-[#FFC107]">BIG Hat Presenter</h1>
            <p className="text-gray-400 mt-1">Create amazing presentations with style</p>
          </div>
          {userName && (
            <div className="flex items-center gap-4">
              <Button 
                variant="outline" 
                onClick={() => navigate('/admin')}
                className="gap-2 bg-gray-800/50 border-gray-600 text-white hover:bg-gray-700"
              >
                <Settings className="h-4 w-4" />
                Admin
              </Button>
              <div className="text-white">
                <span className="text-gray-400">Welcome, </span>
                <span className="font-semibold text-[#FFC107]">{userName}</span>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 px-8 py-12 relative z-10">
        <div className="max-w-7xl mx-auto">
          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            <Card 
              className="bg-gradient-to-br from-[#1657E8] to-[#1F5EE9] border-2 border-[#1657E8]/30 text-white hover:shadow-2xl hover:shadow-[#1657E8]/50 hover:scale-105 transition-all cursor-pointer" 
              onClick={() => setShowSlotMachine(true)}
              data-testid="round-roulette-card"
            >
              <CardHeader>
                <CardTitle className="text-2xl flex items-center gap-3">
                  <Dices className="w-8 h-8" />
                  Round Roulette
                </CardTitle>
                <CardDescription className="text-gray-200">
                  Spin the slot machine to randomly select your trivia rounds
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button className="bg-white text-[#1657E8] hover:bg-gray-100 font-semibold">
                  Get Started
                </Button>
              </CardContent>
            </Card>

            <Card className="bg-gradient-to-br from-[#FFC107] to-[#FFD54F] border-2 border-[#FFC107]/30 text-black hover:shadow-2xl hover:shadow-[#FFC107]/50 hover:scale-105 transition-all cursor-pointer" onClick={() => setShowTriviaWizard(true)}>
              <CardHeader>
                <CardTitle className="text-2xl flex items-center gap-3">
                  <Wand2 className="w-8 h-8" />
                  Build Trivia Presentation
                </CardTitle>
                <CardDescription className="text-gray-800">
                  Build a custom trivia presentation from SharePoint
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button className="bg-[#191919] text-white hover:bg-black font-semibold">
                  Start Wizard
                </Button>
              </CardContent>
            </Card>

            <Card 
              className="bg-gradient-to-br from-[#E91E63] to-[#9C27B0] border-2 border-[#E91E63]/30 text-white hover:shadow-2xl hover:shadow-[#E91E63]/50 hover:scale-105 transition-all cursor-pointer" 
              onClick={() => setShowStoryGenerator(true)}
              data-testid="story-generator-card"
            >
              <CardHeader>
                <CardTitle className="text-2xl flex items-center gap-3">
                  <Video className="w-8 h-8" />
                  Story Generator
                </CardTitle>
                <CardDescription className="text-gray-200">
                  Create Instagram story videos from your presentations
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button className="bg-white text-[#E91E63] hover:bg-gray-100 font-semibold">
                  Generate Story
                </Button>
              </CardContent>
            </Card>
          </div>

          {/* Recent Presentations */}
          <div>
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <span className="w-1 h-8 bg-gradient-to-b from-[#FFC107] to-[#1657E8] rounded-full"></span>
              Recent Presentations
            </h2>
            {loading ? (
              <div className="text-center py-16">
                <Loader2 className="w-16 h-16 text-[#FFC107] mx-auto mb-4 animate-spin" />
                <p className="text-gray-400 text-lg">Loading presentations...</p>
              </div>
            ) : presentations.length === 0 ? (
              <div className="text-center py-16">
                <FileText className="w-16 h-16 text-gray-600 mx-auto mb-4" />
                <p className="text-gray-400 text-lg">No presentations yet</p>
                <p className="text-gray-500 text-sm">Create your first presentation to get started</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {presentations.map((pres) => (
                  <Card key={pres.id} className={`bg-gradient-to-br from-[#1a1a2e] to-[#16213e] border-[#1657E8]/30 hover:border-[#FFC107] hover:shadow-lg hover:shadow-[#FFC107]/20 transition-all ${pres.type === 'trivia' ? 'ring-2 ring-[#FFC107]/30' : ''}`}>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-white">{pres.name}</CardTitle>
                        {pres.type === 'trivia' && (
                          <span className="px-2 py-1 bg-[#FFC107] text-black text-xs font-semibold rounded">
                            TRIVIA
                          </span>
                        )}
                      </div>
                      <CardDescription className="text-gray-400">
                        {pres.type === 'trivia' ? (
                          <>
                            {pres.totalSlides || 0} slides • {pres.location || 'Unknown location'}
                          </>
                        ) : (
                          <>{pres.slides?.length || 0} slides</>
                        )}
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="flex gap-2">
                        <Button
                          onClick={() => handleOpenPresentation(pres.id, pres.type)}
                          className="flex-1 bg-[#1657E8] hover:bg-[#1F5EE9]"
                          disabled={loading}
                        >
                          <Play className="w-4 h-4 mr-2" />
                          {pres.type === 'trivia' ? 'Import to Presenter' : 'Open'}
                        </Button>
                        <Button
                          onClick={(e) => handleDeletePresentation(pres.id, pres.type, e)}
                          variant="outline"
                          className="text-red-500 border-red-500 hover:bg-red-500 hover:text-white"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Name Dialog */}
      <Dialog open={showNameDialog} onOpenChange={setShowNameDialog}>
        <DialogContent className="bg-gradient-to-br from-[#1a1a2e] to-[#16213e] border-[#FFC107]/30 text-white">
          <DialogHeader>
            <DialogTitle className="text-[#FFC107] text-2xl">Welcome to BIG Hat Presenter!</DialogTitle>
            <DialogDescription className="text-gray-400">
              Please enter your name to get started
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="name" className="text-gray-300">Your Name</Label>
            <Input
              id="name"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleNameSubmit()}
              className="mt-2 bg-[#2a2a2a] border-gray-600 text-white"
              placeholder="Enter your name..."
            />
          </div>
          <DialogFooter>
            <Button
              onClick={handleNameSubmit}
              disabled={!userName.trim()}
              className="bg-[#FFC107] hover:bg-[#FFD54F] text-black font-semibold"
            >
              Continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Trivia Builder Wizard */}
      <TriviaBuilderWizard
        open={showTriviaWizard}
        onOpenChange={setShowTriviaWizard}
        onComplete={handleBuildTrivia}
        userName={userName}
      />

      {/* Slot Machine Randomizer */}
      <SlotMachineRandomizer
        open={showSlotMachine}
        onClose={() => setShowSlotMachine(false)}
        onComplete={handleSlotMachineComplete}
        locations={locations}
      />

      {/* Story Generator */}
      <StoryGenerator
        open={showStoryGenerator}
        onClose={() => setShowStoryGenerator(false)}
        userName={userName}
      />
    </div>
  );
};

export default Home;