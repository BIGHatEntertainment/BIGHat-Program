import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { ArrowLeft, Trash2, RefreshCw, Loader2, AlertCircle } from 'lucide-react';
import { toast } from '../hooks/use-toast';
import { adminAPI } from '../services/api';

const Admin = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [releasing, setReleasing] = useState(null);
  const [stats, setStats] = useState({});
  const [usageRecords, setUsageRecords] = useState([]);

  useEffect(() => {
    loadData();
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
        toast({ 
          title: 'Success', 
          description: `Removed ${result.deletedCount} expired records` 
        });
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
    if (window.confirm('⚠️ WARNING: This will release ALL rounds (including active ones) back into the selection pool. This cannot be undone. Are you sure?')) {
      try {
        setLoading(true);
        const result = await adminAPI.releaseAll();
        toast({ 
          title: 'Success', 
          description: `Released all ${result.deletedCount} rounds` 
        });
        await loadData();
      } catch (error) {
        console.error('Error releasing all:', error);
        toast({ title: 'Error', description: 'Failed to release all rounds', variant: 'destructive' });
      } finally {
        setLoading(false);
      }
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
      'MC': 'bg-green-500',
      'REG': 'bg-red-500',
      'MISC': 'bg-blue-500',
      'MYS': 'bg-purple-500',
      'BIG': 'bg-yellow-500 text-black'
    };
    return colors[type] || 'bg-gray-500';
  };

  if (loading && usageRecords.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Button 
              variant="outline" 
              onClick={() => navigate('/')}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Home
            </Button>
            <h1 className="text-3xl font-bold">Admin - Round Management</h1>
          </div>
          <div className="flex gap-2">
            <Button 
              variant="outline" 
              onClick={loadData}
              disabled={loading}
              className="gap-2"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleCleanupExpired}
              disabled={loading || stats.expiredRecords === 0}
              className="gap-2"
            >
              <Trash2 className="h-4 w-4" />
              Cleanup Expired ({stats.expiredRecords || 0})
            </Button>
            <Button 
              variant="destructive" 
              onClick={handleReleaseAll}
              disabled={loading || stats.totalUsageRecords === 0}
              className="gap-2 bg-red-700 hover:bg-red-800"
            >
              <Trash2 className="h-4 w-4" />
              Release All ({stats.totalUsageRecords || 0})
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Records</CardDescription>
              <CardTitle className="text-2xl">{stats.totalUsageRecords || 0}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Active Records</CardDescription>
              <CardTitle className="text-2xl text-green-600">{stats.activeRecords || 0}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Expired Records</CardDescription>
              <CardTitle className="text-2xl text-orange-600">{stats.expiredRecords || 0}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Presentations</CardDescription>
              <CardTitle className="text-2xl">{stats.totalPresentations || 0}</CardTitle>
            </CardHeader>
          </Card>
        </div>

        {/* Usage Records Table */}
        <Card>
          <CardHeader>
            <CardTitle>Round Usage Records</CardTitle>
            <CardDescription>
              Manage which rounds are currently in use at each location. Release rounds to make them available for selection again.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {usageRecords.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <AlertCircle className="h-12 w-12 mx-auto mb-2 opacity-50" />
                <p>No usage records found</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Status</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Location</TableHead>
                      <TableHead>Round File</TableHead>
                      <TableHead>Presentation</TableHead>
                      <TableHead>Used Date</TableHead>
                      <TableHead>Expires</TableHead>
                      <TableHead>Used By</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {usageRecords.map((record) => (
                      <TableRow key={record.id} className={record.isExpired ? 'opacity-60' : ''}>
                        <TableCell>
                          <Badge variant={record.isExpired ? 'secondary' : 'default'}>
                            {record.isExpired ? 'Expired' : 'Active'}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge className={getRoundTypeBadgeColor(record.roundType)}>
                            {record.roundType || 'N/A'}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {record.locationName || record.location}
                        </TableCell>
                        <TableCell className="font-mono text-xs max-w-xs truncate" title={record.roundFile}>
                          {record.roundFileName}
                        </TableCell>
                        <TableCell className="text-sm">
                          {record.presentationName || 'N/A'}
                        </TableCell>
                        <TableCell className="text-sm whitespace-nowrap">
                          {formatDate(record.usedDate)}
                        </TableCell>
                        <TableCell className="text-sm whitespace-nowrap">
                          {formatDate(record.expiresDate)}
                        </TableCell>
                        <TableCell className="text-sm">
                          {record.usedBy}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleReleaseRound(record.id, record.roundFileName)}
                            disabled={releasing === record.id}
                            className="gap-2"
                          >
                            {releasing === record.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Trash2 className="h-4 w-4" />
                            )}
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
  );
};

export default Admin;
