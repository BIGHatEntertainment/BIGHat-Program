import React, { useState, useRef, useEffect } from 'react';
import { User, Building2, Mail, Phone, Globe, Save, Camera, Upload, X, Loader2, MapPin, CheckCircle, AlertTriangle } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '../../components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../../components/ui/alert-dialog';
import { toast } from 'sonner';
import { useData } from '../../context/DataContext';
import { profileApi, accountsApi, accountDeletionApi } from '../../services/api';

const Profile = ({ user, onUpdateUser }) => {
  const { userProfile, userSubscriptions, updateUserProfile, updateUserPicture } = useData();
  const fileInputRef = useRef(null);
  const [loading, setLoading] = useState(false);
  const [imageDialogOpen, setImageDialogOpen] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [zipStatus, setZipStatus] = useState(null);
  
  // Account deletion state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletionRequested, setDeletionRequested] = useState(false);
  const [deletionLoading, setDeletionLoading] = useState(false);

  // Initialize form with user data or profile data
  const [formData, setFormData] = useState({
    name: user?.name || userProfile.name || '',
    email: user?.email || userProfile.email || '',
    businessName: user?.businessName || userProfile.businessName || '',
    phone: userProfile.phone || '',
    website: userProfile.website || '',
    zipCode: userProfile.zipCode || '',
  });

  // Fetch zip code status on mount
  useEffect(() => {
    const fetchZipStatus = async () => {
      const email = user?.email || userProfile.email;
      if (email) {
        try {
          const status = await accountsApi.getZipStatus(email);
          setZipStatus(status);
          if (status.zip_code) {
            setFormData(prev => ({ ...prev, zipCode: status.zip_code }));
          }
        } catch (err) {
          console.error('Failed to fetch zip status:', err);
        }
      }
    };
    fetchZipStatus();
  }, [user?.email, userProfile.email]);

  // Current profile picture (from userProfile or user prop)
  const currentPicture = userProfile.picture || user?.picture || 
    `https://api.dicebear.com/7.x/initials/svg?seed=${formData.name}&backgroundColor=f4d03f&textColor=1a1a2e`;

  // Update form when user changes
  useEffect(() => {
    if (user) {
      setFormData(prev => ({
        ...prev,
        name: user.name || prev.name,
        email: user.email || prev.email,
        businessName: user.businessName || prev.businessName,
      }));
    }
  }, [user]);

  const handleSave = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      // Validate zip code format if provided
      if (formData.zipCode && !/^\d{5}(-\d{4})?$/.test(formData.zipCode)) {
        toast.error('Invalid zip code format. Use 5 digits (e.g., 85001)');
        setLoading(false);
        return;
      }
      
      // Save to backend (including zip code)
      await accountsApi.updateProfile(formData.email, {
        business_name: formData.businessName,
        contact_name: formData.name,
        phone: formData.phone,
        website: formData.website,
        zip_code: formData.zipCode,
      });
      
      // Save to context (persists to localStorage)
      updateUserProfile({
        name: formData.name,
        email: formData.email,
        businessName: formData.businessName,
        phone: formData.phone,
        website: formData.website,
        zipCode: formData.zipCode,
      });

      // Also update the parent user state if callback provided
      if (onUpdateUser) {
        onUpdateUser({
          ...user,
          name: formData.name,
          email: formData.email,
          businessName: formData.businessName,
        });
      }

      // Refresh zip status
      const status = await accountsApi.getZipStatus(formData.email);
      setZipStatus(status);

      toast.success('Profile updated successfully!');
    } catch (err) {
      console.error('Failed to save profile:', err);
      toast.error(err.message || 'Failed to save profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (file) => {
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file');
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image must be less than 5MB');
      return;
    }

    // Create preview
    const reader = new FileReader();
    reader.onload = (e) => {
      setPreviewImage(e.target.result);
      setImageDialogOpen(true);
    };
    reader.readAsDataURL(file);
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const [savingImage, setSavingImage] = useState(false);

  const handleSaveImage = async () => {
    if (previewImage) {
      setSavingImage(true);
      try {
        // Save to backend
        await profileApi.updatePicture(formData.email, previewImage);
        
        // Update local state
        updateUserPicture(previewImage);
        
        // Also update parent user state
        if (onUpdateUser && user) {
          onUpdateUser({
            ...user,
            picture: previewImage,
          });
        }
        
        toast.success('Profile picture updated!');
        setImageDialogOpen(false);
        setPreviewImage(null);
      } catch (err) {
        console.error('Failed to save profile picture:', err);
        toast.error('Failed to save profile picture. Please try again.');
      } finally {
        setSavingImage(false);
      }
    }
  };

  const handleRemoveImage = async () => {
    try {
      // Remove from backend
      await profileApi.removePicture(formData.email);
      
      // Update local state
      updateUserPicture(null);
      if (onUpdateUser && user) {
        onUpdateUser({
          ...user,
          picture: null,
        });
      }
      toast.success('Profile picture removed');
    } catch (err) {
      console.error('Failed to remove profile picture:', err);
      toast.error('Failed to remove profile picture');
    }
  };

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Profile Settings</h1>
      <p className="text-white/60 mb-8">Manage your account information</p>

      <div className="space-y-8">
        {/* Profile Picture */}
        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4">Profile Picture</h2>
          <div className="flex items-center gap-6">
            <div className="relative group">
              <img
                src={currentPicture}
                alt={formData.name}
                className="w-24 h-24 rounded-2xl border-2 border-[#f4d03f]/30 object-cover"
              />
              <div 
                className="absolute inset-0 rounded-2xl bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center cursor-pointer"
                onClick={() => fileInputRef.current?.click()}
              >
                <Camera className="w-8 h-8 text-white" />
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => handleFileSelect(e.target.files[0])}
              />
            </div>
            <div className="flex-1">
              <p className="text-white font-medium">{formData.name}</p>
              <p className="text-white/50 text-sm">{formData.businessName}</p>
              <p className="text-white/40 text-xs mt-1">Member since {userProfile.createdAt}</p>
              <div className="flex gap-2 mt-3">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => fileInputRef.current?.click()}
                  className="btn-outline-gold text-xs"
                >
                  <Upload size={12} className="mr-1" />
                  Upload Photo
                </Button>
                {userProfile.picture && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleRemoveImage}
                    className="border-red-500/30 text-red-400 hover:bg-red-500/10 text-xs"
                  >
                    <X size={12} className="mr-1" />
                    Remove
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Business Information */}
        <form onSubmit={handleSave} className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4">Business Information</h2>
          <div className="space-y-4">
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80 flex items-center gap-2">
                  <User size={14} /> Contact Name
                </Label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>
              <div>
                <Label className="text-white/80 flex items-center gap-2">
                  <Building2 size={14} /> Business Name
                </Label>
                <Input
                  value={formData.businessName}
                  onChange={(e) => setFormData({ ...formData, businessName: e.target.value })}
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>
            </div>

            <div>
              <Label className="text-white/80 flex items-center gap-2">
                <Mail size={14} /> Email
              </Label>
              <Input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
              />
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80 flex items-center gap-2">
                  <Phone size={14} /> Phone
                </Label>
                <Input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>
              <div>
                <Label className="text-white/80 flex items-center gap-2">
                  <Globe size={14} /> Website
                </Label>
                <Input
                  type="url"
                  value={formData.website}
                  onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>
            </div>

            {/* Zip Code Field */}
            <div>
              <Label className="text-white/80 flex items-center gap-2">
                <MapPin size={14} /> Zip Code
              </Label>
              <div className="grid sm:grid-cols-2 gap-4 mt-1.5">
                <Input
                  value={formData.zipCode}
                  onChange={(e) => setFormData({ ...formData, zipCode: e.target.value.replace(/[^\d-]/g, '').slice(0, 10) })}
                  placeholder="Enter your zip code"
                  className="bg-white/5 border-[#f4d03f]/20 text-white"
                />
                {/* Only show eligibility message for valid AZ zip codes */}
                <div className="flex items-center">
                  {zipStatus?.has_zip_code && zipStatus.is_az_resident && (
                    <div className="flex items-center gap-2 text-green-400 text-sm">
                      <CheckCircle size={16} />
                      <span>Eligible for AZ local discounts</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <Button type="submit" disabled={loading} className="btn-gold">
              <Save size={16} className="mr-2" />
              {loading ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </form>

        {/* Current Sponsorship */}
        {userSubscriptions && userSubscriptions.length > 0 && (
          <div className="card-featured rounded-2xl p-6">
            <h2 className="text-lg font-bold text-white mb-4">Current Sponsorship</h2>
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <p className="text-[#f4d03f] font-bold text-xl">{userSubscriptions[0].packageName}</p>
                <p className="text-white/60 text-sm mt-1">
                  Active: {userSubscriptions[0].startDate} - {userSubscriptions[0].endDate}
                </p>
              </div>
              <Button variant="outline" className="btn-outline-gold">
                Upgrade Plan
              </Button>
            </div>
          </div>
        )}

        {/* Danger Zone */}
        <div className="card-dark rounded-2xl p-6 border-red-500/20">
          <h2 className="text-lg font-bold text-red-400 mb-2 flex items-center gap-2">
            <AlertTriangle size={20} />
            Danger Zone
          </h2>
          <p className="text-white/60 text-sm mb-4">
            Once you delete your account, there is no going back. Please be certain.
          </p>
          <Button 
            variant="outline" 
            className="border-red-500/30 text-red-400 hover:bg-red-500/10"
            onClick={() => setDeleteDialogOpen(true)}
          >
            Delete Account
          </Button>
        </div>
      </div>

      {/* Account Deletion Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent className="bg-[#1a1a2e] border-red-500/20">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-red-400 flex items-center gap-2">
              <AlertTriangle size={20} />
              Delete Your Account?
            </AlertDialogTitle>
            <AlertDialogDescription className="text-white/70 space-y-3">
              <p>
                This action <strong className="text-red-400">cannot be undone</strong>. This will permanently delete your account and remove your data from our servers.
              </p>
              <p>
                If you have an active subscription, it will be cancelled and you will not be charged again.
              </p>
              <p className="bg-white/5 p-3 rounded-lg border border-white/10">
                A confirmation email will be sent to <strong className="text-white">{user?.email || userProfile.email}</strong>. 
                You must click the link in the email to confirm deletion.
              </p>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-white/10 text-white border-white/20 hover:bg-white/20">
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={async (e) => {
                e.preventDefault();
                setDeletionLoading(true);
                try {
                  const email = user?.email || userProfile.email;
                  const response = await accountDeletionApi.requestDeletion(email);
                  if (response.success) {
                    setDeletionRequested(true);
                    setDeleteDialogOpen(false);
                    toast.success('Check your email to confirm account deletion');
                  }
                } catch (error) {
                  toast.error('Failed to request account deletion. Please try again.');
                } finally {
                  setDeletionLoading(false);
                }
              }}
              disabled={deletionLoading}
              className="bg-red-500 hover:bg-red-600 text-white"
            >
              {deletionLoading ? (
                <>
                  <Loader2 size={16} className="mr-2 animate-spin" />
                  Sending...
                </>
              ) : (
                'Send Confirmation Email'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Deletion Email Sent Confirmation Dialog */}
      <Dialog open={deletionRequested} onOpenChange={setDeletionRequested}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <Mail size={20} className="text-[#f4d03f]" />
              Confirmation Email Sent
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <p className="text-white/70">
              We&apos;ve sent a confirmation email to <strong className="text-white">{user?.email || userProfile.email}</strong>.
            </p>
            <div className="bg-orange-500/10 border border-orange-500/20 rounded-lg p-4">
              <p className="text-orange-400 text-sm">
                <strong>Important:</strong> You must click the link in the email to complete account deletion. 
                The link will expire in 24 hours.
              </p>
            </div>
            <p className="text-white/50 text-sm">
              If you don&apos;t see the email, please check your spam folder.
            </p>
          </div>
          <DialogFooter>
            <Button onClick={() => setDeletionRequested(false)} className="btn-gold">
              Got it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Image Upload Dialog */}
      <Dialog open={imageDialogOpen} onOpenChange={setImageDialogOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-white">Update Profile Picture</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {previewImage && (
              <div className="flex justify-center">
                <img
                  src={previewImage}
                  alt="Preview"
                  className="w-48 h-48 rounded-2xl object-cover border-2 border-[#f4d03f]/30"
                />
              </div>
            )}
            <p className="text-white/60 text-sm text-center">
              This image will be visible to admins and help them recognize your business.
            </p>
          </div>
          <DialogFooter>
            <Button 
              variant="ghost" 
              onClick={() => {
                setImageDialogOpen(false);
                setPreviewImage(null);
              }}
              className="text-white"
              disabled={savingImage}
            >
              Cancel
            </Button>
            <Button onClick={handleSaveImage} disabled={savingImage} className="btn-gold">
              {savingImage ? (
                <>
                  <Loader2 size={16} className="mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Picture'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Profile;
