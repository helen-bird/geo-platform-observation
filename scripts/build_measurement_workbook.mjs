// Run with Node and @oai/artifact-tool available. The public checkout is the first argument.
// Usage: node build_measurement_workbook.mjs REPO_ROOT OUTPUT.xlsx [PREVIEW_DIR] [TEST_DIR]
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const [repo, output, previewDir, testDir] = process.argv.slice(2);
assert(repo && output, 'Provide the public checkout path and the XLSX output path.');
const book = Workbook.create();
const navy = '#17343D';
const teal = '#176A76';
const pale = '#EAF4F4';
const input = '#F2F7FB';
const ink = '#21353E';
const blue = '#176184';
const line = '#DCE7E8';
const alert = { fill: '#FCE9D8', font: { color: '#873C19', bold: true } };
const waves = ['Baseline', 'Retest 1', 'Retest 2'];
const strata = ['Single', 'Medium', 'High'];
const outcomes = ['Selected', 'Failed', 'Excluded'];
const tri = ['Yes', 'No', 'Unknown'];
const coverage = ['Full', 'Partial', 'Missing', 'Unknown'];
const roles = ['Body', 'Inline', 'Main', 'More', 'Search'];
const firstInputRow = 5;
const attemptEnd = 304;
const sourceEnd = 804;
const competitorEnd = 404;
const publicSite = 'https://helen-bird.github.io/geo-platform-observation';
const labPath = 'stages/09-visibility-baseline';
const cohortSHA = '15b222bddb55255ca67cc9409e126834450fb029';
const labData = `${labPath}/data/observations.jsonl`;
const core = await fs.readFile(path.resolve(repo, labData), 'utf8');
const m2Rows = core.trimEnd().split('\n').flatMap((line, index) => {
  const data = JSON.parse(line);
  return data.prompt_id === 'M2' ? [{ ...data, line: index + 1 }] : [];
});
const m2Prompts = JSON.parse(await fs.readFile(path.resolve(repo, labPath, 'data/prompts.json'), 'utf8'));
const grok = JSON.parse(execFileSync('python3', [path.resolve(repo, 'scripts/build_measurement_resources.py'), '--example-json'], { encoding: 'utf8' }));

const setup = sheet('Start here', [203, 268, 268, 268]);
const results = sheet('Results', [100, 234, 83, 83, 90, 99, 133, 112]);
const attempts = sheet('Attempts', [202, 99, 95, 103, 144, 106, 183, 92, 86, 122, 109, 118, 124, 117, 92, 160, 280, 280, 255]);
const sources = sheet('Sources', [202, 144, 100, 310, 102, 150, 310]);
const competitors = sheet('Competitors', [210, 140, 220, 210, 120, 290, 104, 90, 108]);
const prompts = sheet('Prompt library', [186, 597, 230]);
const examples = sheet('Examples', [100, 130, 83, 113, 131, 129, 159, 278, 278]);

function sheet(name, widths) {
  const current = book.worksheets.add(name);
  current.showGridLines = false;
  widths.forEach((width, index) => {
    const letter = String.fromCharCode(65 + index);
    current.getRange(`${letter}:${letter}`).format.columnWidthPx = width;
  });
  return current;
}

function set(sheet, address, value) { sheet.getRange(address).values = [[value]]; }
function formula(sheet, address, value) { sheet.getRange(address).formulas = [[`=${value}`]]; }
function val(sheet, address) { return sheet.getRange(address).values[0][0] ?? ''; }
function list(sheet, address, values) { sheet.getRange(address).dataValidation = { rule: { type: 'list', values } }; }
function counted(range) { return `SUMPRODUCT(--(${range}<>""))`; }

function band(sheet, address, value, kind = 'note', height = 30) {
  const range = sheet.getRange(address);
  range.merge();
  range.values = [[value]];
  range.format.rowHeightPx = height;
  range.format.wrapText = true;
  range.format.verticalAlignment = 'center';
  range.format.fill = kind === 'title' ? navy : pale;
  range.format.font = { name: 'Aptos', size: kind === 'title' ? 15 : 11, color: kind === 'title' ? '#FFFFFF' : navy, bold: kind !== 'note' };
}

function grid(sheet, header, body, values) {
  const heading = sheet.getRange(header);
  heading.values = [values];
  heading.format.fill = teal;
  heading.format.font = { name: 'Aptos', color: '#FFFFFF', bold: true, size: 10 };
  heading.format.rowHeightPx = 36;
  heading.format.verticalAlignment = 'center';
  heading.format.wrapText = true;
  const data = sheet.getRange(body);
  data.format.font = { name: 'Aptos', color: ink, size: 10 };
  data.format.rowHeightPx = 24;
  data.format.verticalAlignment = 'center';
  data.format.borders = { insideHorizontal: { style: 'thin', color: line } };
}

function shadeInputs(sheet, address) {
  const range = sheet.getRange(address);
  range.format.fill = input;
  range.format.font = { name: 'Aptos', color: blue, size: 10 };
}

function flag(sheet, address, condition) {
  sheet.getRange(address).conditionalFormats.addCustom(condition, alert);
}

function entryTable(sheet, address, name) {
  const table = sheet.tables.add(address, true, name);
  table.style = 'TableStyleLight9';
  table.showFilterButton = true;
  sheet.freezePanes.freezeRows(4);
}

