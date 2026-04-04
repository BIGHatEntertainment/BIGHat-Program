import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Checkbox } from '../components/ui/checkbox';
import { ArrowLeft, Trash2, RefreshCw, Loader2, AlertCircle, ShieldAlert, CheckSquare } from 'lucide-react';
import { toast } from '../hooks/use-toast';
import { adminAPI } from '../services/api';

// List of authorized admin users (case-insensitive)
const ADMIN_USERS = ['nick', 'caelie', 'tommy'];

const Admin = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [releasing, setReleasing] = useState(null);
  const [releasingMultiple, setReleasingMultiple] = useState(false);
  const [stats, setStats] = useState({});
  const [usageRecords, setUsageRecords] = useState([]);
  const [selectedRecords, setSelectedRecords] = useState(new Set());
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [currentUser, setCurrentUser] = useState('');

  useEffect(() => {
    const userName = localStorage.getItem('userName') || '';
    setCurrentUser(userName);
    const authorized = ADMIN_USERS.includes(userName.toLowerCase());
    setIsAuthorized(authorized);
    if (authorized) {
      loadData();
    } else {
      setLoading(false);
    }
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [statsData, usageData] = await Promise.all([
        adminAPI.getStats(),
        adminAPI.getRoundUsage()
      ]);
      setStats(statsData);
      setUsageRecords(usageData);
    } catch (error) {
      console.error('Error loading admin data:', error);
      toast({ title: 'Error', description: 'Failed to load admin data', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleReleaseRound = async (usageId, roundInfo) => {
    if (window.confirm(`Release "${roundInfo}" back into the selection pool?`)) {
      try {
        setReleasing(usageId);
        await adminAPI.releaseRound(usageId);
        toast({ title: 'Success', description: 'Round released successfully' });
        await loadData();
      } catch (error) {
        console.error('Error releasing round:', error);
        toast({ title: 'Error', description: 'Failed to release round', variant: 'destructive' });
      } finally {
        setReleasing(null);
      }
    }
  };

  const handleCleanupExpired = async () => {
    if (window.confirm('Remove all expired usage records? This cannot be undone.')) {
      try {
        setLoading(true);
        const result = await adminAPI.cleanupExpired();
        toast({ title: 'Success', description: `Removed ${result.deletedCount} expired records` });
        await loadData();
      } catch (error) {
        console.error('Error cleaning up:', error);
        toast({ title: 'Error', description: 'Failed to cleanup expired records', variant: 'destructive' });
      } finally {
        setLoading(false);
      }
    }
  };

  const handleReleaseAll = async () => {
    if (window.confirm('⚠️ WARNING: This will release ALL rounds back into the selection pool. Are you sure?')) {
      try {
        setLoading(true);
        const result = await adminAPI.releaseAll();
        toast({ title: 'Success', description: `Released all ${result.deletedCount} rounds` });
        setSelectedRecords(new Set());
        await loadData();
      } catch (error) {
        console.error('Error releasing all:', error);
        toast({ title: 'Error', description: 'Failed to release all rounds', variant: 'destructive' });
      } finally {
        setLoading(false);
      }
    }
  };

  const handleReleaseSelected = async () => {
    if (selectedRecords.size === 0) return;
    const selectedCount = selectedRecords.size;
    if (window.confirm(`Release ${selectedCount} selected round${selectedCount > 1 ? 's' : ''} back into the selection pool?`)) {
      try {
        setReleasingMultiple(true);
        const usageIds = Array.from(selectedRecords);
        await adminAPI.releaseMultiple(usageIds);
        toast({ title: 'Success', description: `Released ${selectedCount} round${selectedCount > 1 ? 's' : ''} successfully` });
        setSelectedRecords(new Set());
        await loadData();
      } catch (error) {
        console.error('Error releasing selected rounds:', error);
        toast({ title: 'Error', description: 'Failed to release selected rounds', variant: 'destructive' });
      } finally {
        setReleasingMultiple(false);
      }
    }
  };

  const toggleRecordSelection = (recordId) => {
    const newSelected = new Set(selectedRecords);
    if (newSelected.has(recordId)) {
      newSelected.delete(recordId);
    } else {
      newSelected.add(recordId);
    }
    setSelectedRecords(newSelected);
  };

  const toggleSelectAll = () => {
    if (selectedRecords.size === usageRecords.length) {
      setSelectedRecords(new Set());
    } else {
      setSelectedRecords(new Set(usageRecords.map(r => r.id)));
    }
  };

  const formatDate = (dateStr) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return dateStr;
    }
  };

  const getRoundTypeBadgeColor = (type) => {
    const colors = {
      'MC': 'bg-green-500/20 text-green-400 border-green-500/30',
      'REG': 'bg-red-500/20 text-red-400 border-red-500/30',
      'MISC': 'bg-blue-500/20 text-blue-400 border-blue-500/30',
      'MYS': 'bg-purple-500/20 text-purple-400 border-purple-500/30',
      'BIG': 'bg-[#fbdd68]/20 text-[#fbdd68] border-[#fbdd68]/30'
    };
    return colors[type] || 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  };

  // Unauthorized access screen
  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-[#000e2a] flex items-center justify-center p-8">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-20 left-10 w-[400px] h-[400px] bg-red-500/10 rounded-full filter blur-[120px]"></div>
          <div className="absolute bottom-20 right-20 w-[400px] h-[400px] bg-[#141b50] rounded-full filter blur-[120px]"></div>
        </div>
        <Card className="max-w-md w-full bg-[#0a1940] border border-red-500/30 relative z-10">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 p-4 bg-red-500/20 rounded-full w-fit">
              <ShieldAlert className="h-12 w-12 text-red-400" />
            </div>
            <CardTitle className="text-2xl text-red-400">Access Denied</CardTitle>
            <CardDescription className="text-[#8892b0] mt-2">
              You do not have permission to access the Admin area.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="bg-[#141b50]/50 rounded-lg p-4 border border-[#fbdd68]/10">
              <p className="text-[#8892b0] text-sm">
                <span className="text-[#8892b0]/70">Logged in as:</span>{' '}
                <span className="text-[#fbdd68] font-semibold">{currentUser || 'Unknown'}</span>
              </p>
              <p className="text-[#8892b0]/60 text-xs mt-2">
                Only authorized administrators can access this area.
              </p>
            </div>
            <Button 
              onClick={() => navigate('/')}
              className="w-full bg-[#fbdd68] text-[#000e2a] hover:bg-[#fee16b] font-semibold"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Return to Home
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (loading && usageRecords.length === 0) {
    return (
      <div className="min-h-screen bg-[#000e2a] flex items-center justify-center">
        <Loader2 className="h-10 w-10 animate-spin text-[#fbdd68]" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#000e2a] relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 w-[500px] h-[500px] bg-[#141b50] rounded-full filter blur-[120px] opacity-40"></div>
        <div className="absolute bottom-20 right-20 w-[400px] h-[400px] bg-[#fbdd68] rounded-full filter blur-[150px] opacity-5"></div>
      </div>

      <div className="relative z-10 p-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-4">
              <Button 
                variant="outline" 
                onClick={() => navigate('/')}
                className="gap-2 bg-[#141b50]/60 border-[#fbdd68]/30 text-[#fbdd68] hover:bg-[#fbdd68] hover:text-[#000e2a]"
              >
                <ArrowLeft className="h-4 w-4" />
                Back
              </Button>
              <div>
                <h1 className="text-3xl font-bold text-white">Admin Panel</h1>
                <p className="text-[#8892b0] text-sm">Round Management</p>
              </div>
            </div>
            <div className="flex gap-2">
              {selectedRecords.size > 0 && (
                <Button 
                  onClick={handleReleaseSelected}
                  disabled={releasingMultiple}
                  className="gap-2 bg-[#fbdd68] text-[#000e2a] hover:bg-[#fee16b]"
                >
                  {releasingMultiple ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckSquare className="h-4 w-4" />}
                  Release Selected ({selectedRecords.size})
                </Button>
              )}
              <Button 
                variant="outline" 
                onClick={loadData}
                disabled={loading}
                className="gap-2 bg-[#141b50]/60 border-[#fbdd68]/20 text-white hover:bg-[#141b50]"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
              <Button 
                variant="outline" 
                onClick={handleCleanupExpired}
                disabled={loading || stats.expiredRecords === 0}
                className="gap-2 bg-orange-500/20 border-orange-500/30 text-orange-400 hover:bg-orange-500 hover:text-white"
              >
                <Trash2 className="h-4 w-4" />
                Cleanup ({stats.expiredRecords || 0})
              </Button>
              <Button 
                onClick={handleReleaseAll}
                disabled={loading || stats.totalUsageRecords === 0}
                className="gap-2 bg-red-500/20 border-red-500/30 text-red-400 hover:bg-red-500 hover:text-white"
              >
                <Trash2 className="h-4 w-4" />
                Release All ({stats.totalUsageRecords || 0})
              </Button>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <Card className="bg-[#141b50]/50 border border-[#fbdd68]/10">
              <CardHeader className="pb-2">
                <CardDescription className="text-[#8892b0]">Total Records</CardDescription>
                <CardTitle className="text-3xl text-white">{stats.totalUsageRecords || 0}</CardTitle>
              </CardHeader>
            </Card>
            <Card className="bg-[#141b50]/50 border border-green-500/20">
              <CardHeader className="pb-2">
                <CardDescription className="text-[#8892b0]">Active Records</CardDescription>
                <CardTitle className="text-3xl text-green-400">{stats.activeRecords || 0}</CardTitle>
              </CardHeader>
            </Card>
            <Card className="bg-[#141b50]/50 border border-orange-500/20">
              <CardHeader className="pb-2">
                <CardDescription className="text-[#8892b0]">Expired Records</CardDescription>
                <CardTitle className="text-3xl text-orange-400">{stats.expiredRecords || 0}</CardTitle>
              </CardHeader>
            </Card>
            <Card className="bg-[#141b50]/50 border border-[#fbdd68]/20">
              <CardHeader className="pb-2">
                <CardDescription className="text-[#8892b0]">Total Presentations</CardDescription>
                <CardTitle className="text-3xl text-[#fbdd68]">{stats.totalPresentations || 0}</CardTitle>
              </CardHeader>
            </Card>
          </div>

          {/* Usage Records Table */}
          <Card className="bg-[#0a1940]/80 backdrop-blur-sm border border-[#fbdd68]/10">
            <CardHeader>
              <CardTitle className="text-white">Round Usage Records</CardTitle>
              <CardDescription className="text-[#8892b0]">
                Manage which rounds are currently in use. Release rounds to make them available again.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {usageRecords.length === 0 ? (
                <div className="text-center py-12">
                  <AlertCircle className="h-12 w-12 mx-auto mb-3 text-[#8892b0]/50" />
                  <p className="text-[#8892b0]">No usage records found</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-[#fbdd68]/10 hover:bg-transparent">
                        <TableHead className="w-12 text-[#8892b0]">
                          <Checkbox 
                            checked={usageRecords.length > 0 && selectedRecords.size === usageRecords.length}
                            onCheckedChange={toggleSelectAll}
                            aria-label="Select all"
                            data-testid="select-all-checkbox"
                            className="border-[#fbdd68]/30 data-[state=checked]:bg-[#fbdd68] data-[state=checked]:text-[#000e2a]"
                          />
                        </TableHead>
                        <TableHead className="text-[#8892b0]">Status</TableHead>
                        <TableHead className="text-[#8892b0]">Type</TableHead>
                        <TableHead className="text-[#8892b0]">Location</TableHead>
                        <TableHead className="text-[#8892b0]">Round File</TableHead>
                        <TableHead className="text-[#8892b0]">Presentation</TableHead>
                        <TableHead className="text-[#8892b0]">Used Date</TableHead>
                        <TableHead className="text-[#8892b0]">Expires</TableHead>
                        <TableHead className="text-[#8892b0]">Used By</TableHead>
                        <TableHead className="text-right text-[#8892b0]">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {usageRecords.map((record) => (
                        <TableRow 
                          key={record.id} 
                          className={`border-[#fbdd68]/5 hover:bg-[#141b50]/30 ${record.isExpired ? 'opacity-50' : ''} ${selectedRecords.has(record.id) ? 'bg-[#fbdd68]/5' : ''}`}
                        >
                          <TableCell>
                            <Checkbox 
                              checked={selectedRecords.has(record.id)}
                              onCheckedChange={() => toggleRecordSelection(record.id)}
                              className="border-[#fbdd68]/30 data-[state=checked]:bg-[#fbdd68] data-[state=checked]:text-[#000e2a]"
                            />
                          </TableCell>
                          <TableCell>
                            <Badge className={record.isExpired ? 'bg-orange-500/20 text-orange-400 border-orange-500/30' : 'bg-green-500/20 text-green-400 border-green-500/30'}>
                              {record.isExpired ? 'Expired' : 'Active'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge className={getRoundTypeBadgeColor(record.roundType)}>
                              {record.roundType || 'N/A'}
                            </Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs text-white/80">
                            {record.locationName || record.location}
                          </TableCell>
                          <TableCell className="font-mono text-xs text-white/80 max-w-xs truncate" title={record.roundFile}>
                            {record.roundFileName}
                          </TableCell>
                          <TableCell className="text-sm text-white/80">
                            {record.presentationName || 'N/A'}
                          </TableCell>
                          <TableCell className="text-sm text-white/60 whitespace-nowrap">
                            {formatDate(record.usedDate)}
                          </TableCell>
                          <TableCell className="text-sm text-white/60 whitespace-nowrap">
                            {formatDate(record.expiresDate)}
                          </TableCell>
                          <TableCell className="text-sm text-[#fbdd68]">
                            {record.usedBy}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleReleaseRound(record.id, record.roundFileName)}
                              disabled={releasing === record.id}
                              className="gap-2 text-red-400 hover:text-white hover:bg-red-500/20"
                            >
                              {releasing === record.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                              Release
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default Admin;
