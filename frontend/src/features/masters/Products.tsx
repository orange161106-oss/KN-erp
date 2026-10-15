import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import axios from 'axios';
import type { AxiosProgressEvent } from 'axios';
import { apiClient, getAccessToken, getApiBaseUrl } from '../../api/client';
import { useAuth } from '../auth/context';
import { TableSkeletonRows } from '../../components/ui/Skeleton';

type ActiveTab = 'consumables' | 'assemble' | 'sales_parts';

// ---------------------------------------------------------------------------
// Type Definitions
// ---------------------------------------------------------------------------

interface ConsumableRow {
  id: string;
  supplier_id: string | null;
  supplier_name: string;
  item_id: string;
  category: string;
  type_of_material: string;
  description: string;
  output_unit: string;
  rate: number | null;
  is_active: boolean;
}

interface AssembleRow {
  id: string;
  consumable_item: string;
  part_no_saleable_item: string;
  used_for_name_of_saleable_part: string;
  used_part_no_prd_order: string;
  process_name: string;
  material_thickness_in_mm_gsm: string;
  no_of_process_per_part: number;
  output_unit: string;
  rate: number | null;
  is_active: boolean;
}

interface SalesPartRow {
  id: string;
  s_no: number;
  part_no: string;
  item_id: string;
  part_description: string;
  uom: string;
  is_active: boolean;
}

interface AssembleRowIssue {
  row: number;
  column?: string;
  error_code: string;
  message: string;
  raw_value?: string;
  suggested_action?: string;
}

interface AssemblePreviewData {
  file_token: string;
  source_filename: string;
  detected_header_row: number;
  columns_matched: string[];
  total_rows: number;
  rows_to_add: number;
  rows_to_update: number;
  errors: AssembleRowIssue[];
  warning_count: number;
  error_count: number;
  can_confirm: boolean;
}

interface AssembleJobStatus {
  job_id: string;
  status: string;
  stage: string;
  progress_percent: number;
  total_rows: number;
  upserted: number;
  rows_added: number;
  rows_updated: number;
  errors: AssembleRowIssue[];
  error_message?: string;
}

