import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Eye, EyeOff } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { toast } from 'sonner';
import { accountsApi } from '../../services/sponsorApi';
import { useData } from '../../context/SponsorContext';
import PasswordResetModal from '../../components/sponsor/PasswordResetModal';
import ProfileVerificationModal from '../../components/sponsor/ProfileVerificationModal';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const Login = ({ onLogin }) => {
  const navigate = useNavigate();
  const { initializeUserProfile } = useData();
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showPasswordReset, setShowPasswordReset] = useState(false);
  const [showProfileVerification, setShowProfileVerification] = useState(false);
  const [pendingLoginEmail, setPendingLoginEmail] = useState('');
  const [pendingAccountData, setPendingAccountData] = useState(null);

  const handleGoogleLogin = () => {
    // Emergent Auth - redirect to Google OAuth
    // After auth, user will be redirected back with session_id in hash
    const redirectUrl = window.location.origin + '/';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    const formData = new FormData(e.target);
    const email = formData.get('email')?.trim().toLowerCase();
    const password = formData.get('password');
    
    try {
      // Special case: admin@bighat.live login (hardcoded for demo)
      if (email === 'admin@bighat.live') {
        // Admin login - check password
        if (password !== 'JeffersonCity11!!') {
          toast.error('Invalid admin credentials');
          setLoading(false);
          return;
        }
        
        const user = {
          id: 'admin_001',
          email: email,
          name: 'Nicholas Sellards',
          picture: 'https://api.dicebear.com/7.x/initials/svg?seed=NS&backgroundColor=f4d03f&textColor=1a1a2e',
          role: 'admin',
          businessName: 'BIG Hat Entertainment'
        };
        
        toast.success('Welcome back, Admin!');
        onLogin(user);
        navigate('/admin');
        setLoading(false);
        return;
      }
      
      // Regular user login via API
      const account = await accountsApi.login(email, password);
      
      // Check if password reset is required
      if (account.must_reset_password) {
        setPendingLoginEmail(email);
        setPendingAccountData(account); // Store account data for profile verification
        setShowPasswordReset(true);
        setLoading(false);
        return;
      }
      
      // Successful login
      // Determine venue sponsor status - ONLY from explicit flag, NOT from tier
      // Venue sponsor status must be explicitly assigned by admin
      const isVenueSponsor = account.is_venue_sponsor === true;
      
      const user = {
        id: account.id,
        email: account.email,
        name: account.contact_name || account.business_name || email.split('@')[0],
        picture: account.picture || `https://api.dicebear.com/7.x/initials/svg?seed=${account.contact_name || 'User'}`,
        role: 'sponsor',
        businessName: account.business_name,
        phone: account.phone,
        website: account.website,
        // Include ALL sponsor data for tier access - these are critical
        sponsorTier: account.sponsor_tier,
        sponsorPackage: account.sponsor_package,
        sponsorId: account.sponsor_id,
        isVenueSponsor: isVenueSponsor,
      };
      
      // CRITICAL: Update DataContext's userProfile so subscription logic works correctly
      initializeUserProfile(user);
      
      toast.success('Login successful!');
      onLogin(user);
      navigate('/dashboard');
      
    } catch (err) {
      console.error('Login error:', err);
      toast.error(err.message || 'Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordResetSuccess = () => {
    setShowPasswordReset(false);
    // Show profile verification modal for admin-created accounts
    setShowProfileVerification(true);
  };

  const handleProfileVerificationComplete = (profileData) => {
    setShowProfileVerification(false);
    
    // Venue sponsor status - ONLY from explicit flag, never from tier
    const isVenueSponsor = pendingAccountData?.is_venue_sponsor === true;
    
    // Create user object and log them in
    // MERGE profile form data with ALL sponsor data from pending account - don't lose sponsor fields!
    const user = {
      id: pendingAccountData?.id || `user_${Date.now()}`,
      email: pendingLoginEmail,
      name: profileData.contactName || profileData.businessName,
      picture: pendingAccountData?.picture || `https://api.dicebear.com/7.x/initials/svg?seed=${profileData.contactName || 'User'}`,
      role: 'sponsor',
      // Profile form data
      businessName: profileData.businessName,
      phone: profileData.phone,
      website: profileData.website,
      // Sponsor data - only set if they actually have a subscription
      sponsorTier: pendingAccountData?.sponsor_tier || null,
      sponsorPackage: pendingAccountData?.sponsor_package || null,
      sponsorId: pendingAccountData?.sponsor_id || null,
      isVenueSponsor: isVenueSponsor,
    };
    
    // CRITICAL: Update DataContext's userProfile so subscription logic works correctly
    initializeUserProfile(user);
    
    onLogin(user);
    navigate('/dashboard');
    setPendingLoginEmail('');
    setPendingAccountData(null);
  };

  const handleProfileVerificationSkip = () => {
    setShowProfileVerification(false);
    toast.info('You can complete your profile later in Settings.');
    
    // Venue sponsor status - ONLY from explicit flag, never from tier
    const isVenueSponsor = pendingAccountData?.is_venue_sponsor === true;
    
    // Still log them in - but INCLUDE ALL sponsor data, don't strip it!
    const user = {
      id: pendingAccountData?.id || `user_${Date.now()}`,
      email: pendingLoginEmail,
      name: pendingAccountData?.contact_name || pendingLoginEmail.split('@')[0],
      picture: pendingAccountData?.picture || `https://api.dicebear.com/7.x/initials/svg?seed=${pendingAccountData?.contact_name || 'User'}`,
      role: 'sponsor',
      businessName: pendingAccountData?.business_name,
      phone: pendingAccountData?.phone,
      website: pendingAccountData?.website,
      // Sponsor data - only set if they actually have a subscription
      sponsorTier: pendingAccountData?.sponsor_tier || null,
      sponsorPackage: pendingAccountData?.sponsor_package || null,
      sponsorId: pendingAccountData?.sponsor_id || null,
      isVenueSponsor: isVenueSponsor,
    };
    
    // CRITICAL: Update DataContext's userProfile so subscription logic works correctly
    initializeUserProfile(user);
    
    onLogin(user);
    navigate('/dashboard');
    setPendingLoginEmail('');
    setPendingAccountData(null);
  };

  return (
    <div className="min-h-screen flex items-center justify-center pt-20 pb-12 px-4">
      <div className="w-full max-w-md">
        <div className="card-dark rounded-2xl p-8">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-gradient-to-br from-[#f4d03f] to-[#d4ac0d] rounded-2xl flex items-center justify-center mx-auto mb-4">
              <span className="text-[#1a1a2e] font-black text-2xl">BH</span>
            </div>
            <h1 className="text-2xl font-bold text-white">Welcome Back</h1>
            <p className="text-white/60 mt-2">Sign in to your sponsor account</p>
          </div>

          {/* Google Login */}
          <Button
            type="button"
            variant="outline"
            onClick={handleGoogleLogin}
            className="w-full h-12 bg-white hover:bg-gray-100 text-gray-800 border-0 mb-6"
          >
            <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Continue with Google
          </Button>

          {/* Divider */}
          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-[#f4d03f]/10" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-4 bg-[#1a1a2e] text-white/40">or continue with email</span>
            </div>
          </div>

          {/* Email Login Form */}
          <form onSubmit={handleEmailLogin} className="space-y-4">
            <div>
              <Label htmlFor="email" className="text-white/80">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                placeholder="your@email.com"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30 focus:border-[#f4d03f] focus:ring-[#f4d03f]/20"
                required
              />
            </div>
            <div>
              <Label htmlFor="password" className="text-white/80">Password</Label>
              <div className="relative mt-1.5">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="••••••••"
                  className="bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30 focus:border-[#f4d03f] focus:ring-[#f4d03f]/20 pr-10"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/60"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full btn-gold h-12"
            >
              {loading ? 'Signing in...' : 'Sign In'}
              <ArrowRight className="ml-2" size={18} />
            </Button>
          </form>

          {/* Footer Links */}
          <div className="mt-6 text-center space-y-2">
            <button className="text-[#f4d03f]/80 hover:text-[#f4d03f] text-sm">
              Forgot password?
            </button>
            <p className="text-white/40 text-sm">
              Don&apos;t have an account?{' '}
              <button
                onClick={() => navigate('/signup')}
                className="text-[#f4d03f] hover:underline"
              >
                Become a Sponsor
              </button>
            </p>
          </div>
        </div>
      </div>

      {/* Password Reset Modal */}
      <PasswordResetModal
        isOpen={showPasswordReset}
        email={pendingLoginEmail}
        onSuccess={handlePasswordResetSuccess}
        onCancel={() => {
          setShowPasswordReset(false);
          setPendingLoginEmail('');
          setPendingAccountData(null);
        }}
      />

      {/* Profile Verification Modal */}
      <ProfileVerificationModal
        isOpen={showProfileVerification}
        email={pendingLoginEmail}
        initialData={pendingAccountData}
        onComplete={handleProfileVerificationComplete}
        onSkip={handleProfileVerificationSkip}
      />
    </div>
  );
};

export default Login;
