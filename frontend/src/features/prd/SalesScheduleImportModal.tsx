import { useEffect, useState } from 'react';
import { apiClient, ApiError } from '../../api/client';

export interface RevisionInfo {
  col_index: number;
  month_label: string;
  planning_period: string;
  revision_label: string;
  schedule_given_on?: string | null;
  month_date?: string | null;
}

export interface BlockInfo {
  block_index: number;
  heading_text: string;
  closing_label: string;
  customer_name?: string | null;
  customer_code?: string | null;
  customer_id?: string | null;
  group_label?: string | null;
  section_type: string;
  part_count: number;
  quantities: Record<string, string>;
  sheet_totals: Record<string, string>;
  reconciliation_ok: boolean;
  reconciliation_diff: Record<string, string>;
  is_mapped: boolean;
}

export interface GrandTotalInfo {
  parts_sum: Record<string, string>;
  sheet_grand_total: Record<string, string>;
  reconciliation_ok: boolean;
  diffs: Record<string, string>;
}

export interface PreviewResponse {
  filename: string;
  sheet_name: string;
  sheet_names: string[];
  header_row_index: number;
  available_revisions: RevisionInfo[];
  active_revisions: RevisionInfo[];
  blocks: BlockInfo[];
  unmapped_aliases: string[];
  grand_total: GrandTotalInfo;
  total_part_rows: number;
  sample_rows: Record<string, any>[];
  can_confirm: boolean;
  warnings: string[];
  errors: string[];
  file_token: string;
}

export interface CustomerMaster {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
}

interface SalesScheduleImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportSuccess: (importedCount: number, sheetName: string) => void;
}

