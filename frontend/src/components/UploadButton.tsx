import { useRef } from 'react';

interface UploadButtonProps {
  label?: string;
  accept?: string;
  disabled?: boolean;
  onFileSelect: (file: File) => void;
  className?: string;
  icon?: string;
}

export default function UploadButton({
  label = 'Upload Excel',
  accept = '.xlsx,.xls,.csv',
  disabled = false,
  onFileSelect,
  className = '',
  icon = '📊',
}: UploadButtonProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleClick = () => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onFileSelect(file);
    }
    e.target.value = '';
  };

  return (
    <div className="inline-block">
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded shadow-xs hover:bg-gray-100 active:bg-gray-200 disabled:opacity-40 transition-colors ${className}`}
      >
        <span>{icon}</span>
        <span>{label}</span>
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleChange}
        className="hidden"
        aria-hidden="true"
      />
    </div>
  );
}