function region(sheet, col, end) { return `'${sheet}'!$${col}$${firstInputRow}:$${col}$${end}`; }
function log(col) { return region('Attempts', col, attemptEnd); }
function source(col) { return region('Sources', col, sourceEnd); }
function criteria(cell) { return `"="&SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(${cell},"~","~~"),"*","~*"),"?","~?")`; }
function invalid(cell, allowed, blankOK = false) {
  return `AND(${[...allowed.map(value => `${cell}<>"${value}"`), ...(blankOK ? [`${cell}<>""`] : [])].join(',')})`;
}

band(setup, 'A1:D1', 'GEO Visibility Measurement Kit v2.0', 'title', 42);
band(setup, 'A2:D2', 'Free worksheet by Helen Bird · GEO Learning Log. Set up one copy for one buyer question and one target.', 'note', 32);
setup.getRange('A4:A6').values = [['Target and acceptable aliases'], ['Citation ownership rule'], ['Question ID or study label (optional)']];
setup.getRange('A4:A6').format.wrapText = true;
setup.getRange('A4:D6').format.rowHeightPx = 36;
setup.getRange('A4:D6').format.verticalAlignment = 'center';
for (const row of [4, 5, 6]) {
  setup.getRange(`B${row}:D${row}`).merge();
  setup.getRange(`B${row}:D${row}`).format.wrapText = true;
  shadeInputs(setup, `B${row}:D${row}`);
}
band(setup, 'A8:D8', '1   Define the target and copy in the exact buyer question. Prompt library gives six starting points. Pick the plan before seeing answers.', 'note', 32);
band(setup, 'A9:D9', '2   Log each attempt, including failures. Use the same slot for a retry and a new attempt ID. Add evidence URLs to Sources by attempt ID.', 'note', 32);
band(setup, 'A10:D10', '3   Check Results. After a documented change, collect one or two new waves with matched settings and verify the version exposed to search.', 'note', 32);
grid(setup, 'A11:D11', 'A12:D24', ['Condition', ...waves]);
setup.getRange('A12:A24').values = [
  'Exact prompt', 'Platform and interface', 'Model label', 'Search setting', 'Session and personalization', 'Language and market',
  'Single-effort slots', 'Medium slots', 'High slots', 'Page version and change', 'Published UTC', 'Version discovery evidence', 'Setup status',
].map(label => [label]);
setup.getRange('A12:A24').format.wrapText = true;
setup.getRange('A12:D12').format.rowHeightPx = 64;
setup.getRange('A16:D16').format.rowHeightPx = 38;
setup.getRange('A21:D23').format.rowHeightPx = 38;
shadeInputs(setup, 'B12:D23');
setup.getRange('B12:D23').format.wrapText = true;
setup.getRange('B22:D22').setNumberFormat('@');
set(setup, 'A25', 'Fixed effort for Single');
shadeInputs(setup, 'B25:D25');
setup.getRange('A25:D25').format.wrapText = true;
setup.getRange('A25:D25').format.rowHeightPx = 35;
for (const letter of ['B', 'C', 'D']) {
  const planCells = [18, 19, 20].map(row => `${letter}${row}`);
  const badPlan = planCells.map(cell => `AND(${cell}<>"",IFERROR(OR(NOT(ISNUMBER(${cell})),${cell}<0,INT(${cell})<>${cell}),TRUE))`);
  const needed = [`LEN(TRIM($B$4))=0`, `LEN(TRIM($B$5))=0`, ...[12, 13, 14, 15, 16, 17].map(r => `LEN(TRIM(${letter}${r}))=0`)];
  const issues = [
    ...needed, ...badPlan, `SUM(${letter}18:${letter}20)=0`,
    `AND(${letter}18>0,OR(SUM(${letter}19:${letter}20)>0,LEN(TRIM(${letter}25))=0))`,
    `AND(N(${letter}18)=0,LEN(TRIM(${letter}25))>0)`,
    `SUM(${letter}18:${letter}20)>${attemptEnd - firstInputRow + 1}`,
  ];
  formula(setup, `${letter}24`, `IF(COUNTA(${letter}12:${letter}23,${letter}25)=0,"Not set",IF(OR(${issues.join(',')}),"Check setup","Ready"))`);
}
flag(setup, 'B24:D24', 'B24="Check setup"');
band(setup, 'A26:D26', 'Use Single with its exact fixed effort or write “not exposed” if the interface has no effort control. Use Medium and High when you plan separate strata. Limits: 300 attempts, 800 sources, 400 competitor rows.', 'note', 37);
band(setup, 'A27:D27', 'To migrate v1, map Follow-up to Retest 1, reuse the original IDs and exact settings, and copy values only. Recode unsupported metrics as Unknown until you inspect their evidence.', 'note', 37);
band(setup, 'A28:D28', 'Guide and coding method: ' + publicSite + '/learning-hub/measurement/', 'note', 30);

