import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowLeft, Shield, ShieldCheck, MapPin, Plus, Trash2, AlertTriangle, CheckCircle } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function ProfilePage() {
  const navigate = useNavigate();
  const [host, setHost] = useState(null);
  const [myRoles, setMyRoles] = useState([]);
  const [allRoles, setAllRoles] = useState([]);
  const [venues, setVenues] = useState([]);
  const [venueServices, setVenueServices] = useState({});
  const [employees, setEmployees] = useState([]);
  const [validation, setValidation] = useState(null);
  const [loading, setLoading] = useState(true);

  // Secondary sign-up form state
  const [selectedVenue, setSelectedVenue] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');

  useEffect(() => {
    const storedHost = sessionStorage.getItem('loggedInHost');
    if (!storedHost) {
      navigate('/');
      return;
    }
    setHost(JSON.parse(storedHost));
  }, [navigate]);

  const fetchData = useCallback(async () => {
    if (!host) return;
    setLoading(true);
    try {
      const [rolesRes, allRolesRes, venuesRes, servicesRes, employeesRes, validationRes] = await Promise.all([
        axios.get(`${API}/venue-roles/employee/${host.id}`),
        axios.get(`${API}/venue-roles`),
        axios.get(`${API}/venues`),
        axios.get(`${API}/venue-roles/services`),
        axios.get(`${API}/employees`),
        axios.get(`${API}/venue-roles/validate/${host.id}`)
      ]);
      setMyRoles(rolesRes.data);
      setAllRoles(allRolesRes.data);
      setVenues(venuesRes.data);
      setVenueServices(servicesRes.data);
      setEmployees(employeesRes.data);
      setValidation(validationRes.data);
    } catch (error) {
      console.error('Error fetching profile data:', error);
      toast.error('Failed to load profile data');
    } finally {
      setLoading(false);
    }
  }, [host]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const getVenueName = (venueId) => venues.find(v => v.id === venueId)?.name || 'Unknown';
  const getEmployeeName = (employeeId) => employees.find(e => e.id === employeeId)?.name || 'Unknown';

  const handleSignUpSecondary = async () => {
    if (!selectedVenue || !selectedCategory) {
      toast.error('Please select a venue and category');
      return;
    }
    try {
      await axios.post(`${API}/venue-roles`, {
        venue_id: selectedVenue,
        employee_id: host.id,
        role_category: selectedCategory,
        role_type: 'secondary'
      });
      toast.success('Signed up as secondary!');
      setSelectedVenue('');
      setSelectedCategory('');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to sign up');
    }
  };

  const handleRemoveRole = async (roleId) => {
    try {
      await axios.delete(`${API}/venue-roles/${roleId}`);
      toast.success('Role removed');
      fetchData();
    } catch (error) {
      toast.error('Failed to remove role');
    }
  };

  const myPrimaryRoles = myRoles.filter(r => r.role_type === 'primary');
  const mySecondaryRoles = myRoles.filter(r => r.role_type === 'secondary');

  // Available venues for secondary sign-up (exclude venues where user already has this role)
  const getAvailableVenuesForCategory = (category) => {
    const existingVenueIds = myRoles
      .filter(r => r.role_category === category && r.role_type === 'secondary')
      .map(r => r.venue_id);
    return Object.values(venueServices)
      .filter(vs => {
        if (category === 'trivia') return vs.offers_trivia;
        if (category === 'bingo_karaoke') return vs.offers_bingo_karaoke;
        return false;
      })
      .filter(vs => !existingVenueIds.includes(vs.venue_id));
  };

  // Get available categories for selected venue
  const getAvailableCategoriesForVenue = (venueId) => {
    const vs = venueServices[venueId];
    if (!vs) return [];
    const categories = [];
    if (vs.offers_trivia) {
      const alreadyHas = myRoles.some(r => r.venue_id === venueId && r.role_category === 'trivia' && r.role_type === 'secondary');
      if (!alreadyHas) categories.push({ value: 'trivia', label: 'Trivia' });
    }
    if (vs.offers_bingo_karaoke) {
      const alreadyHas = myRoles.some(r => r.venue_id === venueId && r.role_category === 'bingo_karaoke' && r.role_type === 'secondary');
      if (!alreadyHas) categories.push({ value: 'bingo_karaoke', label: 'Bingo/Karaoke' });
    }
    return categories;
  };

  // Venues available for secondary sign-up
  const signUpVenues = Object.values(venueServices).filter(vs => {
    const cats = getAvailableCategoriesForVenue(vs.venue_id);
    return cats.length > 0;
  });

  // For each venue, show who is primary/secondary
  const getRolesForVenue = (venueId, category) => {
    return allRoles.filter(r => r.venue_id === venueId && r.role_category === category);
  };

  if (loading || !host) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-primary"></div>
      </div>
    );
  }

  const categoryLabel = (cat) => cat === 'trivia' ? 'Trivia' : 'Bingo/Karaoke';

  return (
    <div className="min-h-screen force-light" style={{ background: "linear-gradient(135deg, #e8eaf6 0%, #f3e5f5 50%, #e0f2fe 100%)" }}>
      {/* Header */}
      <header className="bg-white border-b border-border shadow-sm sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Button onClick={() => navigate('/')} variant="ghost" size="icon" data-testid="profile-back-btn">
                <ArrowLeft className="h-5 w-5" />
              </Button>
              <div className="p-1">
                <img src="/hat-logo.png" alt="BIG Hat Entertainment" className="h-10 w-10 object-contain" />
              </div>
              <div>
                <h1 className="text-2xl sm:text-3xl font-bold text-foreground">My Profile</h1>
                <p className="text-sm text-muted-foreground">{host.name} &middot; {host.email}</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">

        {/* Validation Warning */}
        {validation && !validation.valid && (
          <Card className="border-amber-400 bg-amber-50" data-testid="validation-warning">
            <CardContent className="py-4 flex items-start space-x-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
              <div>
                <p className="font-semibold text-amber-800">{validation.message}</p>
                <p className="text-sm text-amber-700 mt-1">
                  As a primary host, you must sign up as a secondary at least one other location to ensure coverage.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {validation && validation.valid && myPrimaryRoles.length > 0 && (
          <Card className="border-green-400 bg-green-50" data-testid="validation-success">
            <CardContent className="py-4 flex items-center space-x-3">
              <CheckCircle className="h-5 w-5 text-green-600 flex-shrink-0" />
              <p className="font-semibold text-green-800">All role requirements met</p>
            </CardContent>
          </Card>
        )}

        {/* My Primary Roles */}
        <Card data-testid="primary-roles-section">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <ShieldCheck className="h-5 w-5 text-blue-600" />
              <span>My Primary Roles</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {myPrimaryRoles.length === 0 ? (
              <p className="text-muted-foreground text-sm">You are not assigned as a primary at any venue. Admins assign primary roles.</p>
            ) : (
              <div className="space-y-3">
                {myPrimaryRoles.map(role => (
                  <div key={role.id} className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border border-blue-200" data-testid={`primary-role-${role.id}`}>
                    <div className="flex items-center space-x-3">
                      <MapPin className="h-4 w-4 text-blue-600" />
                      <div>
                        <p className="font-medium text-foreground">{getVenueName(role.venue_id)}</p>
                        <Badge variant="outline" className="text-xs mt-1">{categoryLabel(role.role_category)}</Badge>
                      </div>
                    </div>
                    <Badge className="bg-blue-600 text-white">Primary</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* My Secondary Roles */}
        <Card data-testid="secondary-roles-section">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Shield className="h-5 w-5 text-gray-600" />
              <span>My Secondary Roles</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {mySecondaryRoles.length === 0 ? (
              <p className="text-muted-foreground text-sm">You haven't signed up as a secondary at any venue yet.</p>
            ) : (
              <div className="space-y-3">
                {mySecondaryRoles.map(role => (
                  <div key={role.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200" data-testid={`secondary-role-${role.id}`}>
                    <div className="flex items-center space-x-3">
                      <MapPin className="h-4 w-4 text-gray-500" />
                      <div>
                        <p className="font-medium text-foreground">{getVenueName(role.venue_id)}</p>
                        <Badge variant="outline" className="text-xs mt-1">{categoryLabel(role.role_category)}</Badge>
                      </div>
                    </div>
                    <Button variant="ghost" size="icon" onClick={() => handleRemoveRole(role.id)} className="text-red-500 hover:text-red-700 hover:bg-red-50" data-testid={`remove-secondary-${role.id}`}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {/* Sign Up as Secondary */}
            <div className="pt-4 border-t border-border">
              <h4 className="text-sm font-semibold mb-3 text-foreground">Sign Up as Secondary</h4>
              <div className="flex flex-col sm:flex-row gap-3">
                <Select value={selectedVenue} onValueChange={(v) => { setSelectedVenue(v); setSelectedCategory(''); }} data-testid="secondary-venue-select">
                  <SelectTrigger className="flex-1" data-testid="secondary-venue-trigger">
                    <SelectValue placeholder="Select venue..." />
                  </SelectTrigger>
                  <SelectContent>
                    {signUpVenues.map(vs => (
                      <SelectItem key={vs.venue_id} value={vs.venue_id}>{vs.venue_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Select value={selectedCategory} onValueChange={setSelectedCategory} disabled={!selectedVenue} data-testid="secondary-category-select">
                  <SelectTrigger className="flex-1" data-testid="secondary-category-trigger">
                    <SelectValue placeholder="Select type..." />
                  </SelectTrigger>
                  <SelectContent>
                    {selectedVenue && getAvailableCategoriesForVenue(selectedVenue).map(cat => (
                      <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <Button onClick={handleSignUpSecondary} disabled={!selectedVenue || !selectedCategory} className="flex items-center space-x-2" data-testid="sign-up-secondary-btn">
                  <Plus className="h-4 w-4" />
                  <span>Sign Up</span>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* All Venue Roles Overview */}
        <Card data-testid="venue-roles-overview">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <MapPin className="h-5 w-5 text-purple-600" />
              <span>All Venue Roles</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              {Object.values(venueServices).map(vs => {
                const triviaRoles = getRolesForVenue(vs.venue_id, 'trivia');
                const bkRoles = getRolesForVenue(vs.venue_id, 'bingo_karaoke');
                const triviaPrimary = triviaRoles.find(r => r.role_type === 'primary');
                const triviaSecondaries = triviaRoles.filter(r => r.role_type === 'secondary');
                const bkPrimary = bkRoles.find(r => r.role_type === 'primary');
                const bkSecondaries = bkRoles.filter(r => r.role_type === 'secondary');

                return (
                  <div key={vs.venue_id} className="p-4 rounded-lg border border-border bg-white" data-testid={`venue-overview-${vs.venue_id}`}>
                    <h4 className="font-semibold text-lg mb-3">{vs.venue_name}</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {vs.offers_trivia && (
                        <div className="p-3 rounded-md bg-green-50 border border-green-200">
                          <p className="text-sm font-semibold text-green-800 mb-2">Trivia</p>
                          <div className="space-y-1 text-sm">
                            <p className="text-green-700">
                              <span className="font-medium">Primary:</span>{' '}
                              {triviaPrimary ? getEmployeeName(triviaPrimary.employee_id) : <span className="italic text-gray-400">Unassigned</span>}
                            </p>
                            <p className="text-green-700">
                              <span className="font-medium">Secondaries:</span>{' '}
                              {triviaSecondaries.length > 0
                                ? triviaSecondaries.map(r => getEmployeeName(r.employee_id)).join(', ')
                                : <span className="italic text-gray-400">None</span>}
                            </p>
                          </div>
                        </div>
                      )}
                      {vs.offers_bingo_karaoke && (
                        <div className="p-3 rounded-md bg-pink-50 border border-pink-200">
                          <p className="text-sm font-semibold text-pink-800 mb-2">Bingo/Karaoke</p>
                          <div className="space-y-1 text-sm">
                            <p className="text-pink-700">
                              <span className="font-medium">Primary:</span>{' '}
                              {bkPrimary ? getEmployeeName(bkPrimary.employee_id) : <span className="italic text-gray-400">Unassigned</span>}
                            </p>
                            <p className="text-pink-700">
                              <span className="font-medium">Secondaries:</span>{' '}
                              {bkSecondaries.length > 0
                                ? bkSecondaries.map(r => getEmployeeName(r.employee_id)).join(', ')
                                : <span className="italic text-gray-400">None</span>}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {Object.keys(venueServices).length === 0 && (
                <p className="text-muted-foreground text-sm">No venues have pricing configured yet. Ask an admin to set up venue pricing.</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
