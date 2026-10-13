The mirror update is complete. `ajay-453/milkpost` is now at 91e7225. The first Actions run passed both jobs.

- **Python tests:** mypy found no errors. All 87 tests passed. Coverage is 100%.
- **Browser JS:** all 17 tests passed. Stryker killed 106 of 106 mutants.
- **Mirror files:** the root now has `package.json`, `package-lock.json`, `vitest.config.mjs` and `stryker.config.json`.

The push was a normal update. Thus the force flag was not necessary. F5.4 and F6.6 stay partly done until the scan result comes back. The tracker push is fcaf94d.

<!-- ste:strict -->
Next step (you):
1. Scan `https://github.com/ajay-453/milkpost` again on testforge.run.
2. Save the report in Downloads.
<!-- ste:end -->

The TestForge score code gives these numbers: **Unit Tests 100, DORA 90, Mutation 90**. The scan must not show the two old findings about the lockfile and the mutation tool. If a score is different, I will find the TestForge rule that caused it.
