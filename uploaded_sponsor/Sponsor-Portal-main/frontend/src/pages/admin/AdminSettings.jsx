import React, { useState, useEffect } from 'react';
import { Save, Bell, Mail, Shield, UserPlus, Users, Trash2, Key, Building2, Check, AlertCircle, Search, RefreshCw, Link2, LinkIcon, Unlink, Cloud, CloudOff, CheckCircle, XCircle, Clock, FolderSync, HardDrive } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { Badge } from '../../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../../components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
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
} from '../../components/ui/alert-dialog';
import { toast } from 'sonner';
import { useData } from '../../context/DataContext';
import { accountsApi, canvaApi, sharePointApi } from '../../services/api';

const AdminSettings = () => {
  const { sponsors, refetch } = useData();
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState({
    notifyNewSponsors: true,
    notifyNewAssets: true,
    autoApprove: false,
    maxFileSize: 5,
    supportEmail: 'sponsors@bighat.live',
  });

  // User Profile Management State
  const [profiles, setProfiles] = useState([]);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [newProfile, setNewProfile] = useState({
    email: '',
    businessName: '',
    contactName: '',
    phone: '',
    website: '',
    linkToSponsor: '',
  });

  // Canva Integration State
  const [canvaStatus, setCanvaStatus] = useState({ connected: false });
  const [canvaLoading, setCanvaLoading] = useState(false);
  const [syncLogs, setSyncLogs] = useState([]);
  const [pendingSyncCount, setPendingSyncCount] = useState(0);
  const [syncing, setSyncing] = useState(false);

  // SharePoint Integration State
  const [spStatus, setSpStatus] = useState({ connected: false });
  const [spLoading, setSpLoading] = useState(false);
  const [spSyncLogs, setSpSyncLogs] = useState([]);
  const [spSyncing, setSpSyncing] = useState(false);

  // Load registered accounts and Canva status
  useEffect(() => {
    loadProfiles();
    loadCanvaStatus();
    loadSyncLogs();
    loadPendingSyncCount();
    loadSharePointStatus();
    loadSharePointSyncLogs();

    // Check for Canva OAuth callback result
    const urlParams = new URLSearchParams(window.location.search);
    
    // Handle successful connection (redirected from backend)
    if (urlParams.get('canva_connected') === 'true') {
      toast.success('Canva connected successfully!');
      loadCanvaStatus();
      // Clean URL
      window.history.replaceState({}, document.title, window.location.pathname);
    }
    
    // Handle error from OAuth
    if (urlParams.get('canva_error')) {
      const error = urlParams.get('canva_error');
      toast.error(`Canva connection failed: ${error}`);
      // Clean URL
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  const loadProfiles = async () => {
    setLoadingProfiles(true);
    try {
      const accounts = await accountsApi.getAll();
      setProfiles(accounts);
    } catch (err) {
      console.error('Failed to load profiles:', err);
    } finally {
      setLoadingProfiles(false);
    }
  };

  // Canva Functions
  const loadCanvaStatus = async () => {
    try {
      const status = await canvaApi.getStatus();
      setCanvaStatus(status);
    } catch (err) {
      console.error('Failed to load Canva status:', err);
    }
  };

  const loadSyncLogs = async () => {
    try {
      const logs = await canvaApi.getSyncLogs(5);
      setSyncLogs(logs);
    } catch (err) {
      console.error('Failed to load sync logs:', err);
    }
  };

  const loadPendingSyncCount = async () => {
    try {
      const data = await canvaApi.getPendingSyncCount();
      setPendingSyncCount(data.pending_count || 0);
    } catch (err) {
      console.error('Failed to load pending sync count:', err);
    }
  };

  const handleConnectCanva = async () => {
    setCanvaLoading(true);
    try {
      const data = await canvaApi.initiateAuth();
      // Redirect to Canva OAuth - backend will handle callback and redirect back
      window.location.href = data.auth_url;
    } catch (err) {
      console.error('Failed to initiate Canva auth:', err);
      toast.error('Failed to connect to Canva');
      setCanvaLoading(false);
    }
  };

  const handleDisconnectCanva = async () => {
    setCanvaLoading(true);
    try {
      await canvaApi.disconnect();
      setCanvaStatus({ connected: false });
      toast.success('Canva disconnected');
    } catch (err) {
      console.error('Failed to disconnect Canva:', err);
      toast.error('Failed to disconnect Canva');
    } finally {
      setCanvaLoading(false);
    }
  };

  const handleSyncNow = async () => {
    setSyncing(true);
    try {
      await canvaApi.triggerSync();
      toast.success('Sync started! Images will be uploaded to Canva.');
      // Refresh status after a delay
      setTimeout(() => {
        loadSyncLogs();
        loadPendingSyncCount();
      }, 3000);
    } catch (err) {
      console.error('Failed to trigger sync:', err);
      toast.error(err.message || 'Failed to start sync');
    } finally {
      setSyncing(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString();
  };

  // SharePoint Functions
  const loadSharePointStatus = async () => {
    try {
      const status = await sharePointApi.getStatus();
      setSpStatus(status);
    } catch (err) {
      console.error('Failed to load SharePoint status:', err);
    }
  };

  const loadSharePointSyncLogs = async () => {
    try {
      const logs = await sharePointApi.getSyncLogs(5);
      setSpSyncLogs(logs);
    } catch (err) {
      console.error('Failed to load SharePoint sync logs:', err);
    }
  };

  const handleSharePointSync = async (syncType = 'all') => {
    setSpSyncing(true);
    try {
      await sharePointApi.triggerSync(syncType);
      
      const messages = {
        'all': 'Full SharePoint sync started! All venue PowerPoints will be updated.',
        'venue': 'Venue sponsor sync started! Slide 2 of venue PowerPoints will be updated.',
        'advertising': 'Advertising sponsor sync started! Slide 3 of enabled venue PowerPoints will be updated.'
      };
      
      toast.success(messages[syncType] || messages['all']);
      setTimeout(() => {
        loadSharePointSyncLogs();
      }, 5000);
    } catch (err) {
      console.error('Failed to trigger SharePoint sync:', err);
      toast.error(err.message || 'Failed to start SharePoint sync');
    } finally {
      setSpSyncing(false);
    }
  };

  const handleSaveSettings = () => {
    setLoading(true);
    setTimeout(() => {
      toast.success('Settings saved successfully!');
      setLoading(false);
    }, 1000);
  };

  // Get sponsors that don't have linked accounts
  const getUnlinkedSponsors = () => {
    const linkedEmails = profiles.map(p => p.email?.toLowerCase());
    return sponsors.filter(s => !linkedEmails.includes(s.email?.toLowerCase()));
  };

  const handleCreateProfile = async () => {
    if (!newProfile.email) {
      toast.error('Email is required');
      return;
    }

    setLoading(true);
    try {
      // If linking to existing sponsor, pre-fill data from sponsor
      let profileData = { ...newProfile };
      
      if (newProfile.linkToSponsor) {
        const sponsor = sponsors.find(s => s.id === newProfile.linkToSponsor);
        if (sponsor) {
          profileData = {
            ...profileData,
            email: sponsor.email || profileData.email,
            businessName: sponsor.businessName || profileData.businessName,
            contactName: sponsor.contactName || profileData.contactName,
            phone: sponsor.phone || profileData.phone,
            website: sponsor.website || profileData.website,
          };
        }
      }

      // Create account with default password
      await accountsApi.adminCreate(profileData);
      
      toast.success(
        `Profile created for ${profileData.email}. Default password is "B1GHat" - they will need to reset it and verify their information on first login.`
      );
      
      setCreateDialogOpen(false);
      setNewProfile({
        email: '',
        businessName: '',
        contactName: '',
        phone: '',
        website: '',
        linkToSponsor: '',
      });
      
      // Reload profiles
      await loadProfiles();
      await refetch();
      
    } catch (err) {
      console.error('Failed to create profile:', err);
      toast.error(err.message || 'Failed to create profile');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteProfile = async (profileId, email) => {
    try {
      await accountsApi.delete(profileId);
      toast.success(`Profile for ${email} deleted`);
      await loadProfiles();
    } catch (err) {
      console.error('Failed to delete profile:', err);
      toast.error('Failed to delete profile');
    }
  };

  const handleSponsorSelect = (sponsorId) => {
    setNewProfile(prev => ({ ...prev, linkToSponsor: sponsorId }));
    
    if (sponsorId && sponsorId !== 'none') {
      const sponsor = sponsors.find(s => s.id === sponsorId);
      if (sponsor) {
        setNewProfile(prev => ({
          ...prev,
          linkToSponsor: sponsorId,
          email: sponsor.email || '',
          businessName: sponsor.businessName || '',
          contactName: sponsor.contactName || '',
          phone: sponsor.phone || '',
          website: sponsor.website || '',
        }));
      }
    }
  };

  // Filter profiles by search
  const filteredProfiles = profiles.filter(p => 
    (p.email?.toLowerCase() || '').includes(searchQuery.toLowerCase()) ||
    (p.business_name?.toLowerCase() || '').includes(searchQuery.toLowerCase()) ||
    (p.contact_name?.toLowerCase() || '').includes(searchQuery.toLowerCase())
  );

  const unlinkedSponsors = getUnlinkedSponsors();

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Admin Settings</h1>
      <p className="text-white/60 mb-8">Configure system preferences and manage user profiles</p>

      <div className="space-y-8">
        {/* User Profile Management - NEW SECTION */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Users className="w-5 h-5 text-[#f4d03f]" />
              <div>
                <h2 className="text-lg font-bold text-white">User Profile Management</h2>
                <p className="text-white/50 text-sm">Create and manage user login profiles</p>
              </div>
            </div>
            <Button onClick={() => setCreateDialogOpen(true)} className="btn-gold">
              <UserPlus size={16} className="mr-2" />
              Create Profile
            </Button>
          </div>

          {/* Info Box */}
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4 mb-6">
            <p className="text-blue-400 text-sm">
              <strong>How it works:</strong> When you create a profile, the user will receive a default password 
              (<code className="bg-blue-500/20 px-1 rounded">B1GHat</code>). On their first login, they&apos;ll be 
              prompted to create a new password and verify their profile information. This is ideal for venue 
              sponsors who need quick setup.
            </p>
          </div>

          {/* Search */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" size={18} />
            <Input
              placeholder="Search profiles..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/40"
            />
          </div>

          {/* Profiles List */}
          <div className="space-y-3 max-h-[400px] overflow-y-auto">
            {loadingProfiles ? (
              <div className="text-center py-8 text-white/50">Loading profiles...</div>
            ) : filteredProfiles.length === 0 ? (
              <div className="text-center py-8 text-white/50">
                {searchQuery ? 'No profiles match your search' : 'No user profiles created yet'}
              </div>
            ) : (
              filteredProfiles.map((profile) => (
                <div 
                  key={profile.id} 
                  className="flex items-center justify-between p-4 bg-white/5 rounded-xl hover:bg-white/10 transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-full bg-[#f4d03f]/20 flex items-center justify-center">
                      <span className="text-[#f4d03f] font-bold text-sm">
                        {(profile.contact_name || profile.email || '?').charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <p className="text-white font-medium">
                        {profile.contact_name || profile.business_name || 'Unknown'}
                      </p>
                      <p className="text-white/50 text-sm">{profile.email}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {/* Status Badges */}
                    {profile.must_reset_password && (
                      <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30">
                        <Key size={12} className="mr-1" /> Needs Password Reset
                      </Badge>
                    )}
                    {profile.created_by_admin && !profile.must_reset_password && (
                      <Badge className="bg-green-500/20 text-green-400 border-green-500/30">
                        <Check size={12} className="mr-1" /> Active
                      </Badge>
                    )}
                    {profile.google_linked && (
                      <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">
                        Google Linked
                      </Badge>
                    )}
                    
                    {/* Delete Button */}
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="sm" className="text-red-400 hover:text-red-300 hover:bg-red-500/10">
                          <Trash2 size={16} />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                        <AlertDialogHeader>
                          <AlertDialogTitle className="text-white">Delete Profile</AlertDialogTitle>
                          <AlertDialogDescription className="text-white/60">
                            Are you sure you want to delete the profile for <strong>{profile.email}</strong>? 
                            This will remove their login access but won&apos;t affect their sponsor data.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel className="bg-white/10 text-white border-white/20 hover:bg-white/20">
                            Cancel
                          </AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => handleDeleteProfile(profile.id, profile.email)}
                            className="bg-red-500 hover:bg-red-600 text-white"
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Stats */}
          <div className="flex gap-4 mt-4 pt-4 border-t border-white/10">
            <div className="text-center">
              <p className="text-2xl font-bold text-[#f4d03f]">{profiles.length}</p>
              <p className="text-white/50 text-xs">Total Profiles</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-yellow-400">
                {profiles.filter(p => p.must_reset_password).length}
              </p>
              <p className="text-white/50 text-xs">Pending Setup</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-green-400">
                {profiles.filter(p => !p.must_reset_password && p.created_by_admin).length}
              </p>
              <p className="text-white/50 text-xs">Active</p>
            </div>
          </div>
        </div>

        {/* Canva Integration */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Cloud className="w-5 h-5 text-[#f4d03f]" />
              <div>
                <h2 className="text-lg font-bold text-white">Canva Integration</h2>
                <p className="text-white/50 text-sm">Sync sponsor images to your Canva Teams account</p>
              </div>
            </div>
            {canvaStatus.connected && (
              <Button 
                onClick={handleSyncNow} 
                disabled={syncing || pendingSyncCount === 0}
                className="btn-gold"
              >
                <RefreshCw size={16} className={`mr-2 ${syncing ? 'animate-spin' : ''}`} />
                {syncing ? 'Syncing...' : `Sync Now (${pendingSyncCount})`}
              </Button>
            )}
          </div>

          {/* Connection Status */}
          <div className={`p-4 rounded-xl mb-6 ${canvaStatus.connected ? 'bg-green-500/10 border border-green-500/20' : 'bg-white/5 border border-white/10'}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {canvaStatus.connected ? (
                  <CheckCircle className="w-6 h-6 text-green-400" />
                ) : (
                  <CloudOff className="w-6 h-6 text-white/40" />
                )}
                <div>
                  <p className={`font-medium ${canvaStatus.connected ? 'text-green-400' : 'text-white'}`}>
                    {canvaStatus.connected ? 'Connected to Canva Teams' : 'Not Connected'}
                  </p>
                  {canvaStatus.connected && canvaStatus.last_sync && (
                    <p className="text-white/50 text-sm">Last sync: {formatDate(canvaStatus.last_sync)}</p>
                  )}
                </div>
              </div>
              
              {canvaStatus.connected ? (
                <Button 
                  variant="outline" 
                  onClick={handleDisconnectCanva}
                  disabled={canvaLoading}
                  className="border-red-500/30 text-red-400 hover:bg-red-500/10"
                >
                  <Unlink size={16} className="mr-2" />
                  Disconnect
                </Button>
              ) : (
                <Button 
                  onClick={handleConnectCanva}
                  disabled={canvaLoading}
                  className="btn-gold"
                >
                  <LinkIcon size={16} className="mr-2" />
                  {canvaLoading ? 'Connecting...' : 'Connect Canva'}
                </Button>
              )}
            </div>
          </div>

          {/* Info Box */}
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4 mb-6">
            <p className="text-blue-400 text-sm">
              <strong>How it works:</strong> Approved sponsor images are automatically synced to your Canva Teams 
              account daily at 6:00 AM MST. Images are organized into folders: <code className="bg-blue-500/20 px-1 rounded">Sponsors/[Company Name]/16x9</code> and 
              <code className="bg-blue-500/20 px-1 rounded ml-1">Sponsors/[Company Name]/1x1</code>. Preferred images are marked with [PREFERRED] in their name.
            </p>
          </div>

          {/* Sync Stats */}
          {canvaStatus.connected && (
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-white/5 rounded-xl p-4 text-center">
                <Clock className="w-5 h-5 text-yellow-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-yellow-400">{pendingSyncCount}</p>
                <p className="text-white/50 text-xs">Pending Sync</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4 text-center">
                <CheckCircle className="w-5 h-5 text-green-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-green-400">
                  {syncLogs[0]?.successful_uploads || 0}
                </p>
                <p className="text-white/50 text-xs">Last Sync Success</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4 text-center">
                <XCircle className="w-5 h-5 text-red-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-red-400">
                  {syncLogs[0]?.failed_uploads || 0}
                </p>
                <p className="text-white/50 text-xs">Last Sync Failed</p>
              </div>
            </div>
          )}

          {/* Recent Sync Logs */}
          {canvaStatus.connected && syncLogs.length > 0 && (
            <div>
              <h3 className="text-white font-medium mb-3">Recent Sync History</h3>
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {syncLogs.map((log) => (
                  <div key={log.id} className="flex items-center justify-between p-3 bg-white/5 rounded-lg text-sm">
                    <div className="flex items-center gap-3">
                      {log.failed_uploads === 0 ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : log.successful_uploads > 0 ? (
                        <AlertCircle className="w-4 h-4 text-yellow-400" />
                      ) : (
                        <XCircle className="w-4 h-4 text-red-400" />
                      )}
                      <span className="text-white/70">{formatDate(log.started_at)}</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${log.sync_type === 'automatic' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'}`}>
                        {log.sync_type}
                      </span>
                    </div>
                    <span className="text-white/50">
                      {log.successful_uploads}/{log.total_images} synced
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* SharePoint Integration */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <HardDrive className="w-5 h-5 text-[#f4d03f]" />
              <div>
                <h2 className="text-lg font-bold text-white">SharePoint Integration</h2>
                <p className="text-white/50 text-sm">Sync sponsor images to PowerPoint presentations</p>
              </div>
            </div>
            <div className="flex gap-2">
              <Button 
                onClick={() => handleSharePointSync('all')} 
                disabled={spSyncing}
                className="btn-gold"
              >
                <FolderSync size={16} className={`mr-2 ${spSyncing ? 'animate-spin' : ''}`} />
                {spSyncing ? 'Syncing...' : 'Sync All'}
              </Button>
            </div>
          </div>

          {/* Connection Status */}
          <div className={`p-4 rounded-xl mb-6 ${spStatus.connected ? 'bg-green-500/10 border border-green-500/20' : 'bg-white/5 border border-white/10'}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {spStatus.connected ? (
                  <CheckCircle className="w-6 h-6 text-green-400" />
                ) : spStatus.error ? (
                  <XCircle className="w-6 h-6 text-red-400" />
                ) : (
                  <CloudOff className="w-6 h-6 text-white/40" />
                )}
                <div>
                  <p className={`font-medium ${spStatus.connected ? 'text-green-400' : spStatus.error ? 'text-red-400' : 'text-white'}`}>
                    {spStatus.connected ? 'Connected to SharePoint' : spStatus.error ? 'Connection Error' : 'Checking...'}
                  </p>
                  {spStatus.connected && spStatus.last_sync && (
                    <p className="text-white/50 text-sm">Last sync: {formatDate(spStatus.last_sync)}</p>
                  )}
                  {spStatus.error && (
                    <p className="text-red-400/70 text-sm">{spStatus.error}</p>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Sync Types */}
          <div className="grid md:grid-cols-2 gap-4 mb-6">
            {/* Venue Sponsors */}
            <div className="bg-purple-500/10 border border-purple-500/20 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Building2 className="w-5 h-5 text-purple-400" />
                  <h3 className="text-white font-medium">Venue Sponsors</h3>
                </div>
                <Button 
                  onClick={() => handleSharePointSync('venue')} 
                  disabled={spSyncing}
                  size="sm"
                  variant="outline"
                  className="border-purple-500/30 text-purple-400 hover:bg-purple-500/10"
                >
                  <FolderSync size={14} className="mr-1" />
                  Sync
                </Button>
              </div>
              <p className="text-white/60 text-sm">
                Syncs venue sponsor 16:9 images to their <strong className="text-purple-400">location folder</strong> in SharePoint.
              </p>
            </div>

            {/* Advertising Sponsors */}
            <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Users className="w-5 h-5 text-blue-400" />
                  <h3 className="text-white font-medium">Advertising Sponsors</h3>
                </div>
                <Button 
                  onClick={() => handleSharePointSync('advertising')} 
                  disabled={spSyncing}
                  size="sm"
                  variant="outline"
                  className="border-blue-500/30 text-blue-400 hover:bg-blue-500/10"
                >
                  <FolderSync size={14} className="mr-1" />
                  Sync
                </Button>
              </div>
              <p className="text-white/60 text-sm">
                Syncs advertising sponsor 16:9 images to their own <strong className="text-blue-400">Sponsors/{'{'}SponsorName{'}'}</strong> folder in SharePoint.
              </p>
            </div>
          </div>

          {/* Info Box */}
          <div className="bg-[#f4d03f]/10 border border-[#f4d03f]/20 rounded-xl p-4 mb-6">
            <p className="text-[#f4d03f] text-sm">
              <strong>How it works:</strong> When you approve a 16:9 image, it is automatically uploaded to SharePoint. 
              Venue sponsors get their image in their location&apos;s folder. 
              Advertising sponsors get a dedicated folder (Sponsors/{'{'}Name{'}'}) created for them. 
              1:1 images are synced to Canva for use in trivia overlays.
            </p>
          </div>

          {/* Sync Stats */}
          {spSyncLogs.length > 0 && (
            <div className="grid grid-cols-4 gap-4 mb-6">
              <div className="bg-white/5 rounded-xl p-4 text-center">
                <Clock className="w-5 h-5 text-blue-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-blue-400">{spSyncLogs[0]?.total_locations || 0}</p>
                <p className="text-white/50 text-xs">Operations</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4 text-center">
                <CheckCircle className="w-5 h-5 text-green-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-green-400">{spSyncLogs[0]?.successful_updates || 0}</p>
                <p className="text-white/50 text-xs">Updated</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4 text-center">
                <AlertCircle className="w-5 h-5 text-yellow-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-yellow-400">{spSyncLogs[0]?.skipped || 0}</p>
                <p className="text-white/50 text-xs">Skipped</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4 text-center">
                <XCircle className="w-5 h-5 text-red-400 mx-auto mb-2" />
                <p className="text-2xl font-bold text-red-400">{spSyncLogs[0]?.failed_updates || 0}</p>
                <p className="text-white/50 text-xs">Failed</p>
              </div>
            </div>
          )}

          {/* Recent Sync Logs */}
          {spSyncLogs.length > 0 && (
            <div>
              <h3 className="text-white font-medium mb-3">Recent SharePoint Sync History</h3>
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {spSyncLogs.map((log) => (
                  <div key={log.id} className="flex items-center justify-between p-3 bg-white/5 rounded-lg text-sm">
                    <div className="flex items-center gap-3">
                      {log.failed_updates === 0 ? (
                        <CheckCircle className="w-4 h-4 text-green-400" />
                      ) : log.successful_updates > 0 ? (
                        <AlertCircle className="w-4 h-4 text-yellow-400" />
                      ) : (
                        <XCircle className="w-4 h-4 text-red-400" />
                      )}
                      <span className="text-white/70">{formatDate(log.started_at)}</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        log.sync_type === 'advertising_sponsors' 
                          ? 'bg-blue-500/20 text-blue-400'
                          : log.sync_type === 'full_sync'
                            ? 'bg-[#f4d03f]/20 text-[#f4d03f]'
                            : 'bg-purple-500/20 text-purple-400'
                      }`}>
                        {log.sync_type === 'advertising_sponsors' ? 'Ad Sponsors' : 
                         log.sync_type === 'full_sync' ? 'Full Sync' : 'Venue Sponsors'}
                      </span>
                    </div>
                    <span className="text-white/50">
                      {log.successful_updates}/{log.total_locations} updated ({log.skipped} skipped)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Notifications */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Bell className="w-5 h-5 text-[#f4d03f]" />
            <h2 className="text-lg font-bold text-white">Notifications</h2>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl">
              <div>
                <p className="text-white font-medium">New Sponsor Signups</p>
                <p className="text-white/50 text-sm">Get notified when a new sponsor registers</p>
              </div>
              <Switch
                checked={settings.notifyNewSponsors}
                onCheckedChange={(checked) => setSettings({ ...settings, notifyNewSponsors: checked })}
              />
            </div>
            <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl">
              <div>
                <p className="text-white font-medium">New Asset Uploads</p>
                <p className="text-white/50 text-sm">Get notified when assets are submitted for review</p>
              </div>
              <Switch
                checked={settings.notifyNewAssets}
                onCheckedChange={(checked) => setSettings({ ...settings, notifyNewAssets: checked })}
              />
            </div>
          </div>
        </div>

        {/* Media Settings */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Shield className="w-5 h-5 text-[#f4d03f]" />
            <h2 className="text-lg font-bold text-white">Media Settings</h2>
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl">
              <div>
                <p className="text-white font-medium">Auto-Approve Assets</p>
                <p className="text-white/50 text-sm">Automatically approve assets that pass validation</p>
              </div>
              <Switch
                checked={settings.autoApprove}
                onCheckedChange={(checked) => setSettings({ ...settings, autoApprove: checked })}
              />
            </div>
            <div>
              <Label className="text-white/80">Max File Size (MB)</Label>
              <Input
                type="number"
                value={settings.maxFileSize}
                onChange={(e) => setSettings({ ...settings, maxFileSize: parseInt(e.target.value) })}
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white w-32"
              />
            </div>
          </div>
        </div>

        {/* Contact Settings */}
        <div className="card-dark rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-6">
            <Mail className="w-5 h-5 text-[#f4d03f]" />
            <h2 className="text-lg font-bold text-white">Contact Settings</h2>
          </div>
          <div>
            <Label className="text-white/80">Support Email</Label>
            <Input
              type="email"
              value={settings.supportEmail}
              onChange={(e) => setSettings({ ...settings, supportEmail: e.target.value })}
              className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
            />
          </div>
        </div>

        <Button onClick={handleSaveSettings} disabled={loading} className="btn-gold">
          <Save size={16} className="mr-2" />
          {loading ? 'Saving...' : 'Save Settings'}
        </Button>
      </div>

      {/* Create Profile Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <UserPlus className="w-5 h-5 text-[#f4d03f]" />
              Create User Profile
            </DialogTitle>
            <DialogDescription className="text-white/60">
              Create a login profile for a sponsor or venue. They&apos;ll receive a default password and 
              must verify their information on first login.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Link to Existing Sponsor */}
            {unlinkedSponsors.length > 0 && (
              <div className="space-y-2">
                <Label className="text-white/80">Link to Existing Sponsor (Optional)</Label>
                <Select value={newProfile.linkToSponsor} onValueChange={handleSponsorSelect}>
                  <SelectTrigger className="bg-white/5 border-[#f4d03f]/20 text-white">
                    <SelectValue placeholder="Select a sponsor to link..." />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                    <SelectItem value="none" className="text-white hover:bg-white/10">
                      Create without linking
                    </SelectItem>
                    {unlinkedSponsors.map(sponsor => (
                      <SelectItem key={sponsor.id} value={sponsor.id} className="text-white hover:bg-white/10">
                        <div className="flex items-center gap-2">
                          <Building2 size={14} className="text-[#f4d03f]" />
                          {sponsor.businessName} ({sponsor.email})
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-white/40 text-xs">
                  Linking will auto-fill the form with sponsor information
                </p>
              </div>
            )}

            {/* Email */}
            <div className="space-y-2">
              <Label className="text-white/80">Email Address *</Label>
              <Input
                type="email"
                value={newProfile.email}
                onChange={(e) => setNewProfile({ ...newProfile, email: e.target.value })}
                placeholder="user@business.com"
                className="bg-white/5 border-[#f4d03f]/20 text-white"
              />
            </div>

            {/* Business Name */}
            <div className="space-y-2">
              <Label className="text-white/80">Business Name</Label>
              <Input
                value={newProfile.businessName}
                onChange={(e) => setNewProfile({ ...newProfile, businessName: e.target.value })}
                placeholder="Business LLC"
                className="bg-white/5 border-[#f4d03f]/20 text-white"
              />
            </div>

            {/* Contact Name */}
            <div className="space-y-2">
              <Label className="text-white/80">Contact Name</Label>
              <Input
                value={newProfile.contactName}
                onChange={(e) => setNewProfile({ ...newProfile, contactName: e.target.value })}
                placeholder="John Smith"
                className="bg-white/5 border-[#f4d03f]/20 text-white"
              />
            </div>

            {/* Phone */}
            <div className="space-y-2">
              <Label className="text-white/80">Phone</Label>
              <Input
                value={newProfile.phone}
                onChange={(e) => setNewProfile({ ...newProfile, phone: e.target.value })}
                placeholder="(602) 555-1234"
                className="bg-white/5 border-[#f4d03f]/20 text-white"
              />
            </div>

            {/* Info about default password */}
            <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-yellow-400 text-sm font-medium">Default Password</p>
                  <p className="text-yellow-400/70 text-sm mt-1">
                    The user will be assigned the default password <code className="bg-yellow-500/20 px-1 rounded">B1GHat</code>. 
                    On their first login, they&apos;ll be required to:
                  </p>
                  <ul className="text-yellow-400/70 text-sm mt-2 list-disc list-inside">
                    <li>Create a new secure password</li>
                    <li>Verify their profile information</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setCreateDialogOpen(false)}
              className="text-white/60 hover:text-white"
            >
              Cancel
            </Button>
            <Button onClick={handleCreateProfile} disabled={loading || !newProfile.email} className="btn-gold">
              {loading ? 'Creating...' : 'Create Profile'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminSettings;
