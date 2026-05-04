import React, { useState } from 'react';
import { X, Download, FileText, Grid3X3 } from 'lucide-react';

const ANSWER_SHEETS = [
  { id: 'multiple-choice', name: 'Multiple Choice', description: '10-question multiple choice answer form (A, B, C, D)', file: '/trivia-multiple-choice.pdf' },
  { id: 'answer-sheet', name: 'Answer Sheets', description: 'Standard answer sheet for general trivia rounds', file: '/trivia-answer-sheet.pdf' },
  { id: 'tie-breaker', name: 'Tie Breaker', description: 'Tie breaker form for final round decisions', file: '/trivia-tie-breaker.pdf' },
];

export default function AnswerSheetsPopup({ open, onClose }) {
  const [selected, setSelected] = useState(null);

  if (!open) return null;

  const handleDownload = (sheet) => {
    const link = document.createElement('a');
    link.href = sheet.file;
    link.download = `${sheet.name}.pdf`;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center" style={{ backgroundColor: 'rgba(0,0,0,0.85)' }}>
      <div className="relative w-full max-w-lg mx-4 rounded-2xl overflow-hidden" style={{ background: 'linear-gradient(135deg, #0a1940 0%, #000e2a 100%)', border: '2px solid rgba(251, 221, 104, 0.3)' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid rgba(251, 221, 104, 0.15)' }}>
          <div className="flex items-center gap-3">
            <Grid3X3 size={22} style={{ color: '#fbdd68' }} />
            <div>
              <h2 className="text-lg font-bold" style={{ color: '#fbdd68' }}>Trivia Answer Sheets</h2>
              <p className="text-xs" style={{ color: '#8892b0' }}>Select a sheet to download and print</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <X size={20} style={{ color: '#8892b0' }} />
          </button>
        </div>

        {/* Sheet Options */}
        <div className="p-6 space-y-3">
          {ANSWER_SHEETS.map((sheet) => (
            <div
              key={sheet.id}
              className="flex items-center justify-between p-4 rounded-xl cursor-pointer transition-all hover:scale-[1.01]"
              style={{
                background: selected === sheet.id ? 'rgba(251, 221, 104, 0.1)' : 'linear-gradient(135deg, #141b50, #0a1940)',
                border: `1px solid ${selected === sheet.id ? 'rgba(251, 221, 104, 0.4)' : 'rgba(251, 221, 104, 0.1)'}`,
              }}
              onClick={() => setSelected(sheet.id)}
            >
              <div className="flex items-center gap-3">
                <FileText size={20} style={{ color: '#fbdd68' }} />
                <div>
                  <h3 className="text-sm font-semibold text-white">{sheet.name}</h3>
                  <p className="text-xs" style={{ color: '#8892b0' }}>{sheet.description}</p>
                </div>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); handleDownload(sheet); }}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-all hover:shadow-lg"
                style={{ backgroundColor: '#fbdd68', color: '#000e2a' }}
              >
                <Download size={14} />
                Download
              </button>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 text-center" style={{ borderTop: '1px solid rgba(251, 221, 104, 0.1)' }}>
          <p className="text-[10px]" style={{ color: '#8892b0' }}>PDF format, ready to print</p>
        </div>
      </div>
    </div>
  );
}
