import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';

interface ImportError {
  id: string;
  row_number: number;
  column_name?: string;
  error_code: string;
  error_message: string;
  raw_value?: string;
}

interface ImportBatch {
  id: string;
  planning_version_id?: string;
  filename: string;
  file_size_bytes: number;
  row_count: number;
  valid_row_count: number;
  error_row_count: number;
  status: string;
  uploaded_at: string;
  completed_at?: string;
  errors: ImportError[];
}

interface PlanningVersion {
  id: string;
  planning_period: string;
  version_number: number;
  revision_label: string;
  description?: string;
  source_filename: string;
  status: string;
  created_at: string;
}

interface PRDOrderItem {
  id: string;
  source_row_number: number;
  product_code: string;
  plant_code: string;
  planned_quantity: number;
  uom: string;
  target_period: string;
}

export default function PRDPlanning() {
  const [file, setFile] = useState<File | null>(null);
  const [planningPeriod, setPlanningPeriod] = useState('2026-10');
  const [revisionLabel, setRevisionLabel] = useState('R0');
  const [isUploading, setIsUploading] = useState(false);
  const [isPromoting, setIsPromoting] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const [activeBatch, setActiveBatch] = useState<ImportBatch | null>(null);
  const [batchErrors, setBatchErrors] = useState<ImportError[]>([]);
  const [planningVersions, setPlanningVersions] = useState<PlanningVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [versionItems, setVersionItems] = useState<PRDOrderItem[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiClient.get<PlanningVersion[]>('/api/v1/prd/planning-versions')
      .then(versions => { if (!cancelled) setPlanningVersions(versions); })
      .catch(() => { /* Keep the existing offline behavior. */ });
    return () => { cancelled = true; };
  }, []);

  const fetchPlanningVersions = async () => {
    try {
      const versions = await apiClient.get<PlanningVersion[]>('/api/v1/prd/planning-versions');
      setPlanningVersions(versions);
    } catch {
      // Ignore if offline
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      if (!selected.name.endsWith('.xlsx')) {
        setUploadMessage({ type: 'error', text: 'Only .xlsx files are supported.' });
        setFile(null);
        return;
      }
      setFile(selected);
      setUploadMessage(null);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setUploadMessage({ type: 'error', text: 'Please select a valid .xlsx file.' });
      return;
    }

    setIsUploading(true);
    setUploadMessage(null);
    setActiveBatch(null);
    setBatchErrors([]);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('planning_period', planningPeriod);

    try {
      const batch = await apiClient.postFormData<ImportBatch>('/api/v1/prd/upload', formData);
      setActiveBatch(batch);

      if (batch.status === 'VALIDATED') {
        setUploadMessage({
          type: 'success',
          text: `File "${batch.filename}" parsed successfully! All ${batch.valid_row_count} rows passed staging validation.`,
        });
      } else {
        setUploadMessage({
          type: 'error',
          text: `Validation failed with ${batch.error_row_count} error(s). Review the error table below.`,
        });
        const errs = await apiClient.get<ImportError[]>(`/api/v1/prd/batches/${batch.id}/errors`);
        setBatchErrors(errs);
      }
    } catch (err) {
      setUploadMessage({ type: 'error', text: err instanceof Error ? err.message : 'Upload failed' });
    } finally {
      setIsUploading(false);
    }
  };

  const handlePromote = async () => {
    if (!activeBatch) return;
    setIsPromoting(true);

    const formData = new FormData();
    formData.append('planning_period', planningPeriod);
    formData.append('revision_label', revisionLabel);

    try {
      const res = await apiClient.postFormData<{ revision_label: string; total_line_items: number }>(`/api/v1/prd/batches/${activeBatch.id}/promote`, formData);
      setUploadMessage({
        type: 'success',
        text: `Batch promoted successfully to Planning Version ${res.revision_label}! (${res.total_line_items} canonical items created).`,
      });
      setActiveBatch({ ...activeBatch, status: 'PROMOTED' });
      fetchPlanningVersions();
    } catch (err) {
      setUploadMessage({ type: 'error', text: err instanceof Error ? err.message : 'Promotion failed' });
    } finally {
      setIsPromoting(false);
    }
  };

  const loadVersionItems = async (versionId: string) => {
    setSelectedVersionId(versionId);
    setLoadingItems(true);
    try {
      const items = await apiClient.get<PRDOrderItem[]>(`/api/v1/prd/planning-versions/${versionId}/items`);
      setVersionItems(items);
    } catch {
      setVersionItems([]);
    } finally {
      setLoadingItems(false);
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Page Header */}
      <div>
        <h2 className="text-2xl font-bold text-brand-charcoal">PRD Import & Planning Staging</h2>
        <p className="text-sm text-gray-600 mt-1">
          Upload and safely validate Excel production plans (.xlsx) before promoting them to canonical planning versions.
        </p>
      </div>

      {uploadMessage && (
        <div
          className={`p-4 rounded-md border text-sm ${
            uploadMessage.type === 'success'
              ? 'bg-green-50 border-green-300 text-green-800'
              : 'bg-red-50 border-red-300 text-red-800'
          }`}
        >
          {uploadMessage.text}
        </div>
      )}

      {/* Main Grid: Upload & Staging Console */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Panel 1: File Upload */}
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <h3 className="text-lg font-semibold text-brand-navy mb-4">1. Upload PRD Workbook</h3>
          <form onSubmit={handleUpload} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                Target Planning Period
              </label>
              <input
                type="text"
                placeholder="YYYY-MM (e.g. 2026-10)"
                value={planningPeriod}
                onChange={(e) => setPlanningPeriod(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-steel"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                Revision Label
              </label>
              <input
                type="text"
                placeholder="R0, R1..."
                value={revisionLabel}
                onChange={(e) => setRevisionLabel(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-steel"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 uppercase tracking-wider mb-1">
                Excel File (.xlsx)
              </label>
              <input
                type="file"
                accept=".xlsx"
                onChange={handleFileChange}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm text-gray-600 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200"
                required
              />
              <p className="text-xs text-gray-500 mt-1">Expected: Product Code, Plant Code, Planned Quantity, UOM, Target Period</p>
            </div>

            <button
              type="submit"
              disabled={isUploading || !file}
              className={`w-full py-2.5 px-4 rounded font-medium text-white transition-colors text-sm ${
                isUploading || !file
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-brand-navy hover:bg-brand-steel'
              }`}
            >
              {isUploading ? 'Validating & Staging...' : 'Upload & Validate'}
            </button>
          </form>
        </div>

        {/* Panel 2: Staging Status & Error Review */}
        <div className="lg:col-span-2 bg-white p-6 rounded-lg shadow-sm border border-gray-200 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-brand-navy">2. Staging & Validation Review</h3>
              {activeBatch && (
                <span
                  className={`px-2.5 py-1 rounded text-xs font-bold ${
                    activeBatch.status === 'VALIDATED'
                      ? 'bg-green-100 text-green-800'
                      : activeBatch.status === 'PROMOTED'
                      ? 'bg-blue-100 text-blue-800'
                      : 'bg-red-100 text-red-800'
                  }`}
                >
                  {activeBatch.status}
                </span>
              )}
            </div>

            {!activeBatch ? (
              <div className="text-center py-12 text-gray-400 text-sm">
                No active staging batch. Upload a workbook to review validation results.
              </div>
            ) : (
              <div className="space-y-4">
                {/* Metrics */}
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="p-3 bg-gray-50 rounded border border-gray-200">
                    <div className="text-xs text-gray-500 uppercase font-bold">Total Rows</div>
                    <div className="text-xl font-bold text-gray-800">{activeBatch.row_count}</div>
                  </div>
                  <div className="p-3 bg-green-50 rounded border border-green-200">
                    <div className="text-xs text-green-600 uppercase font-bold">Valid Rows</div>
                    <div className="text-xl font-bold text-green-700">{activeBatch.valid_row_count}</div>
                  </div>
                  <div className="p-3 bg-red-50 rounded border border-red-200">
                    <div className="text-xs text-red-600 uppercase font-bold">Error Rows</div>
                    <div className="text-xl font-bold text-red-700">{activeBatch.error_row_count}</div>
                  </div>
                </div>

                {/* Errors Table if any */}
                {batchErrors.length > 0 && (
                  <div className="mt-4">
                    <h4 className="text-sm font-semibold text-red-700 mb-2">Validation Errors ({batchErrors.length})</h4>
                    <div className="max-h-48 overflow-auto border border-red-200 rounded">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-red-100 text-red-800 uppercase font-bold sticky top-0">
                          <tr>
                            <th className="p-2">Row</th>
                            <th className="p-2">Column</th>
                            <th className="p-2">Code</th>
                            <th className="p-2">Message</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-red-200 bg-white">
                          {batchErrors.map((err) => (
                            <tr key={err.id}>
                              <td className="p-2 font-mono">{err.row_number}</td>
                              <td className="p-2 font-semibold">{err.column_name || '—'}</td>
                              <td className="p-2 font-mono text-red-600">{err.error_code}</td>
                              <td className="p-2 text-gray-700">{err.error_message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Promotion CTA */}
          {activeBatch && activeBatch.status === 'VALIDATED' && (
            <div className="mt-6 pt-4 border-t border-gray-200">
              <button
                type="button"
                onClick={handlePromote}
                disabled={isPromoting}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2.5 px-4 rounded transition-colors text-sm"
              >
                {isPromoting ? 'Promoting...' : `Promote Batch to Planning Version (${revisionLabel})`}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Panel 3: Canonical Planning Versions & PRD Orders */}
      <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <h3 className="text-lg font-semibold text-brand-navy mb-4">3. Active Planning Versions</h3>
        {planningVersions.length === 0 ? (
          <p className="text-sm text-gray-500">No planning versions promoted yet.</p>
        ) : (
          <div className="space-y-6">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left border border-gray-200 rounded">
                <thead className="bg-gray-50 text-gray-700 uppercase text-xs font-semibold">
                  <tr>
                    <th className="p-3">Period</th>
                    <th className="p-3">Revision</th>
                    <th className="p-3">Version #</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Source File</th>
                    <th className="p-3">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {planningVersions.map((v) => (
                    <tr key={v.id} className={selectedVersionId === v.id ? 'bg-blue-50' : 'hover:bg-gray-50'}>
                      <td className="p-3 font-semibold">{v.planning_period}</td>
                      <td className="p-3 font-mono">{v.revision_label}</td>
                      <td className="p-3">{v.version_number}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">
                          {v.status}
                        </span>
                      </td>
                      <td className="p-3 text-gray-600 text-xs">{v.source_filename}</td>
                      <td className="p-3">
                        <button
                          type="button"
                          onClick={() => loadVersionItems(v.id)}
                          className="text-xs text-brand-navy font-semibold underline hover:text-brand-steel"
                        >
                          View Line Items
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Selected Version Line Items Table */}
            {selectedVersionId && (
              <div className="mt-4 border-t border-gray-200 pt-4">
                <h4 className="text-md font-semibold text-brand-charcoal mb-3">
                  Canonical PRD Items for Selected Version
                </h4>
                {loadingItems ? (
                  <p className="text-sm text-gray-500">Loading items...</p>
                ) : versionItems.length === 0 ? (
                  <p className="text-sm text-gray-500">No items found for this planning version.</p>
                ) : (
                  <div className="overflow-x-auto border border-gray-200 rounded max-h-60">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-gray-100 text-gray-700 uppercase font-semibold sticky top-0">
                        <tr>
                          <th className="p-2">Row</th>
                          <th className="p-2">Product Code</th>
                          <th className="p-2">Plant Code</th>
                          <th className="p-2 text-right">Planned Qty</th>
                          <th className="p-2">UOM</th>
                          <th className="p-2">Target Period</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {versionItems.map((item) => (
                          <tr key={item.id} className="hover:bg-gray-50">
                            <td className="p-2 font-mono text-gray-500">{item.source_row_number}</td>
                            <td className="p-2 font-semibold text-gray-900">{item.product_code}</td>
                            <td className="p-2 font-mono">{item.plant_code}</td>
                            <td className="p-2 text-right font-mono font-semibold">{item.planned_quantity}</td>
                            <td className="p-2">{item.uom}</td>
                            <td className="p-2">{item.target_period}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
