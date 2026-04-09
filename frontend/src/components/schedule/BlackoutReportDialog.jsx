import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, parseISO } from 'date-fns';
import { Ban, User, Calendar, X } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const BlackoutReportDialog = ({ open, onOpenChange, month }) => {
  const [blackouts, setBlackouts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [groupedBlackouts, setGroupedBlackouts] = useState({});

  useEffect(() => {
    if (open && month) {
      fetchBlackouts();
    }
  }, [open, month]);

  const fetchBlackouts = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/blackouts/month/${month}`);
      setBlackouts(response.data);
      
      // Group blackouts by employee
      const grouped = response.data.reduce((acc, blackout) => {
        const empName = blackout.employee_name || 'Unknown';
        if (!acc[empName]) {
          acc[empName] = [];
        }
        acc[empName].push(blackout);
        return acc;
      }, {});
      
      setGroupedBlackouts(grouped);
    } catch (error) {
      console.error('Error fetching blackouts:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatMonthDisplay = () => {
    if (!month) return '';
    try {
      const [year, monthNum] = month.split('-');
      const date = new Date(parseInt(year), parseInt(monthNum) - 1, 1);
      return format(date, 'MMMM yyyy');
    } catch {
      return month;
    }
  };

  const employeeCount = Object.keys(groupedBlackouts).length;
  const totalBlackouts = blackouts.length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent style={{ backgroundColor: "#0d1220", border: "1px solid rgba(251, 221, 104, 0.2)" }} className="sm:max-w-[600px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <Ban className="h-5 w-5 text-red-600" />
            <span>Blackout Report - {formatMonthDisplay()}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="py-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-800"></div>
            </div>
          ) : blackouts.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <Calendar className="h-12 w-12 mx-auto mb-3 text-gray-300" />
              <p>No blackout dates for {formatMonthDisplay()}</p>
            </div>
          ) : (
            <>
              {/* Summary */}
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4">
                <div className="grid grid-cols-2 gap-4 text-center">
                  <div>
                    <div className="text-2xl font-bold text-gray-800">{employeeCount}</div>
                    <div className="text-sm text-gray-500">
                      {employeeCount === 1 ? 'Employee' : 'Employees'} with Blackouts
                    </div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-red-600">{totalBlackouts}</div>
                    <div className="text-sm text-gray-500">
                      Total Blackout {totalBlackouts === 1 ? 'Period' : 'Periods'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Grouped by Employee */}
              <div className="space-y-4">
                {Object.entries(groupedBlackouts)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([employeeName, employeeBlackouts]) => (
                    <div
                      key={employeeName}
                      className="border border-gray-200 rounded-lg overflow-hidden"
                    >
                      {/* Employee Header */}
                      <div className="bg-gray-100 px-4 py-2 flex items-center space-x-2">
                        <User className="h-4 w-4 text-gray-600" />
                        <span className="font-medium">{employeeName}</span>
                        <span className="text-sm text-gray-500">
                          ({employeeBlackouts.length} {employeeBlackouts.length === 1 ? 'period' : 'periods'})
                        </span>
                      </div>
                      
                      {/* Blackout Dates */}
                      <div className="divide-y divide-gray-100">
                        {employeeBlackouts
                          .sort((a, b) => a.start_date.localeCompare(b.start_date))
                          .map((blackout, index) => (
                            <div
                              key={blackout.id || index}
                              className="px-4 py-3 flex items-center justify-between bg-[#111827] hover:bg-gray-50"
                            >
                              <div className="flex items-center space-x-3">
                                <Ban className="h-4 w-4 text-red-500" />
                                <div>
                                  <div className="font-medium text-gray-800">
                                    {format(parseISO(blackout.start_date), 'MMM d, yyyy')}
                                    <span className="mx-2 text-gray-400">→</span>
                                    {format(parseISO(blackout.end_date), 'MMM d, yyyy')}
                                  </div>
                                  <div className="text-sm text-gray-500">
                                    {calculateDays(blackout.start_date, blackout.end_date)} days
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                      </div>
                    </div>
                  ))}
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// Helper function to calculate days between dates
const calculateDays = (startDate, endDate) => {
  const start = parseISO(startDate);
  const end = parseISO(endDate);
  const diffTime = Math.abs(end - start);
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
  return diffDays;
};

export default BlackoutReportDialog;
