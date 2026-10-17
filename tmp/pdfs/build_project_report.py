from pathlib import Path
from html import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader

ROOT = Path('C:/KN')
OUT = ROOT / 'output/pdf/KNL_ERP_Overall_Project_Report_2026-10-17.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
for name, file in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'), ('Arial-Italic', 'ariali.ttf')]:
    pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/' + file))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic', boldItalic='Arial-Bold')
NAVY = colors.HexColor('#183345')
TEAL = colors.HexColor('#127B78')
ORANGE = colors.HexColor('#D77932')
INK = colors.HexColor('#263C49')
MUTED = colors.HexColor('#61727D')
LIGHT = colors.HexColor('#EFF5F6')
LINE = colors.HexColor('#D8E3E6')
W, H = A4
CW = W - 108
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyReport', fontName='Arial', fontSize=10.1, leading=14.5, textColor=INK, spaceAfter=8))
styles.add(ParagraphStyle(name='SmallReport', fontName='Arial', fontSize=8.6, leading=11.8, textColor=MUTED, spaceAfter=7))
styles.add(ParagraphStyle(name='TitleReport', fontName='Arial-Bold', fontSize=25, leading=29.5, textColor=NAVY, spaceAfter=12))
styles.add(ParagraphStyle(name='SubReport', fontName='Arial-Bold', fontSize=12.5, leading=16.5, textColor=TEAL, spaceBefore=12, spaceAfter=6))
styles.add(ParagraphStyle(name='LabelReport', fontName='Arial-Bold', fontSize=8.5, leading=12, textColor=TEAL, spaceAfter=8))
styles.add(ParagraphStyle(name='CellReport', fontName='Arial', fontSize=9, leading=12.1, textColor=INK))
styles.add(ParagraphStyle(name='CellSmall', fontName='Arial', fontSize=8.1, leading=10.8, textColor=INK))
styles.add(ParagraphStyle(name='CellHead', fontName='Arial-Bold', fontSize=9, leading=12, textColor=colors.white))
story = []

def p(text, style='BodyReport'):
    return Paragraph(text, styles[style])
def add(text, style='BodyReport'):
    story.append(p(text, style))
def h(text):
    add(text, 'SubReport')
def bullet(title, text):
    add('<b>' + title + '</b> ' + text)
def note(text):
    data = [[p(text, 'SmallReport')]]
    t = Table(data, colWidths=[CW], hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),0.6,LINE),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.extend([Spacer(1,7),t,Spacer(1,8)])
def table(headers, rows, widths, small=False):
    cs = 'CellSmall' if small else 'CellReport'
    data = [[p(x, 'CellHead') for x in headers]] + [[p(str(x), cs) for x in row] for row in rows]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),6 if small else 8),('BOTTOMPADDING',(0,0),(-1,-1),6 if small else 8),('LINEBELOW',(0,0),(-1,0),0.6,NAVY),('LINEBELOW',(0,1),(-1,-1),0.35,LINE)]))
    story.extend([t,Spacer(1,8)])
def page(number, title, subtitle):
    if story: story.append(PageBreak())
    add(f'PROJECT REPORT  /  {number:02d}', 'LabelReport')
    add(title, 'TitleReport')
    add(subtitle, 'SmallReport')
    story.append(Spacer(1,5))
def source(text):
    story.append(Spacer(1,5))
    add('Evidence: ' + text, 'SmallReport')

