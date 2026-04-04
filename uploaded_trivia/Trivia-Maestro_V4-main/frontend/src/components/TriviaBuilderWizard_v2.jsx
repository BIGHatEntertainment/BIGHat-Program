import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Input } from './ui/input';
import { Loader2, ChevronRight, ChevronLeft } from 'lucide-react';
import { triviaAPI } from '../services/api';
import { toast } from '../hooks/use-toast';

const TriviaBuilderWizard = ({ open, onOpenChange, onComplete, userName }) => {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  
  // Fuzzy search helper function
  const fuzzyMatch = (text, search) => {
    if (!search) return true;
    
    const searchLower = search.toLowerCase();
    const textLower = text.toLowerCase();
    
    // Exact match or substring match gets highest priority
    if (textLower.includes(searchLower)) return true;
    
    // Fuzzy match - check if all characters in search appear in order in text
    let searchIndex = 0;
    for (let i = 0; i < textLower.length && searchIndex < searchLower.length; i++) {
      if (textLower[i] === searchLower[searchIndex]) {
        searchIndex++;
      }
    }
    return searchIndex === searchLower.length;
  };
  
  // Filter rounds based on search
  const filterRounds = (rounds, searchTerm) => {
    if (!searchTerm || searchTerm.trim() === '') return rounds;
    return rounds.filter(round => fuzzyMatch(round.name, searchTerm));
  };
  
  // Options from SharePoint
  const [hosts, setHosts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [mcRounds, setMcRounds] = useState([]);
  const [regRounds, setRegRounds] = useState([]);
  const [miscRounds, setMiscRounds] = useState([]);
  const [mysRounds, setMysRounds] = useState([]);
  const [bigRounds, setBigRounds] = useState([]);
  
  // User selections
  const [selectedHost, setSelectedHost] = useState('');
  const [selectedLocation, setSelectedLocation] = useState('');
  const [numRounds, setNumRounds] = useState(5);
  const [selectedMC, setSelectedMC] = useState('');
  const [selectedREG1, setSelectedREG1] = useState('');
  const [selectedMISC1, setSelectedMISC1] = useState('');
  const [selectedExtra, setSelectedExtra] = useState(''); // For 6 rounds only
  const [extraType, setExtraType] = useState('reg'); // 'reg' or 'misc'
  const [selectedMYS, setSelectedMYS] = useState('');
  const [selectedBIG, setSelectedBIG] = useState('');
  const [presentationName, setPresentationName] = useState('');
  
  // Search filters for MISC, MYS, and BIG rounds
  const [miscSearch, setMiscSearch] = useState('');
  const [mysSearch, setMysSearch] = useState('');
  const [bigSearch, setBigSearch] = useState('');

  useEffect(() => {
    if (open) {
      loadOptions();
      resetForm();
    }
  }, [open]);

  const resetForm = () => {
    setStep(1);
    setSelectedHost('');
    setSelectedLocation('');
    setNumRounds(5);
    setSelectedMC('');
    setSelectedREG1('');
    setSelectedMISC1('');
    setSelectedExtra('');
    setExtraType('reg');
    setSelectedMYS('');
    setSelectedBIG('');
    setPresentationName(''); // Will be set when location is selected
    
    // Reset search filters
    setMiscSearch('');
    setMysSearch('');
    setBigSearch('');
  };

  const loadOptions = async () => {
    try {
      setLoading(true);
      const [hostsData, locationsData] = await Promise.all([
        triviaAPI.getHosts(),
        triviaAPI.getLocations()
      ]);
      setHosts(hostsData);
      // Filter out "99_Live Stream Show" from main wizard
      const filteredLocations = locationsData.filter(loc => 
        !loc.name.includes('99_Live Stream Show') && !loc.name.includes('Live Stream Show')
      );
      setLocations(filteredLocations);
    } catch (error) {
      console.error('Error loading options:', error);
      toast({ 
        title: 'Error', 
        description: 'Failed to load trivia options from SharePoint', 
        variant: 'destructive' 
      });
    } finally {
      setLoading(false);
    }
  };

  // Load round files after location is selected
  const loadRoundFiles = async (location) => {
    try {
      setLoading(true);
      const [mcData, regData, miscData, mysData, bigData] = await Promise.all([
        triviaAPI.getRoundFilesByType('mc', location),
        triviaAPI.getRoundFilesByType('reg', location),
        triviaAPI.getRoundFilesByType('misc', location),
        triviaAPI.getRoundFilesByType('mys', location),
        triviaAPI.getRoundFilesByType('big', location)
      ]);
      setMcRounds(mcData);
      setRegRounds(regData);
      setMiscRounds(miscData);
      setMysRounds(mysData);
      setBigRounds(bigData);
    } catch (error) {
      console.error('Error loading round files:', error);
      toast({ 
        title: 'Error', 
        description: 'Failed to load round files', 
        variant: 'destructive' 
      });
    } finally {
      setLoading(false);
    }
  };

  const handleNext = () => {
    if (step === 1 && !selectedHost) {
      toast({ title: 'Required', description: 'Please select a host', variant: 'destructive' });
      return;
    }
    if (step === 2 && !selectedLocation) {
      toast({ title: 'Required', description: 'Please select a location', variant: 'destructive' });
      return;
    }
    if (step === 3 && mcRounds.length === 0) {
      toast({ title: 'Loading...', description: 'Please wait for round files to load', variant: 'destructive' });
      return;
    }
    // Validate round selections based on current step
    if (step === 4 && !selectedMC) {
      toast({ title: 'Required', description: 'Please select a Multiple Choice round', variant: 'destructive' });
      return;
    }
    if (step === 5 && !selectedREG1) {
      toast({ title: 'Required', description: 'Please select a General round', variant: 'destructive' });
      return;
    }
    if (step === 6 && numRounds === 6 && !selectedExtra) {
      toast({ title: 'Required', description: 'Please select an additional round', variant: 'destructive' });
      return;
    }
    if (step === 7 && !selectedMISC1) {
      toast({ title: 'Required', description: 'Please select a Specific themed round', variant: 'destructive' });
      return;
    }
    if (step === 8 && !selectedMYS) {
      toast({ title: 'Required', description: 'Please select a Mystery round', variant: 'destructive' });
      return;
    }
    if (step === 9 && !selectedBIG) {
      toast({ title: 'Required', description: 'Please select a BIG Question round', variant: 'destructive' });
      return;
    }
    
    // Skip step 6 if 5 rounds
    if (step === 5 && numRounds === 5) {
      setStep(7);
    } else {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    // Skip step 6 if going back and 5 rounds
    if (step === 7 && numRounds === 5) {
      setStep(5);
    } else {
      setStep(step - 1);
    }
  };

  const handleBuild = async () => {
    try {
      setBuilding(true);
      
      // Build rounds array based on number of rounds
      let rounds = [];
      let roundTypes = [];
      let roundNames = [];
      if (numRounds === 5) {
        rounds = [selectedMC, selectedREG1, selectedMISC1, selectedMYS, selectedBIG];
        roundTypes = ['MC', 'REG', 'MISC', 'MYS', 'BIG'];
        roundNames = [
          mcRounds.find(r => r.path === selectedMC)?.name || mcRounds.find(r => r.path === selectedMC)?.displayName || 'MC Round',
          regRounds.find(r => r.path === selectedREG1)?.name || regRounds.find(r => r.path === selectedREG1)?.displayName || 'REG Round',
          miscRounds.find(r => r.path === selectedMISC1)?.name || miscRounds.find(r => r.path === selectedMISC1)?.displayName || 'MISC Round',
          mysRounds.find(r => r.path === selectedMYS)?.name || mysRounds.find(r => r.path === selectedMYS)?.displayName || 'Mystery Round',
          bigRounds.find(r => r.path === selectedBIG)?.name || bigRounds.find(r => r.path === selectedBIG)?.displayName || 'BIG Round'
        ];
      } else {
        // 6 rounds: MC, REG, Extra (REG or MISC), MISC, MYS, BIG
        rounds = [selectedMC, selectedREG1, selectedExtra, selectedMISC1, selectedMYS, selectedBIG];
        // Determine extra round type based on which pool it came from
        const extraRoundType = regRounds.some(r => r.path === selectedExtra) ? 'REG' : 'MISC';
        const extraRoundName = regRounds.find(r => r.path === selectedExtra)?.name 
          || regRounds.find(r => r.path === selectedExtra)?.displayName 
          || miscRounds.find(r => r.path === selectedExtra)?.name 
          || miscRounds.find(r => r.path === selectedExtra)?.displayName 
          || 'Extra Round';
        roundTypes = ['MC', 'REG', extraRoundType, 'MISC', 'MYS', 'BIG'];
        roundNames = [
          mcRounds.find(r => r.path === selectedMC)?.name || mcRounds.find(r => r.path === selectedMC)?.displayName || 'MC Round',
          regRounds.find(r => r.path === selectedREG1)?.name || regRounds.find(r => r.path === selectedREG1)?.displayName || 'REG Round',
          extraRoundName,
          miscRounds.find(r => r.path === selectedMISC1)?.name || miscRounds.find(r => r.path === selectedMISC1)?.displayName || 'MISC Round',
          mysRounds.find(r => r.path === selectedMYS)?.name || mysRounds.find(r => r.path === selectedMYS)?.displayName || 'Mystery Round',
          bigRounds.find(r => r.path === selectedBIG)?.name || bigRounds.find(r => r.path === selectedBIG)?.displayName || 'BIG Round'
        ];
      }
      
      const triviaData = {
        userName,
        host: selectedHost,
        location: selectedLocation,
        numRounds,
        rounds,
        roundTypes, // Include round types for proper metadata
        roundNames, // Include round names for admin tracking
        presentationName,
        // Additional data for Story Generator save
        hostName: hosts.find(h => h.path === selectedHost)?.name || 'Unknown',
        locationFolder: locations.find(l => l.path === selectedLocation)?.name || 'Unknown',
        locationName: (locations.find(l => l.path === selectedLocation)?.name || 'Unknown').replace(/^\d+_/, '')
      };

      await onComplete(triviaData);
      onOpenChange(false);
      
    } catch (error) {
      console.error('Error building presentation:', error);
      toast({ 
        title: 'Error', 
        description: 'Failed to build presentation. Please try again.', 
        variant: 'destructive' 
      });
    } finally {
      setBuilding(false);
    }
  };

  // Get available REG rounds excluding already selected ones
  const getAvailableREG = () => {
    const excluded = [selectedREG1, selectedExtra].filter(Boolean);
    return regRounds.filter(r => !excluded.includes(r.path));
  };

  // Get available MISC rounds excluding already selected ones
  const getAvailableMISC = () => {
    const excluded = [selectedMISC1, selectedExtra].filter(Boolean);
    return miscRounds.filter(r => !excluded.includes(r.path));
  };

  const renderStep = () => {
    if (loading) {
      return (
        <div className="text-center py-12">
          <Loader2 className="w-12 h-12 text-[#FFC107] mx-auto mb-4 animate-spin" />
          <p className="text-gray-400">Loading options from SharePoint...</p>
        </div>
      );
    }

    switch (step) {
      case 1:
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Select Host</Label>
              <Select value={selectedHost} onValueChange={setSelectedHost}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2">
                  <SelectValue placeholder="Choose a host..." />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600">
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
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Select Location</Label>
              <Select value={selectedLocation} onValueChange={(val) => {
                setSelectedLocation(val);
                loadRoundFiles(val); // Load round files for this location
                
                // Update presentation name with location name
                const location = locations.find(l => l.path === val);
                if (location) {
                  const locationName = location.name;
                  setPresentationName(`${locationName} - ${new Date().toLocaleDateString()}`);
                }
              }}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2">
                  <SelectValue placeholder="Choose a location..." />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600">
                  {locations.map((location) => (
                    <SelectItem key={location.id} value={location.path} className="text-white hover:bg-[#3a3a3a]">
                      {location.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedLocation && loading && (
                <div className="flex items-center gap-2 text-[#FFC107] mt-3">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <p className="text-sm">Loading available rounds for this location...</p>
                </div>
              )}
              {selectedLocation && !loading && mcRounds.length > 0 && (
                <p className="text-sm text-green-400 mt-2">
                  ✓ {mcRounds.length + regRounds.length + miscRounds.length + mysRounds.length + bigRounds.length} rounds loaded
                </p>
              )}
            </div>
          </div>
        );

      case 3:
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Number of Rounds</Label>
              <Select value={numRounds.toString()} onValueChange={(val) => setNumRounds(parseInt(val))}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600">
                  <SelectItem value="5" className="text-white hover:bg-[#3a3a3a]">5 Rounds</SelectItem>
                  <SelectItem value="6" className="text-white hover:bg-[#3a3a3a]">6 Rounds</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-sm text-gray-500 mt-2">
                {numRounds === 5 
                  ? 'MC → General → Specific → Mystery → BIG'
                  : 'MC → General → Extra → Specific → Mystery → BIG'}
              </p>
            </div>
          </div>
        );

      case 4:
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Round 1: Multiple Choice</Label>
              <p className="text-sm text-gray-500 mb-2">This round is always Multiple Choice</p>
              {loading ? (
                <div className="flex items-center gap-2 text-[#FFC107] mt-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <p className="text-sm">Loading rounds...</p>
                </div>
              ) : (
                <Select value={selectedMC} onValueChange={setSelectedMC}>
                  <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2">
                    <SelectValue placeholder="Choose MC round..." />
                  </SelectTrigger>
                  <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-[300px]">
                    {mcRounds.length === 0 ? (
                      <div className="px-2 py-1 text-gray-400">
                        No available rounds (all may have been used recently at this location)
                      </div>
                    ) : (
                      mcRounds.map((round) => (
                        <SelectItem key={round.id} value={round.path} className="text-white hover:bg-[#3a3a3a]">
                          {round.displayName}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>
        );

      case 5:
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Round 2: General Themed</Label>
              <p className="text-sm text-gray-500 mb-2">Select a general themed round (REG)</p>
              <Select value={selectedREG1} onValueChange={setSelectedREG1}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2">
                  <SelectValue placeholder="Choose general round...">
                    {selectedREG1 ? regRounds.find(r => r.path === selectedREG1)?.displayName : 'Choose general round...'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-[300px]">
                  {regRounds.length === 0 ? (
                    <div className="px-2 py-1 text-gray-400">No available rounds</div>
                  ) : (
                    getAvailableREG().map((round) => (
                      <SelectItem key={round.id} value={round.path} className="text-white hover:bg-[#3a3a3a]">
                        {round.displayName}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
        );

      case 6:
        // Only shown for 6 rounds
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Round 3: Additional Round</Label>
              <p className="text-sm text-gray-500 mb-2">Choose another General or Specific round</p>
              
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
                  <SelectValue placeholder="Choose round...">
                    {selectedExtra 
                      ? (extraType === 'reg' 
                          ? regRounds.find(r => r.path === selectedExtra)?.displayName 
                          : miscRounds.find(r => r.path === selectedExtra)?.displayName)
                      : 'Choose round...'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-[300px]">
                  {extraType === 'reg' 
                    ? getAvailableREG().length === 0 ? (
                        <div className="px-2 py-1 text-gray-400">No available rounds</div>
                      ) : (
                        getAvailableREG().map((round) => (
                          <SelectItem key={round.id} value={round.path} className="text-white hover:bg-[#3a3a3a]">
                            {round.displayName}
                          </SelectItem>
                        ))
                      )
                    : getAvailableMISC().length === 0 ? (
                        <div className="px-2 py-1 text-gray-400">No available rounds</div>
                      ) : (
                        getAvailableMISC().map((round) => (
                          <SelectItem key={round.id} value={round.path} className="text-white hover:bg-[#3a3a3a]">
                            {round.displayName}
                          </SelectItem>
                        ))
                      )
                  }
                </SelectContent>
              </Select>
            </div>
          </div>
        );

      case 7:
        const filteredMISC = filterRounds(getAvailableMISC(), miscSearch);
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Round {numRounds === 5 ? '3' : '4'}: Specific Themed</Label>
              <p className="text-sm text-gray-500 mb-2">Select a specific themed round (MISC)</p>
              
              {/* Search Input */}
              <Input
                type="text"
                placeholder="🔍 Search MISC rounds..."
                value={miscSearch}
                onChange={(e) => setMiscSearch(e.target.value)}
                className="bg-[#2a2a2a] border-gray-600 text-white mb-2 mt-2"
              />
              <p className="text-xs text-gray-500 mb-2">
                {miscSearch && `Found ${filteredMISC.length} matches`}
              </p>
              
              <Select value={selectedMISC1} onValueChange={setSelectedMISC1}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white">
                  <SelectValue placeholder="Choose specific round...">
                    {selectedMISC1 ? miscRounds.find(r => r.path === selectedMISC1)?.displayName : 'Choose specific round...'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-[300px]">
                  {filteredMISC.length === 0 ? (
                    <div className="px-2 py-1 text-gray-400">
                      {miscSearch ? 'No matches found' : 'No available rounds'}
                    </div>
                  ) : (
                    filteredMISC.map((round) => (
                      <SelectItem key={round.id} value={round.path} className="text-white hover:bg-[#3a3a3a]">
                        {round.displayName}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
        );

      case 8:
        const filteredMYS = filterRounds(mysRounds, mysSearch);
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Round {numRounds === 5 ? '4' : '5'}: Mystery</Label>
              <p className="text-sm text-gray-500 mb-2">Select a mystery round (MYS)</p>
              
              {/* Search Input */}
              <Input
                type="text"
                placeholder="🔍 Search Mystery rounds..."
                value={mysSearch}
                onChange={(e) => setMysSearch(e.target.value)}
                className="bg-[#2a2a2a] border-gray-600 text-white mb-2 mt-2"
              />
              <p className="text-xs text-gray-500 mb-2">
                {mysSearch && `Found ${filteredMYS.length} matches`}
              </p>
              
              <Select value={selectedMYS} onValueChange={setSelectedMYS}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white">
                  <SelectValue placeholder="Choose mystery round...">
                    {selectedMYS ? mysRounds.find(r => r.path === selectedMYS)?.displayName : 'Choose mystery round...'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-[300px]">
                  {filteredMYS.length === 0 ? (
                    <div className="px-2 py-1 text-gray-400">
                      {mysSearch ? 'No matches found' : 'No available rounds'}
                    </div>
                  ) : (
                    filteredMYS.map((round) => (
                      <SelectItem key={round.id} value={round.path} className="text-white hover:bg-[#3a3a3a]">
                        {round.displayName}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
        );

      case 9:
        const filteredBIG = filterRounds(bigRounds, bigSearch);
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Round {numRounds === 5 ? '5' : '6'}: BIG Question</Label>
              <p className="text-sm text-gray-500 mb-2">Select the final BIG question round</p>
              
              {/* Search Input */}
              <Input
                type="text"
                placeholder="🔍 Search BIG rounds..."
                value={bigSearch}
                onChange={(e) => setBigSearch(e.target.value)}
                className="bg-[#2a2a2a] border-gray-600 text-white mb-2 mt-2"
              />
              <p className="text-xs text-gray-500 mb-2">
                {bigSearch && `Found ${filteredBIG.length} matches`}
              </p>
              
              <Select value={selectedBIG} onValueChange={setSelectedBIG}>
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white">
                  <SelectValue placeholder="Choose BIG round...">
                    {selectedBIG ? bigRounds.find(r => r.path === selectedBIG)?.displayName : 'Choose BIG round...'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-[300px]">
                  {filteredBIG.length === 0 ? (
                    <div className="px-2 py-1 text-gray-400">
                      {bigSearch ? 'No matches found' : 'No available rounds'}
                    </div>
                  ) : (
                    filteredBIG.map((round) => (
                      <SelectItem key={round.id} value={round.path} className="text-white hover:bg-[#3a3a3a]">
                        {round.displayName}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
        );

      case 10:
        return (
          <div className="space-y-4">
            <div>
              <Label className="text-gray-300">Presentation Name</Label>
              <Input
                value={presentationName}
                onChange={(e) => setPresentationName(e.target.value)}
                className="bg-[#2a2a2a] border-gray-600 text-white mt-2"
                placeholder="Enter presentation name..."
              />
            </div>
            <div className="bg-[#2a2a2a] border border-gray-600 rounded-lg p-4 mt-6">
              <h4 className="text-[#FFC107] font-semibold mb-3">Summary</h4>
              <div className="space-y-2 text-sm text-gray-300">
                <p><span className="text-gray-500">Host:</span> {hosts.find(h => h.path === selectedHost)?.name}</p>
                <p><span className="text-gray-500">Location:</span> {locations.find(l => l.path === selectedLocation)?.name}</p>
                <p><span className="text-gray-500">Total Rounds:</span> {numRounds}</p>
                <div>
                  <span className="text-gray-500">Rounds:</span>
                  <ul className="ml-4 mt-1">
                    <li>1. {mcRounds.find(r => r.path === selectedMC)?.name} (MC)</li>
                    <li>2. {regRounds.find(r => r.path === selectedREG1)?.name} (General)</li>
                    {numRounds === 6 && (
                      <li>3. {(extraType === 'reg' ? regRounds : miscRounds).find(r => r.path === selectedExtra)?.name} ({extraType === 'reg' ? 'General' : 'Specific'})</li>
                    )}
                    <li>{numRounds === 5 ? '3' : '4'}. {miscRounds.find(r => r.path === selectedMISC1)?.name} (Specific)</li>
                    <li>{numRounds === 5 ? '4' : '5'}. {mysRounds.find(r => r.path === selectedMYS)?.name} (Mystery)</li>
                    <li>{numRounds === 5 ? '5' : '6'}. {bigRounds.find(r => r.path === selectedBIG)?.name} (BIG)</li>
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

  const getStepTitle = () => {
    const titles = {
      1: 'Choose Host',
      2: 'Choose Location',
      3: 'Number of Rounds',
      4: 'Round 1: Multiple Choice',
      5: 'Round 2: General',
      6: 'Round 3: Additional',
      7: `Round ${numRounds === 5 ? '3' : '4'}: Specific`,
      8: `Round ${numRounds === 5 ? '4' : '5'}: Mystery`,
      9: `Round ${numRounds === 5 ? '5' : '6'}: BIG Question`,
      10: 'Review & Build'
    };
    return titles[step] || '';
  };

  const totalSteps = numRounds === 5 ? 10 : 10; // 10 steps total (skip step 6 for 5 rounds)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-gradient-to-br from-[#1a1a2e] to-[#16213e] border-[#FFC107]/30 text-white max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-[#FFC107] text-2xl">Build Trivia Presentation</DialogTitle>
          <DialogDescription className="text-gray-400">
            Step {step} of {totalSteps}: {getStepTitle()}
          </DialogDescription>
        </DialogHeader>

        <div className="py-6">
          {renderStep()}
        </div>

        <DialogFooter className="flex gap-3">
          {step > 1 && (
            <Button
              onClick={handleBack}
              variant="outline"
              className="border-gray-600 text-gray-300 hover:bg-[#2a2a2a]"
              disabled={building}
            >
              <ChevronLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
          )}
          {step < 10 ? (
            <Button
              onClick={handleNext}
              className="bg-[#1657E8] hover:bg-[#1F5EE9] text-white"
            >
              Next
              <ChevronRight className="w-4 h-4 ml-2" />
            </Button>
          ) : (
            <Button
              onClick={handleBuild}
              disabled={building}
              className="bg-[#FFC107] hover:bg-[#FFD54F] text-black font-semibold"
            >
              {building ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Building...
                </>
              ) : (
                'Build Presentation'
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default TriviaBuilderWizard;
