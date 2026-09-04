#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const sharp = require("sharp");

function sha256File(filename) {
  return crypto.createHash("sha256").update(fs.readFileSync(filename)).digest("hex");
}

async function main() {
  const directory = path.resolve(process.argv[2] || "docs/paper/generated/paper_assets_v1/figures");
  const svgs = fs.readdirSync(directory).filter((name) => /^figure\d+.*\.svg$/.test(name)).sort();
  if (svgs.length !== 8) throw new Error(`Expected 8 SVG figures, found ${svgs.length}`);
  const outputs = {};
  for (const svg of svgs) {
    const png = svg.replace(/\.svg$/, ".png");
    const svgPath = path.join(directory, svg);
    const pngPath = path.join(directory, png);
    await sharp(svgPath, { density: 200 })
      .flatten({ background: "#ffffff" })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toFile(pngPath);
    outputs[png] = {
      bytes: fs.statSync(pngPath).size,
      sha256: sha256File(pngPath),
      source_svg: svg,
      source_svg_sha256: sha256File(svgPath),
    };
  }
  const figuresManifest = path.join(directory, "paper_figures_manifest.json");
  const figuresComplete = path.join(directory, "PAPER_FIGURES_COMPLETE.json");
  if (!fs.existsSync(figuresManifest) || !fs.existsSync(figuresComplete)) {
    throw new Error("Canonical SVG figure manifests must exist before PNG rendering");
  }
  const figuresManifestPayload = JSON.parse(fs.readFileSync(figuresManifest, "utf8"));
  const figuresCompletePayload = JSON.parse(fs.readFileSync(figuresComplete, "utf8"));
  const stageStatus = figuresCompletePayload.status;
  if (!new Set(["pass", "partial_pre_sf4"]).has(stageStatus)) {
    throw new Error(`Figure source gate has invalid stage status: ${stageStatus}`);
  }
  if (
    figuresManifestPayload.status !== stageStatus ||
    figuresManifestPayload.closure_mode !== figuresCompletePayload.closure_mode
  ) {
    throw new Error("Figure manifest/completion stage status mismatch");
  }
  fs.writeFileSync(
    path.join(directory, "PAPER_FIGURES_PNG_COMPLETE.json"),
    JSON.stringify({
      schema_version: "paper_figures_png_complete_v2",
      status: stageStatus,
      closure_mode: figuresCompletePayload.closure_mode,
      supervisor_feedback_closure_status:
        figuresCompletePayload.supervisor_feedback_closure_status,
      final_release_eligible: stageStatus === "pass",
      figure_count: svgs.length,
      conversion: {
        density_dpi: 200,
        background: "#ffffff",
        compression_level: 9,
        adaptive_filtering: true,
      },
      source_figures_manifest_sha256: sha256File(figuresManifest),
      source_figures_complete_sha256: sha256File(figuresComplete),
      renderer_source_sha256: sha256File(__filename),
      files: outputs,
    }, null, 2) + "\n"
  );
  process.stdout.write(JSON.stringify({ status: stageStatus, figure_count: svgs.length }, null, 2) + "\n");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
