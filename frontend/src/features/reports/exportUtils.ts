
export interface ColumnDef {
  header: string;
  key: string;
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Multi-format export: CSV Download
 */
export function downloadCSV(
  columns: ColumnDef[],
  data: Record<string, any>[],
  filename = 'knl_erp_report'
) {
  const headers = columns.map((c) => `"${c.header.replace(/"/g, '""')}"`).join(',');
  const rows = data.map((row) =>
    columns
      .map((c) => {
        const val = row[c.key];
        if (val === null || val === undefined) return '""';
        return `"${String(val).replace(/"/g, '""')}"`;
      })
      .join(',')
  );

  const csvContent = '\uFEFF' + [headers, ...rows].join('\r\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  triggerDownload(blob, `${filename}.csv`);
}

/**
 * Multi-format export: Excel (.xls XML SpreadsheetML) Download
 */
export function downloadExcel(
  columns: ColumnDef[],
  data: Record<string, any>[],
  filename = 'knl_erp_report',
  sheetName = 'Report Data'
) {
  const escapeXml = (unsafe: any) => {
    if (unsafe === null || unsafe === undefined) return '';
    return String(unsafe)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  };

  const headerCells = columns
    .map(
      (c) =>
        `<Cell ss:StyleID="Header"><Data ss:Type="String">${escapeXml(c.header)}</Data></Cell>`
    )
    .join('');

  const rowCells = data
    .map((row) => {
      const cells = columns
        .map((c) => {
          const val = row[c.key];
          const isNum = typeof val === 'number' && !isNaN(val);
          const cellType = isNum ? 'Number' : 'String';
          const cellVal = isNum ? val : escapeXml(val ?? '—');
          return `<Cell ss:StyleID="${isNum ? 'NumberCell' : 'Normal'}"><Data ss:Type="${cellType}">${cellVal}</Data></Cell>`;
        })
        .join('');
      return `<Row>${cells}</Row>`;
    })
    .join('\n');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:x="urn:schemas-microsoft-com:office:excel"
  xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:html="http://www.w3.org/TR/REC-html40">
  <Styles>
    <Style ss:ID="Default" ss:Name="Normal">
      <Alignment ss:Vertical="Center"/>
      <Borders/>
      <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#400101"/>
      <Interior/>
      <NumberFormat/>
      <Protection/>
    </Style>
    <Style ss:ID="Header">
      <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
      <Borders>
        <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D95204"/>
      </Borders>
      <Font ss:FontName="Calibri" ss:Size="11" ss:Color="#FFFFFF" ss:Bold="1"/>
      <Interior ss:Color="#FF5E2C" ss:Pattern="Solid"/>
    </Style>
    <Style ss:ID="Normal">
      <Alignment ss:Vertical="Center"/>
      <Font ss:FontName="Calibri" ss:Size="10" ss:Color="#400101"/>
    </Style>
    <Style ss:ID="NumberCell">
      <Alignment ss:Horizontal="Right" ss:Vertical="Center"/>
      <Font ss:FontName="Calibri" ss:Size="10" ss:Color="#D95204"/>
      <NumberFormat ss:Format="#,##0.00"/>
    </Style>
  </Styles>
  <Worksheet ss:Name="${escapeXml(sheetName)}">
    <Table>
      ${columns.map(() => '<Column ss:Width="120"/>').join('\n')}
      <Row ss:Height="24">
        ${headerCells}
      </Row>
      ${rowCells}
    </Table>
  </Worksheet>
</Workbook>`;

  const blob = new Blob([xml], { type: 'application/vnd.ms-excel;charset=utf-8' });
  triggerDownload(blob, `${filename}.xls`);
}

/**
 * Multi-format export: PDF Download (jsPDF + autoTable)
 */
export async function downloadPDF(
  title: string,
  columns: ColumnDef[],
  data: Record<string, any>[],
  filename = 'knl_erp_report'
) {
  const [{ default: jsPDF }, { default: autoTable }] = await Promise.all([
    import('jspdf'), import('jspdf-autotable'),
  ]);
  const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });

  // Top Accent Banner
  doc.setFillColor(255, 94, 44); // #ff5e2c erp-orange
  doc.rect(0, 0, doc.internal.pageSize.getWidth(), 20, 'F');

  doc.setTextColor(255, 255, 255);
  doc.setFontSize(13);
  doc.setFont('helvetica', 'bold');
  doc.text('KNL Consumable ERP — Official Report Export', 14, 10);

  doc.setFontSize(8);
  doc.setFont('helvetica', 'normal');
  doc.text(`Generated: ${new Date().toLocaleString()}`, 14, 16);

  // Subtitle & Metrics
  doc.setTextColor(64, 1, 1); // #400101 erp-chocolate
  doc.setFontSize(12);
  doc.setFont('helvetica', 'bold');
  doc.text(title, 14, 28);

  doc.setFontSize(9);
  doc.setFont('helvetica', 'normal');
  doc.text(`Total Records: ${data.length}`, 14, 33);

  const head = [columns.map((c) => c.header)];
  const body = data.map((row) =>
    columns.map((c) => {
      const v = row[c.key];
      if (v === null || v === undefined) return '—';
      return String(v);
    })
  );

  autoTable(doc, {
    startY: 36,
    head,
    body,
    theme: 'striped',
    headStyles: {
      fillColor: [255, 94, 44],
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 8,
    },
    bodyStyles: {
      textColor: [64, 1, 1],
      fontSize: 8,
    },
    alternateRowStyles: {
      fillColor: [255, 246, 192], // erp-vanilla
    },
    margin: { left: 14, right: 14 },
    styles: { overflow: 'linebreak' },
  });

  doc.save(`${filename}.pdf`);
}

/**
 * Multi-format export: Word (.docx) Download
 */
export async function downloadWord(
  title: string,
  columns: ColumnDef[],
  data: Record<string, any>[],
  filename = 'knl_erp_report'
) {
  const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType } = await import('docx');
  const tableHeaderRow = new TableRow({
    tableHeader: true,
    children: columns.map(
      (col) =>
        new TableCell({
          shading: {
            type: ShadingType.CLEAR,
            fill: 'FF5E2C', // erp-orange
            color: 'auto',
          },
          children: [
            new Paragraph({
              children: [
                new TextRun({
                  text: col.header,
                  bold: true,
                  color: 'FFFFFF',
                  size: 20,
                }),
              ],
            }),
          ],
        })
    ),
  });

  const dataRows = data.map(
    (row, idx) =>
      new TableRow({
        children: columns.map((col) => {
          const val = row[col.key];
          const strVal = val === null || val === undefined ? '—' : String(val);
          return new TableCell({
            shading:
              idx % 2 === 1
                ? {
                    type: ShadingType.CLEAR,
                    fill: 'FFF6C0', // erp-vanilla
                    color: 'auto',
                  }
                : undefined,
            children: [
              new Paragraph({
                children: [
                  new TextRun({
                    text: strVal,
                    size: 18,
                    color: '400101',
                  }),
                ],
              }),
            ],
          });
        }),
      })
  );

  const doc = new Document({
    sections: [
      {
        properties: {},
        children: [
          new Paragraph({
            children: [
              new TextRun({
                text: 'KNL Consumable ERP',
                bold: true,
                color: 'FF5E2C',
                size: 32,
              }),
            ],
          }),
          new Paragraph({
            children: [
              new TextRun({
                text: title,
                bold: true,
                color: '400101',
                size: 24,
              }),
            ],
          }),
          new Paragraph({
            children: [
              new TextRun({
                text: `Generated: ${new Date().toLocaleString()} | Total Records: ${data.length}`,
                italics: true,
                color: '8C2703',
                size: 18,
              }),
            ],
          }),
          new Paragraph({ text: '' }),
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: [tableHeaderRow, ...dataRows],
          }),
        ],
      },
    ],
  });

  const blob = await Packer.toBlob(doc);
  triggerDownload(blob, `${filename}.docx`);
}