page(1, 'KNL Consumable ERP<br/>Overall Project Report', 'Reporting period: 30 September - 17 October 2026 | Prepared: 17 October 2026 | India Standard Time')
add('What we have built.<br/>What we have focused on.<br/>What comes next.', 'SubReport')
add('The project has progressed from repository and application foundations to an integrated development system for consumable planning, inventory visibility and purchase workflows. The main focus has been turning KNL workbook practices into controlled, explainable and usable software.')
table(['FOUNDATION', 'BUSINESS WORKFLOW', 'CURRENT FOCUS'], [[
    'Authentication, masters, APIs, database migrations and audit history.',
    'Production import, consumption norms, central requirements, inventory, purchase, PO and GRN foundations.',
    'Unified Requirement/MRP review, reliable record loading, editable purchase proposals and protected exports.'
]], [CW/3]*3)
h('Overall position')
bullet('Implemented:', 'major modules, deterministic calculation services, Excel workspaces, administration, reporting and performance improvements are present in code and documented checks.')
bullet('Demonstrated:', 'October R0 produced 65 saved requirement lines for 31 consumables. Central and monthly views were checked against the same saved demand.')
bullet('Still open:', 'company norm/process configuration, complete source evidence, final integration regression checks and operational acceptance. Implemented screens do not by themselves establish production readiness.')
note('<b>Snapshot basis.</b> This report uses repository history through commit 760785b and reviewed local changes, project contracts and dated validation notes. It includes work from all three domain owners. It is a project progress report, not a new test run, deployment approval or company UAT certificate.')
source('[S1-S3, S5, S13]. Detailed source register is on page 11. No credentials or employee account details are included.')

page(2, 'Progress from the start', 'Chronology reconstructed from commit history and dated project records. Dates describe implementation milestones, not production acceptance.')
table(['PERIOD', 'WORK COMPLETED / MAIN FOCUS'], [
    ['30 Sep - 1 Oct', '<b>Project foundation.</b> Repository, documentation, React shell, system status, backend/data foundation, login and role-aware navigation; early customer/product and production masters.'],
    ['2 Oct', '<b>Core planning structure.</b> Consumable/unit/supplier masters, mappings and requirement milestones; plant confirmation, exceptions, approval and final-demand handoff foundations.'],
    ['4 - 6 Oct', '<b>Inventory and purchasing engines.</b> Central source-stock import, projected stock, MSL/reorder assessment, purchase recommendation/review, PO/GRN integration, alerts, reports and dashboard. Technical golden-case framework added.'],
    ['7 - 9 Oct', '<b>Access and verified workflow.</b> User provisioning, granular permissions and CRUD controls; production workbook work, formula foundation, import/export safeguards and integration fixes.'],
    ['10 - 13 Oct', '<b>Usability and monthly workspaces.</b> Visual theme, master/report screens, monthly requirement and purchase workspaces, multi-plant review, spreadsheet editing and safe period deletion; connection recovery.'],
    ['15 Oct', '<b>Workflow simplification and speed.</b> Undated Product Master catalog, reviewed file preview/save, loading/query optimization, diagnostics and dependencies. Owner-approved central basic planning and reviewed schema deployment.'],
    ['16 Oct', '<b>Connected results.</b> Dynamic period/revision import, central/monthly demand consistency, October recalculation, Purchase Plan demand repair, editable audited proposals and faster combined reads.'],
    ['17 Oct', '<b>Integration quality.</b> Purchase-page crash repair, authenticated Excel/issue exports and both-contributor merge review. Latest documented direction: one MRP screen, preserved central scope and an explicit reviewer-selected calculation date.'],
], [94,CW-94])
note('<b>How the focus changed:</b> first establish the modules, then match the real workbook and review process, then improve data consistency, everyday editing and reliable operation. Later owner-approved decisions supersede earlier screen layouts.')
source('[S2, S3, S5, S9-S13]. First recorded commits: 30 September 2026.')

