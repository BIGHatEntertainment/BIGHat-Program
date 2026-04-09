import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameDay, parseISO, addMonths, subMonths, set } from 'date-fns';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight, DollarSign, TrendingUp, TrendingDown, MapPin, Plus, Clock, Search, Ban } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { toast } from 'sonner';
import EventCrawlerDialog from './EventCrawlerDialog';
import BlackoutReportDialog from './BlackoutReportDialog';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const EVENT_TYPE_COLORS = {
  'Trivia': 'bg-green-500',
  'Karaoke': 'bg-pink-500',
  'Music Bingo': 'bg-blue-500',
  'Special': 'bg-purple-500',
};

const MonthlyReports = () => {
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [venues, setVenues] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [selectedVenue, setSelectedVenue] = useState('all');
  const [events, setEvents] = useState([]);
  const [acknowledgedPayments, setAcknowledgedPayments] = useState([]);
  const [venueRevenue, setVenueRevenue] = useState({});
  const [venuePricing, setVenuePricing] = useState({});
  const [expectedIncome, setExpectedIncome] = useState(0);
  const [incomeBreakdown, setIncomeBreakdown] = useState([]); // per-event breakdown from API
  const [loading, setLoading] = useState(true);
  const [eventDialogOpen, setEventDialogOpen] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);
  const [blackoutReportOpen, setBlackoutReportOpen] = useState(false);
  const [newEvent, setNewEvent] = useState({
    event_type: 'Trivia',
    start_time: '19:00'
  });
  const [creatingEvent, setCreatingEvent] = useState(false);
  const [crawlerDialogOpen, setCrawlerDialogOpen] = useState(false);
  const [phoenixEvents, setPhoenixEvents] = useState([]);

  useEffect(() => {
    fetchData();
  }, [currentMonth, selectedVenue]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const monthStart = startOfMonth(currentMonth);
      const monthEnd = endOfMonth(currentMonth);
      const monthKey = format(currentMonth, 'yyyy-MM');

      const [venuesRes, employeesRes, eventsRes, paymentsRes, pricingRes, expectedIncomeRes, crawlerRes] = await Promise.all([
        axios.get(`${API}/venues`),
        axios.get(`${API}/employees`),
        axios.get(`${API}/events?include_past=true`),
        axios.get(`${API}/reports/payment/history?month=${monthKey}`),
        axios.get(`${API}/venue_pricing`),
        axios.get(`${API}/reports/monthly/expected_income?month=${monthKey}${selectedVenue !== 'all' ? `&venue_id=${selectedVenue}` : ''}`),
        axios.get(`${API}/events/crawler/phoenix`).catch(() => ({ data: { events: [] } }))
      ]);

      setVenues(venuesRes.data);
      setEmployees(employeesRes.data);
      
      // Filter events for current month
      const monthEvents = eventsRes.data.filter(event => {
        const eventDate = parseISO(event.date);
        return eventDate >= monthStart && eventDate <= monthEnd;
      });
      setEvents(monthEvents);
      
      setAcknowledgedPayments(paymentsRes.data);

      // Build venue pricing map
      const pricingMap = {};
      pricingRes.data.forEach(p => {
        pricingMap[p.venue_id] = p;
      });
      setVenuePricing(pricingMap);

      // Set expected income from backend calculation
      setExpectedIncome(expectedIncomeRes.data.total_expected_income || 0);
      setIncomeBreakdown(expectedIncomeRes.data.events || []);

      // Get manual revenue overrides from localStorage
      const storedRevenue = localStorage.getItem(`venue_revenue_${monthKey}`);
      setVenueRevenue(storedRevenue ? JSON.parse(storedRevenue) : {});

      // Set Phoenix events from crawler
      setPhoenixEvents(crawlerRes.data.events || []);
    } catch (error) {
      console.error('Error fetching data:', error);
      toast.error('Failed to load monthly report data');
    } finally {
      setLoading(false);
    }
  };

  const handleRevenueChange = (venueId, amount) => {
    const monthKey = format(currentMonth, 'yyyy-MM');
    const updated = {
      ...venueRevenue,
      [venueId]: parseFloat(amount) || 0
    };
    setVenueRevenue(updated);
    localStorage.setItem(`venue_revenue_${monthKey}`, JSON.stringify(updated));
  };

  const handleDateClick = (day) => {
    if (selectedVenue === 'all') {
      toast.error('Please select a specific location to add events');
      return;
    }

    // Check if venue already has an event on this date
    const existingEvents = getEventsForDay(day);
    if (existingEvents.length > 0) {
      toast.error('This venue already has an event on this date');
      return;
    }

    setSelectedDate(day);
    setNewEvent({
      event_type: 'Trivia',
      start_time: '19:00'
    });
    setEventDialogOpen(true);
  };

  const handleCreateEvent = async () => {
    setCreatingEvent(true);
    try {
      const venue = venues.find(v => v.id === selectedVenue);
      if (!venue) {
        toast.error('Venue not found');
        return;
      }

      // Parse time and create datetime
      const [hours, minutes] = newEvent.start_time.split(':');
      const eventDateTime = set(selectedDate, {
        hours: parseInt(hours),
        minutes: parseInt(minutes),
        seconds: 0
      });

      // Generate event title
      const eventTitle = `${newEvent.event_type} Night`;

      // Determine duration based on event type
      const duration = newEvent.event_type === 'Karaoke' ? 3 : 2;

      const eventData = {
        title: eventTitle,
        event_type: newEvent.event_type,
        venue_id: selectedVenue,
        date: eventDateTime.toISOString(),
        duration_hours: duration
      };

      await axios.post(`${API}/events`, eventData);
      
      toast.success(`${newEvent.event_type} event created for ${format(selectedDate, 'MMM d')}`);
      setEventDialogOpen(false);
      
      // Refresh data to show new event and updated income
      fetchData();
    } catch (error) {
      console.error('Error creating event:', error);
      toast.error('Failed to create event');
    } finally {
      setCreatingEvent(false);
    }
  };

  const getDaysInMonth = () => {
    const monthStart = startOfMonth(currentMonth);
    const monthEnd = endOfMonth(currentMonth);
    return eachDayOfInterval({ start: monthStart, end: monthEnd });
  };

  const getEventsForDay = (day) => {
    return events.filter(event => {
      const eventDate = parseISO(event.date);
      const matchesDay = isSameDay(eventDate, day);
      if (selectedVenue === 'all') return matchesDay;
      return matchesDay && event.venue_id === selectedVenue;
    });
  };

  const getPhoenixEventsForDay = (day) => {
    return phoenixEvents.filter(event => {
      try {
        const eventDate = parseISO(event.date);
        return isSameDay(eventDate, day);
      } catch {
        return false;
      }
    });
  };

  const getVenueName = (venueId) => {
    const venue = venues.find(v => v.id === venueId);
    return venue ? venue.name : 'Unknown';
  };

  // Nicholas Sellards (owner) - his payments don't count against outgoing
  const NICK_SELLARDS_EMAIL = 'sellards@bighat.live';
  
  const calculateTotalOutgoing = () => {
    // Filter payments by selected venue if not 'all'
    let paymentsToCount = acknowledgedPayments;
    
    if (selectedVenue !== 'all') {
      paymentsToCount = acknowledgedPayments.filter(payment => payment.venue_id === selectedVenue);
    }
    
    // Calculate outgoing payments:
    // - EXCLUDE all payments to Nick Sellards (owner) - he doesn't count against outgoing
    // - Include all other payments regardless of venue type
    return paymentsToCount.reduce((sum, payment) => {
      // First check if employee_email is stored in the payment record (newer records)
      let employeeEmail = payment.employee_email;
      
      // Fallback to looking up the employee if email not in payment record (older records)
      if (!employeeEmail) {
        const employee = employees.find(e => e.id === payment.employee_id);
        employeeEmail = employee?.email || '';
      }
      
      // Check if this payment is to Nicholas Sellards (the owner)
      if (employeeEmail && employeeEmail.toLowerCase() === NICK_SELLARDS_EMAIL.toLowerCase()) {
        // Payment to Nick (owner) - don't count as outgoing expense
        return sum;
      }
      // Payment to any other employee - count as outgoing
      return sum + (payment.total_pay || 0);
    }, 0);
  };

  const calculateTotalIncoming = () => {
    // Check if there's a manual override for this venue
    if (selectedVenue !== 'all' && venueRevenue[selectedVenue] !== undefined) {
      return venueRevenue[selectedVenue];
    }
    
    // Otherwise use expected income calculated from pricing
    return expectedIncome;
  };

  // Get filtered payments for display (filtered by venue if selected)
  const getFilteredPayments = () => {
    if (selectedVenue === 'all') {
      return acknowledgedPayments;
    }
    return acknowledgedPayments.filter(payment => payment.venue_id === selectedVenue);
  };

  const days = getDaysInMonth();
  const totalIncoming = calculateTotalIncoming();
  const totalOutgoing = calculateTotalOutgoing();
  const filteredPayments = getFilteredPayments();
  const balance = totalIncoming - totalOutgoing;

  const daysOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const firstDayOfMonth = startOfMonth(currentMonth).getDay();

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-primary mx-auto mb-4"></div>
        <p className="text-muted-foreground">Loading monthly report...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <Card className="border-2 shadow-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl flex items-center space-x-2">
                <CalendarIcon className="h-6 w-6 text-primary" />
                <span>Monthly Payment Report</span>
              </CardTitle>
              <CardDescription>Track incoming revenue and outgoing payments by venue</CardDescription>
            </div>
            <div className="flex items-center space-x-2">
              <Button
                onClick={() => setBlackoutReportOpen(true)}
                className="bg-gray-800 hover:bg-gray-900 text-white"
              >
                <Ban className="h-4 w-4 mr-2" />
                Blackout Report
              </Button>
              <Button
                onClick={() => setCrawlerDialogOpen(true)}
                className="bg-purple-500 hover:bg-purple-600 text-white"
              >
                <Search className="h-4 w-4 mr-2" />
                Check Phoenix Events
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
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

          {/* Venue Filter */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Filter by Location</Label>
              {selectedVenue !== 'all' && (
                <Button
                  onClick={() => {}}
                  className="bg-blue-500 hover:bg-blue-600 text-white"
                  size="sm"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Add Events
                </Button>
              )}
            </div>
            <Select value={selectedVenue} onValueChange={setSelectedVenue}>
              <SelectTrigger className="w-full sm:w-80">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Locations</SelectItem>
                {venues.map(venue => (
                  <SelectItem key={venue.id} value={venue.id}>
                    {venue.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Revenue Input */}
          {selectedVenue !== 'all' && (
            <Card className="bg-blue-50 border-2">
              <CardContent className="pt-6 space-y-3">
                <div>
                  <Label className="text-base font-semibold">Revenue for {getVenueName(selectedVenue)}</Label>
                  <p className="text-sm text-muted-foreground mt-1">
                    Expected income is auto-calculated from scheduled events &times; venue pricing.
                  </p>
                </div>
                
                <div className="space-y-2">
                  <div className="p-3 bg-[#111827] rounded border space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-muted-foreground">Expected Income (Auto-calculated):</span>
                      <span className="font-bold text-green-600 text-lg" data-testid="expected-income-total">${expectedIncome.toFixed(2)}</span>
                    </div>
                    {/* Per-type breakdown */}
                    {incomeBreakdown.length > 0 && (
                      <div className="pt-2 border-t border-gray-100 space-y-1">
                        {(() => {
                          const byType = {};
                          incomeBreakdown.forEach(e => {
                            if (!byType[e.event_type]) byType[e.event_type] = { count: 0, total: 0, perEvent: e.expected_income };
                            byType[e.event_type].count++;
                            byType[e.event_type].total += e.expected_income;
                          });
                          return Object.entries(byType).map(([type, data]) => (
                            <div key={type} className="flex justify-between text-xs" data-testid={`venue-breakdown-${type}`}>
                              <span className="text-muted-foreground">{data.count}x {type} @ ${data.perEvent.toFixed(2)}/event</span>
                              <span className="font-medium text-green-700">${data.total.toFixed(2)}</span>
                            </div>
                          ));
                        })()}
                      </div>
                    )}
                    {incomeBreakdown.length === 0 && (
                      <p className="text-xs text-muted-foreground">No events scheduled this month.</p>
                    )}
                  </div>
                  
                  <div className="space-y-1">
                    <Label htmlFor="manual_revenue" className="text-sm">Manual Override (Optional)</Label>
                    <div className="flex items-center space-x-2">
                      <span className="text-lg font-bold">$</span>
                      <Input
                        id="manual_revenue"
                        type="number"
                        step="0.01"
                        placeholder={expectedIncome.toFixed(2)}
                        value={venueRevenue[selectedVenue] || ''}
                        onChange={(e) => handleRevenueChange(selectedVenue, e.target.value)}
                        className="w-48"
                      />
                      {venueRevenue[selectedVenue] && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            const monthKey = format(currentMonth, 'yyyy-MM');
                            const updated = { ...venueRevenue };
                            delete updated[selectedVenue];
                            setVenueRevenue(updated);
                            localStorage.setItem(`venue_revenue_${monthKey}`, JSON.stringify(updated));
                            toast.success('Reset to auto-calculated amount');
                          }}
                        >
                          Reset
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </CardContent>
      </Card>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="border-2">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Incoming Revenue</p>
                <p className="text-3xl font-bold text-green-600" data-testid="incoming-revenue">${totalIncoming.toFixed(2)}</p>
              </div>
              <TrendingUp className="h-10 w-10 text-green-600 opacity-50" />
            </div>
            {/* Income Breakdown by Event Type */}
            {incomeBreakdown.length > 0 && (
              <div className="mt-3 pt-3 border-t border-border space-y-1">
                {(() => {
                  const byType = {};
                  incomeBreakdown.forEach(e => {
                    if (!byType[e.event_type]) byType[e.event_type] = { count: 0, total: 0 };
                    byType[e.event_type].count++;
                    byType[e.event_type].total += e.expected_income;
                  });
                  return Object.entries(byType).map(([type, data]) => (
                    <div key={type} className="flex justify-between text-xs text-muted-foreground" data-testid={`income-breakdown-${type}`}>
                      <span>{data.count}x {type}</span>
                      <span className="font-medium text-green-700">${data.total.toFixed(2)}</span>
                    </div>
                  ));
                })()}
              </div>
            )}
          </CardContent>
        </Card>
        
        <Card className="border-2">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Outgoing Payments</p>
                <p className="text-3xl font-bold text-red-600">${totalOutgoing.toFixed(2)}</p>
              </div>
              <TrendingDown className="h-10 w-10 text-red-600 opacity-50" />
            </div>
          </CardContent>
        </Card>
        
        <Card className={`border-2 ${balance >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Balance</p>
                <p className={`text-3xl font-bold ${balance >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                  ${Math.abs(balance).toFixed(2)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {balance >= 0 ? 'Profit' : 'Loss'}
                </p>
              </div>
              <DollarSign className={`h-10 w-10 opacity-50 ${balance >= 0 ? 'text-green-700' : 'text-red-700'}`} />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Calendar */}
      <Card className="border-2 shadow-card">
        <CardContent className="pt-6">
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
              <div key={`empty-${idx}`} className="min-h-[120px] bg-muted/20 rounded-lg"></div>
            ))}

            {/* Days of month */}
            {days.map(day => {
              const dayEvents = getEventsForDay(day);
              const phoenixDayEvents = getPhoenixEventsForDay(day);
              const isToday = isSameDay(day, new Date());
              const canAddEvent = selectedVenue !== 'all' && dayEvents.length === 0;

              return (
                <div
                  key={day.toString()}
                  onClick={() => canAddEvent && handleDateClick(day)}
                  className={`min-h-[120px] border-2 rounded-lg p-2 transition-all ${
                    isToday ? 'border-primary bg-primary/5' : 'border-border bg-card'
                  } ${canAddEvent ? 'cursor-pointer hover:border-blue-500 hover:bg-blue-50 hover:shadow-md' : ''}`}
                >
                  <div className={`text-sm font-semibold mb-2 flex items-center justify-between ${isToday ? 'text-primary' : 'text-foreground'}`}>
                    <span>{format(day, 'd')}</span>
                    {canAddEvent && (
                      <Plus className="h-4 w-4 text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                    )}
                  </div>

                  {/* Phoenix Events Icons */}
                  {phoenixDayEvents.length > 0 && (
                    <div className="mb-2 flex flex-wrap gap-1">
                      {phoenixDayEvents.slice(0, 3).map((phoenixEvent, idx) => (
                        <div
                          key={idx}
                          className="text-lg"
                          title={`${phoenixEvent.name} at ${phoenixEvent.venue}`}
                        >
                          {phoenixEvent.icon}
                        </div>
                      ))}
                      {phoenixDayEvents.length > 3 && (
                        <span className="text-xs text-muted-foreground">+{phoenixDayEvents.length - 3}</span>
                      )}
                    </div>
                  )}
                  
                  <div className="space-y-1">
                    {dayEvents.map(event => (
                      <div
                        key={event.id}
                        className={`text-xs p-1 rounded ${EVENT_TYPE_COLORS[event.event_type]} bg-opacity-20 border border-current`}
                      >
                        <div className="font-medium truncate">{event.event_type}</div>
                        <div className="text-[10px] truncate">{format(parseISO(event.date), 'h:mm a')}</div>
                        {selectedVenue === 'all' && (
                          <div className="text-[10px] truncate flex items-center">
                            <MapPin className="h-2 w-2 mr-0.5" />
                            {getVenueName(event.venue_id)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Event Creation Dialog */}
      <Dialog open={eventDialogOpen} onOpenChange={setEventDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="text-xl flex items-center space-x-2">
              <CalendarIcon className="h-5 w-5 text-primary" />
              <span>Create Event for {selectedDate && format(selectedDate, 'MMMM d, yyyy')}</span>
            </DialogTitle>
            <DialogDescription>
              Add a new event at {getVenueName(selectedVenue)}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Event Type */}
            <div className="space-y-2">
              <Label htmlFor="event_type">Event Type *</Label>
              <Select
                value={newEvent.event_type}
                onValueChange={(value) => setNewEvent({ ...newEvent, event_type: value })}
              >
                <SelectTrigger id="event_type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Trivia">Trivia</SelectItem>
                  <SelectItem value="Music Bingo">Music Bingo</SelectItem>
                  <SelectItem value="Karaoke">Karaoke</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Start Time */}
            <div className="space-y-2">
              <Label htmlFor="start_time">Start Time *</Label>
              <div className="flex items-center space-x-2">
                <Clock className="h-5 w-5 text-muted-foreground" />
                <Input
                  id="start_time"
                  type="time"
                  value={newEvent.start_time}
                  onChange={(e) => setNewEvent({ ...newEvent, start_time: e.target.value })}
                  className="flex-1"
                />
              </div>
            </div>

            {/* Event Info */}
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg space-y-2">
              <p className="text-sm font-semibold text-blue-900">Event Details:</p>
              <ul className="text-sm text-blue-800 space-y-1">
                <li>• Title: {newEvent.event_type} Night</li>
                <li>• Duration: {newEvent.event_type === 'Karaoke' ? '3' : '2'} hours</li>
                <li>• Status: Available (hosts can claim immediately)</li>
              </ul>
            </div>

            {/* Pricing Info */}
            {venuePricing[selectedVenue] && (
              <div className="p-4 bg-green-50 border border-green-300 rounded-lg">
                <p className="text-sm font-semibold text-green-900 mb-1">Expected Income:</p>
                <p className="text-2xl font-bold text-green-700">
                  ${(() => {
                    const pricing = venuePricing[selectedVenue];
                    if (newEvent.event_type === 'Trivia') return pricing.trivia_price?.toFixed(2) || '0.00';
                    if (newEvent.event_type === 'Music Bingo') return pricing.music_bingo_price?.toFixed(2) || '0.00';
                    if (newEvent.event_type === 'Karaoke') return pricing.karaoke_price?.toFixed(2) || '0.00';
                    return '0.00';
                  })()}
                </p>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setEventDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateEvent}
              disabled={creatingEvent}
              className="bg-blue-500 hover:bg-blue-600 text-white"
            >
              {creatingEvent ? 'Creating...' : 'Create Event'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Event Crawler Dialog */}
      <EventCrawlerDialog
        open={crawlerDialogOpen}
        onOpenChange={setCrawlerDialogOpen}
      />

      {/* Blackout Report Dialog */}
      <BlackoutReportDialog
        open={blackoutReportOpen}
        onOpenChange={setBlackoutReportOpen}
        month={format(currentMonth, 'yyyy-MM')}
      />
    </div>
  );
};

export default MonthlyReports;
