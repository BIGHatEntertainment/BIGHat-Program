import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { ShieldCheck, Shield, MapPin, Plus, Trash2, Users, Mail, Send } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const VenueRoleManager = () => {
  const [venues, setVenues] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [allRoles, setAllRoles] = useState([]);
  const [venueServices, setVenueServices] = useState({});
  const [loading, setLoading] = useState(true);

  // Assignment form
  const [assignVenue, setAssignVenue] = useState('');
  const [assignCategory, setAssignCategory] = useState('');
  const [assignEmployee, setAssignEmployee] = useState('');
  const [assignType, setAssignType] = useState('');
  const [sendingPrimary, setSendingPrimary] = useState(false);
  const [sendingSecondary, setSendingSecondary] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [venuesRes, employeesRes, rolesRes, servicesRes] = await Promise.all([
        axios.get(`${API}/venues`),
        axios.get(`${API}/employees`),
        axios.get(`${API}/venue-roles`),
        axios.get(`${API}/venue-roles/services`)
      ]);
      setVenues(venuesRes.data);
      setEmployees(employeesRes.data);
      setAllRoles(rolesRes.data);
      setVenueServices(servicesRes.data);
    } catch (error) {
      console.error('Error fetching role data:', error);
      toast.error('Failed to load role data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const getEmployeeName = (id) => employees.find(e => e.id === id)?.name || 'Unknown';

  const handleAssignRole = async () => {
    if (!assignVenue || !assignCategory || !assignEmployee || !assignType) {
      toast.error('Please fill all fields');
      return;
    }
    try {
      await axios.post(`${API}/venue-roles`, {
        venue_id: assignVenue,
        employee_id: assignEmployee,
        role_category: assignCategory,
        role_type: assignType
      });
      toast.success('Role assigned!');
      setAssignVenue('');
      setAssignCategory('');
      setAssignEmployee('');
      setAssignType('');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to assign role');
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

  // Get available categories based on selected venue
  const getCategories = () => {
    if (!assignVenue) return [];
    const vs = venueServices[assignVenue];
    if (!vs) return [];
    const cats = [];
    if (vs.offers_trivia) cats.push({ value: 'trivia', label: 'Trivia' });
    if (vs.offers_bingo_karaoke) cats.push({ value: 'bingo_karaoke', label: 'Bingo/Karaoke' });
    return cats;
  };

  // Check if primary is already taken
  const isPrimaryTaken = (venueId, category) => {
    return allRoles.some(r => r.venue_id === venueId && r.role_category === category && r.role_type === 'primary');
  };

  const getRoleTypes = () => {
    if (!assignVenue || !assignCategory) return [];
    const types = [{ value: 'secondary', label: 'Secondary' }];
    if (!isPrimaryTaken(assignVenue, assignCategory)) {
      types.unshift({ value: 'primary', label: 'Primary' });
    }
    return types;
  };

  const handleSendPrimaryEmails = async () => {
    setSendingPrimary(true);
    try {
      const res = await axios.post(`${API}/notifications/send-primary-report`);
      toast.success(`Primary reports sent: ${res.data.sent} email(s)`);
      if (res.data.errors?.length) toast.warning(`${res.data.errors.length} failed`);
    } catch (e) {
      toast.error('Failed to send primary reports');
    } finally { setSendingPrimary(false); }
  };

  const handleSendSecondaryEmails = async () => {
    setSendingSecondary(true);
    try {
      const res = await axios.post(`${API}/notifications/send-secondary-availability`);
      toast.success(`Secondary availability sent: ${res.data.sent} email(s)`);
      if (res.data.errors?.length) toast.warning(`${res.data.errors.length} failed`);
    } catch (e) {
      toast.error('Failed to send secondary availability');
    } finally { setSendingSecondary(false); }
  };

  if (loading) {
    return <div className="flex justify-center py-8"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>;
  }

  const categoryLabel = (cat) => cat === 'trivia' ? 'Trivia' : 'Bingo/Karaoke';

  return (
    <div className="space-y-6">
      {/* Email Notifications */}
      <Card data-testid="notifications-card">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center space-x-2 text-lg">
            <Mail className="h-5 w-5" />
            <span>Email Notifications</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <Button onClick={handleSendPrimaryEmails} disabled={sendingPrimary} variant="outline" className="flex items-center space-x-2" data-testid="send-primary-emails-btn">
              <Send className="h-4 w-4" />
              <span>{sendingPrimary ? 'Sending...' : 'Send Primary Friday Reports'}</span>
            </Button>
            <Button onClick={handleSendSecondaryEmails} disabled={sendingSecondary} variant="outline" className="flex items-center space-x-2" data-testid="send-secondary-emails-btn">
              <Send className="h-4 w-4" />
              <span>{sendingSecondary ? 'Sending...' : 'Send Secondary Monday Availability'}</span>
            </Button>
          </div>
          <p className="text-xs text-gray-400 mt-2">Emails auto-send: Fridays 9AM (primaries) &amp; Mondays 9AM (secondaries). Use buttons to send manually.</p>
        </CardContent>
      </Card>

      {/* Assign Role Form */}
      <Card data-testid="assign-role-card">
        <CardHeader>
          <CardTitle className="flex items-center space-x-2 text-lg">
            <Plus className="h-5 w-5" />
            <span>Assign Role</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <Select value={assignVenue} onValueChange={(v) => { setAssignVenue(v); setAssignCategory(''); setAssignType(''); }} data-testid="assign-venue-select">
              <SelectTrigger data-testid="assign-venue-trigger">
                <SelectValue placeholder="Venue" />
              </SelectTrigger>
              <SelectContent>
                {Object.values(venueServices).map(vs => (
                  <SelectItem key={vs.venue_id} value={vs.venue_id}>{vs.venue_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={assignCategory} onValueChange={(v) => { setAssignCategory(v); setAssignType(''); }} disabled={!assignVenue} data-testid="assign-category-select">
              <SelectTrigger data-testid="assign-category-trigger">
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                {getCategories().map(c => (
                  <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={assignType} onValueChange={setAssignType} disabled={!assignCategory} data-testid="assign-type-select">
              <SelectTrigger data-testid="assign-type-trigger">
                <SelectValue placeholder="Role" />
              </SelectTrigger>
              <SelectContent>
                {getRoleTypes().map(t => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={assignEmployee} onValueChange={setAssignEmployee} data-testid="assign-employee-select">
              <SelectTrigger data-testid="assign-employee-trigger">
                <SelectValue placeholder="Employee" />
              </SelectTrigger>
              <SelectContent>
                {employees.map(e => (
                  <SelectItem key={e.id} value={e.id}>{e.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button onClick={handleAssignRole} disabled={!assignVenue || !assignCategory || !assignEmployee || !assignType} data-testid="assign-role-btn">
              Assign
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Venue Roles List */}
      {Object.values(venueServices).map(vs => {
        const triviaRoles = allRoles.filter(r => r.venue_id === vs.venue_id && r.role_category === 'trivia');
        const bkRoles = allRoles.filter(r => r.venue_id === vs.venue_id && r.role_category === 'bingo_karaoke');

        if (!vs.offers_trivia && !vs.offers_bingo_karaoke) return null;

        return (
          <Card key={vs.venue_id} data-testid={`venue-roles-card-${vs.venue_id}`}>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center space-x-2 text-lg">
                <MapPin className="h-5 w-5 text-purple-600" />
                <span>{vs.venue_name}</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {vs.offers_trivia && (
                  <RoleCategorySection
                    title="Trivia"
                    roles={triviaRoles}
                    getEmployeeName={getEmployeeName}
                    onRemove={handleRemoveRole}
                    colorBg="bg-green-50"
                    colorBorder="border-green-200"
                    colorText="text-green-800"
                    badgeColor="bg-green-600"
                  />
                )}
                {vs.offers_bingo_karaoke && (
                  <RoleCategorySection
                    title="Bingo/Karaoke"
                    roles={bkRoles}
                    getEmployeeName={getEmployeeName}
                    onRemove={handleRemoveRole}
                    colorBg="bg-pink-50"
                    colorBorder="border-pink-200"
                    colorText="text-pink-800"
                    badgeColor="bg-pink-600"
                  />
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}

      {Object.keys(venueServices).length === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-gray-400">
            No venues have pricing configured. Set up venue pricing first to manage roles.
          </CardContent>
        </Card>
      )}
    </div>
  );
};

const RoleCategorySection = ({ title, roles, getEmployeeName, onRemove, colorBg, colorBorder, colorText, badgeColor }) => {
  const primary = roles.find(r => r.role_type === 'primary');
  const secondaries = roles.filter(r => r.role_type === 'secondary');

  return (
    <div className={`p-4 rounded-lg ${colorBg} border ${colorBorder}`}>
      <h4 className={`font-semibold ${colorText} mb-3`}>{title}</h4>

      {/* Primary */}
      <div className="mb-3">
        <p className={`text-xs font-semibold ${colorText} uppercase tracking-wider mb-1`}>Primary</p>
        {primary ? (
          <div className="flex items-center justify-between p-2 bg-[#111827] rounded border border-[#1e293b]">
            <div className="flex items-center space-x-2">
              <ShieldCheck className="h-4 w-4 text-blue-600" />
              <span className="font-medium text-sm">{getEmployeeName(primary.employee_id)}</span>
            </div>
            <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500 hover:text-red-700 hover:bg-red-50" onClick={() => onRemove(primary.id)} data-testid={`remove-role-${primary.id}`}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <p className="text-sm text-gray-400 italic p-2">Unassigned</p>
        )}
      </div>

      {/* Secondaries */}
      <div>
        <p className={`text-xs font-semibold ${colorText} uppercase tracking-wider mb-1`}>Secondaries</p>
        {secondaries.length > 0 ? (
          <div className="space-y-1">
            {secondaries.map(role => (
              <div key={role.id} className="flex items-center justify-between p-2 bg-[#111827] rounded border border-[#1e293b]">
                <div className="flex items-center space-x-2">
                  <Shield className="h-4 w-4 text-gray-400" />
                  <span className="text-sm">{getEmployeeName(role.employee_id)}</span>
                </div>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500 hover:text-red-700 hover:bg-red-50" onClick={() => onRemove(role.id)} data-testid={`remove-role-${role.id}`}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400 italic p-2">None</p>
        )}
      </div>
    </div>
  );
};

export default VenueRoleManager;