band(attempts, 'A1:H1', 'Attempts', 'title', 40);
band(attempts, 'A2:H2', 'One row per attempt. Use UTC and save the full answer or its private location. Give each attempt a unique ID.', 'note', 32);
band(attempts, 'A3:H3', 'Enter only in blue columns B:S, rows 5–304. Scroll right for judgments and proof. Keep failed or excluded attempts even after a replacement.', 'note', 32);
grid(attempts, 'A4:S4', `A5:S${attemptEnd}`, ['Row check', 'Wave', 'Effort', 'Slot ID', 'Attempt ID', 'Disposition', 'Submitted UTC', 'Search seen?', 'Mention', 'Recommendation', 'Strict citation', 'Observed citation', 'Main panel', 'More panel', 'More exposure', 'Version seen', 'Saved answer / evidence', 'Coding evidence', 'Notes or next action']);
shadeInputs(attempts, `B5:S${attemptEnd}`);
for (const [col, values] of Object.entries({ B: waves, C: strata, F: outcomes, H: tri, I: tri, J: tri, K: tri, L: tri, M: coverage, N: coverage, O: tri })) {
  list(attempts, `${col}5:${col}${attemptEnd}`, values);
}
attempts.getRange(`D5:E${attemptEnd}`).setNumberFormat('@');
attempts.getRange(`G5:G${attemptEnd}`).setNumberFormat('@');
entryTable(attempts, `A4:S${attemptEnd}`, 'AttemptLog');
flag(attempts, `A5:A${attemptEnd}`, '$A5<>""');

band(sources, 'A1:G1', 'Sources', 'title', 40);
band(sources, 'A2:G2', 'One row per source URL and role. Reuse the Attempt ID. Add the evidence that supports the ownership judgment or version.', 'note', 32);
band(sources, 'A3:G3', 'Use Body or Inline for attributable final citations, Main for primary sources, More for extra sources and Search for retrieval evidence. Use blue rows 5–804.', 'note', 32);
grid(sources, 'A4:G4', `A5:G${sourceEnd}`, ['Row check', 'Attempt ID', 'Source role', 'Exact source URL', 'Target match?', 'Version seen', 'Relevant claim or evidence']);
shadeInputs(sources, `B5:G${sourceEnd}`);
list(sources, `C5:C${sourceEnd}`, roles);
list(sources, `E5:E${sourceEnd}`, tri);
sources.getRange(`B5:B${sourceEnd}`).setNumberFormat('@');
entryTable(sources, `A4:G${sourceEnd}`, 'SourceLog');
flag(sources, `A5:A${sourceEnd}`, '$A5<>""');

function checked(conditions, valid = '""') {
  return conditions.reduceRight((later, [test, message]) => `IF(${test},"${message}",${later})`, valid);
}

function waveCell(r, row) {
  return `INDEX('Start here'!$B$${row}:$D$${row},1,MATCH(B${r},'Start here'!$B$11:$D$11,0))`;
}

attempts.getRange(`A5:A${attemptEnd}`).formulas = Array.from({ length: attemptEnd - 4 }, (_, i) => {
  const r = i + 5;
  const roleHits = role => `COUNTIFS(${source('B')},${criteria(`E${r}`)},${source('C')},"${role}",${source('E')},"Yes")`;
  const strict = `(${roleHits('Body')}+${roleHits('Inline')})`;
  const observed = `(${strict}+${roleHits('Main')})`;
  const positive = [strict, observed, roleHits('More')];
  const verdicts = ['K', 'L', 'O'];
  const selectedChecks = [
    ...['H', 'I', 'J', 'K', 'L', 'O'].map(col => [invalid(`${col}${r}`, tri), `Check ${col} score`]),
    ...['M', 'N'].map(col => [invalid(`${col}${r}`, coverage), `Check ${col} coverage`]),
    [`AND(N${r}<>"Full",O${r}="No")`, 'More No needs full panel'],
    [`AND(OR(N${r}="Unknown",N${r}="Missing"),O${r}="Yes")`, 'Record panel coverage'],
    [`LEN(TRIM(Q${r}))=0`, 'Add answer evidence'],
    ...positive.map((num, i) => [`(${verdicts[i]}${r}="Yes")<>(${num}>0)`, `Check ${verdicts[i]} source match`]),
  ];
  const unselectedChecks = [
    ...['H', 'I', 'J', 'K', 'L', 'O'].map(col => [invalid(`${col}${r}`, tri, true), `Check ${col} value`]),
    ...['M', 'N'].map(col => [invalid(`${col}${r}`, coverage, true), `Check ${col} coverage`]),
  ];
  const statuses = checked([
    [invalid(`B${r}`, waves), 'Check wave'],
    [invalid(`C${r}`, strata), 'Check effort'],
    [`${waveCell(r, 24)}<>"Ready"`, 'Complete wave setup'],
    [`IF(C${r}="Single",${waveCell(r, 18)},IF(C${r}="Medium",${waveCell(r, 19)},${waveCell(r, 20)}))<=0`, 'Effort not in plan'],
    [`OR(LEN(TRIM(D${r}))=0,LEN(TRIM(E${r}))=0)`, 'Add slot and attempt IDs'],
    [invalid(`F${r}`, outcomes), 'Check disposition'],
    [`OR(LEN(G${r})<20,MID(G${r},5,1)<>"-",MID(G${r},8,1)<>"-",MID(G${r},11,1)<>"T",MID(G${r},14,1)<>":",MID(G${r},17,1)<>":",RIGHT(G${r},1)<>"Z")`, 'Use ISO timestamp in UTC'],
    [`COUNTIF(${log('E')},${criteria(`E${r}`)})>1`, 'Duplicate attempt ID'],
    [`AND(F${r}="Selected",COUNTIFS(${log('B')},B${r},${log('C')},C${r},${log('D')},${criteria(`D${r}`)},${log('F')},"Selected")>1)`, 'Duplicate selected slot'],
  ], `IF(F${r}="Selected",${checked(selectedChecks)},${checked(unselectedChecks)})`);
  return [`=IFERROR(IF(COUNTA(B${r}:S${r})=0,"",${statuses}),"Check pasted input")`];
});

