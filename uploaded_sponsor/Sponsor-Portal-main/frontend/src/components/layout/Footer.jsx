import React from 'react';
import { Link } from 'react-router-dom';
import { Mail, Phone, MapPin, Instagram, Facebook, Twitter } from 'lucide-react';

const Footer = () => {
  return (
    <footer className="bg-[#0f0f1a] border-t border-[#f4d03f]/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-12">
          {/* Brand */}
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 bg-gradient-to-br from-[#f4d03f] to-[#d4ac0d] rounded-xl flex items-center justify-center">
                <span className="text-[#1a1a2e] font-black text-xl">BH</span>
              </div>
              <div>
                <p className="font-bold text-lg text-white">BIG Hat Trivia</p>
                <p className="text-xs text-[#f4d03f]/80">Sponsor Portal</p>
              </div>
            </div>
            <p className="text-white/60 text-sm leading-relaxed">
              Phoenix's premier entertainment provider for bars, restaurants, and corporate events. Put your brand in front of live audiences weekly.
            </p>
            <div className="flex gap-4">
              <a
                href="https://instagram.com/bighattrivia"
                target="_blank"
                rel="noopener noreferrer"
                className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-white/60 hover:bg-[#f4d03f]/20 hover:text-[#f4d03f] transition-colors"
              >
                <Instagram size={18} />
              </a>
              <a
                href="https://facebook.com/bighattrivia"
                target="_blank"
                rel="noopener noreferrer"
                className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-white/60 hover:bg-[#f4d03f]/20 hover:text-[#f4d03f] transition-colors"
              >
                <Facebook size={18} />
              </a>
              <a
                href="https://twitter.com/bighattrivia"
                target="_blank"
                rel="noopener noreferrer"
                className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-white/60 hover:bg-[#f4d03f]/20 hover:text-[#f4d03f] transition-colors"
              >
                <Twitter size={18} />
              </a>
            </div>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="font-semibold text-white mb-4">Quick Links</h4>
            <ul className="space-y-3">
              <li>
                <Link to="/packages" className="text-white/60 hover:text-[#f4d03f] transition-colors text-sm">
                  Sponsorship Packages
                </Link>
              </li>
              <li>
                <Link to="/how-it-works" className="text-white/60 hover:text-[#f4d03f] transition-colors text-sm">
                  How It Works
                </Link>
              </li>
              <li>
                <Link to="/faq" className="text-white/60 hover:text-[#f4d03f] transition-colors text-sm">
                  FAQ
                </Link>
              </li>
              <li>
                <Link to="/signup" className="text-white/60 hover:text-[#f4d03f] transition-colors text-sm">
                  Become a Sponsor
                </Link>
              </li>
            </ul>
          </div>

          {/* Legal */}
          <div>
            <h4 className="font-semibold text-white mb-4">Legal</h4>
            <ul className="space-y-3">
              <li>
                <Link to="/terms" className="text-white/60 hover:text-[#f4d03f] transition-colors text-sm">
                  Terms of Service
                </Link>
              </li>
              <li>
                <Link to="/privacy" className="text-white/60 hover:text-[#f4d03f] transition-colors text-sm">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link to="/content-guidelines" className="text-white/60 hover:text-[#f4d03f] transition-colors text-sm">
                  Content Guidelines
                </Link>
              </li>
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h4 className="font-semibold text-white mb-4">Contact</h4>
            <ul className="space-y-3">
              <li className="flex items-center gap-3 text-white/60 text-sm">
                <Phone size={16} className="text-[#f4d03f]" />
                (602) 775-7577
              </li>
              <li className="flex items-center gap-3 text-white/60 text-sm">
                <Mail size={16} className="text-[#f4d03f]" />
                sponsors@bighat.live
              </li>
              <li className="flex items-start gap-3 text-white/60 text-sm">
                <MapPin size={16} className="text-[#f4d03f] mt-0.5" />
                <span>Phoenix Metro Area<br />Arizona</span>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-[#f4d03f]/10">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-white/40 text-sm">
              © {new Date().getFullYear()} BIG Hat Entertainment. All rights reserved.
            </p>
            <p className="text-white/40 text-sm">
              Powered by <span className="text-[#f4d03f]">BIG Hat Trivia App</span>
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;