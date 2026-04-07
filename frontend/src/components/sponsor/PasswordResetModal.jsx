import React, { useState } from 'react';
import { Lock, Eye, EyeOff, AlertCircle, CheckCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../ui/dialog';
import { toast } from 'sonner';
import { accountsApi } from '../../services/sponsorApi';

const PasswordResetModal = ({ isOpen, email, onSuccess, onCancel }) => {
  const [currentPassword, setCurrentPassword] = useState('B1GHat');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Password validation
  const passwordRequirements = [
    { label: 'At least 8 characters', valid: newPassword.length >= 8 },
    { label: 'Different from default password', valid: newPassword !== 'B1GHat' && newPassword.length > 0 },
    { label: 'Passwords match', valid: newPassword === confirmPassword && newPassword.length > 0 },
  ];

  const isValid = passwordRequirements.every(req => req.valid);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!isValid) {
      setError('Please meet all password requirements');
      return;
    }

    setLoading(true);
    try {
      await accountsApi.resetPassword(email, currentPassword, newPassword);
      toast.success('Password updated successfully! You can now log in.');
      onSuccess();
    } catch (err) {
      console.error('Password reset failed:', err);
      setError(err.message || 'Failed to reset password. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={() => {}}>
      <DialogContent className="bg-[#1a1a2e] border-[#f4d03f]/20 max-w-md" hideCloseButton>
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <Lock className="w-5 h-5 text-[#f4d03f]" />
            Create Your Password
          </DialogTitle>
          <DialogDescription className="text-white/60">
            Your account was created by an administrator. Please create a secure password to continue.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Current Password (hidden by default since it's the default) */}
          <div className="space-y-2">
            <Label className="text-white">Current Password</Label>
            <div className="relative">
              <Input
                type={showCurrentPassword ? 'text' : 'password'}
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="bg-white/5 border-white/10 text-white pr-10"
                placeholder="Enter current password"
              />
              <button
                type="button"
                onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
              >
                {showCurrentPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            <p className="text-white/40 text-xs">Your temporary password is "B1GHat"</p>
          </div>

          {/* New Password */}
          <div className="space-y-2">
            <Label className="text-white">New Password</Label>
            <div className="relative">
              <Input
                type={showNewPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="bg-white/5 border-white/10 text-white pr-10"
                placeholder="Create a secure password"
              />
              <button
                type="button"
                onClick={() => setShowNewPassword(!showNewPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
              >
                {showNewPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Confirm Password */}
          <div className="space-y-2">
            <Label className="text-white">Confirm New Password</Label>
            <div className="relative">
              <Input
                type={showConfirmPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="bg-white/5 border-white/10 text-white pr-10"
                placeholder="Confirm your password"
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
              >
                {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          {/* Password Requirements */}
          <div className="bg-white/5 rounded-lg p-3 space-y-2">
            <p className="text-white/60 text-xs font-medium">Password Requirements:</p>
            {passwordRequirements.map((req, index) => (
              <div key={index} className="flex items-center gap-2">
                {req.valid ? (
                  <CheckCircle size={14} className="text-green-400" />
                ) : (
                  <AlertCircle size={14} className="text-white/30" />
                )}
                <span className={`text-xs ${req.valid ? 'text-green-400' : 'text-white/50'}`}>
                  {req.label}
                </span>
              </div>
            ))}
          </div>

          {/* Error Message */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
              <p className="text-red-400 text-sm flex items-center gap-2">
                <AlertCircle size={16} />
                {error}
              </p>
            </div>
          )}

          <DialogFooter className="gap-2">
            {onCancel && (
              <Button
                type="button"
                variant="ghost"
                onClick={onCancel}
                className="text-white/60 hover:text-white"
                disabled={loading}
              >
                Cancel
              </Button>
            )}
            <Button
              type="submit"
              disabled={!isValid || loading}
              className="btn-gold"
            >
              {loading ? 'Updating...' : 'Set Password'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default PasswordResetModal;
