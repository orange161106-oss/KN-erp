import React, { useEffect, useRef, useState } from 'react';
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
} from 'lucide-react';
import { useAuth } from '../auth/context';
import type { MonthlyRequirementPlan, RequirementLineItem, UpdateLineItemPayload } from './api';

interface PlanGridProps {
  plan: MonthlyRequirementPlan | null;
  items: RequirementLineItem[];
  loading?: boolean;
  uploading?: boolean;
  onUpload: (file: File, uploadAllPlants?: boolean) => Promise<void>;
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
    user?.role === 'ADMIN' ||
    user?.role === 'PLANNER'
  );

  const fileInputRef = useRef<HTMLInputElement>(null);
  const modalFileInputRef = useRef<HTMLInputElement>(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadAllPlants, setUploadAllPlants] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isModalUploading, setIsModalUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

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

  // Explicitly reset upload state whenever plan ID or plant ID changes
  useEffect(() => {
    resetUploadModalState();
  }, [plan?.id, plan?.plant_id]);

  // Inline editing state
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editQty, setEditQty] = useState<number | string>('');
  const [editPartNo, setEditPartNo] = useState<string>('');
  const [editDesc, setEditDesc] = useState<string>('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null);

  const startEdit = (item: RequirementLineItem) => {
    setEditingItemId(item.id);
    setEditQty(item.requested_qty);
    setEditPartNo(item.part_no || '');
    setEditDesc(item.consumable_name || item.description || '');
  };

  const cancelEdit = () => {
    setEditingItemId(null);
    setEditQty('');
    setEditPartNo('');
    setEditDesc('');
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

  const filteredItems = items.filter((item) => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    const code = (item.item_id || item.item_code || item.consumable_id || '').toLowerCase();
    const name = (item.consumable_name || item.description || '').toLowerCase();
    const part = (item.part_no || '').toLowerCase();
    return code.includes(query) || name.includes(query) || part.includes(query);
  });

  const totalRequestedQty = items.reduce((acc, it) => acc + (Number(it.requested_qty) || 0), 0);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden flex flex-col">
      {/* Grid Toolbar */}
      <div className="p-4 border-b border-gray-200 bg-white flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-orange-50 text-erp-orange rounded-lg border border-orange-100">
            <FileSpreadsheet className="w-5 h-5 text-orange-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-gray-900 tracking-tight">Requirement Line Items</h2>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-200">
                {items.length} {items.length === 1 ? 'item' : 'items'}
              </span>
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
              disabled={!plan || !canEdit || loading}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer ${
                !plan || !canEdit || loading
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
            disabled={!plan || !canUpload || uploading || loading}
            title={
              !plan
                ? 'Create a plan first to upload items'
                : !canUpload
                ? 'Plan must be in DRAFT status to upload items'
                : 'Upload CSV or Excel plan'
            }
            className={`inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer ${
              !plan || !canUpload || uploading || loading
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
                <th className="py-3 px-4 w-16 text-center">
                  <span title="S.No.">S.No.</span>
                  <span className="sr-only">S.No</span>
                </th>
                <th className="py-3 px-4 w-36">
                  <span title="Item Id.">Item Id.</span>
                  <span className="sr-only">Item Code</span>
                </th>
                <th className="py-3 px-4">Item Description</th>
                <th className="py-3 px-4 w-36">Part No.</th>
                <th className="py-3 px-4 w-24 text-center">Unit</th>
                <th className="py-3 px-4 w-32 text-right">
                  <span title="QTY">QTY</span>
                  <span className="sr-only">Requested QTY</span>
                </th>
                {canEdit && <th className="py-3 px-4 w-24 text-center">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 text-gray-700">
              {filteredItems.length === 0 ? (
                <tr>
                  <td
                    colSpan={canEdit ? 7 : 6}
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

                return (
                  <tr
                    key={item.id || idx}
                    className="hover:bg-orange-50/40 transition-colors group"
                  >
                    <td className="py-3 px-4 text-center font-mono text-gray-400 group-hover:text-gray-600">
                      {item.serial_no || idx + 1}
                    </td>
                    <td className="py-3 px-4 font-mono font-medium text-gray-900">
                      <span className="bg-gray-100 group-hover:bg-white px-2 py-0.5 rounded border border-gray-200">
                        {item.item_id || item.item_code || item.consumable_id}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-medium text-gray-800">
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
                    <td className="py-3 px-4 text-gray-600 font-mono">
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
                    <td className="py-3 px-4 text-center">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-600 border border-gray-200">
                        {item.unit || 'Nos'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-mono font-semibold text-gray-900 text-sm">
                      {isEditing ? (
                        <input
                          type="number"
                          step="any"
                          min="0"
                          value={editQty}
                          onChange={(e) => setEditQty(e.target.value)}
                          className="w-24 px-2 py-1 text-right text-xs border border-orange-300 rounded bg-white focus:outline-none focus:ring-1 focus:ring-orange-500"
                        />
                      ) : (
                        Number(item.requested_qty).toLocaleString(undefined, {
                          minimumFractionDigits: 0,
                          maximumFractionDigits: 2,
                        })
                      )}
                    </td>
                    {canEdit && (
                      <td className="py-3 px-4 text-center">
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
          <div className="flex items-center gap-4">
            <span>
              Cumulative Requirement:{' '}
              <strong className="text-gray-900 font-mono text-sm">
                {totalRequestedQty.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}
              </strong>
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default PlanGrid;
