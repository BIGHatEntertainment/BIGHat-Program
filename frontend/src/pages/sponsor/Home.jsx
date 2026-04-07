import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Users, Calendar, MapPin, TrendingUp, CheckCircle, Star, Zap } from 'lucide-react';
import { Button } from '../../components/ui/button';

const Home = () => {
  const navigate = useNavigate();

  const stats = [
    { icon: Calendar, value: '8+', label: 'Events Weekly' },
    { icon: Users, value: '60-80', label: 'Avg. Attendance' },
    { icon: MapPin, value: '6+', label: 'Venues' },
    { icon: TrendingUp, value: '6.5K+', label: 'Social Followers' },
  ];

  const benefits = [
    {
      title: 'Brand Recognition',
      description: 'Go far beyond logo placement—create immersive brand experiences that drive recognition and long-term goodwill.',
      icon: Star,
    },
    {
      title: 'In-Play Promotions',
      description: 'Your promotion comes in an active setting—not a commercial break. Maximum ROI with engaged audiences.',
      icon: Zap,
    },
    {
      title: 'Product Handouts',
      description: 'Put your products into the hands of hundreds of excited guests each and every week.',
      icon: CheckCircle,
    },
    {
      title: 'Every Event, Every Week',
      description: 'Downtown, Gilbert, Glendale, Goodyear, Mesa, Tempe—you get seen across the Phoenix metro!',
      icon: MapPin,
    },
  ];

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="relative min-h-[90vh] flex items-center justify-center overflow-hidden">
        {/* Background elements */}
        <div className="absolute inset-0 bg-[#0f0f1a]">
          <div className="absolute top-20 left-10 w-72 h-72 bg-[#f4d03f]/10 rounded-full blur-3xl" />
          <div className="absolute bottom-20 right-10 w-96 h-96 bg-[#f4d03f]/5 rounded-full blur-3xl" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-[#16213e]/50 rounded-full blur-3xl" />
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-32 pb-20">
          <div className="text-center max-w-4xl mx-auto">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#f4d03f]/10 border border-[#f4d03f]/20 mb-8">
              <span className="w-2 h-2 rounded-full bg-[#f4d03f] animate-pulse" />
              <span className="text-[#f4d03f] text-sm font-medium">Phoenix&apos;s Premier Live Entertainment</span>
            </div>

            {/* Headline */}
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black text-white leading-tight mb-6">
              Put Your Business in Front of{' '}
              <span className="gradient-text">Live Trivia Audiences</span>{' '}
              Across Phoenix
            </h1>

            {/* Subheadline */}
            <p className="text-lg sm:text-xl text-white/60 max-w-2xl mx-auto mb-10 leading-relaxed">
              Reach engaged audiences at 8+ weekly events across Mesa, Gilbert & Downtown Phoenix. Your brand integrated seamlessly into live shows—not as ads, but as part of the experience.
            </p>

            {/* CTAs */}
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Button
                size="lg"
                onClick={() => navigate('/signup')}
                className="btn-gold text-lg px-8 py-6 h-auto"
              >
                Become a Sponsor
                <ArrowRight className="ml-2" size={20} />
              </Button>
              <Button
                size="lg"
                variant="outline"
                onClick={() => navigate('/packages')}
                className="btn-outline-gold text-lg px-8 py-6 h-auto"
              >
                View Sponsorship Options
              </Button>
            </div>
          </div>

          {/* Stats */}
          <div className="mt-20 grid grid-cols-2 md:grid-cols-4 gap-6">
            {stats.map((stat, index) => (
              <div
                key={index}
                className="card-dark rounded-2xl p-6 text-center"
              >
                <stat.icon className="w-8 h-8 text-[#f4d03f] mx-auto mb-3" />
                <p className="text-3xl font-bold text-white mb-1">{stat.value}</p>
                <p className="text-white/60 text-sm">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section className="py-24 bg-[#1a1a2e]/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
              Why <span className="gradient-text">Sponsor</span> With Us?
            </h2>
            <p className="text-white/60 max-w-2xl mx-auto">
              We support local businesses at every event. One monthly price and your message reaches every audience, every week.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8">
            {benefits.map((benefit, index) => (
              <div
                key={index}
                className="card-dark rounded-2xl p-8 hover:translate-y-[-4px] transition-transform duration-300"
              >
                <div className="w-14 h-14 rounded-xl bg-[#f4d03f]/10 flex items-center justify-center mb-6">
                  <benefit.icon className="w-7 h-7 text-[#f4d03f]" />
                </div>
                <h3 className="text-xl font-bold text-white mb-3">{benefit.title}</h3>
                <p className="text-white/60 leading-relaxed">{benefit.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works Preview */}
      <section className="py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
              How <span className="gradient-text">Sponsorship</span> Works
            </h2>
          </div>

          <div className="grid md:grid-cols-4 gap-8">
            {[
              { step: '01', title: 'Choose Package', desc: 'Select from our tiered sponsorship options' },
              { step: '02', title: 'Upload Media', desc: 'Submit your GIF or image assets' },
              { step: '03', title: 'Get Approved', desc: 'We review and schedule your content' },
              { step: '04', title: 'Go Live', desc: 'Your ad appears in live shows!' },
            ].map((item, index) => (
              <div key={index} className="text-center">
                <div className="w-16 h-16 rounded-full bg-gradient-to-br from-[#f4d03f] to-[#d4ac0d] flex items-center justify-center mx-auto mb-4">
                  <span className="text-[#1a1a2e] font-bold text-xl">{item.step}</span>
                </div>
                <h3 className="font-bold text-white mb-2">{item.title}</h3>
                <p className="text-white/60 text-sm">{item.desc}</p>
                {index < 3 && (
                  <div className="hidden md:block absolute top-8 left-full w-full h-0.5 bg-[#f4d03f]/20" />
                )}
              </div>
            ))}
          </div>

          <div className="text-center mt-12">
            <Button
              onClick={() => navigate('/how-it-works')}
              className="btn-outline-gold"
            >
              Learn More
              <ArrowRight className="ml-2" size={16} />
            </Button>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24 bg-[#1a1a2e]/50">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="card-featured rounded-3xl p-12">
            <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
              Ready to <span className="gradient-text">Get Seen</span>?
            </h2>
            <p className="text-white/60 mb-8 max-w-xl mx-auto">
              Join the growing list of local businesses reaching engaged audiences across Phoenix every week.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Button
                size="lg"
                onClick={() => navigate('/signup')}
                className="btn-gold"
              >
                Become a Sponsor Today
                <ArrowRight className="ml-2" size={18} />
              </Button>
              <Button
                size="lg"
                variant="ghost"
                onClick={() => navigate('/login')}
                className="text-white hover:bg-white/10"
              >
                Already a Sponsor? Login
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-[#0f0f1a] border-t border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            {/* Logo and Copyright */}
            <div className="flex flex-col items-center md:items-start gap-3">
              <img
                src="https://customer-assets.emergentagent.com/job_fe389e90-8faf-4d17-8387-2fb24e4ce58c/artifacts/a4mgjz8p_BIG%20Hat%20Logo%20Horizontal%20Transparent.png"
                alt="BIG Hat Entertainment"
                className="h-8"
              />
              <p className="text-white/40 text-sm">
                © {new Date().getFullYear()} BIG Hat Entertainment. All rights reserved.
              </p>
            </div>

            {/* Links */}
            <div className="flex items-center gap-6">
              <button
                onClick={() => navigate('/terms')}
                className="text-white/50 hover:text-white text-sm transition-colors"
              >
                Terms of Service
              </button>
              <button
                onClick={() => navigate('/privacy')}
                className="text-white/50 hover:text-white text-sm transition-colors"
              >
                Privacy Policy
              </button>
              <button
                onClick={() => navigate('/faq')}
                className="text-white/50 hover:text-white text-sm transition-colors"
              >
                FAQ
              </button>
            </div>

            {/* Contact */}
            <div className="text-center md:text-right">
              <p className="text-white/50 text-sm">Questions?</p>
              <a 
                href="mailto:info@bighat.live" 
                className="text-[#f4d03f] hover:text-[#d4ac0d] text-sm transition-colors"
              >
                info@bighat.live
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Home;