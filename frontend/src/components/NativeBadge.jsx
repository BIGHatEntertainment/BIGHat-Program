import React from 'react';
import { Cpu, ShieldCheck } from 'lucide-react';
import { useNative } from '../context/NativeContext';

/**
 * Compact native-mode indicator. Hidden when not in native mode.
 * Place anywhere in the header / sidebar.
 */
export default function NativeBadge({ className = '' }) {
  const { nativeMode, license, subscription } = useNative();
  if (!nativeMode) return null;

  const seatsUsed = license?.used_seats ?? 0;
  const seatsTotal = license?.total_seats_allowed ?? 5;
  const isPremium = Boolean(subscription?.active);

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-white/5 border border-white/10 text-xs ${className}`}
      title={`Native standalone • seat ${seatsUsed}/${seatsTotal}`}
      data-testid="native-badge"
    >
      <Cpu className="w-3.5 h-3.5 text-[#fbdd68]" />
      <span className="text-white/70 font-medium">Native</span>
      <span className="text-white/30">•</span>
      <span className="text-[#fbdd68] font-mono">
        {seatsUsed}/{seatsTotal}
      </span>
      {isPremium && (
        <>
          <span className="text-white/30">•</span>
          <ShieldCheck className="w-3.5 h-3.5 text-[#5973F7]" title="Premium active" />
        </>
      )}
    </div>
  );
}
