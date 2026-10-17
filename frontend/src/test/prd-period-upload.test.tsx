import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient } from '../api/client';
import SalesScheduleImportModal, { type PreviewResponse, type RevisionInfo } from '../features/prd/SalesScheduleImportModal';

const october: RevisionInfo = { col_index: 4, month_label: "Oct'26", planning_period: '2026-10', revision_label: 'R0' };
const november: RevisionInfo = { ...october, col_index: 5, month_label: "Nov'26", planning_period: '2026-11' };
const revised: RevisionInfo = { ...october, col_index: 6, revision_label: 'R1' };

function preview(active: RevisionInfo[] = [october], errors: string[] = []): PreviewResponse {
  return {
    filename: 'synthetic.xlsx', sheet_name: 'Schedule', sheet_names: ['Schedule'], header_row_index: 3,
    available_revisions: [november, october, revised], active_revisions: active,
    blocks: [], unmapped_aliases: [], total_part_rows: active.length,
    grand_total: { parts_sum: {}, sheet_grand_total: {}, reconciliation_ok: true, diffs: {} },
    sample_rows: [], can_confirm: errors.length === 0, warnings: [], errors, file_token: 'synthetic-token',
  };
}

function show() {
  vi.spyOn(apiClient, 'get').mockResolvedValue([]);
  const onImportSuccess = vi.fn();
  render(<SalesScheduleImportModal isOpen targetPeriod="2026-10" onClose={vi.fn()} onImportSuccess={onImportSuccess} />);
  return onImportSuccess;
}

async function upload() {
  await userEvent.upload(screen.getByLabelText('Sales schedule Excel file'), new File(['synthetic'], 'synthetic.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  }));
}

afterEach(() => vi.restoreAllMocks());

test('preview and confirmation retain the selected month even when the first workbook month differs', async () => {
  const post = vi.spyOn(apiClient, 'post').mockResolvedValueOnce(preview())
    .mockResolvedValueOnce({ imported_count: 1, sheet_name: 'Schedule' });
  const onSuccess = show();
  await upload();
  expect((post.mock.calls[0][1] as FormData).get('target_period')).toBe('2026-10');
  expect(screen.getByText('Upload period: October 2026')).toBeInTheDocument();
  await userEvent.click(await screen.findByRole('button', { name: /Confirm Import/ }));
  await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(1, 'Schedule'));
  expect(post.mock.calls[1]).toEqual(['/api/v1/prd/workspace/import-confirm', expect.objectContaining({
    target_period: '2026-10', revision_label: 'R0', mode: 'APPEND',
  })]);
});

test('a workbook month mismatch blocks confirmation without changing the upload period', async () => {
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue(preview([november], ['Month mismatch: selected 2026-10 but workbook contains 2026-11.']));
  show();
  await upload();
  expect(await screen.findByText(/Month mismatch:/)).toBeInTheDocument();
  expect(screen.getByText('Upload period: October 2026')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Confirm Import/ })).toBeDisabled();
  expect(post).toHaveBeenCalledTimes(1);
});

test('multiple revisions are previewed separately and changing revision reinspects before confirmation', async () => {
  const post = vi.spyOn(apiClient, 'post').mockResolvedValueOnce(preview([october, revised]))
    .mockResolvedValueOnce(preview([october]))
    .mockResolvedValueOnce(preview([revised]))
    .mockResolvedValueOnce({ imported_count: 1, sheet_name: 'Schedule' });
  show();
  await upload();
  expect((post.mock.calls[1][1] as FormData).get('revision_label')).toBe('R0');
  await userEvent.selectOptions(await screen.findByLabelText('Workbook revision'), 'R1');
  expect((post.mock.calls[2][1] as FormData).get('target_period')).toBe('2026-10');
  expect((post.mock.calls[2][1] as FormData).get('revision_label')).toBe('R1');
  await userEvent.click(await screen.findByRole('button', { name: /Confirm Import \(1 parts\)/ }));
  expect(post.mock.calls[3]).toEqual(['/api/v1/prd/workspace/import-confirm', expect.objectContaining({
    target_period: '2026-10', revision_label: 'R1',
  })]);
});
