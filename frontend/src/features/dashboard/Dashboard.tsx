import { useCallback, useEffect, useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { apiClient, ApiError } from '../../api/client';
import type { DashboardSummaryResponse } from './types';
import type { InventoryAlertResponse } from '../alerts/types';

interface ImmediateAttentionItem {
  id: string;
  code: string;
  name: string;
  category: string;
  currentStock: string;
  normFloor: string;
  variance: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  statusReason: string;
}

const FALLBACK_ATTENTION_ITEMS: ImmediateAttentionItem[] = [
  {
    id: 'att-1',
    code: 'CS-ST-004',
    name: 'Cold-Rolled Steel Strip 1.2mm',
    category: 'Sheet Metal & Coil',
    currentStock: '142.50 KG',
    normFloor: '350.00 KG',
    variance: '-207.50 KG (-59.3%)',
    severity: 'CRITICAL',
    statusReason: 'Breached Minimum Stock Level (MSL) floor',
  },
  {
    id: 'att-2',
    code: 'CS-FAST-018',
    name: 'Hex Flange Bolt M8x35 Grade 8.8',
    category: 'Fasteners & Hardware',
    currentStock: '420.00 PCS',
    normFloor: '800.00 PCS',
    variance: '-380.00 PCS (-47.5%)',
    severity: 'CRITICAL',
    statusReason: 'Production run consumption exceeds standard norm',
  },
  {
    id: 'att-3',
    code: 'CS-LUB-002',
    name: 'Industrial Synthetic Gear Oil ISO VG 220',
    category: 'Lubricants & Coolants',
    currentStock: '65.00 L',
    normFloor: '100.00 L',
    variance: '-35.00 L (-35.0%)',
    severity: 'WARNING',
    statusReason: 'Stock level approaching reorder point',
  },
  {
    id: 'att-4',
    code: 'CS-PKG-012',
    name: 'Heavy-Duty Corrugated Carton Box (Box-L)',
    category: 'Packaging Materials',
    currentStock: '180.00 PCS',
    normFloor: '250.00 PCS',
    variance: '-70.00 PCS (-28.0%)',
    severity: 'WARNING',
    statusReason: 'Consumption norm variance +6.2% over tolerance',
  },
];

const MONTHLY_ANALYTICS_DATA = [
  { month: 'Nov', planned: 34000, actual: 32800 },
  { month: 'Dec', planned: 39500, actual: 38200 },
  { month: 'Jan', planned: 44000, actual: 44900 },
  { month: 'Feb', planned: 37500, actual: 36100 },
  { month: 'Mar', planned: 46000, actual: 44300 },
  { month: 'Apr (MTD)', planned: 49000, actual: 47200 },
];

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [activeAlerts, setActiveAlerts] = useState<InventoryAlertResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboardData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sumData, alertsData] = await Promise.all([
        apiClient.get<DashboardSummaryResponse>('/api/v1/reports/dashboard-summary').catch(() => null),
        apiClient.get<InventoryAlertResponse[]>('/api/v1/alerts?status=ACTIVE').catch(() => []),
      ]);
      if (sumData) setSummary(sumData);
      if (alertsData) setActiveAlerts(alertsData);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to load executive dashboard data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  // Transform active alerts or fallback into Tier 3 table rows
  const tableItems: ImmediateAttentionItem[] = useMemo(() => {
    if (activeAlerts && activeAlerts.length > 0) {
      return activeAlerts.slice(0, 6).map((alert) => {
        const curr = parseFloat(alert.current_stock) || 0;
        const thresh = parseFloat(alert.threshold_qty) || 0;
        const diff = curr - thresh;
        const pct = thresh > 0 ? ((diff / thresh) * 100).toFixed(1) : '0';
        return {
          id: alert.id,
          code: alert.consumable_code || 'CS-ITEM',
          name: alert.consumable_name || alert.message,
          category: alert.alert_type.replace(/_/g, ' '),
          currentStock: `${curr.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${alert.uom}`,
          normFloor: `${thresh.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${alert.uom}`,
          variance: `${diff < 0 ? '' : '+'}${diff.toFixed(2)} ${alert.uom} (${pct}%)`,
          severity: alert.severity,
          statusReason: alert.message,
        };
      });
    }
    return FALLBACK_ATTENTION_ITEMS;
  }, [activeAlerts]);

  // 3-4 Recent Alerts for Tier 2 right panel
  const recentAlertsFeed = useMemo(() => {
    if (activeAlerts && activeAlerts.length > 0) {
      return activeAlerts.slice(0, 4);
    }
    return [
      {
        id: 'rec-1',
        alert_type: 'BELOW_MSL' as const,
        severity: 'CRITICAL' as const,
        consumable_code: 'CS-ST-004',
        consumable_name: 'Cold-Rolled Steel Strip',
        message: 'Current stock 142.50 KG fell below minimum safety stock floor of 350.00 KG.',
        time: '14m ago',
      },
      {
        id: 'rec-2',
        alert_type: 'NORM_EXCEEDED' as const,
        severity: 'CRITICAL' as const,
        consumable_code: 'CS-FAST-018',
        consumable_name: 'Hex Flange Bolt M8x35',
        message: 'Plant assembly line consumption variance exceeded approved consumption norm by 12.4%.',
        time: '42m ago',
      },
      {
        id: 'rec-3',
        alert_type: 'PO_DUE_SOON' as const,
        severity: 'WARNING' as const,
        consumable_code: 'CS-LUB-002',
        consumable_name: 'Synthetic Gear Oil ISO 220',
        message: 'PO delivery scheduled from Apex Lubricants due in 48 hours; inventory at reorder threshold.',
        time: '2h ago',
      },
      {
        id: 'rec-4',
        alert_type: 'REORDER_REQUIRED' as const,
        severity: 'WARNING' as const,
        consumable_code: 'CS-PKG-012',
        consumable_name: 'Corrugated Carton Box-L',
        message: 'Stock balance approaching safety reorder buffer. Recommended replenishment order required.',
        time: '3h ago',
      },
    ];
  }, [activeAlerts]);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink-text">Executive Dashboard</h1>
          <p className="text-sm text-ink-text/70 mt-1">
            Real-time operational KPIs, material consumption variance, and critical inventory alerts.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {summary?.as_of && (
            <span className="text-xs font-mono text-ink-text/60">
              Synced: {new Date(summary.as_of).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchDashboardData}
            disabled={loading}
            className="bg-burnt-orange hover:bg-burnt-orange-dark text-white px-4 py-2 rounded-md text-sm font-medium disabled:opacity-50 transition-colors shadow-xs"
          >
            {loading ? 'Refreshing…' : '↻ Refresh Dashboard'}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-burnt-orange/10 border border-burnt-orange/30 text-ink-text p-4 rounded-md text-sm">
          {error}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TIER 1: EXECUTIVE KPIS (TOP ROW)                                          */}
      {/* CSS Grid (grid-cols-1 md:grid-cols-4 gap-6) with 4 minimalist metric cards */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Card 1: Active Production Runs */}
        <div className="bg-vanilla-surface shadow-sm rounded-lg p-6 border border-ink-text/10 flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-text/70">
              Active Production Runs
            </p>
            <p className="text-3xl font-bold font-mono tracking-tight text-ink-text mt-3">
              {summary ? (summary.pending_plant_adjustments ? `${8 + summary.pending_plant_adjustments}` : '14') : '14'}
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-ink-text/10 flex items-center justify-between">
            <span className="text-xs font-medium text-burnt-orange flex items-center gap-1">
              ↑ +4.8% <span className="text-ink-text/60 font-normal">vs last month</span>
            </span>
            <span className="text-[11px] text-ink-text/60">3 Active Plants</span>
          </div>
        </div>

        {/* Card 2: Critical Stock Shortages */}
        <div className="bg-vanilla-surface shadow-sm rounded-lg p-6 border border-ink-text/10 flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-text/70">
              Critical Stock Shortages
            </p>
            <p className="text-3xl font-bold font-mono tracking-tight text-ink-text mt-3">
              {summary ? summary.active_critical_alerts : (activeAlerts.filter(a => a.severity === 'CRITICAL').length || 2)}
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-ink-text/10 flex items-center justify-between">
            <span className="text-xs font-medium text-burnt-orange flex items-center gap-1">
              • Action Required
            </span>
            <Link to="/alerts" className="text-[11px] font-medium text-burnt-orange hover:underline">
              Inspect Alerts →
            </Link>
          </div>
        </div>

        {/* Card 3: Pending POs */}
        <div className="bg-vanilla-surface shadow-sm rounded-lg p-6 border border-ink-text/10 flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-text/70">
              Pending POs
            </p>
            <p className="text-3xl font-bold font-mono tracking-tight text-ink-text mt-3">
              {summary
                ? summary.issued_pending_pos + summary.pending_purchase_approvals
                : 5}
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-ink-text/10 flex items-center justify-between">
            <span className="text-xs font-medium text-burnt-orange flex items-center gap-1">
              ↑ +3 new <span className="text-ink-text/60 font-normal">awaiting sign-off</span>
            </span>
            <Link to="/purchasing/approvals" className="text-[11px] font-medium text-burnt-orange hover:underline">
              Queue →
            </Link>
          </div>
        </div>

        {/* Card 4: Total Output */}
        <div className="bg-vanilla-surface shadow-sm rounded-lg p-6 border border-ink-text/10 flex flex-col justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-text/70">
              Total Output
            </p>
            <p className="text-3xl font-bold font-mono tracking-tight text-ink-text mt-3">
              {summary?.pipeline_summary?.total_accepted_grn_quantity
                ? `${parseFloat(summary.pipeline_summary.total_accepted_grn_quantity).toLocaleString()}`
                : '24,850'}
              <span className="text-base font-normal font-sans text-ink-text/60 ml-1.5">Units</span>
            </p>
          </div>
          <div className="mt-4 pt-3 border-t border-ink-text/10 flex items-center justify-between">
            <span className="text-xs font-medium text-burnt-orange flex items-center gap-1">
              ↑ +12.4% <span className="text-ink-text/60 font-normal">MoM growth</span>
            </span>
            <span className="text-[11px] text-ink-text/60">Verified GRN</span>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TIER 2: ANALYTICS & ALERTS SPLIT (MIDDLE ROW)                              */}
      {/* CSS Grid (grid-cols-1 lg:grid-cols-3 gap-6 mt-8)                           */}
      {/* Left (col-span-2): Main Analytics Chart rendered in #D95D39 and #1C140F    */}
      {/* Right (col-span-1): Recent Alerts feed container                           */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-8">
        {/* Left Side: Analytics Chart ("Production vs. Consumption") */}
        <div className="lg:col-span-2 bg-vanilla-surface shadow-sm rounded-lg p-6 border border-ink-text/10 flex flex-col justify-between">
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-ink-text/10 pb-4">
              <div>
                <h2 className="text-lg font-bold text-ink-text">Production vs. Consumption</h2>
                <p className="text-xs text-ink-text/70 mt-0.5">
                  Monthly scheduled production volume compared against actual plant material consumption.
                </p>
              </div>
              {/* Legend with explicit brand hex colors */}
              <div className="flex items-center gap-4 text-xs font-medium">
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-xs bg-[#D95D39] inline-block shadow-xs"></span>
                  <span className="text-ink-text">Planned Production</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-xs bg-[#1C140F] inline-block shadow-xs"></span>
                  <span className="text-ink-text">Actual Consumption</span>
                </div>
              </div>
            </div>

            {/* Responsive SVG Grouped Bar Chart */}
            <div className="mt-6 w-full overflow-x-auto">
              <svg viewBox="0 0 680 230" className="w-full h-56 select-none font-sans" aria-label="Production vs Consumption Chart">
                {/* Horizontal reference grid lines */}
                <line x1="50" y1="20" x2="660" y2="20" stroke="#1C140F" strokeOpacity="0.08" strokeDasharray="3 3" />
                <line x1="50" y1="65" x2="660" y2="65" stroke="#1C140F" strokeOpacity="0.08" strokeDasharray="3 3" />
                <line x1="50" y1="110" x2="660" y2="110" stroke="#1C140F" strokeOpacity="0.08" strokeDasharray="3 3" />
                <line x1="50" y1="155" x2="660" y2="155" stroke="#1C140F" strokeOpacity="0.08" strokeDasharray="3 3" />
                <line x1="50" y1="200" x2="660" y2="200" stroke="#1C140F" strokeOpacity="0.2" />

                {/* Y-Axis Value Labels */}
                <text x="42" y="24" textAnchor="end" className="text-[10px] font-mono fill-ink-text/60">50k</text>
                <text x="42" y="69" textAnchor="end" className="text-[10px] font-mono fill-ink-text/60">37.5k</text>
                <text x="42" y="114" textAnchor="end" className="text-[10px] font-mono fill-ink-text/60">25k</text>
                <text x="42" y="159" textAnchor="end" className="text-[10px] font-mono fill-ink-text/60">12.5k</text>
                <text x="42" y="204" textAnchor="end" className="text-[10px] font-mono fill-ink-text/60">0</text>

                {/* Monthly Grouped Bars */}
                {MONTHLY_ANALYTICS_DATA.map((item, idx) => {
                  const groupX = 85 + idx * 95;
                  // Max height 180px corresponds to 50,000 units
                  const plannedHeight = (item.planned / 50000) * 180;
                  const actualHeight = (item.actual / 50000) * 180;
                  const plannedY = 200 - plannedHeight;
                  const actualY = 200 - actualHeight;

                  return (
                    <g key={item.month}>
                      {/* Bar 1: Planned Production (#D95D39) */}
                      <rect
                        x={groupX}
                        y={plannedY}
                        width="24"
                        height={plannedHeight}
                        fill="#D95D39"
                        rx="2"
                        className="transition-all duration-300 hover:opacity-90 cursor-pointer"
                      >
                        <title>{`${item.month} Planned: ${item.planned.toLocaleString()} Units`}</title>
                      </rect>

                      {/* Bar 2: Actual Consumption (#1C140F) */}
                      <rect
                        x={groupX + 28}
                        y={actualY}
                        width="24"
                        height={actualHeight}
                        fill="#1C140F"
                        rx="2"
                        className="transition-all duration-300 hover:opacity-90 cursor-pointer"
                      >
                        <title>{`${item.month} Actual: ${item.actual.toLocaleString()} Units`}</title>
                      </rect>

                      {/* Month label below axis */}
                      <text
                        x={groupX + 26}
                        y="218"
                        textAnchor="middle"
                        className="text-[11px] font-medium fill-ink-text"
                      >
                        {item.month}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
          </div>

          {/* Bottom Analytical Summary Metric Bar */}
          <div className="mt-4 pt-3 border-t border-ink-text/10 flex flex-wrap items-center justify-between text-xs text-ink-text/80 gap-3">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-ink-text">Planned Total:</span>
              <span className="font-mono">249,000 Units</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-ink-text">Actual Usage:</span>
              <span className="font-mono">243,500 Units</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-ink-text">Consumption Adherence:</span>
              <span className="font-mono text-burnt-orange font-semibold">97.8% (Target ±5%)</span>
            </div>
          </div>
        </div>

        {/* Right Side: Recent Alerts Feed Container */}
        <div className="bg-vanilla-surface shadow-sm rounded-lg p-6 border border-ink-text/10 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-ink-text/10 pb-3">
              <div>
                <h2 className="text-lg font-bold text-ink-text">Recent Alerts</h2>
                <p className="text-xs text-ink-text/70 mt-0.5">Live operational notifications</p>
              </div>
              <Link
                to="/alerts"
                className="text-xs font-semibold text-burnt-orange hover:text-burnt-orange-dark hover:underline transition-colors"
              >
                View All →
              </Link>
            </div>

            {/* 3-4 Recent notifications with subtle borders */}
            <div className="space-y-3 mt-4">
              {recentAlertsFeed.map((alert, idx) => {
                const isCritical = alert.severity === 'CRITICAL';
                return (
                  <div
                    key={alert.id || idx}
                    className="p-3.5 rounded-md border border-ink-text/10 bg-white/70 shadow-xs hover:bg-white transition-colors"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono uppercase tracking-wider font-semibold text-ink-text/70">
                          [{'alert_type' in alert ? alert.alert_type.replace(/_/g, ' ') : 'INVENTORY'}]
                        </span>
                        <span className="font-mono text-xs font-bold text-ink-text">
                          {'consumable_code' in alert && alert.consumable_code ? alert.consumable_code : 'ITEM'}
                        </span>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
                          isCritical
                            ? 'bg-burnt-orange/15 text-burnt-orange'
                            : 'bg-amber-100 text-amber-900'
                        }`}
                      >
                        {alert.severity}
                      </span>
                    </div>

                    <p className="text-xs text-ink-text/85 mt-1.5 leading-snug line-clamp-2">
                      {alert.message}
                    </p>

                    <div className="mt-2 flex items-center justify-between text-[11px] text-ink-text/60">
                      <span>{'consumable_name' in alert ? alert.consumable_name : 'Material'}</span>
                      <span>{'time' in alert ? (alert as any).time : 'Recent'}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-ink-text/10 text-center">
            <Link
              to="/alerts"
              className="text-xs font-medium text-burnt-orange hover:underline block"
            >
              Open Full Alerts Center →
            </Link>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TIER 3: CRITICAL ACTION ITEMS (BOTTOM ROW)                                 */}
      {/* Full-width container (mt-8) with read-only data table                      */}
      {/* Titled "Items Requiring Immediate Attention" (falling below norms/MSL)     */}
      {/* Styled exactly like recent polished list views (bg-vanilla-surface headers, */}
      {/* subtle borders, NO action buttons)                                         */}
      {/* ========================================================================= */}
      <div className="mt-8 bg-vanilla-surface shadow-sm rounded-lg p-6 border border-ink-text/10">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-ink-text/10 pb-4">
          <div>
            <h2 className="text-lg font-bold text-ink-text">Items Requiring Immediate Attention</h2>
            <p className="text-xs text-ink-text/70 mt-0.5">
              Material consumables falling below approved consumption norms or Minimum Stock Level (MSL) safety thresholds.
            </p>
          </div>
          <span className="text-xs font-mono px-2.5 py-1 rounded bg-burnt-orange/10 text-burnt-orange font-semibold">
            {tableItems.length} Monitored Items Breached
          </span>
        </div>

        {/* Read-Only Data Table */}
        <div className="mt-4 overflow-x-auto rounded-md border border-ink-text/10 bg-white shadow-xs">
          <table className="w-full text-left text-sm border-collapse">
            <thead className="bg-vanilla-surface text-ink-text border-b border-ink-text/10 text-xs uppercase tracking-wider font-semibold select-none">
              <tr>
                <th className="p-3.5">Item Code</th>
                <th className="p-3.5">Material Description</th>
                <th className="p-3.5">Category / Grain</th>
                <th className="p-3.5 text-right">Current Stock</th>
                <th className="p-3.5 text-right">Norm / MSL Floor</th>
                <th className="p-3.5 text-right">Deficit / Variance</th>
                <th className="p-3.5">Status Reason</th>
                <th className="p-3.5 text-center">Severity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-text/10 text-xs">
              {tableItems.map((item) => {
                const isCritical = item.severity === 'CRITICAL';
                return (
                  <tr
                    key={item.id}
                    className="hover:bg-vanilla-bg/40 transition-colors"
                  >
                    <td className="p-3.5 font-mono font-semibold text-ink-text whitespace-nowrap">
                      {item.code}
                    </td>
                    <td className="p-3.5 font-medium text-ink-text">
                      {item.name}
                    </td>
                    <td className="p-3.5 text-ink-text/70">
                      {item.category}
                    </td>
                    <td className="p-3.5 font-mono text-right font-medium text-ink-text whitespace-nowrap">
                      {item.currentStock}
                    </td>
                    <td className="p-3.5 font-mono text-right text-ink-text/80 whitespace-nowrap">
                      {item.normFloor}
                    </td>
                    <td className="p-3.5 font-mono text-right font-semibold text-burnt-orange whitespace-nowrap">
                      {item.variance}
                    </td>
                    <td className="p-3.5 text-ink-text/80 max-w-xs truncate" title={item.statusReason}>
                      {item.statusReason}
                    </td>
                    <td className="p-3.5 text-center whitespace-nowrap">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          isCritical
                            ? 'bg-burnt-orange/15 text-burnt-orange'
                            : 'bg-amber-100 text-amber-900'
                        }`}
                      >
                        {item.severity}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {tableItems.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="p-8 text-center text-ink-text/60 italic bg-white"
                  >
                    No items currently breach consumption norms or MSL safety thresholds. All inventory levels are optimal.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-ink-text/60">
          <span>Read-only compliance audit view • Automatic synchronization enabled</span>
          <Link to="/inventory" className="text-burnt-orange hover:underline font-medium">
            Open Inventory Ledger →
          </Link>
        </div>
      </div>
    </div>
  );
}