page(3, 'Purpose, workflow and ownership', 'A consumable-planning system around KNL\'s existing ERP, with human review and traceable calculations.')
h('Business purpose')
add('Use production schedules and approved consumption norms to calculate consumable demand, review a central plan, assess stock and incoming supply, recommend purchases, track commitments and receipts, and explain the result to users.')
note('<b>Current basic workflow</b><br/>Master catalog + production schedule + reviewed norms<br/><b>then</b> central requirement calculation and diagnostics<br/><b>then</b> Super Admin review and approved demand<br/><b>then</b> inventory/purchase assessment, independent approval, PO and accepted-receipt tracking.')
h('Architecture implemented')
add('<b>React + TypeScript + Vite + Tailwind</b> provide screens and editing. <b>FastAPI + Pydantic</b> validate requests. Application services coordinate calculations, transactions and audit. <b>SQLAlchemy + PostgreSQL + Alembic</b> provide persistence and schema control. <b>openpyxl</b> supports Excel exchange; supporting data libraries are declared in the dependency lockfile.')
table(['OWNER', 'PRIMARY RESPONSIBILITY'], [
    ['Munees', 'Inventory and purchase planning; consumable/unit/supplier coordination, stock, projection, reorder, recommendation, PO/GRN and purchase reporting.'],
    ['Yathish', 'Production and requirements; product/customer masters, production import, mappings, norms and requirement calculation.'],
    ['Keerthi', 'Plant workflows, access, exceptions/approvals, alerts and dashboard/workflow visibility.'],
], [84,CW-84])
h('Principles retained throughout')
add('One common central store; exact Decimal quantities; explicit revisions and dates; backend permission checks; audit/history preservation; unknown inputs remain unknown. The existing ERP remains the warehouse-posting authority. Phase-1 business decisions use deterministic rules, not AI/ML.')
add('The newer basic central workflow removes Product-Plant Mapping as a prerequisite. Older plant-specific capabilities remain historical/separate; their active navigation and routing have changed during MRP consolidation and need explicit integration review.', 'SmallReport')
source('[S1, S3-S7]. Team ownership files and accepted architecture decisions informed this section.')

page(4, 'Masters, production and norms', 'Focus: reliable source data, reviewed imports and exact identity matching.')
h('Master data and administration')
bullet('Catalogs:', 'products, consumables, units, suppliers and related mappings; account provisioning and granular permissions; soft deletion and change history.')
bullet('Product Master correction:', 'the catalog is undated. Upload creates a preview, review happens before Save changes, and discard does not write records. Consumables, assembly mappings and sales parts use the shared workspace.')
bullet('Data integrity:', 'stable identifiers and mappings are preserved. Unit/UOM is explicit; numeric Output/Unit values do not become invented stock units. Missing units remain review items and can be completed under controlled checks.')
h('Production for Sale imports')
add('The restored Sales Schedule importer detects headers and customer blocks dynamically, handles varying column order and revision columns, reconciles subtotals, and identifies rows needing review. The selected month/year governs loading, preview, confirmation and current-view export.')
add('Part No and Item ID matching remains exact. Wrong-month and mixed-revision payloads are rejected. R0/R1 history stays separate; imports do not silently sum revisions or fabricate new product masters.')
h('Consumption Norms')
add('Manual creation, canonical master selection, XLSX/CSV templates, preview corrections, explicit confirmation, grid editing, filters, exports and version history are implemented. Source references and formula parameters remain explainable. The owner-requested test-calculation panel was removed on 16 October; requirement calculations remain available in their workflow.')
note('<b>Approved example, limited scope:</b> for the supplied direct-rate drill case, 100 production parts x 2 processes = 200 final consumable units. No tool-life divisor is invented for that selected formula. Other formula families retain their own handlers and required parameters.')
h('What we focused on')
add('Separate source mistakes from valid zero values; avoid guessed units, rates and mappings; make upload counts and duplicate/missing-ID diagnostics visible; preserve review before persistence.')
source('[S3, S5, S12]. The catalog review reconciled 468 unique item IDs; this is a source-file observation, not a count of production-approved masters.')

