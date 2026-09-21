import { FileBlob, PresentationFile } from "@oai/artifact-tool";
import fs from "node:fs/promises";

const source = "D:/Github/PertaminaGLD/output/presentation/Presentasi-Rapat-Cilacap-2026-08-18.pptx";
const output = "D:/Github/PertaminaGLD/tmp/presentation-confirmed-revision/template-inspect/template-inspect-full.ndjson";

const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const snapshot = await presentation.inspect({
  kind: "slide,textbox,shape,image,table,chart",
  maxChars: 250000,
});

await fs.writeFile(output, snapshot.ndjson || "", "utf8");
