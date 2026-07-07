import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { apiGet, apiPost, ApiError, NetworkError } from "./client";

const BASE_URL = "http://localhost:8000";

describe("apiGet", () => {
  it("returns the parsed JSON body on a successful response", async () => {
    server.use(http.get(`${BASE_URL}/health`, () => HttpResponse.json({ status: "ok" })));

    const result = await apiGet<{ status: string }>("/health");

    expect(result).toEqual({ status: "ok" });
  });

  it("throws ApiError with the backend's detail message on an error response", async () => {
    server.use(
      http.get(`${BASE_URL}/value-bets`, () =>
        HttpResponse.json({ detail: "no encontrado" }, { status: 404 })
      )
    );

    await expect(apiGet("/value-bets")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "no encontrado",
    });
  });

  it("throws NetworkError when the request fails at the network level", async () => {
    server.use(http.get(`${BASE_URL}/health`, () => HttpResponse.error()));

    await expect(apiGet("/health")).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("apiPost", () => {
  it("sends a JSON body and returns the parsed response", async () => {
    server.use(
      http.post(`${BASE_URL}/value-bets/settle`, async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ received: body });
      })
    );

    const result = await apiPost<{ received: unknown }>("/value-bets/settle", {
      match_id: "m1",
    });

    expect(result).toEqual({ received: { match_id: "m1" } });
  });

  it("supports calls with no body", async () => {
    server.use(http.post(`${BASE_URL}/pipeline/run`, () => HttpResponse.json({ ok: true })));

    const result = await apiPost<{ ok: boolean }>("/pipeline/run");

    expect(result).toEqual({ ok: true });
  });
});
