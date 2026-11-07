# Seeded fixture reference — domain `delta` (NOT a real profile)

`reference` type, so the profile-schema checks do not run here. It exists to carry two
short keywords whose containing keywords differ in exactly one respect — whether the
containing keyword also reaches domain `delta`'s base row:

- `flange` is inside `alpha/notes.md`'s `delta rig flange`, which DOES contain the
  `delta rig` base keyword → reachable → the overlap must be reported. This is the
  regression control for the 2026-08-26 reachability loosening: if this row goes silent,
  the loosening has over-reached and is suppressing real findings.
- `sprocket` is inside `alpha/notes.md`'s `sprocket press`, which does NOT reach the
  `delta` base row → unreachable → the overlap must stay silent. This is the finding the
  loosening exists to remove.

Both pairs are cross-domain and neither is declared in the register, so nothing but the
reachability rule can tell them apart.
