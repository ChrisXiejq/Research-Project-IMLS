#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

async function main() {
  const directory = path.resolve(process.argv[2] || "docs/paper/generated/paper_assets_v1/figures");
  const svgs = fs.readdirSync(directory).filter((name) => /^figure\d+.*\.svg$/.test(name)).sort();
  if (svgs.length !== 8) throw new Error(`Expected 8 SVG figures, found ${svgs.length}`);
  const outputs = {};
  for (const svg of svgs) {
    const png = svg.replace(/\.svg$/, ".png");
    await sharp(path.join(directory, svg), { density: 200 })
      .flatten({ background: "#ffffff" })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toFile(path.join(directory, png));
    outputs[png] = fs.statSync(path.join(directory, png)).size;
  }
  fs.writeFileSync(
    path.join(directory, "PAPER_FIGURES_PNG_COMPLETE.json"),
    JSON.stringify({ schema_version: "paper_figures_png_complete_v1", status: "pass", figure_count: svgs.length, files: outputs }, null, 2) + "\n"
  );
  process.stdout.write(JSON.stringify({ status: "pass", figure_count: svgs.length }, null, 2) + "\n");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
