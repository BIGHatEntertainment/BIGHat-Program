import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameMonth, isSameDay, addMonths, subMonths, parseISO, isWithinInterval } from 'date-fns';
import { ChevronLeft, ChevronRight, X, Calendar, Ban } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const BlackoutCalendarDialog = ({ open, onOpenChange, employeeId, employeeName, events = [] }) => {
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [startDate, setStartDate] = useState(null);
  const [endDate, setEndDate] = useState(null);
  const [existingBlackouts, setExistingBlackouts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // Fetch existing blackouts for this employee
  useEffect(() => {
    if (open && employeeId) {
      fetchBlackouts();
    }
  }, [open, employeeId]);

  const fetchBlackouts = async () => {
    try {
      const response = await axios.get(`${API}/blackouts/employee/${employeeId}`);
      setExistingBlackouts(response.data);
    } catch (error) {
      console.error('Error fetching blackouts:', error);
    }
  };

  const handleDateClick = (date) => {
    const dateStr = format(date, 'yyyy-MM-dd');
    
    if (!startDate) {
      // First click - set start date
      setStartDate(dateStr);
      setEndDate(null);
    } else if (!endDate) {
      // Second click - set end date
      const start = parseISO(startDate);
      if (date < start) {
        // If clicked date is before start, swap them
        setEndDate(startDate);
        setStartDate(dateStr);
      } else {
        setEndDate(dateStr);
      }
    } else {
      // Third click - reset and start new selection
      setStartDate(dateStr);
      setEndDate(null);
    }
  };

  const handleAddBlackout = () => {
    if (startDate && endDate) {
      setShowConfirm(true);
    } else {
      toast.error('Please select both start and end dates');
    }
  };

  const confirmBlackout = async () => {
    setLoading(true);
    try {
      await axios.post(`${API}/blackouts`, {
        employee_id: employeeId,
        start_date: startDate,
        end_date: endDate
      });
      
      toast.success('Blackout dates added successfully!');
      setStartDate(null);
      setEndDate(null);
      setShowConfirm(false);
      fetchBlackouts();
    } catch (error) {
      console.error('Error creating blackout:', error);
      toast.error(error.response?.data?.detail || 'Failed to add blackout dates');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteBlackout = async (blackoutId) => {
    try {
      await axios.delete(`${API}/blackouts/${blackoutId}`);
      toast.success('Blackout removed');
      fetchBlackouts();
    } catch (error) {
      console.error('Error deleting blackout:', error);
      toast.error('Failed to remove blackout');
    }
  };

  const clearSelection = () => {
    setStartDate(null);
    setEndDate(null);
  };

  const handleClose = () => {
    setStartDate(null);
    setEndDate(null);
    setShowConfirm(false);
    onOpenChange(false);
  };

  // Generate calendar days
  const monthStart = startOfMonth(currentMonth);
  const monthEnd = endOfMonth(currentMonth);
  const calendarDays = eachDayOfInterval({ start: monthStart, end: monthEnd });
  
  // Add padding days for alignment
  const startDay = monthStart.getDay();
  const paddingDays = Array(startDay).fill(null);

  // Check if a date is within selection range
  const isInSelectionRange = (date) => {
    if (!startDate || !endDate) return false;
    const start = parseISO(startDate);
    const end = parseISO(endDate);
    return isWithinInterval(date, { start, end });
  };

  // Check if a date is the start or end of selection
  const isSelectionEdge = (date) => {
    const dateStr = format(date, 'yyyy-MM-dd');
    return dateStr === startDate || dateStr === endDate;
  };

  // Check if a date has events
  const getEventsForDate = (date) => {
    const dateStr = format(date, 'yyyy-MM-dd');
    return events.filter(e => e.date === dateStr);
  };

  // Check if a date is within any existing blackout
  const isBlackoutDate = (date) => {
    return existingBlackouts.some(blackout => {
      const start = parseISO(blackout.start_date);
      const end = parseISO(blackout.end_date);
      return isWithinInterval(date, { start, end });
    });
  };

  return (
    <>
      <Dialog open={open && !showConfirm} onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Ban className="h-5 w-5 text-gray-800" />
              <span>Set Blackout Dates - {employeeName}</span>
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            {/* Instructions */}
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-sm text-gray-700">
              <p className="font-medium mb-1">How to set blackout dates:</p>
              <ol className="list-decimal list-inside space-y-1">
                <li>Click a date to set your <strong>Start Date</strong></li>
                <li>Click another date to set your <strong>End Date</strong></li>
                <li>Click &quot;Add Blackout&quot; to confirm</li>
              </ol>
            </div>

            {/* Month Navigation */}
            <div className="flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <h3 className="text-lg font-semibold">
                {format(currentMonth, 'MMMM yyyy')}
              </h3>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>

            {/* Selection Display */}
            {(startDate || endDate) && (
              <div className="flex items-center justify-between bg-gray-100 rounded-lg p-3">
                <div className="flex items-center space-x-4">
                  <div>
                    <span className="text-sm text-gray-500">Start:</span>
                    <span className="ml-2 font-medium">
                      {startDate ? format(parseISO(startDate), 'MMM d, yyyy') : '—'}
                    </span>
                  </div>
                  <div>
                    <span className="text-sm text-gray-500">End:</span>
                    <span className="ml-2 font-medium">
                      {endDate ? format(parseISO(endDate), 'MMM d, yyyy') : '—'}
                    </span>
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={clearSelection}>
                  <X className="h-4 w-4 mr-1" /> Clear
                </Button>
              </div>
            )}

            {/* Calendar Grid */}
            <div className="border rounded-lg overflow-hidden">
              {/* Day Headers */}
              <div className="grid grid-cols-7 bg-gray-100">
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                  <div key={day} className="py-2 text-center text-sm font-medium text-gray-600">
                    {day}
                  </div>
                ))}
              </div>

              {/* Calendar Days */}
              <div className="grid grid-cols-7">
                {paddingDays.map((_, index) => (
                  <div key={`pad-${index}`} className="h-16 border-t border-r bg-gray-50" />
                ))}
                {calendarDays.map(day => {
                  const dateStr = format(day, 'yyyy-MM-dd');
                  const dayEvents = getEventsForDate(day);
                  const isSelected = dateStr === startDate || dateStr === endDate;
                  const isInRange = isInSelectionRange(day);
                  const isBlacked = isBlackoutDate(day);
                  const isToday = isSameDay(day, new Date());

                  return (
                    <div
                      key={dateStr}
                      onClick={() => handleDateClick(day)}
                      className={`
                        h-16 border-t border-r p-1 cursor-pointer transition-colors relative
                        ${isSelected ? 'bg-gray-800 text-white' : ''}
                        ${isInRange && !isSelected ? 'bg-gray-300' : ''}
                        ${isBlacked && !isSelected && !isInRange ? 'bg-red-100' : ''}
                        ${!isSelected && !isInRange && !isBlacked ? 'hover:bg-gray-100' : ''}
                      `}
                    >
                      <div className={`
                        text-sm font-medium
                        ${isToday && !isSelected ? 'text-blue-600' : ''}
                      `}>
                        {format(day, 'd')}
                      </div>
                      
                      {/* Event indicators (not clickable, just visual) */}
                      {dayEvents.length > 0 && (
                        <div className="absolute bottom-1 left-1 right-1 flex flex-wrap gap-0.5">
                          {dayEvents.slice(0, 3).map((event, i) => (
                            <div
                              key={i}
                              className={`
                                h-1.5 w-1.5 rounded-full
                                ${event.event_type === 'Trivia' ? 'bg-green-500' : ''}
                                ${event.event_type === 'Karaoke' ? 'bg-pink-500' : ''}
                                ${event.event_type === 'Music Bingo' ? 'bg-blue-500' : ''}
                              `}
                              title={`${event.event_type} at ${event.venue_name || 'Venue'}`}
                            />
                          ))}
                        </div>
                      )}
                      
                      {/* Blackout indicator */}
                      {isBlacked && !isSelected && !isInRange && (
                        <div className="absolute top-1 right-1">
                          <Ban className="h-3 w-3 text-red-500" />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-4 text-sm">
              <div className="flex items-center space-x-2">
                <div className="w-4 h-4 bg-gray-800 rounded"></div>
                <span>Selected</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-4 h-4 bg-gray-300 rounded"></div>
                <span>In Range</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-4 h-4 bg-red-100 rounded border border-red-200"></div>
                <span>Existing Blackout</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                <span>Trivia</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-pink-500 rounded-full"></div>
                <span>Karaoke</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                <span>Music Bingo</span>
              </div>
            </div>

            {/* Existing Blackouts */}
            {existingBlackouts.length > 0 && (
              <div className="border-t pt-4">
                <h4 className="font-medium mb-2">Your Existing Blackout Dates:</h4>
                <div className="space-y-2">
                  {existingBlackouts.map(blackout => (
                    <div
                      key={blackout.id}
                      className="flex items-center justify-between bg-red-50 border border-red-200 rounded-lg px-3 py-2"
                    >
                      <span className="text-sm">
                        {format(parseISO(blackout.start_date), 'MMM d, yyyy')} — {format(parseISO(blackout.end_date), 'MMM d, yyyy')}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteBlackout(blackout.id)}
                        className="text-red-600 hover:text-red-700 hover:bg-red-100"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={handleClose}>
              Close
            </Button>
            <Button
              onClick={handleAddBlackout}
              disabled={!startDate || !endDate}
              className="bg-gray-800 hover:bg-gray-900 text-white"
            >
              Add Blackout
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog */}
      <Dialog open={showConfirm} onOpenChange={setShowConfirm}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle>Confirm Blackout Dates</DialogTitle>
          </DialogHeader>
          
          <div className="py-4">
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-600">Start Date:</span>
                <span className="font-semibold">
                  {startDate && format(parseISO(startDate), 'MMMM d, yyyy')}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">End Date:</span>
                <span className="font-semibold">
                  {endDate && format(parseISO(endDate), 'MMMM d, yyyy')}
                </span>
              </div>
            </div>
            <p className="text-sm text-gray-500 mt-3">
              You will be marked as unavailable during this period.
            </p>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConfirm(false)}>
              Cancel
            </Button>
            <Button
              onClick={confirmBlackout}
              disabled={loading}
              className="bg-gray-800 hover:bg-gray-900 text-white"
            >
              {loading ? 'Saving...' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default BlackoutCalendarDialog;