sources.getRange(`A5:A${sourceEnd}`).formulas = Array.from({ length: sourceEnd - 4 }, (_, i) => {
  const r = i + 5;
  return [`=IFERROR(IF(COUNTA(B${r}:G${r})=0,"",${checked([
    [`OR(LEN(TRIM(B${r}))=0,COUNTIF(${log('E')},${criteria(`B${r}`)})<>1)`, 'Check parent attempt'],
    [invalid(`C${r}`, roles), 'Check source role'],
    [`OR(D${r}<>TRIM(D${r}),ISNUMBER(SEARCH(" ",D${r})),AND(LEFT(D${r},8)<>"https://",LEFT(D${r},7)<>"http://"),LEN(D${r})<10)`, 'Add HTTP(S) source URL'],
    [invalid(`E${r}`, tri), 'Check target match'],
  ])}),"Check pasted input")`];
});

const rival = col => region('Competitors', col, competitorEnd);
band(competitors, 'A1:F1', 'Competitor recommendations', 'title', 40);
band(competitors, 'A2:F2', 'Record actively recommended alternatives. Use one row per selected answer and standardised name. Preserve the exact text and list position where apparent.', 'note', 32);
band(competitors, 'A3:F3', 'Enter in blue columns B:F, rows 5–404. Reuse the Attempt ID. Enter “unranked” when the answer does not establish a position.', 'note', 32);
grid(competitors, 'A4:I4', `A5:I${competitorEnd}`, ['Row check', 'Attempt ID', 'Name as written', 'Standardised name', 'First position', 'Recommendation evidence', 'Wave', 'Effort', 'Disposition']);
shadeInputs(competitors, `B5:F${competitorEnd}`);
competitors.getRange(`B5:B${competitorEnd}`).setNumberFormat('@');
entryTable(competitors, `A4:I${competitorEnd}`, 'CompetitorLog');
flag(competitors, `A5:A${competitorEnd}`, '$A5<>""');
for (const [column, field] of [['G', 'B'], ['H', 'C'], ['I', 'F']]) {
  competitors.getRange(`${column}5:${column}${competitorEnd}`).formulas = Array.from({ length: competitorEnd - 4 }, (_, i) => {
    const r = i + 5;
    return [`=IF(B${r}="","",IFERROR(INDEX(${log(field)},MATCH(${criteria(`B${r}`).slice(4)},${log('E')},0)),""))`];
  });
}
competitors.getRange(`A5:A${competitorEnd}`).formulas = Array.from({ length: competitorEnd - 4 }, (_, i) => {
  const r = i + 5;
  return [`=IFERROR(IF(COUNTA(B${r}:F${r})=0,"",${checked([
    [`OR(LEN(TRIM(B${r}))=0,COUNTIF(${log('E')},${criteria(`B${r}`)})<>1)`, 'Check parent attempt'],
    [`OR(LEN(TRIM(C${r}))=0,LEN(TRIM(D${r}))=0,D${r}<>TRIM(D${r}))`, 'Add both names'],
    [`OR(LEN(TRIM(E${r}))=0,LEN(TRIM(F${r}))=0)`, 'Add position and proof'],
    [`COUNTIFS(${rival('B')},${criteria(`B${r}`)},${rival('D')},${criteria(`D${r}`)})>1`, 'Duplicate name in answer'],
  ])}),"Check pasted input")`];
});

const resultEnd = 33;
band(results, 'A1:H1', 'AI recommendation results', 'title', 42);
band(results, 'A2:H2', 'Use the effort filter to inspect the pooled sample or one planned stratum. Known = Yes + No. Unknown and failed attempts stay out of the rate.', 'note', 32);
set(results, 'A4', 'Effort filter');
set(results, 'B4', 'All');
shadeInputs(results, 'B4');
list(results, 'B4', ['All', ...strata]);
band(results, 'C4:H4', 'Rates show available evidence. Deltas need matched complete plans and equal known counts. Some unknown means the rate still uses a subset.', 'note', 35);
grid(results, 'A6:H6', 'A7:H9', ['Wave', 'Coverage and comparison', 'Planned', 'Selected', 'Failed', 'Excluded', 'Observed search', 'Search unknown']);
grid(results, 'A12:G12', 'A13:G14', ['Input checks', 'Attempts to fix', 'Sources to fix', 'Extra attempts¹', 'Extra sources¹', 'Rivals to fix', 'Extra rivals¹']);
set(results, 'A13', 'Status');
formula(results, 'B13', counted(log('A')));
formula(results, 'C13', counted(source('A')));
formula(results, 'D13', `COUNTA(Attempts!B:S)-COUNTA(Attempts!B1:S${attemptEnd})`);
formula(results, 'E13', `COUNTA(Sources!B:G)-COUNTA(Sources!B1:G${sourceEnd})`);
formula(results, 'F13', counted(rival('A')));
formula(results, 'G13', `COUNTA(Competitors!B:F)-COUNTA(Competitors!B1:F${competitorEnd})`);
formula(results, 'B14', `IF(${invalid('B4', ['All', ...strata])},"Check effort filter",IF(SUM(B13:G13)>0,"Fix inputs first","Ready"))`);
flag(results, 'B14', 'B14<>"Ready"');
band(results, 'A16:H16', '¹ Extra counts filled cells outside the input areas. Move every value into the blue range before using the rates. Open the log’s Row check column to find the issue.', 'note', 34);
grid(results, 'A18:H18', `A19:H${resultEnd}`, ['Wave', 'Outcome', 'Yes', 'Known', 'Unknown', 'Rate', 'Δ vs baseline (pp)', 'Evidence']);

