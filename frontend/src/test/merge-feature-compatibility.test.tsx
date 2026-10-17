import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { apiClient } from '../api/client';
import { AuthContext } from '../features/auth/context';
import Requirements from '../features/requirements/Requirements';

function show() {
  vi.spyOn(apiClient,'get').mockResolvedValue({records:[],plan_metadata:{has_plan:true,planning_period:'2026-10',
    planning_month:10,planning_year:2026,status:'CALCULATED_WITH_ERRORS',revision_label:'R0',
    source_workflow:'BASIC_CENTRAL_V1',record_count:0,issue_count:2}});
  return render(<AuthContext.Provider value={{user:{id:'sample',username:'sample',roles:[],permissions:[],is_super_admin:true},login:vi.fn(),logout:vi.fn()}}>
    <Requirements/>
  </AuthContext.Provider>);
}

afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();});

test('the incoming single MRP view and issues feature work with authenticated file downloads',async()=>{
  const blob=new Blob(['Part No.,Issue\nPART-A,Review norms'],{type:'text/csv'});
  const download=vi.spyOn(apiClient,'getBlob').mockResolvedValue(blob);
  const created=vi.fn(()=> 'blob:sample-issues');
  const revoked=vi.fn();
  vi.stubGlobal('URL',class extends URL {static createObjectURL=created;static revokeObjectURL=revoked;});
  const links:string[]=[];
  vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){links.push(this.download);});
  show();
  await screen.findByText(/2 issues:/);
  expect(screen.queryByText('Central requirement plan')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/Download issues list/}));
  await screen.findByText('Issues CSV download started.');
  expect(download).toHaveBeenCalledWith('/api/v1/requirements/workspace/issues/export?month=10&year=2026');
  expect(created).toHaveBeenCalledWith(blob);
  expect(links).toEqual(['requirement_issues_2026_10.csv']);
  expect(revoked).toHaveBeenCalledWith('blob:sample-issues');
});

test('an issues download error retains the incoming issues banner and allows retry',async()=>{
  vi.spyOn(apiClient,'getBlob').mockRejectedValue(new Error('Could not load the issues report.'));
  show();
  await screen.findByText(/2 issues:/);
  fireEvent.click(screen.getByRole('button',{name:/Download issues list/}));
  await screen.findByText('Could not load the issues report.');
  expect(screen.getByRole('button',{name:/Download issues list/})).toBeEnabled();
  expect(screen.getByText(/2 issues:/)).toBeInTheDocument();
});