page(5, 'Requirement planning and results', 'Focus: one explainable central demand basis, consistent views and visible configuration gaps.')
h('Implemented planning capability')
add('Production and effective norms feed the existing Decimal rule engine. Saved results retain source production, product/process/material, norm version, inputs, formula steps and rounded quantities. Missing or ambiguous configuration creates diagnostics rather than a trustworthy zero-demand result.')
add('The owner-approved basic workflow reviews one central plan. Central and monthly compatibility reads/recalculation reuse the same saved calculations for the relevant BASIC_CENTRAL_V1 revision. Manual/historical plans are not silently converted into that central path.')
table(['OCTOBER R0', 'VERIFIED SAVED RESULT'], [
    ['65', 'Requirement lines saved after consolidation from 66 formula contributions.'],
    ['31', 'Distinct consumables represented in the saved calculations.'],
    ['159', 'Remaining configuration diagnostics: 142 missing norms and 17 missing process assignments.'],
    ['224', 'Rows shown in the checked monthly compatibility grid: 65 calculations + 159 configuration rows.'],
], [90,CW-90])
add('The recalculation replaced 1,018 stale saved errors and removed false production-unit-change errors. These counts have different meanings and are not a completion percentage. The October plan remains unapproved in the latest recorded live check.', 'SmallReport')
h('Recovery and consistency repairs')
add('A successful save is distinguished from a failed follow-up read. Reload results retries reading without repeating the write or requiring logout. Stale results are cleared, resolved diagnostics disappear after reload, and approval waits for available saved results.')
h('Latest direction: unified MRP')
add('The 17 October contract selects one Requirement/MRP screen retaining central review, diagnostics, formula details and assessment actions. It preserves central/plant access restrictions and requires a reviewer-selected calculation date. Code inspection found restored central-scope guards; final regression verification of the evolving merge remains a release gate.')
source('[S3, S5, S11, S13]. Live recalculation was an explicit recorded owner-session action; this report performed no recalculation or approval.')

page(6, 'Inventory and stock planning', 'Focus: usable stock evidence, controlled monthly corrections and explainable shortage assessment.')
h('Central inventory foundation')
add('A normalized import path stores already-posted source transactions and dated usable-stock snapshots. Imported evidence is append-only; the latest source snapshot supplies the reported balance. Missing stock is unknown, not zero. Actual company export mapping and data freshness still need operational verification.')
add('A PO is a commitment, not stock. Plant dispatch is not automatically consumption. Only accepted usable receipts and usable returns can contribute to usable stock under the source contract; damaged/rejected material remains excluded.')
h('Monthly inventory workspaces')
table(['WORKSPACE', 'DELIVERED BEHAVIOR'], [
    ['Stock Statement', 'Period-specific uploads, opening/receipt/issue/closing quantities and values, description corrections, review and export.'],
    ['Stock Management', 'Monthly material parameters such as MSL, maximum level, MOQ and lead time, with validated edits and catalog references.'],
    ['Shared editing', 'Cell/row editing, formula bar, rectangular paste, clear, undo/redo and keyboard save. Exact decimal text and explicit null are preserved.'],
    ['Safe deletion', 'Reviewed batch + month/year + reason + permission. Deactivate the selected period; retain original rows, other periods and audit history.'],
], [110,CW-110])
h('Projection, MSL and reorder')
add('The inventory engine assesses dated demand, confirmed outstanding incoming supply, usable stock, MSL and lead-time evidence. Results explain projected balances, breach/reorder conditions and incomplete evidence. Monthly demand is not automatically spread across invented daily consumption.')
note('<b>Important boundary:</b> editing an uploaded monthly statement corrects a report workspace. It does not post a warehouse transaction in the existing ERP and does not automatically create the stronger reconciled snapshot/timing evidence required by the normalized projection engine.')
source('[S3, S6, S9]. Policy values, approved unit conversions and real source-reconciliation evidence remain company inputs.')