function attemptCount(wave, effort, pairs = []) {
  return `COUNTIFS(${[log('B'), wave, ...(effort ? [log('C'), effort] : []), ...pairs.flatMap(([col, value]) => [log(col), `"${value}"`])].join(',')})`;
}

function filteredCount(wave, pairs) {
  return `IF($B$4="All",${attemptCount(wave, null, pairs)},${attemptCount(wave, '$B$4', pairs)})`;
}

function readyOnly(expression, setupCol) {
  return `IF(OR($B$14<>"Ready",'Start here'!${setupCol}24<>"Ready"),"",${expression})`;
}

const measures = [
  ['Recommendation', 'J'], ['Mention', 'I'], ['Strict citation', 'K'],
  ['Observed citation (Lab #09)', 'L'], ['More exposure', 'O'],
];

for (const [waveIndex, wave] of waves.entries()) {
  const config = ['B', 'C', 'D'][waveIndex];
  const row = 7 + waveIndex;
  const configRef = `'Start here'!${config}`;
  const waveRef = `$A${row}`;
  set(results, `A${row}`, wave);
  const plan = `IF($B$4="All",SUM(${configRef}18:${config}20),IF($B$4="Single",N(${configRef}18),IF($B$4="Medium",N(${configRef}19),N(${configRef}20))))`;
  formula(results, `C${row}`, readyOnly(plan, config));
  for (const [column, filters] of Object.entries({ D: [['F', 'Selected']], E: [['F', 'Failed']], F: [['F', 'Excluded']], G: [['F', 'Selected'], ['H', 'Yes']], H: [['F', 'Selected'], ['H', 'Unknown']] })) {
    formula(results, `${column}${row}`, readyOnly(filteredCount(waveRef, filters), config));
  }
  const settingsDiffer = waveIndex ? [
    ...[12, 13, 14, 15, 16, 17].map(i => `NOT(EXACT(${configRef}${i},'Start here'!B${i}))`),
    `AND(N(${configRef}18)>0,N('Start here'!B18)>0,NOT(EXACT(${configRef}25,'Start here'!B25)))`,
  ] : [];
  const planDiffers = waveIndex ? strata.map((_, i) => `N(${configRef}${18 + i})<>N('Start here'!B${18 + i})`) : [];
  const incomplete = strata.map((effort, i) => `${attemptCount(waveRef, `"${effort}"`, [['F', 'Selected']])}<>N(${configRef}${18 + i})`);
  formula(results, `B${row}`, checked([
    [`$B$14<>"Ready"`, 'Fix inputs listed below'],
    [`${configRef}24<>"Ready"`, 'Complete setup'],
    ...(waveIndex ? [[`OR(${settingsDiffer.join(',')})`, 'Different prompt or settings'], [`OR(${planDiffers.join(',')})`, 'Different planned effort mix']] : []),
    [`C${row}=0`, 'Effort not planned'],
    [`IF($B$4="All",OR(${incomplete.join(',')}),C${row}<>D${row})`, 'Planned count differs'],
    ...(waveIndex ? [['$B$7<>"Baseline complete"', 'Waiting for baseline']] : []),
  ], waveIndex ? '"Comparable"' : '"Baseline complete"'));
  for (const [measureIndex, [label, column]] of measures.entries()) {
    const dest = 19 + waveIndex * measures.length + measureIndex;
    const baseline = 19 + measureIndex;
    results.getRange(`A${dest}:B${dest}`).values = [[wave, label]];
    const known = filteredCount(waveRef, [['F', 'Selected'], [column, 'No']]);
    formula(results, `C${dest}`, readyOnly(filteredCount(waveRef, [['F', 'Selected'], [column, 'Yes']]), config));
    formula(results, `D${dest}`, readyOnly(`C${dest}+${known}`, config));
    formula(results, `E${dest}`, readyOnly(`D${row}-D${dest}`, config));
    formula(results, `F${dest}`, `IF(OR(D${dest}="",D${dest}=0),"",C${dest}/D${dest})`);
    if (waveIndex) formula(results, `G${dest}`, `IF(OR(B${row}<>"Comparable",D${dest}="",D${dest}=0,D${baseline}="",D${dest}<>D${baseline}),"",100*(F${dest}-F${baseline}))`);
    formula(results, `H${dest}`, `IF(D${dest}="","",IF(D${dest}=0,"No known scores",IF(E${dest}>0,"Some unknown","All known")))`);
  }
}
results.getRange(`F19:F${resultEnd}`).setNumberFormat('0.0%');
results.getRange(`G19:G${resultEnd}`).setNumberFormat('+0.0;-0.0;0.0');
band(results, 'A35:H35', 'A zero is supported only when a known answer was scored No. Changes in observed rates do not isolate the effect of a webpage edit.', 'note', 35);
band(results, 'A36:H36', 'Strict citation = final Body or Inline link. Observed citation adds the Main panel. More is separate. See the guide for coverage and ownership rules.', 'note', 34);
band(results, 'A38:H38', 'Competitor lookup', 'section', 32);
set(results, 'A39', 'Exact name');
shadeInputs(results, 'B39');
band(results, 'C39:H39', 'Enter one name as standardised in Competitors. Counts use selected answers in the current effort filter.', 'note', 35);
grid(results, 'A41:D41', 'A42:D42', ['Count', ...waves]);
set(results, 'A42', 'Answers');
for (const col of ['B', 'C', 'D']) {
  const common = [rival('D'), criteria('$B$39'), rival('G'), `${col}41`, rival('I'), '"Selected"'];
  formula(results, `${col}42`, `IF(OR($B$14<>"Ready",LEN(TRIM($B$39))=0),"",IF($B$4="All",COUNTIFS(${common.join(',')}),COUNTIFS(${common.join(',')},${rival('H')},$B$4)))`);
}

