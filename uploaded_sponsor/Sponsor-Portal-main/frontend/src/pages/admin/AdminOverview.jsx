import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Image, CheckSquare, AlertCircle, TrendingUp, ArrowRight, MapPin } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { useData } from '../../context/DataContext';

const AdminOverview = () => {
  const navigate = useNavigate();
  const { locations, sponsors, assets, pendingApprovals } = useData();

  const stats = [
    { label: 'Total Sponsors', value: sponsors.length, icon: Users, color: 'text-blue-400' },
    { label: 'Total Locations', value: locations.length, icon: MapPin, color: 'text-green-400' },
    { label: 'Pending Approvals', value: pendingApprovals.length, icon: AlertCircle, color: 'text-orange-400' },
    { label: 'Total Assets', value: assets.length + pendingApprovals.length, icon: Image, color: 'text-purple-400' },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Admin Dashboard</h1>
        <p className="text-white/60 mt-1">Manage sponsors and media approvals</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, index) => (
          <div key={index} className="card-dark rounded-xl p-5">
            <stat.icon className={`w-8 h-8 ${stat.color} mb-3`} />
            <p className="text-2xl font-bold text-white">{stat.value}</p>
            <p className="text-white/50 text-sm">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Pending Approvals Alert */}
      {pendingApprovals.length > 0 && (
        <div className="card-dark rounded-2xl p-6 border-orange-500/30 bg-orange-500/5">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-orange-500/20 flex items-center justify-center">
                <AlertCircle className="w-6 h-6 text-orange-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">Pending Approvals</h2>
                <p className="text-white/60 text-sm">
                  {pendingApprovals.length} asset(s) waiting for review
                </p>
              </div>
            </div>
            <Button onClick={() => navigate('/admin/approvals')} className="bg-orange-500 hover:bg-orange-600 text-white">
              Review Now
              <ArrowRight size={16} className="ml-2" />
            </Button>
          </div>
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Recent Sponsors */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-bold text-white">Recent Sponsors</h2>
            <button
              onClick={() => navigate('/admin/sponsors')}
              className="text-[#e94560] text-sm hover:underline flex items-center gap-1"
            >
              View All <ArrowRight size={14} />
            </button>
          </div>
          <div className="space-y-3">
            {sponsors.slice(0, 3).map((sponsor) => (
              <div key={sponsor.id} className="flex items-center gap-4 p-3 bg-white/5 rounded-xl">
                <div className="w-10 h-10 rounded-full bg-[#f4d03f]/10 flex items-center justify-center">
                  <span className="text-[#f4d03f] font-bold text-sm">
                    {sponsor.businessName.charAt(0)}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white font-medium truncate">{sponsor.businessName}</p>
                  <p className="text-white/50 text-xs">{sponsor.package}</p>
                </div>
                <Badge className={sponsor.status === 'active' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}>
                  {sponsor.status}
                </Badge>
              </div>
            ))}
          </div>
        </div>

        {/* Pending Assets */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-bold text-white">Pending Assets</h2>
            <button
              onClick={() => navigate('/admin/approvals')}
              className="text-[#e94560] text-sm hover:underline flex items-center gap-1"
            >
              View All <ArrowRight size={14} />
            </button>
          </div>
          <div className="space-y-3">
            {pendingApprovals.slice(0, 3).map((asset) => (
              <div key={asset.id} className="flex items-center gap-4 p-3 bg-white/5 rounded-xl">
                <img
                  src={asset.thumbnail}
                  alt={asset.assetName}
                  className="w-16 h-10 rounded-lg object-cover"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-white font-medium truncate">{asset.assetName}</p>
                  <p className="text-white/50 text-xs">{asset.sponsorName}</p>
                </div>
                <Badge className="bg-orange-500/20 text-orange-400">
                  Pending
                </Badge>
              </div>
            ))}
            {pendingApprovals.length === 0 && (
              <p className="text-white/50 text-center py-4">No pending approvals</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminOverview;