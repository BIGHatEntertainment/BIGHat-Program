import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, Phone, MessageSquare, ArrowRight } from 'lucide-react';
import { Button } from '../../components/ui/button';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '../../components/ui/accordion';
import { faqs } from '../data/mock';

const FAQ = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen pt-28 pb-20">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-4xl sm:text-5xl font-bold text-white mb-4">
            Frequently Asked <span className="gradient-text">Questions</span>
          </h1>
          <p className="text-white/60 max-w-2xl mx-auto text-lg">
            Everything you need to know about sponsoring with BIG Hat Trivia.
          </p>
        </div>

        {/* FAQ Accordion */}
        <div className="card-dark rounded-2xl p-6 sm:p-8">
          <Accordion type="single" collapsible className="space-y-4">
            {faqs.map((faq, index) => (
              <AccordionItem
                key={index}
                value={`item-${index}`}
                className="border border-[#f4d03f]/10 rounded-xl px-6 py-2 bg-white/5 data-[state=open]:bg-[#f4d03f]/5 transition-colors"
              >
                <AccordionTrigger className="text-white hover:text-[#f4d03f] text-left font-medium py-4 hover:no-underline">
                  {faq.question}
                </AccordionTrigger>
                <AccordionContent className="text-white/60 pb-4 leading-relaxed">
                  {faq.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>

        {/* Contact Section */}
        <div className="mt-16">
          <div className="card-featured rounded-2xl p-8 text-center">
            <MessageSquare className="w-12 h-12 text-[#f4d03f] mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-white mb-2">Still Have Questions?</h2>
            <p className="text-white/60 mb-8 max-w-md mx-auto">
              Our sponsor support team is here to help. Reach out and we'll get back to you promptly.
            </p>

            <div className="grid sm:grid-cols-2 gap-4 max-w-lg mx-auto mb-8">
              <a
                href="tel:6027757577"
                className="flex items-center justify-center gap-3 p-4 bg-white/5 rounded-xl hover:bg-[#f4d03f]/10 transition-colors group"
              >
                <Phone className="w-5 h-5 text-[#f4d03f]" />
                <span className="text-white group-hover:text-[#f4d03f] transition-colors">(602) 775-7577</span>
              </a>
              <a
                href="mailto:sponsors@bighat.live"
                className="flex items-center justify-center gap-3 p-4 bg-white/5 rounded-xl hover:bg-[#f4d03f]/10 transition-colors group"
              >
                <Mail className="w-5 h-5 text-[#f4d03f]" />
                <span className="text-white group-hover:text-[#f4d03f] transition-colors">Email Us</span>
              </a>
            </div>

            <Button
              onClick={() => navigate('/signup')}
              className="btn-gold"
            >
              Become a Sponsor
              <ArrowRight className="ml-2" size={18} />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FAQ;