band(prompts, 'A1:C1', 'Prompt library', 'title', 40);
band(prompts, 'A2:C2', 'Pick one question that a potential user would ask. Adapt it before setup, then keep the exact wording for each wave.', 'note', 32);
grid(prompts, 'A4:C4', 'A5:C10', ['Intent', 'Starting prompt', 'How to use it']);
prompts.getRange('A5:C10').values = [
  ['Category', 'What free tools help a solo founder schedule customer interviews?', 'Natural discovery'],
  ['Category', 'Which lightweight bug trackers work well for a two-person software team?', 'Natural discovery'],
  ['Problem', 'How can a one-person SaaS team track failed payments without a paid dashboard?', 'Natural discovery'],
  ['Problem', 'How can I collect and prioritise feature requests from early customers on a small budget?', 'Natural discovery'],
  ['Named comparison', 'What should I check before choosing between [my product] and [alternative] for [task]?', 'Diagnostic only. Replace brackets.'],
  ['Named comparison', 'Which features of [my product] and [alternative] help a solo founder with [task]?', 'Diagnostic only. Replace brackets.'],
];
prompts.getRange('A5:C10').format.rowHeightPx = 37;
prompts.getRange('A5:C10').format.wrapText = true;

band(examples, 'A1:G1', 'Worked examples', 'title', 40);
band(examples, 'A2:G2', 'These historical and simulated records are separate from the blank Attempts and Sources tabs. They never enter live Results.', 'note', 36);
grid(examples, 'A4:G4', 'A5:G7', ['Sample', 'Scope', 'Answers', 'Mention', 'Recommendation', 'Citation', 'More']);
examples.getRange('A5:C7').values = [['Real Grok', 'Creator', grok.records.length], ['Real M2', 'Guide or worksheet', m2Rows.length], ['Simulated', 'Training demo', null]];
const countExample = (col, start, end) => {
  const range = `${col}${start}:${col}${end}`;
  const yes = `COUNTIF(${range},"Yes")`;
  const known = `(${yes}+COUNTIF(${range},"No"))`;
  const unknown = `COUNTIF(${range},"Unknown")`;
  return `IF(${known}=0,"No rate",${yes}&"/"&${known})&IF(${unknown}=0,""," · "&${unknown}&" unknown")`;
};
for (const [cell, col, start, end] of [['D5', 'C', 12, 21], ['E5', 'D', 12, 21], ['F5', 'E', 12, 21], ['D6', 'C', 28, 57], ['E6', 'D', 28, 57], ['F6', 'E', 28, 57], ['G6', 'F', 28, 57]]) {
  formula(examples, cell, countExample(col, start, end));
}
set(examples, 'G5', 'Not measured');
examples.getRange('A5:G7').format.wrapText = true;
examples.getRange('A5:G7').format.rowHeightPx = 40;
band(examples, 'A9:I9', 'Actual  ·  Grok creator discovery  ·  10 responses, no retest', 'section', 34);
band(examples, 'A10:I10', grok.prompt, 'note', 32);
grid(examples, 'A11:I11', 'A12:I21', ['Slot', 'Platform', 'Mention', 'Recommendation', 'Final citation', 'Search seen?', 'Panel items', 'Saved answer URL', 'Coding URL']);
examples.getRange('A12:I21').values = grok.records.map(x => [x.slot, 'Grok web', x.mention, x.recommendation, x.citation, 'Yes', x.panel_count, x.answer, x.measurement]);
band(examples, 'A22:I22', 'The target was Helen Bird as a person. A creator being named or recommended did not establish an attributable final link. All 10 final citation judgments were Unknown.', 'note', 33);
band(examples, 'A24:I24', 'Actual  ·  Lab #09 M2 resource discovery  ·  30 responses, no retest', 'section', 34);
band(examples, 'A25:I25', m2Prompts.find(x => x.id === 'M2').text, 'note', 32);
band(examples, 'A26:I26', 'ChatGPT web, GPT-6, Medium and High with 15 responses each. Citation here means captured Body/Inline/Main links. For More, 23 complete panels could be judged and seven could not.', 'note', 34);
grid(examples, 'A27:I27', 'A28:I57', ['Answer ID', 'Effort', 'Mention', 'Recommendation', 'Observed citation', 'More exposure', 'Full More panel?', 'Published coding and line', 'Top recommendations (sample)']);
const coded = n => n === 1 ? 'Yes' : n === 0 ? 'No' : 'Unknown';
examples.getRange('A28:I57').values = m2Rows.map(x => [
  x.id, x.effort, coded(x.scores.mention), coded(x.scores.recommendation), coded(x.scores.citation), coded(x.target_in_more), x.panel_coverage === 'complete' ? 'Yes' : 'No',
  `https://github.com/helen-bird/geo-platform-observation/blob/${cohortSHA}/${labData}#L${x.line}`, x.resources_recommended.slice(0, 3).join(', '),
]);
band(examples, 'A58:I58', `Study protocol, published coding and redacted sources: ${publicSite}/${labPath}/technical-appendix.html`, 'note', 31);
band(examples, 'A60:I60', 'Simulated  ·  Practice reading a report  ·  Never part of the research results', 'section', 34);
grid(examples, 'A61:H61', 'A62:H64', ['Wave', 'Practice target', 'Selected', 'Failed', 'Recommended', 'Known', 'Rate', 'Δ vs baseline (pp)']);
examples.getRange('A62:F64').values = [
  ['Baseline', 'Fictional Acme', 3, 1, 1, 3], ['Retest 1', 'Fictional Acme', 3, 0, 2, 3], ['Retest 2', 'Fictional Acme', 3, 0, 1, 3],
];
for (const row of [62, 63, 64]) formula(examples, `G${row}`, `E${row}/F${row}`);
for (const row of [63, 64]) formula(examples, `H${row}`, `100*(G${row}-$G$62)`);
examples.getRange('G62:G64').setNumberFormat('0.0%');
examples.getRange('H63:H64').setNumberFormat('+0.0;-0.0;0.0');
band(examples, 'A66:I66', 'Action example: first retest rose by one answer, then returned to the baseline. Record both results and keep collecting before claiming a sustained change.', 'note', 34);

