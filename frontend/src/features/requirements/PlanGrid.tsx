import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  Upload,
  FileSpreadsheet,
  Search,
  Loader2,
  PackageCheck,
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  FileText,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { useAuth } from '../auth/context';
import {
  uploadGRNFile,
  type MonthlyRequirementPlan,
  type RequirementLineItem,
  type UpdateLineItemPayload,
  type GRNUploadResponse,
} from './api';

interface PlanGridProps {
  plan: MonthlyRequirementPlan | null;
  items: RequirementLineItem[];
  loading?: boolean;
  uploading?: boolean;
  onUpload: (file: File, uploadAllPlants?: boolean) => Promise<void>;
  onUploadGRN?: (file: File) => Promise<GRNUploadResponse | void>;
  onAddItem?: () => void;
  onUpdateItem?: (itemId: string, data: UpdateLineItemPayload) => Promise<void>;
  onDeleteItem?: (itemId: string) => Promise<void>;
  canUpload?: boolean;
  canEdit?: boolean;
}

export const PlanGrid: React.FC<PlanGridProps> = ({
  plan,
  items,
  loading = false,
  uploading = false,
  onUpload,
  onUploadGRN,
  onAddItem,
  onUpdateItem,
  onDeleteItem,
  canUpload = true,
  canEdit = true,
}) => {
  const { user } = useAuth();
  const isAdminOrPlanner = Boolean(
    user?.is_super_admin ||
    user?.is_superuser ||
    user?.roles?.includes('ADMIN') ||
    user?.roles?.includes('PLANNER') ||
    user?.roles?.includes('MATERIALS_PLANNER') ||
    user?.role === 'ADMIN' ||
    user?.role === 'PLANNER' ||
    user?.role === 'MATERIALS_PLANNER'
  );

  const fileInputRef = useRef<HTMLInputElement>(null);
  const modalFileInputRef = useRef<HTMLInputElement>(null);
  const grnFileInputRef = useRef<HTMLInputElement>(null);

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadAllPlants, setUploadAllPlants] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isModalUploading, setIsModalUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // GRN Modal State
  const [isGrnModalOpen, setIsGrnModalOpen] = useState(false);
  const [selectedGrnFile, setSelectedGrnFile] = useState<File | null>(null);
  const [isGrnUploading, setIsGrnUploading] = useState(false);
  const [grnUploadResult, setGrnUploadResult] = useState<GRNUploadResponse | null>(null);
  const [grnError, setGrnError] = useState<string | null>(null);

  const resetUploadModalState = () => {
    setSelectedFile(null);
    setIsModalUploading(false);
    if (modalFileInputRef.current) {
      modalFileInputRef.current.value = '';
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const resetGrnModalState = () => {
    setSelectedGrnFile(null);
    setIsGrnUploading(false);
    setGrnUploadResult(null);
    setGrnError(null);
    if (grnFileInputRef.current) {
      grnFileInputRef.current.value = '';
    }
  };

  // Explicitly reset upload state whenever plan ID or plant ID changes
  useEffect(() => {
    resetUploadModalState();
    resetGrnModalState();
  }, [plan?.id, plan?.plant_id]);

  // Inline editing state
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editQty, setEditQty] = useState<number | string>('');
  const [editPartNo, setEditPartNo] = useState<string>('');
  const [editDesc, setEditDesc] = useState<string>('');
  const [editReason, setEditReason] = useState<string>('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null);

  const startEdit = (item: RequirementLineItem) => {
    setEditingItemId(item.id);
    setEditQty(item.requested_qty);
    setEditPartNo(item.part_no || '');
    setEditDesc(item.consumable_name || item.description || '');
    setEditReason(item.modification_reason || '');
  };

  const cancelEdit = () => {
    setEditingItemId(null);
    setEditQty('');
    setEditPartNo('');
    setEditDesc('');
    setEditReason('');
  };

  const saveEdit = async (itemId: string) => {
    if (!onUpdateItem) return;
    const num = Number(editQty);
    if (isNaN(num) || num < 0) return;
    setSavingEdit(true);
    try {
      await onUpdateItem(itemId, {
        requested_qty: num,
        part_no: editPartNo,
        item_description: editDesc,
        modification_reason: editReason.trim() || undefined,
      });
      setEditingItemId(null);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDelete = async (itemId: string) => {
    if (!onDeleteItem) return;
    setDeletingItemId(itemId);
    try {
      await onDeleteItem(itemId);
    } finally {
      setDeletingItemId(null);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await onUpload(file);
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleConfirmModalUpload = async () => {
    if (!selectedFile) return;
    console.log(
      '[BULK UPLOAD] Triggered with planId:',
      plan?.id,
      'file:',
      selectedFile.name,
      'uploadAllPlants:',
      uploadAllPlants
    );
    setIsModalUploading(true);
    try {
      await onUpload(selectedFile, uploadAllPlants);
      setIsUploadModalOpen(false);
      resetUploadModalState();
    } catch (err) {
      // In case of error, do not leave the upload button stuck in uploading state
      setIsModalUploading(false);
      throw err;
    } finally {
      setIsModalUploading(false);
    }
  };

  const handleConfirmGrnUpload = async () => {
    if (!selectedGrnFile) return;
    setIsGrnUploading(true);
    setGrnError(null);
    try {
      if (onUploadGRN) {
        const res = await onUploadGRN(selectedGrnFile);
        if (res && typeof res === 'object' && 'grn_no' in res) {
          setGrnUploadResult(res as GRNUploadResponse);
        } else {
          setIsGrnModalOpen(false);
          resetGrnModalState();
        }
      } else {
        const res = await uploadGRNFile(selectedGrnFile, plan?.month, plan?.year);
        setGrnUploadResult(res);
      }
    } catch (err: unknown) {
      let msg = 'GRN upload failed';
      if (axios.isAxiosError(err)) {
        msg = err.response?.data?.detail || err.response?.data?.message || err.message || msg;
      } else if (err instanceof Error) {
        msg = err.message;
      }
      setGrnError(msg);
    } finally {
      setIsGrnUploading(false);
    }
  };

  const filteredItems = items.filter((item) => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    const code = (item.item_id || item.item_code || item.consumable_id || '').toLowerCase();
    const name = (item.consumable_name || item.description || '').toLowerCase();
    const part = (item.part_no || '').toLowerCase();
    return code.includes(query) || name.includes(query) || part.includes(query);
  });

  const totalRequestedQty = items.reduce((acc, it) => acc + (Number(it.requested_qty) || 0), 0);
  const totalOrderValue = items.reduce((acc, it) => {
    const rate = Number(it.rate || it.latest_grn_rate || 0);
    const qty = Number(it.approved_qty || it.requested_qty || 0);
    const val = Number(it.order_value) || (qty * rate);
    return acc + (val > 0 ? val : 0);
  }, 0);
  const totalReceiptValue = items.reduce((acc, it) => {
    const rate = Number(it.rate || it.latest_grn_rate || 0);
    const qty = Number(it.receipt_qty || 0);
    const val = Number(it.receipt_value) || (qty * rate);
    return acc + (val > 0 ? val : 0);
  }, 0);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden flex flex-col">
      {/* Grid Toolbar */}
      <div className="p-4 border-b border-gray-200 bg-white flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-orange-50 text-erp-orange rounded-lg border border-orange-100">
            <FileSpreadsheet className="w-5 h-5 text-orange-600" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-gray-900 tracking-tight">Requirement Line Items</h2>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-200">
                {items.length} {items.length === 1 ? 'item' : 'items'}
              </span>
              {(() => {
                const modCount = items.filter(
                  (it) => it.is_modified || (Number(it.formula_qty || 0) > 0 && Math.abs((Number(it.requested_qty) || 0) - Number(it.formula_qty)) > 0.0001)
                ).length;
                if (modCount === 0) return null;
                return (
                  <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 shadow-2xs">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
                    {modCount} {modCount === 1 ? 'item modified' : 'items modified'} by plant
                  </span>
                );
              })()}
            </div>
            <p className="text-xs text-gray-500">
              Total Requested QTY:{' '}
              <span className="font-semibold text-gray-800">
                {totalRequestedQty.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
              </span>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          {/* Search Input */}
          <div className="relative flex-1 sm:w-56">
            <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              placeholder="Search code or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 transition-colors"
            />
          </div>

          {/* Hidden File Input (direct test/legacy trigger) */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".xlsx,.xls,.csv"
            className="hidden"
            data-testid="plan-file-input"
          />

          {/* Action: Add Item (Single Intake) */}
          {onAddItem && (
            <button
              type="button"
              onClick={onAddItem}
              disabled={plan?.status === 'APPROVED' || !canEdit || loading}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer ${
                plan?.status === 'APPROVED' || !canEdit || loading
                  ? 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed shadow-none'
                  : 'bg-white hover:bg-gray-50 text-gray-800 border border-gray-300'
              }`}
            >
              <Plus className="w-3.5 h-3.5 text-orange-600" />
              <span>+ Add Item</span>
            </button>
          )}

          {/* Action: Bulk Upload Button */}
          <button
            type="button"
            onClick={() => setIsUploadModalOpen(true)}
            disabled={plan?.status === 'APPROVED' || !canUpload || uploading || loading}
            title={
              plan?.status === 'APPROVED'
                ? 'Plan is APPROVED and locked'
                : !canUpload
                ? 'Plan must be in DRAFT status to upload items'
                : 'Upload CSV or Excel plan'
            }
            className={`inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer ${
              plan?.status === 'APPROVED' || !canUpload || uploading || loading
                ? 'bg-gray-100 text-gray-400 border border-gray-200 cursor-not-allowed shadow-none'
                : 'bg-orange-600 hover:bg-orange-700 text-white border border-transparent hover:shadow'
            }`}
          >
            {uploading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Ingesting Plan...</span>
              </>
            ) : (
              <>
                <Upload className="w-3.5 h-3.5" />
                <span>Upload Excel/CSV</span>
              </>
            )}
          </button>

          {/* Action: Upload GRN Button (Admin / Planner) */}
          {isAdminOrPlanner && (
            <button
              type="button"
              onClick={() => {
                resetGrnModalState();
                setIsGrnModalOpen(true);
              }}
              disabled={loading}
              title="Upload store Goods Receipt Note (GRN) to update latest purchase rates and store receipts"
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 hover:border-emerald-400"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-700" />
              <span>Upload GRN</span>
            </button>
          )}
        </div>
      </div>

      {/* Bulk Upload Modal */}
      {isUploadModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-md w-full overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-gray-900">Upload Requirement Plan</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Target: {plan?.plant_id || 'Current Plant'} ({plan?.month}/{plan?.year})
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsUploadModalOpen(false);
                  resetUploadModalState();
                }}
                className="p-1 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Only show Multi-Sheet Checkbox to Admin/Planner */}
              {isAdminOrPlanner && (
                <div className="p-3 bg-gray-50 rounded-xl border border-gray-200">
                  <label className="flex items-start gap-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={uploadAllPlants}
                      onChange={(e) => setUploadAllPlants(e.target.checked)}
                      className="mt-0.5 rounded border-gray-300 text-orange-600 focus:ring-orange-500 cursor-pointer"
                    />
                    <div className="text-xs">
                      <span className="font-semibold text-gray-800">
                        Import All 5 Plants (Multi-Sheet Workbook)
                      </span>
                      <p className="text-gray-500 mt-0.5">
                        Reads sheets for Plant 1–5 and bulk upserts into each respective plant plan.
                      </p>
                    </div>
                  </label>
                </div>
              )}

              <input
                type="file"
                ref={modalFileInputRef}
                accept=".xlsx,.xls,.csv"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    setSelectedFile(file);
                  }
                }}
                className="hidden"
              />

              <div
                onClick={() => modalFileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                  selectedFile
                    ? 'border-orange-500 bg-orange-50/30'
                    : 'border-gray-300 hover:border-orange-500 bg-gray-50/50 hover:bg-orange-50/20'
                }`}
              >
                <Upload className="w-8 h-8 text-orange-500 mx-auto mb-2" />
                {selectedFile ? (
                  <div>
                    <p className="text-xs font-bold text-gray-900">
                      Selected: <span className="text-orange-600">{selectedFile.name}</span>
                    </p>
                    <p className="text-[11px] text-gray-500 mt-1">
                      {(selectedFile.size / 1024).toFixed(1)} KB • Click to change file
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-xs font-semibold text-gray-800">
                      Click to select Excel/CSV file to upload
                    </p>
                    <p className="text-[11px] text-gray-400 mt-1">
                      Supports .xlsx, .xls, .csv with plant item records
                    </p>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsUploadModalOpen(false);
                    resetUploadModalState();
                  }}
                  className="px-3.5 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmModalUpload}
                  disabled={!selectedFile || isModalUploading}
                  className={`inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer ${
                    !selectedFile || isModalUploading
                      ? 'bg-gray-200 text-gray-400 cursor-not-allowed shadow-none'
                      : 'bg-orange-600 hover:bg-orange-700 text-white'
                  }`}
                >
                  {isModalUploading ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Uploading...</span>
                    </>
                  ) : (
                    <span>Upload File</span>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* GRN Upload Modal */}
      {isGrnModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 max-w-lg w-full overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-gray-200 flex items-center justify-between bg-emerald-50/50">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-emerald-100 text-emerald-800 rounded-lg">
                  <FileSpreadsheet className="w-4 h-4 text-emerald-700" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-gray-900">Upload Store GRN (Goods Receipt Note)</h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Target Period: {plan?.month ? `${plan.month}/${plan.year}` : 'Current Month'}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsGrnModalOpen(false);
                  resetGrnModalState();
                }}
                className="p-1 text-gray-400 hover:text-gray-700 rounded-lg hover:bg-gray-100 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div className="p-3 bg-gray-50 rounded-xl border border-gray-200 text-xs text-gray-600 leading-relaxed">
                <span className="font-semibold text-gray-800 block mb-1">
                  Automated Purchase Rate & Receipt Matching:
                </span>
                Upload Excel/CSV store receipt notes. The ingestion engine parses GRN Number, Vendor, Item Codes, Received Quantities, and Unit Rates. It updates latest unit rates in the consumable catalog and attributes receipts to active requirement plans.
              </div>

              {grnError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2.5 text-xs text-red-700">
                  <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                  <span>{grnError}</span>
                </div>
              )}

              {grnUploadResult ? (
                <div className="p-4 bg-emerald-50/60 border border-emerald-200 rounded-xl space-y-3">
                  <div className="flex items-center gap-2 text-emerald-800 font-bold text-sm">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                    <span>GRN Ingested Successfully!</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-white p-2.5 rounded-lg border border-emerald-100">
                      <span className="text-gray-500 block text-[10px] uppercase font-semibold">GRN No</span>
                      <span className="font-mono font-bold text-gray-900">{grnUploadResult.grn_no}</span>
                    </div>
                    <div className="bg-white p-2.5 rounded-lg border border-emerald-100">
                      <span className="text-gray-500 block text-[10px] uppercase font-semibold">Vendor</span>
                      <span className="font-semibold text-gray-900 truncate block" title={grnUploadResult.vendor_name || 'N/A'}>
                        {grnUploadResult.vendor_name || 'N/A'}
                      </span>
                    </div>
                    <div className="bg-white p-2.5 rounded-lg border border-emerald-100">
                      <span className="text-gray-500 block text-[10px] uppercase font-semibold">Items Processed</span>
                      <span className="font-semibold text-gray-900">{grnUploadResult.total_items} items</span>
                    </div>
                    <div className="bg-white p-2.5 rounded-lg border border-emerald-100">
                      <span className="text-gray-500 block text-[10px] uppercase font-semibold">Total Receipt Value</span>
                      <span className="font-mono font-bold text-emerald-700">
                        ₹{grnUploadResult.total_receipt_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                  </div>
                  <p className="text-[11px] text-emerald-800">
                    Updated <strong>{grnUploadResult.consumables_updated}</strong> catalog rates and <strong>{grnUploadResult.requirement_lines_updated}</strong> requirement plan line items.
                  </p>
                </div>
              ) : (
                <>
                  <input
                    type="file"
                    ref={grnFileInputRef}
                    accept=".xlsx,.xls,.csv"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        setSelectedGrnFile(file);
                        setGrnError(null);
                      }
                    }}
                    className="hidden"
                  />

                  <div
                    onClick={() => grnFileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
                      selectedGrnFile
                        ? 'border-emerald-500 bg-emerald-50/30'
                        : 'border-gray-300 hover:border-emerald-500 bg-gray-50/50 hover:bg-emerald-50/20'
                    }`}
                  >
                    <FileText className="w-8 h-8 text-emerald-600 mx-auto mb-2" />
                    {selectedGrnFile ? (
                      <div>
                        <p className="text-xs font-bold text-gray-900">
                          Selected: <span className="text-emerald-700">{selectedGrnFile.name}</span>
                        </p>
                        <p className="text-[11px] text-gray-500 mt-1">
                          {(selectedGrnFile.size / 1024).toFixed(1)} KB • Click to change file
                        </p>
                      </div>
                    ) : (
                      <div>
                        <p className="text-xs font-semibold text-gray-800">
                          Click to select GRN Excel or CSV file
                        </p>
                        <p className="text-[11px] text-gray-400 mt-1">
                          Flexible column detection: GRN No, Date, Item Code, Received QTY, Rate
                        </p>
                      </div>
                    )}
                  </div>
                </>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsGrnModalOpen(false);
                    resetGrnModalState();
                  }}
                  className="px-3.5 py-1.5 text-xs font-semibold text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 cursor-pointer"
                >
                  {grnUploadResult ? 'Close' : 'Cancel'}
                </button>
                {!grnUploadResult && (
                  <button
                    type="button"
                    onClick={handleConfirmGrnUpload}
                    disabled={!selectedGrnFile || isGrnUploading}
                    className={`inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer ${
                      !selectedGrnFile || isGrnUploading
                        ? 'bg-gray-200 text-gray-400 cursor-not-allowed shadow-none'
                        : 'bg-emerald-600 hover:bg-emerald-700 text-white'
                    }`}
                  >
                    {isGrnUploading ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Processing GRN...</span>
                      </>
                    ) : (
                      <span>Upload GRN</span>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Grid Table */}
      <div className="overflow-x-auto min-h-[320px]">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 text-gray-400 space-y-3">
            <Loader2 className="w-8 h-8 animate-spin text-orange-500" />
            <p className="text-sm">Loading requirement line items...</p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-gray-50/80 border-b border-gray-200 text-gray-600 font-semibold uppercase tracking-wider text-[11px]">
                <th className="py-3 px-3 w-14 text-center">
                  <span className="sr-only">S.No.</span>
                  <span title="S.No">S.No</span>
                </th>
                <th className="py-3 px-3 w-32">
                  <span className="sr-only">Item Id.</span>
                  <span title="Item Code">Item Code</span>
                </th>
                <th className="py-3 px-3">Item Description</th>
                <th className="py-3 px-3 w-28">Part No.</th>
                <th className="py-3 px-3 w-20 text-center">Unit</th>
                <th className="py-3 px-3 w-28 text-right font-medium text-gray-500">
                  <span title="Formula QTY">Formula QTY</span>
                </th>
                <th className="py-3 px-3 w-36 text-right">
                  <span className="sr-only">QTY</span>
                  <span title="Plant Requested QTY">Requested QTY</span>
                </th>
                <th className="py-3 px-3 w-28 text-right font-medium text-gray-600">
                  <span title="Latest Rate (₹)">Latest Rate (₹)</span>
                </th>
                <th className="py-3 px-3 w-28 text-right font-medium text-gray-600">
                  <span title="Receipt QTY">Receipt QTY</span>
                </th>
                <th className="py-3 px-3 w-32 text-right font-medium text-gray-600">
                  <span title="Order Value (₹)">Order Value (₹)</span>
                </th>
                <th className="py-3 px-3 w-32 text-right font-medium text-emerald-700">
                  <span title="Receipt Value (₹)">Receipt Value (₹)</span>
                </th>
                <th className="py-3 px-3 w-40 text-center">
                  <span>Variance / Status</span>
                </th>
                {canEdit && <th className="py-3 px-3 w-24 text-center">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-gray-700">
              {filteredItems.length === 0 ? (
                <tr>
                  <td
                    colSpan={canEdit ? 13 : 12}
                    className="py-16 px-4 text-center text-gray-400 font-medium"
                  >
                    <div className="flex flex-col items-center justify-center space-y-2">
                      <PackageCheck className="w-8 h-8 text-orange-400/80" />
                      <p className="text-xs text-gray-600">
                        {searchQuery
                          ? `No line items matched "${searchQuery}". Clear your search query to see all items.`
                          : "No items recorded for this period yet. Use '+ Add Item' or 'Upload Excel/CSV' above."}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredItems.map((item, idx) => {
                const isEditing = editingItemId === item.id;
                const isDeleting = deletingItemId === item.id;
                const formula = Number(item.formula_qty) || 0;
                const requested = Number(item.requested_qty) || 0;
                const delta = requested - formula;
                const isModified = Boolean(
                  item.is_modified || (formula > 0 && Math.abs(delta) > 0.0001)
                );

                return (
                  <tr
                    key={item.id || idx}
                    className={`transition-colors group ${
                      isModified
                        ? 'bg-amber-50/50 hover:bg-amber-100/60 border-l-4 border-amber-400'
                        : 'hover:bg-orange-50/40 border-l-4 border-transparent'
                    }`}
                  >
                    <td className="py-3 px-3 text-center font-mono text-gray-400 group-hover:text-gray-600">
                      {item.serial_no || idx + 1}
                    </td>
                    <td className="py-3 px-3 font-mono font-medium text-gray-900">
                      <span className="bg-gray-100 group-hover:bg-white px-2 py-0.5 rounded border border-gray-200">
                        {item.item_id || item.item_code || item.consumable_id}
                      </span>
                    </td>
                    <td className="py-3 px-3 font-medium text-gray-800">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editDesc}
                          onChange={(e) => setEditDesc(e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-orange-300 rounded bg-white focus:outline-none focus:ring-1 focus:ring-orange-500"
                        />
                      ) : (
                        <div>
                          <span>{item.consumable_name || item.description || 'Consumable Item'}</span>
                          {item.description && item.description !== item.consumable_name && (
                            <p className="text-[11px] text-gray-400 font-normal line-clamp-1">{item.description}</p>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-3 text-gray-600 font-mono">
                      {isEditing ? (
                        <input
                          type="text"
                          value={editPartNo}
                          onChange={(e) => setEditPartNo(e.target.value)}
                          className="w-full px-2 py-1 text-xs border border-orange-300 rounded bg-white focus:outline-none focus:ring-1 focus:ring-orange-500"
                        />
                      ) : (
                        item.part_no || '-'
                      )}
                    </td>
                    <td className="py-3 px-3 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-600 border border-gray-200">
                        {item.unit || 'Nos'}
                      </span>
                    </td>
                    {/* Formula QTY */}
                    <td className="py-3 px-3 text-right font-mono text-gray-500 font-medium">
                      {formula.toLocaleString(undefined, {
                        minimumFractionDigits: 0,
                        maximumFractionDigits: 2,
                      })}
                    </td>
                    {/* Plant Requested QTY */}
                    <td className="py-3 px-3 text-right">
                      {isEditing ? (
                        <div className="flex flex-col gap-1 items-end">
                          <input
                            type="number"
                            step="any"
                            min="0"
                            value={editQty}
                            onChange={(e) => setEditQty(e.target.value)}
                            className="w-24 px-2 py-1 text-right text-xs border border-orange-300 rounded bg-white focus:outline-none focus:ring-1 focus:ring-orange-500 font-mono font-semibold"
                          />
                          <input
                            type="text"
                            placeholder="Reason for modification..."
                            value={editReason}
                            onChange={(e) => setEditReason(e.target.value)}
                            className="w-40 px-2 py-0.5 text-[10px] border border-gray-300 rounded bg-white focus:outline-none focus:ring-1 focus:ring-orange-500 placeholder-gray-400"
                          />
                        </div>
                      ) : (
                        <span className="font-mono font-semibold text-gray-900 text-sm">
                          {requested.toLocaleString(undefined, {
                            minimumFractionDigits: 0,
                            maximumFractionDigits: 2,
                          })}
                        </span>
                      )}
                    </td>

                    {/* Latest Rate (₹) */}
                    <td className="py-3 px-3 text-right font-mono text-gray-700">
                      {(() => {
                        const effectiveRate = Number(item.rate || item.latest_grn_rate || 0);
                        if (effectiveRate <= 0) return <span className="text-gray-300">-</span>;
                        return (
                          <span title={`Latest Unit Rate: ₹${effectiveRate.toFixed(2)}`}>
                            ₹{effectiveRate.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </span>
                        );
                      })()}
                    </td>

                    {/* Receipt QTY */}
                    <td className="py-3 px-3 text-right font-mono">
                      {(() => {
                        const recQty = Number(item.receipt_qty || 0);
                        const reqQty = Number(item.requested_qty || 0);
                        if (recQty <= 0) return <span className="text-gray-300">-</span>;
                        const isFullyReceived = reqQty > 0 && recQty >= reqQty;
                        return (
                          <span
                            className={`inline-flex items-center gap-1 font-semibold ${
                              isFullyReceived ? 'text-emerald-700' : 'text-blue-700'
                            }`}
                            title={`Received ${recQty} of ${reqQty}`}
                          >
                            {recQty.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
                          </span>
                        );
                      })()}
                    </td>

                    {/* Order Value (₹) */}
                    <td className="py-3 px-3 text-right font-mono font-medium text-gray-800">
                      {(() => {
                        const effectiveRate = Number(item.rate || item.latest_grn_rate || 0);
                        const effectiveQty = Number(item.approved_qty || item.requested_qty || 0);
                        const ordVal = Number(item.order_value) || (effectiveQty * effectiveRate);
                        if (ordVal <= 0) return <span className="text-gray-300">-</span>;
                        return `₹${ordVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                      })()}
                    </td>

                    {/* Receipt Value (₹) */}
                    <td className="py-3 px-3 text-right font-mono font-medium text-emerald-800">
                      {(() => {
                        const effectiveRate = Number(item.rate || item.latest_grn_rate || 0);
                        const recQty = Number(item.receipt_qty || 0);
                        const recVal = Number(item.receipt_value) || (recQty * effectiveRate);
                        if (recVal <= 0) return <span className="text-gray-300">-</span>;
                        return `₹${recVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                      })()}
                    </td>

                    {/* Variance / Modification Status */}
                    <td className="py-3 px-3 text-center">
                      {isModified ? (
                        <div
                          className="flex flex-col items-center gap-0.5 cursor-help"
                          title={`Formula: ${formula} | Plant Requested: ${requested} (${delta >= 0 ? '+' : ''}${delta.toFixed(1)})`}
                        >
                          <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 shadow-2xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>
                            MODIFIED
                          </div>
                          <span
                            className={`text-[10px] font-mono font-semibold ${
                              delta > 0 ? 'text-amber-700' : 'text-blue-700'
                            }`}
                          >
                            {delta >= 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1)}{' '}
                            {formula > 0 && `(${((delta / formula) * 100).toFixed(0)}%)`}
                          </span>
                          {item.modification_reason && (
                            <span
                              className="text-[10px] text-gray-500 italic max-w-[130px] truncate"
                              title={item.modification_reason}
                            >
                              "{item.modification_reason}"
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600 border border-gray-200">
                          Formula Match
                        </span>
                      )}
                    </td>
                    {canEdit && (
                      <td className="py-3 px-3 text-center">
                        {isEditing ? (
                          <div className="flex items-center justify-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => saveEdit(item.id)}
                              disabled={savingEdit}
                              title="Save Changes"
                              className="p-1 rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100 cursor-pointer"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={cancelEdit}
                              disabled={savingEdit}
                              title="Cancel"
                              className="p-1 rounded bg-gray-100 text-gray-600 hover:bg-gray-200 cursor-pointer"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-center gap-1.5 opacity-80 group-hover:opacity-100">
                            {onUpdateItem && (
                              <button
                                type="button"
                                onClick={() => startEdit(item)}
                                title="Edit item"
                                className="p-1 rounded text-gray-400 hover:text-orange-600 hover:bg-orange-50 cursor-pointer"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {onDeleteItem && (
                              <button
                                type="button"
                                onClick={() => handleDelete(item.id)}
                                disabled={isDeleting}
                                title="Delete item"
                                className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 cursor-pointer"
                              >
                                {isDeleting ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin text-red-600" />
                                ) : (
                                  <Trash2 className="w-3.5 h-3.5" />
                                )}
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                );
              }))}
            </tbody>
          </table>
        )}
      </div>

      {/* Grid Footer Summary */}
      {items.length > 0 && (
        <div className="p-3 bg-gray-50 border-t border-gray-200 flex flex-col sm:flex-row items-center justify-between text-xs text-gray-500 gap-2">
          <span>
            Showing <strong className="text-gray-700">{filteredItems.length}</strong> of{' '}
            <strong className="text-gray-700">{items.length}</strong> total line items
          </span>
          <div className="flex flex-wrap items-center gap-4">
            <span>
              Cumulative Requirement:{' '}
              <strong className="text-gray-900 font-mono text-sm">
                {totalRequestedQty.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
              </strong>
            </span>
            {totalOrderValue > 0 && (
              <span>
                Total Planned Value:{' '}
                <strong className="text-gray-900 font-mono text-sm">
                  ₹{totalOrderValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </strong>
              </span>
            )}
            {totalReceiptValue > 0 && (
              <span>
                Total Receipts:{' '}
                <strong className="text-emerald-700 font-mono text-sm">
                  ₹{totalReceiptValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </strong>
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default PlanGrid;
