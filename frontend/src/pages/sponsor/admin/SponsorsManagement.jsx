import React, { useState, useRef, useEffect } from 'react';
import { Building2, Plus, Pencil, Trash2, Mail, Phone, Globe, Search, Image, Upload, X, MapPin, Key, Grid3X3, User, Eye, CheckCircle, XCircle, Clock, Loader2 } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { accountsApi, assetsApi } from '../../../services/sponsorApi';
import SponsorPlacementMatrix from '../../components/SponsorPlacementMatrix';
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
import { Checkbox } from '../../../components/ui/checkbox';
import { toast } from 'sonner';
import { useData } from '../../../context/SponsorContext';
import { sponsorshipPackages } from '../../data/mock';

const emptySponsor = {
  businessName: '',
  email: '',
  contactName: '',
  phone: '',
  website: '',
  zipCode: '',
  package: '',
  status: 'active',
  notes: '',
  picture: null,
  logo: null,
  isVenueSponsor: false
};

const SponsorsManagement = () => {
  const { sponsors, addSponsor, updateSponsor, deleteSponsor, registeredAccounts } = useData();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingSponsor, setEditingSponsor] = useState(null);
  const [formData, setFormData] = useState(emptySponsor);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterPackage, setFilterPackage] = useState('all');
  const [filterType, setFilterType] = useState('all'); // all, venue, regular
  const [selectedAccount, setSelectedAccount] = useState('');
  const [matrixSponsor, setMatrixSponsor] = useState(null); // For placement matrix modal
  const fileInputRef = useRef(null);
  
  // User profile management state
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [selectedSponsor, setSelectedSponsor] = useState(null);
  const [profileData, setProfileData] = useState({});
  const [userAssets, setUserAssets] = useState([]);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [activeProfileTab, setActiveProfileTab] = useState('profile');
  
  // Asset preview state
  const [assetPreviewOpen, setAssetPreviewOpen] = useState(false);
  const [previewAsset, setPreviewAsset] = useState(null);

  // Open user profile modal
  const handleOpenProfileModal = async (sponsor) => {
    setSelectedSponsor(sponsor);
    setProfileModalOpen(true);
    setLoadingProfile(true);
    setActiveProfileTab('profile');
    
    try {
      // Fetch user's zip status and profile data
      const zipStatus = await accountsApi.getZipStatus(sponsor.email);
      setProfileData({
        businessName: sponsor.businessName || '',
        contactName: sponsor.contactName || '',
        email: sponsor.email || '',
        phone: sponsor.phone || '',
        website: sponsor.website || '',
        zipCode: zipStatus.zip_code || '',
        isAzResident: zipStatus.is_az_resident || false,
        package: sponsor.package || '',
        status: sponsor.status || 'active',
        isVenueSponsor: sponsor.isVenueSponsor || false,
      });
      
      // Fetch user's assets
      const assets = await assetsApi.getUserAssets(sponsor.email);
      setUserAssets(Array.isArray(assets) ? assets : []);
    } catch (err) {
      console.error('Failed to load profile:', err);
      // Use sponsor data as fallback
      setProfileData({
        businessName: sponsor.businessName || '',
        contactName: sponsor.contactName || '',
        email: sponsor.email || '',
        phone: sponsor.phone || '',
        website: sponsor.website || '',
        zipCode: '',
        isAzResident: false,
        package: sponsor.package || '',
        status: sponsor.status || 'active',
        isVenueSponsor: sponsor.isVenueSponsor || false,
      });
      setUserAssets([]);
    } finally {
      setLoadingProfile(false);
    }
  };

  // Save profile changes
  const handleSaveProfile = async () => {
    setSavingProfile(true);
    try {
      // Update backend profile (including zip code)
      await accountsApi.updateProfile(profileData.email, {
        business_name: profileData.businessName,
        contact_name: profileData.contactName,
        phone: profileData.phone,
        website: profileData.website,
        zip_code: profileData.zipCode,
      });
      
      // Update sponsor in our local state
      await updateSponsor(selectedSponsor.id, {
        businessName: profileData.businessName,
        contactName: profileData.contactName,
        phone: profileData.phone,
        website: profileData.website,
        package: profileData.package,
        status: profileData.status,
        isVenueSponsor: profileData.isVenueSponsor,
      });
      
      // Refresh zip status
      const zipStatus = await accountsApi.getZipStatus(profileData.email);
      setProfileData(prev => ({
        ...prev,
        isAzResident: zipStatus.is_az_resident || false,
      }));
      
      toast.success('Profile updated successfully!');
    } catch (err) {
      console.error('Failed to save profile:', err);
      toast.error(err.message || 'Failed to save profile');
    } finally {
      setSavingProfile(false);
    }
  };

  // Handle asset preview
  const handleAssetPreview = (asset) => {
    setPreviewAsset(asset);
    setAssetPreviewOpen(true);
  };

  // Handle asset status change
  const handleAssetStatusChange = async (assetId, action) => {
    try {
      if (action === 'approve') {
        await assetsApi.approve(assetId);
        toast.success('Asset approved!');
      } else if (action === 'reject') {
        await assetsApi.reject(assetId);
        toast.success('Asset rejected');
      }
      
      // Refresh assets
      const assets = await assetsApi.getUserAssets(selectedSponsor.email);
      setUserAssets(Array.isArray(assets) ? assets : []);
    } catch (err) {
      console.error('Failed to update asset:', err);
      toast.error(err.message || 'Failed to update asset');
    }
  };

  // Delete asset
  const handleDeleteAsset = async (assetId) => {
    try {
      await assetsApi.delete(assetId);
      toast.success('Asset deleted');
      
      // Refresh assets
      const assets = await assetsApi.getUserAssets(selectedSponsor.email);
      setUserAssets(Array.isArray(assets) ? assets : []);
    } catch (err) {
      console.error('Failed to delete asset:', err);
      toast.error(err.message || 'Failed to delete asset');
    }
  };

  // Get accounts that aren't already in sponsors list
  const getUnlinkedAccounts = () => {
    const sponsorEmails = sponsors.map(s => s.email?.toLowerCase());
    return registeredAccounts.filter(account => 
      !sponsorEmails.includes(account.email?.toLowerCase())
    );
  };

  const unlinkedAccounts = getUnlinkedAccounts();

  // Handle selecting an existing account
  const handleAccountSelect = (accountId) => {
    setSelectedAccount(accountId);
    if (accountId && accountId !== 'new') {
      const account = registeredAccounts.find(a => a.id === accountId);
      if (account) {
        setFormData({
          ...emptySponsor,
          businessName: account.businessName || '',
          email: account.email || '',
          contactName: account.contactName || '',
          phone: account.phone || '',
          website: account.website || '',
          notes: 'Linked from registered account'
        });
      }
    } else {
      setFormData(emptySponsor);
    }
  };

  const packages = sponsorshipPackages.slice(1); // Tier packages only (exclude à la carte parent)
  
  // Get à la carte items from the first package
  const alaCarteItems = sponsorshipPackages[0]?.items || [];
  
  // Combined list for admin package selection
  const allPackageOptions = [
    ...packages.map(pkg => ({
      id: pkg.id,
      name: pkg.name,
      priceLabel: pkg.priceLabel || `$${pkg.price}`,
      type: 'tier'
    })),
    ...alaCarteItems.map(item => ({
      id: item.id,
      name: item.name,
      priceLabel: `$${item.price}`,
      type: 'alacarte'
    }))
  ];

  const filteredSponsors = sponsors.filter(sponsor => {
    const matchesSearch = sponsor.businessName.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         sponsor.email.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesPackage = filterPackage === 'all' || sponsor.package === filterPackage;
    const matchesType = filterType === 'all' || 
                       (filterType === 'venue' && sponsor.isVenueSponsor) ||
                       (filterType === 'regular' && !sponsor.isVenueSponsor);
    return matchesSearch && matchesPackage && matchesType;
  });

  const handleOpenDialog = (sponsor = null) => {
    if (sponsor) {
      setEditingSponsor(sponsor);
      setFormData(sponsor);
    } else {
      setEditingSponsor(null);
      setFormData(emptySponsor);
      setSelectedAccount('new'); // Reset account selection
    }
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formData.businessName || !formData.email) {
      toast.error('Please fill in business name and email');
      return;
    }

    try {
      if (editingSponsor) {
        await updateSponsor(editingSponsor.id, formData);
        toast.success('Sponsor updated successfully!');
      } else {
        // When admin creates a new sponsor, also create an account with default password
        // This doesn't apply if we're linking to an existing registered account
        const isLinkingExisting = selectedAccount !== '' && selectedAccount !== 'new';
        
        if (!isLinkingExisting) {
          // Create account with default password "B1GHat" - user must reset on first login
          try {
            await accountsApi.adminCreate({
              email: formData.email,
              businessName: formData.businessName,
              contactName: formData.contactName,
              phone: formData.phone,
              website: formData.website,
            });
            // Account created with default password
          } catch (accErr) {
            // Account might already exist if they linked, that's ok
            if (!accErr.message?.includes('already exists')) {
              console.error('Failed to create account:', accErr);
            }
          }
        }
        
        await addSponsor(formData);
        toast.success(
          isLinkingExisting 
            ? 'Sponsor added successfully!' 
            : 'Sponsor added! Default password is "B1GHat" - they must reset on first login.'
        );
      }
      setDialogOpen(false);
    } catch (err) {
      console.error('Failed to save sponsor:', err);
      toast.error(err.message || 'Failed to save sponsor');
    }
  };

  const handleDelete = async (sponsorId) => {
    try {
      await deleteSponsor(sponsorId);
      toast.success('Sponsor deleted successfully');
    } catch (err) {
      console.error('Failed to delete sponsor:', err);
      toast.error(err.message || 'Failed to delete sponsor');
    }
  };

  const handleToggleStatus = async (sponsor) => {
    try {
      await updateSponsor(sponsor.id, { 
        status: sponsor.status === 'active' ? 'inactive' : 'active' 
      });
      toast.success('Sponsor status updated');
    } catch (err) {
      console.error('Failed to update status:', err);
      toast.error(err.message || 'Failed to update status');
    }
  };

  const handleLogoUpload = (file) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Image must be less than 5MB');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      setFormData({ ...formData, logo: e.target.result });
    };
    reader.readAsDataURL(file);
  };

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Sponsors</h1>
          <p className="text-white/60 mt-1">Manage sponsor accounts and packages</p>
        </div>
        <Button onClick={() => handleOpenDialog()} className="btn-gold">
          <Plus size={16} className="mr-2" />
          Add Sponsor
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" size={18} />
          <Input
            placeholder="Search sponsors..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
          />
        </div>
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger className="w-40 bg-white/5 border-[#f4d03f]/20 text-white">
            <SelectValue placeholder="Sponsor Type" />
          </SelectTrigger>
          <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
            <SelectItem value="all" className="text-white hover:bg-white/10">All Types</SelectItem>
            <SelectItem value="venue" className="text-white hover:bg-white/10">
              <span className="flex items-center gap-2">
                <MapPin size={12} className="text-purple-400" />
                Venue Sponsors
              </span>
            </SelectItem>
            <SelectItem value="regular" className="text-white hover:bg-white/10">
              <span className="flex items-center gap-2">
                <Building2 size={12} className="text-blue-400" />
                Regular Sponsors
              </span>
            </SelectItem>
          </SelectContent>
        </Select>
        <Select value={filterPackage} onValueChange={setFilterPackage}>
          <SelectTrigger className="w-48 bg-white/5 border-[#f4d03f]/20 text-white">
            <SelectValue placeholder="Package" />
          </SelectTrigger>
          <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
            <SelectItem value="all" className="text-white hover:bg-white/10">All Packages</SelectItem>
            {packages.map(pkg => (
              <SelectItem key={pkg.id} value={pkg.name} className="text-white hover:bg-white/10">
                {pkg.name}
              </SelectItem>
            ))}
            {alaCarteItems.map(item => (
              <SelectItem key={item.id} value={item.name} className="text-white hover:bg-white/10">
                🎁 {item.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Sponsors Table */}
      <div className="card-dark rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#f4d03f]/10">
                <th className="text-left p-4 text-white/50 font-medium text-sm">Sponsor</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Package</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Contact</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Assets</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Status</th>
                <th className="text-left p-4 text-white/50 font-medium text-sm">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredSponsors.map((sponsor) => (
                <tr key={sponsor.id} className="border-b border-[#f4d03f]/5 hover:bg-white/5 transition-colors">
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-[#f4d03f]/10 flex items-center justify-center flex-shrink-0 overflow-hidden">
                        {sponsor.picture || sponsor.logo ? (
                          <img 
                            src={sponsor.picture || sponsor.logo} 
                            alt={sponsor.businessName}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <span className="text-[#f4d03f] font-bold">
                            {sponsor.businessName.charAt(0)}
                          </span>
                        )}
                      </div>
                      <div>
                        <p className="text-white font-medium">{sponsor.businessName}</p>
                        <p className="text-white/50 text-xs">{sponsor.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="p-4">
                    <div className="flex flex-col gap-1">
                      {/* Sponsor Type Badge */}
                      {sponsor.isVenueSponsor ? (
                        <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30 w-fit">
                          <MapPin size={10} className="mr-1" />
                          Venue Sponsor
                        </Badge>
                      ) : (
                        <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30 w-fit">
                          <Building2 size={10} className="mr-1" />
                          Sponsor
                        </Badge>
                      )}
                      {/* Package/Tier Badge */}
                      {sponsor.package ? (
                        <Badge className={`w-fit ${
                          sponsor.package.toLowerCase().includes('star') ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' :
                          sponsor.package.toLowerCase().includes('gold') ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' :
                          sponsor.package.toLowerCase().includes('silver') ? 'bg-gray-400/20 text-gray-300 border-gray-400/30' :
                          sponsor.package.toLowerCase().includes('bronze') ? 'bg-orange-500/20 text-orange-400 border-orange-500/30' :
                          'bg-white/10 text-white/70 border-white/20'
                        }`}>
                          {sponsor.package}
                        </Badge>
                      ) : (
                        <span className="text-white/40 text-xs italic">No Package</span>
                      )}
                    </div>
                  </td>
                  <td className="p-4">
                    <p className="text-white text-sm">{sponsor.contactName}</p>
                    <p className="text-white/50 text-xs">{sponsor.phone}</p>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-2 text-white/70">
                      <Image size={14} />
                      {sponsor.assetsCount || 0}
                    </div>
                  </td>
                  <td className="p-4">
                    <Badge 
                      className={`cursor-pointer ${sponsor.status === 'active' 
                        ? 'bg-green-500/20 text-green-400 border-green-500/30' 
                        : 'bg-gray-500/20 text-gray-400 border-gray-500/30'
                      }`}
                      onClick={() => handleToggleStatus(sponsor)}
                    >
                      {sponsor.status}
                    </Badge>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-2">
                      {/* View Profile Button */}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleOpenProfileModal(sponsor)}
                        className="text-blue-400 hover:text-blue-400 hover:bg-blue-500/10"
                        title="View Profile & Assets"
                      >
                        <User size={14} />
                      </Button>
                      {/* Placement Matrix Button - Only show for active sponsors */}
                      {sponsor.status === 'active' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setMatrixSponsor(sponsor)}
                          className="text-[#f4d03f] hover:text-[#f4d03f] hover:bg-[#f4d03f]/10"
                          title="Venue Placement Matrix"
                        >
                          <Grid3X3 size={14} />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleOpenDialog(sponsor)}
                        className="text-white/60 hover:text-[#f4d03f] hover:bg-[#f4d03f]/10"
                        title="Edit Sponsor"
                      >
                        <Pencil size={14} />
                      </Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-white/60 hover:text-red-400 hover:bg-red-500/10"
                          >
                            <Trash2 size={14} />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                          <AlertDialogHeader>
                            <AlertDialogTitle className="text-white">Delete Sponsor</AlertDialogTitle>
                            <AlertDialogDescription className="text-white/60">
                              Are you sure you want to delete {sponsor.businessName}? This will also remove all their assets and data.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel className="bg-white/10 text-white border-0 hover:bg-white/20">
                              Cancel
                            </AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => handleDelete(sponsor.id)}
                              className="bg-red-500 hover:bg-red-600 text-white"
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {filteredSponsors.length === 0 && (
        <div className="card-dark rounded-2xl p-12 text-center mt-6">
          <Building2 className="w-12 h-12 text-white/20 mx-auto mb-4" />
          <p className="text-white/60">No sponsors found</p>
        </div>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">
              {editingSponsor ? 'Edit Sponsor' : 'Add New Sponsor'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-2">
            {/* Account Selection - Only show when adding new sponsor */}
            {!editingSponsor && unlinkedAccounts.length > 0 && (
              <div className="p-4 bg-blue-500/10 rounded-xl border border-blue-500/20">
                <Label className="text-white/80 mb-2 block">Link Existing Account (Optional)</Label>
                <Select value={selectedAccount} onValueChange={handleAccountSelect}>
                  <SelectTrigger className="bg-white/5 border-[#f4d03f]/20 text-white">
                    <SelectValue placeholder="Select registered account or create new" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                    <SelectItem value="new" className="text-white hover:bg-white/10">
                      Create new sponsor manually
                    </SelectItem>
                    {unlinkedAccounts.map(account => (
                      <SelectItem key={account.id} value={account.id} className="text-white hover:bg-white/10">
                        {account.businessName} ({account.email})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-white/50 text-xs mt-2">
                  Select an existing registered account to pre-fill sponsor details, or create a new sponsor manually.
                </p>
              </div>
            )}
            {/* Logo Upload */}
            <div>
              <Label className="text-white/80">Business Logo / Picture</Label>
              <div className="mt-1.5 flex items-center gap-4">
                <div className="w-16 h-16 rounded-xl bg-white/5 border border-[#f4d03f]/20 flex items-center justify-center overflow-hidden">
                  {formData.logo || formData.picture ? (
                    <img 
                      src={formData.logo || formData.picture} 
                      alt="Logo" 
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <Building2 className="w-6 h-6 text-white/30" />
                  )}
                </div>
                <div className="flex-1">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => handleLogoUpload(e.target.files[0])}
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                    className="btn-outline-gold text-xs"
                  >
                    <Upload size={12} className="mr-1" />
                    Upload Logo
                  </Button>
                  {(formData.logo || formData.picture) && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => setFormData({ ...formData, logo: null, picture: null })}
                      className="text-red-400 hover:bg-red-500/10 ml-2 text-xs"
                    >
                      <X size={12} className="mr-1" />
                      Remove
                    </Button>
                  )}
                </div>
              </div>
            </div>
            
            <div>
              <Label className="text-white/80">Business Name *</Label>
              <Input
                value={formData.businessName}
                onChange={(e) => setFormData({ ...formData, businessName: e.target.value })}
                placeholder="Business name"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80">Email *</Label>
                <Input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="email@business.com"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                />
              </div>
              <div>
                <Label className="text-white/80">Package</Label>
                <Select
                  value={formData.package}
                  onValueChange={(value) => setFormData({ ...formData, package: value })}
                >
                  <SelectTrigger className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white">
                    <SelectValue placeholder="Select package (optional)" />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                    {packages.map(pkg => (
                      <SelectItem key={pkg.id} value={pkg.name} className="text-white hover:bg-white/10">
                        {pkg.name} - {pkg.priceLabel}
                      </SelectItem>
                    ))}
                    {alaCarteItems.map(item => (
                      <SelectItem key={item.id} value={item.name} className="text-white hover:bg-white/10">
                        🎁 {item.name} - ${item.price}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80">Contact Name</Label>
                <Input
                  value={formData.contactName}
                  onChange={(e) => setFormData({ ...formData, contactName: e.target.value })}
                  placeholder="Contact person"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                />
              </div>
              <div>
                <Label className="text-white/80">Phone</Label>
                <Input
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="(xxx) xxx-xxxx"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                />
              </div>
            </div>
            <div>
              <Label className="text-white/80">Website</Label>
              <Input
                value={formData.website}
                onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                placeholder="https://business.com"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
              />
            </div>
            <div>
              <Label className="text-white/80">Zip Code</Label>
              <Input
                value={formData.zipCode}
                onChange={(e) => setFormData({ ...formData, zipCode: e.target.value.replace(/[^\d-]/g, '').slice(0, 10) })}
                placeholder="Enter zip code for AZ discount eligibility"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
              />
              <p className="text-white/40 text-xs mt-1">AZ zip codes (85001-86556) qualify for local discounts</p>
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
            <div>
              <Label className="text-white/80">Notes</Label>
              <Textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Internal notes about this sponsor..."
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
              />
            </div>

            {/* Venue Sponsor Section - Admin Only */}
            <div className="border-t border-[#f4d03f]/10 pt-4 mt-4">
              <div className="flex items-start gap-3 p-4 bg-purple-500/10 rounded-xl border border-purple-500/20">
                <Checkbox
                  id="venueSponsor"
                  checked={formData.isVenueSponsor}
                  onCheckedChange={(checked) => setFormData({ ...formData, isVenueSponsor: checked })}
                  className="mt-0.5 border-purple-500/50 data-[state=checked]:bg-purple-500 data-[state=checked]:border-purple-500"
                />
                <div className="flex-1">
                  <label htmlFor="venueSponsor" className="text-white font-medium cursor-pointer flex items-center gap-2">
                    <MapPin size={16} className="text-purple-400" />
                    Designate as Venue Sponsor
                  </label>
                  <p className="text-white/50 text-xs mt-1">
                    <strong>Admin Only:</strong> Venue sponsors are locations where trivia events are hosted. 
                    They receive full access without requiring a paid subscription. 
                    Regular sponsors must purchase a package to activate their account.
                  </p>
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)} className="text-white">
              Cancel
            </Button>
            <Button onClick={handleSave} className="btn-gold">
              {editingSponsor ? 'Save Changes' : 'Add Sponsor'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Placement Matrix Modal */}
      {matrixSponsor && (
        <SponsorPlacementMatrix
          sponsor={matrixSponsor}
          onClose={() => setMatrixSponsor(null)}
        />
      )}

      {/* User Profile Management Modal */}
      <Dialog open={profileModalOpen} onOpenChange={setProfileModalOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <User size={20} className="text-[#f4d03f]" />
              User Profile Management
              {selectedSponsor && (
                <span className="text-white/50 font-normal ml-2">- {selectedSponsor.businessName}</span>
              )}
            </DialogTitle>
          </DialogHeader>

          {loadingProfile ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-[#f4d03f] animate-spin" />
            </div>
          ) : (
            <>
              {/* Tab Navigation */}
              <div className="flex gap-2 border-b border-[#f4d03f]/10 pb-2">
                <button
                  onClick={() => setActiveProfileTab('profile')}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeProfileTab === 'profile'
                      ? 'bg-[#f4d03f] text-[#1a1a2e]'
                      : 'text-white/60 hover:text-white hover:bg-white/10'
                  }`}
                >
                  Profile Info
                </button>
                <button
                  onClick={() => setActiveProfileTab('assets')}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activeProfileTab === 'assets'
                      ? 'bg-[#f4d03f] text-[#1a1a2e]'
                      : 'text-white/60 hover:text-white hover:bg-white/10'
                  }`}
                >
                  Assets ({userAssets.length})
                </button>
              </div>

              {/* Profile Tab */}
              {activeProfileTab === 'profile' && (
                <div className="space-y-4 py-4">
                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-white/80 flex items-center gap-2">
                        <Building2 size={14} /> Business Name
                      </Label>
                      <Input
                        value={profileData.businessName}
                        onChange={(e) => setProfileData({ ...profileData, businessName: e.target.value })}
                        className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                      />
                    </div>
                    <div>
                      <Label className="text-white/80 flex items-center gap-2">
                        <User size={14} /> Contact Name
                      </Label>
                      <Input
                        value={profileData.contactName}
                        onChange={(e) => setProfileData({ ...profileData, contactName: e.target.value })}
                        className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                      />
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-white/80 flex items-center gap-2">
                        <Mail size={14} /> Email
                      </Label>
                      <Input
                        value={profileData.email}
                        disabled
                        className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white/50"
                      />
                    </div>
                    <div>
                      <Label className="text-white/80 flex items-center gap-2">
                        <Phone size={14} /> Phone
                      </Label>
                      <Input
                        value={profileData.phone}
                        onChange={(e) => setProfileData({ ...profileData, phone: e.target.value })}
                        className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                      />
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-white/80 flex items-center gap-2">
                        <Globe size={14} /> Website
                      </Label>
                      <Input
                        value={profileData.website}
                        onChange={(e) => setProfileData({ ...profileData, website: e.target.value })}
                        className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                      />
                    </div>
                    <div>
                      <Label className="text-white/80 flex items-center gap-2">
                        <MapPin size={14} /> Zip Code
                      </Label>
                      <div className="flex gap-2 mt-1.5">
                        <Input
                          value={profileData.zipCode}
                          onChange={(e) => setProfileData({ ...profileData, zipCode: e.target.value.replace(/[^\d-]/g, '').slice(0, 10) })}
                          placeholder="Enter zip code"
                          className="bg-white/5 border-[#f4d03f]/20 text-white"
                        />
                        {profileData.zipCode && profileData.isAzResident && (
                          <Badge className="bg-green-500/20 text-green-400 border-green-500/30 whitespace-nowrap">
                            <CheckCircle size={12} className="mr-1" />
                            AZ Resident
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Sponsor Status Section */}
                  <div className="border-t border-[#f4d03f]/10 pt-4 mt-4">
                    <h3 className="text-white font-medium mb-3">Sponsor Status</h3>
                    <div className="grid sm:grid-cols-3 gap-4">
                      <div>
                        <Label className="text-white/80">Package</Label>
                        <Select
                          value={profileData.package || 'none'}
                          onValueChange={(value) => setProfileData({ ...profileData, package: value === 'none' ? '' : value })}
                        >
                          <SelectTrigger className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white">
                            <SelectValue placeholder="Select package" />
                          </SelectTrigger>
                          <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                            <SelectItem value="none" className="text-white hover:bg-white/10">No Package</SelectItem>
                            {sponsorshipPackages.filter(p => p.id !== 'alacarte').map((pkg) => (
                              <SelectItem key={pkg.id} value={pkg.name} className="text-white hover:bg-white/10">
                                {pkg.name}
                              </SelectItem>
                            ))}
                            {alaCarteItems.map(item => (
                              <SelectItem key={item.id} value={item.name} className="text-white hover:bg-white/10">
                                🎁 {item.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <Label className="text-white/80">Status</Label>
                        <Select
                          value={profileData.status}
                          onValueChange={(value) => setProfileData({ ...profileData, status: value })}
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
                      <div className="flex items-end">
                        <div className="flex items-center gap-2 p-2 bg-purple-500/10 rounded-lg border border-purple-500/20 w-full">
                          <Checkbox
                            id="profileVenueSponsor"
                            checked={profileData.isVenueSponsor}
                            onCheckedChange={(checked) => setProfileData({ ...profileData, isVenueSponsor: checked })}
                            className="border-purple-500/50 data-[state=checked]:bg-purple-500"
                          />
                          <label htmlFor="profileVenueSponsor" className="text-white text-sm cursor-pointer flex items-center gap-1">
                            <MapPin size={14} className="text-purple-400" />
                            Venue Sponsor
                          </label>
                        </div>
                      </div>
                    </div>
                  </div>

                  <DialogFooter className="mt-6">
                    <Button variant="ghost" onClick={() => setProfileModalOpen(false)} className="text-white">
                      Cancel
                    </Button>
                    <Button onClick={handleSaveProfile} disabled={savingProfile} className="btn-gold">
                      {savingProfile ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                      Save Changes
                    </Button>
                  </DialogFooter>
                </div>
              )}

              {/* Assets Tab */}
              {activeProfileTab === 'assets' && (
                <div className="py-4">
                  {userAssets.length === 0 ? (
                    <div className="text-center py-12 text-white/50">
                      <Image size={48} className="mx-auto mb-4 opacity-50" />
                      <p>No assets uploaded yet</p>
                    </div>
                  ) : (
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {userAssets.map((asset) => (
                        <div key={asset.id} className="card-dark rounded-xl overflow-hidden group">
                          {/* Asset Preview */}
                          <div className="aspect-video bg-white/5 relative overflow-hidden">
                            {asset.file_data || asset.thumbnail_url ? (
                              <img
                                src={asset.file_data || asset.thumbnail_url}
                                alt={asset.file_name}
                                className="w-full h-full object-contain"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-white/30">
                                <Image size={32} />
                              </div>
                            )}
                            {/* Status Badge */}
                            <Badge
                              className={`absolute top-2 right-2 ${
                                asset.status === 'approved'
                                  ? 'bg-green-500/80 text-white'
                                  : asset.status === 'pending'
                                  ? 'bg-orange-500/80 text-white'
                                  : 'bg-red-500/80 text-white'
                              }`}
                            >
                              {asset.status}
                            </Badge>
                            {/* Hover Preview Button */}
                            <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                              <Button
                                size="sm"
                                variant="secondary"
                                className="bg-white/20 hover:bg-white/30 text-white"
                                onClick={() => handleAssetPreview(asset)}
                              >
                                <Eye size={16} className="mr-1" />
                                Preview
                              </Button>
                            </div>
                          </div>
                          {/* Asset Info */}
                          <div className="p-3">
                            <p className="text-white text-sm font-medium truncate">{asset.file_name}</p>
                            <p className="text-white/50 text-xs">{asset.aspect_ratio || 'Unknown ratio'}</p>
                            {/* Actions */}
                            <div className="flex gap-2 mt-3">
                              {asset.status === 'pending' && (
                                <>
                                  <Button
                                    size="sm"
                                    onClick={() => handleAssetStatusChange(asset.id, 'approve')}
                                    className="flex-1 bg-green-500/20 text-green-400 hover:bg-green-500/30"
                                  >
                                    <CheckCircle size={14} className="mr-1" />
                                    Approve
                                  </Button>
                                  <Button
                                    size="sm"
                                    onClick={() => handleAssetStatusChange(asset.id, 'reject')}
                                    className="flex-1 bg-red-500/20 text-red-400 hover:bg-red-500/30"
                                  >
                                    <XCircle size={14} className="mr-1" />
                                    Reject
                                  </Button>
                                </>
                              )}
                              <AlertDialog>
                                <AlertDialogTrigger asChild>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="text-white/60 hover:text-red-400 hover:bg-red-500/10"
                                  >
                                    <Trash2 size={14} />
                                  </Button>
                                </AlertDialogTrigger>
                                <AlertDialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                                  <AlertDialogHeader>
                                    <AlertDialogTitle className="text-white">Delete Asset</AlertDialogTitle>
                                    <AlertDialogDescription className="text-white/60">
                                      Are you sure you want to delete this asset? This action cannot be undone.
                                    </AlertDialogDescription>
                                  </AlertDialogHeader>
                                  <AlertDialogFooter>
                                    <AlertDialogCancel className="bg-white/10 text-white border-0">Cancel</AlertDialogCancel>
                                    <AlertDialogAction
                                      onClick={() => handleDeleteAsset(asset.id)}
                                      className="bg-red-500 hover:bg-red-600 text-white"
                                    >
                                      Delete
                                    </AlertDialogAction>
                                  </AlertDialogFooter>
                                </AlertDialogContent>
                              </AlertDialog>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Asset Preview Dialog */}
      <Dialog open={assetPreviewOpen} onOpenChange={setAssetPreviewOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-white">{previewAsset?.file_name || 'Asset Preview'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {previewAsset?.file_data || previewAsset?.thumbnail_url ? (
              <img
                src={previewAsset.file_data || previewAsset.thumbnail_url}
                alt={previewAsset?.file_name || 'Asset'}
                className="w-full rounded-lg"
              />
            ) : (
              <div className="w-full h-48 bg-[#0f0f1a] rounded-lg flex items-center justify-center">
                <div className="text-center">
                  <Image className="w-16 h-16 text-white/20 mx-auto mb-2" />
                  <p className="text-white/50 text-sm">No image data available</p>
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-4 text-sm bg-white/5 rounded-xl p-4">
              <div>
                <p className="text-white/50">File Name</p>
                <p className="text-white">{previewAsset?.file_name || 'Unknown'}</p>
              </div>
              <div>
                <p className="text-white/50">Status</p>
                <Badge
                  className={
                    previewAsset?.status === 'approved'
                      ? 'bg-green-500/20 text-green-400'
                      : previewAsset?.status === 'pending'
                      ? 'bg-orange-500/20 text-orange-400'
                      : 'bg-red-500/20 text-red-400'
                  }
                >
                  {previewAsset?.status || 'Unknown'}
                </Badge>
              </div>
              <div>
                <p className="text-white/50">Format</p>
                <p className="text-white">{previewAsset?.aspect_ratio || previewAsset?.type || 'Unknown'}</p>
              </div>
              <div>
                <p className="text-white/50">Uploaded</p>
                <p className="text-white">{previewAsset?.uploaded_at || 'Unknown'}</p>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SponsorsManagement;
