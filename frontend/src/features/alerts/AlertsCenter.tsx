import { useCallback, useEffect, useState } from 'react';
import { apiClient, ApiError } from '../../api/client';
import type {
  AlertEvaluationSummaryResponse,
  AlertSeverity,
  AlertStatus,
  AlertType,
  InventoryAlertResponse,
} from './types';

// ── UI Badges ──────────────────────────────────────────────────────────────────

const SEVERITY_BADGES: Record<AlertSeverity, string> = {
  CRITICAL: 'bg-red-100 text-red-800 border-red-200',
  WARNING: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  INFO: 'bg-blue-100 text-blue-800 border-blue-200',
};

const STATUS_BADGES: Record<AlertStatus, string> = {
  ACTIVE: 'bg-red-50 text-red-700 font-semibold',
  ACKNOWLEDGED: 'bg-gray-100 text-gray-700 font-medium',
  RESOLVED: 'bg-green-50 text-green-700 font-medium',
};

function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  return (
    <span className={`inline-block px-2.5 py-0.5 rounded border text-xs font-bold ${SEVERITY_BADGES[severity]}`}>
      {severity}
    </span>
  );
}

function AlertTypeBadge({ type }: { type: AlertType }) {
  return (
    <span className="inline-block px-2 py-0.5 rounded bg-gray-100 text-gray-700 text-xs font-mono">
      {type}
    </span>
  );
}

function AlertBox({ message, type }: { message: string; type: 'error' | 'success' }) {
  const base = 'rounded p-3 text-sm mb-4';
  const colour = type === 'error'
    ? 'bg-red-50 border border-red-300 text-red-700'
    : 'bg-green-50 border border-green-300 text-green-700';
  return <div className={`${base} ${colour}`}>{message}</div>;
}

// ── Main AlertsCenter Component ────────────────────────────────────────────────

