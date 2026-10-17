import React, { useState, useEffect } from 'react';
import type { UserResponse, UserCreate, UserUpdate } from '../../api/users';
import { usersApi } from '../../api/users';
import { Shield, Key, X, Building, AlertCircle, Eye, EyeOff, Globe, Bell } from 'lucide-react';

export const BASE_ROLES = [
  { code: 'PLANNER', label: 'Planner' },
  { code: 'PLANT_INCHARGE', label: 'Plant Incharge' },
  { code: 'PURCHASE', label: 'Purchase' },
  { code: 'STORE', label: 'Store' },
  { code: 'MANAGEMENT', label: 'Management' },
  { code: 'ADMIN', label: 'Admin' },
];

export interface ModuleDef {
  key: string;
  label: string;
  desc: string;
}

export const MODULES: ModuleDef[] = [
  { key: 'masters', label: '1. Product Master', desc: 'Units, consumables, and supplier master catalogs' },
  { key: 'consumption_norms', label: '2. Consumption Norms', desc: 'Consumption norms, rules, and calculation baselines' },
  { key: 'production_mappings', label: '3. Production Mapping', desc: 'Process and equipment production mappings' },
  { key: 'prd_planning', label: '4. Production for Sale (PRD)', desc: 'PRD planning workspace and production schedules' },
  { key: 'requirements', label: '5. Requirement', desc: 'Consumable requirements workspace and shortage calculations' },
  { key: 'plant_workflow', label: '6. Plant Review', desc: 'Plant confirmation and intake review workflow' },
  { key: 'inventory', label: '7. Inventory', desc: 'Inventory management, stock balance, and ledger tracking' },
  { key: 'purchase', label: '8. Purchase', desc: 'Purchase requests, recommendations, and procurement planning' },
  { key: 'purchase_orders', label: '9. Purchase Order', desc: 'Purchase orders management, vendor POs, and commit status' },
  { key: 'goods_receipts', label: '10. Goods Receipts', desc: 'Goods receipt notes (GRN) and incoming intake verification' },
];

export const PLANT_FLAGS: { key: keyof UserCreate; label: string }[] = [
  { key: 'can_access_plant_1', label: 'Plant I' },
  { key: 'can_access_plant_2', label: 'Plant II' },
  { key: 'can_access_plant_3', label: 'Plant III' },
  { key: 'can_access_plant_4', label: 'Plant IV' },
  { key: 'can_access_plant_5', label: 'Plant V' },
];

export const GLOBAL_MODULE_FLAGS = [
  { key: 'can_access_dashboard', label: 'Executive Reports & Dashboard', desc: 'Executive reporting hub, KPI metrics, stock alerts, and procurement pipeline' },
] as const;

export const ALERT_CATEGORIES = [
  { key: 'alert_production', label: 'Production Delays', desc: 'Plant & manufacturing delay notifications', badge: 'Plant/Mfg' },
  { key: 'alert_inventory', label: 'Stock Shortages', desc: 'Store inventory & consumable shortage alerts', badge: 'Store/Stock' },
  { key: 'alert_purchasing', label: 'Purchasing & PO', desc: 'PO approvals & vendor delivery updates', badge: 'Purchase/PO' },
  { key: 'alert_system', label: 'System & Admin', desc: 'Critical system errors and administrative notices', badge: 'System/Admin' },
] as const;

export const ALL_CRUD_KEYS: string[] = MODULES.flatMap(m => [
  `${m.key}_read`,
  `${m.key}_create`,
  `${m.key}_update`,
  `${m.key}_delete`,
]);

export const DEFAULT_PERMISSIONS: Record<string, boolean> = {
  ...Object.fromEntries(ALL_CRUD_KEYS.map(k => [k, false])),
  can_access_plant_1: false,
  can_access_plant_2: false,
  can_access_plant_3: false,
  can_access_plant_4: false,
  can_access_plant_5: false,
  can_access_dashboard: false,
  alert_production: false,
  alert_inventory: false,
  alert_purchasing: false,
  alert_system: false,
};

