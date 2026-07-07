import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./test/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
// React Testing Library's automatic per-test cleanup only self-registers
// when `afterEach` is a global, which it is not under `globals: false`.
// Call it explicitly here so component tests don't leak mounted DOM into
// each other (otherwise a second render() duplicates roles/text and breaks
// getByRole/getByText queries).
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());