page(7, 'Purchase, PO, GRN and reporting', 'Focus: consolidated demand, explicit proposals and approval evidence, with no fabricated purchasing inputs.')
h('Purchase Plan and assessment')
add('The Purchase Plan now reads central saved demand as well as its separate legacy monthly path. October no longer appears empty merely because the demand is stored in CalculatedRequirement: its 65 lines consolidate to 31 consumables.')
add('Unapproved requirements show a review prerequisite. Stock, incoming, raw need and recommended purchase stay blank when evidence is unavailable. Supplier/policy selection and the traced server assessment remain explicit; a convenient grid does not authorize purchasing.')
bullet('Editable proposals:', 'requested quantity and remarks are versioned and audited separately from system recommendations. Permitted name/unit corrections need master authority as well as purchase authority; historical calculation units are not relabeled.')
bullet('Usable workspace:', 'scrolling, cell/row editing, correct unsaved counts, atomic saves, stale-edit recovery and selected/all/filtered exports. Submitted proposals remain protected and approval is a separate action.')
h('Downstream foundations')
table(['CAPABILITY', 'WHAT HAS BEEN BUILT / BOUNDARY'], [
    ['Recommendation', 'Explicit target, lead time, MOQ, pack and order-multiple assessment with explanations. Unknown constraints block a final recommendation; supplier defaults are not guessed.'],
    ['Purchase orders', 'Traced server evidence, independently reviewed positive approval, draft/issue/cancel checks, precise quantities/pricing and immutable submission evidence.'],
    ['Goods receipts', 'Normalized posted-ERP import with received/accepted/rejected quantities; accepted-only fulfilment, duplicate/retry safeguards and atomic stock-source links.'],
    ['Reports and alerts', 'Material stock, shortage/reorder, supplier plans, pending POs, GRN history, planned/actual foundations, dashboard and PO/MSL alert workflows. Source coverage remains visible.'],
], [98,CW-98], small=True)
note('<b>17 October repair:</b> Purchase Excel downloads now use the authenticated API client rather than opening a protected URL without its token. Errors remain visible; tokens are not placed in URLs. The Purchase-page component wiring was also repaired after the merge.')
source('[S3, S5, S7, S8, S13]. The editable GRN workbook and normalized stock/PO receipt integration are distinct paths; full company reconciliation remains required.')

page(8, 'Usability, speed and reliability', 'Focus: keep the familiar spreadsheet workflow while reducing avoidable loading and recovery problems.')
h('Everyday user experience')
add('The app gained a consistent theme and shell, collapsible grouped sidebar, hover/focus tooltips, bounded page/table scrolling, loading/empty/error states and a page error boundary. Large grids render visible rows while retaining complete filtering, selection, export and editing behavior.')
add('Remote searches debounce at 300 ms and stale responses cannot overwrite the selected period/filter. Export libraries and screens load on demand. Blocking workbook parsing uses request workers. Saves are explicit; transient recovery never automatically repeats business writes.')
h('Recorded optimization evidence')
table(['MEASURE', 'BEFORE', 'AFTER'], [
    ['Login entry JavaScript (15 Oct)', 'About 1.65 MB monolithic build', 'About 286 KB entry / 90 KB gzip'],
    ['500-row stock bulk save SELECTs', '506', '5'],
    ['Stock read queries (15 Oct sample)', '5', '3'],
    ['Central result service (16 Oct)', '5,218 ms', '2,618 ms'],
    ['Monthly metadata/records (16 Oct)', '8,673 ms', '3,948 ms'],
    ['Physical connections in read sample', '4', '1 reused connection'],
], [CW*.47,CW*.265,CW*.265], small=True)
add('Timings are individual recorded observations with different measurement boundaries, not a capacity test or response-time guarantee. Later metadata-specific changes reached two queries; these are separate endpoints/checks, not contradictory measurements.', 'SmallReport')
h('Database and recovery work')
add('Pool-mode detection now distinguishes session/direct reuse from transaction-mode pooling, with bounded budgets, pre-ping, keepalives and recycling. Combined Requirement read APIs reduce separate requests. Read-only diagnostics classify connection/schema/capacity issues without exposing secrets.')
note('<b>Remaining limitation:</b> remote handshake and network/provider latency still varies. A fast warm read does not prove a fast cold start. Hosting-capacity validation, operational monitoring and failover/backup ownership still need release evidence.')
source('[S3, S10, S11]. Measurements are cited from prior validation records; this report did not rerun benchmarks.')

