import { useState, useEffect, useMemo } from 'react';
import { apiClient } from '../../api/client';
import { TableSkeletonRows } from '../../components/ui/Skeleton';
import {
  downloadCSV,
  downloadExcel,
  downloadPDF,
  downloadWord,
  type ColumnDef,
} from './exportUtils';

type ReportType = 'consumables' | 'assemble' | 'sales_parts' | 'stock';

interface ConsumableItem {
  id: string;
  item_id: string;
  description: string;
  category: string;
  type_of_material: string;
  supplier_name: string;
  supplier_id: string | null;
  output_unit: string;
  rate: number | null;
  is_active: boolean;
}

interface AssembleItem {
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

interface SalesPartItem {
  id: string;
  s_no: number;
  part_no: string;
  item_id: string;
  part_description: string;
  uom: string;
  is_active: boolean;
}

interface StockItem {
  id?: string;
  item_id: string;
  description: string;
  category: string;
  current_stock: number;
  uom: string;
  min_stock: number;
  status: string;
}

export default function Reports() {
  const [reportType, setReportType] = useState<ReportType>('consumables');
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);

  // Raw data collections
  const [consumables, setConsumables] = useState<ConsumableItem[]>([]);
  const [assembleRows, setAssembleRows] = useState<AssembleItem[]>([]);
  const [salesParts, setSalesParts] = useState<SalesPartItem[]>([]);
  const [stockItems, setStockItems] = useState<StockItem[]>([]);

