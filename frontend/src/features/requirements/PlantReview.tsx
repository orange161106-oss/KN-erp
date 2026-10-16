import React from 'react';
import PlantWorkflow from '../plant_workflow/PlantWorkflow';
import { useAuth } from '../auth/context';

export interface PlantReviewProps {
  currentUserId?: string;
}

export const PlantReview: React.FC<PlantReviewProps> = ({ currentUserId }) => {
  const { user } = useAuth();
  return <PlantWorkflow currentUserId={currentUserId || user?.id || ''} />;
};

export default PlantReview;
