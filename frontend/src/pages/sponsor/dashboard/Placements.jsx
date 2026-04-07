import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Calendar, MapPin, ShoppingCart, Image } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { useData } from '../../../context/SponsorContext';

const Placements = () => {
  const navigate = useNavigate();
  const { 
    generatePlacements, 
    getActiveSubscription, 
    getUserApprovedAssets 
  } = useData();

  const activeSubscription = getActiveSubscription();
  const approvedAssets = getUserApprovedAssets();
  const placements = generatePlacements();

  // Group placements by date
  const groupedPlacements = placements.reduce((acc, placement) => {
    if (!acc[placement.date]) {
      acc[placement.date] = [];
    }
    acc[placement.date].push(placement);
    return acc;
  }, {});

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      weekday: 'long',
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const isUpcoming = (dateStr) => {
    return new Date(dateStr) >= new Date();
  };

  // If no active subscription, show prompt to purchase
  if (!activeSubscription) {
    return (
      <div>
        <div className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Show Placements</h1>
          <p className="text-white/60 mt-1">View where and when your ads appear</p>
        </div>
        <div className="card-dark rounded-2xl p-12 text-center">
          <ShoppingCart className="w-12 h-12 text-white/20 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">No Active Sponsorship</h2>
          <p className="text-white/60 mb-6">
            Purchase a sponsorship package to see your scheduled placements at trivia events.
          </p>
          <Button onClick={() => navigate('/dashboard/subscribe')} className="btn-gold">
            View Sponsorship Packages
          </Button>
        </div>
      </div>
    );
  }

  // If no approved assets, show prompt to upload
  if (approvedAssets.length === 0) {
    return (
      <div>
        <div className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Show Placements</h1>
          <p className="text-white/60 mt-1">View where and when your ads appear</p>
        </div>

        {/* Subscription Info */}
        <div className="card-featured rounded-2xl p-6 mb-8">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/60 text-sm">Active Sponsorship</p>
              <p className="text-[#f4d03f] font-bold text-lg">{activeSubscription.packageName}</p>
            </div>
            <Badge className="bg-green-500/20 text-green-400 border-green-500/30">Active</Badge>
          </div>
        </div>

        <div className="card-dark rounded-2xl p-12 text-center">
          <Image className="w-12 h-12 text-white/20 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">No Approved Assets</h2>
          <p className="text-white/60 mb-6">
            Upload and get your assets approved to see your scheduled placements.
          </p>
          <Button onClick={() => navigate('/dashboard/upload')} className="btn-gold">
            Upload Assets
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Show Placements</h1>
        <p className="text-white/60 mt-1">View where and when your ads appear</p>
      </div>

      {/* Info Box */}
      <div className="card-featured rounded-2xl p-6 mb-8">
        <div className="flex items-start gap-4">
          <Calendar className="w-8 h-8 text-[#f4d03f] flex-shrink-0" />
          <div>
            <h2 className="text-lg font-bold text-white mb-1">How Scheduling Works</h2>
            <p className="text-white/60 text-sm">
              Your approved assets are automatically rotated across all scheduled shows based on your sponsorship tier ({activeSubscription.packageName}). 
              Gold and Star Tier sponsors receive guaranteed placements at every event, while other tiers are distributed 
              fairly throughout the week.
            </p>
          </div>
        </div>
      </div>

      {/* Placements Timeline */}
      <div className="space-y-6">
        {Object.entries(groupedPlacements).map(([date, datePlacements]) => (
          <div key={date} className="card-dark rounded-2xl overflow-hidden">
            <div className={`px-6 py-4 border-b border-[#f4d03f]/10 ${
              isUpcoming(date) ? 'bg-[#f4d03f]/5' : 'bg-white/5'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                    isUpcoming(date) ? 'bg-[#f4d03f]/20' : 'bg-white/10'
                  }`}>
                    <Calendar className={`w-5 h-5 ${
                      isUpcoming(date) ? 'text-[#f4d03f]' : 'text-white/50'
                    }`} />
                  </div>
                  <div>
                    <p className="text-white font-medium">{formatDate(date)}</p>
                    <p className="text-white/50 text-sm">{datePlacements.length} placement(s)</p>
                  </div>
                </div>
                {isUpcoming(date) && (
                  <Badge className="bg-[#f4d03f]/20 text-[#f4d03f] border-[#f4d03f]/30">
                    Upcoming
                  </Badge>
                )}
              </div>
            </div>
            <div className="divide-y divide-[#f4d03f]/5">
              {datePlacements.map((placement, index) => (
                <div key={index} className="px-6 py-4 flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-white/5 flex items-center justify-center">
                    <MapPin className="w-5 h-5 text-white/50" />
                  </div>
                  <div className="flex-1">
                    <p className="text-white font-medium">{placement.venue}</p>
                    <p className="text-white/50 text-sm">{placement.placement}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Empty State */}
      {Object.keys(groupedPlacements).length === 0 && (
        <div className="card-dark rounded-2xl p-12 text-center">
          <Calendar className="w-12 h-12 text-white/20 mx-auto mb-4" />
          <p className="text-white/60">No placements scheduled yet</p>
          <p className="text-white/40 text-sm mt-1">
            Placements will be generated based on your subscription and approved assets.
          </p>
        </div>
      )}
    </div>
  );
};

export default Placements;
