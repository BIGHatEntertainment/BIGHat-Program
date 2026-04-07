import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ArrowLeft, Check, Plus, Minus, ShoppingCart, Sparkles, Crown, Star, Award } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { useData } from '../../../context/SponsorContext';
import { sponsorshipPackages } from '../../data/mock';

const PackageSelection = () => {
  const navigate = useNavigate();
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [alaCarteItems, setAlaCarteItems] = useState({});
  const [showUpsell, setShowUpsell] = useState(false);

  const packages = sponsorshipPackages.filter(p => p.id !== 'alacarte');
  const alaCarteOptions = sponsorshipPackages.find(p => p.id === 'alacarte')?.items || [];

  const packageIcons = {
    'bronze': Award,
    'silver': Star,
    'gold': Sparkles,
    'star-tier': Crown,
  };

  const toggleAlaCarteItem = (itemName, delta) => {
    setAlaCarteItems(prev => {
      const current = prev[itemName] || 0;
      const newValue = Math.max(0, current + delta);
      if (newValue === 0) {
        const { [itemName]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [itemName]: newValue };
    });
  };

  const calculateTotal = () => {
    let total = 0;
    
    // Package price
    if (selectedPackage) {
      const pkg = packages.find(p => p.id === selectedPackage);
      if (pkg?.price) {
        total += pkg.price;
      }
    }

    // À La Carte items
    Object.entries(alaCarteItems).forEach(([name, qty]) => {
      const item = alaCarteOptions.find(i => i.name === name);
      if (item) {
        total += item.price * qty;
      }
    });

    return total;
  };

  const getSelectedItemsCount = () => {
    return Object.values(alaCarteItems).reduce((sum, qty) => sum + qty, 0);
  };

  const handleContinue = () => {
    if (selectedPackage && !showUpsell) {
      // Show upsell after package selection
      setShowUpsell(true);
    } else {
      // Save selection to localStorage for checkout
      const selection = {
        package: selectedPackage ? packages.find(p => p.id === selectedPackage) : null,
        alaCarteItems: Object.entries(alaCarteItems).map(([name, qty]) => ({
          name,
          quantity: qty,
          price: alaCarteOptions.find(i => i.name === name)?.price || 0,
        })),
        total: calculateTotal(),
      };
      localStorage.setItem('sponsorship_selection', JSON.stringify(selection));
      navigate('/onboarding/checkout');
    }
  };

  const handleBack = () => {
    if (showUpsell) {
      setShowUpsell(false);
    } else {
      navigate('/onboarding/assets');
    }
  };

  const canContinue = selectedPackage || getSelectedItemsCount() > 0;

  // Upsell View
  if (showUpsell) {
    return (
      <div className="space-y-8">
        <div className="text-center">
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Enhance Your Package</h1>
          <p className="text-white/60 mt-2">
            Add extra coverage to maximize your visibility
          </p>
        </div>

        {/* Selected Package Summary */}
        <div className="card-featured rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/60 text-sm">Your Selection</p>
              <p className="text-[#f4d03f] font-bold text-xl">
                {packages.find(p => p.id === selectedPackage)?.name}
              </p>
            </div>
            <p className="text-white font-bold text-2xl">
              ${packages.find(p => p.id === selectedPackage)?.price?.toLocaleString()}
            </p>
          </div>
        </div>

        {/* À La Carte Upsell */}
        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <Plus className="w-5 h-5 text-[#f4d03f]" />
            Add À La Carte Options
          </h2>
          <p className="text-white/60 text-sm mb-6">
            Boost your exposure with additional promotional items
          </p>

          <div className="space-y-3">
            {alaCarteOptions.map((item) => (
              <div 
                key={item.name} 
                className="flex items-center justify-between p-4 bg-white/5 rounded-xl"
              >
                <div className="flex-1">
                  <p className="text-white font-medium">{item.name}</p>
                  <p className="text-[#f4d03f] text-sm">${item.price}</p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => toggleAlaCarteItem(item.name, -1)}
                    className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center text-white hover:bg-white/20 disabled:opacity-50"
                    disabled={!alaCarteItems[item.name]}
                  >
                    <Minus size={16} />
                  </button>
                  <span className="text-white font-bold w-8 text-center">
                    {alaCarteItems[item.name] || 0}
                  </span>
                  <button
                    onClick={() => toggleAlaCarteItem(item.name, 1)}
                    className="w-8 h-8 rounded-lg bg-[#f4d03f]/20 flex items-center justify-center text-[#f4d03f] hover:bg-[#f4d03f]/30"
                  >
                    <Plus size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Total */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/60">Total</p>
              {getSelectedItemsCount() > 0 && (
                <p className="text-white/50 text-sm">
                  Package + {getSelectedItemsCount()} add-on(s)
                </p>
              )}
            </div>
            <p className="text-[#f4d03f] font-bold text-3xl">
              ${calculateTotal().toLocaleString()}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-4">
          <Button
            variant="ghost"
            onClick={handleBack}
            className="text-white hover:bg-white/10"
          >
            <ArrowLeft className="mr-2" size={18} />
            Back
          </Button>
          <Button
            onClick={handleContinue}
            className="flex-1 btn-gold h-12"
          >
            Continue to Checkout
            <ArrowRight className="ml-2" size={18} />
          </Button>
        </div>
      </div>
    );
  }

  // Main Package Selection View
  return (
    <div className="space-y-8">
      <div className="text-center">
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Choose Your Package</h1>
        <p className="text-white/60 mt-2">
          Select a sponsorship tier or build your own with À La Carte options
        </p>
      </div>

      {/* Package Cards */}
      <div className="grid sm:grid-cols-2 gap-4">
        {packages.map((pkg) => {
          const Icon = packageIcons[pkg.id] || Award;
          return (
            <button
              key={pkg.id}
              onClick={() => setSelectedPackage(pkg.id === selectedPackage ? null : pkg.id)}
              className={`p-6 rounded-2xl text-left transition-all ${
                selectedPackage === pkg.id
                  ? 'bg-[#f4d03f]/10 border-2 border-[#f4d03f] ring-2 ring-[#f4d03f]/20'
                  : 'card-dark hover:border-[#f4d03f]/30'
              }`}
            >
              <div className="flex justify-between items-start mb-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                  selectedPackage === pkg.id ? 'bg-[#f4d03f] text-[#1a1a2e]' : 'bg-white/10 text-white'
                }`}>
                  <Icon size={24} />
                </div>
                {selectedPackage === pkg.id && (
                  <div className="w-6 h-6 rounded-full bg-[#f4d03f] flex items-center justify-center">
                    <Check size={14} className="text-[#1a1a2e]" />
                  </div>
                )}
              </div>
              <h3 className="text-xl font-bold text-white mb-1">{pkg.name}</h3>
              <p className="text-[#f4d03f] font-bold text-lg mb-2">{pkg.priceLabel}</p>
              <p className="text-white/50 text-sm mb-4">{pkg.description}</p>
              
              {pkg.features && (
                <ul className="space-y-1">
                  {pkg.features.slice(0, 3).map((feature, i) => (
                    <li key={i} className="text-white/60 text-xs flex items-start gap-2">
                      <Check size={12} className="text-[#f4d03f] mt-0.5 flex-shrink-0" />
                      {feature}
                    </li>
                  ))}
                  {pkg.features.length > 3 && (
                    <li className="text-white/40 text-xs">+ {pkg.features.length - 3} more benefits</li>
                  )}
                </ul>
              )}

              {pkg.spotsAvailable && (
                <Badge className="mt-4 bg-orange-500/20 text-orange-400 border-orange-500/30">
                  Only {pkg.spotsAvailable} spots available
                </Badge>
              )}
            </button>
          );
        })}
      </div>

      {/* Or Divider */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-[#f4d03f]/10" />
        </div>
        <div className="relative flex justify-center">
          <span className="px-4 bg-[#0f0f1a] text-white/40 text-sm">or build your own</span>
        </div>
      </div>

      {/* À La Carte Options */}
      <div className="card-dark rounded-2xl p-6">
        <h2 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
          <ShoppingCart className="w-5 h-5 text-[#f4d03f]" />
          À La Carte Options
        </h2>
        <p className="text-white/60 text-sm mb-4">
          Pick individual items or add them to a package for extra coverage
        </p>
        <p className="text-white/40 text-xs mb-6">
          {sponsorshipPackages.find(p => p.id === 'alacarte')?.note}
        </p>

        <div className="grid sm:grid-cols-2 gap-3">
          {alaCarteOptions.map((item) => (
            <div 
              key={item.name} 
              className="flex items-center justify-between p-3 bg-white/5 rounded-xl"
            >
              <div>
                <p className="text-white text-sm font-medium">{item.name}</p>
                <p className="text-[#f4d03f] text-sm">${item.price}</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => toggleAlaCarteItem(item.name, -1)}
                  className="w-7 h-7 rounded-lg bg-white/10 flex items-center justify-center text-white hover:bg-white/20 disabled:opacity-50"
                  disabled={!alaCarteItems[item.name]}
                >
                  <Minus size={14} />
                </button>
                <span className="text-white font-bold w-6 text-center text-sm">
                  {alaCarteItems[item.name] || 0}
                </span>
                <button
                  onClick={() => toggleAlaCarteItem(item.name, 1)}
                  className="w-7 h-7 rounded-lg bg-[#f4d03f]/20 flex items-center justify-center text-[#f4d03f] hover:bg-[#f4d03f]/30"
                >
                  <Plus size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Cart Summary */}
      {canContinue && (
        <div className="card-featured rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/60 text-sm">Your Selection</p>
              <div className="text-white">
                {selectedPackage && (
                  <span className="font-bold">{packages.find(p => p.id === selectedPackage)?.name}</span>
                )}
                {selectedPackage && getSelectedItemsCount() > 0 && ' + '}
                {getSelectedItemsCount() > 0 && (
                  <span>{getSelectedItemsCount()} à la carte item(s)</span>
                )}
              </div>
            </div>
            <p className="text-[#f4d03f] font-bold text-2xl">
              ${calculateTotal().toLocaleString()}
            </p>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-4">
        <Button
          variant="ghost"
          onClick={handleBack}
          className="text-white hover:bg-white/10"
        >
          <ArrowLeft className="mr-2" size={18} />
          Back
        </Button>
        <Button
          onClick={handleContinue}
          disabled={!canContinue}
          className="flex-1 btn-gold h-12"
        >
          Continue
          <ArrowRight className="ml-2" size={18} />
        </Button>
      </div>
    </div>
  );
};

export default PackageSelection;
