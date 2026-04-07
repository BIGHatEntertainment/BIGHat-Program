import React from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, TrendingUp, Eye, Calendar, RefreshCw, ShoppingCart, Clock, MapPin, Image, Building2, Star } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { useData } from '../../context/DataContext';

const Statistics = () => {
  const navigate = useNavigate();
  const { 
    getSponsorMetrics, 
    getActiveSubscription, 
    getActiveLocations,
    userProfile,
    getUserApprovedAssets
  } = useData();

  const metrics = getSponsorMetrics();
  const activeSubscription = getActiveSubscription();
  const activeLocations = getActiveLocations();
  const approvedAssets = getUserApprovedAssets();
  
  // Check if user is a venue sponsor
  const isVenueSponsor = userProfile?.isVenueSponsor || activeSubscription?.isVenueSponsor;

  // If no active subscription, show prompt to purchase
  if (!activeSubscription) {
    return (
      <div>
        <div className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Statistics</h1>
          <p className="text-white/60 mt-1">Track your sponsorship performance</p>
        </div>
        <div className="card-dark rounded-2xl p-12 text-center">
          <ShoppingCart className="w-12 h-12 text-white/20 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">No Active Sponsorship</h2>
          <p className="text-white/60 mb-6">
            Purchase a sponsorship package to start tracking your performance metrics.
          </p>
          <Button onClick={() => navigate('/dashboard/subscribe')} className="btn-gold">
            View Sponsorship Packages
          </Button>
        </div>
      </div>
    );
  }

  // Metric cards for regular sponsors (multi-venue)
  const regularMetricCards = [
    {
      label: 'Shows This Month',
      value: metrics.totalShows,
      icon: Calendar,
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/10',
    },
    {
      label: 'Est. Impressions',
      value: metrics.estimatedImpressions.toLocaleString(),
      icon: Eye,
      color: 'text-green-400',
      bgColor: 'bg-green-500/10',
    },
    {
      label: 'Venues Covered',
      value: metrics.venuesCovered,
      icon: MapPin,
      color: 'text-purple-400',
      bgColor: 'bg-purple-500/10',
    },
    {
      label: 'Approved Assets',
      value: metrics.activeAssets,
      icon: Image,
      color: 'text-[#f4d03f]',
      bgColor: 'bg-[#f4d03f]/10',
    },
  ];

  // Metric cards for venue sponsors (single venue focus)
  const venueMetricCards = [
    {
      label: 'Your Venue',
      value: '1',
      icon: Building2,
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/10',
    },
    {
      label: 'Approved Assets',
      value: metrics.activeAssets,
      icon: Image,
      color: 'text-[#f4d03f]',
      bgColor: 'bg-[#f4d03f]/10',
    },
  ];
  
  // Use the appropriate metric cards based on sponsor type
  const metricCards = isVenueSponsor ? venueMetricCards : regularMetricCards;

  // Calculate date range for display
  const startDate = new Date(activeSubscription.startDate);
  const today = new Date();
  const dateRange = `${startDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${today.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Statistics</h1>
          <p className="text-white/60 mt-1">Track your sponsorship performance</p>
        </div>
        <Button variant="outline" className="btn-outline-gold">
          <RefreshCw size={16} className="mr-2" />
          Refresh Data
        </Button>
      </div>

      {/* Subscription Info */}
      <div className="card-featured rounded-2xl p-6 mb-8">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <p className="text-white/60 text-sm">Active Sponsorship</p>
            <p className="text-[#f4d03f] font-bold text-xl">{activeSubscription.packageName}</p>
            <p className="text-white/50 text-sm mt-1">
              {activeSubscription.startDate} - {activeSubscription.endDate}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-white/60 text-sm">Days as Sponsor</p>
              <p className="text-white font-bold text-lg">{metrics.daysAsSponsor}</p>
            </div>
            <Badge className="bg-green-500/20 text-green-400 border-green-500/30">Active</Badge>
          </div>
        </div>
      </div>

      {/* Date Range */}
      <div className="card-dark rounded-xl px-4 py-3 mb-8 inline-block">
        <p className="text-white/50 text-sm">
          Showing data for: <span className="text-white font-medium">{dateRange}</span>
        </p>
      </div>

      {/* Metric Cards */}
      <div className={`grid gap-6 mb-8 ${isVenueSponsor ? 'sm:grid-cols-2' : 'sm:grid-cols-2 lg:grid-cols-4'}`}>
        {metricCards.map((metric, index) => (
          <div key={index} className="card-dark rounded-2xl p-6">
            <div className={`w-12 h-12 rounded-xl ${metric.bgColor} flex items-center justify-center mb-4`}>
              <metric.icon className={`w-6 h-6 ${metric.color}`} />
            </div>
            <p className="text-3xl font-bold text-white mb-1">{metric.value}</p>
            <p className="text-white/50 text-sm">{metric.label}</p>
          </div>
        ))}
      </div>

      {/* Venue Sponsor Info Section */}
      {isVenueSponsor && (
        <div className="card-dark rounded-2xl p-6 mb-8">
          <div className="flex items-center gap-2 mb-4">
            <Building2 className="w-5 h-5 text-[#f4d03f]" />
            <h2 className="text-lg font-bold text-white">Your Venue Sponsorship</h2>
          </div>
          
          <div className="bg-[#f4d03f]/5 border border-[#f4d03f]/20 rounded-xl p-6">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-[#f4d03f]/20 flex items-center justify-center flex-shrink-0">
                <Star className="w-6 h-6 text-[#f4d03f]" />
              </div>
              <div>
                <h3 className="text-white font-semibold mb-2">Exclusive Venue Coverage</h3>
                <p className="text-white/60 text-sm leading-relaxed mb-4">
                  As a venue sponsor, your promotional content is displayed exclusively at your own location. 
                  This ensures your messaging reaches your customers directly without being shown at other venues.
                </p>
                <div className="flex flex-wrap gap-3">
                  <div className="bg-white/5 rounded-lg px-3 py-2">
                    <p className="text-white/40 text-xs">Coverage</p>
                    <p className="text-white font-medium text-sm">Your Venue Only</p>
                  </div>
                  <div className="bg-white/5 rounded-lg px-3 py-2">
                    <p className="text-white/40 text-xs">Asset Types</p>
                    <p className="text-white font-medium text-sm">16:9 & 1:1 Formats</p>
                  </div>
                  <div className="bg-white/5 rounded-lg px-3 py-2">
                    <p className="text-white/40 text-xs">Status</p>
                    <p className="text-green-400 font-medium text-sm">Active</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {approvedAssets.length === 0 && (
            <div className="mt-6 text-center py-6 bg-white/5 rounded-xl">
              <Image className="w-10 h-10 text-white/20 mx-auto mb-3" />
              <p className="text-white/60 mb-2">No approved assets yet</p>
              <p className="text-white/40 text-sm mb-4">
                Upload your promotional images to display at your venue.
              </p>
              <Button onClick={() => navigate('/dashboard/upload')} className="btn-outline-gold">
                Upload Assets
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Performance Summary - Only for regular sponsors */}
      {!isVenueSponsor && (
        <div className="card-dark rounded-2xl p-6 mb-8">
          <div className="flex items-center gap-2 mb-6">
            <BarChart3 className="w-5 h-5 text-[#f4d03f]" />
            <h2 className="text-lg font-bold text-white">Performance Summary</h2>
          </div>

          {approvedAssets.length === 0 ? (
            <div className="text-center py-8">
              <Image className="w-12 h-12 text-white/20 mx-auto mb-4" />
              <p className="text-white/60 mb-2">No approved assets yet</p>
              <p className="text-white/40 text-sm mb-4">
                Upload and get your assets approved to start seeing performance data.
              </p>
              <Button onClick={() => navigate('/dashboard/upload')} className="btn-outline-gold">
                Upload Assets
              </Button>
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 gap-6">
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm mb-2">Venue Capacity Breakdown</p>
                <div className="flex gap-2 flex-wrap">
                  {['< 50', '> 50', '100+'].map(tier => {
                    const count = activeLocations.filter(loc => loc.capacityTier === tier).length;
                    return (
                      <Badge key={tier} className="bg-[#f4d03f]/10 text-[#f4d03f] border-[#f4d03f]/30">
                        {tier}: {count}
                      </Badge>
                    );
                  })}
                </div>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm mb-2">Weekly Exposure</p>
                <p className="text-2xl font-bold text-white">
                  {Math.round(metrics.totalShows / 4)}
                </p>
                <p className="text-white/40 text-xs mt-1">shows per week on average</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Venue Breakdown - Only for regular sponsors */}
      {!isVenueSponsor && (
        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4">Venue Breakdown</h2>
          {activeLocations.length > 0 ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {activeLocations.map((venue, index) => {
                const venueShows = Math.round(metrics.totalShows / activeLocations.length);
                const percentage = Math.round((venueShows / metrics.totalShows) * 100) || 0;
                return (
                  <div key={venue.id || index} className="bg-white/5 rounded-xl p-4">
                    <p className="text-white font-medium text-sm mb-2 truncate">
                      {venue.name} - {venue.city}
                    </p>
                    <div className="flex items-end justify-between">
                      <div>
                        <p className="text-2xl font-bold text-[#f4d03f]">{venueShows}</p>
                        <p className="text-white/40 text-xs">shows</p>
                      </div>
                      <div className="text-right">
                        <p className="text-white/50 text-sm">{percentage}%</p>
                        <Badge className="bg-white/10 text-white/60 text-xs">{venue.capacityTier || '> 50'}</Badge>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8">
              <MapPin className="w-12 h-12 text-white/20 mx-auto mb-4" />
              <p className="text-white/60">No venues available</p>
              <p className="text-white/40 text-sm mt-1">
                Venue data will appear once locations are configured.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Disclaimer - Only for regular sponsors */}
      {!isVenueSponsor && (
        <div className="mt-6 text-center">
          <p className="text-white/40 text-xs">
            * Statistics estimated based on venue capacity. Actual numbers may vary.
          </p>
        </div>
      )}
    </div>
  );
};

export default Statistics;
