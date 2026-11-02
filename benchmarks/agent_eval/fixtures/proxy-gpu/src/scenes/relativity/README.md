# Schwarzschild optical tables

The lookup parameterization, `TraceRay` GLSL and static-observer frequency/basis formulas adapt Eric Bruneton's [black-hole shader](https://github.com/ebruneton/black_hole_shader/tree/e72b3f293409893a6fa25528b29572c96fc57f57), pinned to that revision. The full BSD-3-Clause notice is retained in the adapted source files and distributed at `public/optics/LICENSE`.

Upstream source map:

- `black_hole/definitions.glsl` → `bruneton-definitions.glsl`.
- `black_hole/functions.glsl` → `bruneton-functions.glsl`. Documentation blocks were removed; logarithm and inverse-trigonometric inputs are bounded for finite evaluation at critical rays.
- `black_hole/preprocess/functions.cc` → coordinate mappings and table sampling in `optics.ts` and `scripts/generate-optics.mjs`. Integration uses fourth-order Runge–Kutta with a 0.0002-radian step. The inverse-radius table is 128 × 64.
- `black_hole/model.glsl` → static-observer specialization in `materials/relativisticHorizon.glsl`. Procedural sky, advected density and gold grading are local artistic models. There is no imported astronomical catalog, fluid simulation or Kerr spin model.

The shader explicitly filters four float texels, so sampling does not require `OES_texture_float_linear`. HDR postprocessing requires `EXT_color_buffer_float`; unavailable support triggers the still fallback. R3F owns the loop and resource lifetime. React Postprocessing provides Bloom and the single final ACES tone mapping.

Generate from the repository root with Node 22.12+ (tested on Node 24):

```sh
npm run optics:generate -w @royenheart/home
npm run proxy:test -- tests/unit/optics.test.ts
```

The tables total 2,162,704 bytes including dimension headers. `manifest.json` records SHA-256 checksums, integration parameters and source revision; it is imported into the client build to version asset requests. Every load validates length, dimensions and finite samples. Secure contexts additionally verify SHA-256 before creating textures. Plain HTTP contexts still run structural validation; build-time tests verify the checked-in checksums.

Independent symplectic Euler integration checks capture, deflection and disk intersections against the tables. Other tests cover energy conservation, the photon circular orbit, weak-field behavior, inverse-radius accuracy, asset corruption, loading deadlines and real rendered pixels. These checks establish the tested optical approximation, not scientific fidelity of artistic emission.

`framing.ts` shares the center and apparent capture radius with cube aggregation. Both directions use the same geometry and scalar progress; resizing updates both projections together.

The selected `limb` treatment retains optical sky deflection and the capture scale,
but its disk and outer light band now use a common art-directed ribbon mapping.
The mapping compresses material radius around the upper arc and expands it into
the foreground; it is not an additional geodesic disk image or fluid simulation.
The separate `optical` treatment retains both physical disk intersections.
See [the ribbon study](../../../../docs/proxy-continuous-ribbon.md) for the mapping,
diagnostic views, comparison artifacts, and visual-review status.
