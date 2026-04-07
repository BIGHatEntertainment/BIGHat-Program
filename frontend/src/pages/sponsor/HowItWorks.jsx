import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, CheckCircle, Calendar, Eye, ArrowRight, FileImage, MonitorPlay } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { mediaRequirements } from '../data/mock';

const HowItWorks = () => {
  const navigate = useNavigate();

  const steps = [
    {
      number: '01',
      icon: CheckCircle,
      title: 'Choose Your Sponsorship Package',
      description: 'Browse our tiered sponsorship options from Bronze to Star Tier Presenter. Select the package that fits your marketing goals and budget.',
      details: [
        'Compare package features and pricing',
        'View available spots for premium tiers',
        'Understand placement types and frequency',
      ],
    },
    {
      number: '02',
      icon: Upload,
      title: 'Upload Your Media Assets',
      description: 'Submit your promotional graphics through our easy upload portal. We accept GIFs and images optimized for live display.',
      details: [
        `Supported formats: ${mediaRequirements.formats.join(', ')}`,
        `Max file size: ${mediaRequirements.maxFileSize}`,
        `Recommended resolution: ${mediaRequirements.resolutions.recommended}`,
      ],
    },
    {
      number: '03',
      icon: Eye,
      title: 'Review & Approval',
      description: 'Our team reviews your assets for technical compliance and content guidelines. Most submissions are approved within 24-48 hours.',
      details: [
        'Automatic format validation',
        'Content guideline review',
        'Email notification on approval',
      ],
    },
    {
      number: '04',
      icon: Calendar,
      title: 'Scheduling & Placement',
      description: 'Once approved, your media is scheduled into our rotation. View upcoming placements directly in your dashboard.',
      details: [
        'Fair rotation across all sponsors',
        'View scheduled show appearances',
        'Track placement history',
      ],
    },
    {
      number: '05',
      icon: MonitorPlay,
      title: 'Go Live!',
      description: 'Your brand appears in live trivia shows across Phoenix venues. Engaged audiences see your message during active gameplay.',
      details: [
        'Pre-round, mid-round, and closing placements',
        'Host mentions for premium tiers',
        'Captive, engaged audience',
      ],
    },
  ];

  return (
    <div className="min-h-screen pt-28 pb-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-4xl sm:text-5xl font-bold text-white mb-4">
            How <span className="gradient-text">Sponsorship</span> Works
          </h1>
          <p className="text-white/60 max-w-2xl mx-auto text-lg">
            Our streamlined process makes it easy to get your brand in front of live audiences. Here's what to expect.
          </p>
        </div>

        {/* Steps */}
        <div className="space-y-8">
          {steps.map((step, index) => (
            <div
              key={index}
              className="card-dark rounded-2xl p-8 relative overflow-hidden"
            >
              <div className="flex flex-col lg:flex-row gap-8">
                {/* Step Number */}
                <div className="flex-shrink-0">
                  <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-[#f4d03f] to-[#d4ac0d] flex items-center justify-center">
                    <span className="text-[#1a1a2e] font-black text-2xl">{step.number}</span>
                  </div>
                </div>

                {/* Content */}
                <div className="flex-grow">
                  <div className="flex items-center gap-3 mb-3">
                    <step.icon className="w-6 h-6 text-[#f4d03f]" />
                    <h3 className="text-2xl font-bold text-white">{step.title}</h3>
                  </div>
                  <p className="text-white/60 text-lg mb-4">{step.description}</p>
                  <ul className="space-y-2">
                    {step.details.map((detail, idx) => (
                      <li key={idx} className="flex items-center gap-2 text-white/50 text-sm">
                        <div className="w-1.5 h-1.5 rounded-full bg-[#f4d03f]" />
                        {detail}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Connector Line */}
              {index < steps.length - 1 && (
                <div className="hidden lg:block absolute left-[4.5rem] top-full h-8 w-0.5 bg-gradient-to-b from-[#f4d03f] to-transparent" />
              )}
            </div>
          ))}
        </div>

        {/* Media Requirements Section */}
        <div className="mt-16">
          <div className="card-featured rounded-2xl p-8">
            <div className="flex items-center gap-3 mb-6">
              <FileImage className="w-8 h-8 text-[#f4d03f]" />
              <h2 className="text-2xl font-bold text-white">Media Requirements</h2>
            </div>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm mb-1">Supported Formats</p>
                <p className="text-white font-medium">{mediaRequirements.formats.join(', ')}</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm mb-1">Max File Size</p>
                <p className="text-white font-medium">{mediaRequirements.maxFileSize}</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm mb-1">Recommended Resolution</p>
                <p className="text-white font-medium">{mediaRequirements.resolutions.recommended}</p>
              </div>
              <div className="bg-white/5 rounded-xl p-4">
                <p className="text-white/50 text-sm mb-1">GIF Max Duration</p>
                <p className="text-white font-medium">{mediaRequirements.gifMaxDuration}</p>
              </div>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div className="mt-16 text-center">
          <h2 className="text-2xl font-bold text-white mb-4">Ready to Get Started?</h2>
          <p className="text-white/60 mb-6">Join local businesses reaching engaged audiences across Phoenix.</p>
          <Button
            size="lg"
            onClick={() => navigate('/signup')}
            className="btn-gold"
          >
            Become a Sponsor
            <ArrowRight className="ml-2" size={18} />
          </Button>
        </div>
      </div>
    </div>
  );
};

export default HowItWorks;