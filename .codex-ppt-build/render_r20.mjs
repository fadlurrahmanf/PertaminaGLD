import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const deck = await PresentationFile.importPptx(await FileBlob.load(
  "D:/Github/PertaminaGLD/output/presentations/GLDCH-sensor-flow-r20.pptx",
));
for (const index of Array.from({ length: 20 }, (_, i) => i)) {
  const png = await deck.slides.getItem(index).export({ format: "png", scale: 1 });
  await fs.writeFile(`D:/Github/PertaminaGLD/.codex-ppt-build/r20-slide-${index + 1}.png`, new Uint8Array(await png.arrayBuffer()));
}
