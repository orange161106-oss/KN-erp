import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthContext } from '../features/auth/context';
import RequirementWorkspace from '../features/requirements/RequirementWorkspace';
import * as api from '../features/requirements/api';

describe('Phase 3: Monthly Requirement Planner Frontend', () => {
  const mockPlanDraft = {
    id: 'plan-101',
    plant_id: 'PLANT_I',
    month: 10,
    year: 2026,
    status: 'DRAFT',
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
    line_items: [
      {
        id: 'item-1',
        plan_id: 'plan-101',
        consumable_id: 'con-1',
        requested_qty: 1500,
        rate: 450,
        receipt_qty: 500,
        order_value: 675000,
        receipt_value: 225000,
        item_id: 'WLD-WIRE-01',
        consumable_name: 'MIG Welding Wire 1.2mm',
        unit: 'Kg',
        description: 'MIG Welding Wire 1.2mm',
      },
      {
        id: 'item-2',
        plan_id: 'plan-101',
        consumable_id: 'con-2',
        requested_qty: 350,
        item_id: 'PNT-THIN-01',
        consumable_name: 'Industrial Thinner',
        unit: 'Ltr',
        description: 'Industrial Thinner',
      },
    ],
  };

  const mockPlanSubmitted = {
    ...mockPlanDraft,
    status: 'SUBMITTED',
  };

  const mockPlanApproved = {
    ...mockPlanDraft,
    status: 'APPROVED',
  };

  const mockAggregationResponse = {
    month: 10,
    year: 2026,
    total_approved_plans: 3,
    total_aggregated_consumables: 2,
    records: [
      {
        id: 'agg-1',
        month: 10,
        year: 2026,
        consumable_id: 'con-1',
        total_gross_qty: 4500,
        net_purchase_qty: 4200,
        item_id: 'WLD-WIRE-01',
        consumable_name: 'MIG Welding Wire 1.2mm',
      },
      {
        id: 'agg-2',
        month: 10,
        year: 2026,
        consumable_id: 'con-2',
        total_gross_qty: 1050,
        net_purchase_qty: 900,
        item_id: 'PNT-THIN-01',
        consumable_name: 'Industrial Thinner',
      },
    ],
  };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderWithUser = (user: any) => {
    return render(
      <AuthContext.Provider
        value={{
          user,
          login: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <RequirementWorkspace />
      </AuthContext.Provider>
    );
  };

  describe('Task 1: API Client Wiring', () => {
    it('executes API client calls with expected endpoints and methods', async () => {
      const getSpy = vi.spyOn(api.requirementsClient, 'get').mockResolvedValue({ data: [mockPlanDraft] });
      const postSpy = vi.spyOn(api.requirementsClient, 'post').mockResolvedValue({ data: mockPlanDraft });
      const patchSpy = vi.spyOn(api.requirementsClient, 'patch').mockResolvedValue({ data: mockPlanSubmitted });

      // fetchPlans
      const plans = await api.fetchPlans();
      expect(getSpy).toHaveBeenCalledWith('/api/v1/requirements/plans');
      expect(plans).toEqual([mockPlanDraft]);

      // createPlan
      const created = await api.createPlan('PLANT_I', 10, 2026);
      expect(postSpy).toHaveBeenCalledWith('/api/v1/requirements/plans', {
        plant_id: 'PLANT_I',
        month: 10,
        year: 2026,
      });
      expect(created).toEqual(mockPlanDraft);

      // submitPlan
      const submitted = await api.submitPlan('plan-101');
      expect(patchSpy).toHaveBeenCalledWith('/api/v1/requirements/plans/plan-101/submit');
      expect(submitted).toEqual(mockPlanSubmitted);

      // approvePlan
      await api.approvePlan('plan-101');
      expect(patchSpy).toHaveBeenCalledWith('/api/v1/requirements/plans/plan-101/approve');

      // runAggregation
      postSpy.mockResolvedValueOnce({ data: mockAggregationResponse });
      const agg = await api.runAggregation(10, 2026);
      expect(postSpy).toHaveBeenCalledWith('/api/v1/requirements/aggregate/10/2026');
      expect(agg.total_aggregated_consumables).toBe(2);

      // bulkUploadItems
      const file = new File(['item_id,qty\nWLD-WIRE-01,100'], 'plan.csv', { type: 'text/csv' });
      postSpy.mockResolvedValueOnce({
        data: { total_rows: 1, upserted: 1, errors: [], items: [] },
      });
      const uploadRes = await api.bulkUploadItems('plan-101', file);
      expect(uploadRes.upserted).toBe(1);
      expect(postSpy).toHaveBeenCalledWith(
        '/api/v1/requirements/plans/plan-101/items/bulk',
        expect.any(FormData),
        expect.objectContaining({
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      );

      // uploadGRNFile
      const grnFile = new File(['grn_no,item_code,qty,rate\nGRN-01,WLD-WIRE-01,50,450'], 'grn.csv', { type: 'text/csv' });
      postSpy.mockResolvedValueOnce({
        data: {
          grn_no: 'GRN-01',
          total_items: 1,
          total_receipt_qty: 50,
          total_receipt_value: 22500,
          consumables_updated: 1,
          requirement_lines_updated: 1,
          items: [],
        },
      });
      const grnRes = await api.uploadGRNFile(grnFile, 10, 2026);
      expect(grnRes.grn_no).toBe('GRN-01');
      expect(postSpy).toHaveBeenCalledWith(
        '/api/v1/requirements/grn/upload',
        expect.any(FormData),
        expect.objectContaining({
          params: { month: 10, year: 2026 },
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      );
    });
  });

  describe('Task 2: Layout & Control Bar (RBAC Plant Lock)', () => {
    it('locks plant selector to assigned_plant for standard plant incharge', async () => {
      vi.spyOn(api, 'fetchPlans').mockResolvedValue([mockPlanDraft]);

      const standardUser = {
        id: 'user-incharge',
        username: 'incharge1',
        roles: ['USER'],
        assigned_plant: 'PLANT_I',
        permissions: ['requirements.read'],
      };

      renderWithUser(standardUser);

      expect(await screen.findByText('Monthly Requirement Planner')).toBeInTheDocument();
      // Dropdown should not be editable select, but locked display
      expect(screen.queryByRole('combobox', { name: /Plant:/i })).not.toBeInTheDocument();
      expect(screen.getByText('Plant 1 (Main Facility)')).toBeInTheDocument();
      expect(screen.getByTitle('Locked to your assigned plant')).toBeInTheDocument();
    });

    it('allows Admin/Planner to switch across all plants', async () => {
      vi.spyOn(api, 'fetchPlans').mockResolvedValue([mockPlanDraft]);

      const adminUser = {
        id: 'admin-1',
        username: 'superadmin',
        is_super_admin: true,
        roles: ['ADMIN'],
        permissions: ['*'],
      };

      renderWithUser(adminUser);

      expect(await screen.findByText('Monthly Requirement Planner')).toBeInTheDocument();
      const plantSelect = screen.getByLabelText('Plant:');
      expect(plantSelect).toBeInTheDocument();
      expect(plantSelect.tagName).toBe('SELECT');

      // Check all default plants are available options
      expect(screen.getByText('Plant 2 (Fabrication)')).toBeInTheDocument();
      expect(screen.getByText('Plant 3 (Assembly)')).toBeInTheDocument();
    });
  });

  describe('Task 3: Excel-like Grid & Bulk Ingestion', () => {
    it('renders data table with S.No, Item Code, Description, Unit, Requested QTY and search filter', async () => {
      vi.spyOn(api, 'fetchPlans').mockResolvedValue([mockPlanDraft]);

      const plannerUser = {
        id: 'planner-1',
        username: 'planner',
        roles: ['PLANNER'],
        permissions: ['requirements.read'],
      };

      renderWithUser(plannerUser);

      // Verify table headers
      expect(await screen.findByText('Requirement Line Items')).toBeInTheDocument();
      expect(screen.getByText('S.No')).toBeInTheDocument();
      expect(screen.getByText('Item Code')).toBeInTheDocument();
      expect(screen.getByText('Item Description')).toBeInTheDocument();
      expect(screen.getByText('Unit')).toBeInTheDocument();
      expect(screen.getByText('Requested QTY')).toBeInTheDocument();

      // Verify row items
      expect(screen.getByText('WLD-WIRE-01')).toBeInTheDocument();
      expect(screen.getByText('MIG Welding Wire 1.2mm')).toBeInTheDocument();
      expect(screen.getByText('1,500')).toBeInTheDocument();

      expect(screen.getByText('PNT-THIN-01')).toBeInTheDocument();
      expect(screen.getByText('Industrial Thinner')).toBeInTheDocument();
      expect(screen.getByText('350')).toBeInTheDocument();

      // Search filter
      const searchInput = screen.getByPlaceholderText('Search code or description...');
      await userEvent.type(searchInput, 'Thinner');

      expect(screen.queryByText('MIG Welding Wire 1.2mm')).not.toBeInTheDocument();
      expect(screen.getByText('Industrial Thinner')).toBeInTheDocument();
    });

    it('triggers bulk upload when a file is selected', async () => {
      vi.spyOn(api, 'fetchPlans').mockResolvedValue([mockPlanDraft]);
      const uploadSpy = vi.spyOn(api, 'bulkUploadItems').mockResolvedValue({
        total_rows: 5,
        upserted: 5,
        errors: [],
        items: [],
      });

      const plannerUser = {
        id: 'planner-1',
        username: 'planner',
        roles: ['PLANNER'],
        permissions: ['requirements.read'],
      };

      renderWithUser(plannerUser);

      await screen.findByText('Requirement Line Items');

      const fileInput = screen.getByTestId('plan-file-input');
      const testFile = new File(['item_id,qty\nWLD-WIRE-01,1500'], 'monthly_plan.csv', { type: 'text/csv' });

      await userEvent.upload(fileInput, testFile);

      await waitFor(() => {
        expect(uploadSpy).toHaveBeenCalledWith('plan-101', testFile);
      });
      expect(await screen.findByText(/Successfully uploaded and parsed 5 items/)).toBeInTheDocument();
    });

    it('renders GRN rate & receipt columns and opens GRN upload modal', async () => {
      vi.spyOn(api, 'fetchPlans').mockResolvedValue([mockPlanDraft]);

      const adminUser = {
        id: 'admin-1',
        username: 'admin',
        roles: ['ADMIN'],
        permissions: ['*'],
      };

      renderWithUser(adminUser);

      expect(await screen.findByText('Requirement Line Items')).toBeInTheDocument();
      await screen.findByText('WLD-WIRE-01');

      // Check GRN columns
      expect(screen.getByText('Latest Rate (₹)')).toBeInTheDocument();
      expect(screen.getByText('Receipt QTY')).toBeInTheDocument();
      expect(screen.getByText('Order Value (₹)')).toBeInTheDocument();
      expect(screen.getByText('Receipt Value (₹)')).toBeInTheDocument();

      // Check row values for item-1
      expect(screen.getByText(/450\.00/)).toBeInTheDocument();
      expect(screen.getByText('500')).toBeInTheDocument();
      expect(screen.getAllByText(/6,?75,?000/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/2,?25,?000/).length).toBeGreaterThan(0);

      // Verify Upload GRN is removed from Plant tab toolbar
      expect(screen.queryByRole('button', { name: /Upload GRN/i })).not.toBeInTheDocument();
    });
  });

  describe('Task 4: State Machine Action Panel & Aggregation', () => {
    it('shows Submit button for Plant Incharge on DRAFT plan and transitions state', async () => {
      vi.spyOn(api, 'fetchPlans').mockResolvedValue([mockPlanDraft]);
      const submitSpy = vi.spyOn(api, 'submitPlan').mockResolvedValue({
        ...mockPlanDraft,
        status: 'SUBMITTED',
      });

      const plantUser = {
        id: 'incharge-1',
        username: 'plant_lead',
        roles: ['USER'],
        assigned_plant: 'PLANT_I',
        permissions: ['requirements.read'],
      };

      renderWithUser(plantUser);

      expect(await screen.findByText('Submit for Approval')).toBeInTheDocument();
      expect(screen.queryByText('Approve Plan')).not.toBeInTheDocument();

      const submitBtn = screen.getByRole('button', { name: /Submit for Approval/i });
      await userEvent.click(submitBtn);

      await waitFor(() => {
        expect(submitSpy).toHaveBeenCalledWith('plan-101');
      });
      expect(await screen.findByText(/successfully submitted for review and approval/)).toBeInTheDocument();
    });

    it('shows Approve button for Admin/Planner on SUBMITTED plan and executes aggregation', async () => {
      vi.spyOn(api, 'fetchPlans').mockResolvedValue([mockPlanSubmitted]);
      const approveSpy = vi.spyOn(api, 'approvePlan').mockResolvedValue({
        ...mockPlanSubmitted,
        status: 'APPROVED',
      });
      const aggSpy = vi.spyOn(api, 'runAggregation').mockResolvedValue(mockAggregationResponse);

      const plannerUser = {
        id: 'planner-1',
        username: 'planner',
        roles: ['PLANNER'],
        permissions: ['requirements.read', 'requirements.approve'],
      };

      renderWithUser(plannerUser);

      // Approve button is present for Planner
      const approveBtn = await screen.findByRole('button', { name: /Approve Plan/i });
      expect(approveBtn).toBeInTheDocument();

      await userEvent.click(approveBtn);
      await waitFor(() => {
        expect(approveSpy).toHaveBeenCalledWith('plan-101');
      });
      expect(await screen.findByText(/Plan approved successfully/)).toBeInTheDocument();

      // Run Aggregation button in top header
      const aggBtn = screen.getByRole('button', { name: /Run Monthly Aggregation/i });
      await userEvent.click(aggBtn);

      await waitFor(() => {
        expect(aggSpy).toHaveBeenCalledWith(10, 2026);
      });

      // Aggregation Modal opens
      expect(await screen.findByText(/Monthly Aggregation Report/)).toBeInTheDocument();
      expect(screen.getByText('Total Approved Plans')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
      expect(screen.getByText('Aggregated Consumables')).toBeInTheDocument();
      expect(screen.getAllByText('2').length).toBeGreaterThan(0);
      expect(screen.getByText('4,500')).toBeInTheDocument();
      expect(screen.getByText('4,200')).toBeInTheDocument();

      // Close modal
      const closeBtn = screen.getByRole('button', { name: /Close Report/i });
      await userEvent.click(closeBtn);
      expect(screen.queryByText(/Monthly Aggregation Report/)).not.toBeInTheDocument();
    });

    it('displays locked confirmation pill when plan is already APPROVED', async () => {
      vi.spyOn(api, 'fetchPlans').mockResolvedValue([mockPlanApproved]);

      const plannerUser = {
        id: 'planner-1',
        username: 'planner',
        roles: ['PLANNER'],
        permissions: ['requirements.read'],
      };

      renderWithUser(plannerUser);

      expect(await screen.findByText('Plan Approved & Ready for Aggregation')).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Submit for Approval/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Approve Plan/i })).not.toBeInTheDocument();
    });
  });
});
