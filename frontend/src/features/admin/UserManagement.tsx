import React, { useState, useEffect } from 'react';
import type { UserResponse, UserCreate, UserUpdate } from '../../api/users';
import { usersApi } from '../../api/users';
import { User, Shield, Edit, Plus, X, Building, Key, AlertCircle, Eye, EyeOff } from 'lucide-react';
import { TableSkeleton } from '../../components/ui/Skeleton';

const BASE_ROLES = [
  { code: 'PLANNER', label: 'Planner' },
  { code: 'PLANT_INCHARGE', label: 'Plant Incharge' },
  { code: 'PURCHASE', label: 'Purchase' },
  { code: 'APPROVER', label: 'Approver' },
  { code: 'STORE', label: 'Store' },
  { code: 'MANAGEMENT', label: 'Management' },
  { code: 'ADMIN', label: 'Admin' },
];

const FEATURE_FLAGS: { key: keyof UserCreate; label: string; desc: string }[] = [
  { key: 'can_view_master_data', label: 'View Master Data', desc: 'Can view items, customers, suppliers' },
  { key: 'can_edit_master_data', label: 'Edit Master Data', desc: 'Can modify items, customers, suppliers' },
  { key: 'can_view_planning', label: 'View Planning Workspace', desc: 'Access PRD orders & requirement planning' },
  { key: 'can_run_calculations', label: 'Run Requirement Calculations', desc: 'Execute requirement engines' },
  { key: 'can_confirm_demand', label: 'Confirm Plant Demand', desc: 'Confirm plant-wise requirements' },
  { key: 'can_approve_extra_demand', label: 'Approve Extra Demand', desc: 'Approve additional/override requests' },
  { key: 'can_create_po', label: 'Create Purchase Orders', desc: 'Generate draft POs' },
  { key: 'can_approve_po', label: 'Approve Purchase Orders', desc: 'Approve issued POs' },
  { key: 'can_upload_grn', label: 'Upload GRN', desc: 'Import goods receipts from the existing ERP' },
  { key: 'can_view_reports', label: 'View Analytical Reports', desc: 'Access reports & executive dashboard' },
  { key: 'can_access_masters', label: '1. Masters', desc: 'View units, consumables, and suppliers masters' },
  { key: 'can_access_production_mappings', label: '2. Production Mappings', desc: 'View process and equipment mappings' },
  { key: 'can_access_consumption_norms', label: '3. Consumption Norms', desc: 'View consumption norms and rules' },
  { key: 'can_access_prd_planning', label: '4. PRD / Planning', desc: 'View PRD planning workspace' },
  { key: 'can_access_requirements', label: '5. Requirements', desc: 'View consumable requirements workspace' },
  { key: 'can_access_plant_workflow', label: '6. Plant Workflow', desc: 'View plant confirmation workflow' },
  { key: 'can_access_inventory', label: '7. Inventory', desc: 'View inventory management' },
  { key: 'can_access_purchase', label: '8. Purchase', desc: 'View purchase requests & planning' },
  { key: 'can_access_purchase_orders', label: '9. Purchase Orders', desc: 'View purchase orders management' },
  { key: 'can_access_goods_receipts', label: '10. Goods Receipts', desc: 'View goods receipt notes (GRN)' },
];

