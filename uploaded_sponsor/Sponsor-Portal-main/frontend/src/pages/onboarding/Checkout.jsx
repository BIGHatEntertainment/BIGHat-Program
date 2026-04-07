import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, CreditCard, Check, Lock, ShoppingCart, Image, AlertTriangle } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Checkbox } from '../../components/ui/checkbox';
import { toast } from 'sonner';
import { useData } from '../../context/DataContext';

const Checkout = () => {
  const navigate = useNavigate();
  const { purchaseSubscription, userAssets } = useData();
  const [loading, setLoading] = useState(false);
  const [selection, setSelection] = useState(null);
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreeContent, setAgreeContent] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem('sponsorship_selection');
    if (saved) {
      setSelection(JSON.parse(saved));
    } else {
      navigate('/onboarding/packages');
    }
  }, [navigate]);

  const handlePayment = async () => {
    if (!agreeTerms || !agreeContent) {
      toast.error('Please agree to the terms and content guidelines');
      return;
    }

    setLoading(true);

    // Simulate payment processing
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Save subscription if a package was selected
    if (selection?.package) {
      purchaseSubscription({
        id: selection.package.id,
        name: selection.package.name,
        price: selection.total,
      });
    }

    // Clear selection from localStorage
    localStorage.removeItem('sponsorship_selection');

    toast.success('Payment successful! Your sponsorship is pending admin review.');
    
    // Navigate to dashboard
    navigate('/dashboard');
    setLoading(false);
  };

  if (!selection) {
    return (
      <div className="text-center py-12">
        <p className="text-white/60">Loading...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Complete Your Order</h1>
        <p className="text-white/60 mt-2">
          Review your selection and complete payment
        </p>
      </div>

      <div className="grid lg:grid-cols-2 gap-8">
        {/* Order Summary */}
        <div className="space-y-6">
          <div className="card-dark rounded-2xl p-6">
            <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
              <ShoppingCart className="w-5 h-5 text-[#f4d03f]" />
              Order Summary
            </h2>

            {/* Package */}
            {selection.package && (
              <div className="p-4 bg-white/5 rounded-xl mb-4">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="text-white font-bold">{selection.package.name}</p>
                    <p className="text-white/50 text-sm">{selection.package.description}</p>
                  </div>
                  <p className="text-[#f4d03f] font-bold">${selection.package.price?.toLocaleString()}</p>
                </div>
              </div>
            )}

            {/* À La Carte Items */}
            {selection.alaCarteItems?.length > 0 && (
              <div className="space-y-2">
                <p className="text-white/60 text-sm font-medium">À La Carte Items</p>
                {selection.alaCarteItems.map((item, index) => (
                  <div key={index} className="flex justify-between items-center p-3 bg-white/5 rounded-lg">
                    <div>
                      <p className="text-white text-sm">{item.name}</p>
                      <p className="text-white/50 text-xs">Qty: {item.quantity}</p>
                    </div>
                    <p className="text-white font-medium">${(item.price * item.quantity).toLocaleString()}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Divider */}
            <div className="border-t border-[#f4d03f]/10 my-4" />

            {/* Total */}
            <div className="flex justify-between items-center">
              <p className="text-white font-bold">Total</p>
              <p className="text-[#f4d03f] font-bold text-2xl">${selection.total?.toLocaleString()}</p>
            </div>

            <p className="text-white/40 text-xs mt-2">Billed monthly • Cancel anytime</p>
          </div>

          {/* Assets Summary */}
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
                <AlertTriangle className="w-5 h-5 text-orange-400 flex-shrink-0" />
                <div>
                  <p className="text-white text-sm">No assets uploaded</p>
                  <p className="text-white/50 text-xs">You can upload assets from your dashboard after checkout.</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Payment Form */}
        <div className="space-y-6">
          <div className="card-dark rounded-2xl p-6">
            <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
              <CreditCard className="w-5 h-5 text-[#f4d03f]" />
              Payment Details
            </h2>

            {/* Mock Payment Form */}
            <div className="p-6 bg-white/5 rounded-xl border border-dashed border-[#f4d03f]/30">
              <div className="text-center">
                <Lock className="w-8 h-8 text-[#f4d03f]/50 mx-auto mb-3" />
                <p className="text-white font-medium">Stripe Payment Integration</p>
                <p className="text-white/50 text-sm mt-1">Coming soon - Payment will be processed securely via Stripe</p>
              </div>
            </div>

            <p className="text-white/40 text-xs mt-4 text-center">
              🔒 Your payment information is encrypted and secure
            </p>
          </div>

          {/* Terms & Conditions */}
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
                  I agree to the <a href="/terms" className="text-[#f4d03f] hover:underline">Terms of Service</a> and <a href="/privacy" className="text-[#f4d03f] hover:underline">Privacy Policy</a>
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
                  I confirm my media assets comply with the <a href="/content-guidelines" className="text-[#f4d03f] hover:underline">content guidelines</a>
                </label>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-4">
            <Button
              variant="ghost"
              onClick={() => navigate('/onboarding/packages')}
              className="text-white hover:bg-white/10"
            >
              <ArrowLeft className="mr-2" size={18} />
              Back
            </Button>
            <Button
              onClick={handlePayment}
              disabled={loading || !agreeTerms || !agreeContent}
              className="flex-1 btn-gold h-12"
            >
              {loading ? 'Processing...' : `Complete Order - $${selection.total?.toLocaleString()}`}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Checkout;