export interface UserPermissionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  editingUser: UserResponse | null;
}

export default function UserPermissionsModal({
  isOpen,
  onClose,
  onSuccess,
  editingUser,
}: UserPermissionsModalProps) {
  const [fullName, setFullName] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [selectedRole, setSelectedRole] = useState('PLANNER');
  const [isActive, setIsActive] = useState(true);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({ ...DEFAULT_PERMISSIONS });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyRoleDefaults = (role: string) => {
    const p: Record<string, boolean> = { ...DEFAULT_PERMISSIONS };
    if (role === 'ADMIN') {
      ALL_CRUD_KEYS.forEach(k => { p[k] = true; });
      PLANT_FLAGS.forEach(f => { p[f.key] = true; });
      GLOBAL_MODULE_FLAGS.forEach(f => { p[f.key] = true; });
      ALERT_CATEGORIES.forEach(c => { p[c.key] = true; });
    } else if (role === 'PLANNER') {
      ['masters', 'production_mappings', 'consumption_norms', 'prd_planning', 'requirements'].forEach(m => {
        ['read', 'create', 'update', 'delete'].forEach(op => { p[`${m}_${op}`] = true; });
      });
      p.can_access_dashboard = true;
      p.alert_production = true;
    } else if (role === 'PLANT_INCHARGE') {
      ['plant_workflow', 'inventory'].forEach(m => {
        ['read', 'create', 'update', 'delete'].forEach(op => { p[`${m}_${op}`] = true; });
      });
      p.can_access_plant_1 = true;
      p.alert_production = true;
    } else if (role === 'PURCHASE') {
      ['purchase', 'purchase_orders', 'goods_receipts', 'inventory'].forEach(m => {
        ['read', 'create', 'update', 'delete'].forEach(op => { p[`${m}_${op}`] = true; });
      });
      p.alert_purchasing = true;
    } else if (role === 'STORE') {
      ['inventory', 'goods_receipts'].forEach(m => {
        ['read', 'create', 'update', 'delete'].forEach(op => { p[`${m}_${op}`] = true; });
      });
      p.alert_inventory = true;
    } else if (role === 'MANAGEMENT') {
      ALL_CRUD_KEYS.filter(k => k.endsWith('_read')).forEach(k => { p[k] = true; });
      p.can_access_dashboard = true;
      ALERT_CATEGORIES.forEach(c => { p[c.key] = true; });
    }
    return p;
  };

  useEffect(() => {
    if (!isOpen) return;
    setError(null);

    if (editingUser) {
      setFullName(editingUser.full_name || '');
      setEmployeeId(editingUser.employee_id || '');
      setUsername(editingUser.username);
      setPassword('');
      setSelectedRole(editingUser.roles[0] || 'PLANNER');
      setIsActive(editingUser.is_active);

      const loadedPerms: Record<string, boolean> = { ...DEFAULT_PERMISSIONS };
      ALL_CRUD_KEYS.forEach(k => {
        loadedPerms[k] = Boolean((editingUser as any)[k]);
      });
      PLANT_FLAGS.forEach(f => {
        loadedPerms[f.key] = Boolean((editingUser as any)[f.key]);
      });
      GLOBAL_MODULE_FLAGS.forEach(f => {
        loadedPerms[f.key] = Boolean((editingUser as any)[f.key]);
      });
      ALERT_CATEGORIES.forEach(c => {
        loadedPerms[c.key] = Boolean((editingUser as any)[c.key]);
      });
      setPermissions(loadedPerms);
    } else {
      setFullName('');
      setEmployeeId('');
      setUsername('');
      setPassword('');
      setSelectedRole('PLANNER');
      setIsActive(true);
      setPermissions(applyRoleDefaults('PLANNER'));
    }
  }, [isOpen, editingUser]);

  const handleRoleChange = (newRole: string) => {
    setSelectedRole(newRole);
    setPermissions(applyRoleDefaults(newRole));
  };

  const handleToggleCrud = (moduleKey: string, op: 'read' | 'create' | 'update' | 'delete') => {
    setPermissions(prev => {
      const next = { ...prev };
      const currentVal = Boolean(next[`${moduleKey}_${op}`]);
      const newVal = !currentVal;

      next[`${moduleKey}_${op}`] = newVal;

      // If user checks create, update, or delete -> automatically grant read
      if (newVal && (op === 'create' || op === 'update' || op === 'delete')) {
        next[`${moduleKey}_read`] = true;
      }

      // If user unchecks read -> automatically revoke create, update, delete
      if (!newVal && op === 'read') {
        next[`${moduleKey}_create`] = false;
        next[`${moduleKey}_update`] = false;
        next[`${moduleKey}_delete`] = false;
      }

      return next;
    });
  };

  const handleTogglePlant = (key: keyof UserCreate) => {
    setPermissions(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleToggleFlag = (key: string) => {
    setPermissions(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);

    try {
      const finalPermissions = { ...permissions };
      if (selectedRole !== 'PLANT_INCHARGE') {
        PLANT_FLAGS.forEach(f => {
          finalPermissions[f.key] = false;
        });
      }

      if (editingUser) {
        const updatePayload: UserUpdate = {
          full_name: fullName || null,
          employee_id: employeeId || null,
          roles: [selectedRole],
          is_active: isActive,
          ...finalPermissions,
        };
        if (password) updatePayload.password = password;
        await usersApi.updateUser(editingUser.id, updatePayload);
      } else {
        const createPayload: UserCreate = {
          username,
          password,
          full_name: fullName || null,
          employee_id: employeeId || null,
          roles: [selectedRole],
          ...finalPermissions as any,
        };
        await usersApi.createUser(createPayload);
      }
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to save user');
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-erp-chocolate/60 backdrop-blur-xs flex items-center justify-center p-4 sm:p-6 z-50 font-['Plus_Jakarta_Sans',sans-serif]">
      <div className="bg-white rounded-2xl max-w-5xl w-full shadow-2xl border border-erp-dark-vanilla/30 flex flex-col max-h-[90vh] overflow-hidden">
        {/* Modal Header */}
        <div className="flex justify-between items-center px-6 py-4.5 border-b border-erp-dark-vanilla/30 shrink-0 bg-erp-vanilla/30">
          <h2 className="text-lg font-bold text-erp-chocolate flex items-center gap-2">
            <Shield className="w-5 h-5 text-erp-orange" />
            {editingUser ? `Edit User & Permissions: ${editingUser.username}` : 'Provision New User'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="text-erp-chocolate/60 hover:text-erp-chocolate p-1.5 rounded-lg hover:bg-erp-vanilla/50 transition-colors focus:outline-none"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg flex items-center gap-2 text-sm">
            <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} autoComplete="off" className="flex flex-col flex-1 min-h-0 overflow-hidden">
          {/* Scrollable Form Body */}
          <div className="p-6 overflow-y-auto space-y-6 flex-1">
            {/* Section 1: Basic User Details */}
            <div className="space-y-4">
              <div className="text-sm font-bold text-erp-chocolate tracking-wide uppercase flex items-center gap-1.5">
                BASIC USER DETAILS & CREDENTIALS
              </div>

              {/* Employee Information */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-erp-chocolate/80 mb-1">
                    Employee Full Name
                  </label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={e => setFullName(e.target.value)}
                    className="w-full bg-white border border-erp-dark-vanilla/40 rounded-lg px-3.5 py-2 text-sm text-erp-chocolate placeholder:text-erp-chocolate/40 focus:outline-none focus:ring-2 focus:ring-erp-orange focus:border-transparent transition-all"
                    placeholder="e.g. Jane Doe"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-erp-chocolate/80 mb-1">
                    Employee ID
                  </label>
                  <input
                    type="text"
                    value={employeeId}
                    onChange={e => setEmployeeId(e.target.value)}
                    className="w-full bg-white border border-erp-dark-vanilla/40 rounded-lg px-3.5 py-2 text-sm text-erp-chocolate placeholder:text-erp-chocolate/40 focus:outline-none focus:ring-2 focus:ring-erp-orange focus:border-transparent transition-all"
                    placeholder="e.g. EMP-1042"
                  />
                </div>
              </div>

              {/* Account Credentials */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-erp-chocolate/80 mb-1">
                    Username <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    autoComplete="new-password"
                    disabled={Boolean(editingUser?.is_super_admin || editingUser?.is_superuser)}
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    className="w-full bg-white border border-erp-dark-vanilla/40 rounded-lg px-3.5 py-2 text-sm text-erp-chocolate placeholder:text-erp-chocolate/40 focus:outline-none focus:ring-2 focus:ring-erp-orange focus:border-transparent disabled:bg-erp-vanilla/20 disabled:text-erp-chocolate/50 transition-all"
                    placeholder="e.g. store_user"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-erp-chocolate/80 mb-1">
                    {editingUser ? 'Password (Leave blank to keep existing)' : 'Password *'}
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      required={!editingUser}
                      autoComplete={showPassword ? 'off' : 'new-password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      className="w-full bg-white border border-erp-dark-vanilla/40 rounded-lg px-3.5 py-2 pr-10 text-sm text-erp-chocolate placeholder:text-erp-chocolate/40 focus:outline-none focus:ring-2 focus:ring-erp-orange focus:border-transparent transition-all"
                      placeholder="••••••••"
                    />
                    {password.length > 0 && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setShowPassword(prev => !prev);
                        }}
                        onMouseDown={(e) => e.preventDefault()}
                        className="absolute inset-y-0 right-0 pr-3 flex items-center text-erp-chocolate/60 hover:text-erp-chocolate cursor-pointer pointer-events-auto z-20 focus:outline-none"
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                      >
                        {showPassword ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 2: Base Role Assignment & Account Status */}
            <div className="border-t border-erp-dark-vanilla/30 pt-4 space-y-3">
              <div className="text-sm font-bold text-erp-chocolate tracking-wide uppercase flex items-center gap-1.5">
                BASE ROLE ASSIGNMENT & ACCOUNT STATUS
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-erp-chocolate/80 mb-1">Base Role Assignment</label>
                  <select
                    value={selectedRole}
                    onChange={e => handleRoleChange(e.target.value)}
                    className="w-full bg-white border border-erp-dark-vanilla/40 rounded-lg px-3.5 py-2 text-sm text-erp-chocolate focus:outline-none focus:ring-2 focus:ring-erp-orange focus:border-transparent transition-all"
                  >
                    {BASE_ROLES.map(r => (
                      <option key={r.code} value={r.code}>{r.label} ({r.code})</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2 pt-2 sm:pt-6">
                  <input
                    type="checkbox"
                    id="isActive"
                    checked={isActive}
                    onChange={e => setIsActive(e.target.checked)}
                    className="accent-erp-orange h-4 w-4 rounded cursor-pointer"
                  />
                  <label htmlFor="isActive" className="text-sm font-semibold text-erp-chocolate cursor-pointer select-none">
                    Account Active
                  </label>
                </div>
              </div>
            </div>

            {/* Section 3: 40 Granular CRUD Feature Flags (10 Modules) */}
            <div className="border-t border-erp-dark-vanilla/30 pt-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3.5 gap-1">
                <h3 className="text-sm font-bold text-erp-chocolate tracking-wide uppercase flex items-center gap-1.5">
                  <Key className="w-4 h-4 text-erp-orange" />
                  CRUD PERMISSION MATRIX (10 MODULES × 4 ACTIONS)
                </h3>
                <span className="text-[11px] text-erp-chocolate/70 italic">
                  Create/Update/Delete auto-enables Read; unchecking Read revokes all.
                </span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5 bg-erp-vanilla/10 p-4 rounded-xl border border-erp-dark-vanilla/20">
                {MODULES.map(mod => {
                  const isRead = Boolean(permissions[`${mod.key}_read`]);
                  const isCreate = Boolean(permissions[`${mod.key}_create`]);
                  const isUpdate = Boolean(permissions[`${mod.key}_update`]);
                  const isDelete = Boolean(permissions[`${mod.key}_delete`]);
                  return (
                    <div
                      key={mod.key}
                      className="p-3.5 bg-white rounded-xl border border-erp-dark-vanilla/20 shadow-xs flex flex-col justify-between space-y-2.5 hover:border-erp-orange/40 transition-colors"
                    >
                      <div>
                        <div className="text-xs font-bold text-erp-chocolate">{mod.label}</div>
                        <div className="text-[11px] text-erp-chocolate/70 leading-relaxed">{mod.desc}</div>
                      </div>
                      <div className="grid grid-cols-4 gap-2 pt-2 border-t border-erp-dark-vanilla/20 text-xs">
                        <label className="flex items-center gap-1.5 cursor-pointer font-medium text-erp-chocolate/80 hover:text-erp-orange transition-colors">
                          <input
                            type="checkbox"
                            checked={isRead}
                            onChange={() => handleToggleCrud(mod.key, 'read')}
                            className="accent-erp-orange h-3.5 w-3.5 rounded cursor-pointer"
                          />
                          <span className="text-[11px]">Read</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer font-medium text-erp-chocolate/80 hover:text-emerald-700 transition-colors">
                          <input
                            type="checkbox"
                            checked={isCreate}
                            onChange={() => handleToggleCrud(mod.key, 'create')}
                            className="accent-erp-orange h-3.5 w-3.5 rounded cursor-pointer"
                          />
                          <span className="text-[11px]">Create</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer font-medium text-erp-chocolate/80 hover:text-amber-700 transition-colors">
                          <input
                            type="checkbox"
                            checked={isUpdate}
                            onChange={() => handleToggleCrud(mod.key, 'update')}
                            className="accent-erp-orange h-3.5 w-3.5 rounded cursor-pointer"
                          />
                          <span className="text-[11px]">Update</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer font-medium text-erp-chocolate/80 hover:text-rose-700 transition-colors">
                          <input
                            type="checkbox"
                            checked={isDelete}
                            onChange={() => handleToggleCrud(mod.key, 'delete')}
                            className="accent-erp-orange h-3.5 w-3.5 rounded cursor-pointer"
                          />
                          <span className="text-[11px]">Delete</span>
                        </label>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Section 4: Reports & Alerts (Final Workflow Items) */}
            <div className="border-t border-erp-dark-vanilla/30 pt-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3.5 gap-1">
                <h3 className="text-sm font-bold text-erp-chocolate tracking-wide uppercase flex items-center gap-1.5">
                  <Globe className="w-4 h-4 text-erp-orange" />
                  REPORTS & ALERTS (FINAL WORKFLOW ITEMS)
                </h3>
                <span className="text-[11px] text-erp-chocolate/70 italic">
                  Multi-format report analytics & domain notification channels
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Reports & Dashboard Global Access */}
                <div className="bg-erp-vanilla/20 p-4 rounded-xl border border-erp-dark-vanilla/30 flex flex-col justify-between">
                  <div>
                    <div className="text-xs font-bold text-erp-chocolate flex items-center gap-1.5 mb-1">
                      <Globe className="w-3.5 h-3.5 text-erp-orange" />
                      Reports & Executive Modules Access
                    </div>
                    <div className="text-[11px] text-erp-chocolate/70 mb-3">
                      Executive reports dashboard and cross-functional pipeline KPIs
                    </div>
                  </div>
                  <div className="space-y-2">
                    {GLOBAL_MODULE_FLAGS.map(mod => (
                      <label
                        key={mod.key}
                        className="flex items-start gap-2.5 p-2.5 bg-white rounded-lg border border-erp-dark-vanilla/30 hover:border-erp-orange/40 cursor-pointer shadow-2xs transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={Boolean(permissions[mod.key])}
                          onChange={() => handleToggleFlag(mod.key)}
                          className="mt-0.5 accent-erp-orange h-4 w-4 rounded cursor-pointer"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-bold text-erp-chocolate">{mod.label}</div>
                          <div className="text-[11px] text-erp-chocolate/70">{mod.desc}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Categorized Alert Subscriptions */}
                <div className="bg-erp-vanilla/20 p-4 rounded-xl border border-erp-dark-vanilla/30 flex flex-col justify-between">
                  <div>
                    <div className="text-xs font-bold text-erp-chocolate flex items-center gap-1.5 mb-1">
                      <Bell className="w-3.5 h-3.5 text-erp-orange" />
                      Alert Subscriptions (4 Categories)
                    </div>
                    <div className="text-[11px] text-erp-chocolate/70 mb-3">
                      Domain-targeted push notifications across supply chain
                    </div>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {ALERT_CATEGORIES.map(cat => (
                      <label
                        key={cat.key}
                        className="flex items-start gap-2 p-2 bg-white rounded-lg border border-erp-dark-vanilla/30 hover:border-erp-orange/40 cursor-pointer shadow-2xs transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={Boolean(permissions[cat.key])}
                          onChange={() => handleToggleFlag(cat.key)}
                          className="mt-0.5 accent-erp-orange h-4 w-4 rounded cursor-pointer"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1 mb-0.5">
                            <span className="text-xs font-bold text-erp-chocolate leading-tight">{cat.label}</span>
                            <span className="bg-erp-tangerine/15 text-erp-topaz rounded-md px-2 py-0.5 text-xs font-semibold shrink-0">
                              {cat.badge}
                            </span>
                          </div>
                          <div className="text-[10px] text-erp-chocolate/70 leading-snug">{cat.desc}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 5: Plant Scope Access Flags - Only for Plant Incharge */}
            {selectedRole === 'PLANT_INCHARGE' && (
              <div className="border-t border-erp-dark-vanilla/30 pt-4">
                <h3 className="text-sm font-bold text-erp-chocolate tracking-wide uppercase mb-3 flex items-center gap-1.5">
                  <Building className="w-4 h-4 text-erp-orange" />
                  PLANT ACCESS SCOPE (5 PLANTS)
                </h3>
                <div className="grid grid-cols-5 gap-3 bg-erp-vanilla/10 p-4 rounded-xl border border-erp-dark-vanilla/20">
                  {PLANT_FLAGS.map(flag => (
                    <label
                      key={flag.key}
                      className="flex items-center gap-2 p-2.5 bg-white rounded-lg border border-erp-dark-vanilla/30 cursor-pointer hover:border-erp-orange/40 transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={Boolean(permissions[flag.key])}
                        onChange={() => handleTogglePlant(flag.key)}
                        className="accent-erp-orange h-4 w-4 rounded cursor-pointer"
                      />
                      <span className="text-xs font-semibold text-erp-chocolate">{flag.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Modal Footer */}
          <div className="flex justify-end gap-3 px-6 py-4 border-t border-erp-dark-vanilla/30 bg-erp-vanilla/20 shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 border border-erp-dark-vanilla/40 text-erp-chocolate/80 bg-white rounded-lg text-sm font-semibold hover:bg-erp-vanilla/30 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-erp-orange hover:bg-erp-tenne text-white rounded-lg text-sm font-bold shadow-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSaving && (
                <svg
                  className="animate-spin -ml-1 mr-1 h-4 w-4 text-white"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
              )}
              <span>{isSaving ? 'Saving...' : 'Save User & Matrix'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
