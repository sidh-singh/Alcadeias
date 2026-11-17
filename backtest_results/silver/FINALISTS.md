# Silver study: the finalists (PREREG_SILVER.md §5.2-5.3)

**Finalists: 0.**

- The DEV shortlist is empty (`SHORTLIST.md`, sha256 `141bbf3fd9daa0c6aa27abd742be66157052f51cff5ca97155fad98554c4c3c3`): none of the 144 variants passed all of D1-D7 on DEV.
- So no variant ran on VAL, no sizing was chosen, and there is nothing to freeze.
- **The hold-out (2024-07-01 → 2026-11-13) is not run.** It stays clean for a future pre-registered idea (§5.2).
  Spending it on a near miss would need the owner's explicit decision and would be a deviation.
- `backtesting/research/silver.py` refuses any load past 2024-07-01 unless this file matches its sha256 **and** names at least one
  finalist. Module sha256 at freezing: `808a03b74a3dea1d513e63aba950fcde4ec3564ce94c2061b3bac22ad593201e`.
