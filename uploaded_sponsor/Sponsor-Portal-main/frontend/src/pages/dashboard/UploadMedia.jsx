import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, FileImage, X, Check, AlertCircle, Info, Monitor, Square } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
import { Progress } from '../../components/ui/progress';
import { Badge } from '../../components/ui/badge';
import { toast } from 'sonner';
import { mediaRequirements } from '../../data/mock';
import { useData } from '../../context/DataContext';

const UploadMedia = () => {
  const navigate = useNavigate();
  const { uploadUserAsset, userAssets, getActiveSubscription } = useData();
  
  const activeSubscription = getActiveSubscription();
  
  // Check if user has Gold or Star Tier (for 16:9 access)
  const hasWideFormatAccess = activeSubscription && 
    ['gold', 'star-tier'].includes(activeSubscription.packageId);
  
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const [validationErrors, setValidationErrors] = useState([]);
  const [aspectRatio, setAspectRatio] = useState('1:1'); // Default to 1:1 since it's available to all
  
  // Count assets by aspect ratio
  const assets16x9 = userAssets.filter(a => a.aspectRatio === '16:9');
  const assets1x1 = userAssets.filter(a => a.aspectRatio === '1:1');
  
  const [formData, setFormData] = useState({
    campaignName: '',
    startDate: '',
    endDate: '',
    placement: '',
    notes: '',
  });

  const validateFile = (file) => {
    const errors = [];
    const maxSize = 5 * 1024 * 1024; // 5MB
    const allowedTypes = ['image/gif', 'image/png', 'image/jpeg', 'image/jpg'];

    if (!allowedTypes.includes(file.type)) {
      errors.push(`Invalid format. Allowed: ${mediaRequirements.formats.join(', ')}`);
    }
    if (file.size > maxSize) {
      errors.push(`File too large. Maximum: ${mediaRequirements.maxFileSize}`);
    }

    return errors;
  };

  const handleFile = useCallback((selectedFile) => {
    const errors = validateFile(selectedFile);
    setValidationErrors(errors);

    if (errors.length === 0) {
      setFile(selectedFile);
      const reader = new FileReader();
      reader.onload = (e) => setPreview(e.target.result);
      reader.readAsDataURL(selectedFile);
    }
  }, []);

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
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      toast.error('Please select a file to upload');
      return;
    }

    // Check limits
    if (aspectRatio === '16:9' && assets16x9.length >= 3) {
      toast.error('You already have 3 wide format (16:9) images. Delete one to upload more.');
      return;
    }
    if (aspectRatio === '1:1' && assets1x1.length >= 3) {
      toast.error('You already have 3 square format (1:1) images. Delete one to upload more.');
      return;
    }

    setUploading(true);
    
    // Simulate upload progress
    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval);
          return 100;
        }
        return prev + 10;
      });
    }, 200);

    // Simulate API call and save to context
    setTimeout(() => {
      clearInterval(interval);
      setUploadProgress(100);
      
      // Save the asset
      uploadUserAsset({
        name: file.name,
        type: file.type,
        aspectRatio: aspectRatio,
        thumbnail: preview,
        campaignName: formData.campaignName,
        startDate: formData.startDate,
        endDate: formData.endDate,
        placement: formData.placement,
        notes: formData.notes,
      });
      
      toast.success('Asset uploaded successfully! Pending review.');
      setTimeout(() => {
        navigate('/dashboard/assets');
      }, 1000);
    }, 2500);
  };

  const removeFile = () => {
    setFile(null);
    setPreview(null);
    setValidationErrors([]);
  };

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Upload Media</h1>
      <p className="text-white/60 mb-6">Submit your promotional assets for review</p>

      {/* Asset Limits Info */}
      <div className="card-dark rounded-xl p-4 mb-6">
        <div className="flex flex-col sm:flex-row gap-4 sm:gap-8">
          <div className={`flex items-center gap-3 ${!hasWideFormatAccess ? 'opacity-50' : ''}`}>
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              !hasWideFormatAccess ? 'bg-white/5' : assets16x9.length >= 3 ? 'bg-green-500/20' : 'bg-blue-500/10'
            }`}>
              <Monitor className={`w-5 h-5 ${
                !hasWideFormatAccess ? 'text-white/30' : assets16x9.length >= 3 ? 'text-green-400' : 'text-blue-400'
              }`} />
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
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              assets1x1.length >= 3 ? 'bg-green-500/20' : 'bg-purple-500/10'
            }`}>
              <Square className={`w-5 h-5 ${assets1x1.length >= 3 ? 'text-green-400' : 'text-purple-400'}`} />
            </div>
            <div>
              <p className="text-white font-medium">1:1 Square Format</p>
              <p className={`text-sm ${assets1x1.length >= 3 ? 'text-green-400' : 'text-white/50'}`}>
                {assets1x1.length}/3 uploaded
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Logo Note */}
      <div className="bg-[#f4d03f]/5 border border-[#f4d03f]/20 rounded-xl p-4 mb-8">
        <p className="text-[#f4d03f] text-sm">
          <strong>💡 Tip:</strong> Make one of your 1:1 square images your company logo — it will be displayed during trivia rounds across all sponsorship packages.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Aspect Ratio Selection */}
        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4">Select Format</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            {/* 16:9 Wide Format - Gold+ Only */}
            <button
              type="button"
              onClick={() => hasWideFormatAccess && setAspectRatio('16:9')}
              disabled={!hasWideFormatAccess || assets16x9.length >= 3}
              className={`p-4 rounded-xl border-2 text-left transition-all ${
                aspectRatio === '16:9' && hasWideFormatAccess
                  ? 'border-[#f4d03f] bg-[#f4d03f]/10'
                  : 'border-white/10'
              } ${!hasWideFormatAccess ? 'opacity-50 cursor-not-allowed' : assets16x9.length >= 3 ? 'opacity-50 cursor-not-allowed' : 'hover:border-white/20'}`}
            >
              <div className="flex items-center gap-3 mb-2">
                <Monitor className={`w-5 h-5 ${aspectRatio === '16:9' && hasWideFormatAccess ? 'text-[#f4d03f]' : 'text-white/50'}`} />
                <span className="text-white font-medium">Wide Format (16:9)</span>
                <Badge className="bg-[#f4d03f]/10 text-[#f4d03f] border-[#f4d03f]/20 text-xs ml-auto">
                  Gold+
                </Badge>
              </div>
              <p className="text-white/50 text-sm">For projectors & wide displays</p>
              <p className="text-white/40 text-xs mt-1">Recommended: 1920 x 1080</p>
              {!hasWideFormatAccess ? (
                <p className="text-orange-400 text-xs mt-2">Upgrade to Gold or Star Tier to unlock</p>
              ) : assets16x9.length >= 3 ? (
                <Badge className="mt-2 bg-green-500/20 text-green-400 border-green-500/30 text-xs">
                  Limit reached
                </Badge>
              ) : aspectRatio === '16:9' ? (
                <div className="flex items-center gap-1 mt-2 text-[#f4d03f] text-xs">
                  <Check size={14} /> Selected
                </div>
              ) : null}
            </button>

            {/* 1:1 Square Format - All Packages */}
            <button
              type="button"
              onClick={() => setAspectRatio('1:1')}
              disabled={assets1x1.length >= 3}
              className={`p-4 rounded-xl border-2 text-left transition-all ${
                aspectRatio === '1:1'
                  ? 'border-[#f4d03f] bg-[#f4d03f]/10'
                  : 'border-white/10 hover:border-white/20'
              } ${assets1x1.length >= 3 ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div className="flex items-center gap-3 mb-2">
                <Square className={`w-5 h-5 ${aspectRatio === '1:1' ? 'text-[#f4d03f]' : 'text-white/50'}`} />
                <span className="text-white font-medium">Square Format (1:1)</span>
                <Badge className="bg-green-500/10 text-green-400 border-green-500/20 text-xs ml-auto">
                  All Tiers
                </Badge>
              </div>
              <p className="text-white/50 text-sm">For logo & social media displays</p>
              <p className="text-white/40 text-xs mt-1">Recommended: 1080 x 1080</p>
              {assets1x1.length >= 3 ? (
                <Badge className="mt-2 bg-green-500/20 text-green-400 border-green-500/30 text-xs">
                  Limit reached
                </Badge>
              ) : aspectRatio === '1:1' ? (
                <div className="flex items-center gap-1 mt-2 text-[#f4d03f] text-xs">
                  <Check size={14} /> Selected
                </div>
              ) : null}
            </button>
          </div>
        </div>

        {/* Upload Zone */}
        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <FileImage className="text-[#f4d03f]" size={20} />
            Media File
          </h2>

          {!file ? (
            <div
              className={`upload-zone rounded-xl p-12 text-center cursor-pointer ${dragActive ? 'dragging' : ''}`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => document.getElementById('fileInput').click()}
            >
              <input
                id="fileInput"
                type="file"
                className="hidden"
                accept=".gif,.png,.jpg,.jpeg"
                onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
              />
              <Upload className="w-12 h-12 text-[#f4d03f]/60 mx-auto mb-4" />
              <p className="text-white font-medium mb-1">Drag and drop your file here</p>
              <p className="text-white/50 text-sm">or click to browse</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {mediaRequirements.formats.map((format) => (
                  <span key={format} className="px-2 py-1 bg-white/5 rounded text-white/40 text-xs">
                    {format}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Preview */}
              <div className="relative bg-[#0f0f1a] rounded-xl p-4">
                <button
                  type="button"
                  onClick={removeFile}
                  className="absolute top-2 right-2 w-8 h-8 bg-red-500/20 hover:bg-red-500/30 rounded-full flex items-center justify-center text-red-400"
                >
                  <X size={16} />
                </button>
                <div className="flex items-center gap-4">
                  <img
                    src={preview}
                    alt="Preview"
                    className="w-32 h-20 object-cover rounded-lg border border-[#f4d03f]/20"
                  />
                  <div>
                    <p className="text-white font-medium">{file.name}</p>
                    <p className="text-white/50 text-sm">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                    <div className="flex items-center gap-1 mt-1 text-green-400 text-sm">
                      <Check size={14} />
                      Valid format
                    </div>
                  </div>
                </div>
              </div>

              {/* Trivia Overlay Preview */}
              <div className="bg-[#0f0f1a] rounded-xl p-4">
                <p className="text-white/50 text-sm mb-3 flex items-center gap-2">
                  <Info size={14} />
                  {aspectRatio === '1:1' ? 'Preview: Your logo in the trivia overlay' : 'Preview: Your ad in the trivia overlay'}
                </p>
                
                {aspectRatio === '1:1' ? (
                  /* 1:1 Logo Preview - Using the trivia overlay template */
                  <div className="relative rounded-lg overflow-hidden border border-[#f4d03f]/20">
                    <img
                      src="https://customer-assets.emergentagent.com/job_fe389e90-8faf-4d17-8387-2fb24e4ce58c/artifacts/5ezxntnf_Live%20Stream%20Overlays%20%283%29.png"
                      alt="Trivia Overlay Template"
                      className="w-full"
                    />
                    {/* User's logo positioned in bottom-right slot - centered with rounded corners to match Canva frame */}
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
                        src={preview}
                        alt="Your logo"
                        className="w-full h-full object-cover"
                        style={{ borderRadius: '16%' }}
                      />
                    </div>
                  </div>
                ) : (
                  /* 16:9 Wide Format Preview - Full screen preview */
                  <div className="relative rounded-lg overflow-hidden border border-[#f4d03f]/20">
                    <img
                      src={preview}
                      alt="16:9 Preview"
                      className="w-full aspect-video object-cover"
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Validation Errors */}
          {validationErrors.length > 0 && (
            <div className="mt-4 p-4 bg-red-500/10 rounded-xl border border-red-500/20">
              {validationErrors.map((error, index) => (
                <p key={index} className="text-red-400 text-sm flex items-center gap-2">
                  <AlertCircle size={14} />
                  {error}
                </p>
              ))}
            </div>
          )}
        </div>

        {/* Campaign Details */}
        <div className="card-dark rounded-2xl p-6">
          <h2 className="text-lg font-bold text-white mb-4">Campaign Details</h2>
          
          <div className="space-y-4">
            <div>
              <Label className="text-white/80">Campaign Name *</Label>
              <Input
                value={formData.campaignName}
                onChange={(e) => setFormData({ ...formData, campaignName: e.target.value })}
                placeholder="e.g., Summer Promotion 2025"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                required
              />
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80">Desired Start Date</Label>
                <Input
                  type="date"
                  value={formData.startDate}
                  onChange={(e) => setFormData({ ...formData, startDate: e.target.value })}
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>
              <div>
                <Label className="text-white/80">Desired End Date</Label>
                <Input
                  type="date"
                  value={formData.endDate}
                  onChange={(e) => setFormData({ ...formData, endDate: e.target.value })}
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white"
                />
              </div>
            </div>

            <div>
              <Label className="text-white/80">Placement Preference</Label>
              <Select
                value={formData.placement}
                onValueChange={(value) => setFormData({ ...formData, placement: value })}
              >
                <SelectTrigger className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white">
                  <SelectValue placeholder="Select preference" />
                </SelectTrigger>
                <SelectContent className="bg-[#1a1a2e] border-[#f4d03f]/20">
                  <SelectItem value="any" className="text-white hover:bg-white/10">Any Available</SelectItem>
                  <SelectItem value="pre-round" className="text-white hover:bg-white/10">Pre-Round</SelectItem>
                  <SelectItem value="mid-round" className="text-white hover:bg-white/10">Mid-Round Overlay</SelectItem>
                  <SelectItem value="answer" className="text-white hover:bg-white/10">Answer Reveal</SelectItem>
                  <SelectItem value="closing" className="text-white hover:bg-white/10">Closing Credits</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label className="text-white/80">Notes for BIG Hat Team</Label>
              <Textarea
                value={formData.notes}
                onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                placeholder="Any special instructions or requests..."
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30 min-h-[100px]"
              />
            </div>
          </div>
        </div>

        {/* Upload Progress */}
        {uploading && (
          <div className="card-dark rounded-2xl p-6">
            <p className="text-white mb-3">Uploading...</p>
            <Progress value={uploadProgress} className="h-2" />
            <p className="text-white/50 text-sm mt-2">{uploadProgress}%</p>
          </div>
        )}

        {/* Submit Button */}
        <Button
          type="submit"
          disabled={!file || validationErrors.length > 0 || uploading}
          className="w-full btn-gold h-12"
        >
          {uploading ? 'Uploading...' : 'Submit for Review'}
        </Button>
      </form>
    </div>
  );
};

export default UploadMedia;