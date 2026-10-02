import { FileBlob, PresentationFile } from "@oai/artifact-tool";
import fs from "node:fs/promises";

const sourcePath = "D:/Github/PertaminaGLD/docs/wiring/GLDCH.pptx";
const deck = await PresentationFile.importPptx(await FileBlob.load(sourcePath));
const snapshot = await deck.inspect({
  kind: "slide,textbox,shape,image,layout",
  maxChars: 24000,
});
console.log(snapshot.ndjson);
for (const index of [1, 4, 5, 6, 7]) {
  const slide = deck.slides.getItem(index);
  const png = await slide.export({ format: "png", scale: 1 });
  await fs.writeFile(
    `D:/Github/PertaminaGLD/.codex-ppt-build/before-${index + 1}.png`,
    new Uint8Array(await png.arrayBuffer()),
  );
}
