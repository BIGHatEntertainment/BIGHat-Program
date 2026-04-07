import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Building2, User as UserIcon, Mail, Phone, Globe, Lock, Eye, EyeOff, MapPin } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { useData } from '../context/DataContext';

const Signup = ({ onLogin }) => {
  const navigate = useNavigate();
  const { initializeUserProfile, registerAccount } = useData();
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    businessName: '',
    contactName: '',
    email: '',
    phone: '',
    website: '',
    zipCode: '',
    password: '',
  });

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleGoogleSignup = () => {
    // Redirect to Emergent Auth - will redirect back with session_id
    const redirectUrl = window.location.origin + '/dashboard';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const uniqueId = `user_${Date.now()}`;
      
      // Create user profile
      const userData = {
        id: uniqueId,
        email: formData.email,
        name: formData.contactName,
        picture: `https://api.dicebear.com/7.x/initials/svg?seed=${formData.contactName}`,
        businessName: formData.businessName,
        phone: formData.phone,
        website: formData.website,
      };

      // Initialize profile in context
      initializeUserProfile(userData);
      
      // Register the account in backend for admin visibility in "Link Existing Account" dropdown
      // Note: We do NOT add to sponsors list automatically - admin must manually link
      await registerAccount({
        id: uniqueId,
        businessName: formData.businessName,
        email: formData.email,
        contactName: formData.contactName,
        phone: formData.phone,
        website: formData.website,
        zipCode: formData.zipCode,
        password: formData.password
      });
      
      // Set user in app state
      onLogin(userData);
      
      toast.success('Account created! Welcome to your dashboard.');
      
      // Navigate directly to dashboard
      navigate('/dashboard');
    } catch (err) {
      console.error('Signup error:', err);
      toast.error(err.message || 'Failed to create account. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = formData.businessName && formData.contactName && formData.email && formData.password && formData.zipCode;

  return (
    <div className="min-h-screen flex items-center justify-center pt-24 pb-12 px-4">
      <div className="w-full max-w-lg">
        <div className="card-dark rounded-2xl p-8">
          <div className="text-center mb-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#f4d03f] to-[#d4ac0d] flex items-center justify-center mx-auto mb-4">
              <span className="text-[#1a1a2e] font-bold text-2xl">BH</span>
            </div>
            <h2 className="text-2xl font-bold text-white">Create Your Account</h2>
            <p className="text-white/60 mt-2">Join BIG Hat Entertainment as a sponsor</p>
          </div>

          {/* Google Signup Option */}
          <Button
            type="button"
            variant="outline"
            onClick={handleGoogleSignup}
            className="w-full h-12 bg-white hover:bg-gray-100 text-gray-800 border-0 mb-6"
          >
            <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Continue with Google
          </Button>

          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-[#f4d03f]/10" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-4 bg-[#1a1a2e] text-white/40">or create with email</span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80 flex items-center gap-2">
                  <Building2 size={14} /> Business Name *
                </Label>
                <Input
                  value={formData.businessName}
                  onChange={(e) => handleChange('businessName', e.target.value)}
                  placeholder="Your Business LLC"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                  required
                />
              </div>
              <div>
                <Label className="text-white/80 flex items-center gap-2">
                  <UserIcon size={14} /> Contact Name *
                </Label>
                <Input
                  value={formData.contactName}
                  onChange={(e) => handleChange('contactName', e.target.value)}
                  placeholder="John Smith"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                  required
                />
              </div>
            </div>

            <div>
              <Label className="text-white/80 flex items-center gap-2">
                <Mail size={14} /> Email *
              </Label>
              <Input
                type="email"
                value={formData.email}
                onChange={(e) => handleChange('email', e.target.value)}
                placeholder="sponsor@business.com"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                required
              />
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <Label className="text-white/80 flex items-center gap-2">
                  <Phone size={14} /> Phone
                </Label>
                <Input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => handleChange('phone', e.target.value)}
                  placeholder="(602) 555-1234"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                />
              </div>
              <div>
                <Label className="text-white/80 flex items-center gap-2">
                  <MapPin size={14} /> Zip Code *
                </Label>
                <Input
                  value={formData.zipCode}
                  onChange={(e) => handleChange('zipCode', e.target.value.replace(/[^\d-]/g, '').slice(0, 10))}
                  placeholder="Enter zip code"
                  className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
                  required
                />
              </div>
            </div>

            <div>
              <Label className="text-white/80 flex items-center gap-2">
                <Globe size={14} /> Website
              </Label>
              <Input
                type="url"
                value={formData.website}
                onChange={(e) => handleChange('website', e.target.value)}
                placeholder="https://yourbusiness.com"
                className="mt-1.5 bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30"
              />
            </div>

            <div>
              <Label className="text-white/80 flex items-center gap-2">
                <Lock size={14} /> Password *
              </Label>
              <div className="relative mt-1.5">
                <Input
                  type={showPassword ? 'text' : 'password'}
                  value={formData.password}
                  onChange={(e) => handleChange('password', e.target.value)}
                  placeholder="Create a secure password"
                  className="bg-white/5 border-[#f4d03f]/20 text-white placeholder:text-white/30 pr-10"
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
              disabled={!canSubmit || loading}
              className="w-full btn-gold h-12 mt-6"
            >
              {loading ? 'Creating Account...' : 'Create Account'}
              <ArrowRight className="ml-2" size={18} />
            </Button>
          </form>

          {/* Login Link */}
          <p className="text-center text-white/40 text-sm mt-6">
            Already have an account?{' '}
            <button
              onClick={() => navigate('/login')}
              className="text-[#f4d03f] hover:underline"
            >
              Sign in
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Signup;
