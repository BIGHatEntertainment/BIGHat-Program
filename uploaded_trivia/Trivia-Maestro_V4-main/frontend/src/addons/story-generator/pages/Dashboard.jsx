import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Video, Sparkles, Home, Loader2, RefreshCw, Play, Calendar, MapPin } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Card } from '../../../components/ui/card';
import { Badge } from '../../../components/ui/badge';
import { storyGeneratorAPI } from '../../../services/api';
import { toast } from 'sonner';

// Round type colors - updated to match new theme
const ROUND_COLORS = {
  'MC': '#22c55e',    // Green
  'REG': '#ef4444',   // Red
  'MISC': '#3b82f6',  // Blue
  'MYS': '#a855f7',   // Purple
  'BIG': '#fbdd68',   // Gold (theme accent)
};

const Dashboard = () => {
  const navigate = useNavigate();
  const [presentations, setPresentations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [userName, setUserName] = useState('');

  useEffect(() => {
    const storedName = localStorage.getItem('userName') || '';
    const viewAll = localStorage.getItem('viewAll') === 'true';
    setUserName(storedName);
    loadPresentations(storedName, viewAll || !storedName);
  }, []);

  const loadPresentations = async (name, viewAll = false, isRefresh = false) => {
    try {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      
      const userName = viewAll ? null : name.toLowerCase();
      const data = await storyGeneratorAPI.getPresentations(userName);
      setPresentations(data);
      
      if (isRefresh) {
        toast.success(`Loaded ${data.length} presentations`);
      }
    } catch (error) {
      console.error('Error loading presentations:', error);
      toast.error('Failed to load presentations');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    const viewAll = localStorage.getItem('viewAll') === 'true';
    loadPresentations(userName, viewAll, true);
  };

  const handleSelectPresentation = (presentation) => {
    const locationFolder = presentation.locationFolder || presentation.location || '';
    navigate(`/story-generator/create`, { 
      state: { 
        presentation: {
          id: presentation.id,
          name: presentation.name,
          location: (presentation.location || '').replace(/^\d+_/, ''),
          locationFolder: locationFolder,
          host: presentation.host,
          numRounds: presentation.numRounds || presentation.roundTypes?.length || 5,
          roundTypes: presentation.roundTypes || [],
          roundNames: presentation.roundNames || [],
          createdAt: presentation.createdAt,
          createdBy: presentation.createdBy
        }
      }
    });
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      weekday: 'short', 
      month: 'short', 
      day: 'numeric' 
    });
  };

  return (
    <div className="min-h-screen bg-[#000e2a]" data-testid="story-generator-dashboard">
      {/* Animated background */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-20 left-10 w-[500px] h-[500px] bg-[#141b50] rounded-full filter blur-[120px] opacity-40 animate-pulse" />
        <div className="absolute bottom-20 right-20 w-[400px] h-[400px] bg-[#fbdd68] rounded-full filter blur-[150px] opacity-10 animate-pulse" style={{ animationDelay: '1.5s' }} />
        <div className="absolute top-1/2 left-1/2 w-[600px] h-[600px] bg-[#151c51] rounded-full filter blur-[140px] opacity-30 animate-pulse" style={{ animationDelay: '3s' }} />
      </div>

      {/* Header */}
      <header className="border-b border-[#fbdd68]/20 bg-[#000e2a]/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <motion.div 
            className="flex items-center gap-4"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
          >
            <Button
              variant="outline"
              onClick={() => navigate('/')}
              className="rounded-lg border-[#fbdd68]/30 bg-[#141b50]/60 hover:bg-[#fbdd68] hover:text-[#000e2a] text-[#fbdd68] transition-all duration-300 gap-2"
              data-testid="exit-btn"
            >
              <Home className="h-4 w-4" />
              Exit
            </Button>
            
            <div className="h-px w-6 bg-gradient-to-r from-transparent via-[#fbdd68]/50 to-transparent" />
            
            <div className="h-12 w-12 rounded-xl bg-[#fbdd68] flex items-center justify-center shadow-lg shadow-[#fbdd68]/30">
              <Video className="h-6 w-6 text-[#000e2a]" />
            </div>
            <div>
              <h1 className="font-bold text-xl tracking-wide text-white">
                STORY GENERATOR
              </h1>
              <p className="text-xs text-[#fbdd68]/80 font-mono tracking-wider">
                // SELECT PRESENTATION
              </p>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            <Button
              variant="outline"
              onClick={handleRefresh}
              disabled={refreshing}
              className="rounded-lg border-[#fbdd68]/30 bg-[#141b50]/60 hover:bg-[#141b50] text-white transition-all duration-300 gap-2"
              data-testid="refresh-btn"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </motion.div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-12 relative z-10">
        {/* Hero Section */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          className="mb-12"
        >
          <div className="flex items-center gap-2 mb-3">
            <motion.div
              animate={{ rotate: [0, 360] }}
              transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
            >
              <Sparkles className="h-5 w-5 text-[#fbdd68]" />
            </motion.div>
            <span className="font-mono text-sm uppercase tracking-[0.3em] text-[#fbdd68]">
              Your Recent Presentations
            </span>
            <div className="h-px flex-1 bg-gradient-to-r from-[#fbdd68]/50 to-transparent ml-4" />
          </div>
          
          <h2 className="text-4xl font-bold text-white tracking-wide">
            Select a <span className="text-[#fbdd68]">Presentation</span>
          </h2>
          
          <p className="text-[#8892b0] mt-3 max-w-2xl leading-relaxed">
            Click on a presentation to generate an Instagram Story. The same presentations from your home screen are shown here.
          </p>

          {/* Stats bar */}
          <motion.div 
            className="flex gap-8 mt-6 pt-6 border-t border-[#fbdd68]/10"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
          >
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-[#fbdd68] animate-pulse" />
              <span className="font-mono text-xs text-[#8892b0]">{presentations.length} PRESENTATIONS</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-[#fbdd68]/60 animate-pulse" style={{ animationDelay: '0.5s' }} />
              <span className="font-mono text-xs text-[#8892b0]">9:16 FORMAT</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-[#fbdd68]/40 animate-pulse" style={{ animationDelay: '1s' }} />
              <span className="font-mono text-xs text-[#8892b0]">~25s DURATION</span>
            </div>
          </motion.div>
        </motion.div>

        {/* Loading State */}
        {loading ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-20"
          >
            <div className="h-20 w-20 rounded-2xl bg-[#141b50]/50 border border-[#fbdd68]/20 flex items-center justify-center mx-auto mb-6">
              <Loader2 className="h-10 w-10 text-[#fbdd68] animate-spin" />
            </div>
            <h3 className="text-2xl font-bold text-white tracking-wide">
              Loading Presentations
            </h3>
            <p className="text-[#8892b0] mt-2">
              Fetching your recent presentations...
            </p>
          </motion.div>
        ) : presentations.length > 0 ? (
          /* Presentations Grid */
          <div 
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
            data-testid="presentations-grid"
          >
            {presentations.map((presentation, index) => (
              <motion.div
                key={presentation.id}
                initial={{ opacity: 0, y: 40, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ 
                  delay: index * 0.1,
                  duration: 0.5,
                  ease: [0.16, 1, 0.3, 1]
                }}
              >
                <Card 
                  className="group bg-[#0a1940]/80 backdrop-blur-sm border border-[#fbdd68]/10 hover:border-[#fbdd68]/40 hover:shadow-[0_0_30px_rgba(251,221,104,0.15)] transition-all duration-300 overflow-hidden cursor-pointer"
                  onClick={() => handleSelectPresentation(presentation)}
                  data-testid={`presentation-card-${presentation.id}`}
                >
                  {/* Card Header */}
                  <div className="relative h-36 bg-gradient-to-br from-[#141b50] to-[#0a1940] overflow-hidden">
                    <div className="absolute inset-0 bg-gradient-to-t from-[#000e2a] via-transparent to-transparent z-10" />
                    
                    {/* Location name background */}
                    <div className="absolute inset-0 flex items-center justify-center opacity-10">
                      <span className="text-4xl font-bold text-white tracking-widest">
                        {(presentation.location || presentation.locationFolder || 'TRIVIA').replace(/^\d+_/, '').toUpperCase()}
                      </span>
                    </div>
                    
                    {/* Play button on hover */}
                    <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity z-20">
                      <motion.div
                        initial={{ scale: 0.8 }}
                        whileHover={{ scale: 1.1 }}
                        className="h-14 w-14 rounded-full bg-[#fbdd68] flex items-center justify-center shadow-lg shadow-[#fbdd68]/40"
                      >
                        <Play className="h-6 w-6 text-[#000e2a] ml-1" />
                      </motion.div>
                    </div>
                    
                    {/* Badge */}
                    <Badge className="absolute top-3 right-3 z-20 bg-[#fbdd68] text-[#000e2a] font-bold text-[10px]">
                      TRIVIA
                    </Badge>
                    
                    {/* Date */}
                    <div className="absolute bottom-3 left-3 z-20 flex items-center gap-1.5 bg-[#000e2a]/70 backdrop-blur-sm px-2 py-1 rounded-full">
                      <Calendar className="h-3 w-3 text-[#fbdd68]" />
                      <span className="font-mono text-[10px] text-white/80">{formatDate(presentation.createdAt)}</span>
                    </div>
                  </div>

                  {/* Card Content */}
                  <div className="p-4">
                    <h3 className="font-bold text-lg text-white tracking-wide truncate">
                      {presentation.name}
                    </h3>
                    
                    <div className="flex items-center gap-2 mt-2 text-[#8892b0]">
                      <MapPin className="h-3 w-3" />
                      <span className="text-sm truncate">
                        {(presentation.location || presentation.locationFolder || 'Unknown').replace(/^\d+_/, '')}
                      </span>
                    </div>
                    
                    {/* Round colors preview */}
                    {presentation.roundTypes && presentation.roundTypes.length > 0 && (
                      <div className="flex gap-1.5 mt-3">
                        {presentation.roundTypes.map((type, idx) => (
                          <motion.span 
                            key={idx}
                            className="h-3 w-3 rounded-full border border-white/10"
                            style={{ backgroundColor: ROUND_COLORS[type] || '#6b7280' }}
                            whileHover={{ scale: 1.5 }}
                            title={type}
                          />
                        ))}
                      </div>
                    )}
                    
                    {/* Footer */}
                    <div className="flex items-center justify-between mt-4 pt-3 border-t border-[#fbdd68]/10">
                      <span className="font-mono text-xs text-[#8892b0]">
                        {presentation.slideCount || presentation.numRounds * 10 || '~100'} slides
                      </span>
                      <span className="text-xs text-[#fbdd68] font-medium group-hover:underline">
                        Generate →
                      </span>
                    </div>
                  </div>
                </Card>
              </motion.div>
            ))}
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="text-center py-20"
          >
            <div className="h-20 w-20 rounded-2xl bg-[#141b50]/50 border border-[#fbdd68]/10 flex items-center justify-center mx-auto mb-6">
              <Video className="h-10 w-10 text-[#8892b0]" />
            </div>
            <h3 className="text-2xl font-bold text-white tracking-wide">
              No Presentations Yet
            </h3>
            <p className="text-[#8892b0] mt-2 mb-8">
              Build a trivia presentation first to generate stories
            </p>
            <Button
              onClick={() => navigate('/')}
              className="rounded-lg bg-[#fbdd68] text-[#000e2a] hover:bg-[#fee16b] font-semibold"
              data-testid="go-home-btn"
            >
              <Home className="h-4 w-4 mr-2" />
              Go to Build Wizard
            </Button>
          </motion.div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#fbdd68]/10 mt-auto relative z-10">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <p className="text-xs text-[#8892b0] font-mono">
              // CLIENT-SIDE PROCESSING • YOUR DATA STAYS PRIVATE
            </p>
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs text-green-400 font-mono">SYSTEM ONLINE</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Dashboard;
