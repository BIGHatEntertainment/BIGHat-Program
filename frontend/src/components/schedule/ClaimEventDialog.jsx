import React from 'react';
import { format, parseISO } from 'date-fns';
import { Calendar, Clock, MapPin, AlertCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Badge } from '../ui/badge';

const EVENT_TYPE_COLORS = {
  'Trivia': 'bg-green-500',
  'Karaoke': 'bg-pink-500',
  'Music Bingo': 'bg-blue-500',
  'Special': 'bg-purple-500',
};

const ClaimEventDialog = ({ open, onOpenChange, event, venue, onConfirm }) => {
  if (!event || !venue) return null;

  const eventDate = parseISO(event.date);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]" style={{ backgroundColor: "#0d1220", border: "1px solid rgba(251, 221, 104, 0.2)" }}>
        <DialogHeader>
          <DialogTitle className="text-2xl">Confirm Event Claim</DialogTitle>
          <DialogDescription>
            Please review the event details before confirming
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Event Type Badge */}
          <div className="flex items-center space-x-2">
            <Badge className={`${EVENT_TYPE_COLORS[event.event_type] || 'bg-gray-500'} text-white text-sm px-3 py-1`}>
              {event.event_type}
            </Badge>
          </div>

          {/* Event Details */}
          <div className="space-y-3 bg-muted/50 p-4 rounded-lg">
            <div className="flex items-start space-x-3">
              <Calendar className="h-5 w-5 text-primary mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-semibold text-foreground">{format(eventDate, 'EEEE, MMMM d, yyyy')}</p>
                <div className="flex items-center text-sm text-muted-foreground mt-1">
                  <Clock className="h-4 w-4 mr-1" />
                  {format(eventDate, 'h:mm a')} ({event.duration_hours} hours)
                </div>
              </div>
            </div>

            <div className="flex items-start space-x-3">
              <MapPin className="h-5 w-5 text-primary mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-semibold text-foreground">{venue.name}</p>
                <p className="text-sm text-muted-foreground">{venue.address}</p>
                <p className="text-sm text-muted-foreground">{venue.city}, {venue.state}</p>
              </div>
            </div>

            {event.notes && (
              <div className="pt-2 border-t border-border">
                <p className="text-sm text-muted-foreground">{event.notes}</p>
              </div>
            )}

            {event.pay_rate && (
              <div className="pt-2 border-t border-border">
                <p className="text-sm font-medium text-foreground">
                  Pay Rate: ${event.pay_rate}/hour
                </p>
              </div>
            )}
          </div>

          {/* Confirmation Note */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-start space-x-3">
            <AlertCircle className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-blue-900">
              <p className="font-medium mb-1">You&apos;re about to claim this event</p>
              <p>By claiming this event, you commit to hosting. You can unclaim it later if needed.</p>
            </div>
          </div>
        </div>

        <DialogFooter className="space-x-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            onClick={onConfirm}
            className="bg-green-600 hover:bg-green-700 text-white"
          >
            Confirm & Claim Event
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ClaimEventDialog;
