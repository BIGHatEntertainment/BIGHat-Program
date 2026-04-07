import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, Image, Calendar, TrendingUp, ArrowRight, Clock, CheckCircle, AlertCircle, ShoppingCart, AlertTriangle, Building2, Star } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { useData } from '../../context/DataContext';

const DashboardOverview = ({ user }) => {
  const navigate = useNavigate();
  const { 
    getSponsorMetrics, 
    getActiveSubscription, 
    userAssets, 
    generatePlacements,
    getActiveLocations,
    userProfile
  } = useData();

  const metrics = getSponsorMetrics();
  const activeSubscription = getActiveSubscription();
  const placements = generatePlacements();
  const activeLocations = getActiveLocations();
  
  // Check if user is a venue sponsor
  const isVenueSponsor = userProfile?.isVenueSponsor || activeSubscription?.isVenueSponsor;

  const getStatusBadge = (status) => {
    switch (status) {
      case 'approved':
        return <Badge className="status-approved"><CheckCircle size={12} className="mr-1" /> Approved</Badge>;
      case 'pending':
        return <Badge className="status-pending"><Clock size={12} className="mr-1" /> Pending</Badge>;
      case 'revision_requested':
        return <Badge className="status-revision"><AlertCircle size={12} className="mr-1" /> Needs Revision</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  // Calculate days until subscription ends
  const getDaysUntilEnd = () => {
    if (!activeSubscription) return null;
    const endDate = new Date(activeSubscription.endDate);
    const today = new Date();
    const days = Math.ceil((endDate - today) / (1000 * 60 * 60 * 24));
    return days;
  };

  const daysRemaining = getDaysUntilEnd();

  return (
    <div className="space-y-8">
      {/* Welcome Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">
            Welcome back, {user?.name?.split(' ')[0] || 'Sponsor'}!
          </h1>
          <p className="text-white/60 mt-1">
            {activeSubscription 
              ? `${activeSubscription.packageName} • ${daysRemaining} days remaining`
              : "You don't have an active sponsorship yet"
            }
          </p>
        </div>
        {activeSubscription ? (
          <Button onClick={() => navigate('/dashboard/upload')} className="btn-gold">
            <Upload size={16} className="mr-2" />
            Upload New Asset
          </Button>
        ) : (
          <Button onClick={() => navigate('/dashboard/subscribe')} className="btn-gold">
            <ShoppingCart size={16} className="mr-2" />
            View Packages
          </Button>
        )}
      </div>

      {/* No Subscription Alert */}
      {!activeSubscription && (
        <div className="card-dark rounded-2xl p-6 border-orange-500/30 bg-orange-500/5">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-orange-500/20 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-orange-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">No Active Sponsorship</h2>
                <p className="text-white/60 text-sm">
                  Purchase a sponsorship package to get your brand in front of live trivia audiences.
                </p>
              </div>
            </div>
            <Button onClick={() => navigate('/dashboard/subscribe')} className="bg-orange-500 hover:bg-orange-600 text-white">
              Browse Packages
              <ArrowRight size={16} className="ml-2" />
            </Button>
          </div>
        </div>
      )}

      {/* Quick Stats - Different for venue sponsors */}
      {isVenueSponsor ? (
        /* Venue Sponsor Stats - Simplified */
        <div className="grid grid-cols-2 gap-4">
          <div className="card-dark rounded-xl p-5">
            <Building2 className="w-8 h-8 text-purple-400 mb-3" />
            <p className="text-2xl font-bold text-white">1</p>
            <p className="text-white/50 text-sm">Your Venue</p>
          </div>
          <div className="card-dark rounded-xl p-5">
            <Image className="w-8 h-8 text-[#f4d03f] mb-3" />
            <p className="text-2xl font-bold text-white">{metrics.activeAssets}</p>
            <p className="text-white/50 text-sm">Approved Assets</p>
          </div>
        </div>
      ) : (
        /* Regular Sponsor Stats - Full metrics */
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="card-dark rounded-xl p-5">
            <Calendar className="w-8 h-8 text-blue-400 mb-3" />
            <p className="text-2xl font-bold text-white">{metrics.totalShows}</p>
            <p className="text-white/50 text-sm">Shows This Month</p>
          </div>
          <div className="card-dark rounded-xl p-5">
            <TrendingUp className="w-8 h-8 text-green-400 mb-3" />
            <p className="text-2xl font-bold text-white">{metrics.estimatedImpressions.toLocaleString()}</p>
            <p className="text-white/50 text-sm">Est. Impressions</p>
          </div>
          <div className="card-dark rounded-xl p-5">
            <Image className="w-8 h-8 text-[#f4d03f] mb-3" />
            <p className="text-2xl font-bold text-white">{metrics.activeAssets}</p>
            <p className="text-white/50 text-sm">Approved Assets</p>
          </div>
          <div className="card-dark rounded-xl p-5">
            <Upload className="w-8 h-8 text-purple-400 mb-3" />
            <p className="text-2xl font-bold text-white">{metrics.venuesCovered}</p>
            <p className="text-white/50 text-sm">Venues Covered</p>
          </div>
        </div>
      )}

      {/* Active Sponsorship */}
      {activeSubscription && (
        <div className="card-featured rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4">Active Sponsorship</h2>
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div>
              <p className="text-[#f4d03f] font-bold text-xl">{activeSubscription.packageName}</p>
              <p className="text-white/60 text-sm mt-1">
                {activeSubscription.startDate} - {activeSubscription.endDate}
              </p>
            </div>
            <div className="flex items-center gap-3">
              {daysRemaining <= 7 && (
                <Badge className="bg-orange-500/20 text-orange-400 border-orange-500/30">
                  Renew Soon
                </Badge>
              )}
              <Badge className="bg-green-500/20 text-green-400 border-green-500/30">
                Active
              </Badge>
            </div>
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Your Assets */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-bold text-white">Your Assets</h2>
            <button
              onClick={() => navigate('/dashboard/assets')}
              className="text-[#f4d03f] text-sm hover:underline flex items-center gap-1"
            >
              View All <ArrowRight size={14} />
            </button>
          </div>
          {userAssets.length > 0 ? (
            <div className="space-y-3">
              {userAssets.slice(0, 3).map((asset) => (
                <div key={asset.id} className="flex items-center gap-4 p-3 bg-white/5 rounded-xl">
                  <div className="w-16 h-10 rounded-lg bg-[#1a1a2e] flex items-center justify-center overflow-hidden">
                    {asset.thumbnail ? (
                      <img src={asset.thumbnail} alt={asset.name} className="w-full h-full object-cover" />
                    ) : (
                      <Image className="w-6 h-6 text-white/30" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-white font-medium truncate">{asset.name}</p>
                    <p className="text-white/50 text-xs">{asset.uploadedAt}</p>
                  </div>
                  {getStatusBadge(asset.status)}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8">
              <Image className="w-12 h-12 text-white/20 mx-auto mb-3" />
              <p className="text-white/50 text-sm">No assets uploaded yet</p>
              {activeSubscription && (
                <Button 
                  onClick={() => navigate('/dashboard/upload')}
                  className="mt-3 btn-outline-gold text-sm"
                  size="sm"
                >
                  Upload Your First Asset
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Venue Sponsor: Show venue info instead of placements */}
        {isVenueSponsor ? (
          <div className="card-dark rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-4">
              <Building2 className="w-5 h-5 text-[#f4d03f]" />
              <h2 className="text-lg font-bold text-white">Your Venue Coverage</h2>
            </div>
            <div className="bg-[#f4d03f]/5 border border-[#f4d03f]/20 rounded-xl p-5">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-xl bg-[#f4d03f]/20 flex items-center justify-center flex-shrink-0">
                  <Star className="w-5 h-5 text-[#f4d03f]" />
                </div>
                <div>
                  <h3 className="text-white font-semibold mb-2">Exclusive Venue Display</h3>
                  <p className="text-white/60 text-sm leading-relaxed">
                    Your promotional content is displayed exclusively at your venue during trivia shows. 
                    Upload images to showcase your specials, events, or brand messaging to your customers.
                  </p>
                </div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="bg-white/5 rounded-lg p-3 text-center">
                <p className="text-white/40 text-xs">Asset Types</p>
                <p className="text-white font-medium text-sm">16:9 & 1:1</p>
              </div>
              <div className="bg-white/5 rounded-lg p-3 text-center">
                <p className="text-white/40 text-xs">Status</p>
                <p className="text-green-400 font-medium text-sm">Active</p>
              </div>
            </div>
          </div>
        ) : (
          /* Regular Sponsors: Show Upcoming Placements */
          <div className="card-dark rounded-2xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold text-white">Upcoming Placements</h2>
              <button
                onClick={() => navigate('/dashboard/placements')}
                className="text-[#f4d03f] text-sm hover:underline flex items-center gap-1"
              >
                View All <ArrowRight size={14} />
              </button>
            </div>
            {placements.length > 0 ? (
              <div className="space-y-3">
                {placements.slice(0, 4).map((placement) => (
                  <div key={placement.id} className="flex items-center gap-4 p-3 bg-white/5 rounded-xl">
                    <div className="w-12 h-12 rounded-lg bg-[#f4d03f]/10 flex items-center justify-center">
                      <Calendar size={20} className="text-[#f4d03f]" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-white font-medium">{placement.venue}</p>
                      <p className="text-white/50 text-xs">{placement.placement}</p>
                    </div>
                    <p className="text-white/60 text-sm">{placement.date}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <Calendar className="w-12 h-12 text-white/20 mx-auto mb-3" />
                <p className="text-white/50 text-sm">
                  {!activeSubscription 
                    ? "Purchase a sponsorship to get placements"
                    : metrics.activeAssets === 0
                      ? "Upload and get assets approved to see placements"
                      : "No placements scheduled"
                  }
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Available Venues - Only for regular sponsors */}
      {!isVenueSponsor && (
        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4">Available Venues</h2>
          <p className="text-white/60 text-sm mb-4">
            Your sponsorship will be displayed at these {activeLocations.length} active venues:
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {activeLocations.map((location) => (
              <div key={location.id} className="bg-white/5 rounded-xl p-4">
                <p className="text-white font-medium">{location.name}</p>
                <p className="text-white/50 text-sm">{location.city}</p>
                <p className="text-white/40 text-xs mt-1">
                  {location.dayOfWeek} at {location.time} • Capacity: {location.capacityTier || '> 50'}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action Cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <button
          onClick={() => navigate('/dashboard/upload')}
          disabled={!activeSubscription}
          className={`card-dark rounded-xl p-6 text-left transition-colors group ${
            activeSubscription ? 'hover:border-[#f4d03f]/30' : 'opacity-50 cursor-not-allowed'
          }`}
        >
          <Upload className="w-10 h-10 text-[#f4d03f] mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="font-bold text-white mb-1">Upload New Creative</h3>
          <p className="text-white/50 text-sm">Add a new GIF or image to your rotation</p>
        </button>
        <button
          onClick={() => navigate('/dashboard/stats')}
          className="card-dark rounded-xl p-6 text-left hover:border-[#f4d03f]/30 transition-colors group"
        >
          <TrendingUp className="w-10 h-10 text-green-400 mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="font-bold text-white mb-1">View Performance</h3>
          <p className="text-white/50 text-sm">Check your exposure metrics</p>
        </button>
        <button
          onClick={() => navigate('/dashboard/subscribe')}
          className="card-dark rounded-xl p-6 text-left hover:border-[#f4d03f]/30 transition-colors group"
        >
          <ArrowRight className="w-10 h-10 text-purple-400 mb-3 group-hover:scale-110 transition-transform" />
          <h3 className="font-bold text-white mb-1">
            {activeSubscription ? 'Upgrade Package' : 'Get Started'}
          </h3>
          <p className="text-white/50 text-sm">
            {activeSubscription ? 'Get more visibility with a higher tier' : 'Purchase a sponsorship package'}
          </p>
        </button>
      </div>
    </div>
  );
};

export default DashboardOverview;
