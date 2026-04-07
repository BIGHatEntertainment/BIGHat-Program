import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, ArrowLeft, Check, Plus, Minus, ShoppingCart, Sparkles, Crown, Star, Award, Upload, Image, CreditCard, Lock, Loader2 } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Checkbox } from '../../components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';
import { toast } from 'sonner';
import { useData } from '../../context/DataContext';
import { paymentsApi } from '../../services/api';
import { sponsorshipPackages } from '../../data/mock';

const Subscribe = ({ user }) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { purchaseSubscription, getActiveSubscription, userAssets, userProfile } = useData();
  
  const activeSubscription = getActiveSubscription();
  
  // Steps: 'packages' -> 'upsell' -> 'checkout'
  const [step, setStep] = useState('packages');
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [alaCarteItems, setAlaCarteItems] = useState({});
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreeContent, setAgreeContent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [checkingPayment, setCheckingPayment] = useState(false);
  const [discountCode, setDiscountCode] = useState('');
  const [discountApplied, setDiscountApplied] = useState(null);
  const [applyingDiscount, setApplyingDiscount] = useState(false);
  const [showUpgradeOptions, setShowUpgradeOptions] = useState(false);

  // Check for payment callback from Stripe
  useEffect(() => {
    const sessionId = searchParams.get('session_id');
    const success = searchParams.get('success');
    const upgrade = searchParams.get('upgrade');
    const downgrade = searchParams.get('downgrade');
    const cancelled = searchParams.get('cancelled');
    
    if (cancelled) {
      toast.info('Payment was cancelled');
      // Clear URL params
      navigate('/dashboard/subscribe', { replace: true });
      return;
    }
    
    if (sessionId && (success || upgrade || downgrade)) {
      // Verify payment status
      setCheckingPayment(true);
      paymentsApi.getCheckoutStatus(sessionId)
        .then(status => {
          if (status.payment_status === 'paid') {
            const action = upgrade ? 'upgrade' : (downgrade ? 'downgrade' : 'purchase');
            toast.success(`Payment successful! Your ${status.package_name} sponsorship is now active.`);
            
            // Update local state
            if (status.package_id && status.package_name) {
              purchaseSubscription({
                id: status.package_id,
                name: status.package_name,
                price: status.amount_total,
              });
            }
            
            // Clear URL params and go to dashboard
            navigate('/dashboard', { replace: true });
          } else {
            toast.error('Payment verification failed. Please contact support.');
            navigate('/dashboard/subscribe', { replace: true });
          }
        })
        .catch(err => {
          console.error('Payment verification error:', err);
          toast.error('Could not verify payment status');
          navigate('/dashboard/subscribe', { replace: true });
        })
        .finally(() => {
          setCheckingPayment(false);
        });
    }
  }, [searchParams, navigate, purchaseSubscription]);

  const packages = sponsorshipPackages.filter(p => p.id !== 'alacarte');
  const alaCarteOptions = sponsorshipPackages.find(p => p.id === 'alacarte')?.items || [];

  const packageIcons = {
    'bronze': Award,
    'bronze-single': Award,
    'bronze-all': Award,
    'silver': Star,
    'gold': Sparkles,
    'star-tier': Crown,
  };

  // Bronze location option state
  const [bronzeOption, setBronzeOption] = useState(null); // 'bronze-single' or 'bronze-all'

  const toggleAlaCarteItem = (itemId, delta) => {
    setAlaCarteItems(prev => {
      const current = prev[itemId] || 0;
      const newValue = Math.max(0, current + delta);
      if (newValue === 0) {
        const { [itemId]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [itemId]: newValue };
    });
  };

  // Calculate package price only (for discount calculation)
  const getPackagePrice = () => {
    if (!selectedPackage) return 0;
    const pkg = packages.find(p => p.id === selectedPackage);
    if (!pkg) return 0;
    
    // Handle bronze with location options
    if (pkg.hasLocationOptions && bronzeOption) {
      const option = pkg.locationOptions.find(o => o.id === bronzeOption);
      return option?.price || 0;
    }
    return pkg.price || 0;
  };

  // Calculate à la carte total only (not eligible for discounts)
  const getAlaCarteTotal = () => {
    let total = 0;
    Object.entries(alaCarteItems).forEach(([itemId, qty]) => {
      const item = alaCarteOptions.find(i => i.id === itemId);
      if (item) {
        const price = item.hasCapacityPricing ? item.capacityPricing[0].price : item.price;
        total += price * qty;
      }
    });
    return total;
  };

  const calculateSubtotal = () => {
    return getPackagePrice() + getAlaCarteTotal();
  };

  const calculateTotal = () => {
    const packagePrice = getPackagePrice();
    const alaCarteTotal = getAlaCarteTotal();
    
    // Handle discounts based on type
    let discountedPackagePrice = packagePrice;
    let discountedAlaCarteTotal = alaCarteTotal;
    
    if (discountApplied) {
      // Check if this is a fixed_price discount (like 99-SPONSOR-99)
      if (discountApplied.type === 'fixed_price') {
        // Fixed price discount applies to the restricted item(s) only
        if (discountApplied.restricted_to && discountApplied.restricted_to.length > 0) {
          // Calculate the discount for restricted à la carte items
          discountApplied.restricted_to.forEach(itemId => {
            if (alaCarteItems[itemId] && alaCarteItems[itemId] > 0) {
              const item = alaCarteOptions.find(i => i.id === itemId);
              if (item) {
                const originalPrice = item.hasCapacityPricing ? item.capacityPricing[0].price : item.price;
                const qty = alaCarteItems[itemId];
                // Replace the original price with the fixed price
                discountedAlaCarteTotal = discountedAlaCarteTotal - (originalPrice * qty) + (discountApplied.value * qty);
              }
            }
          });
        }
      } else if (discountApplied.appliesToAlaCarte) {
        // À la carte percentage discount
        if (discountApplied.type === 'percent') {
          discountedAlaCarteTotal = alaCarteTotal * (1 - discountApplied.value / 100);
        } else if (discountApplied.type === 'fixed') {
          discountedAlaCarteTotal = Math.max(0, alaCarteTotal - discountApplied.value);
        }
      } else {
        // Package percentage/fixed discount (original behavior)
        if (packagePrice > 0) {
          if (discountApplied.type === 'percent') {
            discountedPackagePrice = packagePrice * (1 - discountApplied.value / 100);
          } else if (discountApplied.type === 'fixed') {
            discountedPackagePrice = Math.max(0, packagePrice - discountApplied.value);
          }
        }
      }
    }
    
    return discountedPackagePrice + discountedAlaCarteTotal;
  };

  const getDiscountAmount = () => {
    if (!discountApplied) return 0;
    
    // Handle fixed_price discounts (like 99-SPONSOR-99)
    if (discountApplied.type === 'fixed_price') {
      if (discountApplied.restricted_to && discountApplied.restricted_to.length > 0) {
        let totalDiscount = 0;
        discountApplied.restricted_to.forEach(itemId => {
          if (alaCarteItems[itemId] && alaCarteItems[itemId] > 0) {
            const item = alaCarteOptions.find(i => i.id === itemId);
            if (item) {
              const originalPrice = item.hasCapacityPricing ? item.capacityPricing[0].price : item.price;
              const qty = alaCarteItems[itemId];
              // Discount is original price minus fixed price
              totalDiscount += (originalPrice - discountApplied.value) * qty;
            }
          }
        });
        return totalDiscount;
      }
    }
    
    // Handle à la carte percentage discounts
    if (discountApplied.appliesToAlaCarte) {
      const alaCarteTotal = getAlaCarteTotal();
      if (alaCarteTotal === 0) return 0;
      
      if (discountApplied.type === 'percent') {
        return alaCarteTotal * (discountApplied.value / 100);
      } else if (discountApplied.type === 'fixed') {
        return Math.min(alaCarteTotal, discountApplied.value);
      }
    }
    
    // Handle package discounts (original behavior)
    const packagePrice = getPackagePrice();
    if (packagePrice === 0) return 0;
    
    if (discountApplied.type === 'percent') {
      return packagePrice * (discountApplied.value / 100);
    } else if (discountApplied.type === 'fixed') {
      return Math.min(packagePrice, discountApplied.value);
    }
    return 0;
  };

  // Check if discount can be applied (either tier package or à la carte items selected)
  const canApplyDiscount = () => {
    // Allow discount if either a package is selected OR à la carte items are selected
    return (selectedPackage !== null && getPackagePrice() > 0) || getSelectedItemsCount() > 0;
  };
  
  // Check if this is an à la carte only purchase (no tier package)
  const isAlaCarteOnlyPurchase = () => {
    return !selectedPackage && getSelectedItemsCount() > 0;
  };

  const applyDiscountCode = async () => {
    if (!discountCode.trim()) {
      toast.error('Please enter a discount code');
      return;
    }
    
    // Check if either a tier package OR à la carte items are selected
    if (!canApplyDiscount()) {
      toast.error('Please select a package or à la carte items first');
      return;
    }
    
    setApplyingDiscount(true);
    try {
      // Determine which package ID to validate against
      // For à la carte only purchases, pass the first selected item
      let packageIdForValidation = null;
      if (selectedPackage) {
        packageIdForValidation = getCheckoutPackageId();
      } else if (getSelectedItemsCount() > 0) {
        // Get the first selected à la carte item ID
        const selectedItemIds = Object.keys(alaCarteItems).filter(id => alaCarteItems[id] > 0);
        if (selectedItemIds.length > 0) {
          packageIdForValidation = selectedItemIds[0];
        }
      }
      
      // Pass user email and package_id for validation
      const response = await paymentsApi.validateDiscountCode(
        discountCode.trim(), 
        userProfile?.email,
        packageIdForValidation
      );
      
      if (response.valid) {
        // Check if the discount is restricted to specific items
        if (response.restricted_to && response.restricted_to.length > 0) {
          // For restricted codes (like 99-SPONSOR-99), check if the restricted item is selected
          const hasRestrictedItem = response.restricted_to.some(itemId => {
            // Check if it's a selected package
            if (selectedPackage === itemId || getCheckoutPackageId() === itemId) return true;
            // Check if it's a selected à la carte item
            if (alaCarteItems[itemId] && alaCarteItems[itemId] > 0) return true;
            return false;
          });
          
          if (!hasRestrictedItem) {
            toast.error(`This discount code is only valid for: ${response.restricted_to.map(id => {
              const item = alaCarteOptions.find(i => i.id === id);
              return item ? item.name : id;
            }).join(', ')}`);
            setApplyingDiscount(false);
            return;
          }
        }
        
        setDiscountApplied({
          code: discountCode.trim().toUpperCase(),
          type: response.type,
          value: response.value,
          description: response.description,
          restricted_to: response.restricted_to || null,
          appliesToAlaCarte: isAlaCarteOnlyPurchase() || (response.restricted_to && response.restricted_to.some(id => id.startsWith('alacarte-')))
        });
        toast.success(`Discount applied: ${response.description}`);
      } else if (response.requires_zip) {
        // User needs to add zip code to profile
        toast.error(response.message || 'Please add your zip code to your profile to use AZ local discounts.');
      } else if (response.not_az_resident) {
        // User is not in Arizona
        toast.error(response.message || 'AZ local discounts are only available for Arizona residents.');
      } else {
        toast.error(response.message || 'Invalid discount code');
      }
    } catch (error) {
      console.error('Error validating discount:', error);
      toast.error('Failed to validate discount code. Please try again.');
    } finally {
      setApplyingDiscount(false);
    }
  };

  const removeDiscount = () => {
    setDiscountApplied(null);
    setDiscountCode('');
    toast.info('Discount removed');
  };

  const getSelectedItemsCount = () => {
    return Object.values(alaCarteItems).reduce((sum, qty) => sum + qty, 0);
  };

  // Get the actual package ID to send to Stripe
  const getCheckoutPackageId = () => {
    if (selectedPackage === 'bronze' && bronzeOption) {
      return bronzeOption;
    }
    return selectedPackage;
  };

  // Helper to get selected package price (handles bronze options)
  const getSelectedPackagePrice = () => {
    const pkg = packages.find(p => p.id === selectedPackage);
    if (!pkg) return 0;
    if (pkg.hasLocationOptions && bronzeOption) {
      const option = pkg.locationOptions.find(o => o.id === bronzeOption);
      return option?.price || 0;
    }
    return pkg.price || 0;
  };

  // Helper to get selected package display name
  const getSelectedPackageDisplayName = () => {
    const pkg = packages.find(p => p.id === selectedPackage);
    if (!pkg) return '';
    if (pkg.hasLocationOptions && bronzeOption) {
      const option = pkg.locationOptions.find(o => o.id === bronzeOption);
      return `${pkg.name} (${option?.name || ''})`;
    }
    return pkg.name;
  };

  const handleContinue = () => {
    // For bronze, ensure location option is selected
    if (selectedPackage === 'bronze' && !bronzeOption) {
      toast.error('Please select a Bronze tier option (Single Location or All Locations)');
      return;
    }
    
    if (step === 'packages' && selectedPackage) {
      setStep('upsell');
    } else if (step === 'packages' && getSelectedItemsCount() > 0) {
      // Allow à la carte only purchase
      setStep('checkout');
    } else if (step === 'upsell') {
      setStep('checkout');
    }
  };

  const handleBack = () => {
    if (step === 'upsell') setStep('packages');
    else if (step === 'checkout') setStep(selectedPackage ? 'upsell' : 'packages');
  };

  const handlePayment = async () => {
    if (!agreeTerms || !agreeContent) {
      toast.error('Please agree to the terms and content guidelines');
      return;
    }

    // Allow either a package or à la carte items
    if (!selectedPackage && getSelectedItemsCount() === 0) {
      toast.error('Please select a sponsorship package or à la carte items');
      return;
    }

    // For bronze, ensure option is selected
    if (selectedPackage === 'bronze' && !bronzeOption) {
      toast.error('Please select a Bronze tier option');
      return;
    }

    setLoading(true);
    
    try {
      // Get user email from userProfile or fallback to user prop
      const userEmail = userProfile?.email || user?.email;
      if (!userEmail) {
        toast.error('Please log in to purchase a subscription');
        setLoading(false);
        return;
      }

      // Determine which package/item ID to send for checkout
      let checkoutPackageId;
      
      if (selectedPackage) {
        // Tier package selected (with optional à la carte add-ons)
        checkoutPackageId = getCheckoutPackageId();
      } else {
        // À la carte only purchase - get the first selected item
        const selectedItemIds = Object.keys(alaCarteItems).filter(id => alaCarteItems[id] > 0);
        if (selectedItemIds.length === 0) {
          toast.error('Please select at least one item');
          setLoading(false);
          return;
        }
        checkoutPackageId = selectedItemIds[0]; // For now, handle single item
        // TODO: Handle multiple à la carte items in a single checkout
      }
      
      // Create Stripe checkout session with discount code if applied
      console.log('[Checkout] Creating session with:', {
        packageId: checkoutPackageId,
        email: userEmail,
        discountCode: discountApplied?.code || null
      });
      
      const response = await paymentsApi.createCheckoutSession(
        checkoutPackageId, 
        userEmail, 
        discountApplied?.code || null
      );
      
      console.log('[Checkout] Response received:', response);
      
      if (response && response.url) {
        // Redirect to Stripe Checkout
        console.log('[Checkout] Redirecting to:', response.url);
        window.location.href = response.url;
      } else {
        console.error('[Checkout] Invalid response - no URL:', response);
        throw new Error('No checkout URL received from server');
      }
    } catch (error) {
      console.error('Payment error:', error);
      // Show the actual error message from the API
      let errorMessage = 'Failed to initiate payment. Please try again.';
      if (error.message) {
        errorMessage = error.message;
      }
      toast.error(errorMessage);
      
      // Log additional details for debugging
      console.error('Checkout details:', {
        selectedPackage,
        packageId: selectedPackage ? getCheckoutPackageId() : Object.keys(alaCarteItems).filter(id => alaCarteItems[id] > 0)[0],
        userEmail: userProfile?.email || user?.email,
        userFromProp: user?.email,
        userFromProfile: userProfile?.email,
        discountCode: discountApplied?.code,
        alaCarteItems: alaCarteItems
      });
      setLoading(false);
    }
  };

  // Handle upgrade/downgrade for existing subscribers
  const handleUpgradeDowngrade = async (newPackageId) => {
    setLoading(true);
    
    try {
      const userEmail = userProfile?.email;
      if (!userEmail) {
        toast.error('Please log in to change your subscription');
        setLoading(false);
        return;
      }

      const response = await paymentsApi.upgradeDowngrade(newPackageId, userEmail);
      
      if (response.url) {
        window.location.href = response.url;
      } else {
        throw new Error('No checkout URL received');
      }
    } catch (error) {
      console.error('Upgrade/downgrade error:', error);
      toast.error(error.message || 'Failed to change subscription. Please try again.');
      setLoading(false);
    }
  };

  // Handle subscription cancellation
  const handleCancelSubscription = async () => {
    if (!confirm('Are you sure you want to cancel your subscription? This action cannot be undone.')) {
      return;
    }
    
    setLoading(true);
    
    try {
      const userEmail = userProfile?.email;
      await paymentsApi.cancelSubscription(userEmail);
      toast.success('Your subscription has been cancelled.');
      navigate('/dashboard');
    } catch (error) {
      console.error('Cancel error:', error);
      toast.error(error.message || 'Failed to cancel subscription');
    } finally {
      setLoading(false);
    }
  };

  // Show loading state while checking payment
  if (checkingPayment) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <Loader2 className="w-12 h-12 text-[#f4d03f] animate-spin" />
        <p className="text-white text-lg">Verifying your payment...</p>
        <p className="text-white/60 text-sm">Please wait while we confirm your subscription.</p>
      </div>
    );
  }

  const canContinue = selectedPackage || getSelectedItemsCount() > 0;

  // If already subscribed, show management view
  if (activeSubscription) {
    // Special view for Venue Sponsors
    if (activeSubscription.isVenueSponsor) {
      return (
        <div className="space-y-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white">Venue Sponsor</h1>
            <p className="text-white/60 mt-1">Your venue sponsorship benefits</p>
          </div>

          <div className="bg-purple-500/10 border border-purple-500/20 rounded-2xl p-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <p className="text-purple-300 text-sm">Your Status</p>
                <p className="text-purple-400 font-bold text-2xl flex items-center gap-2">
                  🏠 Venue Sponsor
                </p>
                <p className="text-white/50 text-sm mt-1">
                  Thank you for hosting BIG Hat Trivia events!
                </p>
              </div>
              <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30">Active</Badge>
            </div>
          </div>

          <div className="card-dark rounded-2xl p-6">
            <h2 className="text-lg font-bold text-white mb-4">Your Benefits</h2>
            <ul className="space-y-3">
              <li className="flex items-center gap-3 text-white/70">
                <Check size={16} className="text-purple-400" />
                All Star Tier sponsorship benefits included
              </li>
              <li className="flex items-center gap-3 text-white/70">
                <Check size={16} className="text-purple-400" />
                Upload 16:9 wide format images for projector displays
              </li>
              <li className="flex items-center gap-3 text-white/70">
                <Check size={16} className="text-purple-400" />
                Upload 1:1 square images for logo displays
              </li>
              <li className="flex items-center gap-3 text-white/70">
                <Check size={16} className="text-purple-400" />
                Display special venue messages during events
              </li>
              <li className="flex items-center gap-3 text-white/70">
                <Check size={16} className="text-purple-400" />
                Complimentary - no monthly fees
              </li>
            </ul>
          </div>

          <div className="card-dark rounded-2xl p-6 text-center">
            <p className="text-white/60 text-sm">
              Need to update your venue information or have questions?
            </p>
            <p className="text-white/40 text-xs mt-1">
              Contact us at support@bighat.live
            </p>
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Manage Subscription</h1>
          <p className="text-white/60 mt-1">View and manage your sponsorship plan</p>
        </div>

        <div className="card-featured rounded-2xl p-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div>
              <p className="text-white/60 text-sm">Current Plan</p>
              <p className="text-[#f4d03f] font-bold text-2xl">{activeSubscription.packageName}</p>
              <p className="text-white/50 text-sm mt-1">
                Active: {activeSubscription.startDate} - {activeSubscription.endDate}
              </p>
            </div>
            <Badge className="bg-green-500/20 text-green-400 border-green-500/30">Active</Badge>
          </div>
        </div>

        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4">Add More Coverage</h2>
          <p className="text-white/60 text-sm mb-6">Boost your exposure with additional promotional items</p>
          
          <div className="grid sm:grid-cols-2 gap-3">
            {alaCarteOptions.map((item) => (
              <div key={item.name} className="flex items-center justify-between p-3 bg-white/5 rounded-xl">
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

          {getSelectedItemsCount() > 0 && (
            <div className="mt-6 pt-4 border-t border-[#f4d03f]/10">
              <div className="flex justify-between items-center">
                <p className="text-white">Additional Items: {getSelectedItemsCount()}</p>
                <p className="text-[#f4d03f] font-bold text-xl">
                  +${Object.entries(alaCarteItems).reduce((sum, [name, qty]) => {
                    const item = alaCarteOptions.find(i => i.name === name);
                    return sum + (item?.price || 0) * qty;
                  }, 0).toLocaleString()}
                </p>
              </div>
              <Button className="w-full btn-gold mt-4">
                Add to Subscription
              </Button>
            </div>
          )}
        </div>

        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-2">Upgrade Plan</h2>
          <p className="text-white/60 text-sm mb-4">Want more exposure? Upgrade to a higher tier.</p>
          <Button 
            variant="outline" 
            className="btn-outline-gold"
            onClick={() => setShowUpgradeOptions(true)}
          >
            View Upgrade Options
          </Button>
        </div>

        {/* Upgrade Options Dialog */}
        <Dialog open={showUpgradeOptions} onOpenChange={setShowUpgradeOptions}>
          <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-2xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-white text-xl">Upgrade Your Sponsorship</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <p className="text-white/60 text-sm">Choose a higher tier to increase your exposure and benefits.</p>
              
              {/* Show packages higher than current */}
              {packages
                .filter(pkg => !pkg.standalone && pkg.id !== 'alacarte')
                .filter(pkg => {
                  // Include bronze in the tier order using its actual package ID
                  const tierOrder = ['bronze', 'silver', 'gold', 'star-tier'];
                  const currentPackageId = activeSubscription?.packageId;
                  
                  // If user has an à la carte item only (no tier), show all packages
                  if (!currentPackageId || currentPackageId.startsWith('alacarte-')) {
                    return true;
                  }
                  
                  // Map bronze-single/bronze-all to 'bronze' for comparison
                  const normalizedCurrent = currentPackageId.startsWith('bronze') ? 'bronze' : currentPackageId;
                  const currentIndex = tierOrder.indexOf(normalizedCurrent);
                  const pkgIndex = tierOrder.indexOf(pkg.id);
                  
                  // Show packages higher than current tier
                  return pkgIndex > currentIndex;
                })
                .map(pkg => {
                  const Icon = packageIcons[pkg.id] || Star;
                  return (
                    <div 
                      key={pkg.id}
                      className="p-4 bg-white/5 rounded-xl border border-white/10 hover:border-[#f4d03f]/30 transition-colors cursor-pointer"
                      onClick={async () => {
                        setShowUpgradeOptions(false);
                        setLoading(true);
                        try {
                          const response = await paymentsApi.createCheckoutSession({
                            package_id: pkg.id,
                            user_email: userProfile?.email,
                            origin_url: window.location.origin
                          });
                          if (response.url) {
                            window.location.href = response.url;
                          }
                        } catch (error) {
                          toast.error('Failed to start upgrade process');
                          setLoading(false);
                        }
                      }}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                            pkg.id === 'star-tier' ? 'bg-purple-500/20' :
                            pkg.id === 'gold' ? 'bg-yellow-500/20' :
                            pkg.id === 'silver' ? 'bg-gray-400/20' : 'bg-orange-500/20'
                          }`}>
                            <Icon className={`w-5 h-5 ${
                              pkg.id === 'star-tier' ? 'text-purple-400' :
                              pkg.id === 'gold' ? 'text-yellow-400' :
                              pkg.id === 'silver' ? 'text-gray-300' : 'text-orange-400'
                            }`} />
                          </div>
                          <div>
                            <p className="text-white font-bold">{pkg.name}</p>
                            <p className="text-white/50 text-xs">{pkg.description}</p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-[#f4d03f] font-bold">${pkg.price}/mo</p>
                          <ArrowRight className="w-4 h-4 text-white/40 ml-auto mt-1" />
                        </div>
                      </div>
                    </div>
                  );
                })}
              
              {packages
                .filter(pkg => !pkg.standalone && pkg.id !== 'alacarte')
                .filter(pkg => {
                  // Include bronze in the tier order using its actual package ID
                  const tierOrder = ['bronze', 'silver', 'gold', 'star-tier'];
                  const currentPackageId = activeSubscription?.packageId;
                  
                  // If user has an à la carte item only (no tier), show all packages
                  if (!currentPackageId || currentPackageId.startsWith('alacarte-')) {
                    return true;
                  }
                  
                  // Map bronze-single/bronze-all to 'bronze' for comparison
                  const normalizedCurrent = currentPackageId.startsWith('bronze') ? 'bronze' : currentPackageId;
                  const currentIndex = tierOrder.indexOf(normalizedCurrent);
                  const pkgIndex = tierOrder.indexOf(pkg.id);
                  
                  // Show packages higher than current tier
                  return pkgIndex > currentIndex;
                }).length === 0 && (
                <div className="text-center py-8">
                  <Crown className="w-12 h-12 text-[#f4d03f] mx-auto mb-3" />
                  <p className="text-white font-bold">You&apos;re at the highest tier!</p>
                  <p className="text-white/50 text-sm">You already have maximum benefits.</p>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // STEP: Checkout
  if (step === 'checkout') {
    const selectedPkg = packages.find(p => p.id === selectedPackage);
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Complete Your Order</h1>
          <p className="text-white/60 mt-1">Review your selection and complete payment</p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8">
          {/* Order Summary */}
          <div className="space-y-6">
            <div className="card-dark rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <ShoppingCart className="w-5 h-5 text-[#f4d03f]" />
                Order Summary
              </h2>

              {selectedPkg && (
                <div className="p-4 bg-white/5 rounded-xl mb-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <p className="text-white font-bold">{getSelectedPackageDisplayName()}</p>
                      <p className="text-white/50 text-sm">{selectedPkg.description}</p>
                    </div>
                    <p className="text-[#f4d03f] font-bold">${getSelectedPackagePrice().toLocaleString()}</p>
                  </div>
                </div>
              )}

              {getSelectedItemsCount() > 0 && (
                <div className="space-y-2">
                  <p className="text-white/60 text-sm font-medium">À La Carte Items</p>
                  {Object.entries(alaCarteItems).map(([itemId, qty]) => {
                    const item = alaCarteOptions.find(i => i.id === itemId);
                    if (!item) return null;
                    const itemPrice = item.hasCapacityPricing ? item.capacityPricing[0].price : item.price;
                    return (
                      <div key={itemId} className="flex justify-between items-center p-3 bg-white/5 rounded-lg">
                        <div>
                          <p className="text-white text-sm">{item.name}</p>
                          <p className="text-white/50 text-xs">Qty: {qty}</p>
                          {item.hasCapacityPricing && (
                            <p className="text-white/40 text-xs">Base price - final price depends on venue capacity</p>
                          )}
                        </div>
                        <p className="text-white font-medium">${(itemPrice * qty).toLocaleString()}</p>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Discount Code Section - Show for packages OR à la carte items */}
              <div className="border-t border-[#f4d03f]/10 my-4" />
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-white/60 text-sm font-medium">Discount Code</p>
                  {!canApplyDiscount() && (
                    <p className="text-white/40 text-xs">Select items first</p>
                  )}
                </div>
                {discountApplied ? (
                  <div className="flex items-center justify-between p-3 bg-green-500/10 rounded-lg border border-green-500/30">
                    <div className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-green-400" />
                      <div>
                        <p className="text-green-400 font-medium text-sm">{discountApplied.code}</p>
                        <p className="text-green-400/70 text-xs">{discountApplied.description}</p>
                      </div>
                    </div>
                    <button 
                      onClick={removeDiscount}
                      className="text-white/50 hover:text-white text-sm underline"
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={discountCode}
                      onChange={(e) => setDiscountCode(e.target.value.toUpperCase())}
                      placeholder={canApplyDiscount() ? "Enter discount code" : "Select items first"}
                      disabled={!canApplyDiscount()}
                      className={`flex-1 px-3 py-2 bg-white/5 border border-[#f4d03f]/20 rounded-lg text-white placeholder:text-white/30 text-sm focus:outline-none focus:border-[#f4d03f]/50 ${!canApplyDiscount() ? 'opacity-50 cursor-not-allowed' : ''}`}
                    />
                    <Button
                      onClick={applyDiscountCode}
                      disabled={applyingDiscount || !discountCode.trim() || !canApplyDiscount()}
                      className="btn-outline-gold px-4"
                    >
                      {applyingDiscount ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Apply'}
                    </Button>
                  </div>
                )}
              </div>

              {/* Totals */}
              <div className="border-t border-[#f4d03f]/10 my-4" />
              <div className="space-y-2">
                {selectedPackage && (
                  <div className="flex justify-between items-center text-sm">
                    <p className="text-white/60">Package ({getSelectedPackageDisplayName()})</p>
                    <p className="text-white">${getPackagePrice().toLocaleString()}</p>
                  </div>
                )}
                {getSelectedItemsCount() > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <p className="text-white/60">À La Carte Items</p>
                    <p className="text-white">${getAlaCarteTotal().toLocaleString()}</p>
                  </div>
                )}
                {discountApplied && getDiscountAmount() > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <p className="text-green-400">
                      Discount ({discountApplied.code})
                      {discountApplied.appliesToAlaCarte || discountApplied.type === 'fixed_price' 
                        ? ' - À la carte' 
                        : selectedPackage ? ' - Package' : ''}
                    </p>
                    <p className="text-green-400">-${getDiscountAmount().toLocaleString()}</p>
                  </div>
                )}
                <div className="border-t border-white/10 my-2" />
                <div className="flex justify-between items-center pt-1">
                  <p className="text-white font-bold">Total</p>
                  <p className="text-[#f4d03f] font-bold text-2xl">${calculateTotal().toLocaleString()}</p>
                </div>
              </div>
              <p className="text-white/40 text-xs mt-2">Billed monthly • Cancel anytime</p>
            </div>

            <div className="card-dark rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <Image className="w-5 h-5 text-[#f4d03f]" />
                Your Assets
              </h2>
              {userAssets.length > 0 ? (
                <div className="flex items-center gap-3">
                  <Check className="w-5 h-5 text-green-400" />
                  <p className="text-white">{userAssets.length} image(s) uploaded</p>
                </div>
              ) : (
                <div className="flex items-start gap-3 p-3 bg-orange-500/10 rounded-lg">
                  <Upload className="w-5 h-5 text-orange-400 flex-shrink-0" />
                  <div>
                    <p className="text-white text-sm">No assets uploaded yet</p>
                    <p className="text-white/50 text-xs">You can upload assets from &quot;Upload Media&quot; after checkout.</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Payment */}
          <div className="space-y-6">
            <div className="card-dark rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                <CreditCard className="w-5 h-5 text-[#f4d03f]" />
                Payment Details
              </h2>
              <div className="p-6 bg-white/5 rounded-xl border border-[#f4d03f]/20">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-[#635bff]/20 rounded-lg flex items-center justify-center">
                      <svg viewBox="0 0 24 24" className="w-6 h-6 text-[#635bff]" fill="currentColor">
                        <path d="M13.976 9.15c-2.172-.806-3.356-1.426-3.356-2.409 0-.831.683-1.305 1.901-1.305 2.227 0 4.515.858 6.09 1.631l.89-5.494C18.252.975 15.697 0 12.165 0 9.667 0 7.589.654 6.104 1.872 4.56 3.147 3.757 4.992 3.757 7.218c0 4.039 2.467 5.76 6.476 7.219 2.585.92 3.445 1.574 3.445 2.583 0 .98-.84 1.545-2.354 1.545-1.875 0-4.965-.921-6.99-2.109l-.9 5.555C5.175 22.99 8.385 24 11.714 24c2.641 0 4.843-.624 6.328-1.813 1.664-1.305 2.525-3.236 2.525-5.732 0-4.128-2.524-5.851-6.591-7.305z"/>
                      </svg>
                    </div>
                    <div>
                      <p className="text-white font-medium">Secure Stripe Checkout</p>
                      <p className="text-white/50 text-sm">You&apos;ll be redirected to complete payment</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <img src="https://js.stripe.com/v3/fingerprinted/img/visa-729c05c240c4bdb47b03ac81d9945bfe.svg" alt="Visa" className="h-6" />
                    <img src="https://js.stripe.com/v3/fingerprinted/img/mastercard-4d8844094130711885b5e41b28c9848f.svg" alt="Mastercard" className="h-6" />
                    <img src="https://js.stripe.com/v3/fingerprinted/img/amex-a49b82f46c5cd6a96a6e418a6ca1717c.svg" alt="Amex" className="h-6" />
                  </div>
                </div>
              </div>
              <p className="text-white/40 text-xs mt-4 text-center">🔒 Your payment information is encrypted and secure</p>
            </div>

            <div className="card-dark rounded-2xl p-6">
              <h2 className="text-lg font-bold text-white mb-4">Terms & Conditions</h2>
              <div className="space-y-4">
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="terms"
                    checked={agreeTerms}
                    onCheckedChange={setAgreeTerms}
                    className="mt-1 border-[#f4d03f]/30 data-[state=checked]:bg-[#f4d03f] data-[state=checked]:border-[#f4d03f]"
                  />
                  <label htmlFor="terms" className="text-white/70 text-sm cursor-pointer">
                    I agree to the Terms of Service and Privacy Policy
                  </label>
                </div>
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="content"
                    checked={agreeContent}
                    onCheckedChange={setAgreeContent}
                    className="mt-1 border-[#f4d03f]/30 data-[state=checked]:bg-[#f4d03f] data-[state=checked]:border-[#f4d03f]"
                  />
                  <label htmlFor="content" className="text-white/70 text-sm cursor-pointer">
                    I confirm my media assets comply with the content guidelines
                  </label>
                </div>
              </div>
            </div>

            <div className="flex gap-4">
              <Button variant="ghost" onClick={handleBack} className="text-white hover:bg-white/10">
                <ArrowLeft className="mr-2" size={18} /> Back
              </Button>
              <Button
                onClick={handlePayment}
                disabled={loading || !agreeTerms || !agreeContent}
                className="flex-1 btn-gold h-12"
              >
                {loading ? 'Processing...' : `Complete Order - $${calculateTotal().toLocaleString()}`}
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // STEP: Upsell (after package selection)
  if (step === 'upsell') {
    return (
      <div className="space-y-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Enhance Your Package</h1>
          <p className="text-white/60 mt-1">Add extra coverage to maximize your visibility</p>
        </div>

        <div className="card-featured rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/60 text-sm">Your Selection</p>
              <p className="text-[#f4d03f] font-bold text-xl">
                {getSelectedPackageDisplayName()}
              </p>
            </div>
            <p className="text-white font-bold text-2xl">
              ${getSelectedPackagePrice().toLocaleString()}
            </p>
          </div>
        </div>

        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <Plus className="w-5 h-5 text-[#f4d03f]" />
            Add À La Carte Options
          </h2>
          <p className="text-white/60 text-sm mb-6">Boost your exposure with additional promotional items</p>

          <div className="space-y-3">
            {alaCarteOptions.map((item) => (
              <div key={item.name} className="flex items-center justify-between p-4 bg-white/5 rounded-xl">
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

        <div className="card-dark rounded-2xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/60">Total</p>
              {getSelectedItemsCount() > 0 && (
                <p className="text-white/50 text-sm">Package + {getSelectedItemsCount()} add-on(s)</p>
              )}
            </div>
            <p className="text-[#f4d03f] font-bold text-3xl">${calculateTotal().toLocaleString()}</p>
          </div>
        </div>

        <div className="flex gap-4">
          <Button variant="ghost" onClick={handleBack} className="text-white hover:bg-white/10">
            <ArrowLeft className="mr-2" size={18} /> Back
          </Button>
          <Button onClick={handleContinue} className="flex-1 btn-gold h-12">
            Continue to Checkout <ArrowRight className="ml-2" size={18} />
          </Button>
        </div>
      </div>
    );
  }

  // STEP: Package Selection (default)
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Choose Your Package</h1>
        <p className="text-white/60 mt-1">Select a sponsorship tier or build your own with À La Carte options</p>
      </div>

      {/* Package Cards */}
      <div className="grid sm:grid-cols-2 gap-4">
        {packages.map((pkg) => {
          const Icon = packageIcons[pkg.id] || Award;
          const isSelected = selectedPackage === pkg.id;
          // Get feature text (handle both string and object formats)
          const getFeatureText = (feature) => typeof feature === 'string' ? feature : feature.text;
          
          return (
            <div
              key={pkg.id}
              className={`p-6 rounded-2xl text-left transition-all ${
                isSelected
                  ? 'bg-[#f4d03f]/10 border-2 border-[#f4d03f] ring-2 ring-[#f4d03f]/20'
                  : 'card-dark hover:border-[#f4d03f]/30 cursor-pointer'
              }`}
              onClick={() => {
                if (!isSelected) {
                  setSelectedPackage(pkg.id);
                  // Reset bronze option when switching packages
                  if (pkg.id !== 'bronze') setBronzeOption(null);
                }
              }}
            >
              <div className="flex justify-between items-start mb-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                  isSelected ? 'bg-[#f4d03f] text-[#1a1a2e]' : 'bg-white/10 text-white'
                }`}>
                  <Icon size={24} />
                </div>
                {isSelected && (
                  <button 
                    onClick={(e) => { e.stopPropagation(); setSelectedPackage(null); setBronzeOption(null); }}
                    className="w-6 h-6 rounded-full bg-[#f4d03f] flex items-center justify-center hover:bg-[#f4d03f]/80"
                  >
                    <Check size={14} className="text-[#1a1a2e]" />
                  </button>
                )}
              </div>
              <h3 className="text-xl font-bold text-white mb-1">{pkg.name}</h3>
              <p className="text-[#f4d03f] font-bold text-lg mb-2">{pkg.priceLabel}</p>
              <p className="text-white/50 text-sm mb-4">{pkg.description}</p>
              
              {/* Bronze Location Options - Show when Bronze is selected */}
              {pkg.hasLocationOptions && isSelected && (
                <div className="mb-4 p-3 bg-white/5 rounded-xl space-y-2">
                  <p className="text-white/70 text-sm font-medium mb-2">Choose your coverage:</p>
                  {pkg.locationOptions.map((option) => (
                    <label
                      key={option.id}
                      className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-all ${
                        bronzeOption === option.id 
                          ? 'bg-[#f4d03f]/20 border border-[#f4d03f]/50' 
                          : 'bg-white/5 hover:bg-white/10 border border-transparent'
                      }`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center gap-3">
                        <input
                          type="radio"
                          name="bronzeOption"
                          value={option.id}
                          checked={bronzeOption === option.id}
                          onChange={() => setBronzeOption(option.id)}
                          className="w-4 h-4 accent-[#f4d03f]"
                        />
                        <span className="text-white text-sm">{option.name}</span>
                      </div>
                      <span className="text-[#f4d03f] font-bold">${option.price}</span>
                    </label>
                  ))}
                </div>
              )}
              
              {pkg.features && (
                <ul className="space-y-1">
                  {pkg.features.slice(0, 3).map((feature, i) => (
                    <li key={i} className="text-white/60 text-xs flex items-start gap-2">
                      <Check size={12} className="text-[#f4d03f] mt-0.5 flex-shrink-0" />
                      {getFeatureText(feature)}
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
            </div>
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

      {/* À La Carte */}
      <div className="card-dark rounded-2xl p-6">
        <h2 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
          <ShoppingCart className="w-5 h-5 text-[#f4d03f]" />
          À La Carte Options
        </h2>
        <p className="text-white/60 text-sm mb-4">Pick individual items or add them to a package</p>
        <p className="text-white/40 text-xs mb-6">
          {sponsorshipPackages.find(p => p.id === 'alacarte')?.note}
        </p>

        <div className="grid sm:grid-cols-2 gap-3">
          {alaCarteOptions.map((item) => (
            <div key={item.id} className="p-3 bg-white/5 rounded-xl">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <p className="text-white text-sm font-medium">{item.name}</p>
                  {item.hasCapacityPricing ? (
                    <p className="text-[#f4d03f] text-sm">
                      ${item.capacityPricing[0].price} <span className="text-white/50">({item.capacityPricing[0].tier})</span>
                      {' / '}
                      ${item.capacityPricing[1].price} <span className="text-white/50">({item.capacityPricing[1].tier})</span>
                    </p>
                  ) : (
                    <p className="text-[#f4d03f] text-sm">${item.price}</p>
                  )}
                  {item.duration && (
                    <p className="text-white/40 text-xs">{item.duration}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => toggleAlaCarteItem(item.id, -1)}
                    className="w-7 h-7 rounded-lg bg-white/10 flex items-center justify-center text-white hover:bg-white/20 disabled:opacity-50"
                    disabled={!alaCarteItems[item.id]}
                  >
                    <Minus size={14} />
                  </button>
                  <span className="text-white font-bold w-6 text-center text-sm">
                    {alaCarteItems[item.id] || 0}
                  </span>
                  <button
                    onClick={() => toggleAlaCarteItem(item.id, 1)}
                    className="w-7 h-7 rounded-lg bg-[#f4d03f]/20 flex items-center justify-center text-[#f4d03f] hover:bg-[#f4d03f]/30"
                  >
                    <Plus size={14} />
                  </button>
                </div>
              </div>
              {item.description && (
                <p className="text-white/50 text-xs">{item.description}</p>
              )}
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
                  <span className="font-bold">{getSelectedPackageDisplayName()}</span>
                )}
                {selectedPackage && getSelectedItemsCount() > 0 && ' + '}
                {getSelectedItemsCount() > 0 && (
                  <span>{getSelectedItemsCount()} à la carte item(s)</span>
                )}
              </div>
            </div>
            <p className="text-[#f4d03f] font-bold text-2xl">${calculateTotal().toLocaleString()}</p>
          </div>
        </div>
      )}

      {/* Standalone À la carte hint */}
      {!selectedPackage && getSelectedItemsCount() > 0 && (
        <p className="text-center text-white/50 text-sm">
          You can purchase à la carte items without a main package!
        </p>
      )}

      {/* Continue Button */}
      <Button
        onClick={handleContinue}
        disabled={!canContinue}
        className="w-full btn-gold h-12"
      >
        Continue <ArrowRight className="ml-2" size={18} />
      </Button>
    </div>
  );
};

export default Subscribe;
