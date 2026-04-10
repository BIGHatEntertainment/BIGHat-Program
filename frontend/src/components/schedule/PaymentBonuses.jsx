import React, { useState } from 'react';
import axios from 'axios';
import { DollarSign, Check } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Checkbox } from '../ui/checkbox';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const PaymentBonuses = ({ event, onUpdate }) => {
  const [bonuses, setBonuses] = useState({
    wore_big_hat: event.wore_big_hat || false,
    social_media_posts: event.social_media_posts || false,
    winners_post: event.winners_post || false
  });
  const [saving, setSaving] = useState(false);

  const handleToggle = (key) => {
    setBonuses(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const getBasePay = () => {
    if (event.event_type === 'Trivia') return 60;
    if (event.event_type === 'Music Bingo') return 70;
    if (event.event_type === 'Karaoke') return 25 * (event.duration_hours || 2);
    return 0;
  };

  const showBonuses = () => {
    return event.event_type === 'Trivia' || event.event_type === 'Music Bingo';
  };

  const calculateTotal = () => {
    let total = getBasePay();
    if (showBonuses()) {
      if (bonuses.wore_big_hat) total += 20;
      if (bonuses.social_media_posts) total += 5;
      if (bonuses.winners_post) total += 5;
    }
    return total;
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/events/${event.id}/bonuses`, bonuses);
      toast.success('Payment bonuses updated!');
      if (onUpdate) onUpdate();
    } catch (error) {
      console.error('Error updating bonuses:', error);
      toast.error('Failed to update bonuses');
    } finally {
      setSaving(false);
    }
  };

  const hasChanges = 
    bonuses.wore_big_hat !== (event.wore_big_hat || false) ||
    bonuses.social_media_posts !== (event.social_media_posts || false) ||
    bonuses.winners_post !== (event.winners_post || false);

  return (
    <Card className="border-2 border-green-200 bg-green-50/50">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center space-x-2">
          <DollarSign className="h-5 w-5 text-green-600" />
          <span>Payment Tracker</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Event Type */}
        <div className="flex items-center justify-between p-2 bg-primary/10 rounded-lg">
          <span className="text-sm font-medium text-primary">{event.event_type}</span>
          {event.event_type === 'Karaoke' && (
            <span className="text-xs text-muted-foreground">${25}/hour × {event.duration_hours}h</span>
          )}
        </div>

        {/* Base Pay */}
        <div className="flex items-center justify-between p-3 bg-white rounded-lg border-2 border-green-300">
          <span className="font-semibold text-foreground">Base Pay</span>
          <span className="text-lg font-bold text-green-700">${getBasePay()}</span>
        </div>

        {/* Bonuses - Only for Trivia and Music Bingo */}
        {showBonuses() && (
          <div className="space-y-3">
            <div className="text-sm font-medium text-muted-foreground mb-2">Bonus Opportunities:</div>
          
          {/* BIG Hat Bonus */}
          <div className="flex items-start space-x-3 p-3 bg-white rounded-lg border hover:border-green-400 transition-colors">
            <Checkbox
              id="wore_big_hat"
              checked={bonuses.wore_big_hat}
              onCheckedChange={() => handleToggle('wore_big_hat')}
              className="mt-0.5"
            />
            <div className="flex-1">
              <Label 
                htmlFor="wore_big_hat" 
                className="text-sm font-medium cursor-pointer flex items-center justify-between"
              >
                <span>Wore BIG Hat</span>
                <span className="text-green-600 font-bold">+$20</span>
              </Label>
            </div>
          </div>

          {/* Social Media Posts */}
          <div className="flex items-start space-x-3 p-3 bg-white rounded-lg border hover:border-green-400 transition-colors">
            <Checkbox
              id="social_media_posts"
              checked={bonuses.social_media_posts}
              onCheckedChange={() => handleToggle('social_media_posts')}
              className="mt-0.5"
            />
            <div className="flex-1">
              <Label 
                htmlFor="social_media_posts" 
                className="text-sm font-medium cursor-pointer flex items-center justify-between"
              >
                <span>Pre & Post-Show Social Media</span>
                <span className="text-green-600 font-bold">+$5</span>
              </Label>
              <p className="text-xs text-muted-foreground mt-1">
                Tagged @bighattrivia in pre-show and post-show posts/stories
              </p>
            </div>
          </div>

          {/* Winners Congratulations */}
          <div className="flex items-start space-x-3 p-3 bg-white rounded-lg border hover:border-green-400 transition-colors">
            <Checkbox
              id="winners_post"
              checked={bonuses.winners_post}
              onCheckedChange={() => handleToggle('winners_post')}
              className="mt-0.5"
            />
            <div className="flex-1">
              <Label 
                htmlFor="winners_post" 
                className="text-sm font-medium cursor-pointer flex items-center justify-between"
              >
                <span>Winners Congratulations Post</span>
                <span className="text-green-600 font-bold">+$5</span>
              </Label>
              <p className="text-xs text-muted-foreground mt-1">
                Posted congratulating the winners on social media
              </p>
            </div>
          </div>
          </div>
        )}

        {/* Karaoke Note */}
        {event.event_type === 'Karaoke' && (
          <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-900">
              <strong>Karaoke events:</strong> Paid at $25/hour with no bonus opportunities.
            </p>
          </div>
        )}

        {/* Total */}
        <div className="flex items-center justify-between p-4 bg-green-600 text-white rounded-lg border-2 border-green-700">
          <span className="font-bold text-lg">Total Pay</span>
          <span className="text-2xl font-bold">${calculateTotal()}</span>
        </div>

        {/* Save Button */}
        {hasChanges && (
          <Button
            onClick={handleSave}
            disabled={saving}
            className="w-full bg-blue-500 hover:bg-blue-600 text-white"
          >
            {saving ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Saving...
              </>
            ) : (
              <>
                <Check className="h-4 w-4 mr-2" />
                Save Payment Bonuses
              </>
            )}
          </Button>
        )}
      </CardContent>
    </Card>
  );
};

export default PaymentBonuses;
