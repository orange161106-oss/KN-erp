import { useState, useEffect } from 'react';
import type { UserResponse } from '../../api/users';
import { usersApi } from '../../api/users';
import { User, Shield, Edit, Plus, AlertCircle } from 'lucide-react';
import { TableSkeleton } from '../../components/ui/Skeleton';
import UserPermissionsModal, { ALL_CRUD_KEYS, PLANT_FLAGS, MODULES } from './UserPermissionsModal';

export { MODULES };

export default function UserManagement() {
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [editingUser, setEditingUser] = useState<UserResponse | null>(null);

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
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (user: UserResponse) => {
    setEditingUser(user);
    setIsModalOpen(true);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-center bg-white p-6 rounded-xl shadow-md border border-erp-dark-vanilla/30 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-erp-chocolate flex items-center gap-2">
            <Shield className="w-7 h-7 text-erp-orange" />
            Users & Permissions
          </h1>
          <p className="text-sm text-erp-chocolate/70 mt-1">
            Manage employee accounts, role assignments, plant access, and granular module permissions.
          </p>
        </div>
        <button
          onClick={handleOpenCreateModal}
          className="flex items-center gap-2 bg-erp-orange hover:bg-erp-tenne text-white px-4 py-2 rounded-lg font-semibold text-sm transition-all shadow-xs"
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
      <UserPermissionsModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={fetchUsers}
        editingUser={editingUser}
      />
    </div>
  );
}
