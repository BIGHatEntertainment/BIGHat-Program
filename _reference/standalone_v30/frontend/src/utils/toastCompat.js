import { toast as sonnerToast } from 'sonner';

export function toast(opts) {
  if (typeof opts === 'string') {
    sonnerToast(opts);
    return;
  }
  if (!opts) return;
  const msg = opts.description || opts.title || 'Notification';
  if (opts.variant === 'destructive') {
    sonnerToast.error(msg);
  } else {
    sonnerToast.success(msg);
  }
}

toast.error = (msg) => sonnerToast.error(msg);
toast.success = (msg) => sonnerToast.success(msg);
toast.info = (msg) => sonnerToast(msg);
