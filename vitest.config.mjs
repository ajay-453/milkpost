// MilkPost browser-JS tests only (the hub holds other apps; keep vitest out of them).
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { include: ["aina-out/barnboard/app/tests/js/**/*.test.js"] },
});
