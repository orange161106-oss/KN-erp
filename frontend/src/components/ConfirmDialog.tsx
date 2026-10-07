interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDestructive?: boolean;
  isLoading?: boolean;
  details?: React.ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  isDestructive = false,
  isLoading = false,
  details,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-2xl max-w-sm w-full p-5 border border-gray-200 text-xs space-y-3 animate-in fade-in zoom-in-95 duration-100">
        <div className="flex items-start gap-2">
          {isDestructive ? (
            <span className="text-xl">⚠️</span>
          ) : (
            <span className="text-xl">ℹ️</span>
          )}
          <div>
            <h3 className="font-bold text-sm text-gray-900">{title}</h3>
            <p className="text-gray-600 mt-1">{message}</p>
          </div>
        </div>

        {details && (
          <div className="p-2.5 bg-gray-50 rounded border border-gray-200 font-mono text-[11px] space-y-1 max-h-40 overflow-y-auto">
            {details}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
          <button
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className="px-3 py-1.5 bg-white border border-gray-300 rounded font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-50 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-3 py-1.5 text-white rounded font-semibold transition-colors disabled:opacity-50 ${
              isDestructive
                ? 'bg-red-600 hover:bg-red-700 active:bg-red-800'
                : 'bg-brand-navy hover:bg-opacity-90 active:bg-opacity-100'
            }`}
          >
            {isLoading ? 'Processing…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

