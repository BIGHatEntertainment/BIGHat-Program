import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Button } from '../../components/ui/button';

const PrivacyPolicy = () => {
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
          <h1 className="text-3xl sm:text-4xl font-bold text-white mb-2">Privacy Policy</h1>
          <p className="text-white/50 mb-8">Last updated: December 2025</p>

          <div className="prose prose-invert max-w-none space-y-8">
            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">1. Introduction</h2>
              <p className="text-white/70 leading-relaxed">
                BIG Hat Entertainment (&quot;we,&quot; &quot;our,&quot; or &quot;us&quot;) is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our Sponsor Portal and related services.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">2. Information We Collect</h2>
              <p className="text-white/70 leading-relaxed mb-4">
                We collect information you provide directly to us, including:
              </p>
              <ul className="list-disc list-inside text-white/70 space-y-2 ml-4">
                <li><strong className="text-white">Account Information:</strong> Name, email address, phone number, business name</li>
                <li><strong className="text-white">Payment Information:</strong> Billing details processed securely through Stripe</li>
                <li><strong className="text-white">Content:</strong> Logos, images, and promotional materials you upload</li>
                <li><strong className="text-white">Communications:</strong> Messages and correspondence with our team</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">3. How We Use Your Information</h2>
              <p className="text-white/70 leading-relaxed mb-4">
                We use the information we collect to:
              </p>
              <ul className="list-disc list-inside text-white/70 space-y-2 ml-4">
                <li>Provide and maintain our sponsorship services</li>
                <li>Process payments and manage subscriptions</li>
                <li>Display your promotional content at events</li>
                <li>Communicate with you about your account and services</li>
                <li>Send you updates, marketing communications, and promotional offers</li>
                <li>Improve our services and develop new features</li>
                <li>Comply with legal obligations</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">4. Information Sharing</h2>
              <p className="text-white/70 leading-relaxed mb-4">
                We do not sell your personal information. We may share your information with:
              </p>
              <ul className="list-disc list-inside text-white/70 space-y-2 ml-4">
                <li><strong className="text-white">Service Providers:</strong> Third parties that help us operate our services (e.g., payment processors, cloud storage)</li>
                <li><strong className="text-white">Venue Partners:</strong> Your business name and promotional content displayed at event venues</li>
                <li><strong className="text-white">Legal Requirements:</strong> When required by law or to protect our rights</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">5. Data Security</h2>
              <p className="text-white/70 leading-relaxed">
                We implement appropriate technical and organizational measures to protect your personal information against unauthorized access, alteration, disclosure, or destruction. However, no method of transmission over the Internet or electronic storage is 100% secure.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">6. Your Rights</h2>
              <p className="text-white/70 leading-relaxed mb-4">
                You have the right to:
              </p>
              <ul className="list-disc list-inside text-white/70 space-y-2 ml-4">
                <li>Access and update your personal information through your account</li>
                <li>Request deletion of your account and associated data</li>
                <li>Opt out of marketing communications</li>
                <li>Request a copy of your data</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">7. Cookies and Tracking</h2>
              <p className="text-white/70 leading-relaxed">
                We use cookies and similar tracking technologies to maintain your session, remember your preferences, and analyze usage patterns. You can control cookies through your browser settings, though disabling them may affect functionality.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">8. Data Retention</h2>
              <p className="text-white/70 leading-relaxed">
                We retain your personal information for as long as your account is active or as needed to provide services. We may retain certain information as required by law or for legitimate business purposes.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">9. Children&apos;s Privacy</h2>
              <p className="text-white/70 leading-relaxed">
                Our services are not intended for children under 18 years of age. We do not knowingly collect personal information from children.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">10. Changes to This Policy</h2>
              <p className="text-white/70 leading-relaxed">
                We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new policy on this page and updating the &quot;Last updated&quot; date.
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold text-[#f4d03f] mb-4">11. Contact Us</h2>
              <p className="text-white/70 leading-relaxed">
                If you have any questions about this Privacy Policy or our data practices, please contact us at:
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

export default PrivacyPolicy;
