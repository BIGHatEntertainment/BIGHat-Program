import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { DollarSign, Save, Building } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const LocationPricing = () => {
  const [venues, setVenues] = useState([]);
  const [selectedVenue, setSelectedVenue] = useState('');
  const [pricing, setPricing] = useState({
    trivia_price: '',
    music_bingo_price: '',
    karaoke_price: ''
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchVenues();
  }, []);

  useEffect(() => {
    if (selectedVenue) {
      fetchVenuePricing(selectedVenue);
    }
  }, [selectedVenue]);

  const fetchVenues = async () => {
    try {
      const response = await axios.get(`${API}/venues`);
      setVenues(response.data);
    } catch (error) {
      console.error('Error fetching venues:', error);
      toast.error('Failed to load venues');
    }
  };

  const fetchVenuePricing = async (venueId) => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/venue_pricing/${venueId}`);
      setPricing({
        trivia_price: response.data.trivia_price || '',
        music_bingo_price: response.data.music_bingo_price || '',
        karaoke_price: response.data.karaoke_price || ''
      });
    } catch (error) {
      console.error('Error fetching venue pricing:', error);
      toast.error('Failed to load pricing');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selectedVenue) {
      toast.error('Please select a venue');
      return;
    }

    setSaving(true);
    try {
      const data = {
        venue_id: selectedVenue,
        trivia_price: parseFloat(pricing.trivia_price) || 0,
        music_bingo_price: parseFloat(pricing.music_bingo_price) || 0,
        karaoke_price: parseFloat(pricing.karaoke_price) || 0
      };

      await axios.post(`${API}/venue_pricing`, data);
      toast.success('Pricing saved successfully');
    } catch (error) {
      console.error('Error saving pricing:', error);
      toast.error('Failed to save pricing');
    } finally {
      setSaving(false);
    }
  };

  const getVenueName = () => {
    const venue = venues.find(v => v.id === selectedVenue);
    return venue ? venue.name : '';
  };

  return (
    <div className="space-y-6">
      <Card className="border-2 shadow-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl flex items-center space-x-2">
                <DollarSign className="h-6 w-6 text-primary" />
                <span>Location Pricing</span>
              </CardTitle>
              <CardDescription>Set pricing for each venue by event type</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Venue Selection */}
          <div className="space-y-2">
            <Label>Select Location</Label>
            <Select value={selectedVenue} onValueChange={setSelectedVenue}>
              <SelectTrigger className="w-full sm:w-96">
                <SelectValue placeholder="Choose a venue..." />
              </SelectTrigger>
              <SelectContent>
                {venues.map(venue => (
                  <SelectItem key={venue.id} value={venue.id}>
                    {venue.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Pricing Form */}
          {selectedVenue && (
            <Card className="border-2">
              <CardHeader>
                <CardTitle className="text-lg flex items-center space-x-2">
                  <Building className="h-5 w-5 text-primary" />
                  <span>Pricing for {getVenueName()}</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-4 border-primary mx-auto"></div>
                    <p className="text-muted-foreground mt-2">Loading pricing...</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    {/* Trivia Price */}
                    <div className="space-y-2">
                      <Label htmlFor="trivia_price" className="text-base font-semibold">
                        Trivia Events
                      </Label>
                      <div className="flex items-center space-x-2">
                        <span className="text-2xl font-bold">$</span>
                        <Input
                          id="trivia_price"
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          value={pricing.trivia_price}
                          onChange={(e) => setPricing({ ...pricing, trivia_price: e.target.value })}
                          className="w-48 text-lg"
                        />
                        <span className="text-sm text-muted-foreground">per event</span>
                      </div>
                    </div>

                    {/* Music Bingo Price */}
                    <div className="space-y-2">
                      <Label htmlFor="music_bingo_price" className="text-base font-semibold">
                        Music Bingo Events
                      </Label>
                      <div className="flex items-center space-x-2">
                        <span className="text-2xl font-bold">$</span>
                        <Input
                          id="music_bingo_price"
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          value={pricing.music_bingo_price}
                          onChange={(e) => setPricing({ ...pricing, music_bingo_price: e.target.value })}
                          className="w-48 text-lg"
                        />
                        <span className="text-sm text-muted-foreground">per event</span>
                      </div>
                    </div>

                    {/* Karaoke Price */}
                    <div className="space-y-2">
                      <Label htmlFor="karaoke_price" className="text-base font-semibold">
                        Karaoke Events
                      </Label>
                      <div className="flex items-center space-x-2">
                        <span className="text-2xl font-bold">$</span>
                        <Input
                          id="karaoke_price"
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          value={pricing.karaoke_price}
                          onChange={(e) => setPricing({ ...pricing, karaoke_price: e.target.value })}
                          className="w-48 text-lg"
                        />
                        <span className="text-sm text-muted-foreground">per event</span>
                      </div>
                    </div>

                    {/* Save Button */}
                    <div className="pt-4 border-t border-border">
                      <Button
                        onClick={handleSave}
                        disabled={saving}
                        className="bg-blue-500 hover:bg-blue-600 text-white w-full sm:w-auto"
                      >
                        <Save className="h-4 w-4 mr-2" />
                        {saving ? 'Saving...' : 'Save Pricing'}
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {!selectedVenue && (
            <div className="text-center py-12 text-muted-foreground">
              <DollarSign className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Select a location to set pricing</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Info Card */}
      <Card className="border-2 bg-blue-50">
        <CardContent className="pt-6">
          <div className="space-y-2 text-sm">
            <p className="font-semibold text-foreground">💡 About Location Pricing:</p>
            <ul className="list-disc list-inside space-y-1 text-muted-foreground">
              <li>Set the flat rate you charge each venue per event type</li>
              <li>Prices are locked in based on when the venue joined</li>
              <li>These rates are used to calculate expected income in Monthly Reports</li>
              <li>You can edit pricing anytime to reflect contract changes</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default LocationPricing;
