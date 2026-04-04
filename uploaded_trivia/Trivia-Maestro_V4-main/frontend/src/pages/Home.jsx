import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { FileText, Play, Trash2, Loader2, Wand2, Settings, Dices, Users, LogOut, Video } from 'lucide-react';
import { toast } from '../hooks/use-toast';
import { presentationAPI, storyBuildsAPI } from '../services/api';
import TriviaBuilderWizard from '../components/TriviaBuilderWizard_v2';
import SlotMachineRandomizer from '../components/SlotMachineRandomizer';

// List of authorized admin users (case-insensitive)
const ADMIN_USERS = ['nick', 'caelie', 'tommy'];

const Home = () => {
  const navigate = useNavigate();
  const [userName, setUserName] = useState('');
  const [showNameDialog, setShowNameDialog] = useState(false);
  const [showTriviaWizard, setShowTriviaWizard] = useState(false);
  const [showSlotMachine, setShowSlotMachine] = useState(false);
  const [presentations, setPresentations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [locations, setLocations] = useState([]);
  const [viewAll, setViewAll] = useState(false);
  const [showUserSwitcher, setShowUserSwitcher] = useState(false);
  const [newUserName, setNewUserName] = useState('');

  // Check if current user is an admin
  const isAdmin = ADMIN_USERS.includes(userName.toLowerCase());

  useEffect(() => {
    const savedName = localStorage.getItem('userName');
    const savedViewAll = localStorage.getItem('viewAll') === 'true';
    setViewAll(savedViewAll);
    if (!savedName) {
      setShowNameDialog(true);
    } else {
      setUserName(savedName);
      loadPresentations(savedName, savedViewAll);
      loadLocations();
    }
  }, []);

  const loadLocations = async () => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/trivia/locations`);
      const data = await response.json();
      const locationNames = data.map(loc => loc.name.replace(/^\d+_/, ''));
      setLocations(locationNames);
    } catch (error) {
      console.error('Error loading locations:', error);
      setLocations([
        'Bristol\'s Mesa', 'Denver', 'Colorado Springs', 'Boulder', 
        'Fort Collins', 'Aurora', 'Lakewood', 'Thornton'
      ]);
    }
  };

  const loadPresentations = async (name, showAll = false) => {
    try {
      setLoading(true);
      const data = await presentationAPI.getAllCombined(name.toLowerCase(), showAll);
      const filteredData = data.filter(pres => pres.type === 'trivia');
      setPresentations(filteredData);
    } catch (error) {
      console.error('Error loading presentations:', error);
      toast({ title: 'Error', description: 'Failed to load presentations', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleViewAllToggle = (checked) => {
    setViewAll(checked);
    localStorage.setItem('viewAll', checked.toString());
    loadPresentations(userName, checked);
  };

  const handleSwitchUser = () => {
    if (newUserName.trim()) {
      localStorage.setItem('userName', newUserName.trim());
      setUserName(newUserName.trim());
      setShowUserSwitcher(false);
      setNewUserName('');
      toast({ title: 'User Switched', description: `Now logged in as ${newUserName.trim()}` });
      loadPresentations(newUserName.trim(), viewAll);
      loadLocations();
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('userName');
    localStorage.removeItem('viewAll');
    setUserName('');
    setPresentations([]);
    setViewAll(false);
    setShowNameDialog(true);
    toast({ title: 'Logged Out', description: 'You have been logged out' });
  };

  const handleNameSubmit = () => {
    if (userName.trim()) {
      localStorage.setItem('userName', userName);
      setShowNameDialog(false);
      toast({ title: 'Welcome!', description: `Hello, ${userName}!` });
      loadPresentations(userName, viewAll);
      loadLocations();
    }
  };

  const handleBuildTrivia = async (triviaData) => {
    try {
      setLoading(true);
      const normalizedData = { ...triviaData, userName: triviaData.userName.toLowerCase() };
      const presentation = await presentationAPI.importTrivia(normalizedData);
      
      try {
        const buildResult = await storyBuildsAPI.saveBuild({
          host: triviaData.hostName || 'Unknown',
          location: triviaData.locationName || 'Unknown',
          locationFolder: triviaData.locationFolder || 'Unknown',
          numRounds: triviaData.numRounds,
          roundNames: triviaData.roundNames || [],
          roundTypes: triviaData.roundTypes || [],
          presentationName: triviaData.presentationName,
          createdBy: triviaData.userName.toLowerCase()
        });
        console.log('[Home] Build saved to SharePoint:', buildResult.path);
        toast({ 
          title: 'Success!', 
          description: `Presentation built and saved to ${triviaData.locationName || 'SharePoint'}!` 
        });
      } catch (buildError) {
        console.warn('[Home] Failed to save build to SharePoint:', buildError);
        toast({ 
          title: 'Presentation Built!', 
          description: 'Note: Could not save to Story Generator. Presentation is still available.'
        });
      }
      
      await loadPresentations(userName.toLowerCase(), viewAll);
    } catch (error) {
      console.error('Error building trivia:', error);
      toast({ title: 'Error', description: 'Failed to build trivia presentation', variant: 'destructive' });
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const handleSlotMachineComplete = async (selectedRounds, selectedLocation, roundPaths, builtFullPresentation = false) => {
    if (builtFullPresentation) {
      toast({ 
        title: '🎉 Trivia Presentation Built!', 
        description: `Created presentation for ${selectedLocation}`,
        duration: 6000
      });
      await loadPresentations(userName.toLowerCase(), viewAll);
      return;
    }
    
    try {
      setLoading(true);
      const locationsResponse = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/trivia/locations`);
      const locationsData = await locationsResponse.json();
      const liveStreamLocation = locationsData.find(loc => loc.name.includes('99_Live Stream Show'));
      
      if (!liveStreamLocation) {
        throw new Error('Live Stream Show location not found in SharePoint');
      }
      
      const triviaData = {
        userName: userName.toLowerCase(),
        host: '',
        hostName: 'Live Stream',
        location: liveStreamLocation.path,
        numRounds: 3,
        rounds: [roundPaths.REG, roundPaths.MISC, roundPaths.BIG],
        roundTypes: ['REG', 'MISC', 'BIG'],
        roundNames: [selectedRounds.REG, selectedRounds.MISC, selectedRounds.BIG],
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
        if (type === 'trivia' || type === 'trivia-imported') {
          await presentationAPI.deleteTrivia(id);
        } else {
          await presentationAPI.delete(id);
        }
        setPresentations(prevPresentations => prevPresentations.filter(p => p.id !== id));
        toast({ title: 'Deleted', description: 'Presentation deleted successfully', variant: 'default' });
        setTimeout(() => loadPresentations(userName.toLowerCase(), viewAll), 500);
      } catch (error) {
        console.error('Error deleting presentation:', error);
        if (error.response?.status === 404) {
          setPresentations(prevPresentations => prevPresentations.filter(p => p.id !== id));
          toast({ title: 'Already deleted', description: 'This presentation has already been removed', variant: 'default' });
        } else {
          toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to delete presentation', variant: 'destructive' });
        }
      } finally {
        setLoading(false);
      }
    }
  };

  const handleOpenPresentation = async (id, type) => {
    if (type === 'trivia' || type === 'trivia-imported') {
      try {
        setLoading(true);
        toast({ title: 'Opening...', description: 'Loading presentation editor...', variant: 'default' });
        localStorage.setItem('currentPresentationId', id);
        navigate('/editor');
      } catch (error) {
        console.error('Error opening trivia:', error);
        toast({ title: 'Error', description: 'Failed to open trivia presentation', variant: 'destructive' });
      } finally {
        setLoading(false);
      }
    } else {
      localStorage.setItem('currentPresentationId', id);
      navigate('/editor');
    }
  };

  return (
    <div className="min-h-screen bg-[#000e2a] flex flex-col relative overflow-hidden">
      {/* Animated Background Elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 w-[500px] h-[500px] bg-[#141b50] rounded-full filter blur-[120px] opacity-40 animate-pulse-glow"></div>
        <div className="absolute top-40 right-20 w-[400px] h-[400px] bg-[#fbdd68] rounded-full filter blur-[150px] opacity-10 animate-pulse-glow" style={{animationDelay: '1.5s'}}></div>
        <div className="absolute bottom-20 left-1/3 w-[600px] h-[600px] bg-[#151c51] rounded-full filter blur-[140px] opacity-30 animate-pulse-glow" style={{animationDelay: '3s'}}></div>
      </div>
      
      {/* Header */}
      <header className="bg-[#000e2a]/80 backdrop-blur-xl border-b border-[#fbdd68]/20 px-8 py-5 relative z-10">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold text-[#fbdd68] tracking-tight">BIG Hat Presenter</h1>
            <p className="text-[#8892b0] mt-1 text-sm">Create amazing presentations with style</p>
          </div>
          {userName && (
            <div className="flex items-center gap-4">
              {/* View All Toggle */}
              <div className="flex items-center gap-2 bg-[#141b50]/60 backdrop-blur-sm px-4 py-2 rounded-lg border border-[#fbdd68]/10">
                <Label htmlFor="view-all" className="text-[#8892b0] text-sm">View All</Label>
                <Switch 
                  id="view-all"
                  checked={viewAll}
                  onCheckedChange={handleViewAllToggle}
                  className="data-[state=checked]:bg-[#22c55e]"
                />
              </div>
              
              {/* Admin Button */}
              {isAdmin && (
                <Button 
                  variant="outline" 
                  onClick={() => navigate('/admin')}
                  className="gap-2 bg-[#141b50]/60 border-[#fbdd68]/30 text-[#fbdd68] hover:bg-[#fbdd68] hover:text-[#000e2a] transition-all"
                >
                  <Settings className="h-4 w-4" />
                  Admin
                </Button>
              )}
              
              {/* User Menu */}
              <div className="flex items-center gap-3 bg-[#141b50]/60 backdrop-blur-sm px-4 py-2 rounded-lg border border-[#fbdd68]/10">
                <div>
                  <span className="text-[#8892b0] text-sm">Welcome, </span>
                  <span className="font-semibold text-[#fbdd68]">{userName}</span>
                </div>
                <div className="flex items-center gap-1 border-l border-[#fbdd68]/20 pl-3">
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => setShowUserSwitcher(true)}
                    className="text-[#8892b0] hover:text-[#fbdd68] hover:bg-[#fbdd68]/10 h-8 w-8 p-0"
                    title="Switch User"
                  >
                    <Users className="h-4 w-4" />
                  </Button>
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={handleLogout}
                    className="text-[#8892b0] hover:text-red-400 hover:bg-red-400/10 h-8 w-8 p-0"
                    title="Logout"
                  >
                    <LogOut className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 px-8 py-10 relative z-10">
        <div className="max-w-7xl mx-auto">
          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
            {/* Round Roulette Card */}
            <Card 
              className="group bg-gradient-to-br from-[#141b50] to-[#0a1940] border border-[#fbdd68]/20 hover:border-[#fbdd68]/50 text-white hover:shadow-[0_0_40px_rgba(251,221,104,0.15)] transition-all duration-300 cursor-pointer overflow-hidden"
              onClick={() => setShowSlotMachine(true)}
              data-testid="round-roulette-card"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-[#fbdd68]/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
              <CardHeader className="relative">
                <CardTitle className="text-2xl flex items-center gap-3 text-white">
                  <div className="p-2 bg-[#fbdd68]/10 rounded-lg group-hover:bg-[#fbdd68]/20 transition-colors">
                    <Dices className="w-7 h-7 text-[#fbdd68]" />
                  </div>
                  Round Roulette
                </CardTitle>
                <CardDescription className="text-[#8892b0]">
                  Spin the slot machine to randomly select your trivia rounds
                </CardDescription>
              </CardHeader>
              <CardContent className="relative">
                <Button 
                  className="bg-[#fbdd68] text-[#000e2a] hover:bg-[#fee16b] font-semibold shadow-lg shadow-[#fbdd68]/20"
                  onClick={(e) => { e.stopPropagation(); setShowSlotMachine(true); }}
                >
                  Get Started
                </Button>
              </CardContent>
            </Card>

            {/* Build Trivia Card */}
            <Card 
              className="group bg-gradient-to-br from-[#fbdd68] to-[#f5d050] border border-[#fbdd68]/50 text-[#000e2a] hover:shadow-[0_0_50px_rgba(251,221,104,0.3)] transition-all duration-300 cursor-pointer overflow-hidden"
              onClick={() => setShowTriviaWizard(true)}
              data-testid="build-trivia-card"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-white/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
              <CardHeader className="relative">
                <CardTitle className="text-2xl flex items-center gap-3">
                  <div className="p-2 bg-[#000e2a]/10 rounded-lg group-hover:bg-[#000e2a]/20 transition-colors">
                    <Wand2 className="w-7 h-7 text-[#000e2a]" />
                  </div>
                  Build Trivia
                </CardTitle>
                <CardDescription className="text-[#000e2a]/70">
                  Build a custom trivia presentation from SharePoint
                </CardDescription>
              </CardHeader>
              <CardContent className="relative">
                <Button 
                  className="bg-[#000e2a] text-[#fbdd68] hover:bg-[#001030] font-semibold"
                  onClick={(e) => { e.stopPropagation(); setShowTriviaWizard(true); }}
                >
                  Start Wizard
                </Button>
              </CardContent>
            </Card>

            {/* Story Generator Card - Instagram gradient to stand out */}
            <Card 
              className="group bg-gradient-to-br from-[#833AB4] via-[#E1306C] to-[#F77737] border border-white/20 hover:border-white/40 text-white hover:shadow-[0_0_50px_rgba(225,48,108,0.4)] transition-all duration-300 cursor-pointer overflow-hidden"
              onClick={() => navigate('/story-generator')}
              data-testid="story-generator-card"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-white/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
              <CardHeader className="relative">
                <CardTitle className="text-2xl flex items-center gap-3 text-white">
                  <div className="p-2 bg-white/20 rounded-lg group-hover:bg-white/30 transition-colors">
                    <Video className="w-7 h-7 text-white" />
                  </div>
                  Story Generator
                </CardTitle>
                <CardDescription className="text-white/80">
                  Create Instagram Stories from your trivia presentations
                </CardDescription>
              </CardHeader>
              <CardContent className="relative">
                <Button 
                  className="bg-white text-[#E1306C] hover:bg-white/90 font-semibold shadow-lg"
                  onClick={(e) => { e.stopPropagation(); navigate('/story-generator'); }}
                >
                  Create Story
                </Button>
              </CardContent>
            </Card>
          </div>

          {/* Recent Presentations */}
          <div>
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
              <span className="w-1 h-8 bg-[#fbdd68] rounded-full"></span>
              Recent Presentations
            </h2>
            {loading ? (
              <div className="text-center py-16">
                <Loader2 className="w-12 h-12 text-[#fbdd68] mx-auto mb-4 animate-spin" />
                <p className="text-[#8892b0]">Loading presentations...</p>
              </div>
            ) : presentations.length === 0 ? (
              <div className="text-center py-16 bg-[#141b50]/30 rounded-2xl border border-[#fbdd68]/10">
                <FileText className="w-12 h-12 text-[#8892b0] mx-auto mb-4" />
                <p className="text-[#8892b0] text-lg">No presentations yet</p>
                <p className="text-[#8892b0]/60 text-sm mt-1">Create your first presentation to get started</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                {presentations.map((pres) => (
                  <Card 
                    key={pres.id} 
                    className="group bg-[#141b50]/50 backdrop-blur-sm border border-[#fbdd68]/10 hover:border-[#fbdd68]/40 transition-all duration-300 hover:shadow-[0_0_30px_rgba(251,221,104,0.1)]"
                  >
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="text-white text-lg truncate">{pres.name}</CardTitle>
                        {pres.type === 'trivia' && (
                          <span className="px-2 py-1 bg-[#fbdd68] text-[#000e2a] text-xs font-bold rounded shrink-0">
                            TRIVIA
                          </span>
                        )}
                      </div>
                      <CardDescription className="text-[#8892b0] text-sm">
                        {pres.type === 'trivia' ? (
                          <>{pres.totalSlides || 0} slides • {pres.location || 'Unknown location'}</>
                        ) : (
                          <>{pres.slides?.length || 0} slides</>
                        )}
                        {viewAll && pres.createdBy && (
                          <span className="block mt-1 text-xs">
                            Created by: <span className="text-[#fbdd68]">{pres.createdBy}</span>
                          </span>
                        )}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <div className="flex gap-2">
                        <Button
                          onClick={() => handleOpenPresentation(pres.id, pres.type)}
                          className="flex-1 bg-[#fbdd68] text-[#000e2a] hover:bg-[#fee16b] font-medium"
                          disabled={loading}
                        >
                          <Play className="w-4 h-4 mr-2" />
                          {pres.type === 'trivia' ? 'Import' : 'Open'}
                        </Button>
                        <Button
                          onClick={(e) => handleDeletePresentation(pres.id, pres.type, e)}
                          variant="outline"
                          className="border-red-500/50 text-red-400 hover:bg-red-500 hover:text-white hover:border-red-500"
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
        <DialogContent className="bg-[#0a1940] border border-[#fbdd68]/30 text-white">
          <DialogHeader>
            <DialogTitle className="text-[#fbdd68] text-2xl">Welcome to BIG Hat Presenter!</DialogTitle>
            <DialogDescription className="text-[#8892b0]">
              Please enter your name to get started
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="name" className="text-[#8892b0]">Your Name</Label>
            <Input
              id="name"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleNameSubmit()}
              className="mt-2 bg-[#141b50] border-[#fbdd68]/20 text-white placeholder:text-[#8892b0]/50 focus:border-[#fbdd68]/50"
              placeholder="Enter your name..."
            />
          </div>
          <DialogFooter>
            <Button
              onClick={handleNameSubmit}
              disabled={!userName.trim()}
              className="bg-[#fbdd68] hover:bg-[#fee16b] text-[#000e2a] font-semibold"
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

      {/* User Switcher Dialog */}
      <Dialog open={showUserSwitcher} onOpenChange={setShowUserSwitcher}>
        <DialogContent className="bg-[#0a1940] border border-[#fbdd68]/30 text-white">
          <DialogHeader>
            <DialogTitle className="text-[#fbdd68] text-2xl flex items-center gap-2">
              <Users className="w-6 h-6" />
              Switch User
            </DialogTitle>
            <DialogDescription className="text-[#8892b0]">
              Enter a different username to switch accounts.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <div>
              <Label className="text-[#8892b0]">Current User</Label>
              <div className="mt-1 text-[#fbdd68] font-semibold">{userName}</div>
            </div>
            <div>
              <Label htmlFor="new-name" className="text-[#8892b0]">Switch to</Label>
              <Input
                id="new-name"
                value={newUserName}
                onChange={(e) => setNewUserName(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSwitchUser()}
                className="mt-2 bg-[#141b50] border-[#fbdd68]/20 text-white placeholder:text-[#8892b0]/50 focus:border-[#fbdd68]/50"
                placeholder="Enter new username..."
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => { setShowUserSwitcher(false); setNewUserName(''); }}
              className="border-[#fbdd68]/30 text-[#8892b0] hover:bg-[#141b50] hover:text-white"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSwitchUser}
              disabled={!newUserName.trim()}
              className="bg-[#fbdd68] hover:bg-[#fee16b] text-[#000e2a] font-semibold"
            >
              Switch User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Home;
