const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const source = fs.readFileSync(path.join(__dirname, "../js/firmware.js"), "utf8");
const constants = source.slice(source.indexOf("const GLD_MODEL_SLOTS ="), source.indexOf("let builtinPackageRequestId"));
const functions = source.slice(source.indexOf("function selectedModelSlot("), source.indexOf("\nasync function refreshFirmwareUploadPorts("));
const fields = {
  firmwareUploadEnv: { value: "gld" },
  firmwareUploadModel: { value: "model_1_dataset_workflow_wifi", disabled: false },
  firmwareUploadModelStatus: { textContent: "" },
};
const select = new Function("$", `${constants}\n${functions}\nreturn updateModelSelection;`)((id) => fields[id]);
for (const model of [1, 2, 3]) {
  fields.firmwareUploadModel.value = `model_${model}_dataset_workflow_wifi`;
  fields.firmwareUploadEnv.value = "gld";
  assert.equal(select().environment, `gld_model_${model}_dataset_workflow_wifi`);
  assert.equal(select().available, true);
  fields.firmwareUploadEnv.value = "gld_atex";
  const atex = select();
  assert.equal(atex.environment, `gld_atex_model_${model}_dataset_workflow_wifi`);
  assert.equal(atex.available, false);
  assert.equal(fields.firmwareUploadModel.disabled, false);
  assert.match(fields.firmwareUploadModelStatus.textContent, /GLD ATEX/);
}
fields.firmwareUploadEnv.value = "gld";
fields.firmwareUploadModel.value = "model_1_h2_dataset_workflow_wifi";
assert.equal(select().environment, "gld_model_1_h2_dataset_workflow_wifi");
assert.equal(select().label, "Model 1 (H2, LPG, Clean Air)");
assert.match(fields.firmwareUploadModelStatus.textContent, /Model uji/);
fields.firmwareUploadEnv.value = "gld_atex";
assert.equal(select().available, false);
fields.firmwareUploadEnv.value = "gld_v2";
assert.equal(select(), null);
assert.equal(fields.firmwareUploadModel.disabled, true);
console.log("GLD1 model selection and fail-closed ATEX slots: PASS");
