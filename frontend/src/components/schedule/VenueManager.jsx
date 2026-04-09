import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Plus, Pencil, Trash2, MapPin, Building } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Checkbox } from '../ui/checkbox';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const VenueManager = () => {
  const [venues, setVenues] = useState([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingVenue, setEditingVenue] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    address: '',
    city: 'Phoenix',
    state: 'AZ',
    notes: '',
    venue_pays_host_directly: false
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchVenues();
  }, []);

  const fetchVenues = async () => {
    try {
      const response = await axios.get(`${API}/venues`);
      setVenues(response.data);
    } catch (error) {
      console.error('Error fetching venues:', error);
      toast.error('Failed to load venues');
    }
  };

  const handleOpenDialog = (venue = null) => {
    if (venue) {
      setEditingVenue(venue);
      setFormData({
        name: venue.name,
        address: venue.address,
        city: venue.city,
        state: venue.state,
        notes: venue.notes || '',
        venue_pays_host_directly: venue.venue_pays_host_directly || false
      });
    } else {
      setEditingVenue(null);
      setFormData({
        name: '',
        address: '',
        city: 'Phoenix',
        state: 'AZ',
        notes: '',
        venue_pays_host_directly: false
      });
    }
    setDialogOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (editingVenue) {
        await axios.put(`${API}/venues/${editingVenue.id}`, formData);
        toast.success('Venue updated successfully');
      } else {
        await axios.post(`${API}/venues`, formData);
        toast.success('Venue added successfully');
      }
      setDialogOpen(false);
      fetchVenues();
    } catch (error) {
      console.error('Error saving venue:', error);
      toast.error('Failed to save venue');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (venueId) => {
    if (!window.confirm('Are you sure you want to delete this venue?')) return;

    try {
      await axios.delete(`${API}/venues/${venueId}`);
      toast.success('Venue deleted successfully');
      fetchVenues();
    } catch (error) {
      console.error('Error deleting venue:', error);
      toast.error('Failed to delete venue');
    }
  };

  return (
    <div className="space-y-6">
      <Card className="border-2 shadow-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl flex items-center space-x-2">
                <Building className="h-6 w-6 text-primary" />
                <span>Venue Management</span>
              </CardTitle>
              <CardDescription>Add, edit, or remove venues</CardDescription>
            </div>
            <Button
              onClick={() => handleOpenDialog()}
              className="bg-blue-500 hover:bg-blue-600 text-white transition-smooth"
              type="button"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Venue
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {venues.map((venue) => (
              <Card key={venue.id} className="hover:shadow-lg transition-smooth border-2">
                <CardContent className="pt-6">
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-semibold text-lg text-white">{venue.name}</h3>
                      </div>
                      <div className="flex space-x-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleOpenDialog(venue)}
                          className="h-8 w-8 hover:bg-primary/10"
                        >
                          <Pencil className="h-4 w-4 text-primary" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(venue.id)}
                          className="h-8 w-8 hover:bg-destructive/10"
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-2 text-sm text-gray-400">
                      <div className="flex items-start space-x-2">
                        <MapPin className="h-4 w-4 mt-0.5 flex-shrink-0" />
                        <div>
                          <p>{venue.address}</p>
                          <p>{venue.city}, {venue.state}</p>
                        </div>
                      </div>
                      {venue.notes && (
                        <div className="pt-2 border-t border-[#1e293b]">
                          <p className="text-xs italic">{venue.notes}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          {venues.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <Building className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No venues added yet</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent style={{ backgroundColor: "#0d1220", border: "1px solid rgba(251, 221, 104, 0.2)" }} className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>{editingVenue ? 'Edit Venue' : 'Add New Venue'}</DialogTitle>
            <DialogDescription>
              {editingVenue ? 'Update venue information' : 'Enter the new venue details'}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit}>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">Venue Name *</Label>
                <Input
                  id="name"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="The Sports Bar"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="address">Street Address *</Label>
                <Input
                  id="address"
                  value={formData.address}
                  onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                  placeholder="123 Main Street"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="city">City *</Label>
                  <Input
                    id="city"
                    value={formData.city}
                    onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                    placeholder="Phoenix"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="state">State *</Label>
                  <Input
                    id="state"
                    value={formData.state}
                    onChange={(e) => setFormData({ ...formData, state: e.target.value })}
                    placeholder="AZ"
                    required
                    maxLength={2}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="notes">Notes (Optional)</Label>
                <Textarea
                  id="notes"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  placeholder="Parking instructions, contact info, etc."
                  rows={3}
                />
              </div>
              
              {/* Franchise Checkbox */}
              <div className="flex items-center space-x-2 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <Checkbox
                  id="venue_pays_host_directly"
                  checked={formData.venue_pays_host_directly}
                  onCheckedChange={(checked) => setFormData({ ...formData, venue_pays_host_directly: checked })}
                />
                <div className="flex-1">
                  <Label 
                    htmlFor="venue_pays_host_directly" 
                    className="text-sm font-semibold cursor-pointer"
                  >
                    Franchise Location (Venue Pays Host Directly)
                  </Label>
                  <p className="text-xs text-gray-400 mt-0.5">
                    For locations like Monkey Pants where the venue pays the host directly. Income only counts when Nicholas Sellards claims events.
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
                {loading ? 'Saving...' : editingVenue ? 'Update' : 'Add Venue'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default VenueManager;
