#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

function usage() {
  return [
    "Usage: render_w1_r3_figures_png.cjs [--repo-root PATH] [--output PATH]",
    "",
    "Render the two canonical corrected-R3 SVGs and the declared W1 workflow",
    "correction as hash-bound PNG presentation assets. No experiment is rerun.",
  ].join("\n");
}

function parseArgs(argv) {
  const options = { repoRoot: null, output: null };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") {
      process.stdout.write(`${usage()}\n`);
      process.exit(0);
    }
    if (arg === "--repo-root" || arg === "--output") {
      if (index + 1 >= argv.length) throw new Error(`Missing value for ${arg}`);
      const value = path.resolve(argv[index + 1]);
      if (arg === "--repo-root") options.repoRoot = value;
      else options.output = value;
      index += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${arg}\n${usage()}`);
  }
  return options;
}

function digest(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function replaceRequired(text, oldValue, newValue) {
  if (!text.includes(oldValue)) {
    throw new Error(`Expected workflow text not found: ${oldValue}`);
  }
  return text.replace(oldValue, newValue);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const sharp = require("sharp");
  const repo = options.repoRoot || path.resolve(__dirname, "../../..");
  const sourceDir = path.join(
    repo,
    "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis"
  );
  const outputDir = options.output || path.join(
      repo,
      "docs/paper/generated/distinction_v1/11_w1_manuscript"
    );
  const names = ["figure_r3_h3_translation", "figure_r3_h4_dominance"];
  fs.mkdirSync(outputDir, { recursive: true });

  const sources = {};
  const artifacts = {};
  for (const name of names) {
    const input = path.join(sourceDir, `${name}.svg`);
    const output = path.join(outputDir, `${name}.png`);
    if (!fs.existsSync(input)) throw new Error(`Missing canonical R3 figure: ${input}`);
    await sharp(input, { density: 220 })
      .flatten({ background: "#ffffff" })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toFile(output);
    sources[path.relative(repo, input)] = digest(input);
    artifacts[path.basename(output)] = digest(output);
  }

  // The historical workflow asset predates corrected R3. Preserve that source
  // unchanged and create a W1-only corrected rendering with an explicit,
  // deterministic text transformation.
  const workflowInput = path.join(
    repo,
    "docs/paper/generated/paper_assets_v1/figures/figure01_research_workflow.svg"
  );
  const workflowOutput = path.join(outputDir, "figure_w1_research_workflow.png");
  if (!fs.existsSync(workflowInput)) {
    throw new Error(`Missing historical workflow source: ${workflowInput}`);
  }
  let workflowSvg = fs.readFileSync(workflowInput, "utf8");
  workflowSvg = replaceRequired(
    workflowSvg,
    '<tspan x="913.00" dy="22">timing</tspan>',
    '<tspan x="913.00" dy="22">init group</tspan>'
  );
  workflowSvg = replaceRequired(
    workflowSvg,
    '<tspan x="913.00" dy="0">120 formal rollouts</tspan>',
    '<tspan x="913.00" dy="0">80 formal rollouts</tspan>'
  );
  workflowSvg = replaceRequired(
    workflowSvg,
    '<tspan x="155.00" dy="22">arrival timing, solver feasibility and supervisor intervention. Tested Transformers use sequence context but do not beat</tspan>',
    '<tspan x="155.00" dy="22">target style and executed operating point. Tested Transformers use sequence context but do not beat simple B1 adaptation,</tspan>'
  );
  workflowSvg = replaceRequired(
    workflowSvg,
    '<tspan x="155.00" dy="22">simple B1 adaptation.</tspan>',
    '<tspan x="155.00" dy="22">and adaptive risk does not universally dominate fixed controls.</tspan>'
  );
  workflowSvg = replaceRequired(
    workflowSvg,
    'Primary evidence: Day8 frozen test + Day10 nominal + Day11/12 timing synthesis | Day13 is sensitivity only',
    'Primary evidence: frozen test + corrected R3 (80 rollouts) | legacy timing and sensitivity analyses are diagnostic only'
  );
  await sharp(Buffer.from(workflowSvg), { density: 220 })
    .flatten({ background: "#ffffff" })
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toFile(workflowOutput);
  sources[path.relative(repo, workflowInput)] = digest(workflowInput);
  artifacts[path.basename(workflowOutput)] = digest(workflowOutput);

  const completion = {
    schema_version: "w1_manuscript_figures_v2",
    status: "pass",
    role: "canonical_a2_format_conversion_plus_declared_workflow_correction",
    workflow_correction: {
      original_asset_preserved: true,
      formal_rollouts: { historical_label: 120, corrected_r3: 80 },
      factorial_axis: "initialisation_group_not_legacy_timing",
      evidence_boundary: "corrected_r3_primary_legacy_day10_to_13_diagnostic",
    },
    source_sha256: sources,
    artifacts,
  };
  fs.writeFileSync(
    path.join(outputDir, "W1_R3_FIGURES_COMPLETE.json"),
    JSON.stringify(completion, null, 2) + "\n"
  );
  process.stdout.write(JSON.stringify({ status: "pass", figure_count: names.length + 1 }, null, 2) + "\n");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
