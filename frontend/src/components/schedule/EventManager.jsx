import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, parseISO } from 'date-fns';
import { Plus, Pencil, Trash2, Calendar, MapPin, Clock, UserMinus, Star, UserPlus } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const EVENT_TYPES = ['Trivia', 'Karaoke', 'Music Bingo', 'Special'];

const EVENT_TYPE_COLORS = {
  'Trivia': 'bg-green-500',
  'Karaoke': 'bg-pink-500',
  'Music Bingo': 'bg-blue-500',
  'Special': 'bg-purple-500',
};

const EventManager = () => {
  const [events, setEvents] = useState([]);
  const [venues, setVenues] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [assignDialogOpen, setAssignDialogOpen] = useState(false);
  const [assigningEvent, setAssigningEvent] = useState(null);
  const [selectedHostId, setSelectedHostId] = useState('');
  const [editingEvent, setEditingEvent] = useState(null);
  const [formData, setFormData] = useState({
    title: '',
    event_type: 'Trivia',
    venue_id: '',
    date: '',
    time: '',
    duration_hours: 2,
    pay_rate: '',
    notes: '',
    is_special_event: false
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [eventsRes, venuesRes, employeesRes] = await Promise.all([
        axios.get(`${API}/events?include_past=true`),
        axios.get(`${API}/venues`),
        axios.get(`${API}/employees`)
      ]);
      setEvents(eventsRes.data);
      setVenues(venuesRes.data);
      setEmployees(employeesRes.data);
    } catch (error) {
      console.error('Error fetching data:', error);
      toast.error('Failed to load data');
    }
  };

  const handleOpenDialog = (event = null) => {
    if (event) {
      const eventDate = parseISO(event.date);
      setEditingEvent(event);
      setFormData({
        title: event.title,
        event_type: event.event_type,
        venue_id: event.venue_id,
        date: format(eventDate, 'yyyy-MM-dd'),
        time: format(eventDate, 'HH:mm'),
        duration_hours: event.duration_hours,
        pay_rate: event.pay_rate || '',
        notes: event.notes || '',
        is_special_event: event.is_special_event || false
      });
    } else {
      setEditingEvent(null);
      setFormData({
        title: '',
        event_type: 'Trivia',
        venue_id: '',
        date: '',
        time: '',
        duration_hours: 2,
        pay_rate: '',
        notes: '',
        is_special_event: false
      });
    }
    setDialogOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      // Combine date and time
      const dateTime = new Date(`${formData.date}T${formData.time}`);
      
      const payload = {
        title: formData.title,
        event_type: formData.event_type,
        venue_id: formData.venue_id,
        date: dateTime.toISOString(),
        duration_hours: parseFloat(formData.duration_hours),
        pay_rate: formData.pay_rate ? parseFloat(formData.pay_rate) : null,
        notes: formData.notes || null,
        is_special_event: formData.is_special_event
      };

      if (editingEvent) {
        await axios.put(`${API}/events/${editingEvent.id}`, payload);
        toast.success('Event updated successfully');
      } else {
        await axios.post(`${API}/events`, payload);
        toast.success('Event added successfully');
      }
      setDialogOpen(false);
      fetchData();
    } catch (error) {
      console.error('Error saving event:', error);
      toast.error(error.response?.data?.detail || 'Failed to save event');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (eventId) => {
    if (!window.confirm('Are you sure you want to delete this event?')) return;

    try {
      await axios.delete(`${API}/events/${eventId}`);
      toast.success('Event deleted successfully');
      fetchData();
    } catch (error) {
      console.error('Error deleting event:', error);
      toast.error('Failed to delete event');
    }
  };

  const handleUnclaim = async (eventId, eventTitle) => {
    if (!window.confirm(`Are you sure you want to unclaim "${eventTitle}"? This will make it available for other employees to claim.`)) return;

    try {
      await axios.post(`${API}/events/${eventId}/unclaim`);
      toast.success('Event unclaimed successfully');
      fetchData();
    } catch (error) {
      console.error('Error unclaiming event:', error);
      toast.error('Failed to unclaim event');
    }
  };

  const handleOpenAssignDialog = (event) => {
    setAssigningEvent(event);
    setSelectedHostId(event.claimed_by || '');
    setAssignDialogOpen(true);
  };

  const handleAssignHost = async () => {
    if (!selectedHostId) {
      toast.error('Please select a host');
      return;
    }

    setLoading(true);
    try {
      // Use the claim endpoint with admin override
      await axios.post(`${API}/events/${assigningEvent.id}/admin-assign`, {
        employee_id: selectedHostId
      });
      toast.success('Host assigned successfully');
      setAssignDialogOpen(false);
      setAssigningEvent(null);
      setSelectedHostId('');
      fetchData();
    } catch (error) {
      console.error('Error assigning host:', error);
      toast.error(error.response?.data?.detail || 'Failed to assign host');
    } finally {
      setLoading(false);
    }
  };

  const getVenueName = (venueId) => {
    const venue = venues.find(v => v.id === venueId);
    return venue ? venue.name : 'Unknown';
  };

  const getEmployeeName = (employeeId) => {
    const employee = employees.find(e => e.id === employeeId);
    return employee ? employee.name : 'Unknown';
  };

  return (
    <div className="space-y-6">
      <Card className="border-2 shadow-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl flex items-center space-x-2">
                <Calendar className="h-6 w-6 text-primary" />
                <span>Event Management</span>
              </CardTitle>
              <CardDescription>Create, edit, or remove events</CardDescription>
            </div>
            <Button
              onClick={() => handleOpenDialog()}
              className="bg-blue-500 hover:bg-blue-600 text-white transition-smooth"
              disabled={venues.length === 0}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Event
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {venues.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <Calendar className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Please add venues first before creating events</p>
            </div>
          ) : (
            <div className="space-y-4">
              {events.map((event) => {
                const eventDate = parseISO(event.date);
                return (
                  <Card key={event.id} className="hover:shadow-lg transition-smooth border-2">
                    <CardContent className="pt-6">
                      <div className="flex items-start justify-between">
                        <div className="flex-1 space-y-3">
                          <div className="flex items-center space-x-3">
                            <Badge className={`${EVENT_TYPE_COLORS[event.event_type]} text-white`}>
                              {event.event_type}
                            </Badge>
                            {event.is_special_event && (
                              <Star className="h-5 w-5 text-yellow-500 fill-yellow-500" />
                            )}
                            <h3 className="font-semibold text-lg text-white">{event.title}</h3>
                            {event.status === 'claimed' && (
                              <Badge variant="secondary">Claimed</Badge>
                            )}
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm text-gray-400">
                            <div className="flex items-center space-x-2">
                              <Calendar className="h-4 w-4" />
                              <span>{format(eventDate, 'EEEE, MMM d, yyyy')}</span>
                            </div>
                            <div className="flex items-center space-x-2">
                              <Clock className="h-4 w-4" />
                              <span>{format(eventDate, 'h:mm a')} ({event.duration_hours}h)</span>
                            </div>
                            <div className="flex items-center space-x-2">
                              <MapPin className="h-4 w-4" />
                              <span>{getVenueName(event.venue_id)}</span>
                            </div>
                            {event.pay_rate && (
                              <div className="font-medium text-white">
                                ${event.pay_rate}/hour
                              </div>
                            )}
                          </div>
                          {event.notes && (
                            <p className="text-sm text-gray-400 italic">{event.notes}</p>
                          )}
                          {event.claimed_by && (
                            <div className="flex items-center space-x-2 pt-2 border-t border-[#1e293b]">
                              <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-300">
                                Claimed by: {getEmployeeName(event.claimed_by)}
                              </Badge>
                            </div>
                          )}
                        </div>
                        <div className="flex flex-col space-y-1 ml-4">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleOpenAssignDialog(event)}
                            className="h-8 w-8 hover:bg-green-100"
                            title="Assign host"
                          >
                            <UserPlus className="h-4 w-4 text-green-600" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleOpenDialog(event)}
                            className="h-8 w-8 hover:bg-primary/10"
                            title="Edit event"
                          >
                            <Pencil className="h-4 w-4 text-primary" />
                          </Button>
                          {event.claimed_by && (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleUnclaim(event.id, event.title)}
                              className="h-8 w-8 hover:bg-orange-100"
                              title="Unclaim event"
                            >
                              <UserMinus className="h-4 w-4 text-orange-600" />
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleDelete(event.id)}
                            className="h-8 w-8 hover:bg-destructive/10"
                            title="Delete event"
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
              {events.length === 0 && (
                <div className="text-center py-12 text-gray-400">
                  <Calendar className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No events added yet</p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent style={{ backgroundColor: "#0d1220", border: "1px solid rgba(251, 221, 104, 0.2)" }} className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingEvent ? 'Edit Event' : 'Add New Event'}</DialogTitle>
            <DialogDescription>
              {editingEvent ? 'Update event information' : 'Create a new event'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="title">Event Title *</Label>
                <Input
                  id="title"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  placeholder="Tuesday Night Trivia"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="event_type">Event Type *</Label>
                <Select
                  value={formData.event_type}
                  onValueChange={(value) => setFormData({ ...formData, event_type: value })}
                >
                  <SelectTrigger id="event_type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {EVENT_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {type}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="venue_id">Venue *</Label>
                <Select
                  value={formData.venue_id}
                  onValueChange={(value) => setFormData({ ...formData, venue_id: value })}
                  required
                >
                  <SelectTrigger id="venue_id">
                    <SelectValue placeholder="Select a venue" />
                  </SelectTrigger>
                  <SelectContent>
                    {venues.map((venue) => (
                      <SelectItem key={venue.id} value={venue.id}>
                        {venue.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="date">Date *</Label>
                  <Input
                    id="date"
                    type="date"
                    value={formData.date}
                    onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="time">Time *</Label>
                  <Input
                    id="time"
                    type="time"
                    value={formData.time}
                    onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                    required
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="duration_hours">Duration (hours) *</Label>
                  <Input
                    id="duration_hours"
                    type="number"
                    step="0.5"
                    min="0.5"
                    value={formData.duration_hours}
                    onChange={(e) => setFormData({ ...formData, duration_hours: e.target.value })}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="pay_rate">Pay Rate ($/hour)</Label>
                  <Input
                    id="pay_rate"
                    type="number"
                    step="0.01"
                    min="0"
                    value={formData.pay_rate}
                    onChange={(e) => setFormData({ ...formData, pay_rate: e.target.value })}
                    placeholder="Optional"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="notes">Notes (Optional)</Label>
                <Textarea
                  id="notes"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  placeholder="Special instructions, equipment needs, etc."
                  rows={3}
                />
              </div>
              
              {/* Special Event Checkbox */}
              <div className="flex items-center space-x-3 p-4 bg-yellow-50 border-2 border-yellow-300 rounded-lg">
                <Checkbox
                  id="is_special_event"
                  checked={formData.is_special_event}
                  onCheckedChange={(checked) => setFormData({ ...formData, is_special_event: checked })}
                />
                <div className="flex-1">
                  <Label 
                    htmlFor="is_special_event" 
                    className="text-sm font-medium cursor-pointer flex items-center space-x-2"
                  >
                    <Star className="h-4 w-4 text-yellow-600 fill-yellow-500" />
                    <span>Special Event (Giveaway/Promotion)</span>
                  </Label>
                  <p className="text-xs text-gray-400 mt-1">
                    Displays a yellow star on the schedule to highlight this event
                  </p>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={loading}
                className="bg-blue-500 hover:bg-blue-600 text-white"
              >
                {loading ? 'Saving...' : editingEvent ? 'Update' : 'Create Event'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Assign Host Dialog */}
      <Dialog open={assignDialogOpen} onOpenChange={setAssignDialogOpen}>
        <DialogContent style={{ backgroundColor: "#0d1220", border: "1px solid rgba(251, 221, 104, 0.2)" }} className="sm:max-w-[450px]">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <UserPlus className="h-5 w-5 text-green-600" />
              <span>Assign Host to Event</span>
            </DialogTitle>
            <DialogDescription>
              Select an employee to assign as the host for this event
            </DialogDescription>
          </DialogHeader>
          
          {assigningEvent && (
            <div className="py-4 space-y-4">
              {/* Event Info */}
              <div className="bg-[#111827] border border-[#1e293b] rounded-lg p-3">
                <div className="font-medium text-gray-800">{assigningEvent.title}</div>
                <div className="text-sm text-gray-300 mt-1">
                  {format(parseISO(assigningEvent.date), 'EEEE, MMM d, yyyy')} at {format(parseISO(assigningEvent.date), 'h:mm a')}
                </div>
                <div className="text-sm text-gray-300">
                  {getVenueName(assigningEvent.venue_id)}
                </div>
                {assigningEvent.claimed_by && (
                  <div className="text-sm text-orange-600 mt-2">
                    Currently assigned to: {getEmployeeName(assigningEvent.claimed_by)}
                  </div>
                )}
              </div>

              {/* Host Selection */}
              <div className="space-y-2">
                <Label htmlFor="assign-host">Select Host *</Label>
                <Select
                  value={selectedHostId}
                  onValueChange={setSelectedHostId}
                >
                  <SelectTrigger id="assign-host">
                    <SelectValue placeholder="Choose an employee" />
                  </SelectTrigger>
                  <SelectContent>
                    {employees
                      .sort((a, b) => a.name.localeCompare(b.name))
                      .map((employee) => (
                        <SelectItem key={employee.id} value={employee.id}>
                          {employee.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setAssignDialogOpen(false);
                setAssigningEvent(null);
                setSelectedHostId('');
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleAssignHost}
              disabled={loading || !selectedHostId}
              className="bg-green-500 hover:bg-green-600 text-white"
            >
              {loading ? 'Assigning...' : 'Assign Host'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default EventManager;