export default function AlertsCenter() {
  const [alerts, setAlerts] = useState<InventoryAlertResponse[]>([]);
  const [summary, setSummary] = useState<AlertEvaluationSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Filters
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | ''>('');
  const [typeFilter, setTypeFilter] = useState<AlertType | ''>('');
  const [statusFilter, setStatusFilter] = useState<AlertStatus | ''>('ACTIVE');

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (severityFilter) params.set('severity', severityFilter);
      if (typeFilter) params.set('alert_type', typeFilter);
      if (statusFilter) params.set('status', statusFilter);

      const data = await apiClient.get<InventoryAlertResponse[]>(`/api/v1/alerts?${params}`);
      setAlerts(data);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load inventory alerts.');
    } finally {
      setLoading(false);
    }
  }, [severityFilter, typeFilter, statusFilter]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const handleEvaluate = async () => {
    setEvaluating(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await apiClient.post<AlertEvaluationSummaryResponse>('/api/v1/alerts/evaluate', {});
      setSummary(res);
      setSuccess(`Evaluation completed: Evaluated ${res.total_evaluated} consumables. Active Critical: ${res.active_critical_count}, Active Warning: ${res.active_warning_count}.`);
      await fetchAlerts();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Alert evaluation failed.');
    } finally {
      setEvaluating(false);
    }
  };

  const handleAcknowledge = async (alertId: string) => {
    setError(null);
    setSuccess(null);
    const notes = window.prompt('Optional acknowledgement note:');
    try {
      await apiClient.patch(`/api/v1/alerts/${alertId}/acknowledge`, { notes: notes || null });
      setSuccess('Alert acknowledged successfully.');
      await fetchAlerts();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to acknowledge alert.');
    }
  };

  const criticalCount = alerts.filter((a) => a.severity === 'CRITICAL' && a.status === 'ACTIVE').length;
  const warningCount = alerts.filter((a) => a.severity === 'WARNING' && a.status === 'ACTIVE').length;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-800">Inventory Alert Center</h1>
          <p className="text-sm text-gray-500">
            Monitor stock breaches, MSL floor warnings, and delivery risk notifications.
          </p>
        </div>
        <button
          onClick={handleEvaluate}
          disabled={evaluating}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
        >
          {evaluating ? 'Evaluating…' : '↻ Evaluate Stock Alerts'}
        </button>
      </div>

      {error && <AlertBox message={error} type="error" />}
      {success && <AlertBox message={success} type="success" />}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-red-600">Critical MSL Breaches</p>
            <p className="text-2xl font-bold text-red-900 mt-1">{summary ? summary.active_critical_count : criticalCount}</p>
          </div>
          <span className="text-2xl">⚠️</span>
        </div>

        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-yellow-700">Low Stock Warnings</p>
            <p className="text-2xl font-bold text-yellow-900 mt-1">{summary ? summary.active_warning_count : warningCount}</p>
          </div>
          <span className="text-2xl">⚡</span>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Total Filtered Alerts</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{alerts.length}</p>
          </div>
          <span className="text-2xl">📋</span>
        </div>
      </div>

      {/* Filters Toolbar */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 flex flex-wrap items-center justify-between gap-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Status</label>
            <select
              className="border rounded px-3 py-1.5 text-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as AlertStatus | '')}
            >
              <option value="">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="ACKNOWLEDGED">Acknowledged</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Severity</label>
            <select
              className="border rounded px-3 py-1.5 text-sm"
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as AlertSeverity | '')}
            >
              <option value="">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="WARNING">Warning</option>
              <option value="INFO">Info</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Alert Type</label>
            <select
              className="border rounded px-3 py-1.5 text-sm"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as AlertType | '')}
            >
              <option value="">All Types</option>
              <option value="BELOW_MSL">Below MSL</option>
              <option value="LOW_STOCK">Low Stock</option>
              <option value="REORDER_REQUIRED">Reorder Required</option>
              <option value="PO_DELAY">PO Delay</option>
            </select>
          </div>
        </div>

        <button
          onClick={() => {
            setSeverityFilter('');
            setTypeFilter('');
            setStatusFilter('ACTIVE');
          }}
          className="text-xs text-gray-500 hover:text-gray-800 underline"
        >
          Reset Filters
        </button>
      </div>

      {/* Alerts Table */}
      {loading ? (
        <p className="text-gray-500 text-sm p-4">Loading alerts…</p>
      ) : alerts.length === 0 ? (
        <div className="bg-white border rounded-lg p-8 text-center text-gray-500 text-sm">
          No inventory alerts found matching your filter criteria.
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b text-gray-600">
                  <th className="px-4 py-3 text-left font-medium">Consumable</th>
                  <th className="px-4 py-3 text-left font-medium">Type</th>
                  <th className="px-4 py-3 text-left font-medium">Severity</th>
                  <th className="px-4 py-3 text-right font-medium">Current Stock</th>
                  <th className="px-4 py-3 text-right font-medium">MSL Threshold</th>
                  <th className="px-4 py-3 text-left font-medium">UOM</th>
                  <th className="px-4 py-3 text-left font-medium">Message</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-left font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {alerts.map((alert) => (
                  <tr key={alert.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs text-gray-500">{alert.consumable_code}</span>
                      <span className="block font-medium text-gray-900">{alert.consumable_name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <AlertTypeBadge type={alert.alert_type} />
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={alert.severity} />
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-red-700">
                      {alert.current_stock}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700">
                      {alert.threshold_qty}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{alert.uom}</td>
                    <td className="px-4 py-3 max-w-xs text-xs text-gray-700">
                      {alert.message}
                      {alert.acknowledged_by_username && (
                        <span className="block text-[11px] text-gray-400 mt-0.5">
                          Ack by {alert.acknowledged_by_username} at {new Date(alert.acknowledged_at || '').toLocaleTimeString()}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs ${STATUS_BADGES[alert.status]}`}>
                        {alert.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {alert.status === 'ACTIVE' ? (
                        <button
                          onClick={() => handleAcknowledge(alert.id)}
                          className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700 transition-colors shadow-sm"
                        >
                          Acknowledge
                        </button>
                      ) : (
                        <span className="text-xs text-gray-400">✓ Done</span>
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
  );
}
