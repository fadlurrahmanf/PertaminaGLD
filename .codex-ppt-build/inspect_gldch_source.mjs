import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const deck = await PresentationFile.importPptx(
  await FileBlob.load("D:/Github/PertaminaGLD/docs/wiring/GLDCH.pptx"),
);
console.log((await deck.inspect({
  kind: "slide,textbox,shape,image,layout",
  maxChars: 30000,
})).ndjson);