export default function SalesScheduleImportModal({
  isOpen,
  onClose,
  onImportSuccess,
}: SalesScheduleImportModalProps) {
  const [step, setStep] = useState<'upload' | 'preview' | 'mapping'>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);

  // Filter selections
  const [selectedSheet, setSelectedSheet] = useState<string>('');
  const [selectedPeriod, setSelectedPeriod] = useState<string>('');
  const [selectedRevision, setSelectedRevision] = useState<string>('');

  // Alias mappings
  const [customers, setCustomers] = useState<CustomerMaster[]>([]);
  const [aliasMappings, setAliasMappings] = useState<Record<string, string>>({}); // heading -> customer_id

  useEffect(() => {
    if (isOpen) {
      setStep('upload');
      setFile(null);
      setErrorMsg(null);
      setPreviewData(null);
      setAliasMappings({});
      // Fetch customers master for alias mapping
      void (async () => {
        try {
          const list = await apiClient.get<CustomerMaster[]>('/api/v1/masters/customers');
          setCustomers(list.filter(c => c.is_active));
        } catch {
          // ignore
        }
      })();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleUploadFile = async (chosenFile?: File) => {
    const targetFile = chosenFile || file;
    if (!targetFile) {
      setErrorMsg('Please select an Excel file (.xlsx) to upload.');
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);
    try {
      const formData = new FormData();
      formData.append('file', targetFile);
      if (selectedSheet) formData.append('sheet_name', selectedSheet);
      if (selectedPeriod) formData.append('target_period', selectedPeriod);
      if (selectedRevision) formData.append('revision_label', selectedRevision);

      const res = await apiClient.post<PreviewResponse>('/api/v1/prd/workspace/import-preview', formData);
      setPreviewData(res);
      setSelectedSheet(res.sheet_name);
      if (res.available_revisions.length > 0) {
        setSelectedPeriod(res.available_revisions[0].planning_period);
        setSelectedRevision(res.available_revisions[0].revision_label);
      }
      setStep('preview');
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Failed to inspect sales schedule file.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!previewData) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const payload = {
        file_token: previewData.file_token,
        sheet_name: selectedSheet || previewData.sheet_name,
        target_period: selectedPeriod || undefined,
        revision_label: selectedRevision || undefined,
        alias_mappings: Object.keys(aliasMappings).length > 0 ? aliasMappings : undefined,
        mode: 'APPEND',
        reason: 'Confirmed KNL sales schedule import',
      };

      const res = await apiClient.post<{ imported_count: number; sheet_name: string }>(
        '/api/v1/prd/workspace/import-confirm',
        payload
      );

      onImportSuccess(res.imported_count, res.sheet_name);
      onClose();
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Failed to confirm sales schedule import.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveAliasMapping = async (headingText: string, customerId: string) => {
    if (!customerId) return;
    try {
      await apiClient.post('/api/v1/masters/customers/aliases', {
        customer_id: customerId,
        alias_text: headingText,
        group_label: null,
      });

      setAliasMappings(prev => ({ ...prev, [headingText]: customerId }));

      // Re-trigger preview with the new mapping
      if (file) {
        await handleUploadFile(file);
      }
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Failed to create alias mapping.');
    }
  };

  return (
    <div className="fixed inset-0 z-[10000] bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-5xl w-full max-h-[92vh] flex flex-col overflow-hidden border border-gray-200">
        {/* Header */}
        <div className="px-5 py-3.5 bg-brand-navy text-white flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-base font-bold flex items-center gap-2">
              <span>📄</span> KNL Sales Schedule Import (Production Order)
            </h2>
            <p className="text-xs text-blue-200 mt-0.5">
              Deterministic two-pass parser: Customer detection, exact alias matching, reconciliation cross-checks, and revision control.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-white/80 hover:text-white text-xl font-bold p-1 rounded hover:bg-white/10"
          >
            ✕
          </button>
        </div>

        {errorMsg && (
          <div className="mx-5 mt-3 p-3 bg-red-50 border border-red-300 text-red-800 rounded-lg text-xs flex items-start gap-2">
            <span>⚠️</span>
            <div className="flex-1">{errorMsg}</div>
            <button onClick={() => setErrorMsg(null)} className="font-bold text-red-500">✕</button>
          </div>
        )}

        {/* Content Body */}
        <div className="flex-1 min-h-0 overflow-y-auto p-5 space-y-4">
          {step === 'upload' && (
            <div className="space-y-4">
              {/* Dropzone */}
              <div
                onDragOver={e => e.preventDefault()}
                onDrop={e => {
                  e.preventDefault();
                  if (e.dataTransfer.files?.[0]) {
                    const f = e.dataTransfer.files[0];
                    setFile(f);
                    void handleUploadFile(f);
                  }
                }}
                className="border-2 border-dashed border-gray-300 hover:border-brand-steel rounded-xl p-8 text-center cursor-pointer bg-gray-50/50 hover:bg-blue-50/30 transition-all flex flex-col items-center justify-center space-y-3"
                onClick={() => {
                  const input = document.createElement('input');
                  input.type = 'file';
                  input.accept = '.xlsx';
                  input.onchange = e => {
                    const f = (e.target as HTMLInputElement).files?.[0];
                    if (f) {
                      setFile(f);
                      void handleUploadFile(f);
                    }
                  };
                  input.click();
                }}
              >
                <div className="w-14 h-14 rounded-full bg-blue-100 text-brand-navy flex items-center justify-center text-2xl font-bold">
                  📊
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-800">
                    {file ? file.name : 'Click to select or drag & drop Sales Schedule (.xlsx)'}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Supports KNL hierarchical Sales Schedule ("Pro.Order.pdf" layout) with Ashok Leyland, TAFE, TVS, Job Work, and R0/R1 revisions.
                  </p>
                </div>
                {file && (
                  <span className="text-xs font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                    {(file.size / 1024).toFixed(1)} KB
                  </span>
                )}
              </div>

              {/* Rules & Layout Info */}
              <div className="bg-amber-50/70 border border-amber-200 rounded-lg p-3.5 text-xs text-amber-900 space-y-1.5">
                <p className="font-bold flex items-center gap-1.5">
                  <span>ℹ️</span> KNL File Layout Verification Rules:
                </p>
                <ul className="list-disc list-inside space-y-1 text-amber-800/90 pl-1">
                  <li><strong>First block:</strong> Ashok Leyland is identified by its closing row <code>ASHOK LEYLAND - TOTAL</code>.</li>
                  <li><strong>Section headings:</strong> Converted to first-class <code>Customer</code>, <code>Customer ID</code>, and <code>Group</code> columns on every row.</li>
                  <li><strong>Reconciliation:</strong> Block part quantities must match closing subtotal rows; Grand Total row cross-checked.</li>
                  <li><strong>Value columns:</strong> INR / Lakhs / Value columns are skipped; only physical quantities are imported.</li>
                  <li><strong>Revisions:</strong> R0 and R1 are preserved as separate records and never summed together.</li>
                </ul>
              </div>
            </div>
          )}

          {step === 'preview' && previewData && (
            <div className="space-y-4">
              {/* Summary Metrics Bar */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-center">
                  <div className="text-[11px] text-blue-700 font-semibold uppercase tracking-wider">Customer Blocks</div>
                  <div className="text-xl font-bold text-blue-900 mt-0.5">{previewData.blocks.length}</div>
                  <div className="text-[10px] text-blue-600">All detected</div>
                </div>
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-center">
                  <div className="text-[11px] text-emerald-700 font-semibold uppercase tracking-wider">Part Rows</div>
                  <div className="text-xl font-bold text-emerald-900 mt-0.5">{previewData.total_part_rows}</div>
                  <div className="text-[10px] text-emerald-600">Across active revisions</div>
                </div>
                <div className={`border rounded-lg p-3 text-center ${
                  previewData.grand_total.reconciliation_ok
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                    : 'bg-amber-50 border-amber-200 text-amber-900'
                }`}>
                  <div className="text-[11px] font-semibold uppercase tracking-wider">Reconciliation</div>
                  <div className="text-xl font-bold mt-0.5">
                    {previewData.grand_total.reconciliation_ok ? 'VERIFIED ✓' : 'MISMATCH ⚠️'}
                  </div>
                  <div className="text-[10px] opacity-80">
                    Grand Total check: {previewData.grand_total.reconciliation_ok ? 'Sum equals sheet' : 'Discrepancy flagged'}
                  </div>
                </div>
                <div className={`border rounded-lg p-3 text-center ${
                  previewData.unmapped_aliases.length === 0
                    ? 'bg-blue-50 border-blue-200 text-blue-900'
                    : 'bg-red-50 border-red-200 text-red-900'
                }`}>
                  <div className="text-[11px] font-semibold uppercase tracking-wider">Alias Mapping</div>
                  <div className="text-xl font-bold mt-0.5">
                    {previewData.unmapped_aliases.length === 0 ? '100% Mapped' : `${previewData.unmapped_aliases.length} Unknown`}
                  </div>
                  <div className="text-[10px]">
                    {previewData.unmapped_aliases.length === 0 ? 'Ready for import' : 'Action required'}
                  </div>
                </div>
              </div>

              {/* Revision & Sheet Selector */}
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex flex-wrap items-center gap-3">
                  {previewData.sheet_names.length > 1 && (
                    <label className="font-semibold text-gray-700 flex items-center gap-1.5">
                      Sheet:
                      <select
                        value={selectedSheet}
                        onChange={e => {
                          setSelectedSheet(e.target.value);
                          void handleUploadFile();
                        }}
                        className="px-2 py-1 border rounded bg-white text-xs font-medium"
                      >
                        {previewData.sheet_names.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </label>
                  )}

                  {previewData.available_revisions.length > 0 && (
                    <>
                      <label className="font-semibold text-gray-700 flex items-center gap-1.5">
                        Month:
                        <select
                          value={selectedPeriod}
                          onChange={e => setSelectedPeriod(e.target.value)}
                          className="px-2 py-1 border rounded bg-white text-xs font-medium"
                        >
                          {Array.from(new Set(previewData.available_revisions.map(r => r.planning_period))).map(p => (
                            <option key={p} value={p}>{p}</option>
                          ))}
                        </select>
                      </label>

                      <label className="font-semibold text-gray-700 flex items-center gap-1.5">
                        Revision:
                        <select
                          value={selectedRevision}
                          onChange={e => setSelectedRevision(e.target.value)}
                          className="px-2 py-1 border rounded bg-white text-xs font-medium"
                        >
                          {previewData.available_revisions
                            .filter(r => !selectedPeriod || r.planning_period === selectedPeriod)
                            .map(r => (
                              <option key={r.revision_label} value={r.revision_label}>
                                {r.revision_label} ({r.month_label})
                              </option>
                            ))}
                        </select>
                      </label>
                    </>
                  )}
                </div>

                <div className="text-gray-500 font-mono text-[11px]">
                  File: {previewData.filename}
                </div>
              </div>

              {/* Unmapped Aliases Resolver Card */}
              {previewData.unmapped_aliases.length > 0 && (
                <div className="bg-red-50 border border-red-300 rounded-lg p-3.5 space-y-3">
                  <div className="flex items-center gap-2 text-red-900 font-bold text-xs">
                    <span>⚠️</span>
                    <span>Unknown Company Headings Detected ({previewData.unmapped_aliases.length})</span>
                  </div>
                  <p className="text-xs text-red-700">
                    KNL requires exact, deterministic customer alias matching. Please map each detected heading to its Customer Master record before proceeding:
                  </p>

                  <div className="space-y-2">
                    {previewData.unmapped_aliases.map(heading => (
                      <div key={heading} className="flex flex-wrap items-center justify-between gap-2 p-2 bg-white border border-red-200 rounded text-xs">
                        <span className="font-mono font-bold text-gray-900">"{heading}"</span>
                        <div className="flex items-center gap-2">
                          <select
                            value={aliasMappings[heading] || ''}
                            onChange={e => setAliasMappings(prev => ({ ...prev, [heading]: e.target.value }))}
                            className="px-2 py-1 border border-gray-300 rounded bg-white text-xs"
                          >
                            <option value="">Select Customer Master…</option>
                            {customers.map(c => (
                              <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
                            ))}
                          </select>
                          <button
                            type="button"
                            disabled={!aliasMappings[heading]}
                            onClick={() => handleSaveAliasMapping(heading, aliasMappings[heading])}
                            className="px-2.5 py-1 bg-brand-navy disabled:opacity-40 text-white rounded font-semibold text-xs shadow-2xs"
                          >
                            Map & Save
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Customer Blocks & Reconciliation Breakdown Table */}
              <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-2xs">
                <div className="px-3 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between text-xs">
                  <span className="font-bold text-gray-800">Detected Customer Blocks & Reconciliation</span>
                  <span className="text-gray-500">{previewData.blocks.length} blocks found</span>
                </div>
                <div className="max-h-56 overflow-y-auto">
                  <table className="w-full text-xs text-left border-collapse">
                    <thead className="bg-gray-100 text-gray-700 sticky top-0 z-10 border-b">
                      <tr>
                        <th className="p-2 text-center w-10">#</th>
                        <th className="p-2">Section / Heading</th>
                        <th className="p-2">Customer Master</th>
                        <th className="p-2">Group</th>
                        <th className="p-2 text-center">Parts</th>
                        <th className="p-2 text-right">Parts Sum</th>
                        <th className="p-2 text-right">Sheet Total</th>
                        <th className="p-2 text-center">Reconciliation</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {previewData.blocks.map(b => (
                        <tr key={b.block_index} className="hover:bg-gray-50/80">
                          <td className="p-2 text-center text-gray-400 font-mono">{b.block_index}</td>
                          <td className="p-2 font-semibold text-gray-900">
                            {b.heading_text}
                            {b.section_type === 'JOB_WORK' && (
                              <span className="ml-1.5 px-1.5 py-0.2 bg-purple-100 text-purple-800 text-[10px] font-bold rounded">
                                Job Work
                              </span>
                            )}
                          </td>
                          <td className="p-2">
                            {b.customer_name ? (
                              <span className="text-emerald-800 font-semibold">{b.customer_name} ({b.customer_code})</span>
                            ) : (
                              <span className="text-red-700 font-bold bg-red-50 px-1.5 py-0.5 rounded border border-red-200">
                                Unmapped
                              </span>
                            )}
                          </td>
                          <td className="p-2 text-gray-600">{b.group_label || '—'}</td>
                          <td className="p-2 text-center font-mono font-medium">{b.part_count}</td>
                          <td className="p-2 text-right font-mono font-bold text-gray-900">
                            {Object.values(b.quantities)[0] || '0.0000'}
                          </td>
                          <td className="p-2 text-right font-mono text-gray-600">
                            {Object.values(b.sheet_totals)[0] || '—'}
                          </td>
                          <td className="p-2 text-center">
                            {b.reconciliation_ok ? (
                              <span className="text-emerald-700 font-semibold">OK ✓</span>
                            ) : (
                              <span className="text-amber-700 font-bold">Diff: {Object.values(b.reconciliation_diff)[0]}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Data Preview Table (First 50 Rows with Customer Columns) */}
              <div className="border border-gray-200 rounded-lg overflow-hidden bg-white shadow-2xs">
                <div className="px-3 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between text-xs">
                  <span className="font-bold text-gray-800">
                    Flat Grid Data Preview (First 50 rows showing Customer columns)
                  </span>
                  <span className="text-gray-500">Every row has distinct Customer & Customer ID</span>
                </div>
                <div className="max-h-60 overflow-auto">
                  <table className="w-full text-xs text-left border-collapse table-fixed">
                    <thead className="bg-gray-100 text-gray-700 sticky top-0 z-10 border-b">
                      <tr>
                        <th className="p-2 w-12 text-center">Row</th>
                        <th className="p-2 w-32">Customer</th>
                        <th className="p-2 w-28">Customer ID</th>
                        <th className="p-2 w-24">Group</th>
                        <th className="p-2 w-32">Part No.</th>
                        <th className="p-2 w-28">Item ID</th>
                        <th className="p-2 w-48">Description</th>
                        <th className="p-2 w-24 text-right">Plan Qty</th>
                        <th className="p-2 w-16 text-center">Unit</th>
                        <th className="p-2 w-20 text-center">Rev</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 font-mono text-[11px]">
                      {previewData.sample_rows.map((r, rIdx) => (
                        <tr key={rIdx} className="hover:bg-blue-50/40">
                          <td className="p-2 text-center text-gray-400">{r.source_row}</td>
                          <td className="p-2 font-bold text-blue-900 truncate font-sans">{r.customer}</td>
                          <td className="p-2 text-gray-700 font-bold">{r.customer_code || '—'}</td>
                          <td className="p-2 text-gray-600 font-sans">{r.customer_group || '—'}</td>
                          <td className="p-2 text-gray-900 font-bold">{r.part_no || r.product_code}</td>
                          <td className="p-2 text-gray-500">{r.item_id || '—'}</td>
                          <td className="p-2 text-gray-800 font-sans truncate">{r.description}</td>
                          <td className="p-2 text-right font-bold text-gray-900">{r.planned_quantity}</td>
                          <td className="p-2 text-center text-gray-600">{r.uom}</td>
                          <td className="p-2 text-center text-indigo-700 font-bold">{r.revision}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between flex-shrink-0">
          <div>
            {step === 'preview' && (
              <button
                type="button"
                onClick={() => setStep('upload')}
                className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-xs font-semibold"
              >
                ← Back to Upload
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 bg-white hover:bg-gray-100 border border-gray-300 text-gray-700 rounded-lg text-xs font-semibold"
            >
              Cancel
            </button>

            {step === 'preview' && previewData && (
              <button
                type="button"
                disabled={!previewData.can_confirm || isLoading}
                onClick={handleConfirmImport}
                className="px-5 py-1.5 bg-brand-navy hover:bg-opacity-95 disabled:opacity-40 text-white rounded-lg text-xs font-bold shadow-xs transition-colors flex items-center gap-1.5"
              >
                {isLoading ? (
                  <>
                    <div className="animate-spin h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full" />
                    <span>Importing…</span>
                  </>
                ) : (
                  <>
                    <span>Confirm Import ({previewData.total_part_rows} parts)</span>
                    <span>→</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