page(9, 'Testing, controls and release status', 'Technical validation is substantial. Company acceptance and a fresh integrated release check are separate requirements.')
table(['RECORDED CHECK', 'RESULT AND SCOPE'], [
    ['15 Oct performance hardening', '133 targeted backend checks; 114 frontend checks across 17 files; TypeScript/build and dependency installation/lock checks passed.'],
    ['16 Oct record loading', '90 focused backend and 31 frontend checks, TypeScript and production build passed. Read-only live samples retained 65 calculations / 159 diagnostics / 31 consumables.'],
    ['16 Oct Purchase editing', '37 backend and 28 frontend checks plus build; synthetic browser verified scrolling and row saving. Company master/approval data was not edited for that verification.'],
    ['17 Oct page/export fixes', '18 focused frontend page checks; 26 frontend export checks and 1 isolated backend workbook check, with TypeScript/build recorded as passing. Runs overlap and must not be added.'],
    ['17 Oct merge audit', '32 frontend checks passed. The earlier backend audit recorded 20 passed / 2 central-scope failures. A later owner-approved contract and restored code guards supersede the undecided policy; new integrated pass evidence is still required.'],
], [129,CW-129], small=True)
h('Controls built into the workflow')
add('Backend authorization, current-user checks, audit records, batch/period ownership, explicit reasons, exact decimal validation, protected identifiers, transactional saves and history-preserving deletion. These controls have targeted tests; cross-module permission consistency still requires final review.')
h('Schema and deployment evidence')
add('A reviewed central-planning migration was recorded on 15 October with a clean application schema gate and unchanged protected data counts. A later Purchase draft table was added while preserving an external database migration marker absent from this checkout. Local and hosted ancestry must be reconciled before any generic upgrade.')
note('<b>Release position:</b> no overall completion percentage or production-ready claim is assigned. Synthetic tests are not KNL numeric acceptance. Golden company examples, end-to-end stock/PO/GRN reconciliation and operational deployment checks remain necessary. Older findings are historical unless explicitly reverified.')
source('[S3, S5, S10, S11, S13, S14]. Counts describe their original runs, not a fresh full-repository test result.')

page(10, 'Current priorities and next steps', 'Suggested sequence based on the latest recorded work. No delivery dates or company policy values are assumed.')
table(['PRIORITY', 'NEXT WORK / EXPECTED EVIDENCE'], [
    ['1. Finish unified integration', 'Keep the owner-selected single MRP surface, central review, contributor features, existing plant boundaries and explicit calculation date. Recheck navigation, all read/export/recalculate routes and the previously failing scope tests.'],
    ['2. Complete October configuration', 'Review the 142 missing-norm and 17 process diagnostics against company sources. Supply real units/effective norms; recalculate and independently check results before central approval.'],
    ['3. Prove purchase readiness', 'Obtain reviewed usable stock, incoming schedules, targets, supplier/lead-time/MOQ/pack/multiple evidence. Verify consolidated demand applies shared stock once and cannot bypass traced approval.'],
    ['4. Reconcile receipts and reporting', 'Validate one complete company example from production through requirement, assessment, approval, PO and accepted GRN; compare pending quantities and stock/report source coverage.'],
    ['5. Close release controls', 'Reconcile hosted/local migration ancestry, review operation-level permissions, confirm secret rotation where historically exposed, run integrated regression/concurrency checks and validate deployment/backup/restore ownership.'],
    ['6. Owner UAT and handover', 'Record independently expected numbers and reviewer acceptance; exercise upload, correction, failed-read recovery, rejection, stale edit and export flows; prepare a repeatable operator checklist.'],
], [119,CW-119])
h('Main achievements to preserve')
add('A broad ERP foundation; traceable deterministic engines; reviewed workbook intake; central demand visibility; familiar controlled editing; audit/history; separate proposal and approval stages; authenticated exports; measurable loading improvements; and domain-based team ownership.')
h('Main focus now')
add('Move from feature availability to a consistently validated operating workflow: the same source demand across screens, explicit company configuration, reliable access boundaries, reconciled purchase/receipt evidence and repeatable acceptance checks.')
source('[S3, S5-S8, S13, S14]. Suggested priorities are report recommendations, not newly approved implementation tasks.')

