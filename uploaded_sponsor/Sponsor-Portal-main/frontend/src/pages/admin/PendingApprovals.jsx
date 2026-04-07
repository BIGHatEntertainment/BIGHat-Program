import React, { useState } from 'react';
import { Check, X, Eye, MessageSquare, Star } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { Textarea } from '../../components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../../components/ui/dialog';
import { toast } from 'sonner';
import { useData } from '../../context/DataContext';

const PendingApprovals = () => {
  const { pendingApprovals, approveAsset, rejectAsset, requestRevision } = useData();
  const [selectedAsset, setSelectedAsset] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [revisionNotes, setRevisionNotes] = useState('');

  const handleApprove = (assetId) => {
    approveAsset(assetId);
    toast.success('Asset approved and scheduled!');
  };

  const handleRequestRevision = () => {
    if (!revisionNotes.trim()) {
      toast.error('Please provide revision notes');
      return;
    }
    requestRevision(selectedAsset.id, revisionNotes);
    toast.success('Revision request sent to sponsor');
    setRevisionOpen(false);
    setRevisionNotes('');
  };

  const handleReject = (assetId) => {
    rejectAsset(assetId);
    toast.success('Asset rejected');
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Pending Approvals</h1>
        <p className="text-white/60 mt-1">Review and approve sponsor media assets</p>
      </div>

      {pendingApprovals.length === 0 ? (
        <div className="card-dark rounded-2xl p-12 text-center">
          <Check className="w-16 h-16 text-green-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-white mb-2">All Caught Up!</h2>
          <p className="text-white/60">No pending approvals at this time.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {pendingApprovals.map((asset) => (
            <div key={asset.id} className="card-dark rounded-2xl overflow-hidden">
              <div className="flex flex-col lg:flex-row">
                {/* Thumbnail */}
                <div className="lg:w-80 flex-shrink-0">
                  <img
                    src={asset.thumbnail}
                    alt={asset.assetName}
                    className="w-full h-48 lg:h-full object-cover"
                  />
                </div>

                {/* Details */}
                <div className="flex-1 p-6">
                  <div className="flex flex-col sm:flex-row justify-between items-start gap-4 mb-4">
                    <div>
                      <h3 className="text-xl font-bold text-white">{asset.assetName}</h3>
                      <p className="text-white/60 text-sm mt-1">
                        by {asset.sponsorName} • {asset.package}
                      </p>
                    </div>
                    <Badge className="bg-orange-500/20 text-orange-400 border-orange-500/30">
                      Pending Review
                    </Badge>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4 mb-6 text-sm">
                    <div>
                      <p className="text-white/50">Campaign</p>
                      <p className="text-white">{asset.campaignName || 'N/A'}</p>
                    </div>
                    <div>
                      <p className="text-white/50">Format</p>
                      <div className="flex items-center gap-2">
                        <p className="text-white">{asset.type}</p>
                        {asset.isPreferred && (
                          <Badge className="bg-[#f4d03f]/20 text-[#f4d03f] text-xs">
                            <Star size={10} className="mr-1 fill-[#f4d03f]" /> Preferred
                          </Badge>
                        )}
                      </div>
                    </div>
                    <div>
                      <p className="text-white/50">Date Range</p>
                      <p className="text-white">{asset.startDate && asset.endDate ? `${asset.startDate} - ${asset.endDate}` : 'N/A'}</p>
                    </div>
                    <div>
                      <p className="text-white/50">Uploaded</p>
                      <p className="text-white">{asset.uploadedAt}</p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-wrap gap-3">
                    <Button
                      onClick={() => {
                        setSelectedAsset(asset);
                        setPreviewOpen(true);
                      }}
                      variant="outline"
                      className="btn-outline-gold"
                    >
                      <Eye size={16} className="mr-2" />
                      Preview
                    </Button>
                    <Button
                      onClick={() => handleApprove(asset.id)}
                      className="bg-green-500 hover:bg-green-600 text-white"
                    >
                      <Check size={16} className="mr-2" />
                      Approve
                    </Button>
                    <Button
                      onClick={() => {
                        setSelectedAsset(asset);
                        setRevisionOpen(true);
                      }}
                      variant="outline"
                      className="border-orange-500/30 text-orange-400 hover:bg-orange-500/10"
                    >
                      <MessageSquare size={16} className="mr-2" />
                      Request Revision
                    </Button>
                    <Button
                      onClick={() => handleReject(asset.id)}
                      variant="outline"
                      className="border-red-500/30 text-red-400 hover:bg-red-500/10"
                    >
                      <X size={16} className="mr-2" />
                      Reject
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-white">Asset Preview</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {/* Full Preview */}
            <div className="bg-[#0f0f1a] rounded-xl p-4">
              <p className="text-white/50 text-sm mb-3">Uploaded Image</p>
              <img
                src={selectedAsset?.thumbnail}
                alt={selectedAsset?.assetName}
                className="w-full max-h-[40vh] object-contain rounded-lg"
              />
            </div>
            
            {/* In-Show Preview - Different for 16:9 vs 1:1 */}
            <div className="bg-[#0f0f1a] rounded-xl p-4">
              <p className="text-white/50 text-sm mb-3">
                {selectedAsset?.aspectRatio === '1:1' || selectedAsset?.type === '1:1'
                  ? 'In-Show Preview (Logo Placement)'
                  : 'Full Screen Preview (16:9 Display)'}
              </p>
              {selectedAsset?.aspectRatio === '1:1' || selectedAsset?.type === '1:1' ? (
                /* 1:1 Logo Preview - Using trivia overlay template */
                <div className="relative rounded-lg overflow-hidden border border-[#f4d03f]/20">
                  <img
                    src="https://customer-assets.emergentagent.com/job_fe389e90-8faf-4d17-8387-2fb24e4ce58c/artifacts/5ezxntnf_Live%20Stream%20Overlays%20%283%29.png"
                    alt="Trivia Overlay Template"
                    className="w-full"
                  />
                  <div 
                    className="absolute"
                    style={{
                      bottom: '5.5%',
                      right: '4%',
                      width: '13.5%',
                      aspectRatio: '1/1',
                    }}
                  >
                    <img
                      src={selectedAsset?.thumbnail}
                      alt="Logo preview"
                      className="w-full h-full object-cover"
                      style={{ borderRadius: '16%' }}
                    />
                  </div>
                </div>
              ) : (
                /* 16:9 Wide Format Preview - Full screen display */
                <div className="relative rounded-lg overflow-hidden border border-[#f4d03f]/20">
                  <img
                    src={selectedAsset?.thumbnail}
                    alt="16:9 Full Preview"
                    className="w-full aspect-video object-cover"
                  />
                </div>
              )}
            </div>

            {/* Asset Details */}
            <div className="grid grid-cols-2 gap-4 text-sm bg-white/5 rounded-xl p-4">
              <div>
                <p className="text-white/50">Sponsor</p>
                <p className="text-white">{selectedAsset?.sponsorName}</p>
              </div>
              <div>
                <p className="text-white/50">Package</p>
                <p className="text-white">{selectedAsset?.package}</p>
              </div>
              <div>
                <p className="text-white/50">Format</p>
                <p className="text-white">{selectedAsset?.aspectRatio || '16:9'}</p>
              </div>
              <div>
                <p className="text-white/50">Uploaded</p>
                <p className="text-white">{selectedAsset?.uploadedAt}</p>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Revision Request Dialog */}
      <Dialog open={revisionOpen} onOpenChange={setRevisionOpen}>
        <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
          <DialogHeader>
            <DialogTitle className="text-white">Request Revision</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-white/60 text-sm">
              Provide feedback for {selectedAsset?.sponsorName} about their asset.
            </p>
            <Textarea
              value={revisionNotes}
              onChange={(e) => setRevisionNotes(e.target.value)}
              placeholder="Please describe what changes are needed..."
              className="bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30 min-h-[120px]"
            />
          </div>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setRevisionOpen(false)}
              className="text-white"
            >
              Cancel
            </Button>
            <Button
              onClick={handleRequestRevision}
              className="bg-orange-500 hover:bg-orange-600 text-white"
            >
              Send Revision Request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PendingApprovals;