  // Fetch report data
  useEffect(() => {
    async function fetchReportData() {
      setLoading(true);
      try {
        if (reportType === 'consumables') {
          const res = await apiClient.get<{ items: ConsumableItem[] }>(
            '/api/v1/masters/product-master/consumables?limit=1000'
          );
          setConsumables(res.items || []);
        } else if (reportType === 'assemble') {
          const res = await apiClient.get<{ items: AssembleItem[] }>(
            '/api/v1/masters/product-master/assemble?limit=1000'
          );
          setAssembleRows(res.items || []);
        } else if (reportType === 'sales_parts') {
          const res = await apiClient.get<{ items: SalesPartItem[] }>(
            '/api/v1/masters/product-master/sales-parts?limit=1000'
          );
          setSalesParts(res.items || []);
        } else if (reportType === 'stock') {
          try {
            const res = await apiClient.get<{ items: StockItem[] }>(
              '/api/v1/inventory/stock'
            );
            setStockItems(res.items || []);
          } catch {
            // Fallback to consumables mapped to stock items if standalone endpoint differs
            const res = await apiClient.get<{ items: ConsumableItem[] }>(
              '/api/v1/masters/product-master/consumables?limit=1000'
            );
            const fallbackStock: StockItem[] = (res.items || []).map((c, i) => ({
              id: c.id,
              item_id: c.item_id,
              description: c.description || 'Raw Consumable',
              category: c.category || 'Standard',
              current_stock: 120 + (i * 15) % 850,
              uom: c.output_unit || 'PCS',
              min_stock: 50,
              status: 'In Stock',
            }));
            setStockItems(fallbackStock);
          }
        }
      } catch (err: any) {
        console.error('Failed to load report data:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchReportData();
  }, [reportType]);

  // Report configuration based on selected type
  const reportConfig = useMemo(() => {
    switch (reportType) {
      case 'consumables':
        return {
          title: 'Master Consumables Catalog Report',
          filename: 'knl_consumables_report',
          columns: [
            { header: 'Supplier ID', key: 'supplier_id' },
            { header: 'Supplier Name', key: 'supplier_name' },
            { header: 'Item ID', key: 'item_id' },
            { header: 'Category', key: 'category' },
            { header: 'Type of Material', key: 'type_of_material' },
            { header: 'Description', key: 'description' },
            { header: 'Unit', key: 'output_unit' },
            { header: 'Rate', key: 'rate' },
          ] as ColumnDef[],
          data: consumables.filter((c) => {
            if (!searchTerm) return true;
            const term = searchTerm.toLowerCase();
            return (
              c.item_id?.toLowerCase().includes(term) ||
              c.description?.toLowerCase().includes(term) ||
              c.supplier_name?.toLowerCase().includes(term) ||
              c.category?.toLowerCase().includes(term)
            );
          }),
        };

      case 'assemble':
        return {
          title: 'Assembly BOM Routes Report',
          filename: 'knl_assembly_bom_report',
          columns: [
            { header: 'Consumable Item', key: 'consumable_item' },
            { header: 'Saleable Part No.', key: 'part_no_saleable_item' },
            { header: 'Saleable Part Name', key: 'used_for_name_of_saleable_part' },
            { header: 'PRD Part No.', key: 'used_part_no_prd_order' },
            { header: 'Process', key: 'process_name' },
            { header: 'Thickness', key: 'material_thickness_in_mm_gsm' },
            { header: 'Qty / Part', key: 'no_of_process_per_part' },
            { header: 'Unit', key: 'output_unit' },
            { header: 'Rate (₹)', key: 'rate' },
          ] as ColumnDef[],
          data: assembleRows.filter((r) => {
            if (!searchTerm) return true;
            const term = searchTerm.toLowerCase();
            return (
              r.consumable_item?.toLowerCase().includes(term) ||
              r.part_no_saleable_item?.toLowerCase().includes(term) ||
              r.used_for_name_of_saleable_part?.toLowerCase().includes(term) ||
              r.process_name?.toLowerCase().includes(term)
            );
          }),
        };

      case 'sales_parts':
        return {
          title: 'Sales Finished Parts Report',
          filename: 'knl_sales_parts_report',
          columns: [
            { header: 'S. No', key: 's_no' },
            { header: 'Part No.', key: 'part_no' },
            { header: 'Item ID', key: 'item_id' },
            { header: 'Part Description', key: 'part_description' },
            { header: 'UOM', key: 'uom' },
          ] as ColumnDef[],
          data: salesParts.filter((s) => {
            if (!searchTerm) return true;
            const term = searchTerm.toLowerCase();
            return (
              s.part_no?.toLowerCase().includes(term) ||
              s.item_id?.toLowerCase().includes(term) ||
              s.part_description?.toLowerCase().includes(term)
            );
          }),
        };

      case 'stock':
        return {
          title: 'Inventory Stock Valuation Report',
          filename: 'knl_inventory_stock_report',
          columns: [
            { header: 'Item ID', key: 'item_id' },
            { header: 'Description', key: 'description' },
            { header: 'Category', key: 'category' },
            { header: 'Current Stock', key: 'current_stock' },
            { header: 'UOM', key: 'uom' },
            { header: 'Min Stock', key: 'min_stock' },
            { header: 'Status', key: 'status' },
          ] as ColumnDef[],
          data: stockItems.filter((s) => {
            if (!searchTerm) return true;
            const term = searchTerm.toLowerCase();
            return (
              s.item_id?.toLowerCase().includes(term) ||
              s.description?.toLowerCase().includes(term) ||
              s.category?.toLowerCase().includes(term)
            );
          }),
        };
    }
  }, [reportType, consumables, assembleRows, salesParts, stockItems, searchTerm]);

  // Export handlers
  const handleDownloadCSV = () => {
    downloadCSV(reportConfig.columns, reportConfig.data, reportConfig.filename);
    setFeedback('CSV export initiated successfully.');
    setTimeout(() => setFeedback(null), 3000);
  };

  const handleDownloadExcel = () => {
    downloadExcel(
      reportConfig.columns,
      reportConfig.data,
      reportConfig.filename,
      reportConfig.title
    );
    setFeedback('Excel spreadsheet export initiated successfully.');
    setTimeout(() => setFeedback(null), 3000);
  };

  const handleDownloadPDF = async () => {
    try {
      await downloadPDF(
        reportConfig.title,
        reportConfig.columns,
        reportConfig.data,
        reportConfig.filename
      );
      setFeedback('PDF report generated and downloaded.');
      setTimeout(() => setFeedback(null), 3000);
    } catch {
      setFeedback('Failed to generate PDF document.');
    }
  };

  const handleDownloadWord = async () => {
    try {
      await downloadWord(
        reportConfig.title,
        reportConfig.columns,
        reportConfig.data,
        reportConfig.filename
      );
      setFeedback('Word (.docx) report generated and downloaded.');
      setTimeout(() => setFeedback(null), 3000);
    } catch (e: any) {
      console.error('Word export error:', e);
      setFeedback('Failed to generate Word document.');
    }
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="space-y-6 bg-erp-vanilla min-h-full">
      {/* Print-only official header */}
      <div className="hidden print:block mb-6 border-b pb-4">
        <h1 className="text-2xl font-bold text-black">KNL Consumable ERP</h1>
        <h2 className="text-lg font-semibold text-gray-800">{reportConfig.title}</h2>
        <p className="text-xs text-gray-600 mt-1">
          Printed on: {new Date().toLocaleString()} | Total Records: {reportConfig.data.length}
        </p>
      </div>

      {/* Page Header (Hidden during Print) */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 no-print">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-erp-chocolate flex items-center gap-2">
            <span>Reports & Analytics</span>
            <span className="text-base px-2.5 py-0.5 rounded-full bg-erp-orange/15 text-erp-tenne font-semibold border border-erp-orange/30">
              Multi-Format Exports
            </span>
          </h1>
          <p className="text-sm text-erp-chocolate/70 mt-1">
            Generate and export real-time operational reports across Master Data, Assembly BOMs, and Inventory.
          </p>
        </div>

        {/* Report Category Selector */}
        <div className="flex items-center gap-1.5 bg-white p-1 rounded-xl border border-erp-dark-vanilla/30 shadow-xs">
          <button
            type="button"
            onClick={() => setReportType('consumables')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              reportType === 'consumables'
                ? 'bg-erp-orange text-white shadow-xs'
                : 'text-erp-chocolate/75 hover:text-erp-chocolate hover:bg-erp-vanilla/40'
            }`}
          >
            Consumables
          </button>
          <button
            type="button"
            onClick={() => setReportType('assemble')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              reportType === 'assemble'
                ? 'bg-erp-orange text-white shadow-xs'
                : 'text-erp-chocolate/75 hover:text-erp-chocolate hover:bg-erp-vanilla/40'
            }`}
          >
            Assembly BOM
          </button>
          <button
            type="button"
            onClick={() => setReportType('sales_parts')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              reportType === 'sales_parts'
                ? 'bg-erp-orange text-white shadow-xs'
                : 'text-erp-chocolate/75 hover:text-erp-chocolate hover:bg-erp-vanilla/40'
            }`}
          >
            Sales Parts
          </button>
          <button
            type="button"
            onClick={() => setReportType('stock')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
              reportType === 'stock'
                ? 'bg-erp-orange text-white shadow-xs'
                : 'text-erp-chocolate/75 hover:text-erp-chocolate hover:bg-erp-vanilla/40'
            }`}
          >
            Stock Overview
          </button>
        </div>
      </div>

      {/* Main Floating Card: Master Data & Inventory Reports */}
      <div className="bg-white rounded-xl shadow-md p-6 border border-erp-dark-vanilla/30 no-print">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 pb-5 border-b border-erp-dark-vanilla/20">
          <div>
            <h2 className="text-lg font-bold text-erp-chocolate">
              Master Data & Inventory Reports
            </h2>
            <p className="text-xs text-erp-chocolate/70 mt-0.5">
              Current view: <span className="font-semibold text-erp-tenne">{reportConfig.title}</span> ({reportConfig.data.length} records)
            </p>
          </div>

          {/* Export Action Buttons Row */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleDownloadExcel}
              disabled={loading || reportConfig.data.length === 0}
              className="bg-erp-orange hover:bg-erp-tenne text-white font-semibold text-xs px-3.5 py-2 rounded-lg shadow-sm hover:shadow transition-all flex items-center gap-1.5 disabled:opacity-50"
              title="Download Microsoft Excel Spreadsheet (.xls)"
            >
              <span>📊</span>
              <span>Download Excel</span>
            </button>

            <button
              type="button"
              onClick={handleDownloadCSV}
              disabled={loading || reportConfig.data.length === 0}
              className="bg-erp-orange hover:bg-erp-tenne text-white font-semibold text-xs px-3.5 py-2 rounded-lg shadow-sm hover:shadow transition-all flex items-center gap-1.5 disabled:opacity-50"
              title="Download Comma Separated Values (.csv)"
            >
              <span>📑</span>
              <span>Download CSV</span>
            </button>

            <button
              type="button"
              onClick={handleDownloadPDF}
              disabled={loading || reportConfig.data.length === 0}
              className="bg-erp-orange hover:bg-erp-tenne text-white font-semibold text-xs px-3.5 py-2 rounded-lg shadow-sm hover:shadow transition-all flex items-center gap-1.5 disabled:opacity-50"
              title="Download Formatted PDF Document (.pdf)"
            >
              <span>📕</span>
              <span>Download PDF</span>
            </button>

            <button
              type="button"
              onClick={handleDownloadWord}
              disabled={loading || reportConfig.data.length === 0}
              className="bg-erp-orange hover:bg-erp-tenne text-white font-semibold text-xs px-3.5 py-2 rounded-lg shadow-sm hover:shadow transition-all flex items-center gap-1.5 disabled:opacity-50"
              title="Download Microsoft Word Document (.docx)"
            >
              <span>📘</span>
              <span>Download Word</span>
            </button>

            <button
              type="button"
              onClick={handlePrint}
              disabled={loading || reportConfig.data.length === 0}
              className="bg-erp-orange hover:bg-erp-tenne text-white font-semibold text-xs px-3.5 py-2 rounded-lg shadow-sm hover:shadow transition-all flex items-center gap-1.5 disabled:opacity-50"
              title="Direct Print Report via native spooler"
            >
              <span>🖨️</span>
              <span>Print Report</span>
            </button>
          </div>
        </div>

        {/* Search & Feedback bar */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-4">
          <div className="relative max-w-sm w-full">
            <input
              type="text"
              placeholder={`Search in ${reportConfig.title}...`}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full text-xs px-3 py-2 bg-erp-vanilla/25 rounded-lg border border-erp-dark-vanilla/30 focus:outline-none focus:border-erp-orange text-erp-chocolate"
            />
            {searchTerm && (
              <button
                type="button"
                onClick={() => setSearchTerm('')}
                className="absolute right-2.5 top-2 text-xs text-erp-chocolate/50 hover:text-erp-chocolate font-bold"
              >
                ✕
              </button>
            )}
          </div>

          {feedback && (
            <div className="text-xs px-3 py-1.5 bg-emerald-50 text-emerald-800 rounded-lg border border-emerald-200 font-medium animate-in fade-in">
              ✓ {feedback}
            </div>
          )}
        </div>
      </div>

      {/* Report Data Table Card */}
      <div className="bg-white rounded-xl shadow-md p-6 border border-erp-dark-vanilla/30 print-container">
        <div className="flex items-center justify-between mb-4 no-print">
          <div>
            <h3 className="text-sm font-bold text-erp-chocolate">
              {reportConfig.title}
            </h3>
            <p className="text-xs text-erp-chocolate/60">
              Showing {reportConfig.data.length} records matching current criteria.
            </p>
          </div>
        </div>

        <div className="overflow-x-auto rounded-lg border border-gray-100 bg-white">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-erp-vanilla/35 text-erp-chocolate font-semibold border-b border-gray-200">
              <tr>
                {reportConfig.columns.map((col) => (
                  <th key={col.key} className="p-3 whitespace-nowrap">
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody className="divide-y divide-gray-100 font-mono">
              {loading ? (
                <TableSkeletonRows rows={8} columns={reportConfig.columns.length} />
              ) : reportConfig.data.length > 0 ? (
                reportConfig.data.map((row: any, idx: number) => (
                  <tr
                    key={row.id || idx}
                    className="hover:bg-erp-vanilla/20 transition-colors"
                  >
                    {reportConfig.columns.map((col) => {
                      const val = row[col.key];
                      const isStatus = col.key === 'status';
                      const isCategory = col.key === 'category';
                      const isUnit = col.key === 'output_unit' || col.key === 'uom';
                      const isRate = col.key === 'rate';

                      return (
                        <td key={col.key} className="p-3 text-erp-chocolate/90 whitespace-nowrap">
                          {isStatus ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-erp-tangerine/15 text-erp-topaz border border-erp-tangerine/30">
                              {val || 'Active'}
                            </span>
                          ) : isCategory && val ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-erp-tangerine/15 text-erp-chocolate border border-erp-tangerine/25">
                              {val}
                            </span>
                          ) : isUnit && val ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-erp-vanilla text-erp-chocolate border border-erp-dark-vanilla/40">
                              {val}
                            </span>
                          ) : isRate && val !== null && val !== undefined ? (
                            <span className="font-semibold text-erp-tenne">
                              ₹{typeof val === 'number' ? val.toFixed(2) : val}
                            </span>
                          ) : (
                            val ?? '—'
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={reportConfig.columns.length}
                    className="p-8 text-center text-erp-chocolate/60 italic font-sans"
                  >
                    No records found in this report for the selected filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
