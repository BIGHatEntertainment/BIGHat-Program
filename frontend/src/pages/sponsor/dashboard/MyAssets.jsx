import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, Trash2, Clock, CheckCircle, AlertCircle, RefreshCw, Image, Upload, Star, StarOff } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
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
import { toast } from 'sonner';
import { useData } from '../../../context/SponsorContext';
import { assetsApi } from '../../../services/sponsorApi';

const MyAssets = () => {
  const navigate = useNavigate();
  const { userAssets, deleteAsset, getActiveSubscription, userProfile, refetch } = useData();
  const [selectedAsset, setSelectedAsset] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [settingPreferred, setSettingPreferred] = useState(null);

  const activeSubscription = getActiveSubscription();

  // Count assets by aspect ratio (check both 'type' and 'aspectRatio' fields)
  const assets16x9 = userAssets.filter(a => a.type === '16:9' || a.aspectRatio === '16:9');
  const assets1x1 = userAssets.filter(a => a.type === '1:1' || a.aspectRatio === '1:1');
  
  // Get preferred assets
  const preferred16x9 = userAssets.find(a => (a.type === '16:9' || a.aspectRatio === '16:9') && a.isPreferred);
  const preferred1x1 = userAssets.find(a => (a.type === '1:1' || a.aspectRatio === '1:1') && a.isPreferred);

  // Check if user has Gold or Star Tier (for 16:9 access)
  const hasWideFormatAccess = activeSubscription && 
    ['gold', 'star-tier'].includes(activeSubscription.packageId);

  const getStatusBadge = (status) => {
    switch (status) {
      case 'approved':
        return <Badge className="status-approved"><CheckCircle size={12} className="mr-1" /> Approved</Badge>;
      case 'pending':
        return <Badge className="status-pending"><Clock size={12} className="mr-1" /> Under Review</Badge>;
      case 'revision_requested':
        return <Badge className="status-revision"><AlertCircle size={12} className="mr-1" /> Revision Requested</Badge>;
      case 'rejected':
        return <Badge className="bg-red-500/20 text-red-400 border-red-500/30"><AlertCircle size={12} className="mr-1" /> Rejected</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const handleDelete = async (assetId) => {
    try {
      await deleteAsset(assetId);
      toast.success('Asset deleted successfully');
    } catch (err) {
      console.error('Failed to delete asset:', err);
      toast.error('Failed to delete asset');
    }
  };

  const handlePreview = (asset) => {
    setSelectedAsset(asset);
    setPreviewOpen(true);
  };

  const handleSetPreferred = async (asset) => {
    setSettingPreferred(asset.id);
    try {
      if (asset.isPreferred) {
        // Unset preferred
        await assetsApi.unsetPreferred(asset.id);
        toast.success(`Removed preferred status from "${asset.name}"`);
      } else {
        // Set as preferred
        await assetsApi.setPreferred(asset.id);
        const assetType = asset.type || asset.aspectRatio;
        toast.success(`"${asset.name}" is now your preferred ${assetType} image`);
      }
      // Refresh data to get updated preferred status
      await refetch();
    } catch (err) {
      console.error('Failed to update preferred status:', err);
      toast.error('Failed to update preferred status');
    } finally {
      setSettingPreferred(null);
    }
  };

  const getAssetType = (asset) => asset.type || asset.aspectRatio || 'Unknown';

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">My Assets</h1>
          <p className="text-white/60 mt-1">Manage your uploaded media files</p>
        </div>
        <Button onClick={() => navigate('/dashboard/upload')} className="btn-gold">
          <Upload size={16} className="mr-2" />
          Upload New Asset
        </Button>
      </div>

      {/* Asset Limits Info */}
      <div className="card-dark rounded-xl p-4 mb-6">
        <div className="flex flex-col sm:flex-row gap-4 sm:gap-8">
          <div className={`flex items-center gap-3 ${!hasWideFormatAccess ? 'opacity-50' : ''}`}>
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              hasWideFormatAccess ? 'bg-blue-500/10' : 'bg-white/5'
            }`}>
              <Image className={`w-5 h-5 ${hasWideFormatAccess ? 'text-blue-400' : 'text-white/30'}`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="text-white font-medium">16:9 Wide Format</p>
                {!hasWideFormatAccess && (
                  <Badge className="bg-[#f4d03f]/10 text-[#f4d03f] border-[#f4d03f]/20 text-xs">
                    Gold+
                  </Badge>
                )}
              </div>
              <p className={`text-sm ${assets16x9.length >= 3 ? 'text-green-400' : 'text-white/50'}`}>
                {hasWideFormatAccess ? `${assets16x9.length}/3 uploaded` : 'Requires Gold or Star Tier'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
              <Image className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p className="text-white font-medium">1:1 Square Format</p>
              <p className={`text-sm ${assets1x1.length >= 3 ? 'text-green-400' : 'text-white/50'}`}>
                {assets1x1.length}/3 uploaded
              </p>
            </div>
          </div>
          {!activeSubscription && (
            <div className="sm:ml-auto flex items-center">
              <Badge className="bg-orange-500/20 text-orange-400 border-orange-500/30">
                Upload now, activate later
              </Badge>
            </div>
          )}
        </div>
      </div>

      {/* Preferred Assets Summary */}
      <div className="bg-[#f4d03f]/5 border border-[#f4d03f]/20 rounded-xl p-4 mb-6">
        <h3 className="text-[#f4d03f] font-semibold text-sm mb-3 flex items-center gap-2">
          <Star size={16} className="fill-[#f4d03f]" /> Preferred Images for Admin
        </h3>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              preferred16x9 ? 'bg-[#f4d03f]/20' : 'bg-white/5'
            }`}>
              {preferred16x9 ? (
                <Star size={14} className="text-[#f4d03f] fill-[#f4d03f]" />
              ) : (
                <StarOff size={14} className="text-white/30" />
              )}
            </div>
            <div>
              <p className="text-white text-sm font-medium">16:9 Wide Format</p>
              <p className="text-white/50 text-xs">
                {preferred16x9 ? preferred16x9.name : 'No preference set'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              preferred1x1 ? 'bg-[#f4d03f]/20' : 'bg-white/5'
            }`}>
              {preferred1x1 ? (
                <Star size={14} className="text-[#f4d03f] fill-[#f4d03f]" />
              ) : (
                <StarOff size={14} className="text-white/30" />
              )}
            </div>
            <div>
              <p className="text-white text-sm font-medium">1:1 Square Format</p>
              <p className="text-white/50 text-xs">
                {preferred1x1 ? preferred1x1.name : 'No preference set'}
              </p>
            </div>
          </div>
        </div>
        <p className="text-white/40 text-xs mt-3">
          Click the star icon on any asset to set it as your preferred image for that format. This helps admins know which images to use.
        </p>
      </div>

      {/* Logo Note */}
      <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-4 mb-8">
        <p className="text-blue-400 text-sm">
          <strong>💡 Tip:</strong> Make one of your 1:1 square images your company logo — it will be displayed during trivia rounds across all sponsorship packages.
        </p>
      </div>

      {/* Asset Grid */}
      {userAssets.length === 0 ? (
        <div className="card-dark rounded-2xl p-12 text-center">
          <Image className="w-12 h-12 text-white/20 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">No Assets Yet</h2>
          <p className="text-white/60 mb-4">Upload your first promotional asset to get started.</p>
          <Button onClick={() => navigate('/dashboard/upload')} className="btn-gold">
            Upload Your First Asset
          </Button>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {userAssets.map((asset) => (
            <div key={asset.id} className={`card-dark rounded-2xl overflow-hidden group relative ${
              asset.isPreferred ? 'ring-2 ring-[#f4d03f]/50' : ''
            }`}>
              {/* Preferred Badge */}
              {asset.isPreferred && (
                <div className="absolute top-2 left-2 z-10">
                  <Badge className="bg-[#f4d03f] text-black text-xs font-semibold">
                    <Star size={10} className="mr-1 fill-black" /> Preferred
                  </Badge>
                </div>
              )}
              
              {/* Format Badge */}
              <div className="absolute top-2 right-2 z-10">
                <Badge className={`text-xs ${
                  getAssetType(asset) === '16:9' 
                    ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' 
                    : 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                }`}>
                  {getAssetType(asset)}
                </Badge>
              </div>
              
              {/* Thumbnail */}
              <div className="relative aspect-video bg-[#0f0f1a]">
                {asset.thumbnail ? (
                  <img
                    src={asset.thumbnail}
                    alt={asset.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center">
                    <Image className="w-12 h-12 text-white/20" />
                  </div>
                )}
                {/* Overlay Actions */}
                <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handleSetPreferred(asset)}
                    disabled={settingPreferred === asset.id}
                    className={`${
                      asset.isPreferred 
                        ? 'bg-[#f4d03f]/30 hover:bg-[#f4d03f]/40 text-[#f4d03f]' 
                        : 'bg-white/20 hover:bg-white/30 text-white'
                    }`}
                    title={asset.isPreferred ? 'Remove preferred status' : 'Set as preferred'}
                  >
                    {asset.isPreferred ? <Star size={16} className="fill-[#f4d03f]" /> : <Star size={16} />}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handlePreview(asset)}
                    className="bg-white/20 hover:bg-white/30 text-white"
                  >
                    <Eye size={16} />
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        size="sm"
                        variant="secondary"
                        className="bg-red-500/20 hover:bg-red-500/30 text-red-400"
                      >
                        <Trash2 size={16} />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                      <AlertDialogHeader>
                        <AlertDialogTitle className="text-white">Delete Asset</AlertDialogTitle>
                        <AlertDialogDescription className="text-white/60">
                          Are you sure you want to delete &quot;{asset.name}&quot;? This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel className="bg-white/10 text-white border-0 hover:bg-white/20">
                          Cancel
                        </AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => handleDelete(asset.id)}
                          className="bg-red-500 hover:bg-red-600 text-white"
                        >
                          Delete
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>

              {/* Info */}
              <div className="p-4">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-bold text-white truncate">{asset.name}</h3>
                  {getStatusBadge(asset.status)}
                </div>
                {asset.campaignName && (
                  <p className="text-white/50 text-sm mb-1">{asset.campaignName}</p>
                )}
                <p className="text-white/40 text-xs">
                  Uploaded: {asset.uploadedAt}
                </p>

                {/* Revision Notes */}
                {asset.status === 'revision_requested' && asset.notes && (
                  <div className="mt-3 p-3 bg-orange-500/10 rounded-lg border border-orange-500/20">
                    <p className="text-orange-400 text-xs font-medium mb-1">Revision Notes:</p>
                    <p className="text-white/70 text-xs">{asset.notes}</p>
                    <Button 
                      size="sm" 
                      className="mt-2 w-full btn-outline-gold text-xs h-8"
                      onClick={() => navigate('/dashboard/upload')}
                    >
                      <RefreshCw size={12} className="mr-1" />
                      Upload Revised Version
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-white">{selectedAsset?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {(selectedAsset?.fileData || selectedAsset?.thumbnail || selectedAsset?.file_data) ? (
              <img
                src={selectedAsset.fileData || selectedAsset.thumbnail || selectedAsset.file_data}
                alt={selectedAsset.name}
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
            <div className="grid grid-cols-2 gap-4 text-sm">
              {selectedAsset?.campaignName && (
                <div>
                  <p className="text-white/50">Campaign</p>
                  <p className="text-white">{selectedAsset.campaignName}</p>
                </div>
              )}
              <div>
                <p className="text-white/50">Status</p>
                {selectedAsset && getStatusBadge(selectedAsset.status)}
              </div>
              <div>
                <p className="text-white/50">Uploaded</p>
                <p className="text-white">{selectedAsset?.uploadedAt}</p>
              </div>
              {selectedAsset?.type && (
                <div>
                  <p className="text-white/50">Type</p>
                  <p className="text-white">{selectedAsset.type}</p>
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MyAssets;
