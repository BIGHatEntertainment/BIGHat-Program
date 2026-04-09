import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Lock, AlertCircle, Eye, EyeOff, Info } from 'lucide-react';
import { Button } from '../ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const PasswordConfirmDialog = ({ open, onOpenChange, employeeId, employeeName, action, onConfirm }) => {
  const [password, setPassword] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [isDefaultPassword, setIsDefaultPassword] = useState(false);
  const [defaultPassword, setDefaultPassword] = useState(null);
  const [checkingDefault, setCheckingDefault] = useState(false);

  // Check if user has default password when dialog opens
  useEffect(() => {
    const checkDefaultPassword = async () => {
      if (open && employeeId) {
        setCheckingDefault(true);
        try {
          const response = await axios.get(`${API}/host/password/is-default/${employeeId}`);
          setIsDefaultPassword(response.data.is_default);
          setDefaultPassword(response.data.default_password);
        } catch (error) {
          console.error('Error checking default password:', error);
          setIsDefaultPassword(false);
          setDefaultPassword(null);
        } finally {
          setCheckingDefault(false);
        }
      }
    };

    checkDefaultPassword();
  }, [open, employeeId]);

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setPassword('');
      setShowPassword(false);
    }
  }, [open]);

  const handleVerify = async () => {
    if (!password) {
      toast.error('Please enter your password');
      return;
    }

    setVerifying(true);
    try {
      await axios.post(`${API}/host/password/verify`, {
        employee_id: employeeId,
        password: password
      });

      // Password verified, proceed with action
      onConfirm();
      setPassword('');
      onOpenChange(false);
    } catch (error) {
      console.error('Password verification error:', error);
      toast.error('Invalid password');
      setPassword('');
    } finally {
      setVerifying(false);
    }
  };

  const handleUseDefaultPassword = () => {
    if (defaultPassword) {
      setPassword(defaultPassword);
      setShowPassword(true);
    }
  };

  const handleClose = () => {
    setPassword('');
    setShowPassword(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[425px]" style={{ backgroundColor: '#0d1220', border: '1px solid rgba(251, 221, 104, 0.2)' }}>
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <Lock className="h-5 w-5 text-primary" />
            <span>Confirm Password</span>
          </DialogTitle>
          <DialogDescription>
            Enter your password to {action} this event
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start space-x-3">
            <AlertCircle className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-blue-900">
              <p className="font-medium mb-1">Security Check</p>
              <p>Please confirm it&apos;s really you, {employeeName}.</p>
            </div>
          </div>

          {/* Show default password hint if user hasn't changed their password */}
          {!checkingDefault && isDefaultPassword && defaultPassword && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start space-x-3">
              <Info className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-amber-900">
                <p className="font-medium mb-1">Using Default Password</p>
                <p className="mb-2">You haven&apos;t set a custom password yet. Your default password is:</p>
                <div className="flex items-center space-x-2">
                  <code className="bg-amber-100 px-2 py-1 rounded font-mono text-amber-800 font-bold">
                    {defaultPassword}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleUseDefaultPassword}
                    className="text-xs h-7 border-amber-300 hover:bg-amber-100"
                  >
                    Use This
                  </Button>
                </div>
                <p className="mt-2 text-xs text-amber-700">
                  Tip: You can change your password after logging in.
                </p>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="confirm-password">Password</Label>
            <div className="relative">
              <Input
                id="confirm-password"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleVerify();
                  }
                }}
                autoFocus
                className="border-2 pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleClose}
          >
            Cancel
          </Button>
          <Button
            onClick={handleVerify}
            disabled={verifying || !password || checkingDefault}
            className="bg-blue-500 hover:bg-blue-600 text-white"
          >
            {verifying ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Verifying...
              </>
            ) : checkingDefault ? (
              'Loading...'
            ) : (
              'Confirm'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PasswordConfirmDialog;
