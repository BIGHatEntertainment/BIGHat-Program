import React, { useState } from 'react';
import axios from 'axios';
import { format, parseISO } from 'date-fns';
import { DollarSign, Calendar, MapPin, User, Check, Star } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Badge } from '../ui/badge';
import { Separator } from '../ui/separator';
import { Checkbox } from '../ui/checkbox';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const PaymentDetailDialog = ({ open, onOpenChange, payment, onAcknowledge }) => {
  const [acknowledging, setAcknowledging] = useState(false);
  const [bonuses, setBonuses] = useState({
    wore_big_hat: false,
    social_media_posts: false,
    winners_post: false
  });

  // Initialize bonuses when payment changes
  React.useEffect(() => {
    if (payment) {
      setBonuses({
        wore_big_hat: payment.wore_big_hat || false,
        social_media_posts: payment.social_media_posts || false,
        winners_post: payment.winners_post || false
      });
    }
  }, [payment]);

  if (!payment) return null;

  const calculateTotal = () => {
    let total = payment.base_pay;
    if (payment.event_type !== 'Karaoke') {
      if (bonuses.wore_big_hat) total += 20;
      if (bonuses.social_media_posts) total += 5;
      if (bonuses.winners_post) total += 5;
    }
    return total;
  };

  const calculateBonusTotal = () => {
    let total = 0;
    if (payment.event_type !== 'Karaoke') {
      if (bonuses.wore_big_hat) total += 20;
      if (bonuses.social_media_posts) total += 5;
      if (bonuses.winners_post) total += 5;
    }
    return total;
  };

  const handleToggleBonus = (bonusKey) => {
    setBonuses(prev => ({
      ...prev,
      [bonusKey]: !prev[bonusKey]
    }));
  };

  const handleAcknowledge = async () => {
    const totalPayment = calculateTotal();
    if (!window.confirm(`Confirm payment of $${totalPayment.toFixed(2)} to ${payment.employee_name}?\n\nThis will remove the event from the weekly report and save the payment record.`)) {
      return;
    }

    setAcknowledging(true);
    try {
      await axios.post(`${API}/reports/payment/acknowledge`, {
        event_id: payment.event_id,
        wore_big_hat: bonuses.wore_big_hat,
        social_media_posts: bonuses.social_media_posts,
        winners_post: bonuses.winners_post
      });
      toast.success(`Payment of $${totalPayment.toFixed(2)} acknowledged for ${payment.employee_name}!`);
      onOpenChange(false);
      onAcknowledge();
    } catch (error) {
      console.error('Error acknowledging payment:', error);
      toast.error('Failed to acknowledge payment');
    } finally {
      setAcknowledging(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl flex items-center space-x-2">
            <DollarSign className="h-6 w-6 text-green-600" />
            <span>Payment Details</span>
          </DialogTitle>
          <DialogDescription>
            Review payment breakdown and acknowledge when paid
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Event Information */}
          <div className="space-y-3 bg-muted/50 p-4 rounded-lg">
            <div className="flex items-start space-x-3">
              <User className="h-5 w-5 text-primary mt-0.5" />
              <div>
                <p className="font-semibold text-foreground text-lg">{payment.employee_name}</p>
                <p className="text-sm text-muted-foreground">Host</p>
              </div>
            </div>

            <div className="flex items-start space-x-3">
              <Calendar className="h-5 w-5 text-primary mt-0.5" />
              <div>
                <p className="font-semibold text-foreground">{payment.event_title}</p>
                <p className="text-sm text-muted-foreground">
                  {format(parseISO(payment.date), 'EEEE, MMMM d, yyyy • h:mm a')}
                </p>
              </div>
            </div>

            <div className="flex items-start space-x-3">
              <MapPin className="h-5 w-5 text-primary mt-0.5" />
              <div>
                <p className="font-semibold text-foreground">{payment.venue_name}</p>
                <p className="text-sm text-muted-foreground">Venue</p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Badge className="bg-blue-500 text-white">{payment.event_type}</Badge>
              <span className="text-sm text-muted-foreground">
                {payment.duration_hours} hours
              </span>
            </div>
          </div>

          <Separator />

          {/* Payment Breakdown */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg flex items-center space-x-2">
              <DollarSign className="h-5 w-5 text-green-600" />
              <span>Payment Breakdown</span>
            </h3>

            {/* Base Pay */}
            <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg">
              <span className="font-medium text-foreground">Base Pay</span>
              <span className="text-lg font-bold text-green-700">${payment.base_pay.toFixed(2)}</span>
            </div>

            {/* Bonuses - Only show for Trivia and Music Bingo */}
            {payment.event_type !== 'Karaoke' && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-muted-foreground">Bonus Breakdown:</p>

                {/* BIG Hat Bonus */}
                <div 
                  className={`flex items-center justify-between p-3 rounded-lg border-2 transition-colors ${
                    bonuses.wore_big_hat 
                      ? 'bg-green-50 border-green-400' 
                      : 'bg-white border-gray-300 hover:border-gray-400'
                  }`}
                >
                  <div className="flex items-center space-x-3 cursor-pointer" onClick={() => handleToggleBonus('wore_big_hat')}>
                    <Checkbox
                      checked={bonuses.wore_big_hat}
                      onCheckedChange={() => handleToggleBonus('wore_big_hat')}
                      className="pointer-events-auto"
                    />
                    <span className={`text-sm select-none ${bonuses.wore_big_hat ? 'font-medium' : 'text-muted-foreground'}`}>
                      Wore BIG Hat
                    </span>
                  </div>
                  <span className={`font-bold ${bonuses.wore_big_hat ? 'text-green-600' : 'text-gray-400'}`}>
                    +$20
                  </span>
                </div>

                {/* Social Media Posts */}
                <div 
                  className={`flex items-center justify-between p-3 rounded-lg border-2 transition-colors ${
                    bonuses.social_media_posts 
                      ? 'bg-green-50 border-green-400' 
                      : 'bg-white border-gray-300 hover:border-gray-400'
                  }`}
                >
                  <div className="flex items-center space-x-3 cursor-pointer" onClick={() => handleToggleBonus('social_media_posts')}>
                    <Checkbox
                      checked={bonuses.social_media_posts}
                      onCheckedChange={() => handleToggleBonus('social_media_posts')}
                      className="pointer-events-auto"
                    />
                    <span className={`text-sm select-none ${bonuses.social_media_posts ? 'font-medium' : 'text-muted-foreground'}`}>
                      Pre & Post-Show Social Media
                    </span>
                  </div>
                  <span className={`font-bold ${bonuses.social_media_posts ? 'text-green-600' : 'text-gray-400'}`}>
                    +$5
                  </span>
                </div>

                {/* Winners Post */}
                <div 
                  className={`flex items-center justify-between p-3 rounded-lg border-2 transition-colors ${
                    bonuses.winners_post 
                      ? 'bg-green-50 border-green-400' 
                      : 'bg-white border-gray-300 hover:border-gray-400'
                  }`}
                >
                  <div className="flex items-center space-x-3 cursor-pointer" onClick={() => handleToggleBonus('winners_post')}>
                    <Checkbox
                      checked={bonuses.winners_post}
                      onCheckedChange={() => handleToggleBonus('winners_post')}
                      className="pointer-events-auto"
                    />
                    <span className={`text-sm select-none ${bonuses.winners_post ? 'font-medium' : 'text-muted-foreground'}`}>
                      Winners Congratulations Post
                    </span>
                  </div>
                  <span className={`font-bold ${bonuses.winners_post ? 'text-green-600' : 'text-gray-400'}`}>
                    +$5
                  </span>
                </div>

                {/* Total Bonuses */}
                {calculateBonusTotal() > 0 && (
                  <div className="flex items-center justify-between p-3 bg-green-100 border-2 border-green-400 rounded-lg">
                    <span className="font-semibold text-foreground">Total Bonuses</span>
                    <span className="text-lg font-bold text-green-700">+${calculateBonusTotal().toFixed(2)}</span>
                  </div>
                )}
              </div>
            )}

            {/* Karaoke Note */}
            {payment.event_type === 'Karaoke' && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-sm text-blue-900">
                  <strong>Karaoke Rate:</strong> $25/hour × {payment.duration_hours} hours = ${payment.base_pay.toFixed(2)}
                </p>
              </div>
            )}
          </div>

          <Separator />

          {/* Total Payment */}
          <div className="flex items-center justify-between p-5 bg-green-600 text-white rounded-lg border-2 border-green-700">
            <span className="font-bold text-xl">Total Payment</span>
            <span className="text-3xl font-bold">${calculateTotal().toFixed(2)}</span>
          </div>

          {/* Acknowledge Note */}
          <div className="p-4 bg-orange-50 border border-orange-200 rounded-lg">
            <p className="text-sm text-orange-900">
              <strong>Important:</strong> Clicking &quot;Acknowledge Payment&quot; will:
            </p>
            <ul className="text-sm text-orange-900 list-disc list-inside mt-2 space-y-1">
              <li>Remove this event from the weekly report</li>
              <li>Save the payment record with timestamp</li>
              <li>Store the record in payment history by month</li>
              <li>Mark the payment as completed</li>
            </ul>
          </div>
        </div>

        <DialogFooter className="space-x-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
          <Button
            onClick={handleAcknowledge}
            disabled={acknowledging}
            className="bg-green-600 hover:bg-green-700 text-white"
          >
            {acknowledging ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Processing...
              </>
            ) : (
              <>
                <Check className="h-4 w-4 mr-2" />
                Acknowledge Payment
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PaymentDetailDialog;