export default function Products() {
  const { user } = useAuth();
  const isSuperAdmin = Boolean(user?.is_super_admin || user?.is_superuser);
  const canRead = Boolean(
    isSuperAdmin ||
    user?.masters_read ||
    user?.permissions?.includes('masters.read') ||
    user?.permissions?.some((p: string) => p.startsWith('masters.'))
  );
  const canCreate = Boolean(
    isSuperAdmin ||
    user?.masters_create ||
    user?.permissions?.includes('masters.write') ||
    user?.permissions?.some((p: string) => p.endsWith('.write'))
  );
  const canEdit = Boolean(
    isSuperAdmin ||
    user?.masters_create ||
    user?.permissions?.includes('masters.write') ||
    user?.permissions?.some((p: string) => p.endsWith('.write'))
  );
  const canDelete = canEdit;

  const [activeTab, setActiveTab] = useState<ActiveTab>('consumables');

  // Editing state for inline CRUD
  const [editingConsumableId, setEditingConsumableId] = useState<string | null>(null);
  const [editingAssembleId, setEditingAssembleId] = useState<string | null>(null);
  const [editingSalesPartId, setEditingSalesPartId] = useState<string | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  // Loading & Notification states
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Bulk Upload Modal & Progress states
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadPhase, setUploadPhase] = useState<'idle' | 'uploading' | 'parsing'>('idle');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [assemblePreview, setAssemblePreview] = useState<AssemblePreviewData | null>(null);
  const [assembleJob, setAssembleJob] = useState<AssembleJobStatus | null>(null);
  const [isConfirming, setIsConfirming] = useState<boolean>(false);

  const activeTabLabel = useMemo(() => {
    switch (activeTab) {
      case 'consumables':
        return 'List of Consumables';
      case 'assemble':
        return 'Consumable for Assemble';
      case 'sales_parts':
        return 'List of Sales Parts';
    }
  }, [activeTab]);

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [toast]);

  // Table Data states
  const [consumables, setConsumables] = useState<ConsumableRow[]>([]);
  const [assembleRows, setAssembleRows] = useState<AssembleRow[]>([]);
  const [salesParts, setSalesParts] = useState<SalesPartRow[]>([]);

  // Localized Inline Column Search States
  const [consumableFilters, setConsumableFilters] = useState<Record<string, string>>({
    supplier_id: '',
    supplier_name: '',
    item_id: '',
    category: '',
    type_of_material: '',
    description: '',
    output_unit: '',
    rate: '',
  });

  const [assembleFilters, setAssembleFilters] = useState<Record<string, string>>({
    consumable_item: '',
    part_no_saleable_item: '',
    used_for_name_of_saleable_part: '',
    used_part_no_prd_order: '',
    process_name: '',
    material_thickness_in_mm_gsm: '',
    no_of_process_per_part: '',
    output_unit: '',
    rate: '',
  });

  const [salesPartFilters, setSalesPartFilters] = useState<Record<string, string>>({
    s_no: '',
    part_no: '',
    item_id: '',
    part_description: '',
    uom: '',
  });

  // Single Entry Form States
  const [consumableForm, setConsumableForm] = useState({
    supplier_id: '',
    supplier_name: '',
    item_id: '',
    category: '',
    type_of_material: '',
    description: '',
    output_unit: 'PCS',
    rate: '',
  });

  const [assembleForm, setAssembleForm] = useState({
    consumable_item: '',
    part_no_saleable_item: '',
    used_for_name_of_saleable_part: '',
    used_part_no_prd_order: '',
    process_name: 'ASSEMBLY',
    material_thickness_in_mm_gsm: '',
    no_of_process_per_part: '1.0',
    output_unit: 'PCS',
    rate: '',
  });

  const [salesPartForm, setSalesPartForm] = useState({
    part_no: '',
    item_id: '',
    part_description: '',
    uom: 'PCS',
  });

  // File Upload Drag & Drop State
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ---------------------------------------------------------------------------
  // Data Fetching
  // ---------------------------------------------------------------------------

  const loadData = useCallback(async () => {
    if (!canRead) return;
    setLoading(true);
    try {
      if (activeTab === 'consumables') {
        const res = await apiClient.get<{ items: ConsumableRow[]; total: number }>(
          '/api/v1/masters/product-master/consumables?limit=1000'
        );
        setConsumables(res.items || []);
      } else if (activeTab === 'assemble') {
        const res = await apiClient.get<{ items: AssembleRow[]; total: number }>(
          '/api/v1/masters/product-master/assemble?limit=1000'
        );
        setAssembleRows(res.items || []);
      } else if (activeTab === 'sales_parts') {
        const res = await apiClient.get<{ items: SalesPartRow[]; total: number }>(
          '/api/v1/masters/product-master/sales-parts?limit=1000'
        );
        setSalesParts(res.items || []);
      }
    } catch (e: any) {
      setFeedback({ type: 'error', message: e?.message || 'Failed to load master records.' });
    } finally {
      setLoading(false);
    }
  }, [activeTab, canRead]);

  useEffect(() => {
    loadData();
    setFeedback(null);
  }, [loadData]);

  // ---------------------------------------------------------------------------
  // Single Entry Form Submission & Inline CRUD Updates
  // ---------------------------------------------------------------------------

  const safeScrollTop = () => {
    try {
      if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } catch {
      // safe fallback in test environments
    }
  };

  const startEditConsumable = (row: ConsumableRow) => {
    setEditingConsumableId(row.id);
    setConsumableForm({
      supplier_id: row.supplier_id || '',
      supplier_name: row.supplier_name || '',
      item_id: row.item_id || '',
      category: row.category || '',
      type_of_material: row.type_of_material || '',
      description: row.description || '',
      output_unit: row.output_unit || 'PCS',
      rate: row.rate !== null && row.rate !== undefined ? String(row.rate) : '',
    });
    safeScrollTop();
  };

  const cancelEditConsumable = () => {
    setEditingConsumableId(null);
    setConsumableForm({
      supplier_id: '',
      supplier_name: '',
      item_id: '',
      category: '',
      type_of_material: '',
      description: '',
      output_unit: 'PCS',
      rate: '',
    });
  };

  const handleConsumableSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!consumableForm.item_id.trim()) {
      setFeedback({ type: 'error', message: 'Item ID is required.' });
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      const payload = {
        supplier_id: consumableForm.supplier_id ? consumableForm.supplier_id : undefined,
        supplier_name: consumableForm.supplier_name.trim() || undefined,
        item_id: consumableForm.item_id.trim().toUpperCase(),
        category: consumableForm.category.trim() || undefined,
        type_of_material: consumableForm.type_of_material.trim() || undefined,
        description: consumableForm.description.trim() || undefined,
        output_unit: consumableForm.output_unit.trim() || 'PCS',
        rate: consumableForm.rate ? parseFloat(consumableForm.rate) : undefined,
      };

      if (editingConsumableId) {
        await apiClient.put(`/api/v1/masters/product-master/consumables/${editingConsumableId}`, payload);
        const msg = `Consumable ${consumableForm.item_id} updated successfully.`;
        setFeedback({ type: 'success', message: msg });
        setToast({ type: 'success', message: msg });
        setEditingConsumableId(null);
      } else {
        await apiClient.post('/api/v1/masters/product-master/consumables/single', payload);
        const msg = `Consumable ${consumableForm.item_id} saved successfully.`;
        setFeedback({ type: 'success', message: msg });
        setToast({ type: 'success', message: msg });
      }

      setConsumableForm({
        supplier_id: '',
        supplier_name: '',
        item_id: '',
        category: '',
        type_of_material: '',
        description: '',
        output_unit: 'PCS',
        rate: '',
      });
      await loadData();
    } catch (e: any) {
      setFeedback({ type: 'error', message: e?.message || 'Failed to save consumable.' });
    } finally {
      setSubmitting(false);
    }
  };

  const startEditAssemble = (row: AssembleRow) => {
    setEditingAssembleId(row.id);
    setAssembleForm({
      consumable_item: row.consumable_item || '',
      part_no_saleable_item: row.part_no_saleable_item || '',
      used_for_name_of_saleable_part: row.used_for_name_of_saleable_part || '',
      used_part_no_prd_order: row.used_part_no_prd_order || '',
      process_name: row.process_name || 'ASSEMBLY',
      material_thickness_in_mm_gsm: row.material_thickness_in_mm_gsm || '',
      no_of_process_per_part: row.no_of_process_per_part ? String(row.no_of_process_per_part) : '1.0',
      output_unit: row.output_unit || 'PCS',
      rate: row.rate !== null && row.rate !== undefined ? String(row.rate) : '',
    });
    safeScrollTop();
  };

  const cancelEditAssemble = () => {
    setEditingAssembleId(null);
    setAssembleForm({
      consumable_item: '',
      part_no_saleable_item: '',
      used_for_name_of_saleable_part: '',
      used_part_no_prd_order: '',
      process_name: 'ASSEMBLY',
      material_thickness_in_mm_gsm: '',
      no_of_process_per_part: '1.0',
      output_unit: 'PCS',
      rate: '',
    });
  };

  const handleAssembleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!assembleForm.consumable_item.trim() || !assembleForm.part_no_saleable_item.trim()) {
      setFeedback({ type: 'error', message: 'Consumable Description and Part No. of Saleable Item are required.' });
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      const payload = {
        consumable_item: assembleForm.consumable_item.trim(),
        part_no_saleable_item: assembleForm.part_no_saleable_item.trim(),
        used_for_name_of_saleable_part: assembleForm.used_for_name_of_saleable_part.trim() || undefined,
        used_part_no_prd_order: assembleForm.used_part_no_prd_order.trim() || undefined,
        process_name: assembleForm.process_name.trim() || 'ASSEMBLY',
        material_thickness_in_mm_gsm: assembleForm.material_thickness_in_mm_gsm.trim() || undefined,
        no_of_process_per_part: assembleForm.no_of_process_per_part ? parseFloat(assembleForm.no_of_process_per_part) : 1.0,
        output_unit: assembleForm.output_unit.trim() || 'PCS',
        rate: assembleForm.rate ? parseFloat(assembleForm.rate) : undefined,
      };

      if (editingAssembleId) {
        await apiClient.put(`/api/v1/masters/product-master/assemble/${editingAssembleId}`, payload);
        const msg = 'Assembly mapping updated successfully.';
        setFeedback({ type: 'success', message: msg });
        setToast({ type: 'success', message: msg });
        setEditingAssembleId(null);
      } else {
        await apiClient.post('/api/v1/masters/product-master/assemble/single', payload);
        const msg = 'Assembly mapping saved successfully.';
        setFeedback({ type: 'success', message: msg });
        setToast({ type: 'success', message: msg });
      }

      setAssembleForm({
        consumable_item: '',
        part_no_saleable_item: '',
        used_for_name_of_saleable_part: '',
        used_part_no_prd_order: '',
        process_name: 'ASSEMBLY',
        material_thickness_in_mm_gsm: '',
        no_of_process_per_part: '1.0',
        output_unit: 'PCS',
        rate: '',
      });
      await loadData();
    } catch (e: any) {
      setFeedback({ type: 'error', message: e?.message || 'Failed to save assembly mapping.' });
    } finally {
      setSubmitting(false);
    }
  };

  const startEditSalesPart = (row: SalesPartRow) => {
    setEditingSalesPartId(row.id);
    setSalesPartForm({
      part_no: row.part_no || '',
      item_id: row.item_id || '',
      part_description: row.part_description || '',
      uom: row.uom || 'PCS',
    });
    safeScrollTop();
  };

  const cancelEditSalesPart = () => {
    setEditingSalesPartId(null);
    setSalesPartForm({
      part_no: '',
      item_id: '',
      part_description: '',
      uom: 'PCS',
    });
  };

  const handleSalesPartSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!salesPartForm.part_no.trim() || !salesPartForm.item_id.trim()) {
      setFeedback({ type: 'error', message: 'Part No. and Item ID are required.' });
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      const payload = {
        part_no: salesPartForm.part_no.trim(),
        item_id: salesPartForm.item_id.trim(),
        part_description: salesPartForm.part_description.trim() || salesPartForm.part_no.trim(),
        uom: salesPartForm.uom.trim() || 'PCS',
      };

      if (editingSalesPartId) {
        await apiClient.put(`/api/v1/masters/product-master/sales_parts/${editingSalesPartId}`, payload);
        const msg = `Sales part ${salesPartForm.part_no} updated successfully.`;
        setFeedback({ type: 'success', message: msg });
        setToast({ type: 'success', message: msg });
        setEditingSalesPartId(null);
      } else {
        await apiClient.post('/api/v1/masters/product-master/sales-parts/single', payload);
        const msg = `Sales part ${salesPartForm.part_no} saved successfully.`;
        setFeedback({ type: 'success', message: msg });
        setToast({ type: 'success', message: msg });
      }

      setSalesPartForm({
        part_no: '',
        item_id: '',
        part_description: '',
        uom: 'PCS',
      });
      await loadData();
    } catch (e: any) {
      setFeedback({ type: 'error', message: e?.message || 'Failed to save sales part.' });
    } finally {
      setSubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Soft Delete (Deactivate) Handler
  // ---------------------------------------------------------------------------

  const handleDeactivate = async (category: string, id: string, name: string) => {
    const confirmed = window.confirm(`Are you sure you want to delete "${name}"? This record will be deactivated.`);
    if (!confirmed) return;

    setActionLoadingId(id);
    try {
      await apiClient.patch(`/api/v1/masters/product-master/${category}/${id}/deactivate`, {});
      const msg = `Record "${name}" deactivated successfully.`;
      setFeedback({ type: 'success', message: msg });
      setToast({ type: 'success', message: msg });
      await loadData();
    } catch (e: any) {
      setFeedback({ type: 'error', message: e?.message || 'Failed to deactivate record.' });
    } finally {
      setActionLoadingId(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Bulk Excel File Upload & Header Hunter Execution
  // ---------------------------------------------------------------------------

  const handleFileUpload = async (file: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      const err = 'Please select a valid Excel (.xlsx) file.';
      setUploadError(err);
      setFeedback({ type: 'error', message: err });
      return;
    }

    if (file.size > 15 * 1024 * 1024) {
      const err = 'File size exceeds 15 MB limit. Please select a smaller file.';
      setUploadError(err);
      setFeedback({ type: 'error', message: err });
      return;
    }

    setSelectedFile(file);
    setUploading(true);
    setUploadProgress(0);
    setUploadPhase('uploading');
    setUploadError(null);
    setFeedback(null);

    const formData = new FormData();
    formData.append('file', file);

    const token = getAccessToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    // Two-step preview for Consumable for Assemble tab
    if (activeTab === 'assemble') {
      try {
        const response = await axios.post<AssemblePreviewData>(
          `${getApiBaseUrl()}/api/v1/masters/product-master/assemble/preview`,
          formData,
          {
            headers,
            timeout: 60000,
            onUploadProgress: (progressEvent: AxiosProgressEvent) => {
              if (progressEvent.total) {
                const percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
                setUploadProgress(percent);
                if (percent >= 100) {
                  setUploadPhase('parsing');
                } else {
                  setUploadPhase('uploading');
                }
              }
            },
          }
        );

        setAssemblePreview(response.data);
        setUploading(false);
        setUploadProgress(0);
        setUploadPhase('idle');
        return;
      } catch (e: any) {
        const isTimeout = e?.code === 'ECONNABORTED' || e?.message?.includes('timeout');
        const errMsg = isTimeout
          ? 'Preview generation timed out after 60 seconds. High network latency or large row processing took too long. You can click "Retry Upload" below.'
          : e?.response?.data?.message ||
            e?.response?.data?.detail ||
            e?.message ||
            'Failed to preview assemble file.';
        setUploadError(errMsg);
        setFeedback({ type: 'error', message: errMsg });
        setUploading(false);
        return;
      }
    }

    // Direct upload for consumables and sales_parts tabs
    let endpoint = '/api/v1/masters/product-master/consumables/bulk';
    if (activeTab === 'sales_parts') {
      endpoint = '/api/v1/masters/product-master/sales-parts/bulk';
    }

    try {
      const response = await axios.post<{
        total_rows: number;
        upserted: number;
        errors: string[];
      }>(`${getApiBaseUrl()}${endpoint}`, formData, {
        headers,
        timeout: 60000,
        onUploadProgress: (progressEvent: AxiosProgressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
            setUploadProgress(percent);
            if (percent >= 100) {
              setUploadPhase('parsing');
            } else {
              setUploadPhase('uploading');
            }
          }
        },
      });

      const res = response.data;
      const msg = `Bulk upload complete: ${res.upserted} records successfully upserted out of ${res.total_rows} evaluated rows.`;
      setFeedback({ type: 'success', message: msg });
      setToast({ type: 'success', message: msg });
      if (res.errors && res.errors.length > 0) {
        console.warn('Bulk upload row notices:', res.errors);
      }

      setIsUploadModalOpen(false);
      setUploading(false);
      setUploadProgress(0);
      setUploadPhase('idle');
      setSelectedFile(null);
      await loadData();
    } catch (e: any) {
      const isTimeout = e?.code === 'ECONNABORTED' || e?.message?.includes('timeout');
      const errMsg = isTimeout
        ? 'Processing timed out after 60 seconds. High network latency or large row processing took too long. You can click "Retry Upload" below.'
        : e?.response?.data?.message ||
          e?.response?.data?.detail ||
          e?.message ||
          'Bulk upload failed.';
      setUploadError(errMsg);
      setFeedback({ type: 'error', message: errMsg });
      setUploading(false);
    }
  };

  const handleConfirmAssemble = async () => {
    if (!assemblePreview?.file_token) return;
    setIsConfirming(true);
    setUploadError(null);
    try {
      const token = getAccessToken();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await axios.post<AssembleJobStatus>(
        `${getApiBaseUrl()}/api/v1/masters/product-master/assemble/confirm`,
        { file_token: assemblePreview.file_token },
        { headers, timeout: 60000 }
      );

      const job = res.data;
      if (job.status === 'completed') {
        const msg = `Bulk import complete: ${job.upserted} records successfully upserted.`;
        setFeedback({ type: 'success', message: msg });
        setToast({ type: 'success', message: msg });
        setIsUploadModalOpen(false);
        setAssemblePreview(null);
        setSelectedFile(null);
        setIsConfirming(false);
        await loadData();
      } else {
        setAssembleJob(job);
        pollAssembleJob(job.job_id);
      }
    } catch (e: any) {
      const isTimeout = e?.code === 'ECONNABORTED' || e?.message?.includes('timeout');
      const errMsg = isTimeout
        ? 'Import request timed out. Your import may be continuing in the background. You can retry if needed.'
        : e?.response?.data?.message || e?.response?.data?.detail || e?.message || 'Import confirmation failed.';
      setUploadError(errMsg);
      setIsConfirming(false);
    }
  };

  const pollAssembleJob = (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const token = getAccessToken();
        const headers: Record<string, string> = {};
        if (token) headers.Authorization = `Bearer ${token}`;

        const res = await axios.get<AssembleJobStatus>(
          `${getApiBaseUrl()}/api/v1/masters/product-master/assemble/jobs/${jobId}`,
          { headers }
        );
        const job = res.data;
        setAssembleJob(job);

        if (job.status === 'completed') {
          clearInterval(interval);
          const msg = `Bulk import complete: ${job.upserted} records successfully upserted.`;
          setFeedback({ type: 'success', message: msg });
          setToast({ type: 'success', message: msg });
          setIsUploadModalOpen(false);
          setAssemblePreview(null);
          setAssembleJob(null);
          setSelectedFile(null);
          setIsConfirming(false);
          await loadData();
        } else if (job.status === 'failed') {
          clearInterval(interval);
          setUploadError(`Import failed: ${job.error_message || 'Background import failed.'}`);
          setIsConfirming(false);
        }
      } catch {
        clearInterval(interval);
        setUploadError('Failed to retrieve background job progress.');
        setIsConfirming(false);
      }
    }, 1500);
  };

  const handleDownloadErrorReport = async () => {
    if (!assemblePreview?.file_token) return;
    try {
      const token = getAccessToken();
      const url = `${getApiBaseUrl()}/api/v1/masters/product-master/assemble/preview-errors?file_token=${encodeURIComponent(
        assemblePreview.file_token
      )}`;
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Failed to download error report');
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `assemble_import_errors_${assemblePreview.source_filename || 'assemble.xlsx'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(blobUrl);
    } catch (err: any) {
      setUploadError(`Error report download failed: ${err.message}`);
    }
  };

  const handleResetUpload = () => {
    setAssemblePreview(null);
    setAssembleJob(null);
    setSelectedFile(null);
    setUploadError(null);
    setUploading(false);
    setIsConfirming(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // Drag and drop handlers
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  // ---------------------------------------------------------------------------
  // Localized Inline Column Search Filters
  // ---------------------------------------------------------------------------

  const filteredConsumables = useMemo(() => {
    return consumables.filter((c) => {
      return (
        (!consumableFilters.supplier_id || (c.supplier_id && c.supplier_id.toLowerCase().includes(consumableFilters.supplier_id.toLowerCase()))) &&
        (!consumableFilters.supplier_name || c.supplier_name.toLowerCase().includes(consumableFilters.supplier_name.toLowerCase())) &&
        (!consumableFilters.item_id || c.item_id.toLowerCase().includes(consumableFilters.item_id.toLowerCase())) &&
        (!consumableFilters.category || c.category.toLowerCase().includes(consumableFilters.category.toLowerCase())) &&
        (!consumableFilters.type_of_material || c.type_of_material.toLowerCase().includes(consumableFilters.type_of_material.toLowerCase())) &&
        (!consumableFilters.description || c.description.toLowerCase().includes(consumableFilters.description.toLowerCase())) &&
        (!consumableFilters.output_unit || c.output_unit.toLowerCase().includes(consumableFilters.output_unit.toLowerCase())) &&
        (!consumableFilters.rate || (c.rate !== null && c.rate.toString().includes(consumableFilters.rate)))
      );
    });
  }, [consumables, consumableFilters]);

  const filteredAssembleRows = useMemo(() => {
    return assembleRows.filter((r) => {
      return (
        (!assembleFilters.consumable_item || r.consumable_item.toLowerCase().includes(assembleFilters.consumable_item.toLowerCase())) &&
        (!assembleFilters.part_no_saleable_item || r.part_no_saleable_item.toLowerCase().includes(assembleFilters.part_no_saleable_item.toLowerCase())) &&
        (!assembleFilters.used_for_name_of_saleable_part || r.used_for_name_of_saleable_part.toLowerCase().includes(assembleFilters.used_for_name_of_saleable_part.toLowerCase())) &&
        (!assembleFilters.used_part_no_prd_order || r.used_part_no_prd_order.toLowerCase().includes(assembleFilters.used_part_no_prd_order.toLowerCase())) &&
        (!assembleFilters.process_name || r.process_name.toLowerCase().includes(assembleFilters.process_name.toLowerCase())) &&
        (!assembleFilters.material_thickness_in_mm_gsm || r.material_thickness_in_mm_gsm.toLowerCase().includes(assembleFilters.material_thickness_in_mm_gsm.toLowerCase())) &&
        (!assembleFilters.no_of_process_per_part || r.no_of_process_per_part.toString().includes(assembleFilters.no_of_process_per_part)) &&
        (!assembleFilters.output_unit || r.output_unit.toLowerCase().includes(assembleFilters.output_unit.toLowerCase())) &&
        (!assembleFilters.rate || (r.rate !== null && r.rate.toString().includes(assembleFilters.rate)))
      );
    });
  }, [assembleRows, assembleFilters]);

  const filteredSalesParts = useMemo(() => {
    return salesParts.filter((p) => {
      return (
        (!salesPartFilters.s_no || p.s_no.toString().includes(salesPartFilters.s_no)) &&
        (!salesPartFilters.part_no || p.part_no.toLowerCase().includes(salesPartFilters.part_no.toLowerCase())) &&
        (!salesPartFilters.item_id || p.item_id.toLowerCase().includes(salesPartFilters.item_id.toLowerCase())) &&
        (!salesPartFilters.part_description || p.part_description.toLowerCase().includes(salesPartFilters.part_description.toLowerCase())) &&
        (!salesPartFilters.uom || p.uom.toLowerCase().includes(salesPartFilters.uom.toLowerCase()))
      );
    });
  }, [salesParts, salesPartFilters]);

  if (!canRead) {
    return (
      <div className="p-6 bg-erp-vanilla min-h-full">
        <p role="alert" className="text-sm text-erp-topaz font-medium">
          You do not have permission to view product master records.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Title & Context with Top Right Action */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-erp-chocolate">Product Master</h1>
          <p className="text-sm text-erp-chocolate/70 mt-1">
            Authoritative master catalog for raw consumables, sales parts, and assembly BOM mappings.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setUploadError(null);
            setUploadProgress(0);
            setUploadPhase('idle');
            setIsUploadModalOpen(true);
          }}
          disabled={!canCreate}
          className="inline-flex items-center gap-2 bg-erp-orange hover:bg-erp-tenne text-white text-xs sm:text-sm font-semibold px-4 py-2.5 rounded-lg shadow-sm hover:shadow transition-all disabled:opacity-50"
        >
          Bulk Import ☁️
        </button>
      </div>

      {/* Task 2: Dashboard KPI Cards (Top Row) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Consumables */}
        <div className="bg-white rounded-xl p-5 shadow-md border border-erp-dark-vanilla/30 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-erp-chocolate/70 uppercase tracking-wider">Total Consumables</p>
            <p className="text-2xl font-bold text-erp-chocolate mt-1">{loading ? '—' : consumables.length}</p>
            <div className="mt-2 flex items-center gap-1">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                ↑ Active Catalog
              </span>
            </div>
          </div>
          <div className="w-12 h-12 rounded-xl bg-erp-vanilla/60 flex items-center justify-center text-xl text-erp-orange shadow-xs">
            📦
          </div>
        </div>

        {/* Card 2: Active Suppliers */}
        <div className="bg-white rounded-xl p-5 shadow-md border border-erp-dark-vanilla/30 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-erp-chocolate/70 uppercase tracking-wider">Active Suppliers</p>
            <p className="text-2xl font-bold text-erp-chocolate mt-1">
              {loading ? '—' : new Set(consumables.map(c => c.supplier_name?.trim()).filter(Boolean)).size}
            </p>
            <div className="mt-2 flex items-center gap-1">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                ↑ Verified Sources
              </span>
            </div>
          </div>
          <div className="w-12 h-12 rounded-xl bg-erp-vanilla/60 flex items-center justify-center text-xl text-erp-orange shadow-xs">
            🏭
          </div>
        </div>

        {/* Card 3: Assembly Mappings */}
        <div className="bg-white rounded-xl p-5 shadow-md border border-erp-dark-vanilla/30 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-erp-chocolate/70 uppercase tracking-wider">Assembly BOMs</p>
            <p className="text-2xl font-bold text-erp-chocolate mt-1">
              {assembleRows.length > 0 ? assembleRows.length : '—'}
            </p>
            <div className="mt-2 flex items-center gap-1">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                ↑ BOM Routes
              </span>
            </div>
          </div>
          <div className="w-12 h-12 rounded-xl bg-erp-vanilla/60 flex items-center justify-center text-xl text-erp-orange shadow-xs">
            ⚙️
          </div>
        </div>

        {/* Card 4: Sales Parts */}
        <div className="bg-white rounded-xl p-5 shadow-md border border-erp-dark-vanilla/30 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-erp-chocolate/70 uppercase tracking-wider">Sales Parts</p>
            <p className="text-2xl font-bold text-erp-chocolate mt-1">
              {salesParts.length > 0 ? salesParts.length : '—'}
            </p>
            <div className="mt-2 flex items-center gap-1">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                ↑ Registered SKUs
              </span>
            </div>
          </div>
          <div className="w-12 h-12 rounded-xl bg-erp-vanilla/60 flex items-center justify-center text-xl text-erp-orange shadow-xs">
            🏷️
          </div>
        </div>
      </div>

      {/* Top Tabs Bar */}
      <div className="flex border-b border-erp-dark-vanilla/30 space-x-1">
        <button
          onClick={() => setActiveTab('consumables')}
          className={`px-5 py-2.5 text-sm font-semibold rounded-t-lg transition-all ${
            activeTab === 'consumables'
              ? 'bg-erp-orange text-white shadow-xs'
              : 'text-erp-chocolate/75 hover:text-erp-chocolate hover:bg-white/60'
          }`}
        >
          List of Consumables
        </button>
        <button
          onClick={() => setActiveTab('assemble')}
          className={`px-5 py-2.5 text-sm font-semibold rounded-t-lg transition-all ${
            activeTab === 'assemble'
              ? 'bg-erp-orange text-white shadow-xs'
              : 'text-erp-chocolate/75 hover:text-erp-chocolate hover:bg-white/60'
          }`}
        >
          Consumable for Assemble
        </button>
        <button
          onClick={() => setActiveTab('sales_parts')}
          className={`px-5 py-2.5 text-sm font-semibold rounded-t-lg transition-all ${
            activeTab === 'sales_parts'
              ? 'bg-erp-orange text-white shadow-xs'
              : 'text-erp-chocolate/75 hover:text-erp-chocolate hover:bg-white/60'
          }`}
        >
          List of Sales Parts
        </button>
      </div>

      {/* System Feedback Alert */}
      {feedback && (
        <div
          className={`p-4 rounded-xl text-sm border flex items-center justify-between ${
            feedback.type === 'success'
              ? 'bg-emerald-50 border-emerald-300 text-emerald-900'
              : 'bg-erp-orange/10 border-erp-orange/30 text-erp-chocolate'
          }`}
        >
          <span>{feedback.message}</span>
          <button
            onClick={() => setFeedback(null)}
            className="text-xs font-semibold uppercase hover:underline ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 1: LIST OF CONSUMABLES                                                */}
      {/* ========================================================================= */}
      {activeTab === 'consumables' && (
        <div className="space-y-6">
          {/* Horizontal Single Consumable Intake Panel */}
          <div className="bg-white rounded-xl p-6 border border-erp-dark-vanilla/30 shadow-md">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-erp-dark-vanilla/20 gap-3">
              <div>
                <h2 className="text-base font-bold text-erp-chocolate flex items-center gap-2">
                  {editingConsumableId ? 'Edit Consumable' : 'Single Consumable Intake'}
                  {editingConsumableId && (
                    <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                      Editing: {consumableForm.item_id || 'Selected item'}
                    </span>
                  )}
                </h2>
                <p className="text-xs text-erp-chocolate/70 mt-0.5">
                  {editingConsumableId
                    ? 'Modify the fields below and click Update Record to save changes.'
                    : 'Fast manual consumable entry matching inventory columns with auto-provisioned units.'}
                </p>
              </div>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                {editingConsumableId ? (
                  <button
                    type="button"
                    onClick={cancelEditConsumable}
                    className="text-xs px-3.5 py-2 border border-erp-dark-vanilla/40 rounded-lg hover:bg-erp-vanilla/40 transition-colors font-medium text-erp-chocolate"
                  >
                    Cancel Edit
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      setConsumableForm({
                        supplier_id: '',
                        supplier_name: '',
                        item_id: '',
                        category: '',
                        type_of_material: '',
                        description: '',
                        output_unit: 'PCS',
                        rate: '',
                      })
                    }
                    className="text-xs px-3.5 py-2 border border-erp-dark-vanilla/40 rounded-lg hover:bg-erp-vanilla/40 transition-colors font-medium text-erp-chocolate"
                  >
                    Clear
                  </button>
                )}
                <button
                  type="submit"
                  form="single-consumable-form"
                  disabled={Boolean(submitting || (!editingConsumableId && !canCreate) || (editingConsumableId && !canEdit))}
                  className="bg-erp-orange hover:bg-erp-tenne text-white text-xs font-semibold px-5 py-2 rounded-lg shadow-sm hover:shadow transition-all disabled:opacity-50"
                >
                  {submitting ? 'Saving…' : editingConsumableId ? 'Update Record' : 'Save Consumable'}
                </button>
              </div>
            </div>

            <form id="single-consumable-form" onSubmit={handleConsumableSubmit} className="space-y-5">
              {/* Section 1: Basic Information */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-erp-topaz mb-2.5 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-erp-orange" />
                  Basic Information
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                  <div>
                    <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                      Item ID <span className="text-erp-orange">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="CS-ST-004"
                      value={consumableForm.item_id}
                      onChange={(e) => setConsumableForm({ ...consumableForm, item_id: e.target.value })}
                      className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono uppercase"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                      Description
                    </label>
                    <input
                      type="text"
                      placeholder="CR Steel Strip"
                      value={consumableForm.description}
                      onChange={(e) => setConsumableForm({ ...consumableForm, description: e.target.value })}
                      className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                      Category
                    </label>
                    <input
                      type="text"
                      placeholder="Raw Material"
                      value={consumableForm.category}
                      onChange={(e) => setConsumableForm({ ...consumableForm, category: e.target.value })}
                      className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                      Type of Material
                    </label>
                    <input
                      type="text"
                      placeholder="CR Steel"
                      value={consumableForm.type_of_material}
                      onChange={(e) => setConsumableForm({ ...consumableForm, type_of_material: e.target.value })}
                      className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange"
                    />
                  </div>
                </div>
              </div>

              {/* Split Row for Section 2 & Section 3 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 pt-3 border-t border-erp-dark-vanilla/15">
                {/* Section 2: Supplier Details */}
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-erp-topaz mb-2.5 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-erp-orange" />
                    Supplier Details
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Supplier ID
                      </label>
                      <input
                        type="text"
                        placeholder="SUP-001"
                        value={consumableForm.supplier_id}
                        onChange={(e) => setConsumableForm({ ...consumableForm, supplier_id: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Supplier Name
                      </label>
                      <input
                        type="text"
                        placeholder="TATA Steel"
                        value={consumableForm.supplier_name}
                        onChange={(e) => setConsumableForm({ ...consumableForm, supplier_name: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange"
                      />
                    </div>
                  </div>
                </div>

                {/* Section 3: Inventory Control & Pricing */}
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-erp-topaz mb-2.5 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-erp-orange" />
                    Inventory Control & Pricing
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Output Unit
                      </label>
                      <input
                        type="text"
                        placeholder="KG / PCS"
                        value={consumableForm.output_unit}
                        onChange={(e) => setConsumableForm({ ...consumableForm, output_unit: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange uppercase"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Rate
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="85.50"
                        value={consumableForm.rate}
                        onChange={(e) => setConsumableForm({ ...consumableForm, rate: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </form>
          </div>

          {/* Consumables Data Table with Localized Inline Search */}
          <div className="bg-white rounded-xl p-6 border border-erp-dark-vanilla/30 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-erp-chocolate">List of Consumables Table</h3>
                <p className="text-xs text-erp-chocolate/70 mt-0.5">
                  Showing {filteredConsumables.length} of {consumables.length} consumables. Use header filters below to narrow results.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() =>
                    setConsumableFilters({
                      supplier_id: '',
                      supplier_name: '',
                      item_id: '',
                      category: '',
                      type_of_material: '',
                      description: '',
                      output_unit: '',
                      rate: '',
                    })
                  }
                  className="text-xs text-erp-chocolate/70 hover:text-erp-orange hover:underline font-semibold"
                >
                  Clear Filters
                </button>
                <button
                  onClick={loadData}
                  disabled={loading}
                  className="text-xs text-erp-orange hover:text-erp-tenne hover:underline font-semibold"
                >
                  {loading ? 'Refreshing…' : '↻ Refresh'}
                </button>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-gray-100 bg-white shadow-xs">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-erp-vanilla/35 text-erp-chocolate font-semibold border-b border-gray-200">
                  <tr>
                    {/* 1. Supplier ID Header with inline search */}
                    <th className="p-3 min-w-[130px]">
                      <div>Supplier ID</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={consumableFilters.supplier_id}
                        onChange={(e) => setConsumableFilters({ ...consumableFilters, supplier_id: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 2. Supplier name Header with inline search */}
                    <th className="p-3 min-w-[150px]">
                      <div>Supplier name</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={consumableFilters.supplier_name}
                        onChange={(e) => setConsumableFilters({ ...consumableFilters, supplier_name: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 3. Item Id Header with inline search */}
                    <th className="p-3 min-w-[140px]">
                      <div>Item Id</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={consumableFilters.item_id}
                        onChange={(e) => setConsumableFilters({ ...consumableFilters, item_id: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal uppercase focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 4. Category Header with inline search */}
                    <th className="p-3 min-w-[120px]">
                      <div>Category</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={consumableFilters.category}
                        onChange={(e) => setConsumableFilters({ ...consumableFilters, category: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 5. Type of material Header with inline search */}
                    <th className="p-3 min-w-[130px]">
                      <div>Type of material</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={consumableFilters.type_of_material}
                        onChange={(e) => setConsumableFilters({ ...consumableFilters, type_of_material: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 6. Description Header with inline search */}
                    <th className="p-3 min-w-[200px]">
                      <div>Description</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={consumableFilters.description}
                        onChange={(e) => setConsumableFilters({ ...consumableFilters, description: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 7. Output/Unit Header with inline search */}
                    <th className="p-3 min-w-[90px] text-center">
                      <div>Output/Unit</div>
                      <input
                        type="text"
                        placeholder="UOM"
                        value={consumableFilters.output_unit}
                        onChange={(e) => setConsumableFilters({ ...consumableFilters, output_unit: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-1 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal text-center uppercase focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 8. Rate Header with inline search */}
                    <th className="p-3 min-w-[100px] text-right">
                      <div>Rate</div>
                      <input
                        type="text"
                        placeholder="Rate"
                        value={consumableFilters.rate}
                        onChange={(e) => setConsumableFilters({ ...consumableFilters, rate: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-1 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal text-right font-mono focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 9. Actions Header */}
                    <th className="p-3 w-24 text-center">
                      <div>Actions</div>
                      <div className="mt-1.5 text-[10px] text-erp-chocolate/50 font-normal">Edit / Del</div>
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-100 font-mono">
                  {loading ? (
                    <TableSkeletonRows rows={7} columns={9} />
                  ) : filteredConsumables.length > 0 ? (
                    filteredConsumables.map((row) => (
                      <tr
                        key={row.id}
                        className={`transition-colors ${
                          editingConsumableId === row.id
                            ? 'bg-erp-orange/10 font-semibold'
                            : 'hover:bg-erp-vanilla/25'
                        }`}
                      >
                        <td className="p-3 font-mono text-erp-chocolate/75 whitespace-nowrap">
                          {row.supplier_id || '—'}
                        </td>
                        <td className="p-3 font-sans text-erp-chocolate/90">
                          {row.supplier_name || '—'}
                        </td>
                        <td className="p-3 font-bold text-erp-chocolate whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <span>{row.item_id}</span>
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                              {row.is_active !== false ? 'Active' : 'Inactive'}
                            </span>
                          </div>
                        </td>
                        <td className="p-3 font-sans text-erp-chocolate/80">
                          {row.category ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-erp-tangerine/15 text-erp-chocolate border border-erp-tangerine/25">
                              {row.category}
                            </span>
                          ) : (
                            <span className="text-erp-chocolate/40">—</span>
                          )}
                        </td>
                        <td className="p-3 font-sans text-erp-chocolate/80">
                          {row.type_of_material ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-erp-dark-vanilla/25 text-erp-chocolate border border-erp-dark-vanilla/40">
                              {row.type_of_material}
                            </span>
                          ) : (
                            <span className="text-erp-chocolate/40">—</span>
                          )}
                        </td>
                        <td className="p-3 font-sans font-medium text-erp-chocolate/90">
                          {row.description || '—'}
                        </td>
                        <td className="p-3 text-center">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-erp-vanilla text-erp-chocolate border border-erp-dark-vanilla/40">
                            {row.output_unit}
                          </span>
                        </td>
                        <td className="p-3 text-right font-semibold text-erp-tenne">
                          {row.rate !== null && row.rate !== undefined ? row.rate : '—'}
                        </td>
                        <td className="p-3 text-center whitespace-nowrap">
                          <div className="flex items-center justify-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => startEditConsumable(row)}
                              disabled={!canEdit}
                              title="Edit consumable"
                              className="p-1 rounded text-erp-chocolate/70 hover:text-erp-orange hover:bg-erp-orange/10 transition-colors disabled:opacity-40 text-xs"
                            >
                              ✏️
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeactivate('consumables', row.id, row.item_id)}
                              disabled={!canDelete || actionLoadingId === row.id}
                              title="Delete consumable"
                              className="p-1 rounded text-erp-chocolate/70 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-40 text-xs"
                            >
                              {actionLoadingId === row.id ? '…' : '🗑️'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={9} className="p-8 text-center text-erp-chocolate/60 italic font-sans">
                        No consumables match your search filters or the master table is empty.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: CONSUMABLE FOR ASSEMBLE (BOM MAPPING)                              */}
      {/* ========================================================================= */}
      {activeTab === 'assemble' && (
        <div className="space-y-6">
          {/* Horizontal Single Assembly Intake Panel */}
          <div className="bg-white rounded-xl p-6 border border-erp-dark-vanilla/30 shadow-md">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-erp-dark-vanilla/20 gap-3">
              <div>
                <h2 className="text-base font-bold text-erp-chocolate flex items-center gap-2">
                  {editingAssembleId ? 'Edit Assembly Mapping' : 'Single Assembly Intake'}
                  {editingAssembleId && (
                    <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                      Editing: {assembleForm.consumable_item} → {assembleForm.part_no_saleable_item}
                    </span>
                  )}
                </h2>
                <p className="text-xs text-erp-chocolate/70 mt-0.5">
                  {editingAssembleId
                    ? 'Modify assembly process parameters below and click Update Record.'
                    : 'Map raw consumables to finished saleable parts with process parameters.'}
                </p>
              </div>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                {editingAssembleId ? (
                  <button
                    type="button"
                    onClick={cancelEditAssemble}
                    className="text-xs px-3.5 py-2 border border-erp-dark-vanilla/40 rounded-lg hover:bg-erp-vanilla/40 transition-colors font-medium text-erp-chocolate"
                  >
                    Cancel Edit
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      setAssembleForm({
                        consumable_item: '',
                        part_no_saleable_item: '',
                        used_for_name_of_saleable_part: '',
                        used_part_no_prd_order: '',
                        process_name: 'ASSEMBLY',
                        material_thickness_in_mm_gsm: '',
                        no_of_process_per_part: '1.0',
                        output_unit: 'PCS',
                        rate: '',
                      })
                    }
                    className="text-xs px-3.5 py-2 border border-erp-dark-vanilla/40 rounded-lg hover:bg-erp-vanilla/40 transition-colors font-medium text-erp-chocolate"
                  >
                    Clear
                  </button>
                )}
                <button
                  type="submit"
                  form="single-assemble-form"
                  disabled={Boolean(submitting || (!editingAssembleId && !canCreate) || (editingAssembleId && !canEdit))}
                  className="bg-erp-orange hover:bg-erp-tenne text-white text-xs font-semibold px-5 py-2 rounded-lg shadow-sm hover:shadow transition-all disabled:opacity-50"
                >
                  {submitting ? 'Saving…' : editingAssembleId ? 'Update Record' : 'Save Assembly Mapping'}
                </button>
              </div>
            </div>

            <form id="single-assemble-form" onSubmit={handleAssembleSubmit} className="space-y-5">
              {/* Section 1: Part & Consumable Mapping */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-erp-topaz mb-2.5 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-erp-orange" />
                  Part & Consumable Mapping
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
                  <div>
                    <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                      Consumable Description <span className="text-erp-orange">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="CS-ST-004"
                      value={assembleForm.consumable_item}
                      onChange={(e) => setAssembleForm({ ...assembleForm, consumable_item: e.target.value })}
                      className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange uppercase font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                      Part No. of Saleable Item <span className="text-erp-orange">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="PN-DOOR-LH"
                      value={assembleForm.part_no_saleable_item}
                      onChange={(e) => setAssembleForm({ ...assembleForm, part_no_saleable_item: e.target.value })}
                      className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono uppercase"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                      Used for – Name of Saleable Part
                    </label>
                    <input
                      type="text"
                      placeholder="Outer Door LH"
                      value={assembleForm.used_for_name_of_saleable_part}
                      onChange={(e) => setAssembleForm({ ...assembleForm, used_for_name_of_saleable_part: e.target.value })}
                      className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                      Used Part No. (PRD Order)
                    </label>
                    <input
                      type="text"
                      placeholder="PRD-PART-01"
                      value={assembleForm.used_part_no_prd_order}
                      onChange={(e) => setAssembleForm({ ...assembleForm, used_part_no_prd_order: e.target.value })}
                      className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono"
                    />
                  </div>
                </div>
              </div>

              {/* Split Row for Section 2 & Section 3 */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 pt-3 border-t border-erp-dark-vanilla/15">
                {/* Section 2: Process Specifications */}
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-erp-topaz mb-2.5 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-erp-orange" />
                    Process Specifications
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Process Name
                      </label>
                      <input
                        type="text"
                        placeholder="ASSEMBLY"
                        value={assembleForm.process_name}
                        onChange={(e) => setAssembleForm({ ...assembleForm, process_name: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange uppercase"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Material Thickness in mm / GSM
                      </label>
                      <input
                        type="text"
                        placeholder="1.20mm"
                        value={assembleForm.material_thickness_in_mm_gsm}
                        onChange={(e) => setAssembleForm({ ...assembleForm, material_thickness_in_mm_gsm: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        No. of Processes per Part
                      </label>
                      <input
                        type="number"
                        step="0.0001"
                        placeholder="1.0000"
                        value={assembleForm.no_of_process_per_part}
                        onChange={(e) => setAssembleForm({ ...assembleForm, no_of_process_per_part: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono"
                      />
                    </div>
                  </div>
                </div>

                {/* Section 3: Valuation & Unit */}
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-erp-topaz mb-2.5 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-erp-orange" />
                    Valuation & Unit
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Output / Unit
                      </label>
                      <input
                        type="text"
                        placeholder="PCS"
                        value={assembleForm.output_unit}
                        onChange={(e) => setAssembleForm({ ...assembleForm, output_unit: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange uppercase"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Rate
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="85.50"
                        value={assembleForm.rate}
                        onChange={(e) => setAssembleForm({ ...assembleForm, rate: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </form>
          </div>

          {/* Assembly Data Table with Localized Inline Search */}
          <div className="bg-white rounded-xl p-6 border border-erp-dark-vanilla/30 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-erp-chocolate">Consumable for Assemble Table</h3>
                <p className="text-xs text-erp-chocolate/70 mt-0.5">
                  Showing {filteredAssembleRows.length} of {assembleRows.length} mappings.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() =>
                    setAssembleFilters({
                      consumable_item: '',
                      part_no_saleable_item: '',
                      used_for_name_of_saleable_part: '',
                      used_part_no_prd_order: '',
                      process_name: '',
                      material_thickness_in_mm_gsm: '',
                      no_of_process_per_part: '',
                      output_unit: '',
                      rate: '',
                    })
                  }
                  className="text-xs text-erp-chocolate/70 hover:text-erp-orange hover:underline font-semibold"
                >
                  Clear Filters
                </button>
                <button
                  onClick={loadData}
                  disabled={loading}
                  className="text-xs text-erp-orange hover:text-erp-tenne hover:underline font-semibold"
                >
                  {loading ? 'Refreshing…' : '↻ Refresh'}
                </button>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-gray-100 bg-white shadow-xs">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-erp-vanilla/35 text-erp-chocolate font-semibold border-b border-gray-200">
                  <tr>
                    <th className="p-3 min-w-[150px]">
                      <div>Consumable Description</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={assembleFilters.consumable_item}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, consumable_item: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[150px]">
                      <div>Part No. of Saleable Item</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={assembleFilters.part_no_saleable_item}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, part_no_saleable_item: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[180px]">
                      <div>Used for – Name of Saleable Part</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={assembleFilters.used_for_name_of_saleable_part}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, used_for_name_of_saleable_part: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[150px]">
                      <div>Used Part No. (PRD Order)</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={assembleFilters.used_part_no_prd_order}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, used_part_no_prd_order: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[120px]">
                      <div>Process Name</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={assembleFilters.process_name}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, process_name: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[160px]">
                      <div>Material Thickness in mm / GSM</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={assembleFilters.material_thickness_in_mm_gsm}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, material_thickness_in_mm_gsm: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[150px] text-right">
                      <div>No. of Processes per Part</div>
                      <input
                        type="text"
                        placeholder="Qty"
                        value={assembleFilters.no_of_process_per_part}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, no_of_process_per_part: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-1 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal text-right font-mono focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[100px] text-center">
                      <div>Output / Unit</div>
                      <input
                        type="text"
                        placeholder="UOM"
                        value={assembleFilters.output_unit}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, output_unit: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-1 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal text-center uppercase focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[90px] text-right">
                      <div>Rate</div>
                      <input
                        type="text"
                        placeholder="Rate"
                        value={assembleFilters.rate}
                        onChange={(e) => setAssembleFilters({ ...assembleFilters, rate: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-1 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal text-right font-mono focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 10. Actions Header */}
                    <th className="p-3 w-24 text-center">
                      <div>Actions</div>
                      <div className="mt-1.5 text-[10px] text-erp-chocolate/50 font-normal">Edit / Del</div>
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-100 font-mono">
                  {loading ? (
                    <TableSkeletonRows rows={7} columns={10} />
                  ) : filteredAssembleRows.length > 0 ? (
                    filteredAssembleRows.map((row) => (
                      <tr
                        key={row.id}
                        className={`transition-colors ${
                          editingAssembleId === row.id
                            ? 'bg-erp-orange/10 font-semibold'
                            : 'hover:bg-erp-vanilla/25'
                        }`}
                      >
                        <td className="p-3 font-bold text-erp-chocolate whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <span>{row.consumable_item}</span>
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                              {row.is_active !== false ? 'Active' : 'Inactive'}
                            </span>
                          </div>
                        </td>
                        <td className="p-3 font-semibold text-erp-chocolate whitespace-nowrap">
                          {row.part_no_saleable_item}
                        </td>
                        <td className="p-3 font-sans font-medium text-erp-chocolate/90">
                          {row.used_for_name_of_saleable_part}
                        </td>
                        <td className="p-3 text-erp-chocolate/75 whitespace-nowrap">
                          {row.used_part_no_prd_order}
                        </td>
                        <td className="p-3 font-sans text-erp-chocolate/80">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-erp-tangerine/15 text-erp-chocolate border border-erp-tangerine/25">
                            {row.process_name}
                          </span>
                        </td>
                        <td className="p-3 text-erp-chocolate/75">
                          {row.material_thickness_in_mm_gsm}
                        </td>
                        <td className="p-3 text-right font-bold text-erp-chocolate">
                          {row.no_of_process_per_part.toFixed(4)}
                        </td>
                        <td className="p-3 text-center">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-erp-vanilla text-erp-chocolate border border-erp-dark-vanilla/40">
                            {row.output_unit}
                          </span>
                        </td>
                        <td className="p-3 text-right font-semibold text-erp-tenne">
                          {row.rate !== null ? `₹${row.rate.toFixed(2)}` : '—'}
                        </td>
                        <td className="p-3 text-center whitespace-nowrap">
                          <div className="flex items-center justify-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => startEditAssemble(row)}
                              disabled={!canEdit}
                              title="Edit assembly mapping"
                              className="p-1 rounded text-erp-chocolate/70 hover:text-erp-orange hover:bg-erp-orange/10 transition-colors disabled:opacity-40 text-xs"
                            >
                              ✏️
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeactivate('assemble', row.id, `${row.consumable_item} -> ${row.part_no_saleable_item}`)}
                              disabled={!canDelete || actionLoadingId === row.id}
                              title="Delete assembly mapping"
                              className="p-1 rounded text-erp-chocolate/70 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-40 text-xs"
                            >
                              {actionLoadingId === row.id ? '…' : '🗑️'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={10} className="p-8 text-center text-erp-chocolate/60 italic font-sans">
                        No assembly mappings match your search filters or the table is empty.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: LIST OF SALES PARTS                                                */}
      {/* ========================================================================= */}
      {activeTab === 'sales_parts' && (
        <div className="space-y-6">
          {/* Horizontal Single Sales Part Intake Panel */}
          <div className="bg-white rounded-xl p-6 border border-erp-dark-vanilla/30 shadow-md">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 mb-5 border-b border-erp-dark-vanilla/20 gap-3">
              <div>
                <h2 className="text-base font-bold text-erp-chocolate flex items-center gap-2">
                  {editingSalesPartId ? 'Edit Sales Part' : 'Single Sales Part Intake'}
                  {editingSalesPartId && (
                    <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                      Editing: {salesPartForm.part_no || 'Selected part'}
                    </span>
                  )}
                </h2>
                <p className="text-xs text-erp-chocolate/70 mt-0.5">
                  {editingSalesPartId
                    ? 'Modify the sales part details below and click Update Record.'
                    : 'Register finished saleable components with compound (Part No, Item ID) uniqueness.'}
                </p>
              </div>
              <div className="flex items-center gap-2 self-end sm:self-auto">
                {editingSalesPartId ? (
                  <button
                    type="button"
                    onClick={cancelEditSalesPart}
                    className="text-xs px-3.5 py-2 border border-erp-dark-vanilla/40 rounded-lg hover:bg-erp-vanilla/40 transition-colors font-medium text-erp-chocolate"
                  >
                    Cancel Edit
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      setSalesPartForm({
                        part_no: '',
                        item_id: '',
                        part_description: '',
                        uom: 'PCS',
                      })
                    }
                    className="text-xs px-3.5 py-2 border border-erp-dark-vanilla/40 rounded-lg hover:bg-erp-vanilla/40 transition-colors font-medium text-erp-chocolate"
                  >
                    Clear
                  </button>
                )}
                <button
                  type="submit"
                  form="single-sales-part-form"
                  disabled={Boolean(submitting || (!editingSalesPartId && !canCreate) || (editingSalesPartId && !canEdit))}
                  className="bg-erp-orange hover:bg-erp-tenne text-white text-xs font-semibold px-5 py-2 rounded-lg shadow-sm hover:shadow transition-all disabled:opacity-50"
                >
                  {submitting ? 'Saving…' : editingSalesPartId ? 'Update Record' : 'Save Sales Part'}
                </button>
              </div>
            </div>

            <form id="single-sales-part-form" onSubmit={handleSalesPartSubmit} className="space-y-5">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* Section 1: Part Identification */}
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-erp-topaz mb-2.5 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-erp-orange" />
                    Part Identification
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Part No. <span className="text-erp-orange">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="PN-DOOR-LH"
                        value={salesPartForm.part_no}
                        onChange={(e) => setSalesPartForm({ ...salesPartForm, part_no: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono uppercase"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Item ID <span className="text-erp-orange">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="ITM-DOOR-01"
                        value={salesPartForm.item_id}
                        onChange={(e) => setSalesPartForm({ ...salesPartForm, item_id: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange font-mono uppercase"
                      />
                    </div>
                  </div>
                </div>

                {/* Section 2: Specifications & Unit */}
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-erp-topaz mb-2.5 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-erp-orange" />
                    Specifications & Unit
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Part Description <span className="text-erp-orange">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        placeholder="Door Assembly Outer Panel LH"
                        value={salesPartForm.part_description}
                        onChange={(e) => setSalesPartForm({ ...salesPartForm, part_description: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-semibold text-erp-chocolate mb-1">
                        Unit of Measure (UOM)
                      </label>
                      <input
                        type="text"
                        placeholder="PCS"
                        value={salesPartForm.uom}
                        onChange={(e) => setSalesPartForm({ ...salesPartForm, uom: e.target.value })}
                        className="w-full text-xs px-3 py-2 bg-white rounded-lg border border-erp-dark-vanilla/40 focus:outline-none focus:border-erp-orange focus:ring-1 focus:ring-erp-orange uppercase"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </form>
          </div>

          {/* Sales Parts Data Table with Localized Inline Search */}
          <div className="bg-white rounded-xl p-6 border border-erp-dark-vanilla/30 shadow-md">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-erp-chocolate">List of Sales Parts Table</h3>
                <p className="text-xs text-erp-chocolate/70 mt-0.5">
                  Showing {filteredSalesParts.length} of {salesParts.length} sales parts.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() =>
                    setSalesPartFilters({
                      s_no: '',
                      part_no: '',
                      item_id: '',
                      part_description: '',
                      uom: '',
                    })
                  }
                  className="text-xs text-erp-chocolate/70 hover:text-erp-orange hover:underline font-semibold"
                >
                  Clear Filters
                </button>
                <button
                  onClick={loadData}
                  disabled={loading}
                  className="text-xs text-erp-orange hover:text-erp-tenne hover:underline font-semibold"
                >
                  {loading ? 'Refreshing…' : '↻ Refresh'}
                </button>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-gray-100 bg-white shadow-xs">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-erp-vanilla/35 text-erp-chocolate font-semibold border-b border-gray-200">
                  <tr>
                    <th className="p-3 w-16 text-center">
                      <div>S. No</div>
                      <input
                        type="text"
                        placeholder="#"
                        value={salesPartFilters.s_no}
                        onChange={(e) => setSalesPartFilters({ ...salesPartFilters, s_no: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-1 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal text-center focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[140px]">
                      <div>Part No.</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={salesPartFilters.part_no}
                        onChange={(e) => setSalesPartFilters({ ...salesPartFilters, part_no: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal uppercase focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[140px]">
                      <div>Item ID</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={salesPartFilters.item_id}
                        onChange={(e) => setSalesPartFilters({ ...salesPartFilters, item_id: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal uppercase focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[240px]">
                      <div>Part Description</div>
                      <input
                        type="text"
                        placeholder="Search..."
                        value={salesPartFilters.part_description}
                        onChange={(e) => setSalesPartFilters({ ...salesPartFilters, part_description: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-2 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    <th className="p-3 min-w-[80px] text-center">
                      <div>UOM</div>
                      <input
                        type="text"
                        placeholder="UOM"
                        value={salesPartFilters.uom}
                        onChange={(e) => setSalesPartFilters({ ...salesPartFilters, uom: e.target.value })}
                        className="mt-1.5 w-full text-[11px] px-1 py-1 bg-white border border-erp-dark-vanilla/30 rounded font-normal text-center uppercase focus:outline-none focus:border-erp-orange"
                      />
                    </th>

                    {/* 6. Actions Header */}
                    <th className="p-3 w-24 text-center">
                      <div>Actions</div>
                      <div className="mt-1.5 text-[10px] text-erp-chocolate/50 font-normal">Edit / Del</div>
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-gray-100 font-mono">
                  {loading ? (
                    <TableSkeletonRows rows={7} columns={6} />
                  ) : filteredSalesParts.length > 0 ? (
                    filteredSalesParts.map((row) => (
                      <tr
                        key={row.id}
                        className={`transition-colors ${
                          editingSalesPartId === row.id
                            ? 'bg-erp-orange/10 font-semibold'
                            : 'hover:bg-erp-vanilla/25'
                        }`}
                      >
                        <td className="p-3 text-center text-erp-chocolate/60 font-bold">
                          {row.s_no}
                        </td>
                        <td className="p-3 font-bold text-erp-chocolate whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <span>{row.part_no}</span>
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                              {row.is_active !== false ? 'Active' : 'Inactive'}
                            </span>
                          </div>
                        </td>
                        <td className="p-3 font-semibold text-erp-chocolate/90 whitespace-nowrap">
                          {row.item_id}
                        </td>
                        <td className="p-3 font-sans font-medium text-erp-chocolate/90">
                          {row.part_description}
                        </td>
                        <td className="p-3 text-center">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-erp-vanilla text-erp-chocolate border border-erp-dark-vanilla/40">
                            {row.uom}
                          </span>
                        </td>
                        <td className="p-3 text-center whitespace-nowrap">
                          <div className="flex items-center justify-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => startEditSalesPart(row)}
                              disabled={!canEdit}
                              title="Edit sales part"
                              className="p-1 rounded text-erp-chocolate/70 hover:text-erp-orange hover:bg-erp-orange/10 transition-colors disabled:opacity-40 text-xs"
                            >
                              ✏️
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeactivate('sales_parts', row.id, row.part_no)}
                              disabled={!canDelete || actionLoadingId === row.id}
                              title="Delete sales part"
                              className="p-1 rounded text-erp-chocolate/70 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-40 text-xs"
                            >
                              {actionLoadingId === row.id ? '…' : '🗑️'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-erp-chocolate/60 italic font-sans">
                        No sales parts match your search filters or the table is empty.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
      {/* ========================================================================= */}
      {/* BULK UPLOAD MODAL OVERLAY                                                 */}
      {/* ========================================================================= */}
      {isUploadModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto animate-in fade-in duration-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="bulk-upload-modal-title"
        >
          {/* Backdrop dismiss */}
          <div
            className="fixed inset-0 -z-10"
            onClick={() => !uploading && setIsUploadModalOpen(false)}
          />

          <div className="bg-white border border-erp-dark-vanilla/30 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative">
            <div className="flex items-start justify-between pb-3 border-b border-erp-dark-vanilla/20 mb-4">
              <div>
                <h2 id="bulk-upload-modal-title" className="text-lg font-bold text-erp-chocolate">
                  Bulk Excel Intake
                </h2>
                <p className="text-xs text-erp-chocolate/70 mt-0.5">
                  Target: <span className="font-semibold text-erp-orange">{activeTabLabel}</span>
                </p>
              </div>
              <button
                type="button"
                disabled={uploading || isConfirming}
                onClick={() => {
                  handleResetUpload();
                  setIsUploadModalOpen(false);
                }}
                className="text-erp-chocolate/60 hover:text-erp-chocolate p-1.5 rounded hover:bg-erp-vanilla/40 transition-colors disabled:opacity-30 text-sm font-bold"
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-erp-chocolate/75 mb-3 leading-relaxed">
              Upload an unformatted Excel file (.xlsx up to 15MB, max 5,000 rows). Header Hunter scans top rows, drops banners, and maps columns into <span className="font-semibold text-erp-chocolate">{activeTabLabel}</span>.
            </p>

            <div className="mb-4 flex items-center justify-between text-[11px] bg-erp-vanilla/25 px-2.5 py-1.5 rounded-lg border border-erp-dark-vanilla/20 text-erp-chocolate/70">
              <span>File limits: <strong className="text-erp-chocolate">Max 15 MB</strong></span>
              <span>Capacity: <strong className="text-erp-chocolate">Up to 5,000 rows</strong></span>
            </div>

            {uploadError && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-900 rounded-md text-xs space-y-2">
                <div>{uploadError}</div>
                {selectedFile && !uploading && !isConfirming && (
                  <div className="flex items-center gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => handleFileUpload(selectedFile)}
                      className="px-2.5 py-1 bg-red-800 hover:bg-red-900 text-white font-semibold rounded text-[11px] transition-colors"
                    >
                      ↻ Retry with {selectedFile.name}
                    </button>
                    <button
                      type="button"
                      onClick={handleResetUpload}
                      className="px-2 py-1 border border-red-300 text-red-800 hover:bg-red-100 rounded text-[11px]"
                    >
                      Clear
                    </button>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'assemble' && assemblePreview ? (
              <div className="space-y-4">
                {/* Header match badge & metadata */}
                <div className="bg-erp-vanilla/20 border border-erp-dark-vanilla/30 rounded-xl p-3.5 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-erp-chocolate flex items-center gap-1.5">
                      <span>📄</span>
                      <span className="truncate max-w-[220px]">{assemblePreview.source_filename}</span>
                    </span>
                    <span className="px-2 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-full text-[11px] font-medium">
                      Header Row {assemblePreview.detected_header_row}
                    </span>
                  </div>
                  <p className="text-[11px] text-erp-chocolate/70">
                    Matched <span className="font-semibold text-erp-chocolate">{assemblePreview.columns_matched.length} columns</span> using Header Hunter v2.0.
                  </p>

                  {/* Summary Stat Badges */}
                  <div className="grid grid-cols-4 gap-2 pt-1 text-center">
                    <div className="p-2 bg-white rounded-lg border border-erp-dark-vanilla/20 shadow-xs">
                      <div className="text-[10px] text-erp-chocolate/60 font-medium">Total Rows</div>
                      <div className="text-sm font-bold text-erp-chocolate font-mono">{assemblePreview.total_rows}</div>
                    </div>
                    <div className="p-2 bg-emerald-50 rounded-lg border border-emerald-200 shadow-xs">
                      <div className="text-[10px] text-emerald-700 font-medium">Additions</div>
                      <div className="text-sm font-bold text-emerald-800 font-mono">+{assemblePreview.rows_to_add}</div>
                    </div>
                    <div className="p-2 bg-blue-50 rounded-lg border border-blue-200 shadow-xs">
                      <div className="text-[10px] text-blue-700 font-medium">Updates</div>
                      <div className="text-sm font-bold text-blue-800 font-mono">↺ {assemblePreview.rows_to_update}</div>
                    </div>
                    <div className={`p-2 rounded-lg border shadow-xs ${assemblePreview.error_count > 0 ? 'bg-red-50 border-red-200 text-red-800' : 'bg-amber-50 border-amber-200 text-amber-800'}`}>
                      <div className="text-[10px] font-medium">{assemblePreview.error_count > 0 ? 'Errors' : 'Notices'}</div>
                      <div className="text-sm font-bold font-mono">{assemblePreview.error_count + assemblePreview.warning_count}</div>
                    </div>
                  </div>
                </div>

                {/* Issues display if any */}
                {assemblePreview.errors && assemblePreview.errors.length > 0 && (
                  <div className="border border-erp-dark-vanilla/25 rounded-xl p-3 bg-white space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-erp-chocolate">
                        Row Notices ({assemblePreview.errors.length}{assemblePreview.warning_count + assemblePreview.error_count > assemblePreview.errors.length ? ` of ${assemblePreview.warning_count + assemblePreview.error_count}` : ''})
                      </span>
                      <button
                        type="button"
                        onClick={handleDownloadErrorReport}
                        className="text-[11px] text-erp-orange hover:text-erp-chocolate font-semibold flex items-center gap-1 hover:underline"
                      >
                        <span>📥</span> Download Error Report (.xlsx)
                      </button>
                    </div>
                    <div className="max-h-32 overflow-y-auto space-y-1 pr-1 text-[11px]">
                      {assemblePreview.errors.slice(0, 5).map((err, i) => (
                        <div key={i} className="p-1.5 rounded bg-amber-50/60 border border-amber-200/50 text-erp-chocolate flex items-start gap-1.5">
                          <span className="font-mono font-bold text-amber-800 min-w-[50px]">Row {err.row}:</span>
                          <span className="flex-1">{err.message}</span>
                        </div>
                      ))}
                      {assemblePreview.errors.length > 5 && (
                        <div className="text-center text-[10px] text-erp-chocolate/60 pt-0.5 italic">
                          + {assemblePreview.errors.length - 5} additional issues recorded. Click Download Error Report for full details.
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Confirmation Progress State */}
                {isConfirming && (
                  <div className="p-3 bg-white rounded-lg border border-erp-dark-vanilla/25 space-y-2">
                    <div className="flex justify-between items-center text-xs font-semibold text-erp-chocolate">
                      <span className="flex items-center gap-1.5">
                        <svg className="animate-spin h-3.5 w-3.5 text-erp-orange" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                        </svg>
                        <span>{assembleJob?.stage || 'Committing records to database...'}</span>
                      </span>
                      <span className="font-mono text-erp-orange font-bold">
                        {assembleJob?.progress_percent || 0}%
                      </span>
                    </div>
                    <div className="w-full bg-erp-vanilla/60 rounded-full h-2.5 overflow-hidden border border-erp-dark-vanilla/30">
                      <div
                        className="bg-erp-orange h-2.5 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${assembleJob?.progress_percent || 20}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Modal Buttons */}
                <div className="flex items-center justify-between pt-2 border-t border-erp-dark-vanilla/20">
                  <button
                    type="button"
                    disabled={isConfirming}
                    onClick={handleResetUpload}
                    className="text-xs px-3 py-1.5 border border-erp-dark-vanilla/40 rounded-lg hover:bg-erp-vanilla/40 text-erp-chocolate disabled:opacity-40"
                  >
                    Choose Another File
                  </button>

                  <button
                    type="button"
                    disabled={isConfirming || !assemblePreview.can_confirm}
                    onClick={handleConfirmAssemble}
                    className="text-xs px-4 py-2 bg-erp-orange hover:bg-erp-orange/90 text-white font-bold rounded-lg shadow-sm transition-all disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {isConfirming ? (
                      <>Saving Records...</>
                    ) : (
                      <>Confirm & Import {assemblePreview.total_rows} Records ✓</>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div
                  onDragEnter={handleDrag}
                  onDragLeave={handleDrag}
                  onDragOver={handleDrag}
                  onDrop={handleDrop}
                  onClick={() => !uploading && fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
                    uploading
                      ? 'pointer-events-none opacity-60 border-erp-orange bg-erp-orange/5'
                      : dragActive
                      ? 'border-erp-orange bg-erp-orange/10'
                      : 'border-erp-dark-vanilla/40 hover:border-erp-orange bg-erp-vanilla/15 hover:bg-erp-vanilla/30'
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".xlsx"
                    className="hidden"
                    disabled={uploading}
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        handleFileUpload(e.target.files[0]);
                      }
                    }}
                  />
                  <div className="space-y-1.5">
                    <div className="text-3xl">📥</div>
                    <p className="text-xs font-bold text-erp-chocolate">
                      {uploading ? 'Processing File…' : `Drag & drop ${activeTabLabel} Excel here`}
                    </p>
                    <p className="text-[11px] text-erp-chocolate/60">
                      or click to browse from device (.xlsx up to 15MB)
                    </p>
                  </div>
                </div>

                {/* Progress Bar & Processing States */}
                {uploading && (
                  <div className="mt-4 p-3 bg-white rounded-lg border border-erp-dark-vanilla/25 space-y-2">
                    <div className="flex justify-between items-center text-xs font-semibold text-erp-chocolate">
                      <span className="flex items-center gap-1.5">
                        {uploadPhase !== 'parsing' && uploadProgress < 100 ? (
                          `Uploading: ${uploadProgress}%`
                        ) : (
                          <>
                            <svg className="animate-spin h-3.5 w-3.5 text-erp-orange" viewBox="0 0 24 24" fill="none">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                            </svg>
                            <span>Scanning headers & validating rows...</span>
                          </>
                        )}
                      </span>
                      <span className="font-mono text-erp-orange font-bold">{uploadProgress}%</span>
                    </div>

                    <div className="w-full bg-erp-vanilla/60 rounded-full h-2.5 overflow-hidden border border-erp-dark-vanilla/30">
                      <div
                        className="bg-erp-orange h-2.5 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>

                    {(uploadPhase === 'parsing' || uploadProgress === 100) && (
                      <p className="text-[11px] text-erp-chocolate/60 italic pt-0.5">
                        Header Hunter is scanning top rows and validating column vocabulary...
                      </p>
                    )}
                  </div>
                )}

                <div className="mt-4 pt-3 border-t border-erp-dark-vanilla/20 flex items-center justify-between text-[11px] text-erp-chocolate/60">
                  <span className="font-mono text-erp-topaz font-semibold">Header Hunter v2.0</span>
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() => {
                      handleResetUpload();
                      setIsUploadModalOpen(false);
                    }}
                    className="text-xs px-3 py-1.5 border border-erp-dark-vanilla/40 rounded-lg hover:bg-erp-vanilla/40 transition-colors disabled:opacity-40 text-erp-chocolate"
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Floating Success Toast */}
      {toast && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-3 px-4 py-3 bg-emerald-900 text-white text-xs font-medium rounded-lg shadow-xl border border-emerald-700 animate-in slide-in-from-bottom duration-300">
          <span className="text-base font-bold text-emerald-300">✓</span>
          <span>{toast.message}</span>
          <button
            onClick={() => setToast(null)}
            className="ml-3 text-white/70 hover:text-white font-bold"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
}
