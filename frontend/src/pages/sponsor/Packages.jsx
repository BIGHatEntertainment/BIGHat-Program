import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Star, ArrowRight, Info } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/ui/tooltip';
import { sponsorshipPackages } from '../data/mock';

const Packages = () => {
  const navigate = useNavigate();

  const getPackageStyle = (pkg) => {
    if (pkg.featured) return 'card-featured';
    return 'card-dark';
  };

  return (
    <div className="min-h-screen pt-28 pb-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-4xl sm:text-5xl font-bold text-white mb-4">
            Sponsorship <span className="gradient-text">Packages</span>
          </h1>
          <p className="text-white/60 max-w-2xl mx-auto text-lg">
            Choose the perfect sponsorship tier for your business. From single-event exposure to full-year partnerships.
          </p>
        </div>

        {/* À La Carte Section */}
        <div className="mb-16">
          <div className="card-dark rounded-2xl p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-[#f4d03f]/10 flex items-center justify-center">
                <span className="text-[#f4d03f] font-bold text-xl">BH</span>
              </div>
              <div>
                <h2 className="text-2xl font-bold text-white">À La Carte Options</h2>
                <p className="text-white/60">Pick and choose individual promotional items</p>
              </div>
            </div>
            <div className="space-y-3">
              {sponsorshipPackages[0].items.map((item, index) => (
                <div key={index} className="bg-white/5 rounded-xl p-4 hover:bg-white/10 transition-colors">
                  <div className="flex justify-between items-start">
                    <p className="text-white font-medium">{item.name}</p>
                    {item.hasCapacityPricing ? (
                      <div className="text-right">
                        <p className="text-[#f4d03f] font-bold">
                          ${item.capacityPricing[0].price} <span className="text-white/50 text-sm font-normal">({item.capacityPricing[0].tier})</span>
                          {' / '}
                          ${item.capacityPricing[1].price} <span className="text-white/50 text-sm font-normal">({item.capacityPricing[1].tier})</span>
                        </p>
                        {item.duration && (
                          <p className="text-white/40 text-xs mt-1">{item.duration}</p>
                        )}
                      </div>
                    ) : (
                      <p className="text-[#f4d03f] font-bold">${item.price}</p>
                    )}
                  </div>
                  {item.description && (
                    <p className="text-white/50 text-sm mt-1">{item.description}</p>
                  )}
                </div>
              ))}
            </div>
            <p className="text-white/40 text-sm mt-4 flex items-center gap-2">
              <Info size={14} />
              {sponsorshipPackages[0].note}
            </p>
          </div>
        </div>

        {/* Main Packages Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8 items-stretch mt-8 overflow-visible">
          {sponsorshipPackages.slice(1).map((pkg) => (
            <div
              key={pkg.id}
              className={`${getPackageStyle(pkg)} rounded-2xl p-6 flex flex-col relative h-full`}
              style={{ overflow: 'visible' }}
            >
              {/* Badges positioned above the card */}
              {(pkg.featured || pkg.spotsAvailable) && (
                <div className="absolute -top-4 left-0 right-0 flex justify-between px-4 z-20">
                  {pkg.featured && (
                    <Badge className="bg-[#f4d03f] text-[#1a1a2e] border-0 shadow-lg px-3 py-1">
                      <Star size={12} className="mr-1" fill="currentColor" />
                      Popular
                    </Badge>
                  )}
                  {!pkg.featured && <span></span>}
                  {pkg.spotsAvailable && (
                    <Badge className="bg-[#e94560] text-white border-0 shadow-lg px-3 py-1">
                      Only {pkg.spotsAvailable} Spots
                    </Badge>
                  )}
                </div>
              )}

              <div className="mb-4 mt-2">
                <div className="w-10 h-10 rounded-lg bg-[#f4d03f]/10 flex items-center justify-center mb-4">
                  <span className="text-[#f4d03f] font-bold">BH</span>
                </div>
                <h3 className="text-xl font-bold text-white mb-1">{pkg.name}</h3>
                <p className="text-[#f4d03f] font-bold text-2xl">{pkg.priceLabel}</p>
                <p className="text-white/50 text-sm mt-2">{pkg.description}</p>
              </div>

              {/* Bronze location options */}
              {pkg.hasLocationOptions && (
                <div className="mb-4 p-3 bg-white/5 rounded-lg">
                  {pkg.locationOptions.map((option) => (
                    <div key={option.id} className="flex justify-between items-center py-1">
                      <span className="text-white/70 text-sm">{option.name}</span>
                      <span className="text-[#f4d03f] font-semibold">${option.price}</span>
                    </div>
                  ))}
                </div>
              )}

              <ul className="space-y-2 flex-grow mb-6">
                {pkg.features.map((feature, index) => (
                  <li key={index} className="flex items-start gap-2 text-white/70 text-sm">
                    <Check size={14} className="text-[#f4d03f] mt-0.5 flex-shrink-0" />
                    <span>{typeof feature === 'string' ? feature : feature.text}</span>
                  </li>
                ))}
              </ul>

              <Button
                onClick={() => navigate('/signup', { state: { packageId: pkg.id } })}
                className={`${pkg.featured ? 'btn-gold' : 'btn-outline-gold'} w-full mt-auto`}
              >
                Select Package
                <ArrowRight size={16} className="ml-2" />
              </Button>
            </div>
          ))}
        </div>

        {/* Contact CTA */}
        <div className="mt-16 text-center">
          <div className="card-dark rounded-2xl p-8 max-w-2xl mx-auto">
            <h3 className="text-xl font-bold text-white mb-2">Need a Custom Package?</h3>
            <p className="text-white/60 mb-6">
              We can create tailored sponsorship solutions for your specific needs. Contact us to discuss.
            </p>
            <Button
              variant="outline"
              onClick={() => navigate('/faq')}
              className="btn-outline-gold"
            >
              Contact BIG Hat
              <ArrowRight size={16} className="ml-2" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Packages;