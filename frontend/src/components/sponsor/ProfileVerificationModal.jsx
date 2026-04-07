import React, { useState, useEffect } from 'react';
import { User, Building2, Mail, Phone, Globe, Check, AlertCircle, ChevronRight } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '../ui/dialog';
import { toast } from 'sonner';
import { profileApi, sponsorsApi } from '../../services/sponsorApi';

const ProfileVerificationModal = ({ isOpen, email, initialData, onComplete, onSkip }) => {
  const [step, setStep] = useState(1); // 1 = verify info, 2 = confirmation
  const [loading, setLoading] = useState(false);
  const [profileData, setProfileData] = useState({
    businessName: '',
    contactName: '',
    phone: '',
    website: '',
  });
  const [linkedSponsor, setLinkedSponsor] = useState(null);

  // Load initial data and check for linked sponsor
  useEffect(() => {
    const loadData = async () => {
      // Start with initial data passed in
      if (initialData) {
        setProfileData({
          businessName: initialData.businessName || initialData.business_name || '',
          contactName: initialData.contactName || initialData.contact_name || '',
          phone: initialData.phone || '',
          website: initialData.website || '',
        });
      }

      // Try to find linked sponsor data
      try {
        const sponsor = await sponsorsApi.getByEmail(email);
        if (sponsor) {
          setLinkedSponsor(sponsor);
          // Pre-fill with sponsor data if available
          setProfileData(prev => ({
            businessName: sponsor.business_name || sponsor.businessName || prev.businessName,
            contactName: sponsor.contact_name || sponsor.contactName || prev.contactName,
            phone: sponsor.phone || prev.phone,
            website: sponsor.website || prev.website,
          }));
        }
      } catch (err) {
        // No linked sponsor, that's ok
        // No linked sponsor found - user may need to create profile
      }
    };

    if (isOpen && email) {
      loadData();
    }
  }, [isOpen, email, initialData]);

  const handleVerify = async () => {
    if (!profileData.businessName || !profileData.contactName) {
      toast.error('Please fill in your business name and contact name');
      return;
    }

    setLoading(true);
    try {
      // Update profile in backend
      await profileApi.update(email, {
        businessName: profileData.businessName,
        name: profileData.contactName,
        phone: profileData.phone,
        website: profileData.website,
      });

      // If there's a linked sponsor, update that too
      if (linkedSponsor) {
        try {
          await sponsorsApi.update(linkedSponsor.id, {
            businessName: profileData.businessName,
            contactName: profileData.contactName,
            phone: profileData.phone,
            website: profileData.website,
          });
        } catch (err) {
          // Could not update sponsor - non-critical error
        }
      }

      setStep(2);
    } catch (err) {
      console.error('Failed to update profile:', err);
      toast.error('Failed to save profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = () => {
    toast.success('Profile verified successfully! Welcome to your dashboard.');
    onComplete(profileData);
  };

  return (
    <Dialog open={isOpen} onOpenChange={() => {}}>
      <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-lg" hideCloseButton>
        {step === 1 ? (
          <>
            <DialogHeader>
              <DialogTitle className="text-white flex items-center gap-2">
                <User className="w-5 h-5 text-[#f4d03f]" />
                Verify Your Profile
              </DialogTitle>
              <DialogDescription className="text-white/60">
                Please verify and complete your profile information. This helps us better serve you as a sponsor.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {/* Linked Sponsor Info */}
              {linkedSponsor && (
                <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-4 mb-4">
                  <div className="flex items-center gap-2 text-green-400 text-sm">
                    <Check size={16} />
                    <span>Your profile is linked to: <strong>{linkedSponsor.business_name || linkedSponsor.businessName}</strong></span>
                  </div>
                </div>
              )}

              {/* Email (read-only) */}
              <div className="space-y-2">
                <Label className="text-white/80 flex items-center gap-2">
                  <Mail size={14} />
                  Email Address
                </Label>
                <Input
                  type="email"
                  value={email}
                  disabled
                  className="bg-white/5 border-white/10 text-white/50"
                />
              </div>

              {/* Business Name */}
              <div className="space-y-2">
                <Label className="text-white/80 flex items-center gap-2">
                  <Building2 size={14} />
                  Business Name *
                </Label>
                <Input
                  value={profileData.businessName}
                  onChange={(e) => setProfileData({ ...profileData, businessName: e.target.value })}
                  placeholder="Your Business LLC"
                  className="bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>

              {/* Contact Name */}
              <div className="space-y-2">
                <Label className="text-white/80 flex items-center gap-2">
                  <User size={14} />
                  Your Name *
                </Label>
                <Input
                  value={profileData.contactName}
                  onChange={(e) => setProfileData({ ...profileData, contactName: e.target.value })}
                  placeholder="John Smith"
                  className="bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>

              {/* Phone */}
              <div className="space-y-2">
                <Label className="text-white/80 flex items-center gap-2">
                  <Phone size={14} />
                  Phone Number
                </Label>
                <Input
                  value={profileData.phone}
                  onChange={(e) => setProfileData({ ...profileData, phone: e.target.value })}
                  placeholder="(602) 555-1234"
                  className="bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>

              {/* Website */}
              <div className="space-y-2">
                <Label className="text-white/80 flex items-center gap-2">
                  <Globe size={14} />
                  Website
                </Label>
                <Input
                  value={profileData.website}
                  onChange={(e) => setProfileData({ ...profileData, website: e.target.value })}
                  placeholder="https://yourbusiness.com"
                  className="bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>
            </div>

            <div className="flex justify-between">
              {onSkip && (
                <Button
                  variant="ghost"
                  onClick={onSkip}
                  className="text-white/40 hover:text-white/60"
                >
                  Skip for now
                </Button>
              )}
              <Button
                onClick={handleVerify}
                disabled={loading || !profileData.businessName || !profileData.contactName}
                className="btn-gold ml-auto"
              >
                {loading ? 'Saving...' : 'Verify & Continue'}
                <ChevronRight size={16} className="ml-1" />
              </Button>
            </div>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle className="text-white flex items-center gap-2">
                <Check className="w-5 h-5 text-green-400" />
                Profile Verified!
              </DialogTitle>
            </DialogHeader>

            <div className="py-6">
              <div className="bg-green-500/10 border border-green-500/20 rounded-xl p-6 text-center">
                <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Check className="w-8 h-8 text-green-400" />
                </div>
                <h3 className="text-white text-lg font-semibold mb-2">You're All Set!</h3>
                <p className="text-white/60 text-sm">
                  Your profile has been verified. You can now access your sponsor dashboard 
                  and start uploading your media assets.
                </p>
              </div>

              {/* Summary */}
              <div className="mt-6 space-y-3">
                <div className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                  <span className="text-white/60 text-sm">Business</span>
                  <span className="text-white font-medium">{profileData.businessName}</span>
                </div>
                <div className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                  <span className="text-white/60 text-sm">Contact</span>
                  <span className="text-white font-medium">{profileData.contactName}</span>
                </div>
                {profileData.phone && (
                  <div className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                    <span className="text-white/60 text-sm">Phone</span>
                    <span className="text-white font-medium">{profileData.phone}</span>
                  </div>
                )}
              </div>
            </div>

            <Button onClick={handleComplete} className="btn-gold w-full">
              Go to Dashboard
              <ChevronRight size={16} className="ml-1" />
            </Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default ProfileVerificationModal;
