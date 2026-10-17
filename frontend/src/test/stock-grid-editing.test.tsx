import {useState} from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import {expect,test,vi} from 'vitest';
import DataTable from '../components/DataTable';

const initial=[{id:'1',code:'TEST-1',quantity:'10',value:'20'},{id:'2',code:'TEST-2',quantity:'30',value:'40'}];
const columns=[{key:'code',label:'Code',isEditable:false},{key:'quantity',label:'Quantity',isEditable:true},{key:'value',label:'Value',isEditable:true}] as const;
function Harness({editable=true}:{editable?:boolean}) {
 const [rows,setRows]=useState(initial);
 return <DataTable columns={[...columns]} data={rows} originalData={new Map(initial.map(r=>[r.id,r]))}
 selectedIds={new Set()} onSelectionChange={()=>{}} canUpdate={editable}
 onCellChange={(id,key,value)=>setRows(prev=>prev.map(row=>row.id===id?{...row,[key]:value}:row))}/>;
}
function cell(value:string) {return screen.getByRole('cell',{name:value});}
function undo() {fireEvent.keyDown(document.body,{key:'z',ctrlKey:true});}
function redo() {fireEvent.keyDown(document.body,{key:'y',ctrlKey:true});}
function select(value:string) {const target=cell(value);fireEvent.click(target);target.focus();return target;}

test('cell commit, clear and redo all participate in Ctrl+Z history',()=>{
 render(<Harness/>);
 fireEvent.doubleClick(cell('10'));
 const editor=screen.getByRole('textbox',{name:'Edit Quantity'});
 fireEvent.change(editor,{target:{value:'12.1234'}});
 fireEvent.blur(editor);
 select('12.1234'); undo(); expect(cell('10')).toBeInTheDocument();
 redo();expect(cell('12.1234')).toBeInTheDocument();
 fireEvent.keyDown(select('12.1234'),{key:'Delete'});
 undo(); expect(cell('12.1234')).toBeInTheDocument();
});

test('native copy/paste and rectangular paste are one undo action',()=>{
 render(<Harness/>);
 const target=select('10');const setData=vi.fn();
 fireEvent.copy(target,{clipboardData:{setData}});
 expect(setData).toHaveBeenCalledWith('text/plain','10');
 fireEvent.paste(target,{clipboardData:{getData:()=> '1.1234\t2\n3\t4'}});
 expect(cell('1.1234')).toBeInTheDocument();expect(cell('4')).toBeInTheDocument();
 undo();expect(cell('10')).toBeInTheDocument();expect(cell('40')).toBeInTheDocument();
 redo();expect(cell('1.1234')).toBeInTheDocument();
});

test('formula-bar edit and context-menu clear can be undone',async()=>{
 render(<Harness/>);select('10');
 fireEvent.change(screen.getByRole('textbox',{name:'Formula bar'}),{target:{value:'15'}});
 select('15');undo();expect(cell('10')).toBeInTheDocument();
 select('10');
 fireEvent.contextMenu(cell('10'));
 fireEvent.click(await screen.findByRole('button',{name:/^Clear cell/}));
 undo();expect(cell('10')).toBeInTheDocument();
});

test('row editor changes participate in history and protected identifiers stay read-only',()=>{
 render(<Harness/>);fireEvent.contextMenu(select('10'));
 fireEvent.click(screen.getByRole('button',{name:'Edit row…'}));
 fireEvent.change(screen.getByLabelText('Quantity'),{target:{value:'15'}});
 expect(screen.queryByRole('textbox',{name:'Code'})).not.toBeInTheDocument();
 fireEvent.keyDown(screen.getByLabelText('Quantity'),{key:'z',ctrlKey:true});
 expect(screen.getByLabelText('Quantity')).toHaveValue('10');
});

test('paste, clear and formula bar cannot mutate read-only columns or readers',()=>{
 render(<Harness/>);const target=select('TEST-1');
 expect(screen.getByRole('textbox',{name:'Formula bar'})).toBeDisabled();
 fireEvent.paste(target,{clipboardData:{getData:()=> 'NEW-CODE'}});
 expect(cell('TEST-1')).toBeInTheDocument();
 expect(screen.getByRole('alert')).toHaveTextContent('read-only');
});

test('Ctrl+Z in an unrelated text input keeps its native behavior',()=>{
 render(<><input aria-label="External search"/><Harness/></>);
 fireEvent.doubleClick(cell('10'));
 fireEvent.change(screen.getByRole('textbox',{name:'Edit Quantity'}),{target:{value:'15'}});
 fireEvent.blur(screen.getByRole('textbox',{name:'Edit Quantity'}));
 const search=screen.getByLabelText('External search');search.focus();
 fireEvent.keyDown(search,{key:'z',ctrlKey:true});expect(cell('15')).toBeInTheDocument();
});


test('multi-row paste beyond the table is rejected without partial edits',()=>{
 render(<Harness/>);const target=select('10');
 fireEvent.paste(target,{clipboardData:{getData:()=> '1\n2\n3'}});
 expect(cell('10')).toBeInTheDocument();expect(cell('30')).toBeInTheDocument();
 expect(screen.getByRole('alert')).toHaveTextContent('beyond the table');
});

test('read-only viewers cannot change cells by edit, paste, clear or row menu',()=>{
 render(<Harness editable={false}/>);const target=select('10');
 fireEvent.doubleClick(target);expect(screen.queryByRole('textbox',{name:'Edit Quantity'})).not.toBeInTheDocument();
 fireEvent.paste(target,{clipboardData:{getData:()=> '99'}});fireEvent.keyDown(target,{key:'Delete'});
 expect(cell('10')).toBeInTheDocument();
 fireEvent.contextMenu(target);
 expect(screen.getByRole('button',{name:'Edit row…'})).toBeDisabled();
});


test('right-click Edit cell keeps typed text when selecting text inside the input',()=>{
 render(<Harness/>);
 fireEvent.contextMenu(select('10'));
 fireEvent.click(screen.getByRole('button',{name:/^Edit cell/}));
 const editor=screen.getByRole('textbox',{name:'Edit Quantity'});
 fireEvent.change(editor,{target:{value:'12.1234'}});
 fireEvent.doubleClick(editor);
 expect(editor).toHaveValue('12.1234');
 fireEvent.keyDown(editor,{key:'Enter'});
 expect(cell('12.1234')).toBeInTheDocument();
});


test('F2 focuses and selects the current value; typing starts with the caret after the first character',()=>{
 render(<Harness/>);
 const target=select('10');fireEvent.keyDown(target,{key:'F2'});
 const editor=screen.getByRole('textbox',{name:'Edit Quantity'}) as HTMLInputElement;
 expect(editor).toHaveFocus();expect(editor.selectionStart).toBe(0);expect(editor.selectionEnd).toBe(2);
 fireEvent.keyDown(editor,{key:'Escape'});
 fireEvent.keyDown(select('10'),{key:'1'});
 const typed=screen.getByRole('textbox',{name:'Edit Quantity'}) as HTMLInputElement;
 expect(typed).toHaveFocus();expect(typed).toHaveValue('1');expect(typed.selectionStart).toBe(1);expect(typed.selectionEnd).toBe(1);
});