function verify(sheet, expected) {
  for (const [address, value] of Object.entries(expected)) {
    const actual = val(sheet, address);
    if (typeof value === 'number' && typeof actual === 'number') assert.ok(Math.abs(actual - value) < 1e-9, `${sheet.name}!${address} expected ${value}, got ${actual}`);
    else assert.equal(actual, value, `${sheet.name}!${address}`);
  }
}

async function save(filename) { await (await SpreadsheetFile.exportXlsx(book)).save(filename); }

function setupFixture() {
  set(setup, 'B4', 'Acme');
  set(setup, 'B5', 'Owned pages at acme.example');
  for (const col of ['B', 'C', 'D']) {
    setup.getRange(`${col}12:${col}23`).values = ['Which free tools help with invoices?', 'Web', 'Fixture model', 'Auto', 'Fresh', 'English', 3, null, null, 'v2', '2026-11-01T12:00:00Z', 'Fixture'].map(x => [x]);
    set(setup, `${col}25`, 'Medium');
  }
  const exampleRows = [
    ['S1', 'A1', 'Selected', 'Yes', 'Yes', 'Yes', 'No', 'Yes', 'Full', 'Full', 'Yes', 'Fixture answer A1'],
    ['S2', 'B1', 'Failed', null, null, null, null, null, null, null, null, null],
    ['S2', 'B2', 'Selected', 'Yes', 'No', 'No', 'No', 'No', 'Full', 'Full', 'No', 'Fixture answer B2'],
    ['S3', 'C1', 'Selected', 'Unknown', 'No', 'No', 'No', 'No', 'Missing', 'Missing', 'Unknown', 'Fixture answer C1'],
  ];
  for (const [index, wave] of waves.entries()) {
    const suffix = index ? `-${index}` : '';
    const rows = exampleRows.map(([slot, id, status, search, mention, rec, strict, obs, main, moreCoverage, more, evidence]) => [
      wave, 'Single', slot, id + suffix, status, '2026-11-09T11:02:30Z', search, mention, rec, strict, obs, main, moreCoverage, more, null, evidence,
    ]);
    const start = 5 + index * 4;
    attempts.getRange(`B${start}:Q${start + 3}`).values = rows;
    const sourceStart = 5 + index * 2;
    sources.getRange(`B${sourceStart}:E${sourceStart + 1}`).values = [
      [`A1${suffix}`, 'Main', 'https://acme.example/guide', 'Yes'],
      [`A1${suffix}`, 'More', 'https://acme.example/guide', 'Yes'],
    ];
    const rivalStart = 5 + index * 2;
    competitors.getRange(`B${rivalStart}:F${rivalStart + 1}`).values = [
      [`A1${suffix}`, 'Other tool plus', 'Other Tool', 1, 'Fixture proof'],
      [`C1${suffix}`, 'Other Tool', 'Other Tool', 'unranked', 'Fixture proof'],
    ];
  }
  set(results, 'B39', 'Other Tool');
}

