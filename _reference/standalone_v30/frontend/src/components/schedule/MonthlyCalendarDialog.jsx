import React, { useState, useEffect } from 'react';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameDay, parseISO, addMonths, subMonths } from 'date-fns';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, MapPin, Clock, X } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Badge } from '../ui/badge';

const EVENT_TYPE_COLORS = {
  'Trivia': 'bg-green-500',
  'Karaoke': 'bg-pink-500',
  'Music Bingo': 'bg-blue-500',
  'Special': 'bg-purple-500',
};

const MonthlyCalendarDialog = ({ open, onOpenChange, events, currentUserId, onEventClick }) => {
  const [currentMonth, setCurrentMonth] = useState(new Date());

  const getDaysInMonth = () => {
    const monthStart = startOfMonth(currentMonth);
    const monthEnd = endOfMonth(currentMonth);
    return eachDayOfInterval({ start: monthStart, end: monthEnd });
  };

  const getEventsForDay = (day) => {
    return events.filter(event => {
      const eventDate = parseISO(event.date);
      return isSameDay(eventDate, day);
    });
  };

  const isUserClaimedDay = (day) => {
    const dayEvents = getEventsForDay(day);
    return dayEvents.some(event => event.claimed_by === currentUserId);
  };

  const days = getDaysInMonth();
  const daysOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const firstDayOfMonth = startOfMonth(currentMonth).getDay();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-2xl flex items-center space-x-2">
              <CalendarIcon className="h-6 w-6 text-primary" />
              <span>Monthly Calendar</span>
            </DialogTitle>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onOpenChange(false)}
              className="h-8 w-8"
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Month Navigation */}
          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
            >
              <ChevronLeft className="h-5 w-5" />
            </Button>
            <h2 className="text-2xl font-bold">
              {format(currentMonth, 'MMMM yyyy')}
            </h2>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
            >
              <ChevronRight className="h-5 w-5" />
            </Button>
          </div>

          {/* Legend */}
          <div className="flex items-center justify-center space-x-4 text-sm">
            <div className="flex items-center space-x-2">
              <div className="w-4 h-4 bg-gray-200 rounded"></div>
              <span className="text-muted-foreground">You&apos;re claimed</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-4 h-4 bg-green-500 rounded"></div>
              <span className="text-muted-foreground">Trivia</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-4 h-4 bg-blue-500 rounded"></div>
              <span className="text-muted-foreground">Music Bingo</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-4 h-4 bg-pink-500 rounded"></div>
              <span className="text-muted-foreground">Karaoke</span>
            </div>
          </div>

          {/* Calendar Header */}
          <div className="grid grid-cols-7 gap-2 mb-2">
            {daysOfWeek.map(day => (
              <div key={day} className="text-center font-semibold text-sm text-muted-foreground py-2">
                {day}
              </div>
            ))}
          </div>

          {/* Calendar Grid */}
          <div className="grid grid-cols-7 gap-2">
            {/* Empty cells for days before month starts */}
            {Array.from({ length: firstDayOfMonth }).map((_, idx) => (
              <div key={`empty-${idx}`} className="min-h-[100px] bg-muted/20 rounded-lg"></div>
            ))}

            {/* Days of month */}
            {days.map(day => {
              const dayEvents = getEventsForDay(day);
              const isToday = isSameDay(day, new Date());
              const isUserClaimed = isUserClaimedDay(day);
              const hasMultipleEvents = dayEvents.length > 1;

              return (
                <div
                  key={day.toString()}
                  className={`min-h-[100px] border-2 rounded-lg p-2 transition-colors ${
                    isToday ? 'border-primary bg-primary/5' : 
                    isUserClaimed && !hasMultipleEvents ? 'border-gray-500 bg-gray-300' :
                    'border-border bg-card'
                  }`}
                >
                  <div className={`text-sm font-semibold mb-2 ${
                    isToday ? 'text-primary' : 
                    isUserClaimed ? 'text-gray-600' :
                    'text-foreground'
                  }`}>
                    {format(day, 'd')}
                  </div>
                  
                  <div className="space-y-1">
                    {dayEvents.map(event => (
                      <div
                        key={event.id}
                        onClick={() => {
                          onEventClick(event);
                          onOpenChange(false);
                        }}
                        className={`text-xs p-1 rounded cursor-pointer hover:shadow-md transition-shadow ${
                          EVENT_TYPE_COLORS[event.event_type]
                        } bg-opacity-20 border border-current`}
                      >
                        <div className="font-medium truncate">{event.event_type}</div>
                        <div className="text-[10px] truncate flex items-center">
                          <Clock className="h-2 w-2 mr-0.5" />
                          {format(parseISO(event.date), 'h:mm a')}
                        </div>
                        {event.claimed_by && (
                          <div className="text-[10px] text-gray-600 truncate">
                            {event.claimed_by === currentUserId ? '✓ You' : 'Claimed'}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default MonthlyCalendarDialog;
