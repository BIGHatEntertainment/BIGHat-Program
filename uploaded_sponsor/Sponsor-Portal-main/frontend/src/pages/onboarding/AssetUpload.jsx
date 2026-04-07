import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Upload, X, Image, Monitor, Square, Info, CheckCircle } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { toast } from 'sonner';
import { useData } from '../../context/DataContext';

const AssetUpload = () => {
  const navigate = useNavigate();
  const { uploadUserAsset } = useData();
  const fileInputRef = useRef(null);
  
  const [assets16x9, setAssets16x9] = useState([]);
  const [assets1x1, setAssets1x1] = useState([]);
  const [dragOver, setDragOver] = useState(null);

  const MAX_ASSETS_PER_TYPE = 3;

  const handleFileSelect = async (e, aspectRatio) => {
    const files = Array.from(e.target.files || []);
    await processFiles(files, aspectRatio);
  };

  const handleDrop = async (e, aspectRatio) => {
    e.preventDefault();
    setDragOver(null);
    const files = Array.from(e.dataTransfer.files);
    await processFiles(files, aspectRatio);
  };

  const processFiles = async (files, aspectRatio) => {
    const currentAssets = aspectRatio === '16:9' ? assets16x9 : assets1x1;
    const setAssets = aspectRatio === '16:9' ? setAssets16x9 : setAssets1x1;
    
    if (currentAssets.length >= MAX_ASSETS_PER_TYPE) {
      toast.error(`Maximum ${MAX_ASSETS_PER_TYPE} ${aspectRatio} images allowed`);
      return;
    }

    const remainingSlots = MAX_ASSETS_PER_TYPE - currentAssets.length;
    const filesToProcess = files.slice(0, remainingSlots);

    for (const file of filesToProcess) {
      if (!file.type.startsWith('image/')) {
        toast.error(`${file.name} is not an image file`);
        continue;
      }

      if (file.size > 5 * 1024 * 1024) {
        toast.error(`${file.name} exceeds 5MB limit`);
        continue;
      }

      // Create preview URL
      const reader = new FileReader();
      reader.onload = (e) => {
        const newAsset = {
          id: `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          name: file.name,
          type: file.type,
          aspectRatio,
          thumbnail: e.target.result,
          file: file,
        };
        setAssets(prev => [...prev, newAsset]);
      };
      reader.readAsDataURL(file);
    }
  };

  const removeAsset = (id, aspectRatio) => {
    if (aspectRatio === '16:9') {
      setAssets16x9(prev => prev.filter(a => a.id !== id));
    } else {
      setAssets1x1(prev => prev.filter(a => a.id !== id));
    }
  };

  const handleContinue = () => {
    // Save assets to context
    [...assets16x9, ...assets1x1].forEach(asset => {
      uploadUserAsset({
        name: asset.name,
        type: asset.type,
        aspectRatio: asset.aspectRatio,
        thumbnail: asset.thumbnail,
      });
    });

    navigate('/onboarding/packages');
  };

  const handleSkip = () => {
    navigate('/onboarding/packages');
  };

  const UploadZone = ({ aspectRatio, assets, setAssets, icon: Icon, label, dimensions }) => (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-[#f4d03f]/10 flex items-center justify-center">
          <Icon className="w-5 h-5 text-[#f4d03f]" />
        </div>
        <div>
          <h3 className="text-white font-bold">{label}</h3>
          <p className="text-white/50 text-sm">{dimensions} • Up to {MAX_ASSETS_PER_TYPE} images</p>
        </div>
        <div className="ml-auto">
          <span className={`text-sm font-medium ${
            assets.length >= MAX_ASSETS_PER_TYPE ? 'text-green-400' : 'text-white/50'
          }`}>
            {assets.length}/{MAX_ASSETS_PER_TYPE}
          </span>
        </div>
      </div>

      {/* Drop Zone */}
      <div
        className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors ${
          dragOver === aspectRatio
            ? 'border-[#f4d03f] bg-[#f4d03f]/10'
            : 'border-[#f4d03f]/20 hover:border-[#f4d03f]/40'
        } ${assets.length >= MAX_ASSETS_PER_TYPE ? 'opacity-50 pointer-events-none' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(aspectRatio); }}
        onDragLeave={() => setDragOver(null)}
        onDrop={(e) => handleDrop(e, aspectRatio)}
      >
        <input
          type="file"
          ref={fileInputRef}
          onChange={(e) => handleFileSelect(e, aspectRatio)}
          accept="image/*"
          multiple
          className="hidden"
          id={`upload-${aspectRatio}`}
        />
        <label
          htmlFor={`upload-${aspectRatio}`}
          className="cursor-pointer"
        >
          <Upload className="w-8 h-8 text-[#f4d03f]/50 mx-auto mb-2" />
          <p className="text-white/60 text-sm">
            Drag & drop or <span className="text-[#f4d03f]">browse</span>
          </p>
          <p className="text-white/40 text-xs mt-1">PNG, JPG, GIF up to 5MB</p>
        </label>
      </div>

      {/* Preview Grid */}
      {assets.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {assets.map((asset) => (
            <div key={asset.id} className="relative group">
              <div className={`rounded-lg overflow-hidden bg-[#0f0f1a] ${
                aspectRatio === '16:9' ? 'aspect-video' : 'aspect-square'
              }`}>
                <img
                  src={asset.thumbnail}
                  alt={asset.name}
                  className="w-full h-full object-cover"
                />
              </div>
              <button
                onClick={() => removeAsset(asset.id, aspectRatio)}
                className="absolute -top-2 -right-2 w-6 h-6 rounded-full bg-red-500 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <X size={14} />
              </button>
              <p className="text-white/50 text-xs truncate mt-1">{asset.name}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-8">
      <div className="text-center">
        <h1 className="text-2xl sm:text-3xl font-bold text-white">Upload Your Assets</h1>
        <p className="text-white/60 mt-2">
          Add your promotional images. Only one of each size will be displayed at a time.
        </p>
      </div>

      {/* Info Box */}
      <div className="card-dark rounded-xl p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-[#f4d03f] flex-shrink-0 mt-0.5" />
        <div className="text-sm text-white/60">
          <p className="text-white font-medium mb-1">Image Requirements</p>
          <ul className="space-y-1">
            <li>• <strong>16:9 images</strong> are used for wide displays and projector screens</li>
            <li>• <strong>1:1 images</strong> are used for social media and square displays</li>
            <li>• Upload up to 3 of each - we'll rotate them throughout your sponsorship</li>
            <li>• You can always add more images later from your dashboard</li>
          </ul>
        </div>
      </div>

      {/* Upload Zones */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="card-dark rounded-2xl p-6">
          <UploadZone
            aspectRatio="16:9"
            assets={assets16x9}
            setAssets={setAssets16x9}
            icon={Monitor}
            label="Wide Format (16:9)"
            dimensions="1920 x 1080 recommended"
          />
        </div>

        <div className="card-dark rounded-2xl p-6">
          <UploadZone
            aspectRatio="1:1"
            assets={assets1x1}
            setAssets={setAssets1x1}
            icon={Square}
            label="Square Format (1:1)"
            dimensions="1080 x 1080 recommended"
          />
        </div>
      </div>

      {/* Summary */}
      {(assets16x9.length > 0 || assets1x1.length > 0) && (
        <div className="card-dark rounded-xl p-4 flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-green-400" />
          <p className="text-white">
            <span className="font-bold">{assets16x9.length + assets1x1.length}</span> image(s) ready to upload
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-4">
        <Button
          variant="ghost"
          onClick={handleSkip}
          className="text-white/60 hover:text-white hover:bg-white/10"
        >
          Skip for now
        </Button>
        <Button
          onClick={handleContinue}
          className="flex-1 btn-gold h-12"
        >
          {assets16x9.length > 0 || assets1x1.length > 0 ? 'Continue with Assets' : 'Continue without Assets'}
          <ArrowRight className="ml-2" size={18} />
        </Button>
      </div>
    </div>
  );
};

export default AssetUpload;
