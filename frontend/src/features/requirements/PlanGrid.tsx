import React, { useRef, useState } from 'react';
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
import type { MonthlyRequirementPlan, RequirementLineItem, UpdateLineItemPayload } from './api';

interface PlanGridProps {
  plan: MonthlyRequirementPlan | null;
  items: RequirementLineItem[];
  loading?: boolean;
  uploading?: boolean;
  onUpload: (file: File) => Promise<void>;
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [searchQuery, setSearchQuery] = useState('');

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

          {/* Hidden File Input */}
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
            onClick={() => fileInputRef.current?.click()}
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