page(11, 'Evidence register and reading guide', 'Internal project sources reviewed for this report. Paths are relative to the C:/KN repository.')
refs = [
    ('S1', 'Scope, architecture, rules and ownership', 'docs/01_PROJECT_SCOPE.md through 12_AI_TASK_TEMPLATE.md; docs/team/; docs/adr/'),
    ('S2', 'Chronology and current snapshot', 'Git history, 30 Sep - 17 Oct 2026; HEAD 760785b; local changes reviewed on 17 Oct.'),
    ('S3', 'Dated context and verified workflow notes', 'docs/PROJECT_CONTEXT.md (dated sections; later decisions supersede earlier snapshots).'),
    ('S4', 'Authentication and security contract', 'docs/13_AUTH_RBAC_CONTRACT.md; docs/10_TESTING_SECURITY_DOD.md'),
    ('S5', 'Central planning and purchase compatibility', 'docs/24_CENTRAL_BASIC_PLANNING_CONTRACT.md (includes 17 Oct owner-selected resolution).'),
    ('S6', 'Inventory, projection and reorder', 'docs/17_CENTRAL_INVENTORY_CONTRACT.md; 18_PROJECTED_INVENTORY_CONTRACT.md; 19_REORDER_TIMING_CONTRACT.md'),
    ('S7', 'Recommendation, purchase orders and receipts', 'docs/20_PURCHASE_RECOMMENDATION_CONTRACT.md; 21_PURCHASE_ORDER_CONTRACT.md; 22_GRN_INVENTORY_CONTRACT.md'),
    ('S8', 'Inventory and purchase reporting', 'docs/23_INVENTORY_PURCHASE_REPORTS_CONTRACT.md'),
    ('S9', 'Spreadsheet editing and safe deletion', 'docs/validation/STOCK_GRID_EDITING_2026-10-13.md; STOCK_MANAGEMENT_PERIOD_DELETION_2026-10-13.md; STOCK_STATEMENT_PERIOD_DELETION_2026-10-13.md'),
    ('S10', '15 October performance validation', 'docs/validation/PERFORMANCE_RELIABILITY_2026-10-15.md'),
    ('S11', '16 October record loading validation', 'docs/validation/RECORD_LOADING_2026-10-16.md'),
    ('S12', 'Product Master catalog correction', 'docs/validation/PRODUCT_MASTER_CATALOG_2026-10-15.md'),
    ('S13', 'Contributor comparison and earlier merge audit', 'docs/validation/MERGE_REVIEW_2026-10-17.md; current registered routes and Requirement/Purchase source inspected.'),
    ('S14', 'Company numeric acceptance boundary', 'docs/24_INVENTORY_PURCHASE_GOLDEN_CASES.md'),
]
table(['ID', 'SOURCE / PURPOSE'], [(ref, '<b>'+label+'</b><br/>'+escape(path)) for ref,label,path in refs], [36,CW-36], small=True)
add('<b>Interpretation:</b> "implemented" means present in reviewed code/records; "verified" names the documented test or observation; "owner-approved" records the project owner\'s decision and is not company-wide UAT. Test counts overlap. Historical module contracts may describe capabilities whose current screen registration changed during consolidation.', 'SmallReport')

def decorate(c, doc):
    c.saveState()
    c.setStrokeColor(LINE)
    c.setLineWidth(.7)
    c.line(54,H-34,W-54,H-34)
    c.setFillColor(TEAL)
    c.setFont('Arial-Bold',8)
    c.drawString(54,H-25,'KNL  /  CONSUMABLE PLANNING ERP')
    c.setFillColor(MUTED)
    c.setFont('Arial',8)
    c.drawRightString(W-54,H-25,'PROJECT PROGRESS  |  17 OCT 2026')
    c.line(54,39,W-54,39)
    c.drawString(54,25,'Internal project report  |  Based on repository and dated validation records')
    c.drawRightString(W-54,25,f'{doc.page} / 11')
    c.restoreState()

doc = SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=54,leftMargin=54,topMargin=55,bottomMargin=54,
    title='KNL Consumable ERP - Overall Project Report', author='KNL Project Team', subject='Project progress from 30 September to 17 October 2026')
doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
reader=PdfReader(OUT)
assert len(reader.pages)==11, f'Unexpected page count: {len(reader.pages)}'
for n, pg in enumerate(reader.pages,1):
    text=pg.extract_text()
    assert text and len(text)>300, f'Unexpected empty page {n}'
    assert f'{n} / 11' in text, f'Missing footer page {n}'
print(f'Created {OUT} | pages={len(reader.pages)} | bytes={OUT.stat().st_size}')
