import React, { useState } from 'react';
import { MapPin, Plus, Pencil, Trash2, Clock, Users, Phone, Search } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../../../components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '../../../components/ui/alert-dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select';
import { Textarea } from '../../../components/ui/textarea';
import { toast } from 'sonner';
import { useData } from '../../../context/SponsorContext';

const emptyLocation = {
  name: '',
  address: '',
  city: '',
  dayOfWeek: '',
  time: '',
  capacityTier: '> 50',
  status: 'active',
  contactName: '',
  contactPhone: '',
  notes: ''
};

const LocationsManagement = () => {
  const { locations, addLocation, updateLocation, deleteLocation } = useData();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingLocation, setEditingLocation] = useState(null);
  const [formData, setFormData] = useState(emptyLocation);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');

  const filteredLocations = locations.filter(loc => {
    const matchesSearch = loc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         loc.city.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = filterStatus === 'all' || loc.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  const handleOpenDialog = (location = null) => {
    if (location) {
      setEditingLocation(location);
      setFormData(location);
    } else {
      setEditingLocation(null);
      setFormData(emptyLocation);
    }
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formData.name || !formData.address || !formData.city) {
      toast.error('Please fill in required fields');
      return;
    }

    try {
      if (editingLocation) {
        await updateLocation(editingLocation.id, formData);
        toast.success('Location updated successfully!');
      } else {
        await addLocation(formData);
        toast.success('Location added successfully!');
      }
      setDialogOpen(false);
    } catch (err) {
      console.error('Failed to save location:', err);
      toast.error(err.message || 'Failed to save location');
    }
  };

  const handleDelete = async (locationId) => {
    try {
      await deleteLocation(locationId);
      toast.success('Location deleted successfully');
    } catch (err) {
      console.error('Failed to delete location:', err);
      toast.error(err.message || 'Failed to delete location');
    }
  };

  const handleToggleStatus = async (location) => {
    try {
      await updateLocation(location.id, { 
        status: location.status === 'active' ? 'inactive' : 'active' 
      });
      toast.success('Location status updated');
    } catch (err) {
      console.error('Failed to update status:', err);
      toast.error(err.message || 'Failed to update status');
    }
  };

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Locations</h1>
          <p className="text-white/60 mt-1">Manage trivia venues and schedules</p>
        </div>
        <Button onClick={() => handleOpenDialog()} className="btn-gold">
          <Plus size={16} className="mr-2" />
          Add Location
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" size={18} />
          <Input
            placeholder="Search locations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
          />
        </div>
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-40 bg-white/5 border-[#f4d03f]/20 text-white">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
            <SelectItem value="all" className="text-white hover:bg-white/10">All Status</SelectItem>
            <SelectItem value="active" className="text-white hover:bg-white/10">Active</SelectItem>
            <SelectItem value="inactive" className="text-white hover:bg-white/10">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Locations Grid */}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredLocations.map((location) => (
          <div key={location.id} className="card-dark rounded-2xl p-6">
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-[#f4d03f]/10 flex items-center justify-center">
                  <MapPin className="w-6 h-6 text-[#f4d03f]" />
                </div>
                <div>
                  <h3 className="font-bold text-white">{location.name}</h3>
                  <p className="text-white/50 text-sm">{location.city}</p>
                </div>
              </div>
              <Badge 
                className={`cursor-pointer ${location.status === 'active' 
                  ? 'bg-green-500/20 text-green-400 border-green-500/30' 
                  : 'bg-gray-500/20 text-gray-400 border-gray-500/30'
                }`}
                onClick={() => handleToggleStatus(location)}
              >
                {location.status}
              </Badge>
            </div>

            <p className="text-white/60 text-sm mb-4">{location.address}</p>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="bg-white/5 rounded-lg p-3">
                <div className="flex items-center gap-2 text-white/50 text-xs mb-1">
                  <Clock size={12} />
                  Schedule
                </div>
                <p className="text-white text-sm font-medium">
                  {location.dayOfWeek} {location.time}
                </p>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <div className="flex items-center gap-2 text-white/50 text-xs mb-1">
                  <Users size={12} />
                  Available Capacity
                </div>
                <p className="text-white text-sm font-medium">{location.capacityTier || '> 50'}</p>
              </div>
            </div>

            {location.contactName && (
              <div className="text-sm text-white/50 mb-4">
                <span className="flex items-center gap-2">
                  <Phone size={12} />
                  {location.contactName} - {location.contactPhone}
                </span>
              </div>
            )}

            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleOpenDialog(location)}
                className="flex-1 btn-outline-gold"
              >
                <Pencil size={14} className="mr-1" />
                Edit
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-red-500/30 text-red-400 hover:bg-red-500/10"
                  >
                    <Trash2 size={14} />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                  <AlertDialogHeader>
                    <AlertDialogTitle className="text-white">Delete Location</AlertDialogTitle>
                    <AlertDialogDescription className="text-white/60">
                      Are you sure you want to delete {location.name}? This will remove all associated schedule data.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel className="bg-white/10 text-white border-0 hover:bg-white/20">
                      Cancel
                    </AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => handleDelete(location.id)}
                      className="bg-red-500 hover:bg-red-600 text-white"
                    >
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        ))}
      </div>

      {filteredLocations.length === 0 && (
        <div className="card-dark rounded-2xl p-12 text-center">
          <MapPin className="w-12 h-12 text-white/20 mx-auto mb-4" />
          <p className="text-white/60">No locations found</p>
        </div>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">
              {editingLocation ? 'Edit Location' : 'Add New Location'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
            <div>
              <Label className="text-white/80">Venue Name *</Label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Monkey Pants"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
              />
            </div>
            <div>
              <Label className="text-white/80">Address *</Label>
              <Input
                value={formData.address}
                onChange={(e) => setFormData({ ...formData, address: e.target.value })}
                placeholder="Street address"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80">City *</Label>
                <Input
                  value={formData.city}
                  onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                  placeholder="City"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                />
              </div>
              <div>
                <Label className="text-white/80">Status</Label>
                <Select
                  value={formData.status}
                  onValueChange={(value) => setFormData({ ...formData, status: value })}
                >
                  <SelectTrigger className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                    <SelectItem value="active" className="text-white hover:bg-white/10">Active</SelectItem>
                    <SelectItem value="inactive" className="text-white hover:bg-white/10">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80">Day of Week</Label>
                <Select
                  value={formData.dayOfWeek}
                  onValueChange={(value) => setFormData({ ...formData, dayOfWeek: value })}
                >
                  <SelectTrigger className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white">
                    <SelectValue placeholder="Select day" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                    {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map(day => (
                      <SelectItem key={day} value={day} className="text-white hover:bg-white/10">{day}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-white/80">Time</Label>
                <Input
                  type="time"
                  value={formData.time}
                  onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>
            </div>
            <div>
              <Label className="text-white/80">Available Capacity</Label>
              <Select
                value={formData.capacityTier || '> 50'}
                onValueChange={(value) => setFormData({ ...formData, capacityTier: value })}
              >
                <SelectTrigger className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white">
                  <SelectValue placeholder="Select capacity tier" />
                </SelectTrigger>
                <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                  <SelectItem value="< 50" className="text-white hover:bg-white/10">{'< 50'}</SelectItem>
                  <SelectItem value="> 50" className="text-white hover:bg-white/10">{'> 50'}</SelectItem>
                  <SelectItem value="100+" className="text-white hover:bg-white/10">100+</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80">Contact Name</Label>
                <Input
                  value={formData.contactName}
                  onChange={(e) => setFormData({ ...formData, contactName: e.target.value })}
                  placeholder="Venue contact"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                />
              </div>
              <div>
                <Label className="text-white/80">Contact Phone</Label>
                <Input
                  value={formData.contactPhone}
                  onChange={(e) => setFormData({ ...formData, contactPhone: e.target.value })}
                  placeholder="(xxx) xxx-xxxx"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                />
              </div>
            </div>
            <div>
              <Label className="text-white/80">Notes</Label>
              <Textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Internal notes about this venue..."
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)} className="text-white">
              Cancel
            </Button>
            <Button onClick={handleSave} className="btn-gold">
              {editingLocation ? 'Save Changes' : 'Add Location'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LocationsManagement;
