import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient, ApiError } from '../../api/client';
import type { DashboardSummaryResponse } from './types';
import type { InventoryAlertResponse } from '../alerts/types';

export default function ExecutiveDashboard() {
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [activeAlerts, setActiveAlerts] = useState<InventoryAlertResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboardData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sumData, alertsData] = await Promise.all([
        apiClient.get<DashboardSummaryResponse>('/api/v1/reports/dashboard-summary'),
        apiClient.get<InventoryAlertResponse[]>('/api/v1/alerts?status=ACTIVE'),
      ]);
      setSummary(sumData);
      setActiveAlerts(alertsData.slice(0, 5)); // Show top 5 active alerts
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load executive dashboard data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Executive Dashboard</h1>
          <p className="text-sm text-gray-500">
            Real-time procurement pipeline, stock alert visibility, and workflow approval queues.
          </p>
        </div>
        <button
          onClick={fetchDashboardData}
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
        >
          {loading ? 'Refreshing…' : '↻ Refresh Dashboard'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 p-4 rounded text-sm">
          {error}
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {/* Critical Alerts */}
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 shadow-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-red-600">Critical Breaches</p>
            <p className="text-3xl font-bold text-red-900 mt-2">
              {summary ? summary.active_critical_alerts : '—'}
            </p>
          </div>
          <Link to="/alerts" className="text-xs font-medium text-red-700 hover:underline mt-3 block">
            View Alerts →
          </Link>
        </div>

        {/* Low Stock Warnings */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 shadow-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-yellow-700">Stock Warnings</p>
            <p className="text-3xl font-bold text-yellow-900 mt-2">
              {summary ? summary.active_warning_alerts : '—'}
            </p>
          </div>
          <Link to="/alerts" className="text-xs font-medium text-yellow-800 hover:underline mt-3 block">
            View Warnings →
          </Link>
        </div>

        {/* Pending Purchase Approvals */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 shadow-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-blue-600">Pending PO Approvals</p>
            <p className="text-3xl font-bold text-blue-900 mt-2">
              {summary ? summary.pending_purchase_approvals : '—'}
            </p>
          </div>
          <Link to="/purchasing/approvals" className="text-xs font-medium text-blue-700 hover:underline mt-3 block">
            Open Queue →
          </Link>
        </div>

        {/* Pending Plant Adjustments */}
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4 shadow-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">Plant Adjustments</p>
            <p className="text-3xl font-bold text-indigo-900 mt-2">
              {summary ? summary.pending_plant_adjustments : '—'}
            </p>
          </div>
          <Link to="/plant-workflow" className="text-xs font-medium text-indigo-700 hover:underline mt-3 block">
            Review Workflow →
          </Link>
        </div>

        {/* Issued Pending POs */}
        <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 shadow-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-purple-600">Active Issued POs</p>
            <p className="text-3xl font-bold text-purple-900 mt-2">
              {summary ? summary.issued_pending_pos : '—'}
            </p>
          </div>
          <Link to="/reports/inventory-purchase" className="text-xs font-medium text-purple-700 hover:underline mt-3 block">
            Track Deliveries →
          </Link>
        </div>

        {/* Active Managed Consumables */}
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 shadow-sm flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-emerald-600">Managed Consumables</p>
            <p className="text-3xl font-bold text-emerald-900 mt-2">
              {summary ? summary.total_active_consumables : '—'}
            </p>
          </div>
          <Link to="/reports/inventory-purchase" className="text-xs font-medium text-emerald-700 hover:underline mt-3 block">
            View Masters →
          </Link>
        </div>
      </div>

      {/* Procurement Lifecycle Pipeline Flow */}
      <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b pb-3">
          <div>
            <h2 className="text-lg font-bold text-gray-800">Demand-to-Receipt Procurement Pipeline</h2>
            <p className="text-xs text-gray-500">
              Aggregated system quantities from calculation engine to physical GRN receipt.
            </p>
          </div>
          {summary && (
            <span className="text-xs font-mono text-gray-400">
              As of: {new Date(summary.as_of).toLocaleTimeString()}
            </span>
          )}
        </div>

        {summary ? (
          <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-7 gap-3 text-center">
            <div className="bg-gray-50 p-3 rounded border">
              <p className="text-[11px] font-semibold text-gray-500 uppercase">1. Calculated Qty</p>
              <p className="text-base font-bold font-mono text-gray-800 mt-1">
                {summary.pipeline_summary.total_calculated_quantity}
              </p>
            </div>

            <div className="bg-gray-50 p-3 rounded border">
              <p className="text-[11px] font-semibold text-gray-500 uppercase">2. Plant Additions</p>
              <p className="text-base font-bold font-mono text-blue-700 mt-1">
                +{summary.pipeline_summary.total_approved_additions}
              </p>
            </div>

            <div className="bg-blue-50 p-3 rounded border border-blue-200">
              <p className="text-[11px] font-semibold text-blue-700 uppercase">3. Final Requirement</p>
              <p className="text-base font-bold font-mono text-blue-900 mt-1">
                {summary.pipeline_summary.total_final_requirement}
              </p>
            </div>

            <div className="bg-gray-50 p-3 rounded border">
              <p className="text-[11px] font-semibold text-gray-500 uppercase">4. Recommended Qty</p>
              <p className="text-base font-bold font-mono text-gray-800 mt-1">
                {summary.pipeline_summary.total_recommended_quantity}
              </p>
            </div>

            <div className="bg-indigo-50 p-3 rounded border border-indigo-200">
              <p className="text-[11px] font-semibold text-indigo-700 uppercase">5. Approved Purchase</p>
              <p className="text-base font-bold font-mono text-indigo-900 mt-1">
                {summary.pipeline_summary.total_approved_purchase_quantity}
              </p>
            </div>

            <div className="bg-purple-50 p-3 rounded border border-purple-200">
              <p className="text-[11px] font-semibold text-purple-700 uppercase">6. Ordered (PO)</p>
              <p className="text-base font-bold font-mono text-purple-900 mt-1">
                {summary.pipeline_summary.total_ordered_quantity}
              </p>
            </div>

            <div className="bg-emerald-50 p-3 rounded border border-emerald-200">
              <p className="text-[11px] font-semibold text-emerald-700 uppercase">7. Received (GRN)</p>
              <p className="text-base font-bold font-mono text-emerald-900 mt-1">
                {summary.pipeline_summary.total_accepted_grn_quantity}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400 py-4 text-center">Loading pipeline summary…</p>
        )}
      </div>

      {/* Top Active Alerts Feed & Quick Action Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Alerts Panel */}
        <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b pb-2">
            <h3 className="text-sm font-bold text-gray-800">Top Active Alerts</h3>
            <Link to="/alerts" className="text-xs font-semibold text-blue-600 hover:underline">
              View All Alerts →
            </Link>
          </div>

          {activeAlerts.length === 0 ? (
            <p className="text-xs text-gray-500 py-4 text-center">No active inventory alerts.</p>
          ) : (
            <div className="space-y-2">
              {activeAlerts.map((alert) => (
                <div key={alert.id} className="flex items-center justify-between p-2.5 rounded bg-gray-50 border text-xs">
                  <div>
                    <span className="font-mono text-[11px] text-gray-500 mr-2">[{alert.alert_type}]</span>
                    <span className="font-medium text-gray-900">{alert.consumable_code || alert.consumable_name}</span>
                    <p className="text-gray-600 text-[11px] mt-0.5 max-w-sm truncate">{alert.message}</p>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    alert.severity === 'CRITICAL' ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'
                  }`}>
                    {alert.severity}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quick Reports & Analytical Tools */}
        <div className="bg-white border border-gray-200 rounded-lg p-5 shadow-sm space-y-4">
          <div className="border-b pb-2">
            <h3 className="text-sm font-bold text-gray-800">Analytical Reports & Domain Workflows</h3>
            <p className="text-xs text-gray-500">Quick access to authoritative report screens.</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Link
              to="/reports/planned-vs-actual"
              className="p-3 border rounded-lg hover:border-blue-500 hover:bg-blue-50/50 transition-colors block"
            >
              <p className="text-xs font-bold text-gray-800">Planned vs Actual Report</p>
              <p className="text-[11px] text-gray-500 mt-1">Compare planned demand against actual stock usage.</p>
            </Link>

            <Link
              to="/reports/inventory-purchase"
              className="p-3 border rounded-lg hover:border-blue-500 hover:bg-blue-50/50 transition-colors block"
            >
              <p className="text-xs font-bold text-gray-800">Inventory & Purchase Reports</p>
              <p className="text-[11px] text-gray-500 mt-1">Material stock, MSL, supplier plans, and GRNs.</p>
            </Link>

            <Link
              to="/purchasing/approvals"
              className="p-3 border rounded-lg hover:border-blue-500 hover:bg-blue-50/50 transition-colors block"
            >
              <p className="text-xs font-bold text-gray-800">Purchase Approvals Queue</p>
              <p className="text-[11px] text-gray-500 mt-1">Review and approve purchase recommendations.</p>
            </Link>

            <Link
              to="/alerts"
              className="p-3 border rounded-lg hover:border-blue-500 hover:bg-blue-50/50 transition-colors block"
            >
              <p className="text-xs font-bold text-gray-800">Inventory Alert Center</p>
              <p className="text-[11px] text-gray-500 mt-1">Evaluate stock floors, PO delays, and MSL risks.</p>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
