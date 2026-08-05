# GLD model slots

Each slot represents one independently compiled GLD inference model.  A slot
is selectable in Operator Hub only after its verified firmware package exists.

`model_1` is the default source for the GLD production environment. Select
`model_2` only for a Board 2 package; its build overrides the default slot.

For a new slot, provide a compatible set of artifacts before enabling it:

- `model_data.cpp` and `model_data.h` (TFLite bytes and symbol names)
- `ModelMetadata.h` (profile/scaler identity, input/output contract, class map)
- `cnn_gas_datasheet_normalize_params.h`
- `cnn_gas_sensitivity_table.h` when the model uses evidence features

Do not copy Model 1 into another slot merely to make the selector available.
That would make two labels point to the same compiled inference model.
