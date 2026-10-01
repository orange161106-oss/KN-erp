import { useState } from 'react';

export type Role = 'ADMIN' | 'PLANNER' | 'PLANT_INCHARGE' | 'STORE' | 'PURCHASE' | null;

export default function Login({ onLogin }: { onLogin: (role: Role) => void }) {
  const [selectedRole, setSelectedRole] = useState<Role>('ADMIN');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onLogin(selectedRole);
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-brand-offwhite">
      <div className="w-full max-w-md bg-white p-8 rounded-lg shadow-md border border-gray-200">
        <h1 className="text-2xl font-bold text-brand-navy text-center mb-6">KN Consumable ERP</h1>
        <p className="text-sm text-gray-500 text-center mb-6">M1.4 Persona Login (Mock Auth)</p>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-brand-charcoal mb-1">Select Persona</label>
            <select 
              value={selectedRole || 'ADMIN'}
              onChange={(e) => setSelectedRole(e.target.value as Role)}
              className="w-full border border-gray-300 rounded p-2 text-brand-charcoal focus:outline-none focus:border-brand-steel"
            >
              <option value="ADMIN">System Admin</option>
              <option value="PLANNER">Planner (Yathish)</option>
              <option value="PLANT_INCHARGE">Plant Incharge (Keerthi)</option>
              <option value="STORE">Store Manager (Munees)</option>
              <option value="PURCHASE">Purchase Dept</option>
            </select>
          </div>
          <button 
            type="submit" 
            className="w-full bg-brand-navy text-white font-semibold py-2 px-4 rounded hover:bg-brand-steel transition-colors"
          >
            Enter System
          </button>
        </form>
      </div>
    </div>
  );
}