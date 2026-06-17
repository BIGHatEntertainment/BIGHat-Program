import React, { useState } from 'react';
import axios from 'axios';
import { User, Lock, LogIn } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const HostLogin = ({ employees, onLoginSuccess }) => {
  const [selectedEmployee, setSelectedEmployee] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPasswordChange, setShowPasswordChange] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [loggedInEmployee, setLoggedInEmployee] = useState(null);

  const handleGoogleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    
    if (!selectedEmployee) {
      toast.error('Please select your name');
      return;
    }

    if (!password) {
      toast.error('Please enter your password');
      return;
    }

    setLoading(true);
    try {
      const employee = employees.find(e => e.id === selectedEmployee);
      const response = await axios.post(`${API}/host/login`, {
        name: employee.name,
        password: password
      });

      // Store login info in sessionStorage
      sessionStorage.setItem('loggedInHost', JSON.stringify(response.data.employee));
      
      setLoggedInEmployee(response.data.employee);
      
      // Server tells us whether the host is still on the default password —
      // we don't compare against a baked-in literal (v31.0.10 leak fix).
      if (response.data?.is_default_password) {
        toast.success('Login successful!');
        setShowPasswordChange(true);
      } else {
        toast.success(`Welcome back, ${response.data.employee.name}!`);
        onLoginSuccess(response.data.employee);
      }
    } catch (error) {
      console.error('Login error:', error);
      toast.error(error.response?.data?.detail || 'Invalid password');
      setPassword('');
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordChange = async () => {
    if (!newPassword) {
      toast.error('Please enter a new password');
      return;
    }

    try {
      await axios.post(`${API}/host/password/change`, {
        employee_id: loggedInEmployee.id,
        current_password: password,
        new_password: newPassword
      });

      toast.success('Password changed successfully!');
      setShowPasswordChange(false);
      onLoginSuccess(loggedInEmployee);
    } catch (error) {
      console.error('Password change error:', error);
      toast.error('Failed to change password');
    }
  };

  const handleSkipPasswordChange = () => {
    setShowPasswordChange(false);
    onLoginSuccess(loggedInEmployee);
  };

  return (
    <>
      <div className="min-h-screen gradient-hero flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <Card className="shadow-xl border-2">
            <CardHeader className="text-center">
              <div className="mx-auto mb-4">
                <img 
                  src="/assets/hat-logo.png" 
                  alt="BIG Hat Entertainment" 
                  className="w-24 h-24 mx-auto object-contain"
                />
              </div>
              <CardTitle className="text-2xl">Host Login</CardTitle>
              <CardDescription>
                Sign in to claim and manage your events
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {/* Google OAuth Login - Primary */}
                <div>
                  <Button
                    onClick={handleGoogleLogin}
                    className="w-full bg-white hover:bg-gray-50 text-gray-700 border-2 border-gray-300 font-semibold py-6 text-lg shadow-md"
                    type="button"
                  >
                    <svg className="w-6 h-6 mr-3" viewBox="0 0 24 24">
                      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                    </svg>
                    Sign in with Google
                  </Button>
                  <p className="text-xs text-center text-muted-foreground mt-2">
                    Secure login using your Google account
                  </p>
                </div>

                {/* Divider */}
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t border-gray-300" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-card px-2 text-muted-foreground">Or use password</span>
                  </div>
                </div>

                {/* Password Login - Fallback */}
                <form onSubmit={handleLogin} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="employee">Select Your Name</Label>
                    <Select
                      value={selectedEmployee || ''}
                      onValueChange={setSelectedEmployee}
                    >
                      <SelectTrigger id="employee" className="h-12 border-2">
                        <SelectValue placeholder="Select your name..." />
                      </SelectTrigger>
                      <SelectContent>
                        {employees.map(emp => (
                          <SelectItem key={emp.id} value={emp.id}>
                            {emp.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter your password"
                      className="h-12 border-2"
                      required
                    />
                  </div>

                  <Button
                    type="submit"
                    className="w-full bg-primary hover:bg-primary/90 py-6 text-lg font-semibold"
                    disabled={!selectedEmployee || !password}
                  >
                    <LogIn className="mr-2 h-5 w-5" />
                    Sign In with Password
                  </Button>
                </form>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Password Change Dialog */}
      <Dialog open={showPasswordChange} onOpenChange={setShowPasswordChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change Your Password?</DialogTitle>
            <DialogDescription>
              You&apos;re currently using the default password. Would you like to set a personal password?
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="new-password">New Password</Label>
              <Input
                id="new-password"
                type="password"
                placeholder="Enter new password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Optional - You can keep using the default password if you prefer
              </p>
            </div>
          </div>
          <DialogFooter className="flex space-x-2">
            <Button
              variant="outline"
              onClick={handleSkipPasswordChange}
            >
              Skip for Now
            </Button>
            <Button
              onClick={handlePasswordChange}
              className="bg-blue-500 hover:bg-blue-600 text-white"
              disabled={!newPassword}
            >
              Change Password
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default HostLogin;
