import React, { useState } from 'react';
import { Eye, Trash2, CheckCircle, Clock, AlertCircle, Image } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog';
import { useData } from '../../../context/SponsorContext';

const AllAssets = () => {
  const { assets, pendingApprovals } = useData();
  const [filter, setFilter] = useState('all');
  const [selectedAsset, setSelectedAsset] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  
  const allAssets = [
    ...assets,
    ...pendingApprovals.map(a => ({ ...a, name: a.assetName, status: 'pending' }))
  ];

  const filteredAssets = filter === 'all' 
    ? allAssets 
    : allAssets.filter(a => a.status === filter);

  const getStatusBadge = (status) => {
    switch (status) {
      case 'approved':
        return <Badge className="status-approved"><CheckCircle size={12} className="mr-1" /> Approved</Badge>;
      case 'pending':
        return <Badge className="status-pending"><Clock size={12} className="mr-1" /> Pending</Badge>;
      case 'revision_requested':
        return <Badge className="status-revision"><AlertCircle size={12} className="mr-1" /> Revision</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const handlePreview = (asset) => {
    setSelectedAsset(asset);
    setPreviewOpen(true);
  };

  // Get the image source - prioritize fileData, then thumbnail
  const getImageSrc = (asset) => {
    return asset?.fileData || asset?.thumbnail || asset?.file_data || null;
  };

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">All Assets</h1>
          <p className="text-white/60 mt-1">View and manage all sponsor media</p>
        </div>
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="w-40 bg-white/5 border-[#f4d03f]/20 text-white">
            <SelectValue placeholder="Filter" />
          </SelectTrigger>
          <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
            <SelectItem value="all" className="text-white hover:bg-white/10">All Assets</SelectItem>
            <SelectItem value="approved" className="text-white hover:bg-white/10">Approved</SelectItem>
            <SelectItem value="pending" className="text-white hover:bg-white/10">Pending</SelectItem>
            <SelectItem value="revision_requested" className="text-white hover:bg-white/10">Revision</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredAssets.map((asset) => (
          <div key={asset.id} className="card-dark rounded-2xl overflow-hidden group">
            <div className="relative aspect-video bg-[#0f0f1a]">
              {getImageSrc(asset) ? (
                <img
                  src={getImageSrc(asset)}
                  alt={asset.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <Image className="w-12 h-12 text-white/20" />
                </div>
              )}
              <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  className="bg-white/20 hover:bg-white/30 text-white"
                  onClick={() => handlePreview(asset)}
                >
                  <Eye size={16} />
                </Button>
              </div>
            </div>
            <div className="p-4">
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-bold text-white truncate">{asset.name || asset.assetName}</h3>
                {getStatusBadge(asset.status)}
              </div>
              <p className="text-white/50 text-sm mb-1">{asset.campaignName}</p>
              <p className="text-white/40 text-xs">
                {asset.sponsorName || 'Unknown Sponsor'}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-white">{selectedAsset?.name || selectedAsset?.assetName}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {getImageSrc(selectedAsset) ? (
              <img
                src={getImageSrc(selectedAsset)}
                alt={selectedAsset?.name || selectedAsset?.assetName}
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
              <div>
                <p className="text-white/50">Sponsor</p>
                <p className="text-white">{selectedAsset?.sponsorName || 'Unknown'}</p>
              </div>
              <div>
                <p className="text-white/50">Status</p>
                {selectedAsset && getStatusBadge(selectedAsset.status)}
              </div>
              <div>
                <p className="text-white/50">Type / Format</p>
                <p className="text-white">{selectedAsset?.type || selectedAsset?.aspectRatio || 'Unknown'}</p>
              </div>
              <div>
                <p className="text-white/50">Uploaded</p>
                <p className="text-white">{selectedAsset?.uploadedAt || 'Unknown'}</p>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AllAssets;
