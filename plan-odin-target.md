# Plan: an Odin target for PyCrop2ML

Goal: `cyml -p <package> odin` generates an Odin package from a Crop2ML package. The
generated code has the same structure as the `cpp2` target (State/Rate/Auxiliary/Exogenous
structs, one struct + procs per ModelUnit, one Component that drives the ModelUnits), so it can
be called from `monica_odin` the way the cpp2 output is called from MONICA.

Decisions already made:

| Question | Decision |
| --- | --- |
| Shape of the generated code | Mirror cpp2 |
| Where the target lives | In-tree: `generators/odinGenerator.py`, `rules/odinRules.py`, entry `"odin"` in `target_registry.TARGETS` |
| Naming | Odin style: `snake_case` variables and procs, `Ada_Case` types (as in `monica_odin` and Odin's `core`) |

---

## 0. Feasibility

Feasible; no changes to the PyCrop2ML core are needed beyond one registry entry. The parser and
the Crop2ML syntax tree are shared by all targets. A target is a generator class that walks
that tree plus a rules class with the built-in function and type mappings.

Odin is close to C, so the statement/expression part of `cpp2Generator.py` maps almost 1:1.
Several parts get *simpler* in Odin:

* slice copies: the ~450 lines of `for (_i, _k ...)` slice-assignment cases in cpp2 become one
  `copy(dst[a:b], src[c:d])`;
* multiple return values are native (`a, b = f(x)`), no `std::tie`/`std::make_tuple`;
* no getters/setters: struct fields are public. Only the Component gets setters, for
  parameters that fan out to several ModelUnits.

Two things are *harder* and drive the design:

1. **No implicit numeric conversion.** `x / n` with `x: f64, n: int` is a compile error
   (checked with the pinned compiler). The generator must insert `f64(...)` wherever an `int`
   operand meets an `f64` operand, and wherever an `int` value is assigned or passed where an
   `f64` is expected. The syntax tree carries a `pseudo_type` on every expression, so this is
   possible, but it is the main source of compile errors to expect.
2. **No destructors.** Dynamic arrays must be freed explicitly; see the memory policy below.

Tooling: the pinned compiler `dev-2026-08` (same as `monica_odin/odin/versions.json`) is in the
Nix store. `odin check <dir> -no-entry-point` type-checks a library package without a `main`,
which is the check every stage uses. `-vet` additionally fails on unused imports and variables;
the goal is vet-clean output.

---

## 1. Mapping table (the design artifact)

| Crop2ML concept | Odin representation |
| --- | --- |
| Package `Monica_SoilTemp` | one Odin package (directory) `src/odin/Monica_SoilTemp/`, `package monica_soiltemp` |
| State / Rate / Auxiliary / Exogenous variables | `Soil_Temperature_Comp_State :: struct { ... }` etc., plus `destroy_soil_temperature_comp_state :: proc(s: ^...)` |
| ModelUnit `SoilTemperature` | `Soil_Temperature :: struct { <parameters> }` |
| Parameter defaults | `make_soil_temperature :: proc() -> Soil_Temperature` (Odin structs have no field defaults) |
| Model algorithm (`model_*`) | `soil_temperature_calculate_model :: proc(m: ^Soil_Temperature, s, s1: ^..._State, r: ^..._Rate, a: ^..._Auxiliary, ex: ^..._Exogenous)` |
| Initialisation (`init_*`) | `soil_temperature_init :: proc(<same signature>)` |
| Helper functions in a ModelUnit's algorithm | `@(private="file")` procs, so equal names in different ModelUnits don't collide in the package |
| External function libraries (`<Function>` files) | package-level procs in their own file |
| Composition | `Soil_Temperature_Comp_Component :: struct { soil_temperature: Soil_Temperature, ... }` with `make_`, `destroy_`, `_init`, `_calculate_model` procs |
| Composition parameter linked to several ModelUnits | `soil_temperature_comp_component_set_time_step :: proc(c: ^..., v: f64)` that sets it on every target ModelUnit |
| InternalLink between differently named variables | plain assignment in `_calculate_model` (as cpp2) |
| `INT` / `DOUBLE` / `BOOLEAN` / `STRING` / `DATE` | `int` / `f64` / `bool` / `string` / `string` |
| `*ARRAY` (with `len`) and `*LIST` | `[dynamic]T` (array length is set in `init`) |
| `dict` | `map[K]V` |
| helper returning a tuple | multiple return values |
| `math.*` | `core:math` (`math.pow`, `math.exp`, `math.ln`, `math.log10`, …); `min`/`max`/`abs` builtins with explicit casts |
| `a if c else b` | `c ? a : b` |
| `for i in range(a, b, s)` | `for i = a; i < b; i += s` (sign-aware for negative steps) |
| `for x in xs` | `for x in xs` |

Struct parameters inside procs are named `m, s, s1, r, a, ex`. If a model variable has one of
these names (after snake_case conversion), the struct parameter gets a trailing `_`, the same
rule cpp2 uses.

### Names

`camelCase`/`PascalCase` → `snake_case` with the usual two-step regex (`noOfTempLayersPlus1` →
`no_of_temp_layers_plus1`, `hasSnowCover` → `has_snow_cover`, `LAI` → `lai`). Types →
`Ada_Case` (`SoilTemperatureCompState` → `Soil_Temperature_Comp_State`). Odin keywords and
builtins (`in`, `map`, `proc`, `context`, `len`, `min`, `max`, …) get a trailing `_`.

The conversion can collide: Monica_SoilTemp has `V` and `B`, which become `v` and `b`. A model
with both `V` and `v` would collide. The generator detects collisions per scope and fails with
an error naming both originals instead of generating wrong code. (If this turns up in real
packages, fall back to a suffix; decide then.)

File names stay as the pipeline produces them (`SoilTemperature.odin`,
`SoilTemperatureCompComponent.odin`). Odin doesn't care, and changing it would mean touching
the shared `nameconvention.signature`.

### Memory policy

* Struct fields that are dynamic arrays are owned by their struct; each struct gets a
  `destroy_*` proc that `delete`s them. The Component's `destroy_` destroys its ModelUnits.
* `init` sizes state arrays with `resize(&s.x, n)` (+ `slice.fill` for `[v]*n`), not
  `make`, so calling `init` twice does not leak.
* Local arrays inside a proc get `defer delete(x)` unless they are returned.
* All allocations use `context.allocator`, so a host can redirect them (arena, tracking
  allocator in tests).

---

## 2. Stages

Each stage ends with: `cyml -p <scratch copy> odin` runs, and `odin check -no-entry-point`
passes on the output (from stage 2 also with `-vet`).

### Stage 1: skeleton and domain structs

* `rules/odinRules.py`: types, operators, `math`/system function map, list/array/dict/str
  methods, keyword list, `to_snake` / `to_ada` helpers.
* `generators/odinGenerator.py` with `OdinGenerator` (ModelUnits), `OdinTrans` (variable
  categories, like `Cpp2Trans.model_to_node`), `OdinCompo` (composition) and
  `to_struct_odin` (domain-class factory).
* registry entry:
  `TargetPlatform("odin", "pycropml.transpiler.generators.odinGenerator", "OdinGenerator", "OdinCompo", "odin", domain_class_factory="to_struct_odin")`.
* Output: the four domain-struct files + one struct/`make_`/`destroy_` per ModelUnit.
  Algorithms not yet translated.

### Stage 2: ModelUnit algorithms (Monica_SoilTemp)

* statements: declarations, assignment, `if`/`elif`/`else`, `for` (range, sequence, with
  index), `while`, `break`/`continue`, `return` (multiple values);
* expressions: binary/unary ops with precedence, comparisons, conditional expression, calls,
  standard calls via the rules table, indexing, slices, literals;
* the **numeric cast pass**: wrap `int`-typed operands in `f64(...)` when the other operand,
  the assignment target or the parameter is `f64`;
* struct-qualified access (`s.soil_temperature[i]`, `m.no_of_soil_layers`, `ex.tmin`);
* `init_` / `model_` procs with the shared signature;
* imports emitted only when used (`core:math`, `core:slice`), so `-vet` passes.

### Stage 3: composition

* `OdinCompo`: Component struct, `make_`/`destroy_`, setters for fan-out parameters,
  `_init` calling each ModelUnit's `init` in order, `_calculate_model` calling each ModelUnit
  and the internal-link assignments.
* Milestone: the full Monica_SoilTemp package passes `odin check -vet`.

### Stage 4: coverage against real packages

Run the target over every package in `monica_amei/SoilTemperatureModels/Models` (ApsimCampbell,
BiomaSurfacePartonSoilSWATC, BiomaSurfacePartonSoilSWATHourlyPartonC,
BiomaSurfaceSWATSoilSWATC, campbell_SoilTemp, DSSAT_EPICST_standalone, DSSAT_ST_standalone,
Simplace_Soil_Temperature, SQ_Soil_Temperature, Stics_soil_temperature) and
`EvapoTranspirationModels/Monica`. These exercise lists, strings, dates, external function
libraries, slices, tuple-returning helpers and `while` loops that Monica_SoilTemp doesn't use.
Fix generator gaps until each one passes `odin check -vet`. Report any package where another
target (e.g. cpp2) also fails, because then the problem is in the package or the shared
front end, not in the Odin target.

### Stage 5: numerical validation

For Monica_SoilTemp (then 2–3 of the others): a small Odin driver that builds the Component,
runs `init` and N days of `calculate_model` on fixed inputs, and prints the outputs. Compare
with the generated Python target (`py`) on the same inputs, to within ~1e-12 relative. This is
the only check that catches wrong casts or wrong operator precedence, which still compile.

### Stage 6: tests, docs

* `src/pycropml/transpiler/tests/`: a test that transpiles `example/Monica_SoilTemp` to Odin
  (file list, key signatures), and a compile test that runs `odin check -vet` when an `odin`
  binary is on `PATH` or in `$ODIN`, and is skipped otherwise. This keeps CI green without
  Odin.
* docs: add `odin` to the target lists (`README.rst`, `doc/`), short section on the generated
  API and the memory policy.

---

## Status (2026-10-22)

Stages 1–6 are done.

* `odin check -no-entry-point -vet` passes for all 12 packages (Monica_SoilTemp, the 10 AMEI
  soil temperature packages, both MONICA evapotranspiration packages).
* Numerical comparison with the Python target, 30 steps, every output and state:
  `test/cyml/test_odin_numerics.py` (driver and reference in `test/cyml/odin_reference.py`).
  It always runs `example/Monica_SoilTemp`; more packages via `CROP2ML_ODIN_PACKAGES`
  (directories separated by `os.pathsep`). Skipped without an Odin compiler (`$ODIN` or PATH)
  and `clang`. With all AMEI packages: 12 pass (bit-identical, or within 1e-12 for
  DSSAT_EPICST_standalone and ApsimCampbell); BiomaSurfacePartonSoilSWATHourlyPartonC fails on
  every target (see B9).

---

## Bugs found along the way

Found while building and validating the Odin target. "Odin" says whether the Odin target is
affected. Who to tell: **PyCrop2ML** = upstream PyCrop2ML; **model** = the authors of that
Crop2ML package.

### Shared front end (all targets)

* **B1 Cython 3, fixed here.** `ast_transform.py`: `visit_condexprnode` (Cython 3 renamed
  `CondExprNode.test` to `condition`) and `visit_cenumdefnode` (new `underlying_type` field).
  Before the fix, every package with a conditional expression (`a if c else b`) failed to
  transpile: ApsimCampbell, SQ_Soil_Temperature, Monica_Evapotranspiration. Works with Cython
  0.29 and 3.x. Tell: PyCrop2ML (part of the upstream contribution).
* **B2 No `|` operator.** `ast_transform.py` has no `visit_bitwiseornode`;
  `test/cyml/test_cyml_operations.py::TestCyMLDataFiles::test_advanced_features_file` fails.
  Not fixed. Tell: PyCrop2ML.
* **B3 Composition `init` ignores renamed InputLinks.** `topology.py`, `algo2cyml`: the model
  function gets `inps_assignment()` (line 335; e.g. `Albedo = cAlbedo`), the init function
  (lines 353–360, `val_init2` + `initialization2`) does not. `initialization2` (lines 391–411)
  then passes the ModelUnit's name (`Albedo`), which the composition's init doesn't have. In
  Python that is a `NameError` (Simplace_Soil_Temperature); in cpp2 the ModelUnit init reads
  unset fields (`iTempMax`, `iRadiation` in Simplace's SnowCoverCalculator). Odin: handled in
  `OdinCompo.renamed_input_links`. The real fix belongs in `algo2cyml`. Tell: PyCrop2ML.

### cpp2 target

* **B4 A ModelUnit uses its own variable categories, not the composition's.**
  `cpp2Generator.py` lines 41–46: `Cpp2Generator.__init__` categorises with
  `Cpp2Trans([model])`, i.e. from the ModelUnit's XML. `struct_name_for` (line 1161) uses those
  lists, and `visit_local` (lines 250–256) prefixes `s.`/`r.`/`a.`/`ex.` accordingly. The
  domain structs are built from the composition (`header_cpp`, line 1886, `Cpp2Trans(models)`
  with the composition). When the two disagree, the generated code doesn't compile. Example:
  BiomaSurfacePartonSoilSWATHourlyPartonC, `unit.ThermalDiffu.xml` declares
  `ThermalConductivity` auxiliary, the composition makes it a state → `a.ThermalConductivity`
  (also `HeatCapacity`, `SoilTemperatureMinimum`). Odin: handled (`composition_of`, categories
  from the composition, unit categories only as fallback). Tell: PyCrop2ML.
* **B5 `log(x, base)` drops the base.** The front end maps `log(x)` to `ln` and
  `log(x, base)` to `log` (`api_transform.py` lines 224–227), so the targets' `log` rule only
  sees the two-argument form. cpp/cpp2/java translate it to `log10(x)`, ignoring the base:
  `cppRules.py` lines 14–15 and 173, `cpp2Rules.py` lines 13–14 and 177 (the rules cpp2 uses),
  `javaRules.py` lines 50–51 and 113. Correct elsewhere: Python `log(x, b)`, C# `Math.Log(x, b)`,
  R `log(x, b)`, Fortran `LOG(x)/LOG(b)`, Odin `math.log(x, b)`. One-argument `log(x)` is
  correct on every target. No AMEI package uses the two-argument form (`log(x, 10)` would even
  be right by accident), so no current results are wrong; it's an inconsistency that bites
  the first model that uses another base. Tell: PyCrop2ML, and mention it to the other model
  teams in case they have unpublished models using `log(x, base)`.

### Python target

* **B6 Single precision arrays.** Generated code uses `array('f', ...)` (120 places in the AMEI
  packages), so all arrays are 32-bit floats; every other target uses doubles.
* **B7 The composition function is not stateful.** It re-declares states as fresh locals
  (`soilTemperature = array('f', [0.0]*n)`) on every call, so e.g. Monica_SoilTemp's soil
  temperature profile is reset to zero each day, and it uses states it never receives
  (`soilSurfaceTemperature` in Monica_SoilTemp → `UnboundLocalError`). ModelUnit parameters
  the composition doesn't expose (`potential_evapotranspiration_cap`) are declared but never
  set.
* **B8** The composition init has B3 as well. Tell (B6–B8): PyCrop2ML.

### Models

* **B9 BiomaSurfacePartonSoilSWATHourlyPartonC can't run.** Its arrays have no length
  (`len=""`), the composition sizes them with `DayLength` (a DOUBLE), and nothing allocates
  `ThermalDiffusivity`/`HeatCapacity` before `ThermalDiffu` indexes them: Python
  `IndexError`, Odin bounds-check panic in `ThermalDiffu.odin`, cpp2 out-of-bounds write.
  Tell: model (Bioma).
* **B10 MONICA radiation: result unassigned with the default input.**
  `monica_amei/EvapoTranspirationModels/Monica/Monica_Evapotranspiration/crop2ml/algo/pyx/radiation.pyx`
  lines 41–45: `sunshine_hours_global_radiation` is only assigned inside
  `if sunshine_hours > 0.0:`. `sunshine_hours` has `default="0"` (`unit.radiation.xml`). Python:
  `UnboundLocalError`; C++: uninitialised `double`; Odin: 0.0. Fix: assign it (probably 0.0)
  in an `else` branch. Tell: model (MONICA, i.e. us).
* **B11 MONICA stomata resistance: result unassigned with the default input.** Same package,
  `algo/pyx/stomata_resistance.pyx` line 5: `stomata_resistance` is only assigned inside
  `if carboxylation_pathway > 0:`; `carboxylation_pathway` has `default="0"`
  (`unit.stomata_resistance.xml`). Same consequences and fix as B10. Tell: model (MONICA).

## 3. Out of scope (for now)

* notebook generation (`generate_notebooks`, cpp2 doesn't do it either);
* a platform wrapper (`wrapper_factory`);
* translating Odin back into Crop2ML (a *source* platform).

## 4. Open points (decide when they come up)

* name collisions after snake_case conversion (see Names);
* whether `monica_odin` wants an allocator parameter on `make_*`/`init` instead of
  `context.allocator`;
* fixed-size arrays (`[N]f64`) for arrays whose `len` is a literal, instead of `[dynamic]`.
