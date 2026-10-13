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

  const mockRunResponse: reqApi.AggregationRunResponse = {
    month: 10,
    year: 2026,
    total_approved_plans: 3,
    total_aggregated_consumables: 2,
    records: mockAggregatedRecords,
  };

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

  describe('Task 3: UI Layout & Controls', () => {
    it('removes manual UUID input from main view and provides floating Control Bar with Month, Year, and Action buttons', async () => {
      vi.spyOn(reqApi, 'fetchAggregatedRequirements').mockResolvedValue(mockAggregatedRecords);

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

      // Verify Action Buttons
      expect(screen.getByRole('button', { name: /Load Aggregation/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Run\/Refresh Aggregation Engine/i })).toBeInTheDocument();
    });

    it('clicking "Load Aggregation" triggers GET request for selected month and year', async () => {
      const fetchSpy = vi.spyOn(reqApi, 'fetchAggregatedRequirements').mockResolvedValue(mockAggregatedRecords);

      renderPlantWorkflow();

      await screen.findByText('Plant Review & Aggregation');
      const loadBtn = screen.getByRole('button', { name: /Load Aggregation/i });

      await userEvent.click(loadBtn);

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });
    });

    it('clicking "Run/Refresh Aggregation Engine" triggers calculation and auto-reloads grid', async () => {
      const fetchSpy = vi.spyOn(reqApi, 'fetchAggregatedRequirements').mockResolvedValue(mockAggregatedRecords);
      const runSpy = vi.spyOn(reqApi, 'runAggregation').mockResolvedValue(mockRunResponse);

      renderPlantWorkflow();

      await screen.findByText('Plant Review & Aggregation');
      const runBtn = screen.getByRole('button', { name: /Run\/Refresh Aggregation Engine/i });

      await userEvent.click(runBtn);

      await waitFor(() => {
        expect(runSpy).toHaveBeenCalled();
      });

      expect(await screen.findByText(/Aggregation complete! Consolidated 2 items across 3 approved plans/)).toBeInTheDocument();
      expect(fetchSpy).toHaveBeenCalled();
    });
  });

  describe('Task 4: Aggregated Data Grid', () => {
    it('renders data table under Final Requirements tab with Item Code, Description, Part No, Unit, Gross QTY, and Net Purchase QTY', async () => {
      vi.spyOn(reqApi, 'fetchAggregatedRequirements').mockResolvedValue(mockAggregatedRecords);

      renderPlantWorkflow();

      // Final Requirements is default active tab
      const headings = await screen.findAllByText('Final Requirements (Handoff)');
      expect(headings.length).toBeGreaterThan(0);

      // Verify Table Columns
      expect(screen.getByText('S.No')).toBeInTheDocument();
      expect(screen.getByText('Item Code')).toBeInTheDocument();
      expect(screen.getByText('Item Description')).toBeInTheDocument();
      expect(screen.getByText('Part No')).toBeInTheDocument();
      expect(screen.getByText('Unit')).toBeInTheDocument();
      expect(screen.getByText('Total Gross QTY (Sum across plants)')).toBeInTheDocument();
      expect(screen.getByText('Net Purchase QTY')).toBeInTheDocument();

      // Verify Records
      expect(screen.getByText('WLD-WIRE-01')).toBeInTheDocument();
      expect(screen.getByText('MIG Welding Wire 1.2mm')).toBeInTheDocument();
      expect(screen.getByText('PN-WLD-12')).toBeInTheDocument();
      expect(screen.getByText('Kg')).toBeInTheDocument();
      expect(screen.getByText('4,500')).toBeInTheDocument();
      expect(screen.getByText('4,200')).toBeInTheDocument();

      expect(screen.getByText('PNT-THIN-01')).toBeInTheDocument();
      expect(screen.getByText('Industrial Paint Thinner')).toBeInTheDocument();
      expect(screen.getByText('PN-THIN-01')).toBeInTheDocument();
      expect(screen.getByText('Ltr')).toBeInTheDocument();
      expect(screen.getByText('1,250')).toBeInTheDocument();
      expect(screen.getByText('1,100')).toBeInTheDocument();

      // Verify Summary Footer
      expect(screen.getByText(/5,750/)).toBeInTheDocument(); // 4500 + 1250
      expect(screen.getByText(/5,300/)).toBeInTheDocument(); // 4200 + 1100
    });

    it('filters rows via search input', async () => {
      vi.spyOn(reqApi, 'fetchAggregatedRequirements').mockResolvedValue(mockAggregatedRecords);

      renderPlantWorkflow();

      await screen.findByText('MIG Welding Wire 1.2mm');

      const searchInput = screen.getByPlaceholderText(/Search code, description, part no/i);
      await userEvent.type(searchInput, 'Thinner');

      expect(screen.queryByText('MIG Welding Wire 1.2mm')).not.toBeInTheDocument();
      expect(screen.getByText('Industrial Paint Thinner')).toBeInTheDocument();
    });

    it('displays friendly empty state when no aggregation exists', async () => {
      vi.spyOn(reqApi, 'fetchAggregatedRequirements').mockResolvedValue([]);

      renderPlantWorkflow();

      expect(await screen.findByText('No Aggregated Requirements Found')).toBeInTheDocument();
      expect(screen.getByText(/Click "Run\/Refresh Aggregation Engine" to group approved monthly plans/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Run Aggregation Engine Now/i })).toBeInTheDocument();
    });
  });
});
