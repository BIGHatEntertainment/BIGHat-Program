import React from 'react';
import { format, parseISO } from 'date-fns';
import { Calendar, Clock, MapPin, DollarSign, Star, Check, Info } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Badge } from '../ui/badge';
import { Separator } from '../ui/separator';

const EVENT_TYPE_COLORS = {
  'Trivia': 'bg-green-500',
  'Karaoke': 'bg-pink-500',
  'Music Bingo': 'bg-blue-500',
  'Special': 'bg-purple-500',
};

const EventDetailDialog = ({ open, onOpenChange, event, venue, onClaim, onUnclaim, isClaimedByUser, isClaimed }) => {
  if (!event || !venue) return null;

  const eventDate = parseISO(event.date);

  // Check if this is a franchise venue (like Monkey Pants)
  const isFranchiseVenue = venue.venue_pays_host_directly || false;

  // Calculate payment info
  const getBasePay = () => {
    // Franchise venues pay a flat rate directly
    if (isFranchiseVenue) return 150;
    
    if (event.event_type === 'Trivia') return 60;
    if (event.event_type === 'Music Bingo') return 70;
    if (event.event_type === 'Karaoke') return 25 * (event.duration_hours || 2);
    return 0;
  };

  const calculateBonuses = () => {
    // No bonuses for franchise venues
    if (isFranchiseVenue) return 0;
    
    let total = 0;
    if (event.event_type !== 'Karaoke') {
      if (event.wore_big_hat) total += 20;
      if (event.social_media_posts) total += 5;
      if (event.winners_post) total += 5;
    }
    return total;
  };

  const basePay = getBasePay();
  const bonuses = calculateBonuses();
  const totalPay = basePay + bonuses;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto" style={{ backgroundColor: '#0d1220', border: '1px solid rgba(251, 221, 104, 0.2)' }}>
        <DialogHeader>
          <DialogTitle className="text-2xl flex items-center space-x-2">
            <Calendar className="h-6 w-6 text-primary" />
            <span>{event.title}</span>
          </DialogTitle>
          <DialogDescription>
            Complete event details and payment information
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Event Type and Status */}
          <div className="flex items-center justify-between">
            <Badge className={`${EVENT_TYPE_COLORS[event.event_type] || 'bg-[#111827]0'} text-white text-base px-4 py-1`}>
              {event.event_type}
            </Badge>
            {isClaimed && (
              <Badge variant="secondary" className="text-sm">
                Claimed
              </Badge>
            )}
          </div>

          {/* Franchise Venue Notice */}
          {isFranchiseVenue && (
            <div className="p-4 bg-amber-50 border-2 border-amber-400 rounded-lg flex items-center space-x-3">
              <DollarSign className="h-6 w-6 text-amber-600 flex-shrink-0" />
              <div>
                <p className="font-bold text-amber-900">Direct Payment from Venue</p>
                <p className="text-sm text-amber-800">
                  This is a franchise location. You will receive $150 payment directly from {venue.name}.
                </p>
              </div>
            </div>
          )}

          {/* Special Event Banner */}
          {event.is_special_event && (
            <div className="p-4 bg-yellow-50 border-2 border-yellow-400 rounded-lg flex items-center space-x-3">
              <Star className="h-6 w-6 text-yellow-600 fill-yellow-500 flex-shrink-0" />
              <div>
                <p className="font-bold text-yellow-900">Special Event!</p>
                <p className="text-sm text-yellow-800">This event features a giveaway or promotion</p>
              </div>
            </div>
          )}

          {/* Event Details */}
          <div className="space-y-3 bg-[#141b50]/50 p-4 rounded-lg">
            <h3 className="font-semibold text-base flex items-center space-x-2">
              <Info className="h-5 w-5 text-primary" />
              <span>Event Details</span>
            </h3>

            <div className="space-y-3">
              <div className="flex items-start space-x-3">
                <Calendar className="h-5 w-5 text-primary mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-white">{format(eventDate, 'EEEE, MMMM d, yyyy')}</p>
                  <div className="flex items-center text-sm text-gray-400 mt-1">
                    <Clock className="h-4 w-4 mr-1" />
                    {format(eventDate, 'h:mm a')} • {event.duration_hours} hours
                  </div>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <MapPin className="h-5 w-5 text-primary mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-white">{venue.name}</p>
                  <p className="text-sm text-gray-400">{venue.address}</p>
                  <p className="text-sm text-gray-400">{venue.city}, {venue.state}</p>
                </div>
              </div>

              {event.notes && (
                <div className="pt-2 border-t border-[#1e293b]">
                  <p className="text-sm font-medium text-white mb-1">Event Notes:</p>
                  <p className="text-sm text-gray-400 italic">{event.notes}</p>
                </div>
              )}

              {venue.notes && (
                <div className="pt-2 border-t border-[#1e293b]">
                  <p className="text-sm font-medium text-white mb-1">Venue Notes:</p>
                  <p className="text-sm text-gray-400 italic">{venue.notes}</p>
                </div>
              )}
            </div>
          </div>

          <Separator />

          {/* Payment Information */}
          <div className="space-y-4">
            <h3 className="font-semibold text-lg flex items-center space-x-2">
              <DollarSign className="h-5 w-5 text-green-600" />
              <span>Payment Information</span>
            </h3>

            {/* Base Pay */}
            <div className="flex items-center justify-between p-3 bg-green-50 border-2 border-green-300 rounded-lg">
              <span className="font-medium text-white">Base Pay</span>
              <span className="text-xl font-bold text-green-700">${basePay.toFixed(2)}</span>
            </div>

            {/* Bonuses - Hidden for franchise venues */}
            {!isFranchiseVenue && event.event_type !== 'Karaoke' && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-gray-400">Bonus Opportunities:</p>

                {bonuses > 0 ? (
                  <>
                    {event.wore_big_hat && (
                      <div className="flex items-center justify-between p-3 bg-green-50 border border-green-300 rounded-lg">
                        <div className="flex items-center space-x-2">
                          <Check className="h-5 w-5 text-green-600" />
                          <span className="text-sm font-medium">Wore BIG Hat</span>
                        </div>
                        <span className="font-bold text-green-600">+$20</span>
                      </div>
                    )}
                    {event.social_media_posts && (
                      <div className="flex items-center justify-between p-3 bg-green-50 border border-green-300 rounded-lg">
                        <div className="flex items-center space-x-2">
                          <Check className="h-5 w-5 text-green-600" />
                          <span className="text-sm font-medium">Pre & Post-Show Social Media</span>
                        </div>
                        <span className="font-bold text-green-600">+$5</span>
                      </div>
                    )}
                    {event.winners_post && (
                      <div className="flex items-center justify-between p-3 bg-green-50 border border-green-300 rounded-lg">
                        <div className="flex items-center space-x-2">
                          <Check className="h-5 w-5 text-green-600" />
                          <span className="text-sm font-medium">Winners Congratulations Post</span>
                        </div>
                        <span className="font-bold text-green-600">+$5</span>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <p className="text-sm text-blue-900">
                      <strong>Earn extra bonuses:</strong>
                    </p>
                    <ul className="text-sm text-blue-800 list-disc list-inside mt-2 space-y-1">
                      <li>Wear BIG Hat: +$20</li>
                      <li>Pre & Post-Show Social Media posts: +$5</li>
                      <li>Winners Congratulations post: +$5</li>
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Karaoke Note */}
            {!isFranchiseVenue && event.event_type === 'Karaoke' && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-sm text-blue-900">
                  <strong>Karaoke Rate:</strong> $25/hour × {event.duration_hours} hours = ${basePay.toFixed(2)}
                </p>
                <p className="text-xs text-blue-700 mt-1">No bonus opportunities for Karaoke events</p>
              </div>
            )}

            {/* Total Payment */}
            <div className="flex items-center justify-between p-5 bg-green-600 text-white rounded-lg border-2 border-green-700">
              <span className="font-bold text-xl">Total Payment</span>
              <span className="text-3xl font-bold">${totalPay.toFixed(2)}</span>
            </div>
          </div>
        </div>

        <DialogFooter className="space-x-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
          {!isClaimed && onClaim && (
            <Button
              onClick={() => {
                onOpenChange(false);
                onClaim();
              }}
              className="bg-green-600 hover:bg-green-700 text-white"
            >
              Claim This Event
            </Button>
          )}
          {isClaimedByUser && onUnclaim && (
            <Button
              onClick={() => {
                onOpenChange(false);
                onUnclaim();
              }}
              variant="outline"
              className="border-red-300 text-red-600 hover:bg-red-50"
            >
              Unclaim Event
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default EventDetailDialog;
