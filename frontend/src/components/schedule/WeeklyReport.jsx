import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, startOfWeek, parseISO, subDays } from 'date-fns';
import { FileText, Download, Calendar, DollarSign, Eye } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { Badge } from '../ui/badge';
import { toast } from 'sonner';
import PaymentDetailDialog from './PaymentDetailDialog';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const EVENT_TYPE_COLORS = {
  'Trivia': 'bg-green-500',
  'Karaoke': 'bg-pink-500',
  'Music Bingo': 'bg-blue-500',
  'Special': 'bg-purple-500',
};

const WeeklyReport = () => {
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedWeek, setSelectedWeek] = useState(() => {
    // Get last Friday by default
    const today = new Date();
    const dayOfWeek = today.getDay();
    const daysToFriday = dayOfWeek >= 5 ? dayOfWeek - 5 : dayOfWeek + 2;
    return subDays(today, daysToFriday);
  });
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [selectedPayment, setSelectedPayment] = useState(null);

  useEffect(() => {
    fetchReport();
  }, [selectedWeek]);

  const fetchReport = async () => {
    setLoading(true);
    try {
      const weekStart = startOfWeek(selectedWeek, { weekStartsOn: 5 }); // Friday
      const response = await axios.get(`${API}/reports/weekly?week_start=${weekStart.toISOString()}`);
      setReportData(response.data);
    } catch (error) {
      console.error('Error fetching report:', error);
      toast.error('Failed to load report');
    } finally {
      setLoading(false);
    }
  };

  const exportToCSV = () => {
    if (!reportData || !reportData.events || reportData.events.length === 0) {
      toast.error('No data to export');
      return;
    }

    const headers = ['Employee', 'Venue', 'Event Type', 'Date', 'Base Pay', 'Bonuses', 'Bonus Details', 'Total Pay'];
    const rows = reportData.events.map(event => [
      event.employee_name,
      event.venue_name,
      event.event_type,
      format(parseISO(event.date), 'MMM d, yyyy h:mm a'),
      event.base_pay ? `$${event.base_pay.toFixed(2)}` : '$0.00',
      event.bonuses ? `$${event.bonuses}` : '$0',
      event.bonus_details ? event.bonus_details.join('; ') : '-',
      event.total_pay ? `$${event.total_pay.toFixed(2)}` : 'N/A'
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `weekly-report-${format(parseISO(reportData.week_start), 'yyyy-MM-dd')}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
    toast.success('Report exported successfully');
  };

  const calculateTotals = () => {
    if (!reportData || !reportData.events) return { totalHours: 0, totalPay: 0 };
    
    return reportData.events.reduce((acc, event) => {
      acc.totalHours += event.duration_hours || 0;
      acc.totalPay += event.total_pay || 0;
      return acc;
    }, { totalHours: 0, totalPay: 0 });
  };

  const totals = calculateTotals();

  return (
    <div className="space-y-6">
      <Card className="border-2 shadow-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl flex items-center space-x-2">
                <FileText className="h-6 w-6 text-primary" />
                <span>Weekly Payment Report</span>
              </CardTitle>
              <CardDescription>View employee work hours and payment details</CardDescription>
            </div>
            <Button
              onClick={exportToCSV}
              variant="outline"
              className="flex items-center space-x-2 hover:bg-primary hover:text-primary-foreground transition-smooth"
              disabled={!reportData || reportData.events?.length === 0}
            >
              <Download className="h-4 w-4" />
              <span>Export CSV</span>
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Week Selector */}
          <div className="flex items-center space-x-4">
            <Label className="font-medium">Report Week:</Label>
            <div className="flex items-center space-x-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedWeek(prev => subDays(prev, 7))}
              >
                Previous Week
              </Button>
              <div className="px-4 py-2 bg-[#141b50] rounded-md font-medium">
                {reportData && (
                  <>
                    {format(parseISO(reportData.week_start), 'MMM d')} - {format(parseISO(reportData.week_end), 'MMM d, yyyy')}
                  </>
                )}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedWeek(prev => new Date(prev.getTime() + 7 * 24 * 60 * 60 * 1000))}
              >
                Next Week
              </Button>
            </div>
          </div>

          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-primary mx-auto mb-4"></div>
              <p className="text-gray-400">Loading report...</p>
            </div>
          ) : reportData && reportData.events && reportData.events.length > 0 ? (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card className="border-2">
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-400">Total Events</p>
                        <p className="text-3xl font-bold text-white">{reportData.events.length}</p>
                      </div>
                      <Calendar className="h-10 w-10 text-primary opacity-50" />
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-2">
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-400">Total Hours</p>
                        <p className="text-3xl font-bold text-white">{totals.totalHours.toFixed(1)}</p>
                      </div>
                      <FileText className="h-10 w-10 text-primary opacity-50" />
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-2">
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-400">Total Payout</p>
                        <p className="text-3xl font-bold text-white">${totals.totalPay.toFixed(2)}</p>
                      </div>
                      <DollarSign className="h-10 w-10 text-primary opacity-50" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Events Table */}
              <div className="border-2 rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Employee</TableHead>
                      <TableHead>Venue</TableHead>
                      <TableHead>Event Type</TableHead>
                      <TableHead>Date & Time</TableHead>
                      <TableHead className="text-right">Base Pay</TableHead>
                      <TableHead className="text-right">Bonuses</TableHead>
                      <TableHead className="text-right">Total Pay</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reportData.events.map((event, idx) => (
                      <TableRow key={idx}>
                        <TableCell className="font-medium">{event.employee_name}</TableCell>
                        <TableCell>{event.venue_name}</TableCell>
                        <TableCell>
                          <Badge className={`${EVENT_TYPE_COLORS[event.event_type]} text-white`}>
                            {event.event_type}
                          </Badge>
                        </TableCell>
                        <TableCell>{format(parseISO(event.date), 'MMM d, h:mm a')}</TableCell>
                        <TableCell className="text-right">
                          ${event.base_pay ? event.base_pay.toFixed(2) : '0.00'}
                        </TableCell>
                        <TableCell className="text-right">
                          {event.bonuses > 0 ? (
                            <div className="flex flex-col items-end">
                              <span className="font-semibold text-green-600">+${event.bonuses}</span>
                              {event.bonus_details && event.bonus_details.length > 0 && (
                                <span className="text-xs text-gray-400">
                                  {event.bonus_details.join(', ')}
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right font-semibold">
                          <div className="flex flex-col items-end space-y-1">
                            <span>{event.total_pay ? `$${event.total_pay.toFixed(2)}` : 'N/A'}</span>
                            {event.venue_pays_host_directly && (
                              <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-300">
                                Venue Pays Directly
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setSelectedPayment(event);
                              setDetailDialogOpen(true);
                            }}
                            className="hover:bg-blue-50"
                          >
                            <Eye className="h-4 w-4 mr-1" />
                            Details
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          ) : (
            <div className="text-center py-12 text-gray-400">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No events found for this week</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Payment Detail Dialog */}
      {selectedPayment && (
        <PaymentDetailDialog
          open={detailDialogOpen}
          onOpenChange={setDetailDialogOpen}
          payment={selectedPayment}
          onAcknowledge={fetchReport}
        />
      )}
    </div>
  );
};

const Label = ({ children, className = '' }) => (
  <label className={`text-sm font-medium ${className}`}>{children}</label>
);

export default WeeklyReport;
