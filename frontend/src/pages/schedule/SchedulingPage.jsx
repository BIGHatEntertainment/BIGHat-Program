import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { format, startOfWeek, addDays, isSameDay, parseISO, isAfter } from 'date-fns';
import { Calendar, Clock, MapPin, User, ChevronLeft, ChevronRight, Settings, TrendingUp, Star, DollarSign, Ban, UserCircle, Lock } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Card, CardContent } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import ClaimEventDialog from '../../components/schedule/ClaimEventDialog';
import EmployeeSelector from '../../components/schedule/EmployeeSelector';
import PaymentBonuses from '../../components/schedule/PaymentBonuses';
import { useAuth } from '../../context/AuthContext';
import PasswordConfirmDialog from '../../components/schedule/PasswordConfirmDialog';
import EventDetailDialog from '../../components/schedule/EventDetailDialog';
import MonthlyCalendarDialog from '../../components/schedule/MonthlyCalendarDialog';
import BlackoutCalendarDialog from '../../components/schedule/BlackoutCalendarDialog';
import PageHeader from '../../components/PageHeader';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const EVENT_TYPE_COLORS = {
  'Trivia': { bg: 'bg-green-50', border: 'border-green-400', text: 'text-green-700', badge: 'bg-green-500' },
  'Karaoke': { bg: 'bg-pink-50', border: 'border-pink-400', text: 'text-pink-700', badge: 'bg-pink-500' },
  'Music Bingo': { bg: 'bg-blue-50', border: 'border-blue-400', text: 'text-blue-700', badge: 'bg-blue-500' },
  'Special': { bg: 'bg-purple-50', border: 'border-purple-400', text: 'text-purple-700', badge: 'bg-purple-500' },
};

