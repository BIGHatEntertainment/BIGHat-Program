import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '../components/ui/button';

const TermsOfService = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0f0f1a] to-[#1a1a2e]">
      {/* Header */}
      <header className="py-6 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <Button
            variant="ghost"
            onClick={() => navigate(-1)}
            className="text-white/70 hover:text-white"
          >
            <ArrowLeft className="mr-2" size={18} />
            Back
          </Button>
          <img
            src="https://customer-assets.emergentagent.com/job_fe389e90-8faf-4d17-8387-2fb24e4ce58c/artifacts/a4mgjz8p_BIG%20Hat%20Logo%20Horizontal%20Transparent.png"
            alt="BIG Hat Entertainment"
            className="h-10 cursor-pointer"
            onClick={() => navigate('/')}
          />
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="card-dark rounded-2xl p-8 sm:p-12">
          <h1 className="text-3xl sm:text-4xl font-bold text-white mb-2">Terms of Service</h1>
          <p className="text-white/50 mb-8">Last updated: December 2025</p>

          <div className="prose prose-invert max-w-none space-y-8">
            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">1. Acceptance of Terms</h2>
              <p className="text-white/70 leading-relaxed">
                By accessing and using the BIG Hat Entertainment Sponsor Portal, you accept and agree to be bound by these Terms of Service. If you do not agree to these terms, please do not use our services.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">2. Sponsor Account</h2>
              <p className="text-white/70 leading-relaxed mb-4">
                To use our sponsorship services, you must create an account and provide accurate, complete information. You are responsible for:
              </p>
              <ul className="list-disc list-inside text-white/70 space-y-2 ml-4">
                <li>Maintaining the confidentiality of your account credentials</li>
                <li>All activities that occur under your account</li>
                <li>Notifying us immediately of any unauthorized use</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">3. Sponsorship Services</h2>
              <p className="text-white/70 leading-relaxed mb-4">
                BIG Hat Entertainment provides advertising and sponsorship opportunities at live trivia, bingo, and entertainment events. Our services include:
              </p>
              <ul className="list-disc list-inside text-white/70 space-y-2 ml-4">
                <li>Display of sponsor logos and promotional content during events</li>
                <li>Host mentions and acknowledgments</li>
                <li>Social media promotions (based on sponsorship tier)</li>
                <li>Access to the sponsor portal for asset management</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">4. Content Guidelines</h2>
              <p className="text-white/70 leading-relaxed mb-4">
                All uploaded content must comply with our content guidelines. You agree not to upload content that:
              </p>
              <ul className="list-disc list-inside text-white/70 space-y-2 ml-4">
                <li>Is illegal, harmful, or offensive</li>
                <li>Infringes on intellectual property rights</li>
                <li>Contains false or misleading information</li>
                <li>Promotes illegal activities or substances</li>
                <li>Is inappropriate for a general audience at entertainment venues</li>
              </ul>
              <p className="text-white/70 leading-relaxed mt-4">
                BIG Hat Entertainment reserves the right to reject or remove any content that violates these guidelines.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">5. Payment Terms</h2>
              <p className="text-white/70 leading-relaxed">
                Sponsorship fees are billed monthly. By subscribing to a sponsorship package, you authorize us to charge your payment method on a recurring basis. You may cancel your subscription at any time, and cancellation will take effect at the end of your current billing period.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">6. Intellectual Property</h2>
              <p className="text-white/70 leading-relaxed">
                You retain ownership of the content you upload. By uploading content, you grant BIG Hat Entertainment a non-exclusive license to display, reproduce, and distribute your content as part of our sponsorship services at live events and related promotional materials.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">7. Limitation of Liability</h2>
              <p className="text-white/70 leading-relaxed">
                BIG Hat Entertainment shall not be liable for any indirect, incidental, special, or consequential damages arising from your use of our services. Our total liability shall not exceed the amount paid by you for the services in the twelve months preceding the claim.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">8. Changes to Terms</h2>
              <p className="text-white/70 leading-relaxed">
                We reserve the right to modify these terms at any time. We will notify you of significant changes via email or through the sponsor portal. Continued use of our services after changes constitutes acceptance of the modified terms.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">9. Contact Us</h2>
              <p className="text-white/70 leading-relaxed">
                If you have any questions about these Terms of Service, please contact us at:
              </p>
              <p className="text-white/70 mt-2">
                <strong className="text-white">BIG Hat Entertainment</strong><br />
                Email: info@bighat.live
              </p>
            </section>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="py-8 px-4 text-center">
        <p className="text-white/40 text-sm">
          © {new Date().getFullYear()} BIG Hat Entertainment. All rights reserved.
        </p>
      </footer>
    </div>
  );
};

export default TermsOfService;
