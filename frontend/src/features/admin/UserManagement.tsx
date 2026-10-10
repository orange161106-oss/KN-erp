import React, { useState, useEffect } from 'react';
import type { UserResponse, UserCreate, UserUpdate } from '../../api/users';
import { usersApi } from '../../api/users';
import { User, Shield, Edit, Plus, X, Building, Key, AlertCircle, Eye, EyeOff, Globe, Bell } from 'lucide-react';
import { TableSkeleton } from '../../components/ui/Skeleton';

const BASE_ROLES = [
  { code: 'PLANNER', label: 'Planner' },
  { code: 'PLANT_INCHARGE', label: 'Plant Incharge' },
  { code: 'PURCHASE', label: 'Purchase' },
  { code: 'STORE', label: 'Store' },
  { code: 'MANAGEMENT', label: 'Management' },
  { code: 'ADMIN', label: 'Admin' },
];

interface ModuleDef {
  key: string;
  label: string;
  desc: string;
}

const MODULES: ModuleDef[] = [
  { key: 'masters', label: '1. Masters', desc: 'Units, consumables, and suppliers masters' },
  { key: 'production_mappings', label: '2. Production Mappings', desc: 'Process and equipment mappings' },
  { key: 'consumption_norms', label: '3. Consumption Norms', desc: 'Consumption norms and rules' },
  { key: 'prd_planning', label: '4. PRD / Planning', desc: 'PRD planning workspace' },
  { key: 'requirements', label: '5. Requirements', desc: 'Consumable requirements workspace' },
  { key: 'plant_workflow', label: '6. Plant Workflow', desc: 'Plant confirmation workflow' },
  { key: 'inventory', label: '7. Inventory', desc: 'Inventory management and stock' },
  { key: 'purchase', label: '8. Purchase', desc: 'Purchase requests and planning' },
  { key: 'purchase_orders', label: '9. Purchase Orders', desc: 'Purchase orders management' },
  { key: 'goods_receipts', label: '10. Goods Receipts', desc: 'Goods receipt notes (GRN)' },
];

const PLANT_FLAGS: { key: keyof UserCreate; label: string }[] = [
  { key: 'can_access_plant_1', label: 'Plant I' },
  { key: 'can_access_plant_2', label: 'Plant II' },
  { key: 'can_access_plant_3', label: 'Plant III' },
  { key: 'can_access_plant_4', label: 'Plant IV' },
  { key: 'can_access_plant_5', label: 'Plant V' },
];

const GLOBAL_MODULE_FLAGS = [
  { key: 'can_access_dashboard', label: 'Executive Dashboard', desc: 'KPI metrics, stock alerts, and procurement pipeline' },
] as const;

const ALERT_CATEGORIES = [
  { key: 'alert_production', label: 'Production Delays', desc: 'Plant & manufacturing delay notifications', badge: 'Plant/Mfg' },
  { key: 'alert_inventory', label: 'Stock Shortages', desc: 'Store inventory & consumable shortage alerts', badge: 'Store/Stock' },
  { key: 'alert_purchasing', label: 'Purchasing & PO', desc: 'PO approvals & vendor delivery updates', badge: 'Purchase/PO' },
  { key: 'alert_system', label: 'System & Admin', desc: 'Critical system errors and administrative notices', badge: 'System/Admin' },
] as const;

const ALL_CRUD_KEYS: string[] = MODULES.flatMap(m => [
  `${m.key}_read`,
  `${m.key}_create`,
  `${m.key}_update`,
  `${m.key}_delete`,
]);

