import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Button } from '../../ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter
} from '../../ui/dialog';
import { Layers, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '../../ui/alert';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const OverlayManager = ({ presentationId, locationName, onOverlaysApplied, slides }) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // Fetch preview when dialog opens
  useEffect(() => {
    if (open) {
      if (!presentationId || !locationName) {
        setError('No location information available for this presentation');
        setLoading(false);
        return;
      }
      fetchPreview();
    }
  }, [open, presentationId, locationName]);

  const fetchPreview = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Use POST endpoint with slides if we have them
      let response;
      if (slides && slides.length > 0) {
        response = await axios.post(
          `${API}/overlays/preview-with-slides/${presentationId}`,
          {
            presentationId,
            locationName,
            slides
          }
        );
      } else {
        // Fallback to GET endpoint
        response = await axios.get(
          `${API}/overlays/preview/${presentationId}?location_name=${encodeURIComponent(locationName)}`
        );
      }
      
      setPreview(response.data);
    } catch (err) {
      console.error('Error fetching overlay preview:', err);
      setError(err.response?.data?.detail || 'Failed to fetch overlay preview');
    } finally {
      setLoading(false);
    }
  };

  const applyOverlays = async () => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);
      
      const response = await axios.post(
        `${API}/overlays/apply/${presentationId}`,
        {
          presentationId,
          locationName,
          slides: slides || []  // Pass slides directly for overlay application
        }
      );
      
      setResult(response.data);
      
      // Notify parent component
      if (onOverlaysApplied) {
        onOverlaysApplied(response.data);
      }
      
      // Auto-close after success
      setTimeout(() => {
        setOpen(false);
        setResult(null);
      }, 2000);
      
    } catch (err) {
      console.error('Error applying overlays:', err);
      setError(err.response?.data?.detail || 'Failed to apply overlays');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button 
          variant="ghost" 
          size="sm" 
          className="text-white hover:bg-gray-700"
        >
          <Layers className="w-4 h-4 mr-2" />
          Overlays
        </Button>
      </DialogTrigger>
      
      <DialogContent className="sm:max-w-[600px] bg-[#1a1a1a] text-white border-gray-700">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="w-5 h-5" />
            Apply Location Overlays
          </DialogTitle>
          <DialogDescription className="text-gray-400">
            Location: <span className="font-semibold text-white">{locationName}</span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {loading && !result && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
              <span className="ml-3 text-gray-300">
                {preview ? 'Applying overlays...' : 'Loading preview...'}
              </span>
            </div>
          )}

          {error && (
            <Alert className="bg-red-900/20 border-red-500">
              <AlertCircle className="h-4 w-4 text-red-500" />
              <AlertDescription className="text-red-300">
                {error}
              </AlertDescription>
            </Alert>
          )}

          {result && (
            <Alert className="bg-green-900/20 border-green-500">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <AlertDescription className="text-green-300">
                Successfully applied {result.overlaysApplied} overlays to your presentation!
              </AlertDescription>
            </Alert>
          )}

          {preview && !loading && !result && (
            <div className="space-y-3">
              <div className="bg-gray-800 rounded-lg p-4">
                <h4 className="font-semibold mb-2 text-sm text-gray-300">Preview Summary</h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-400">Total Slides:</span>
                    <span className="ml-2 font-semibold">{preview.totalSlides}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Available Overlays:</span>
                    <span className="ml-2 font-semibold">{preview.availableOverlays}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Rounds Detected:</span>
                    <span className="ml-2 font-semibold">{preview.preview?.length || 0}</span>
                  </div>
                </div>
              </div>

              {preview.preview && preview.preview.length > 0 && (
                <div className="max-h-64 overflow-y-auto space-y-2">
                  <h4 className="font-semibold text-sm text-gray-300 sticky top-0 bg-[#1a1a1a] py-2">
                    Overlays to Apply:
                  </h4>
                  {preview.preview.map((item, index) => (
                    <div 
                      key={index}
                      className="bg-gray-800 rounded p-3 text-sm border border-gray-700"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="font-medium text-white">
                            Round {item.roundNumber} ({item.roundType})
                          </div>
                          <div className="text-gray-400 text-xs mt-1">
                            Title Slide: {item.slideIndex}
                          </div>
                        </div>
                        <div className="text-right">
                          {item.overlayName ? (
                            <div className="text-green-400 text-xs">
                              ✓ {item.overlayName}
                            </div>
                          ) : (
                            <div className="text-yellow-400 text-xs">
                              ⚠ No overlay found
                            </div>
                          )}
                          {item.willApplyToSlide !== null && (
                            <div className="text-gray-500 text-xs mt-1">
                              → Apply to slide {item.willApplyToSlide}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {(!preview.preview || preview.preview.length === 0) && (
                <Alert className="bg-yellow-900/20 border-yellow-500">
                  <AlertCircle className="h-4 w-4 text-yellow-500" />
                  <AlertDescription className="text-yellow-300">
                    No rounds detected in this presentation. Overlays are applied to round title slides.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          {preview && !result && (
            <>
              <Button
                variant="outline"
                onClick={() => setOpen(false)}
                disabled={loading}
                className="bg-gray-800 text-white hover:bg-gray-700 border-gray-600"
              >
                Cancel
              </Button>
              <Button
                onClick={applyOverlays}
                disabled={loading || !preview.preview || preview.preview.length === 0}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Applying...
                  </>
                ) : (
                  'Apply Overlays'
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default OverlayManager;
