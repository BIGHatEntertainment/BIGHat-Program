import React from "react";
import { Timer } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../../components/ui/dialog";

/**
 * v32.2.9: the "Auto-advance songs" switch, the same control in Music Bingo and Traditional Bingo.
 * It shows what the server REALLY saved. Turning it ON asks the host to confirm first; turning it OFF is one click.
 */
export default function AutoAdvanceSwitch({ on, ready, saving, mode, confirmOpen, setConfirmOpen, onSave }) {
  const noun = mode === "music" ? "song" : "number";
  const action = mode === "music" ? "Next Song" : "Call Number";
  return (
    <>
      <div
        className={`flex items-center justify-between p-3 rounded-lg bg-zinc-800/60 border ${on ? "border-emerald-500/60" : "border-zinc-700"} select-none ${ready && !saving ? "cursor-pointer" : "opacity-60"}`}
        onClick={() => { if (!ready || saving) return; on ? onSave(false) : setConfirmOpen(true); }}
        role="switch" aria-checked={on} aria-label="Auto-advance"
        data-testid="auto-advance-toggle"
      >
        <div className="flex items-center gap-2">
          <Timer size={16} className="text-emerald-400" />
          <div>
            <span className="text-sm text-zinc-300">Auto-advance</span>
            <p className="text-[11px] text-zinc-500" data-testid="auto-advance-state">
              {on ? `ON: the next ${noun} plays when the timer reaches 0` : `OFF: you press ${action} yourself`}
            </p>
          </div>
        </div>
        <div className={`w-10 h-5 rounded-full relative transition-colors duration-200 ${on ? "bg-emerald-500" : "bg-zinc-600"}`}>
          <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform duration-200 ${on ? "translate-x-5" : "translate-x-0.5"}`} />
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={(o) => { if (!saving) setConfirmOpen(o); }}>
        <DialogContent className="bg-zinc-900 border-zinc-700" data-testid="auto-advance-confirm">
          <DialogHeader><DialogTitle>Turn on auto-advance?</DialogTitle></DialogHeader>
          <div className="text-sm text-zinc-300 space-y-2">
            <p>When the timer reaches 0, the next {noun} will play by itself, exactly as if you pressed <b>{action}</b>.</p>
            <p>It does <b>not</b> start a round. It stops while a bingo is being checked, while the winner video plays, when you pause, and when the round ends.
               After a bingo, press Resume or start a new round and play a {noun} to continue.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={saving} data-testid="auto-advance-cancel">Cancel</Button>
            <Button className="btn-success" onClick={() => onSave(true)} disabled={saving} data-testid="auto-advance-confirm-yes">
              {saving ? "Saving..." : "Yes, turn it on"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
