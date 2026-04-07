import React from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Check, Image, Package, CreditCard } from 'lucide-react';

const OnboardingLayout = ({ user }) => {
  const location = useLocation();
  const navigate = useNavigate();

  const steps = [
    { id: 'assets', label: 'Upload Assets', icon: Image, path: '/onboarding/assets' },
    { id: 'packages', label: 'Choose Package', icon: Package, path: '/onboarding/packages' },
    { id: 'checkout', label: 'Checkout', icon: CreditCard, path: '/onboarding/checkout' },
  ];

  const getCurrentStepIndex = () => {
    const path = location.pathname;
    if (path.includes('assets')) return 0;
    if (path.includes('packages')) return 1;
    if (path.includes('checkout')) return 2;
    return 0;
  };

  const currentStep = getCurrentStepIndex();

  return (
    <div className="min-h-screen bg-[#0f0f1a] pt-8 pb-12">
      {/* Header */}
      <div className="max-w-4xl mx-auto px-4 mb-8">
        <div className="flex items-center justify-between">
          <div 
            className="flex items-center gap-3 cursor-pointer" 
            onClick={() => navigate('/')}
          >
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#f4d03f] to-[#d4ac0d] flex items-center justify-center">
              <span className="text-[#1a1a2e] font-bold">BH</span>
            </div>
            <div>
              <h1 className="text-white font-bold">BIG Hat Trivia</h1>
              <p className="text-[#f4d03f] text-xs">Sponsor Portal</p>
            </div>
          </div>
          {user && (
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-white text-sm font-medium">{user.name}</p>
                <p className="text-white/50 text-xs">{user.businessName || user.email}</p>
              </div>
              <div className="w-10 h-10 rounded-full bg-[#f4d03f] flex items-center justify-center">
                <span className="text-[#1a1a2e] font-bold text-sm">
                  {user.name?.charAt(0) || 'U'}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Progress Steps */}
      <div className="max-w-4xl mx-auto px-4 mb-8">
        <div className="flex items-center justify-center gap-4">
          {steps.map((step, index) => (
            <React.Fragment key={step.id}>
              <div className="flex flex-col items-center">
                <div
                  className={`w-12 h-12 rounded-full flex items-center justify-center font-bold transition-colors ${
                    currentStep > index
                      ? 'bg-green-500 text-white'
                      : currentStep === index
                        ? 'bg-gradient-to-br from-[#f4d03f] to-[#d4ac0d] text-[#1a1a2e]'
                        : 'bg-white/10 text-white/40'
                  }`}
                >
                  {currentStep > index ? <Check size={20} /> : <step.icon size={20} />}
                </div>
                <p className={`text-xs mt-2 ${
                  currentStep >= index ? 'text-white' : 'text-white/40'
                }`}>
                  {step.label}
                </p>
              </div>
              {index < steps.length - 1 && (
                <div className={`w-20 h-0.5 mb-6 ${
                  currentStep > index ? 'bg-green-500' : 'bg-white/10'
                }`} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4">
        <Outlet />
      </div>
    </div>
  );
};

export default OnboardingLayout;
