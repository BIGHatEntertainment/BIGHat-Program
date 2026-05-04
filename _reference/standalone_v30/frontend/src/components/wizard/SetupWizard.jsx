import React, { useState } from 'react';

const steps = [
"Terms & License",
  'Welcome & License',
  'File Placement',
  'Venue Configuration',
  'Modules & Library'
];

export default function SetupWizard({ onComplete }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [formData, setFormData] = useState({
    license_key: '', accepted_terms: false,
    paths: {
      trivia_data: 'C:/BIGHat/Trivia',
      assets: 'C:/BIGHat/Assets',
      logos: 'C:/BIGHat/Logos'
    },
    settings: {
      location_name: '',
      timezone: 'America/Phoenix',
      logo_url: ''
    },
    modules: {
      trivia_lib: false,
      bingo: false,
      karaoke: false
    }
  });

  const nextStep = () => setCurrentStep(prev => Math.min(prev + 1, steps.length - 1));
  const prevStep = () => setCurrentStep(prev => Math.max(prev - 1, 0));

  const handleFinish = async () => {
    // Call /api/setup/initialize
    console.log("Finalizing Setup:", formData);
    onComplete(formData);
  };

  return (
    <div className="max-w-2xl mx-auto mt-20 p-8 glass-card rounded-3xl text-white">
      <div className="mb-8">
        <h2 className="text-2xl font-bold mb-2">BIGHat Setup Wizard</h2>
        <div className="flex gap-2">
          {steps.map((s, i) => (
            <div key={i} className={`h-1 flex-1 rounded ${i <= currentStep ? 'bg-[#fbdd68]' : 'bg-white/10'}`} />
          ))}
        </div>
        <p className="text-sm mt-2 text-gray-400">Step {currentStep + 1}: {steps[currentStep]}</p>
      </div>

      {currentStep === 0 && (
        <div className="space-y-4">
          <div className="mb-6 p-4 bg-white/5 border border-white/10 rounded-lg max-h-40 overflow-y-auto text-xs text-gray-400">
            <h4 className="font-bold mb-2">Proprietary License & Terms</h4>
            <p>This software is proprietary to BIGHat Entertainment. By using this software, you agree to the Terms of Use and License Agreement. Each license allows up to 5 concurrent installations (seats).</p>
          </div>
          <label className="flex items-center gap-2 mb-4 cursor-pointer text-sm">
            <input type="checkbox" checked={formData.accepted_terms} onChange={e => setFormData({...formData, accepted_terms: e.target.checked})} />
            I accept the Proprietary License and Terms of Use
          </label>
          <p>Please enter your BIGHat License Key to activate the program (Allows up to 5 installations).</p>
          <input 
            className="w-full bg-white/5 border border-white/10 rounded-lg p-3"
            placeholder="XXXX-XXXX-XXXX-XXXX"
            value={formData.license_key}
            onChange={e => setFormData({...formData, license_key: e.target.value})}
          />
        </div>
      )}

      {currentStep === 1 && (
        <div className="space-y-4">
          <p>Select where you want to store your local data.</p>
          {Object.keys(formData.paths).map(key => (
            <div key={key}>
              <label className="text-xs uppercase text-gray-400">{key.replace('_', ' ')}</label>
              <input 
                className="w-full bg-white/5 border border-white/10 rounded-lg p-2"
                value={formData.paths[key]}
                onChange={e => setFormData({
                  ...formData, 
                  paths: {...formData.paths, [key]: e.target.value}
                })}
              />
            </div>
          ))}
        </div>
      )}

      {currentStep === 2 && (
        <div className="space-y-4">
          <p>Configure your venue details.</p>
          <input 
            className="w-full bg-white/5 border border-white/10 rounded-lg p-3"
            placeholder="Venue Name (e.g. Monkey Pants)"
            value={formData.settings.location_name}
            onChange={e => setFormData({
              ...formData, 
              settings: {...formData.settings, location_name: e.target.value}
            })}
          />
          <select 
            className="w-full bg-white/5 border border-white/10 rounded-lg p-3 text-white"
            value={formData.settings.timezone}
            onChange={e => setFormData({
                ...formData, 
                settings: {...formData.settings, timezone: e.target.value}
              })}
          >
            <option value="America/Phoenix">Phoenix (MST)</option>
            <option value="America/Los_Angeles">Pacific (PST)</option>
            <option value="UTC">UTC</option>
          </select>
        </div>
      )}

      {currentStep === 3 && (
        <div className="space-y-4">
          <p>Enable additional modules. Subscriptions will be verified via your license key.</p>
          <div className="grid grid-cols-1 gap-3">
             {['trivia_lib', 'bingo', 'karaoke'].map(mod => (
               <label key={mod} className="flex items-center gap-3 p-3 border border-white/10 rounded-xl cursor-pointer hover:bg-white/5">
                 <input 
                  type="checkbox" 
                  checked={formData.modules[mod]}
                  onChange={e => setFormData({
                    ...formData,
                    modules: {...formData.modules, [mod]: e.target.checked}
                  })}
                 />
                 <span className="capitalize">{mod.replace('_', ' ')}</span>
               </label>
             ))}
          </div>
        </div>
      )}

      <div className="mt-10 flex justify-between">
        <button 
          onClick={prevStep} 
          disabled={currentStep === 0}
          className="px-6 py-2 rounded-lg font-bold disabled:opacity-30"
        >
          Back
        </button>
        {currentStep === steps.length - 1 ? (
          <button 
            onClick={handleFinish}
            className="px-6 py-2 bg-[#fbdd68] text-black rounded-lg font-bold"
          >
            Finish & Launch
          </button>
        ) : (
          <button 
            onClick={nextStep}
            className={`px-6 py-2 bg-white/10 rounded-lg font-bold ${currentStep === 0 className="px-6 py-2 bg-white/10 rounded-lg font-bold"className="px-6 py-2 bg-white/10 rounded-lg font-bold" !formData.accepted_terms ? "opacity-30 cursor-not-allowed" : ""}`} disabled={currentStep === 0 className="px-6 py-2 bg-white/10 rounded-lg font-bold"className="px-6 py-2 bg-white/10 rounded-lg font-bold" !formData.accepted_terms}
          >
            Next
          </button>
        )}
      </div>
    </div>
  );
}
