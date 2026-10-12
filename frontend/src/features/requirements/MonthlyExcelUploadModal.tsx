import { useRef, useState } from 'react';
import { apiClient } from '../../api/client';

export interface RowError {
  row_number: number;
  column_name: string;
  error_description: string;
}

export interface InspectExcelResponse {
  filename: string;
  total_rows: number;
  valid_rows: number;
  error_count: number;
  planning_month: number;
  planning_year: number;
  planning_period: string;
  plan_already_exists: boolean;
  errors: RowError[];
  preview_rows: Array<{
    row_index: number;
    part_name: string;
    part_number: string;
    consumable_code: string;
    consumable_name: string;
    process_name: string;
    part_thickness: string;
    process_count: number;
    production_order_qty: string;
    scheduled_consumable_qty: string;
    is_valid: boolean;
    errors: string[];
  }>;
}

interface MonthlyExcelUploadModalProps {
  isOpen: boolean;
  planningMonth: number;
  planningYear: number;
  monthName: string;
  onClose: () => void;
  onImportSuccess: (message: string) => void;
}

export default function MonthlyExcelUploadModal({
  isOpen,
  planningMonth,
  planningYear,
  monthName,
  onClose,
  onImportSuccess,
}: MonthlyExcelUploadModalProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isInspecting, setIsInspecting] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [inspectResult, setInspectResult] = useState<InspectExcelResponse | null>(null);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleSelectFile = async (chosenFile?: File) => {
    if (!chosenFile) return;
    setErrorMessage('');
    setIsInspecting(true);
    setInspectResult(null);
    setConfirmOverwrite(false);

    try {
      const formData = new FormData();
      formData.append('file', chosenFile);
      formData.append('month', String(planningMonth));
      formData.append('year', String(planningYear));

      const res = await apiClient.post<InspectExcelResponse>(
        '/api/v1/requirements/workspace/inspect-excel',
        formData
      );
      setInspectResult(res);
      if (res.plan_already_exists) {
        setConfirmOverwrite(true);
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to inspect Excel file.');
    } finally {
      setIsInspecting(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!inspectResult) return;
    setIsImporting(true);
    setErrorMessage('');

    try {
      await apiClient.post('/api/v1/requirements/workspace/import', {
        planning_month: planningMonth,
        planning_year: planningYear,
        source_filename: inspectResult.filename,
        records: inspectResult.preview_rows,
        overwrite: confirmOverwrite,
      });

      onImportSuccess(
        `Successfully imported ${inspectResult.valid_rows} records for ${monthName} ${planningYear}.`
      );
      handleClose();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Import failed.');
    } finally {
      setIsImporting(false);
    }
  };

  const handleClose = () => {
    setInspectResult(null);
    setErrorMessage('');
    setConfirmOverwrite(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4">
      <div className="bg-white rounded-lg shadow-2xl border border-gray-300 w-full max-w-4xl max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-100">
        {/* Header */}
        <div className="px-6 py-3.5 bg-brand-navy text-white flex items-center justify-between">
          <div>
            <h3 className="font-bold text-sm tracking-wide">
              Upload Monthly Production & Consumable Plan
            </h3>
            <p className="text-xs text-gray-300 mt-0.5">
              Target Period:{' '}
              <span className="font-semibold text-white">
                {monthName} {planningYear}
              </span>{' '}
              · Validated deterministic KNL consumable requirements import
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="text-gray-300 hover:text-white font-bold text-lg p-1"
          >
            ✕
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4 text-xs">
          {errorMessage && (
            <div className="p-3 bg-red-50 text-red-800 border border-red-200 rounded flex items-center justify-between">
              <span>⚠️ {errorMessage}</span>
              <button
                type="button"
                onClick={() => setErrorMessage('')}
                className="font-bold text-gray-500 hover:text-gray-800"
              >
                ✕
              </button>
            </div>
          )}

          {/* Step 1 & 2: Dropzone / File Picker */}
          {!inspectResult && (
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
              className={`border-2 border-dashed rounded-lg p-8 flex flex-col items-center justify-center gap-3 transition-colors ${
                isDragging
                  ? 'border-brand-steel bg-blue-50/50'
                  : 'border-gray-300 hover:border-gray-400 bg-gray-50/50'
              }`}
            >
              <div className="text-4xl text-gray-400">📊</div>
              <div className="text-center">
                <p className="text-sm font-semibold text-gray-800">
                  Drag & Drop Excel File Here
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Supported formats: <strong>.xlsx</strong>, <strong>.xls</strong> · Expected headers: Used For – Part Name, Used Part No., Consumable Item ID, Production Order Qty
                </p>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                onChange={e => {
                  const f = e.target.files?.[0];
                  if (f) void handleSelectFile(f);
                }}
              />

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isInspecting}
                className="mt-2 px-4 py-2 bg-brand-navy hover:bg-opacity-90 text-white rounded font-medium shadow-xs text-xs flex items-center gap-2"
              >
                {isInspecting ? (
                  <>
                    <div className="animate-spin h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full" />
                    <span>Inspecting & Validating…</span>
                  </>
                ) : (
                  <span>📁 Browse File</span>
                )}
              </button>
            </div>
          )}

          {/* Step 3 & 4: Inspection & Validation Preview */}
          {inspectResult && (
            <div className="space-y-4">
              {/* Validation Summary Bar */}
              <div className="grid grid-cols-4 gap-3">
                <div className="p-3 bg-gray-50 border border-gray-200 rounded">
                  <div className="text-gray-500 text-2xs uppercase font-bold">File</div>
                  <div className="text-xs font-semibold text-gray-900 truncate mt-0.5">
                    {inspectResult.filename}
                  </div>
                </div>
                <div className="p-3 bg-gray-50 border border-gray-200 rounded">
                  <div className="text-gray-500 text-2xs uppercase font-bold">Total Rows</div>
                  <div className="text-sm font-bold text-gray-900 mt-0.5">
                    {inspectResult.total_rows}
                  </div>
                </div>
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded">
                  <div className="text-emerald-700 text-2xs uppercase font-bold">Valid Rows</div>
                  <div className="text-sm font-bold text-emerald-800 mt-0.5">
                    {inspectResult.valid_rows}
                  </div>
                </div>
                <div
                  className={`p-3 border rounded ${
                    inspectResult.error_count > 0
                      ? 'bg-red-50 border-red-200 text-red-800'
                      : 'bg-gray-50 border-gray-200 text-gray-800'
                  }`}
                >
                  <div className="text-2xs uppercase font-bold">Validation Errors</div>
                  <div className="text-sm font-bold mt-0.5">
                    {inspectResult.error_count}
                  </div>
                </div>
              </div>

              {/* Overwrite Confirmation Alert */}
              {inspectResult.plan_already_exists && (
                <div className="p-3 bg-amber-50 border border-amber-300 rounded text-amber-900 flex items-start gap-2">
                  <span className="text-base">⚠️</span>
                  <div>
                    <div className="font-bold text-xs">
                      Existing Plan Detected for {monthName} {planningYear}
                    </div>
                    <p className="text-xs text-amber-800 mt-0.5">
                      A requirement plan already exists for this period. Confirming import will create a new revision and update the active records safely.
                    </p>
                    <label className="flex items-center gap-2 mt-2 font-semibold text-xs cursor-pointer">
                      <input
                        type="checkbox"
                        checked={confirmOverwrite}
                        onChange={e => setConfirmOverwrite(e.target.checked)}
                        className="rounded text-amber-600"
                      />
                      <span>I confirm overwriting/updating the existing {monthName} {planningYear} plan</span>
                    </label>
                  </div>
                </div>
              )}

              {/* Row-by-Row Error List if any */}
              {inspectResult.errors.length > 0 && (
                <div className="border border-red-200 rounded bg-red-50/50 p-3 max-h-36 overflow-y-auto space-y-1">
                  <div className="font-bold text-red-900 text-xs mb-1.5 flex items-center gap-1">
                    <span>⚠️</span>
                    <span>Validation Issues ({inspectResult.errors.length})</span>
                  </div>
                  {inspectResult.errors.map((err, idx) => (
                    <div key={idx} className="text-red-700 text-2xs font-mono flex items-start gap-2">
                      <span className="font-bold bg-red-100 px-1 rounded">Row {err.row_number}</span>
                      <span className="font-semibold">{err.column_name}:</span>
                      <span>{err.error_description}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Spreadsheet-style Preview Table with Section 7A headers */}
              <div className="border border-gray-300 rounded overflow-hidden max-h-64 overflow-y-auto bg-white">
                <table className="w-full border-collapse text-left text-2xs">
                  <thead>
                    {/* Group Headers */}
                    <tr className="sticky top-0 z-20 bg-brand-navy text-white text-[10px]">
                      <th className="p-1 border-r border-navy-800 text-center w-8">#</th>
                      <th colSpan={2} className="p-1 border-r border-navy-800 text-center uppercase font-bold">
                        FOR COMPONENT
                      </th>
                      <th colSpan={7} className="p-1 text-center uppercase font-bold bg-steel-800">
                        FOR CONSUMABLES
                      </th>
                    </tr>
                    {/* Sub Headers */}
                    <tr className="sticky top-6 z-20 bg-gray-100 border-b border-gray-300 font-semibold text-gray-700">
                      <th className="p-1 border-r border-gray-200 text-center w-8">#</th>
                      <th className="p-1.5 border-r border-gray-200 w-32">Used For – Part Name</th>
                      <th className="p-1.5 border-r border-gray-200 w-32">Used Part No.</th>
                      <th className="p-1.5 border-r border-gray-200 w-28">Consumable Item ID</th>
                      <th className="p-1.5 border-r border-gray-200 w-36">Consumable Name</th>
                      <th className="p-1.5 border-r border-gray-200 w-24">Process</th>
                      <th className="p-1.5 border-r border-gray-200 text-right w-16">Thk (mm)</th>
                      <th className="p-1.5 border-r border-gray-200 text-center w-12">Proc #</th>
                      <th className="p-1.5 border-r border-gray-200 text-right w-24">Prod Qty</th>
                      <th className="p-1.5 text-center w-16">Valid?</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inspectResult.preview_rows.map((row, rIdx) => (
                      <tr
                        key={rIdx}
                        className={`border-b border-gray-100 ${
                          !row.is_valid
                            ? 'bg-red-50/70 text-red-900 font-medium'
                            : rIdx % 2 === 1
                            ? 'bg-gray-50/60'
                            : 'bg-white'
                        }`}
                      >
                        <td className="p-1 text-center border-r border-gray-200">{rIdx + 1}</td>
                        <td className="p-1.5 border-r border-gray-200 truncate">{row.part_name}</td>
                        <td className="p-1.5 border-r border-gray-200 font-mono">{row.part_number}</td>
                        <td className="p-1.5 border-r border-gray-200 font-mono font-bold text-blue-900">
                          {row.consumable_code}
                        </td>
                        <td className="p-1.5 border-r border-gray-200 truncate">{row.consumable_name}</td>
                        <td className="p-1.5 border-r border-gray-200">{row.process_name}</td>
                        <td className="p-1.5 border-r border-gray-200 text-right font-mono">{row.part_thickness}</td>
                        <td className="p-1.5 border-r border-gray-200 text-center font-mono">{row.process_count}</td>
                        <td className="p-1.5 border-r border-gray-200 text-right font-mono font-bold">
                          {row.production_order_qty}
                        </td>
                        <td className="p-1.5 text-center">
                          {row.is_valid ? (
                            <span className="text-emerald-700 font-bold">✓ Valid</span>
                          ) : (
                            <span className="text-red-700 font-bold" title={row.errors.join(', ')}>
                              ✕ Error
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="px-6 py-3.5 bg-gray-50 border-t border-gray-200 flex items-center justify-between">
          <div>
            {inspectResult && (
              <button
                type="button"
                onClick={() => setInspectResult(null)}
                className="text-xs text-gray-600 hover:text-gray-900 font-medium"
              >
                ← Choose different file
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-1.5 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded font-medium text-xs transition-colors"
            >
              Cancel
            </button>
            {inspectResult && (
              <button
                type="button"
                onClick={handleConfirmImport}
                disabled={isImporting || (inspectResult.plan_already_exists && !confirmOverwrite)}
                className="px-4 py-1.5 bg-brand-navy hover:bg-opacity-90 disabled:opacity-50 text-white rounded font-medium text-xs transition-colors shadow-xs flex items-center gap-2"
              >
                {isImporting ? (
                  <>
                    <div className="animate-spin h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full" />
                    <span>Saving plan…</span>
                  </>
                ) : (
                  <span>Confirm Import ({inspectResult.valid_rows} rows)</span>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
