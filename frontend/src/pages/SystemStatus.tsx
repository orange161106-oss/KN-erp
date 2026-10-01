import { useEffect, useState } from 'react';
import { apiClient } from '../api/client';

type HealthStatus = {
  status: string;
};

export default function SystemStatus() {
  const [status, setStatus] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.get<HealthStatus>('/api/v1/health')
      .then(data => {
        setStatus(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  if (loading) return <div className="p-8 text-brand-steel">Loading system status...</div>;
  
  if (error) return (
    <div className="p-8">
      <h2 className="text-xl font-bold text-red-600 mb-2">System Error</h2>
      <p>The backend is unreachable. Error: {error}</p>
      <p className="text-sm text-gray-500 mt-4">Note: This error state is expected until Munees's backend is running.</p>
    </div>
  );

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold text-brand-navy mb-4">System Status</h2>
      <div className="bg-white p-4 rounded shadow border border-green-200">
        <p className="text-green-700 font-semibold">Backend Status: {status?.status}</p>
      </div>
    </div>
  );
}