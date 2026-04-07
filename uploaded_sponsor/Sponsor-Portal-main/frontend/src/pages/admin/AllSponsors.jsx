import React from 'react';
import { Mail, Building2, Calendar, Image } from 'lucide-react';
import { Badge } from '../../components/ui/badge';
import { mockAllSponsors } from '../../data/mock';

const AllSponsors = () => {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-white">All Sponsors</h1>
        <p className="text-white/60 mt-1">Manage sponsor accounts and subscriptions</p>
      </div>

      <div className="card-dark rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#f4d03f]/10">
                <th className="text-left p-4 text-white/50 font-medium text-sm">Sponsor</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Package</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Assets</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Joined</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Status</th>
              </tr>
            </thead>
            <tbody>
              {mockAllSponsors.map((sponsor) => (
                <tr key={sponsor.id} className="border-b border-[#f4d03f]/5 hover:bg-white/5 transition-colors">
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-[#f4d03f]/10 flex items-center justify-center flex-shrink-0">
                        <span className="text-[#f4d03f] font-bold">
                          {sponsor.businessName.charAt(0)}
                        </span>
                      </div>
                      <div>
                        <p className="text-white font-medium">{sponsor.businessName}</p>
                        <p className="text-white/50 text-sm flex items-center gap-1">
                          <Mail size={12} />
                          {sponsor.email}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="p-4">
                    <span className="text-[#f4d03f] font-medium">{sponsor.package}</span>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-2 text-white/70">
                      <Image size={14} />
                      {sponsor.assetsCount}
                    </div>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-2 text-white/50 text-sm">
                      <Calendar size={14} />
                      {sponsor.joinedAt}
                    </div>
                  </td>
                  <td className="p-4">
                    <Badge className={sponsor.status === 'active' 
                      ? 'bg-green-500/20 text-green-400 border-green-500/30' 
                      : 'bg-gray-500/20 text-gray-400 border-gray-500/30'
                    }>
                      {sponsor.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default AllSponsors;