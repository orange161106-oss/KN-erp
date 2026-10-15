import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import PlantWorkflow from '../features/plant_workflow/PlantWorkflow';
import * as reqApi from '../features/requirements/api';

describe('Plant Review UI & Aggregation Dashboard', () => {
  const mockAggregatedRecords: reqApi.AggregatedRequirementRecord[] = [
    {
      id: 'agg-1',
      month: 10,
      year: 2026,
      consumable_id: 'con-1',
      total_gross_qty: 4500,
      net_purchase_qty: 4200,
      item_id: 'WLD-WIRE-01',
      item_code: 'WLD-WIRE-01',
      item_description: 'MIG Welding Wire 1.2mm',
      consumable_name: 'MIG Welding Wire 1.2mm',
      part_no: 'PN-WLD-12',
      unit: 'Kg',
    },
    {
      id: 'agg-2',
      month: 10,
      year: 2026,
      consumable_id: 'con-2',
      total_gross_qty: 1250,
      net_purchase_qty: 1100,
      item_id: 'PNT-THIN-01',
      item_code: 'PNT-THIN-01',
      item_description: 'Industrial Paint Thinner',
      consumable_name: 'Industrial Paint Thinner',
      part_no: 'PN-THIN-01',
      unit: 'Ltr',
    },
  ];

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderPlantWorkflow = (userRole = 'PLANNER') => {
    return render(
      <AuthContext.Provider
        value={{
          user: {
            id: 'planner-uuid',
            username: 'lead_planner',
            roles: [userRole],
            permissions: ['plant_workflow.read', 'requirements.read', 'requirements.calculate'],
          },
          login: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <PlantWorkflow currentUserId="planner-uuid" />
      </AuthContext.Provider>
    );
  };

  describe('Task 2: API Wiring', () => {
    it('fetchAggregatedRequirements queries GET /api/v1/requirements/aggregate/{month}/{year}', async () => {
      const getSpy = vi.spyOn(reqApi.requirementsClient, 'get').mockResolvedValue({
        data: mockAggregatedRecords,
      });

      const data = await reqApi.fetchAggregatedRequirements(10, 2026);
      expect(getSpy).toHaveBeenCalledWith('/api/v1/requirements/aggregate/10/2026');
      expect(data).toEqual(mockAggregatedRecords);
    });
  });

  describe('Task 3: Compact 5-Plant Layout & Controls', () => {
    it('renders ONLY the 5 plant tabs and clean month labels without numeric prefixes', async () => {
      vi.spyOn(reqApi, 'fetchPlans').mockResolvedValue([]);

      renderPlantWorkflow();

      // Verify Title
      expect(await screen.findByText('Plant Review & Aggregation')).toBeInTheDocument();

      // Verify manual planning version UUID input is NOT on main view
      expect(screen.queryByPlaceholderText('Paste planning version UUID…')).not.toBeInTheDocument();

      // Verify Month and Year Selectors
      const monthSelect = screen.getByLabelText('Month:');
      const yearSelect = screen.getByLabelText('Year:');
      expect(monthSelect).toBeInTheDocument();
      expect(yearSelect).toBeInTheDocument();

      // Verify Clean Month Dropdown Labels (January, February... no "1 - ")
      expect(screen.getByRole('option', { name: 'January' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'October' })).toBeInTheDocument();
      expect(screen.queryByRole('option', { name: '10 - October' })).not.toBeInTheDocument();

      // Verify ONLY 5 plant tabs are present (No Final Requirements, Confirmations, or Additional Requirements)
      expect(screen.getByRole('button', { name: 'Plant I' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Plant II' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Plant III' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Plant IV' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Plant V' })).toBeInTheDocument();

      expect(screen.queryByRole('button', { name: /Final Requirements/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Confirmations/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Additional Requirements/i })).not.toBeInTheDocument();

      // Verify Old Aggregation buttons and badge are removed
      expect(screen.queryByRole('button', { name: /Load Aggregation/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Run\/Refresh Aggregation Engine/i })).not.toBeInTheDocument();
      expect(screen.queryByText('Phase 4 Workspace')).not.toBeInTheDocument();
    });

    it('switches between plant tabs and renders always-visible table headers even when empty', async () => {
      const mockPlant1Plan: reqApi.MonthlyRequirementPlan = {
        id: 'plan-p1',
        plant_id: 'PLANT_I',
        month: 10,
        year: 2026,
        status: 'DRAFT',
        line_items: [],
      };
      vi.spyOn(reqApi, 'fetchPlans').mockResolvedValue([mockPlant1Plan]);

      renderPlantWorkflow();

      expect(await screen.findByText('Plant Review & Aggregation')).toBeInTheDocument();

      // Table headers are clearly visible
      expect(screen.getByText('S.No.')).toBeInTheDocument();
      expect(screen.getByText('Item Id.')).toBeInTheDocument();
      expect(screen.getByText('Item Description')).toBeInTheDocument();
      expect(screen.getByText('Part No.')).toBeInTheDocument();
      expect(screen.getByText('Unit')).toBeInTheDocument();
      expect(screen.getByText('QTY')).toBeInTheDocument();
      expect(screen.getByText('Actions')).toBeInTheDocument();

      // Clean empty state message inside tbody
      expect(
        screen.getByText("No items recorded for this period yet. Use '+ Add Item' or 'Upload Excel/CSV' above.")
      ).toBeInTheDocument();

      // Verify action readiness
      expect(screen.getAllByRole('button', { name: '+ Add Item' }).length).toBeGreaterThan(0);
      expect(screen.getByRole('button', { name: /Upload Excel\/CSV/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Approve Plant I' })).toBeInTheDocument();
    });

    it('renders line items and allows approving plant plan directly', async () => {
      const mockPlant1Plan: reqApi.MonthlyRequirementPlan = {
        id: 'plan-p1',
        plant_id: 'PLANT_I',
        month: 10,
        year: 2026,
        status: 'DRAFT',
        line_items: [
          {
            id: 'item-1',
            plan_id: 'plan-p1',
            consumable_id: 'c1',
            item_id: 'CON-001',
            item_code: 'CON-001',
            consumable_name: 'Hydraulic Oil 68',
            part_no: 'OIL-68',
            unit: 'L',
            requested_qty: 250,
          },
        ],
      };
      vi.spyOn(reqApi, 'fetchPlans').mockResolvedValue([mockPlant1Plan]);
      const approveSpy = vi.spyOn(reqApi, 'approvePlan').mockResolvedValue({
        ...mockPlant1Plan,
        status: 'APPROVED',
      });

      renderPlantWorkflow();

      expect(await screen.findByText('Hydraulic Oil 68')).toBeInTheDocument();
      expect(screen.getByText('CON-001')).toBeInTheDocument();
      expect(screen.getByText('OIL-68')).toBeInTheDocument();
      expect(screen.getAllByText('250').length).toBeGreaterThan(0);

      const approveBtn = screen.getByRole('button', { name: 'Approve Plant I' });
      await userEvent.click(approveBtn);

      await waitFor(() => {
        expect(approveSpy).toHaveBeenCalledWith('plan-p1');
      });
    });
  });
});