const SchedulingPage = () => {
  const { user: hubUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [events, setEvents] = useState([]);
  const [venues, setVenues] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [showCalendar, setShowCalendar] = useState(false);
  const [monthlyCalendarOpen, setMonthlyCalendarOpen] = useState(false);
  const [blackoutCalendarOpen, setBlackoutCalendarOpen] = useState(false);
  const [claimDialogOpen, setClaimDialogOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [showBonuses, setShowBonuses] = useState(null); // event id to show bonuses for
  const [loading, setLoading] = useState(true);
  const [loggedInHost, setLoggedInHost] = useState(null);
  const [passwordConfirmOpen, setPasswordConfirmOpen] = useState(false);
  const [passwordAction, setPasswordAction] = useState(null); // { type: 'claim' | 'unclaim', event: eventObj }
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [selectedEventDetail, setSelectedEventDetail] = useState(null);
  const [authChecked, setAuthChecked] = useState(false); // Track if we've checked auth state
  const [claimEligibility, setClaimEligibility] = useState({}); // {event_id: {status, primary_employee_id, opens_at}}

  // SSO: Auto-login using hub auth
  useEffect(() => {
    const autoLogin = async () => {
      const storedHost = sessionStorage.getItem('loggedInHost');
      if (storedHost) {
        try { const host = JSON.parse(storedHost); setLoggedInHost(host); setSelectedEmployee(host.id); setAuthChecked(true); return; } catch (e) { console.warn('[Schedule] Invalid stored host:', e.message); sessionStorage.removeItem('loggedInHost'); }
      }
      if (hubUser?.email) {
        try {
          const res = await axios.get(`${API}/employees`);
          const match = res.data.find(e => e.email.toLowerCase() === hubUser.email.toLowerCase());
          if (match) {
            const hostData = { id: match.id, name: match.name, email: match.email, is_admin: match.is_admin || hubUser.role === 'admin' || hubUser.role === 'master_admin' };
            setLoggedInHost(hostData); setSelectedEmployee(match.id); sessionStorage.setItem('loggedInHost', JSON.stringify(hostData));
          } else {
            const hostData = { id: hubUser.id, name: hubUser.name, email: hubUser.email, is_admin: hubUser.role === 'admin' || hubUser.role === 'master_admin' };
            setLoggedInHost(hostData); setSelectedEmployee(hubUser.id); sessionStorage.setItem('loggedInHost', JSON.stringify(hostData));
          }
        } catch (err) { console.warn('[Schedule] Auto-login failed:', err.message); }
      }
      setAuthChecked(true);
    };
    autoLogin();
  }, [hubUser]);


  // Fetch data after auth check is complete
  useEffect(() => {
    if (authChecked) {
      fetchData();
    }
  }, [authChecked]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [eventsRes, venuesRes, employeesRes, eligibilityRes] = await Promise.all([
        axios.get(`${API}/events`),
        axios.get(`${API}/venues`),
        axios.get(`${API}/employees`),
        axios.get(`${API}/events/claim-eligibility`)
      ]);
      setEvents(eventsRes.data);
      setVenues(venuesRes.data);
      setEmployees(employeesRes.data);
      setClaimEligibility(eligibilityRes.data);
    } catch (error) {
      // Don't toast on a fresh install where the schedule collections
      // are simply empty — the merchant correctly noted this is the
      // expected first-run state. Only show the error when the failure
      // is something other than "no data yet" (4xx auth, 5xx server).
      console.error('Error fetching data:', error);
      const status = error?.response?.status;
      if (status && status !== 404) {
        toast.error('Failed to load data');
      }
    } finally {
      setLoading(false);
    }
  };

  const getWeekStart = (date) => {
    return startOfWeek(date, { weekStartsOn: 0 });
  };

  const getCurrentWeekDays = () => {
    const weekStart = getWeekStart(selectedDate);
    return Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  };

  const getEventsForDay = (day) => {
    return events.filter(event => {
      const eventDate = parseISO(event.date);
      return isSameDay(eventDate, day) && isAfter(eventDate, new Date());
    }).sort((a, b) => new Date(a.date) - new Date(b.date));
  };

  const getVenueName = (venueId) => {
    const venue = venues.find(v => v.id === venueId);
    return venue ? venue.name : 'Unknown Venue';
  };

  const getEmployeeName = (employeeId) => {
    const employee = employees.find(e => e.id === employeeId);
    return employee ? employee.name : 'Unknown';
  };

  const handleClaimEvent = (event) => {
    if (!loggedInHost) {
      toast.error('Please login first');
      return;
    }
    setSelectedEvent(event);
    setClaimDialogOpen(true);
  };

  const confirmClaimEvent = async () => {
    setClaimDialogOpen(false);
    // Show password confirmation dialog
    setPasswordAction({ type: 'claim', event: selectedEvent });
    setPasswordConfirmOpen(true);
  };

  const executeClaim = async () => {
    try {
      await axios.post(`${API}/events/${passwordAction.event.id}/claim`, {
        employee_id: loggedInHost.id
      });
      toast.success('Event claimed successfully!');
      setSelectedEvent(null);
      setPasswordAction(null);
      fetchData();
    } catch (error) {
      console.error('Error claiming event:', error);
      toast.error(error.response?.data?.detail || 'Failed to claim event');
    }
  };

  const handleUnclaimEvent = async (event) => {
    // Show password confirmation dialog
    setPasswordAction({ type: 'unclaim', event: event });
    setPasswordConfirmOpen(true);
  };

  const executeUnclaim = async () => {
    try {
      const response = await axios.post(`${API}/events/${passwordAction.event.id}/unclaim`);
      console.log('Unclaim successful:', response.data);
      toast.success('Event unclaimed successfully');
      setPasswordAction(null);
      await fetchData();
    } catch (error) {
      console.error('Error unclaiming event:', error);
      toast.error('Failed to unclaim event');
    }
  };

  const navigateWeek = (direction) => {
    setSelectedDate(prev => addDays(prev, direction * 7));
  };

  const goToToday = () => {
    setSelectedDate(new Date());
  };

  const weekDays = getCurrentWeekDays();

  const handleLoginSuccess = (host) => {
    setLoggedInHost(host);
    setSelectedEmployee(host.id);
  };

  const handleLogout = () => {
    // Kept for backwards-compat with the old "Logout" button — now wired
    // only to clear the schedule-only session.
    sessionStorage.removeItem('loggedInHost');
    navigate('/');
    toast.success('Returned to dashboard');
  };

  // Show loading while checking auth state OR loading data
  if (!authChecked || loading) {
    return (
      <div className="min-h-screen gradient-hero flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-primary mx-auto mb-4"></div>
          <p className="text-lg text-muted-foreground">
            {!authChecked ? 'Checking authentication...' : 'Loading schedule...'}
          </p>
        </div>
      </div>
    );
  }

  // Show loading if SSO hasn't resolved yet
  if (!loggedInHost) {
    return (<div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-purple-50"><div className="text-center"><img src="/hat-logo.png" alt="Loading" className="w-16 h-16 mx-auto mb-4 animate-pulse" /><p className="text-sm text-gray-500">Setting up your schedule...</p></div></div>);
  }

  return (
    <div className="min-h-screen force-light" style={{ background: "linear-gradient(135deg, #e8eaf6 0%, #f3e5f5 50%, #e0f2fe 100%)" }}>
      {/* Unified PageHeader (Back + Home pinned to identical positions
          across every sub-page). The schedule-specific Profile / Admin
          actions slot in as `actions` so they sit next to Home but
          never displace it. */}
      <PageHeader
        title="Event Scheduler"
        subtitle={loggedInHost?.name ? `Welcome, ${loggedInHost.name}` : 'Welcome'}
        variant="light"
        actions={(
          <>
            <Button
              onClick={() => navigate('/schedule/profile')}
              variant="outline"
              size="sm"
              className="flex items-center space-x-2 hover:bg-purple-50 hover:text-purple-600 transition-smooth"
              data-testid="profile-btn"
            >
              <UserCircle className="h-4 w-4" />
              <span className="hidden sm:inline ml-1">Profile</span>
            </Button>
            {loggedInHost?.is_admin && (
              <Button
                onClick={() => navigate('/schedule/admin')}
                variant="outline"
                size="sm"
                className="flex items-center space-x-2 hover:bg-primary hover:text-primary-foreground transition-smooth"
              >
                <Settings className="h-4 w-4" />
                <span className="hidden sm:inline ml-1">Admin</span>
              </Button>
            )}
          </>
        )}
      />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

        {/* Week Navigation */}
        <div className="mb-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-2">
            <Button
              onClick={() => navigateWeek(-1)}
              variant="outline"
              size="icon"
              className="hover:bg-primary hover:text-primary-foreground transition-smooth"
            >
              <ChevronLeft className="h-5 w-5" />
            </Button>
            <Button
              onClick={goToToday}
              variant="outline"
              className="px-6 hover:bg-primary hover:text-primary-foreground transition-smooth"
            >
              Today
            </Button>
            <Button
              onClick={() => navigateWeek(1)}
              variant="outline"
              size="icon"
              className="hover:bg-primary hover:text-primary-foreground transition-smooth"
            >
              <ChevronRight className="h-5 w-5" />
            </Button>
          </div>
          
          <div className="flex items-center space-x-2">
            <h2 className="text-xl font-semibold text-foreground">
              {format(weekDays[0], 'MMM d')} - {format(weekDays[6], 'MMM d, yyyy')}
            </h2>
          </div>

          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              onClick={() => setBlackoutCalendarOpen(true)}
              className="flex items-center space-x-2 bg-gray-800 text-white hover:bg-gray-900 border-gray-800"
            >
              <Ban className="h-4 w-4" />
              <span>Blackout</span>
            </Button>
            <Button
              variant="outline"
              onClick={() => setMonthlyCalendarOpen(true)}
              className="flex items-center space-x-2 hover:bg-primary hover:text-primary-foreground transition-smooth"
            >
              <Calendar className="h-4 w-4" />
              <span>Calendar</span>
            </Button>
          </div>
        </div>

        {/* Weekly Events Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-7 gap-4">
          {weekDays.map((day, idx) => {
            const dayEvents = getEventsForDay(day);
            const isToday = isSameDay(day, new Date());

            return (
              <div key={idx} className="flex flex-col">
                <div className={`text-center p-3 rounded-t-xl border-2 ${
                  isToday
                    ? 'bg-primary text-primary-foreground border-primary shadow-glow'
                    : 'bg-card border-border'
                }`}>
                  <div className="text-sm font-medium">{format(day, 'EEE')}</div>
                  <div className={`text-2xl font-bold ${
                    isToday ? 'text-primary-foreground' : 'text-foreground'
                  }`}>
                    {format(day, 'd')}
                  </div>
                </div>

                <div className="flex-1 bg-card border-2 border-t-0 border-border rounded-b-xl p-3 space-y-3 min-h-[200px]">
                  {dayEvents.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground text-sm">
                      No events
                    </div>
                  ) : (
                    dayEvents.map((event) => {
                      const colors = EVENT_TYPE_COLORS[event.event_type] || EVENT_TYPE_COLORS['Special'];
                      const isClaimed = !!event.claimed_by;
                      const isClaimedByUser = event.claimed_by === selectedEmployee;
                      const elig = claimEligibility[event.id];
                      const isPrimaryLocked = !isClaimed && elig?.status === 'primary_only';
                      const isUserThePrimary = isPrimaryLocked && elig?.primary_employee_id === loggedInHost?.id;

                      return (
                        <Card
                          key={event.id}
                          className={`${colors.bg} ${colors.border} border-2 transition-all duration-300 hover:shadow-lg hover:scale-[1.02] cursor-pointer ${isPrimaryLocked && !isUserThePrimary ? 'opacity-75' : ''}`}
                          onClick={() => {
                            setSelectedEventDetail(event);
                            setDetailDialogOpen(true);
                          }}
                        >
                          <CardContent className="p-4 space-y-2">
                            <div className="flex items-start justify-between">
                              <div className="flex items-center space-x-1">
                                <Badge className={`${colors.badge} text-white`}>
                                  {event.event_type}
                                </Badge>
                                {event.is_special_event && (
                                  <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" title="Special Event - Giveaway/Promotion" />
                                )}
                              </div>
                              {isClaimed && (
                                <Badge variant="secondary" className="text-xs">
                                  Claimed
                                </Badge>
                              )}
                              {isPrimaryLocked && !isUserThePrimary && (
                                <Lock className="h-4 w-4 text-amber-600" title="Reserved for primary host" />
                              )}
                            </div>

                            <div className="space-y-1">
                              <div className="flex items-center text-sm text-muted-foreground">
                                <Clock className="h-3 w-3 mr-1" />
                                {format(parseISO(event.date), 'h:mm a')}
                              </div>
                              <div className="flex items-start text-sm font-medium text-foreground">
                                <MapPin className="h-3 w-3 mr-1 mt-0.5 flex-shrink-0" />
                                <span className="line-clamp-2">{getVenueName(event.venue_id)}</span>
                              </div>
                              {isClaimed && (
                                <div className="flex items-center text-sm text-muted-foreground">
                                  <User className="h-3 w-3 mr-1" />
                                  {getEmployeeName(event.claimed_by)}
                                </div>
                              )}
                            </div>

                            {!isClaimed ? (
                              isPrimaryLocked && !isUserThePrimary ? (
                                <div className="text-center space-y-1" data-testid={`primary-locked-${event.id}`}>
                                  <div className="flex items-center justify-center text-xs text-amber-700 font-medium">
                                    <Lock className="h-3 w-3 mr-1" />
                                    Reserved for {getEmployeeName(elig.primary_employee_id)}
                                  </div>
                                  <p className="text-[10px] text-amber-600">
                                    Opens {new Date(elig.opens_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                                  </p>
                                </div>
                              ) : (
                                <Button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleClaimEvent(event);
                                  }}
                                  className="w-full bg-green-600 hover:bg-green-700 text-white transition-smooth"
                                  size="sm"
                                  disabled={!selectedEmployee}
                                  data-testid={`claim-btn-${event.id}`}
                                >
                                  Claim Event
                                </Button>
                              )
                            ) : isClaimedByUser ? (
                              <div className="space-y-2">
                                <Button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleUnclaimEvent(event);
                                  }}
                                  variant="outline"
                                  className="w-full border-red-300 text-red-600 hover:bg-red-50 transition-smooth"
                                  size="sm"
                                >
                                  Unclaim
                                </Button>
                                {(event.event_type === 'Trivia' || event.event_type === 'Music Bingo' || event.event_type === 'Karaoke') && (
                                  <Button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setShowBonuses(showBonuses === event.id ? null : event.id);
                                    }}
                                    className="w-full bg-green-600 hover:bg-green-700 text-white transition-smooth"
                                    size="sm"
                                  >
                                    {showBonuses === event.id ? 'Hide' : 'Track'} Payment
                                  </Button>
                                )}
                              </div>
                            ) : (
                              <Button
                                variant="outline"
                                className="w-full cursor-not-allowed"
                                size="sm"
                                disabled
                              >
                                Unavailable
                              </Button>
                            )}
                          </CardContent>
                        </Card>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Payment Bonuses Section */}
        {showBonuses && (
          <div className="mt-6">
            <PaymentBonuses 
              event={events.find(e => e.id === showBonuses)} 
              onUpdate={fetchData}
            />
          </div>
        )}

        {/* Legend */}
        <Card className="mt-8 shadow-card border-2">
          <CardContent className="pt-6">
            <h3 className="text-lg font-semibold mb-4">Event Types</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {Object.entries(EVENT_TYPE_COLORS).map(([type, colors]) => (
                <div key={type} className="flex items-center space-x-2">
                  <div className={`w-4 h-4 rounded ${colors.badge}`}></div>
                  <span className="text-sm font-medium">{type}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Claim Dialog */}
      {selectedEvent && (
        <ClaimEventDialog
          open={claimDialogOpen}
          onOpenChange={setClaimDialogOpen}
          event={selectedEvent}
          venue={venues.find(v => v.id === selectedEvent.venue_id)}
          onConfirm={confirmClaimEvent}
        />
      )}

      {/* Password Confirmation Dialog */}
      {passwordAction && loggedInHost && (
        <PasswordConfirmDialog
          open={passwordConfirmOpen}
          onOpenChange={setPasswordConfirmOpen}
          employeeId={loggedInHost.id}
          employeeName={loggedInHost.name}
          action={passwordAction.type}
          onConfirm={passwordAction.type === 'claim' ? executeClaim : executeUnclaim}
        />
      )}

      {/* Event Detail Dialog */}
      {selectedEventDetail && (
        <EventDetailDialog
          open={detailDialogOpen}
          onOpenChange={setDetailDialogOpen}
          event={selectedEventDetail}
          venue={venues.find(v => v.id === selectedEventDetail.venue_id)}
          isClaimed={!!selectedEventDetail.claimed_by}
          isClaimedByUser={selectedEventDetail.claimed_by === loggedInHost?.id}
          onClaim={() => handleClaimEvent(selectedEventDetail)}
          onUnclaim={() => handleUnclaimEvent(selectedEventDetail)}
        />
      )}

      {/* Monthly Calendar Dialog */}
      <MonthlyCalendarDialog
        open={monthlyCalendarOpen}
        onOpenChange={setMonthlyCalendarOpen}
        events={events}
        currentUserId={loggedInHost?.id}
        onEventClick={(event) => {
          setSelectedEventDetail(event);
          setDetailDialogOpen(true);
        }}
      />

      {/* Blackout Calendar Dialog */}
      <BlackoutCalendarDialog
        open={blackoutCalendarOpen}
        onOpenChange={setBlackoutCalendarOpen}
        employeeId={loggedInHost?.id}
        employeeName={loggedInHost?.name}
        events={events.map(e => ({
          ...e,
          venue_name: venues.find(v => v.id === e.venue_id)?.name
        }))}
      />
    </div>
  );
};

export default SchedulingPage;
