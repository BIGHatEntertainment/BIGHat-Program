import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { Button } from '../components/ui/button';
import { accountDeletionApi } from '../services/api';

const ConfirmDeletion = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');
  
  const [status, setStatus] = useState('loading'); // loading, confirming, success, error, expired
  const [error, setError] = useState('');
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    // Validate the token on mount
    const validateToken = async () => {
      if (!token) {
        setStatus('error');
        setError('Invalid deletion link. No token provided.');
        return;
      }
      
      try {
        const result = await accountDeletionApi.getDeletionStatus(token);
        if (result.status === 'pending') {
          setStatus('confirming');
        } else if (result.status === 'completed') {
          setStatus('success');
        } else if (result.status === 'expired') {
          setStatus('expired');
        } else {
          setStatus('error');
          setError('Invalid deletion request.');
        }
      } catch (err) {
        setStatus('error');
        setError('Invalid or expired deletion link.');
      }
    };
    
    validateToken();
  }, [token]);

  const handleConfirmDeletion = async () => {
    setProcessing(true);
    try {
      const result = await accountDeletionApi.confirmDeletion(token);
      if (result.success) {
        setStatus('success');
      }
    } catch (err) {
      setStatus('error');
      setError(err.detail || 'Failed to delete account. Please try again or contact support.');
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#1a1a2e] via-[#16213e] to-[#0f0f1a] flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-[#f4d03f]">BIG Hat Entertainment</h1>
          <p className="text-white/60 mt-1">Sponsor Portal</p>
        </div>

        <div className="card-dark rounded-2xl p-8">
          {status === 'loading' && (
            <div className="text-center space-y-4">
              <Loader2 className="w-12 h-12 text-[#f4d03f] animate-spin mx-auto" />
              <p className="text-white">Validating deletion request...</p>
            </div>
          )}

          {status === 'confirming' && (
            <div className="text-center space-y-6">
              <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto">
                <AlertTriangle className="w-8 h-8 text-red-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white mb-2">Confirm Account Deletion</h2>
                <p className="text-white/70 text-sm">
                  You are about to permanently delete your account. This action cannot be undone.
                </p>
              </div>
              
              <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 text-left">
                <p className="text-red-400 text-sm font-medium mb-2">This will:</p>
                <ul className="text-white/60 text-sm space-y-1">
                  <li>• Cancel any active subscriptions</li>
                  <li>• Delete all your uploaded assets</li>
                  <li>• Remove your sponsor profile</li>
                  <li>• Permanently delete your account</li>
                </ul>
              </div>

              <div className="flex gap-3">
                <Button
                  variant="outline"
                  className="flex-1 border-white/20 text-white hover:bg-white/10"
                  onClick={() => navigate('/login')}
                >
                  Cancel
                </Button>
                <Button
                  className="flex-1 bg-red-500 hover:bg-red-600 text-white"
                  onClick={handleConfirmDeletion}
                  disabled={processing}
                >
                  {processing ? (
                    <>
                      <Loader2 size={16} className="mr-2 animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    'Delete My Account'
                  )}
                </Button>
              </div>
            </div>
          )}

          {status === 'success' && (
            <div className="text-center space-y-6">
              <div className="w-16 h-16 bg-green-500/20 rounded-full flex items-center justify-center mx-auto">
                <CheckCircle className="w-8 h-8 text-green-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white mb-2">Account Deleted</h2>
                <p className="text-white/70 text-sm">
                  Your account has been successfully deleted. Any active subscriptions have been cancelled.
                </p>
              </div>
              <p className="text-white/50 text-sm">
                Thank you for being a BIG Hat sponsor. We hope to see you again!
              </p>
              <Button
                className="btn-gold w-full"
                onClick={() => navigate('/')}
              >
                Return to Home
              </Button>
            </div>
          )}

          {status === 'expired' && (
            <div className="text-center space-y-6">
              <div className="w-16 h-16 bg-orange-500/20 rounded-full flex items-center justify-center mx-auto">
                <AlertTriangle className="w-8 h-8 text-orange-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white mb-2">Link Expired</h2>
                <p className="text-white/70 text-sm">
                  This deletion link has expired. For security, deletion links are only valid for 24 hours.
                </p>
              </div>
              <p className="text-white/50 text-sm">
                If you still want to delete your account, please log in and request deletion again.
              </p>
              <Button
                className="btn-gold w-full"
                onClick={() => navigate('/login')}
              >
                Go to Login
              </Button>
            </div>
          )}

          {status === 'error' && (
            <div className="text-center space-y-6">
              <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto">
                <XCircle className="w-8 h-8 text-red-400" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-white mb-2">Something Went Wrong</h2>
                <p className="text-white/70 text-sm">{error}</p>
              </div>
              <Button
                className="btn-gold w-full"
                onClick={() => navigate('/login')}
              >
                Go to Login
              </Button>
            </div>
          )}
        </div>

        <p className="text-white/40 text-xs text-center mt-6">
          Need help? Contact support@bighat.live
        </p>
      </div>
    </div>
  );
};

export default ConfirmDeletion;