async function testWorkbook() {
  await fs.mkdir(testDir, { recursive: true });
  setupFixture();
  book.recalculate();
  verify(results, { B7: 'Baseline complete', B8: 'Comparable', B9: 'Comparable', D7: 3, E7: 1, G7: 2, H7: 1, B13: 0, C13: 0, D13: 0, E13: 0, F13: 0, G13: 0, B14: 'Ready', C19: 1, D19: 3, F19: 1 / 3, C21: 0, D21: 3, F21: 0, C22: 1, D22: 3, C23: 1, D23: 2, E23: 1, G24: 0, G29: 0, B42: 2, C42: 2, D42: 2 });
  await save(path.join(testDir, 'comparison.xlsx'));

  set(attempts, 'N12', 'Full');
  set(attempts, 'O12', 'No');
  book.recalculate();
  verify(results, { D28: 3, G28: '', F28: 1 / 3 });
  set(attempts, 'N12', 'Missing');
  set(attempts, 'O12', 'Unknown');

  set(setup, 'C25', 'High');
  set(setup, 'D12', 'Actually a different question');
  book.recalculate();
  verify(results, { B8: 'Different prompt or settings', B9: 'Different prompt or settings', G24: '', G29: '' });
  set(setup, 'C25', 'Medium');
  set(setup, 'D12', 'Which free tools help with invoices?');
  set(setup, 'D18', null);
  set(setup, 'D19', 2);
  set(setup, 'D20', 1);
  set(setup, 'D25', null);
  attempts.getRange('C13:C16').values = [['Medium'], ['Medium'], ['Medium'], ['High']];
  book.recalculate();
  verify(results, { B9: 'Different planned effort mix', D9: 3, G29: '' });
  set(results, 'B4', 'High');
  book.recalculate();
  verify(results, { C7: 0, C9: 1, D9: 1, D29: 1, E33: 1, F33: '' });
  set(results, 'B4', 'All');
  set(attempts, 'B5', 'Basline');
  set(attempts, 'J7', 'Yse');
  set(attempts, 'Q18', 'evidence only');
  set(sources, 'D14', 'https://orphan.example/');
  set(attempts, 'Q901', 'attempt overflow');
  set(sources, 'D9909', 'source overflow');
  set(competitors, 'F1020', 'rival overflow');
  competitors.getRange('B15:F15').values = [['A1', 'Alternative spelling', 'Other Tool', 2, 'Second entry']];
  book.recalculate();
  verify(attempts, { A5: 'Check wave', A7: 'Check J score', A18: 'Check wave' });
  verify(sources, { A14: 'Check parent attempt' });
  verify(competitors, { A5: 'Duplicate name in answer', A15: 'Duplicate name in answer' });
  verify(results, { B13: 3, C13: 1, D13: 1, E13: 1, F13: 2, G13: 1, B14: 'Fix inputs first', F19: '', G24: '', B42: '' });
  await save(path.join(testDir, 'invalid.xlsx'));

  set(attempts, 'B5', 'Baseline');
  set(attempts, 'J7', 'No');
  set(attempts, 'Q18', null);
  set(sources, 'D14', null);
  set(attempts, 'Q901', null);
  set(sources, 'D9909', null);
  set(competitors, 'F1020', null);
  competitors.getRange('B15:F15').values = [[null, null, null, null, null]];
  set(attempts, 'D7', 'S1');
  set(attempts, 'F6', 'Selected');
  book.recalculate();
  verify(attempts, { A5: 'Duplicate selected slot', A7: 'Duplicate selected slot' });
  set(attempts, 'D7', 'S2');
  set(attempts, 'F6', 'Failed');
  set(attempts, 'O8', 'No');
  book.recalculate();
  verify(attempts, { A8: 'More No needs full panel' });
  set(attempts, 'O8', 'Unknown');
  set(attempts, 'E7', 'A1');
  book.recalculate();
  verify(attempts, { A5: 'Duplicate attempt ID', A7: 'Duplicate attempt ID' });
  set(attempts, 'E7', 'B2');
  set(attempts, 'E8', 'A*');
  set(attempts, 'E7', 'AA');
  book.recalculate();
  verify(attempts, { A7: '', A8: '' });
  console.log('Fixture passed: scoped metrics, orphan and overflow checks, pasted scores, duplicates, comparison gates and separate competitor counts.');
}

book.recalculate();
verify(results, { B7: 'Complete setup', B13: 0, C13: 0, D13: 0, E13: 0, F13: 0, G13: 0, F19: '' });
verify(examples, { D5: '8/10', E5: '7/10', F5: 'No rate · 10 unknown', D6: '0/30', E6: '0/30', F6: '0/30', G6: '0/23 · 7 unknown', H63: 100 / 3, H64: 0 });
const errors = await book.inspect({kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NULL!', options: {useRegex: true, maxResults: 20}});
console.log(errors.ndjson);
if (previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  for (const [index, [view, range]] of [[setup, 'A1:D27'], [results, 'A1:H26'], [attempts, 'A1:H9'], [sources, 'A1:G9'], [competitors, 'A1:G9'], [prompts, 'A1:C10'], [examples, 'A1:G7']].entries()) {
    const image = await book.render({ sheetName: view.name, range, scale: 0.9, format: 'png' });
    await fs.writeFile(path.join(previewDir, `sheet-${index + 1}.png`), new Uint8Array(await image.arrayBuffer()));
  }
}
await save(output);
if (testDir) await testWorkbook();