const PLANT_FLAGS: { key: keyof UserCreate; label: string }[] = [
  { key: 'can_access_plant_1', label: 'Plant I' },
  { key: 'can_access_plant_2', label: 'Plant II' },
  { key: 'can_access_plant_3', label: 'Plant III' },
  { key: 'can_access_plant_4', label: 'Plant IV' },
  { key: 'can_access_plant_5', label: 'Plant V' },
];

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
  const [permissions, setPermissions] = useState<Record<string, boolean>>({
    can_view_master_data: false,
    can_edit_master_data: false,
    can_view_planning: false,
    can_run_calculations: false,
    can_confirm_demand: false,
    can_approve_extra_demand: false,
    can_create_po: false,
    can_approve_po: false,
    can_upload_grn: false,
    can_view_reports: false,
    can_access_masters: false,
    can_access_production_mappings: false,
    can_access_consumption_norms: false,
    can_access_prd_planning: false,
    can_access_requirements: false,
    can_access_plant_workflow: false,
    can_access_inventory: false,
    can_access_purchase: false,
    can_access_purchase_orders: false,
    can_access_goods_receipts: false,
    can_access_plant_1: false,
    can_access_plant_2: false,
    can_access_plant_3: false,
    can_access_plant_4: false,
    can_access_plant_5: false,
  });

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
    setPermissions({
      can_view_master_data: false,
      can_edit_master_data: false,
      can_view_planning: false,
      can_run_calculations: false,
      can_confirm_demand: false,
      can_approve_extra_demand: false,
      can_create_po: false,
      can_approve_po: false,
      can_upload_grn: false,
      can_view_reports: false,
      can_access_masters: false,
      can_access_production_mappings: false,
      can_access_consumption_norms: false,
      can_access_prd_planning: false,
      can_access_requirements: false,
      can_access_plant_workflow: false,
      can_access_inventory: false,
      can_access_purchase: false,
      can_access_purchase_orders: false,
      can_access_goods_receipts: false,
      can_access_plant_1: false,
      can_access_plant_2: false,
      can_access_plant_3: false,
      can_access_plant_4: false,
      can_access_plant_5: false,
    });
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

    const userPerms: Record<string, boolean> = {};
    [...FEATURE_FLAGS, ...PLANT_FLAGS].forEach(flag => {
      userPerms[flag.key] = Boolean(user[flag.key as keyof UserResponse]);
    });
    setPermissions(userPerms);
    setIsModalOpen(true);
  };

  const handleToggleFlag = (key: string) => {
    setPermissions(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const finalPermissions = { ...permissions };


      if (editingUser) {
        const updatePayload: UserUpdate = {
          full_name: fullName || null,
          employee_id: employeeId || null,
          roles: editingUser.roles[0] === selectedRole ? editingUser.roles : [selectedRole, ...editingUser.roles.slice(1).filter(r => r !== selectedRole)],
          is_active: isActive,
          ...finalPermissions,
        };
        if (password) updatePayload.password = password;
        await usersApi.updateUser(editingUser.id, updatePayload);
      } else {
        const createPayload: UserCreate = {
          username,
          password,
          is_active: isActive,
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
            Provision employee accounts, workflow visibility, action permissions, and plant access.
          </p>
        </div>
        <button
          onClick={handleOpenCreateModal}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md font-medium text-sm transition-colors"
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
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
          <table className="w-full text-left text-sm text-gray-600">
            <thead className="bg-gray-50 text-gray-700 border-b border-gray-200 uppercase text-xs font-semibold">
              <tr>
                <th className="py-3 px-4">Employee / Username</th>
                <th className="py-3 px-4">Base Role</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Plant Access</th>
                <th className="py-3 px-4">Active Feature Flags</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {users.filter(u => !u.is_super_admin).length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-400">No users found.</td>
                </tr>
              ) : (
              users.filter(u => !u.is_super_admin).map(u => {
                const activeFeatureCount = FEATURE_FLAGS.filter(f => Boolean(u[f.key as keyof UserResponse])).length;
                const activePlants = PLANT_FLAGS.filter(p => Boolean(u[p.key as keyof UserResponse])).map(p => p.label);

                return (
                  <tr key={u.id} className="hover:bg-gray-50 transition-colors">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-gray-400 flex-shrink-0" />
                        <div>
                          <div className="font-medium text-gray-900 flex items-center gap-1.5">
                            {u.username}
                            {u.is_super_admin && (
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
                      <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-1 rounded border border-indigo-100">
                        {activeFeatureCount} / {FEATURE_FLAGS.length} Enabled
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">
                      {u.is_super_admin ? (
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
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-white rounded-lg max-w-3xl w-full p-6 shadow-xl space-y-6 my-8">
            <div className="flex justify-between items-center border-b pb-4">
              <h2 className="text-lg font-bold text-gray-900">
                {editingUser ? `Edit User & Permissions: ${editingUser.username}` : 'Provision New User'}
              </h2>
              <button onClick={() => setIsModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} autoComplete="off" className="space-y-6">
              {/* Employee Information */}
              <div className="grid grid-cols-2 gap-4">
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
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Username</label>
                  <input
                    type="text"
                    required
                    autoComplete="new-password"
                    disabled={Boolean(editingUser?.is_super_admin)}
                    value={username}
                    onChange={e => setUsername(e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100"
                    placeholder="e.g. store_user"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    {editingUser ? 'Password (Leave blank to keep existing)' : 'Password'}
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

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">Base Role Assignment</label>
                  <select
                    value={selectedRole}
                    onChange={e => setSelectedRole(e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                  >
                    {BASE_ROLES.map(r => (
                      <option key={r.code} value={r.code}>{r.label} ({r.code})</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2 pt-6">
                  <input
                    type="checkbox"
                    id="isActive"
                    checked={isActive}
                    onChange={e => setIsActive(e.target.checked)}
                    className="h-4 w-4 text-indigo-600 rounded border-gray-300"
                  />
                  <label htmlFor="isActive" className="text-sm font-medium text-gray-700">Account Active</label>
                </div>
              </div>

              {/* Action permissions and workflow visibility */}
              <div className="border-t pt-4">
                <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-1.5">
                  <Key className="w-4 h-4 text-indigo-600" />
                  Action Permissions & Workflow Visibility
                </h3>
                <div className="grid grid-cols-2 gap-3 bg-gray-50 p-4 rounded-lg border border-gray-200">
                  {FEATURE_FLAGS.map(flag => (
                    <label key={flag.key} className="flex items-start gap-2.5 p-2 bg-white rounded border border-gray-200 cursor-pointer hover:border-indigo-300 transition-colors">
                      <input
                        type="checkbox"
                        checked={Boolean(permissions[flag.key])}
                        onChange={() => handleToggleFlag(flag.key)}
                        className="mt-0.5 h-4 w-4 text-indigo-600 rounded border-gray-300"
                      />
                      <div>
                        <div className="text-xs font-semibold text-gray-800">{flag.label}</div>
                        <div className="text-[11px] text-gray-500">{flag.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* Plant scope is independent of the employee's role label. */}
              {(
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
                          onChange={() => handleToggleFlag(flag.key)}
                          className="h-4 w-4 text-emerald-600 rounded border-gray-300"
                        />
                        <span className="text-xs font-medium text-gray-800">{flag.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-3 border-t pt-4">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-gray-300 text-gray-700 rounded-md text-sm font-medium hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