const DEFAULT_PERMISSIONS: Record<string, boolean> = {
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

export default function UserManagement() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null);

  // Form State
  const [fullName, setFullName] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [selectedRole, setSelectedRole] = useState('PLANNER');
  const [isActive, setIsActive] = useState(true);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({ ...DEFAULT_PERMISSIONS });

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await usersApi.getUsers();
      setUsers(data);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleOpenCreateModal = () => {
    setEditingUser(null);
    setFullName('');
    setEmployeeId('');
    setUsername('');
    setPassword('');
    setShowPassword(false);
    setSelectedRole('PLANNER');
    setIsActive(true);
    setPermissions({ ...DEFAULT_PERMISSIONS });
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (user: UserResponse) => {
    setEditingUser(user);
    setFullName(user.full_name || '');
    setEmployeeId(user.employee_id || '');
    setUsername(user.username);
    setPassword('');
    setShowPassword(false);
    setSelectedRole(user.roles[0] || 'PLANNER');
    setIsActive(user.is_active);

    const userPerms: Record<string, boolean> = { ...DEFAULT_PERMISSIONS };
    ALL_CRUD_KEYS.forEach(k => {
      userPerms[k] = Boolean((user as any)[k]);
    });
    PLANT_FLAGS.forEach(p => {
      userPerms[p.key] = Boolean(user[p.key as keyof UserResponse]);
    });
    GLOBAL_MODULE_FLAGS.forEach(g => {
      userPerms[g.key] = Boolean((user as any)[g.key]);
    });
    ALERT_CATEGORIES.forEach(a => {
      userPerms[a.key] = Boolean((user as any)[a.key]);
    });
    setPermissions(userPerms);
    setIsModalOpen(true);
  };

  const handleToggleCrud = (moduleKey: string, op: 'read' | 'create' | 'update' | 'delete') => {
    setPermissions(prev => {
      const field = `${moduleKey}_${op}`;
      const nextVal = !prev[field];
      const updated = { ...prev, [field]: nextVal };

      if (op === 'read' && !nextVal) {
        // Unchecking Read auto-unchecks Create, Update, Delete
        updated[`${moduleKey}_create`] = false;
        updated[`${moduleKey}_update`] = false;
        updated[`${moduleKey}_delete`] = false;
      } else if (op !== 'read' && nextVal) {
        // Checking Create, Update, or Delete auto-checks Read
        updated[`${moduleKey}_read`] = true;
      }

      return updated;
    });
  };

  const handleTogglePlant = (key: string) => {
    setPermissions(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleToggleFlag = (key: string) => {
    setPermissions(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const finalPermissions = { ...permissions };
      if (selectedRole !== 'PLANT_INCHARGE') {
        PLANT_FLAGS.forEach(p => {
          finalPermissions[p.key] = false;
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
      setIsModalOpen(false);
      fetchUsers();
    } catch (err: any) {
      alert(err.message || 'Failed to save user');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center bg-white p-6 rounded-lg shadow-sm border border-gray-200">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Shield className="w-7 h-7 text-indigo-600" />
            User Management & Role Matrix
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Provision employee accounts, base roles, 10 granular feature flags, and plant-scoped access.
          </p>
        </div>
        <button
          onClick={handleOpenCreateModal}
          className="flex items-center gap-2 bg-burnt-orange hover:bg-burnt-orange-dark text-white px-4 py-2 rounded-md font-medium text-sm transition-colors shadow-xs"
        >
          <Plus className="w-4 h-4" /> Add New User
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-md flex items-center gap-2 text-sm">
          <AlertCircle className="w-5 h-5 text-red-500" />
          {error}
        </div>
      )}

      {/* Users Table */}
      {loading ? (
        <TableSkeleton columns={6} rows={5} />
      ) : (
        <div className="bg-white rounded-lg border border-ink-text/10 shadow-2xs overflow-hidden">
          <table className="w-full text-left text-sm text-ink-text/80">
            <thead className="bg-vanilla-surface text-ink-text border-b border-ink-text/10 uppercase text-xs font-semibold">
              <tr>
                <th className="py-3 px-4">Employee / Username</th>
                <th className="py-3 px-4">Base Role</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Plant Access</th>
                <th className="py-3 px-4">Active CRUD Permissions</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-text/10">
              {users.filter(u => !(u.is_super_admin || u.is_superuser)).length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-400">No users found.</td>
                </tr>
              ) : (
              users.filter(u => !(u.is_super_admin || u.is_superuser)).map(u => {
                const activeCrudCount = ALL_CRUD_KEYS.filter(k => Boolean((u as any)[k])).length;
                const activePlants = PLANT_FLAGS.filter(p => Boolean(u[p.key as keyof UserResponse])).map(p => p.label);

                return (
                  <tr key={u.id} className="hover:bg-gray-50 transition-colors">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-gray-400 flex-shrink-0" />
                        <div>
                          <div className="font-medium text-gray-900 flex items-center gap-1.5">
                            {u.username}
                            {(u.is_super_admin || u.is_superuser) && (
                              <span className="bg-purple-100 text-purple-800 text-[10px] px-1.5 py-0.5 rounded font-bold">Super Admin</span>
                            )}
                          </div>
                          {(u.full_name || u.employee_id) && (
                            <div className="text-xs text-gray-500">
                              {u.full_name || 'No Name'} {u.employee_id ? `• ${u.employee_id}` : ''}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span className="bg-blue-50 text-blue-700 border border-blue-200 px-2 py-1 rounded text-xs font-medium">
                        {u.roles.join(', ') || 'No Role'}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      {u.is_active ? (
                        <span className="text-green-700 bg-green-50 px-2 py-0.5 rounded text-xs font-medium">Active</span>
                      ) : (
                        <span className="text-red-700 bg-red-50 px-2 py-0.5 rounded text-xs font-medium">Inactive</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {activePlants.length === 5 ? (
                          <span className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">All 5 Plants</span>
                        ) : activePlants.length > 0 ? (
                          activePlants.map(p => (
                            <span key={p} className="text-xs bg-emerald-50 text-emerald-700 px-1.5 py-0.5 rounded border border-emerald-200">{p}</span>
                          ))
                        ) : (
                          <span className="text-xs text-gray-400">None</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-col gap-1 items-start">
                        <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">
                          {activeCrudCount} / 40 Permissions
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {u.can_access_dashboard && (
                            <span className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded border border-blue-200 font-medium">Dash</span>
                          )}
                          {(u.alert_production || u.alert_inventory || u.alert_purchasing || u.alert_system) && (
                            <span className="text-[10px] bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded border border-amber-200 font-medium">Alerts</span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      {(u.is_super_admin || u.is_superuser) ? (
                        <span className="text-xs text-gray-400 italic font-medium px-2 py-1 bg-gray-100 rounded">Protected</span>
                      ) : (
                        <button
                          onClick={() => handleOpenEditModal(u)}
                          className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-900 font-medium bg-indigo-50 px-2.5 py-1.5 rounded border border-indigo-200"
                        >
                          <Edit className="w-3.5 h-3.5" /> Edit Permissions
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      )}

      {/* Form Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 sm:p-6 z-50">
          <div className="bg-white rounded-xl max-w-5xl w-full shadow-2xl flex flex-col max-h-[90vh] overflow-hidden">
            <div className="flex justify-between items-center px-6 py-4 border-b border-ink-text/10 shrink-0 bg-vanilla-surface">
              <h2 className="text-lg font-bold text-ink-text flex items-center gap-2">
                <Shield className="w-5 h-5 text-burnt-orange" />
                {editingUser ? `Edit User & Permissions: ${editingUser.username}` : 'Provision New User'}
              </h2>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 p-1 rounded-md hover:bg-gray-100 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} autoComplete="off" className="flex flex-col flex-1 min-h-0 overflow-hidden">
              {/* Scrollable Form Body */}
              <div className="p-6 overflow-y-auto space-y-6 flex-1">
                {/* Basic User Details */}
                <div className="space-y-4">
                  <div className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                    Basic User Details & Credentials
                  </div>

                  {/* Employee Information */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-gray-700 mb-1">Employee Full Name</label>
                      <input
                        type="text"
                        autoComplete="new-password"
                        value={fullName}
                        onChange={e => setFullName(e.target.value)}
                        className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                        placeholder="e.g. John Doe"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-gray-700 mb-1">Employee ID</label>
                      <input
                        type="text"
                        autoComplete="new-password"
                        value={employeeId}
                        onChange={e => setEmployeeId(e.target.value)}
                        className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                        placeholder="e.g. EMP-1042"
                      />
                    </div>
                  </div>

                  {/* Account Credentials */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-gray-700 mb-1">
                        Username <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        required
                        autoComplete="new-password"
                        disabled={Boolean(editingUser?.is_super_admin || editingUser?.is_superuser)}
                        value={username}
                        onChange={e => setUsername(e.target.value)}
                        className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100"
                        placeholder="e.g. store_user"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-gray-700 mb-1">
                        {editingUser ? 'Password (Leave blank to keep existing)' : 'Password *'}
                      </label>
                      <div className="relative">
                        <input
                          type={showPassword ? 'text' : 'password'}
                          required={!editingUser}
                          autoComplete={showPassword ? 'off' : 'new-password'}
                          value={password}
                          onChange={e => setPassword(e.target.value)}
                          className="w-full border border-gray-300 rounded px-3 py-2 pr-10 text-sm focus:ring-indigo-500 focus:border-indigo-500"
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
                            className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-500 hover:text-gray-700 cursor-pointer pointer-events-auto z-20 focus:outline-none"
                            style={{ cursor: 'pointer', pointerEvents: 'auto' }}
                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                          >
                            {showPassword ? (
                              <EyeOff className="w-4 h-4 cursor-pointer pointer-events-auto" />
                            ) : (
                              <Eye className="w-4 h-4 cursor-pointer pointer-events-auto" />
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Base Role Assignment & Account Status */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 border-t pt-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">Base Role Assignment</label>
                    <select
                      value={selectedRole}
                      onChange={e => setSelectedRole(e.target.value)}
                      className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:ring-indigo-500 focus:border-indigo-500 bg-white"
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
                      className="h-4 w-4 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500"
                    />
                    <label htmlFor="isActive" className="text-sm font-medium text-gray-700 cursor-pointer">
                      Account Active
                    </label>
                  </div>
                </div>

                {/* 40 Granular CRUD Feature Flags (10 Modules) */}
                <div className="border-t pt-4">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3 gap-1">
                    <h3 className="text-sm font-bold text-gray-900 flex items-center gap-1.5">
                      <Key className="w-4 h-4 text-indigo-600" />
                      CRUD Permission Matrix (10 Modules × 4 Actions)
                    </h3>
                    <span className="text-[11px] text-gray-500 italic">
                      Create/Update/Delete auto-enables Read; unchecking Read revokes all.
                    </span>
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 bg-gray-50 p-4 rounded-lg border border-gray-200">
                  {MODULES.map(mod => {
                    const isRead = Boolean(permissions[`${mod.key}_read`]);
                    const isCreate = Boolean(permissions[`${mod.key}_create`]);
                    const isUpdate = Boolean(permissions[`${mod.key}_update`]);
                    const isDelete = Boolean(permissions[`${mod.key}_delete`]);
                    return (
                      <div key={mod.key} className="p-3 bg-white rounded-lg border border-gray-200 shadow-xs flex flex-col justify-between space-y-2">
                        <div>
                          <div className="text-xs font-bold text-gray-800">{mod.label}</div>
                          <div className="text-[11px] text-gray-500">{mod.desc}</div>
                        </div>
                        <div className="grid grid-cols-4 gap-1 pt-2 border-t border-gray-100 text-xs">
                          <label className="flex items-center gap-1 cursor-pointer font-medium text-gray-700 hover:text-indigo-600">
                            <input
                              type="checkbox"
                              checked={isRead}
                              onChange={() => handleToggleCrud(mod.key, 'read')}
                              className="h-3.5 w-3.5 text-indigo-600 rounded border-gray-300 focus:ring-indigo-500"
                            />
                            <span className="text-[11px]">Read</span>
                          </label>
                          <label className="flex items-center gap-1 cursor-pointer font-medium text-gray-700 hover:text-emerald-600">
                            <input
                              type="checkbox"
                              checked={isCreate}
                              onChange={() => handleToggleCrud(mod.key, 'create')}
                              className="h-3.5 w-3.5 text-emerald-600 rounded border-gray-300 focus:ring-emerald-500"
                            />
                            <span className="text-[11px]">Create</span>
                          </label>
                          <label className="flex items-center gap-1 cursor-pointer font-medium text-gray-700 hover:text-amber-600">
                            <input
                              type="checkbox"
                              checked={isUpdate}
                              onChange={() => handleToggleCrud(mod.key, 'update')}
                              className="h-3.5 w-3.5 text-amber-600 rounded border-gray-300 focus:ring-amber-500"
                            />
                            <span className="text-[11px]">Update</span>
                          </label>
                          <label className="flex items-center gap-1 cursor-pointer font-medium text-gray-700 hover:text-red-600">
                            <input
                              type="checkbox"
                              checked={isDelete}
                              onChange={() => handleToggleCrud(mod.key, 'delete')}
                              className="h-3.5 w-3.5 text-red-600 rounded border-gray-300 focus:ring-red-500"
                            />
                            <span className="text-[11px]">Delete</span>
                          </label>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Global Modules & Categorized Alerts */}
              <div className="border-t pt-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-3 gap-1">
                  <h3 className="text-sm font-bold text-gray-900 flex items-center gap-1.5">
                    <Globe className="w-4 h-4 text-blue-600" />
                    Global & Alert Permissions
                  </h3>
                  <span className="text-[11px] text-gray-500 italic">
                    Standalone modules & domain-specific notification channels
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Global Modules */}
                  <div className="bg-blue-50/40 p-3.5 rounded-lg border border-blue-200 flex flex-col justify-between">
                    <div>
                      <div className="text-xs font-bold text-blue-900 flex items-center gap-1.5 mb-1">
                        <Globe className="w-3.5 h-3.5 text-blue-600" />
                        Global Modules Access
                      </div>
                      <div className="text-[11px] text-gray-500 mb-3">
                        Isolated executive modules outside the 10-step workflow matrix
                      </div>
                    </div>
                    <div className="space-y-2">
                      {GLOBAL_MODULE_FLAGS.map(mod => (
                        <label
                          key={mod.key}
                          className="flex items-start gap-2.5 p-2 bg-white rounded border border-blue-100 hover:border-blue-300 cursor-pointer shadow-xs transition-colors"
                        >
                          <input
                            type="checkbox"
                            checked={Boolean(permissions[mod.key])}
                            onChange={() => handleToggleFlag(mod.key)}
                            className="mt-0.5 h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-semibold text-gray-800">{mod.label}</div>
                            <div className="text-[11px] text-gray-500">{mod.desc}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Categorized Alerts */}
                  <div className="bg-amber-50/40 p-3.5 rounded-lg border border-amber-200 flex flex-col justify-between">
                    <div>
                      <div className="text-xs font-bold text-amber-900 flex items-center gap-1.5 mb-1">
                        <Bell className="w-3.5 h-3.5 text-amber-600" />
                        Alert Subscriptions (4 Categories)
                      </div>
                      <div className="text-[11px] text-gray-500 mb-3">
                        Domain-targeted notifications (hidden if none selected)
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {ALERT_CATEGORIES.map(cat => (
                        <label
                          key={cat.key}
                          className="flex items-start gap-2 p-2 bg-white rounded border border-amber-100 hover:border-amber-300 cursor-pointer shadow-xs transition-colors"
                        >
                          <input
                            type="checkbox"
                            checked={Boolean(permissions[cat.key])}
                            onChange={() => handleToggleFlag(cat.key)}
                            className="mt-0.5 h-4 w-4 text-amber-600 rounded border-gray-300 focus:ring-amber-500"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-1">
                              <span className="text-xs font-semibold text-gray-800 leading-tight">{cat.label}</span>
                              <span className="text-[9px] px-1 py-0.5 bg-amber-100 text-amber-800 rounded font-medium shrink-0">
                                {cat.badge}
                              </span>
                            </div>
                            <div className="text-[10px] text-gray-500 mt-0.5 leading-snug">{cat.desc}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* 5 Plant Scope Access Flags - Only for Plant Incharge */}
              {selectedRole === 'PLANT_INCHARGE' && (
                <div className="border-t pt-4">
                  <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-1.5">
                    <Building className="w-4 h-4 text-emerald-600" />
                    Plant Access Scope (5 Plants)
                  </h3>
                  <div className="grid grid-cols-5 gap-3 bg-emerald-50/50 p-4 rounded-lg border border-emerald-200">
                    {PLANT_FLAGS.map(flag => (
                      <label key={flag.key} className="flex items-center gap-2 p-2 bg-white rounded border border-emerald-200 cursor-pointer hover:border-emerald-400">
                        <input
                          type="checkbox"
                          checked={Boolean(permissions[flag.key])}
                          onChange={() => handleTogglePlant(flag.key)}
                          className="h-4 w-4 text-emerald-600 rounded border-gray-300"
                        />
                        <span className="text-xs font-medium text-gray-800">{flag.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
              </div>

              {/* Fixed Footer */}
              <div className="flex justify-end gap-3 px-6 py-4 border-t border-ink-text/10 bg-vanilla-surface shrink-0">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-ink-text/15 text-ink-text/80 bg-white rounded-md text-sm font-medium hover:bg-vanilla-surface transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="inline-flex items-center gap-2 px-5 py-2 bg-burnt-orange text-white rounded-md text-sm font-semibold hover:bg-burnt-orange-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-xs"
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
      )}
    </div>
  );
}
