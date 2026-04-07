import React, { useState, useEffect } from 'react';
import { X, Check, Loader2, Grid3X3, MapPin, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from './ui/button';
import { Checkbox } from './ui/checkbox';
import { placementsApi } from '../services/api';
import { toast } from 'sonner';

/**
 * Sponsor Placement Matrix Component
 * Shows a grid of venues (columns) x placement types (rows)
 * Admin can toggle each cell to control where sponsor images appear
 */
const SponsorPlacementMatrix = ({ sponsor, onClose }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [matrix, setMatrix] = useState(null);
  const [placements, setPlacements] = useState({});
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    loadMatrix();
  }, [sponsor.id]);

  const loadMatrix = async () => {
    setLoading(true);
    try {
      const data = await placementsApi.getMatrix(sponsor.id);
      setMatrix(data);
      setPlacements(data.placements || {});
    } catch (err) {
      console.error('Failed to load placement matrix:', err);
      toast.error('Failed to load placement matrix');
    } finally {
      setLoading(false);
    }
  };

  const handleCellToggle = (locationId, placementType) => {
    setPlacements(prev => {
      const newPlacements = { ...prev };
      if (!newPlacements[locationId]) {
        newPlacements[locationId] = {};
      }
      newPlacements[locationId] = {
        ...newPlacements[locationId],
        [placementType]: !newPlacements[locationId][placementType]
      };
      return newPlacements;
    });
    setHasChanges(true);
  };

  const handleSelectAllLocation = async (locationId) => {
    // Check if all are currently selected
    const allSelected = matrix.placement_types.every(
      pt => placements[locationId]?.[pt.id]
    );
    const newEnabled = !allSelected;

    // Update local state immediately
    setPlacements(prev => {
      const newPlacements = { ...prev };
      newPlacements[locationId] = {};
      matrix.placement_types.forEach(pt => {
        newPlacements[locationId][pt.id] = newEnabled;
      });
      return newPlacements;
    });

    // Save to backend
    try {
      await placementsApi.selectAllForLocation(sponsor.id, locationId, newEnabled);
      toast.success(`${newEnabled ? 'Selected' : 'Deselected'} all for this venue`);
    } catch (err) {
      toast.error('Failed to update');
      loadMatrix(); // Reload on error
    }
  };

  const handleSelectAllPlacementType = async (placementType) => {
    // Check if all are currently selected for this placement type
    const allSelected = matrix.locations.every(
      loc => placements[loc.id]?.[placementType]
    );
    const newEnabled = !allSelected;

    // Update local state immediately
    setPlacements(prev => {
      const newPlacements = { ...prev };
      matrix.locations.forEach(loc => {
        if (!newPlacements[loc.id]) {
          newPlacements[loc.id] = {};
        }
        newPlacements[loc.id][placementType] = newEnabled;
      });
      return newPlacements;
    });

    // Save to backend
    try {
      await placementsApi.selectAllForPlacementType(sponsor.id, placementType, newEnabled);
      toast.success(`${newEnabled ? 'Selected' : 'Deselected'} all venues for this placement`);
    } catch (err) {
      toast.error('Failed to update');
      loadMatrix(); // Reload on error
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      await placementsApi.bulkUpdate(sponsor.id, placements);
      toast.success('Placements saved successfully');
      setHasChanges(false);
    } catch (err) {
      console.error('Failed to save placements:', err);
      toast.error('Failed to save placements');
    } finally {
      setSaving(false);
    }
  };

  const handleSingleCellSave = async (locationId, placementType, enabled) => {
    try {
      await placementsApi.updatePlacement(sponsor.id, locationId, placementType, enabled);
    } catch (err) {
      console.error('Failed to update placement:', err);
      // Revert on error
      setPlacements(prev => ({
        ...prev,
        [locationId]: {
          ...prev[locationId],
          [placementType]: !enabled
        }
      }));
      toast.error('Failed to update placement');
    }
  };

  // Auto-save individual cell changes
  const handleCellChange = async (locationId, placementType) => {
    const newEnabled = !placements[locationId]?.[placementType];
    
    // Update local state
    setPlacements(prev => {
      const newPlacements = { ...prev };
      if (!newPlacements[locationId]) {
        newPlacements[locationId] = {};
      }
      newPlacements[locationId] = {
        ...newPlacements[locationId],
        [placementType]: newEnabled
      };
      return newPlacements;
    });

    // Save to backend
    await handleSingleCellSave(locationId, placementType, newEnabled);
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
        <div className="bg-[#1a1a2e] rounded-2xl p-8">
          <Loader2 className="w-8 h-8 animate-spin text-[#f4d03f] mx-auto" />
          <p className="text-white mt-4">Loading placement matrix...</p>
        </div>
      </div>
    );
  }

  if (!matrix || !matrix.locations || matrix.locations.length === 0) {
    return (
      <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
        <div className="bg-[#1a1a2e] rounded-2xl p-8 max-w-md">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-white">Placement Matrix</h2>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="w-5 h-5" />
            </Button>
          </div>
          <p className="text-white/60">No active venues found. Please add venues first.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-[#1a1a2e] rounded-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-white/10 flex justify-between items-center shrink-0">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Grid3X3 className="w-5 h-5 text-[#f4d03f]" />
              Placement Matrix
            </h2>
            <p className="text-white/60 text-sm mt-1">
              {sponsor.business_name} - Control where this sponsor appears at each venue
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="w-5 h-5" />
          </Button>
        </div>

        {/* Matrix Grid */}
        <div className="flex-1 overflow-auto p-6">
          <div className="min-w-max">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="sticky left-0 bg-[#1a1a2e] z-10 p-3 text-left text-white/70 text-sm font-medium border-b border-white/10 min-w-[200px]">
                    Placement Type
                  </th>
                  {matrix.locations.map(loc => (
                    <th key={loc.id} className="p-3 text-center border-b border-white/10 min-w-[100px]">
                      <div className="flex flex-col items-center gap-1">
                        <span className="text-white text-sm font-medium truncate max-w-[120px]" title={loc.name}>
                          {loc.name}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs text-[#f4d03f] hover:bg-[#f4d03f]/10 h-6 px-2"
                          onClick={() => handleSelectAllLocation(loc.id)}
                        >
                          {matrix.placement_types.every(pt => placements[loc.id]?.[pt.id]) 
                            ? 'Deselect All' 
                            : 'Select All'}
                        </Button>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.placement_types.map((pt, idx) => (
                  <tr key={pt.id} className={idx % 2 === 0 ? 'bg-white/5' : ''}>
                    <td className="sticky left-0 bg-[#1a1a2e] z-10 p-3 border-b border-white/5">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-white text-sm">{pt.name}</span>
                          <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                            pt.asset_type === '16:9' 
                              ? 'bg-blue-500/20 text-blue-400' 
                              : 'bg-purple-500/20 text-purple-400'
                          }`}>
                            {pt.asset_type}
                          </span>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs text-[#f4d03f] hover:bg-[#f4d03f]/10 h-6 px-2 ml-2"
                          onClick={() => handleSelectAllPlacementType(pt.id)}
                        >
                          {matrix.locations.every(loc => placements[loc.id]?.[pt.id]) 
                            ? 'None' 
                            : 'All'}
                        </Button>
                      </div>
                    </td>
                    {matrix.locations.map(loc => (
                      <td key={`${loc.id}-${pt.id}`} className="p-3 text-center border-b border-white/5">
                        <div className="flex justify-center">
                          <Checkbox
                            checked={placements[loc.id]?.[pt.id] || false}
                            onCheckedChange={() => handleCellChange(loc.id, pt.id)}
                            className="h-5 w-5 border-white/30 data-[state=checked]:bg-[#f4d03f] data-[state=checked]:border-[#f4d03f]"
                          />
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10 flex justify-between items-center shrink-0 bg-[#1a1a2e]">
          <p className="text-white/50 text-sm">
            <MapPin className="w-4 h-4 inline mr-1" />
            {matrix.locations.length} venues × {matrix.placement_types.length} placements
          </p>
          <div className="flex gap-3">
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SponsorPlacementMatrix;
