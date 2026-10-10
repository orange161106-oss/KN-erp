import { useRef, useState } from 'react';
import type { ReactNode } from 'react';

export interface SheetInfo {
  name: string;
  row_count: number;
  column_count: number;
  headers: string[];
  sample_rows: Record<string, string>[];
}

export interface InspectResult {
  filename: string;
  sheets: SheetInfo[];
}

interface ExcelUploadModalProps {
  isOpen: boolean;
  title?: string;
  subtitle?: string;
  onClose: () => void;
  onInspect: (file: File) => Promise<InspectResult>;
  onImport: (file: File, sheetName: string) => Promise<void>;
  isLoading?: boolean;
  children?: ReactNode;
}

export default function ExcelUploadModal({
  isOpen,
  title = 'Import Excel File',
  subtitle = 'Upload your Excel file to populate the table',
  onClose,
  onInspect,
  onImport,
  isLoading = false,
  children,
}: ExcelUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [inspectData, setInspectData] = useState<InspectResult | null>(null);
  const [selectedSheet, setSelectedSheet] = useState<string>('');
  const [isInspecting, setIsInspecting] = useState<boolean>(false);
  const [isImporting, setIsImporting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [isDragging, setIsDragging] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleSelectFile = async (chosenFile?: File) => {
    if (!chosenFile) return;
    setFile(chosenFile);
    setErrorMessage('');
    setIsInspecting(true);

    try {
      const result = await onInspect(chosenFile);
      setInspectData(result);
      if (result.sheets.length > 0) {
        setSelectedSheet(result.sheets[0].name);
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to inspect file.');
    } finally {
      setIsInspecting(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!file || !selectedSheet) return;
    setIsImporting(true);
    setErrorMessage('');
    try {
      await onImport(file, selectedSheet);
      handleClose();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to import sheet.');
    } finally {
      setIsImporting(false);
    }
  };

  const handleClose = () => {
    setFile(null);
    setInspectData(null);
    setSelectedSheet('');
    setErrorMessage('');
    onClose();
  };

  const activeSheetInfo = inspectData?.sheets.find(s => s.name === selectedSheet);

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-xl border border-gray-300 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
        {/* Header */}
        <div className="px-5 py-3.5 bg-brand-navy text-white flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm">{title}</h3>
            <p className="text-xs text-gray-300">{subtitle}</p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="text-gray-300 hover:text-white text-lg font-bold transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 text-xs">
          {errorMessage && (
            <div role="alert" className="p-3 bg-red-50 border border-red-300 rounded text-red-800 flex items-start justify-between">
              <div className="flex items-center gap-2">
                <span className="text-base">⚠️</span>
                <span className="font-medium">{errorMessage}</span>
              </div>
              <button
                type="button"
                onClick={() => setErrorMessage('')}
                className="text-red-500 hover:text-red-700 font-bold ml-2"
              >
                ✕
              </button>
            </div>
          )}

          {children}
          {!file ? (
            <div
              onDragOver={e => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={e => {
                e.preventDefault();
                setIsDragging(false);
                const dropped = e.dataTransfer.files?.[0];
                if (dropped) void handleSelectFile(dropped);
              }}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center text-center transition-colors cursor-pointer ${
                isDragging
                  ? 'border-brand-steel bg-blue-50/70'
                  : 'border-gray-300 bg-gray-50 hover:border-brand-steel hover:bg-gray-100/60'
              }`}
            >
              <span className="text-3xl mb-2">📁</span>
              <p className="font-semibold text-gray-700">Drag & Drop Excel File Here</p>
              <p className="text-gray-400 mt-1">or click to browse from your computer</p>
              <button
                type="button"
                onClick={e => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
                className="mt-3 px-4 py-1.5 bg-brand-navy text-white font-medium rounded shadow-xs cursor-pointer hover:bg-opacity-90"
              >
                Browse File
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) void handleSelectFile(f);
                  e.target.value = '';
                }}
              />
              <p className="text-[11px] text-gray-400 mt-3">Supported formats: .xlsx, .xls, .csv</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* File Card */}
              <div className="flex items-center justify-between p-3 bg-blue-50/60 rounded border border-blue-200">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">📊</span>
                  <div>
                    <p className="font-bold text-gray-800">{file.name}</p>
                    <p className="text-[11px] text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setFile(null);
                    setInspectData(null);
                    setErrorMessage('');
                  }}
                  className="px-2.5 py-1 text-xs text-brand-navy hover:text-brand-steel font-medium border border-gray-300 bg-white rounded hover:bg-gray-50"
                >
                  Change File
                </button>
              </div>

              {isInspecting && (
                <div className="p-4 bg-gray-50 text-gray-700 rounded border border-gray-200 text-center flex items-center justify-center gap-2">
                  <div className="animate-spin h-4 w-4 border-2 border-brand-steel border-t-transparent rounded-full" />
                  <span>Reading and inspecting sheets in {file.name}…</span>
                </div>
              )}

              {inspectData && (
                <div className="space-y-3">
                  <div>
                    <label className="font-bold text-gray-700 block mb-1">Select Sheet to Import:</label>
                    <div className="space-y-1 max-h-36 overflow-y-auto border border-gray-200 rounded p-1.5 bg-white">
                      {inspectData.sheets.map(sheet => (
                        <label
                          key={sheet.name}
                          className={`flex items-center justify-between p-2 rounded cursor-pointer border transition-colors ${
                            selectedSheet === sheet.name
                              ? 'bg-blue-50 border-brand-steel text-brand-navy font-bold'
                              : 'hover:bg-gray-50 border-gray-200 text-gray-700'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <input
                              type="radio"
                              name="sheetChoice"
                              checked={selectedSheet === sheet.name}
                              onChange={() => setSelectedSheet(sheet.name)}
                              className="text-brand-steel"
                            />
                            <span>{sheet.name}</span>
                          </div>
                          <span className="text-gray-400 text-[11px] font-normal">
                            {sheet.row_count} rows • {sheet.column_count} cols
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {activeSheetInfo && (
                    <div className="bg-gray-50 p-2.5 rounded border border-gray-200 space-y-2">
                      <div className="flex justify-between text-gray-600 font-semibold border-b border-gray-200 pb-1">
                        <span>Detected Rows: {activeSheetInfo.row_count}</span>
                        <span>Columns: {activeSheetInfo.column_count}</span>
                      </div>
                      {activeSheetInfo.headers.length > 0 && (
                        <div>
                          <p className="text-[11px] text-gray-500 font-semibold mb-1">Detected Headers:</p>
                          <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                            {activeSheetInfo.headers.map((h, i) => (
                              <span key={i} className="px-1.5 py-0.5 bg-white border border-gray-200 rounded text-[10px] text-gray-700">
                                {h}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-gray-50 border-t border-gray-200 flex justify-end gap-2 text-xs">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-1.5 bg-white border border-gray-300 rounded font-semibold text-gray-700 hover:bg-gray-100"
          >
            Cancel
          </button>
          {inspectData && (
            <button
              type="button"
              onClick={handleConfirmImport}
              disabled={!selectedSheet || isImporting || isLoading}
              className="px-4 py-1.5 bg-brand-navy text-white rounded font-semibold hover:bg-opacity-90 disabled:opacity-50 flex items-center gap-1.5"
            >
              {isImporting ? (
                <>
                  <div className="animate-spin h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full" />
                  <span>Importing…</span>
                </>
              ) : (
                <span>Confirm Import</span>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

