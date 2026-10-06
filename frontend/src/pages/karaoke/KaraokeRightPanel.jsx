import React from "react";
import { QRCodeSVG } from "qrcode.react";
import { Mic, Music, Check, X, QrCode, AlertCircle, Monitor } from "lucide-react";

const accent = "#22c55e";
const accentDim = "rgba(34,197,94,0.15)";
const accentBorder = "rgba(34,197,94,0.25)";

/**
 * Karaoke Player, right side (alpha.89). Top to bottom, as in the prototype:
 *   1. Audience Preview (16:9)  - what the TV shows right now
 *   2. Request QR               - the "QR lobby": phones scan it to browse and request songs
 *   3. Song Requests            - pending phone requests, Accept / Reject
 *   4. In Queue                 - how many singers are waiting
 * Shown in BOTH the Filler and the Karaoke tab.
 */
export default function KaraokeRightPanel({
  mode, currentSinger, songPlaying, isFillerPlaying, currentTrackName,
  audienceOpen, onOpenAudience,
  showQr, requestUrl,
  pendingRequests, onAccept, onReject,
  queueCount,
}) {
  const live = songPlaying && currentSinger;
  return (
    <aside className="w-[17rem] xl:w-[22rem] shrink-0 flex flex-col gap-3 rounded-xl p-3 overflow-y-auto" data-testid="karaoke-right-panel"
           style={{ border: `1.5px solid ${accentBorder}`, backgroundColor: "rgba(10,25,64,0.5)" }}>
      {/* 1. preview */}
      <div>
        <div className="rounded-xl overflow-hidden flex items-center justify-center text-center" data-testid="karaoke-preview"
             style={{ border: `1.5px solid ${accentBorder}`, aspectRatio: "16/9", backgroundColor: "#000" }}>
          {live ? (
            <div className="p-3" data-testid="karaoke-preview-live">
              <Mic size={26} style={{ color: accent }} className="mx-auto mb-2" />
              <p className="text-sm font-bold text-white">{currentSinger.singer_name}</p>
              <p className="text-xs" style={{ color: accent }}>{currentSinger.song_title}</p>
              {currentSinger.song_artist && <p className="text-[10px]" style={{ color: "#8892b0" }}>{currentSinger.song_artist}</p>}
            </div>
          ) : (
            <div className="p-3" data-testid="karaoke-preview-idle">
              <Music size={22} style={{ color: "#8892b0" }} className="mx-auto mb-1" />
              <p className="text-[11px]" style={{ color: "#8892b0" }}>
                {isFillerPlaying ? `Filler music${currentTrackName ? `: ${currentTrackName}` : ""}` : "Waiting..."}
              </p>
            </div>
          )}
        </div>
        <p className="text-[10px] text-center mt-1" style={{ color: "#8892b0" }}>Audience Preview (on TV)</p>
        {!audienceOpen && (
          <button onClick={onOpenAudience} className="w-full mt-2 flex items-center justify-center gap-2 py-1.5 rounded-lg text-[11px] font-bold"
                  style={{ backgroundColor: "rgba(251,221,104,0.12)", border: "1px solid rgba(251,221,104,0.4)", color: "#fbdd68" }}
                  data-testid="karaoke-preview-open-audience">
            <Monitor size={12} /> The TV screen is not open. Open Audience View
          </button>
        )}
      </div>

      {/* 2. request QR */}
      {showQr && (
        <div className="rounded-xl p-3 text-center" data-testid="karaoke-qr-card"
             style={{ backgroundColor: "rgba(34,197,94,0.05)", border: `1.5px solid ${accentBorder}` }}>
          <p className="text-[10px] uppercase tracking-wider font-bold mb-2 flex items-center justify-center gap-1" style={{ color: accent }}>
            <QrCode size={11} /> Song Request QR
          </p>
          {requestUrl ? (
            <>
              <div className="bg-white rounded-lg p-2 inline-block" data-testid="karaoke-host-qr"><QRCodeSVG value={requestUrl} size={132} /></div>
              <p className="text-[10px] mt-2" style={{ color: "#8892b0" }}>Scan to browse and request songs</p>
            </>
          ) : (
            <div className="text-xs rounded-lg px-3 py-2 flex items-start gap-2 text-left" data-testid="karaoke-qr-offline"
                 style={{ backgroundColor: "rgba(251,221,104,0.12)", color: "#fbdd68", border: "1px solid rgba(251,221,104,0.4)" }}>
              <AlertCircle size={14} className="shrink-0 mt-0.5" />
              Phone requests are not available right now. Check the internet connection. You can still add songs by hand.
            </div>
          )}
        </div>
      )}

      {/* 3. song requests */}
      <div className="flex-1 min-h-[6rem] flex flex-col" data-testid="karaoke-requests">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: "#fbdd68" }}>Song Requests</span>
          <span className="text-[10px]" style={{ color: "#8892b0" }} data-testid="karaoke-requests-count">{pendingRequests.length} pending</span>
        </div>
        <div className="flex-1 overflow-y-auto space-y-1">
          {pendingRequests.map((r) => (
            <div key={r.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg" data-testid={`karaoke-request-${r.id}`}
                 style={{ backgroundColor: "rgba(251,221,104,0.06)", border: "1px solid rgba(251,221,104,0.2)" }}>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-white truncate">{r.singer_name}</p>
                <p className="text-[10px] truncate" style={{ color: "#8892b0" }}>{r.song_title}{r.song_artist ? ` - ${r.song_artist}` : ""}</p>
              </div>
              <button onClick={() => onAccept(r.id)} className="w-6 h-6 rounded-full flex items-center justify-center shrink-0" title="Accept"
                      style={{ backgroundColor: accentDim }} data-testid={`karaoke-accept-${r.id}`}><Check size={13} style={{ color: accent }} /></button>
              <button onClick={() => onReject(r.id)} className="w-6 h-6 rounded-full flex items-center justify-center shrink-0" title="Reject"
                      style={{ backgroundColor: "rgba(239,68,68,0.15)" }} data-testid={`karaoke-reject-${r.id}`}><X size={13} style={{ color: "#ef4444" }} /></button>
            </div>
          ))}
          {pendingRequests.length === 0 && <p className="text-[10px] text-center py-3" style={{ color: "#555" }}>No pending requests</p>}
        </div>
      </div>

      {/* 4. in queue */}
      <div className="rounded-xl p-3 text-center shrink-0" style={{ backgroundColor: "rgba(255,255,255,0.03)" }}>
        <p className="text-2xl font-bold" style={{ color: accent }} data-testid="karaoke-queue-count">{queueCount}</p>
        <p className="text-[10px]" style={{ color: "#8892b0" }}>In Queue</p>
      </div>
    </aside>
  );
}
