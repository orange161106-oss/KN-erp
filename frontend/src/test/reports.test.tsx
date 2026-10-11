import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import Reports from '../features/reports/Reports';
import { AuthContext } from '../features/auth/context';
import * as exportUtils from '../features/reports/exportUtils';

describe('Reports Dashboard & Multi-Format Exports', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/product-master/consumables')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 'c-1',
                supplier_id: 'SUP-001',
                supplier_name: 'Tata Steel',
                item_id: 'CS-ST-001',
                category: 'Raw Material',
                type_of_material: 'Steel',
                description: 'Cold Rolled Steel',
                output_unit: 'KG',
                rate: 45.5,
                is_active: true,
              },
              {
                id: 'c-2',
                supplier_id: 'SUP-002',
                supplier_name: 'Jindal Aluminium',
                item_id: 'CS-AL-002',
                category: 'Alloy',
                type_of_material: 'Aluminium',
                description: 'Aluminium Sheet',
                output_unit: 'PCS',
                rate: 110.0,
                is_active: true,
              },
            ],
            total: 2,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url.includes('/product-master/assemble')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 'a-1',
                consumable_item: 'CS-ST-001',
                part_no_saleable_item: 'PN-100',
                used_for_name_of_saleable_part: 'Chassis Frame',
                used_part_no_prd_order: 'PRD-10',
                process_name: 'ASSEMBLY',
                material_thickness_in_mm_gsm: '2.5mm',
                no_of_process_per_part: 1.5,
                output_unit: 'PCS',
                rate: 85.0,
                is_active: true,
              },
            ],
            total: 1,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url.includes('/product-master/sales-parts')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 'sp-1',
                s_no: 1,
                part_no: 'SP-DOOR-01',
                item_id: 'ITM-DOOR-01',
                part_description: 'Outer Door Panel',
                uom: 'PCS',
                is_active: true,
              },
            ],
            total: 1,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders the floating card titled "Master Data & Inventory Reports" and all 5 action buttons', async () => {
    render(
      <AuthContext.Provider
        value={{
          user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true },
          login: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <Reports />
      </AuthContext.Provider>
    );

    // Title Check
    expect(screen.getByRole('heading', { name: 'Master Data & Inventory Reports' })).toBeInTheDocument();

    // 5 Styled Action Buttons Check
    const excelBtn = screen.getByRole('button', { name: /Download Excel/i });
    const csvBtn = screen.getByRole('button', { name: /Download CSV/i });
    const pdfBtn = screen.getByRole('button', { name: /Download PDF/i });
    const wordBtn = screen.getByRole('button', { name: /Download Word/i });
    const printBtn = screen.getByRole('button', { name: /Print Report/i });

    expect(excelBtn).toBeInTheDocument();
    expect(csvBtn).toBeInTheDocument();
    expect(pdfBtn).toBeInTheDocument();
    expect(wordBtn).toBeInTheDocument();
    expect(printBtn).toBeInTheDocument();

    // Verify button styling has bg-erp-orange and text-white
    expect(excelBtn.className).toContain('bg-erp-orange');
    expect(excelBtn.className).toContain('text-white');
    expect(printBtn.className).toContain('bg-erp-orange');
    expect(printBtn.className).toContain('text-white');

    // Verify loaded consumable data
    expect(await screen.findByText('CS-ST-001')).toBeInTheDocument();
    expect(screen.getByText('CS-AL-002')).toBeInTheDocument();
  });

  it('invokes native window.print() when Print Report button is clicked', async () => {
    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {});

    render(
      <AuthContext.Provider
        value={{
          user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true },
          login: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <Reports />
      </AuthContext.Provider>
    );

    // Wait for data load
    expect(await screen.findByText('CS-ST-001')).toBeInTheDocument();

    const printBtn = screen.getByRole('button', { name: /Print Report/i });
    fireEvent.click(printBtn);

    expect(printSpy).toHaveBeenCalledTimes(1);
  });

  it('triggers export functions for Excel, CSV, PDF, and Word', async () => {
    const csvSpy = vi.spyOn(exportUtils, 'downloadCSV').mockImplementation(() => {});
    const excelSpy = vi.spyOn(exportUtils, 'downloadExcel').mockImplementation(() => {});
    const pdfSpy = vi.spyOn(exportUtils, 'downloadPDF').mockImplementation(() => {});
    const wordSpy = vi.spyOn(exportUtils, 'downloadWord').mockImplementation(async () => {});

    render(
      <AuthContext.Provider
        value={{
          user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true },
          login: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <Reports />
      </AuthContext.Provider>
    );

    expect(await screen.findByText('CS-ST-001')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Download CSV/i }));
    expect(csvSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Download Excel/i }));
    expect(excelSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Download PDF/i }));
    expect(pdfSpy).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Download Word/i }));
    expect(wordSpy).toHaveBeenCalled();
  });

  it('allows switching report categories and searching table data', async () => {
    const user = userEvent.setup();
    render(
      <AuthContext.Provider
        value={{
          user: { id: 'root', username: 'root', roles: [], permissions: [], is_super_admin: true },
          login: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <Reports />
      </AuthContext.Provider>
    );

    expect(await screen.findByText('CS-ST-001')).toBeInTheDocument();
    expect(screen.getByText('CS-AL-002')).toBeInTheDocument();

    // Search filter
    const searchInput = screen.getByPlaceholderText(/Search in/i);
    await user.type(searchInput, 'Tata');

    expect(screen.getByText('CS-ST-001')).toBeInTheDocument();
    expect(screen.queryByText('CS-AL-002')).not.toBeInTheDocument();

    // Clear search
    await user.clear(searchInput);
    expect(screen.getByText('CS-AL-002')).toBeInTheDocument();

    // Switch to Assembly BOM tab
    await user.click(screen.getByRole('button', { name: 'Assembly BOM' }));
    expect(await screen.findByText('Chassis Frame')).toBeInTheDocument();

    // Switch to Sales Parts tab
    await user.click(screen.getByRole('button', { name: 'Sales Parts' }));
    expect(await screen.findByText('SP-DOOR-01')).toBeInTheDocument();
  });

  it('renders Reports navigation link in sidebar with modern SVG icon and active styling on /reports route', async () => {
    const { MemoryRouter } = await import('react-router-dom');
    const Sidebar = (await import('../components/Sidebar')).default;

    render(
      <AuthContext.Provider
        value={{
          user: {
            id: 'root',
            username: 'root',
            roles: [],
            permissions: ['reports.inventory.read'],
            is_super_admin: true,
          },
          login: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <MemoryRouter initialEntries={['/reports']}>
          <Sidebar />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    // Sidebar Reports item
    const reportsLink = screen.getByRole('link', { name: /Reports/i });
    expect(reportsLink).toBeInTheDocument();
    // Raw emoji must be removed
    expect(reportsLink.textContent).not.toContain('📊');
    // Lucide SVG icon must be present with premium motion classes
    const svgIcon = reportsLink.querySelector('svg');
    expect(svgIcon).toBeInTheDocument();
    expect(svgIcon?.getAttribute('class')).toContain('group-hover:scale-110');
    expect(svgIcon?.getAttribute('class')).toContain('group-hover:-translate-y-0.5');

    // On /reports route, active state has bg-erp-orange and text-white
    expect(reportsLink.className).toContain('bg-erp-orange');
    expect(reportsLink.className).toContain('text-white');
  });
});
