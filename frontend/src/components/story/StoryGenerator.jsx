import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Loader2, Download, Upload, Play, Image as ImageIcon, Video, AlertCircle, CheckCircle2, Trash2, RefreshCw, X } from 'lucide-react';
import { toast } from '../../utils/toastCompat';
import { storyGeneratorAPI } from '../../services/triviaApi';

// Round type colors
const ROUND_COLORS = {
  'MC': 'bg-green-500',
  'REG': 'bg-red-500',
  'MISC': 'bg-blue-500',
  'MYS': 'bg-purple-500',
  'BIG': 'bg-yellow-500'
};

const ROUND_NAMES = {
  'MC': 'Multiple Choice',
  'REG': 'General',
  'MISC': 'Specific',
  'MYS': 'Mystery',
  'BIG': 'BIG Question'
};

const StoryGenerator = ({ open, onClose, userName }) => {
  const [activeTab, setActiveTab] = useState('generate');
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  
  // Presentation selection
  const [presentations, setPresentations] = useState([]);
  const [selectedPresentationId, setSelectedPresentationId] = useState('');
  const [selectedPresentation, setSelectedPresentation] = useState(null);
  const [preview, setPreview] = useState(null);
  
  // Assets management
  const [assets, setAssets] = useState({ locations: [], hosts: [], backgrounds: [], sharepoint_enabled: false });
  const [uploadingAsset, setUploadingAsset] = useState(false);
  const [refreshingAssets, setRefreshingAssets] = useState(false);
  
  // Generated video
  const [generatedVideo, setGeneratedVideo] = useState(null);

  useEffect(() => {
    if (open) {
      loadPresentations();
      loadAssets();
    }
  }, [open, userName]);

  const loadPresentations = async () => {
    try {
      setLoading(true);
      const data = await storyGeneratorAPI.getPresentations(userName);
      setPresentations(data);
    } catch (error) {
      console.error('Error loading presentations:', error);
      toast({ title: 'Error', description: 'Failed to load presentations', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const loadAssets = async (refresh = false) => {
    try {
      if (refresh) {
        setRefreshingAssets(true);
      }
      const data = await storyGeneratorAPI.getAssets(refresh);
      setAssets(data);
      if (refresh) {
        toast({ title: 'Refreshed', description: 'Asset list updated from SharePoint' });
      }
    } catch (error) {
      console.error('Error loading assets:', error);
    } finally {
      setRefreshingAssets(false);
    }
  };

  const handleRefreshAssets = async () => {
    try {
      setRefreshingAssets(true);
      const result = await storyGeneratorAPI.refreshAssets();
      if (result.success) {
        toast({ 
          title: 'Assets Refreshed', 
          description: `Loaded ${result.counts.locations} locations, ${result.counts.hosts} hosts, ${result.counts.backgrounds} backgrounds`
        });
        await loadAssets();
      }
    } catch (error) {
      console.error('Error refreshing assets:', error);
      toast({ title: 'Error', description: 'Failed to refresh assets', variant: 'destructive' });
    } finally {
      setRefreshingAssets(false);
    }
  };

  const handlePresentationSelect = async (presentationId) => {
    setSelectedPresentationId(presentationId);
    setGeneratedVideo(null);
    
    if (!presentationId) {
      setSelectedPresentation(null);
      setPreview(null);
      return;
    }

    try {
      setLoading(true);
      
      // Load presentation details and preview simultaneously
      const [details, previewData] = await Promise.all([
        storyGeneratorAPI.getPresentation(presentationId),
        storyGeneratorAPI.generatePreview(presentationId)
      ]);
      
      setSelectedPresentation(details);
      setPreview(previewData.preview);
    } catch (error) {
      console.error('Error loading presentation details:', error);
      toast({ title: 'Error', description: 'Failed to load presentation details', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateVideo = async () => {
    if (!selectedPresentationId) {
      toast({ title: 'Error', description: 'Please select a presentation first', variant: 'destructive' });
      return;
    }

    try {
      setGenerating(true);
      toast({ title: 'Generating...', description: 'Creating your Instagram story video. This may take a minute.' });
      
      const result = await storyGeneratorAPI.generateVideo(selectedPresentationId);
      
      if (result.success) {
        setGeneratedVideo({
          filename: result.filename,
          downloadUrl: storyGeneratorAPI.getDownloadUrl(result.filename)
        });
        toast({ title: 'Success!', description: 'Video generated successfully. Click download to save.' });
      }
    } catch (error) {
      console.error('Error generating video:', error);
      toast({ 
        title: 'Error', 
        description: error.response?.data?.detail || 'Failed to generate video', 
        variant: 'destructive' 
      });
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = () => {
    if (generatedVideo?.downloadUrl) {
      window.open(generatedVideo.downloadUrl, '_blank');
    }
  };

  const handleUploadAsset = async (event, assetType) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setUploadingAsset(true);
      await storyGeneratorAPI.uploadAsset(file, assetType);
      toast({ title: 'Success', description: `${assetType} asset uploaded successfully` });
      await loadAssets();
    } catch (error) {
      console.error('Error uploading asset:', error);
      toast({ title: 'Error', description: 'Failed to upload asset', variant: 'destructive' });
    } finally {
      setUploadingAsset(false);
      // Reset file input
      event.target.value = '';
    }
  };

  const handleDeleteAsset = async (assetType, assetId) => {
    if (!window.confirm('Are you sure you want to delete this asset?')) return;

    try {
      await storyGeneratorAPI.deleteAsset(assetType, assetId);
      toast({ title: 'Deleted', description: 'Asset deleted successfully' });
      await loadAssets();
    } catch (error) {
      console.error('Error deleting asset:', error);
      toast({ title: 'Error', description: 'Failed to delete asset', variant: 'destructive' });
    }
  };

  const renderRoundsPreview = () => {
    if (!selectedPresentation?.rounds) return null;

    return (
      <div className="space-y-2 mt-4">
        <Label className="text-gray-300">Rounds ({selectedPresentation.numRounds})</Label>
        <div className="space-y-2">
          {selectedPresentation.rounds.map((round, idx) => (
            <div 
              key={idx} 
              className={`${ROUND_COLORS[round.type] || 'bg-gray-500'} rounded-lg px-4 py-2 flex items-center justify-between`}
            >
              <span className="font-semibold text-white text-sm">
                {ROUND_NAMES[round.type] || round.type}
              </span>
              <span className="text-white text-sm truncate ml-4">
                {round.name}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderPreviewTimeline = () => {
    if (!preview) return null;

    return (
      <div className="bg-[#2a2a2a] border border-gray-600 rounded-lg p-4 mt-4">
        <h4 className="text-[#FFC107] font-semibold mb-3 flex items-center gap-2">
          <Video className="w-4 h-4" />
          Story Timeline ({preview.totalDuration}s)
        </h4>
        <div className="space-y-3">
          {/* Location segment */}
          <div className="flex items-center gap-3">
            <div className="w-16 text-right text-gray-500 text-sm">{preview.location.duration}s</div>
            <div className="flex-1 bg-[#1657E8] rounded-lg p-3 flex items-center justify-between">
              <span className="text-white text-sm">📍 Location: {preview.location.name}</span>
              {preview.location.hasAsset ? (
                <CheckCircle2 className="w-4 h-4 text-green-400" />
              ) : (
                <AlertCircle className="w-4 h-4 text-yellow-400" />
              )}
            </div>
          </div>
          
          {/* Host segment */}
          <div className="flex items-center gap-3">
            <div className="w-16 text-right text-gray-500 text-sm">{preview.host.duration}s</div>
            <div className="flex-1 bg-[#16213e] rounded-lg p-3 flex items-center justify-between">
              <span className="text-white text-sm">🎤 Host: {preview.host.name}</span>
              {preview.host.hasAsset ? (
                <CheckCircle2 className="w-4 h-4 text-green-400" />
              ) : (
                <AlertCircle className="w-4 h-4 text-yellow-400" />
              )}
            </div>
          </div>
          
          {/* Rounds segment */}
          <div className="flex items-center gap-3">
            <div className="w-16 text-right text-gray-500 text-sm">{preview.rounds.duration}s</div>
            <div className="flex-1 bg-[#0a0a1a] rounded-lg p-3 flex items-center justify-between">
              <span className="text-white text-sm">🎯 Rounds ({preview.rounds.items.length})</span>
              {preview.rounds.hasBackground ? (
                <CheckCircle2 className="w-4 h-4 text-green-400" />
              ) : (
                <AlertCircle className="w-4 h-4 text-yellow-400" />
              )}
            </div>
          </div>
        </div>
        
        {/* Missing assets warning */}
        {(!preview.location.hasAsset || !preview.host.hasAsset || !preview.rounds.hasBackground) && (
          <div className="mt-3 p-2 bg-yellow-500/20 border border-yellow-500/30 rounded-lg">
            <p className="text-yellow-400 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              Some assets are missing. Placeholder images will be used. Go to &quot;Manage Assets&quot; to upload custom images.
            </p>
          </div>
        )}
      </div>
    );
  };

  const renderAssetsList = (assetType, assetsList) => (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-gray-300 capitalize">{assetType}s ({assetsList.length})</Label>
        <label className="cursor-pointer">
          <Input
            type="file"
            accept="image/*,.gif"
            className="hidden"
            onChange={(e) => handleUploadAsset(e, assetType)}
            disabled={uploadingAsset}
          />
          <Button 
            variant="outline" 
            size="sm" 
            className="gap-1 text-xs"
            disabled={uploadingAsset}
            asChild
          >
            <span>
              {uploadingAsset ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
              Upload Local
            </span>
          </Button>
        </label>
      </div>
      <div className="max-h-48 overflow-y-auto space-y-1">
        {assetsList.length === 0 ? (
          <p className="text-gray-500 text-sm">No {assetType} assets available</p>
        ) : (
          assetsList.map((asset) => (
            <div 
              key={asset.id} 
              className="flex items-center justify-between bg-[#2a2a2a] rounded px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <ImageIcon className="w-4 h-4 text-gray-400" />
                <span className="text-white text-sm">{asset.name}</span>
                <Badge variant="outline" className="text-xs">{asset.type}</Badge>
                {asset.source === 'sharepoint' ? (
                  <Badge className="text-xs bg-blue-600">SharePoint</Badge>
                ) : (
                  <Badge className="text-xs bg-gray-600">Local</Badge>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="text-red-400 hover:text-red-500 h-6 w-6 p-0"
                onClick={() => handleDeleteAsset(assetType, asset.id)}
              >
                <Trash2 className="w-3 h-3" />
              </Button>
            </div>
          ))
        )}
      </div>
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="bg-gradient-to-br from-[#1a1a2e] to-[#16213e] border-[#FFC107]/30 text-white max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-[#FFC107] text-2xl flex items-center gap-2">
            <Video className="w-6 h-6" />
            Instagram Story Generator
          </DialogTitle>
          <DialogDescription className="text-gray-400">
            Generate a 25-second video from your trivia presentations for Instagram Stories
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
          <TabsList className="grid w-full grid-cols-2 bg-[#2a2a2a]">
            <TabsTrigger value="generate" className="data-[state=active]:bg-[#FFC107] data-[state=active]:text-black">
              Generate Story
            </TabsTrigger>
            <TabsTrigger value="assets" className="data-[state=active]:bg-[#FFC107] data-[state=active]:text-black">
              Manage Assets
            </TabsTrigger>
          </TabsList>

          <TabsContent value="generate" className="space-y-4 mt-4">
            {/* Presentation Selector */}
            <div>
              <Label className="text-gray-300">Select Presentation</Label>
              <Select 
                value={selectedPresentationId} 
                onValueChange={handlePresentationSelect}
                disabled={loading}
              >
                <SelectTrigger className="bg-[#2a2a2a] border-gray-600 text-white mt-2">
                  <SelectValue placeholder="Choose a presentation..." />
                </SelectTrigger>
                <SelectContent className="bg-[#2a2a2a] border-gray-600 max-h-64">
                  {presentations.length === 0 ? (
                    <div className="px-2 py-2 text-gray-400 text-sm">
                      No presentations found. Build a trivia presentation first.
                    </div>
                  ) : (
                    presentations.map((pres) => (
                      <SelectItem 
                        key={pres.id} 
                        value={pres.id} 
                        className="text-white hover:bg-[#3a3a3a]"
                      >
                        <div className="flex items-center gap-2">
                          <span>{pres.name}</span>
                          <Badge variant="outline" className="text-xs">{pres.numRounds} rounds</Badge>
                        </div>
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>

            {loading && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-8 h-8 text-[#FFC107] animate-spin" />
              </div>
            )}

            {/* Presentation Details */}
            {selectedPresentation && !loading && (
              <Card className="bg-[#2a2a2a] border-gray-600">
                <CardHeader className="pb-2">
                  <CardTitle className="text-white text-lg">{selectedPresentation.name}</CardTitle>
                  <CardDescription className="text-gray-400">
                    📍 {selectedPresentation.location} • 🎤 {selectedPresentation.host}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {renderRoundsPreview()}
                  {renderPreviewTimeline()}
                </CardContent>
              </Card>
            )}

            {/* Generated Video Download */}
            {generatedVideo && (
              <Card className="bg-green-900/30 border-green-500/50">
                <CardContent className="py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <CheckCircle2 className="w-6 h-6 text-green-400" />
                      <div>
                        <p className="text-white font-semibold">Video Ready!</p>
                        <p className="text-gray-400 text-sm">{generatedVideo.filename}</p>
                      </div>
                    </div>
                    <Button 
                      onClick={handleDownload}
                      className="bg-green-600 hover:bg-green-700"
                    >
                      <Download className="w-4 h-4 mr-2" />
                      Download MP4
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Generate Button */}
            <DialogFooter className="pt-4">
              <Button
                onClick={handleGenerateVideo}
                disabled={!selectedPresentationId || generating || loading}
                className="bg-[#FFC107] hover:bg-[#FFD54F] text-black font-semibold w-full"
              >
                {generating ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Generating Video...
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 mr-2" />
                    Generate Instagram Story
                  </>
                )}
              </Button>
            </DialogFooter>
          </TabsContent>

          <TabsContent value="assets" className="space-y-6 mt-4">
            {/* SharePoint Status */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {assets.sharepoint_enabled ? (
                  <Badge className="bg-green-600 text-white">
                    <CheckCircle2 className="w-3 h-3 mr-1" />
                    SharePoint Connected
                  </Badge>
                ) : (
                  <Badge className="bg-gray-600 text-white">
                    <AlertCircle className="w-3 h-3 mr-1" />
                    Local Mode
                  </Badge>
                )}
                <span className="text-gray-400 text-sm">
                  {assets.sharepoint_enabled 
                    ? 'Assets loaded from SharePoint 01_Socials folder'
                    : 'Using local placeholder assets'}
                </span>
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={handleRefreshAssets}
                disabled={refreshingAssets}
                className="gap-1"
              >
                <RefreshCw className={`w-3 h-3 ${refreshingAssets ? 'animate-spin' : ''}`} />
                {refreshingAssets ? 'Refreshing...' : 'Refresh from SharePoint'}
              </Button>
            </div>

            <div className="grid gap-6">
              {renderAssetsList('location', assets.locations || [])}
              {renderAssetsList('host', assets.hosts || [])}
              {renderAssetsList('background', assets.backgrounds || [])}
            </div>

            <div className="bg-[#2a2a2a] border border-gray-600 rounded-lg p-4">
              <h4 className="text-[#FFC107] font-semibold mb-2">📋 SharePoint Folder Structure</h4>
              <ul className="text-gray-400 text-sm space-y-1">
                <li>• <code className="text-blue-400">01_Socials/01_Locations/</code> - Location images (named to match location)</li>
                <li>• <code className="text-blue-400">01_Socials/02_Hosts/</code> - Host GIF animations</li>
                <li>• <code className="text-blue-400">01_Socials/03_Backgrounds/</code> - Background images (named to match location)</li>
                <li>• Supported formats: PNG, JPG, JPEG, WebP, GIF</li>
                <li>• Recommended size: 1080x1920 pixels (9:16 aspect ratio for Instagram Stories)</li>
                <li>• New assets are automatically detected when you click &quot;Refresh from SharePoint&quot;</li>
              </ul>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};

export default StoryGenerator;
