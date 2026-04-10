import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Lock, ArrowLeft } from 'lucide-react';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const AdminAuth = ({ onSuccess }) => {
  const navigate = useNavigate();
  const [passcode, setPasscode] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!passcode) {
      toast.error('Please enter the admin passcode');
      return;
    }

    setLoading(true);
    try {
      await axios.post(`${API}/admin/verify`, { passcode });
      onSuccess();
    } catch (error) {
      console.error('Auth error:', error);
      toast.error('Invalid passcode');
      setPasscode('');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen gradient-hero flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <Button
          onClick={() => navigate('/')}
          variant="ghost"
          className="mb-4 hover:bg-white/50"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Schedule
        </Button>
        
        <Card className="shadow-xl border-2">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4">
              <img 
                src="/assets/hat-logo.png" 
                alt="BIG Hat Entertainment" 
                className="w-24 h-24 mx-auto object-contain"
              />
            </div>
            <CardTitle className="text-2xl">Admin Access</CardTitle>
            <CardDescription>
              Enter the admin passcode to continue
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="passcode">Passcode</Label>
                <Input
                  id="passcode"
                  type="password"
                  placeholder="Enter admin passcode"
                  value={passcode}
                  onChange={(e) => setPasscode(e.target.value)}
                  className="text-center text-lg tracking-widest"
                  autoFocus
                />
              </div>
              <Button
                type="submit"
                className="w-full bg-blue-500 hover:bg-blue-600 text-white transition-smooth"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                    Verifying...
                  </>
                ) : (
                  'Access Admin Panel'
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default AdminAuth;
