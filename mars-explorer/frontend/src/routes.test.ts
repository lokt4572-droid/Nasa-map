import { describe, expect, it } from "vitest";

import { hrefFor, pageFor } from "./routes";

describe("site routes", () => {
  it("maps paths to pages with or without a trailing slash", () => {
    expect(pageFor("/", "")).toBe("home");
    expect(pageFor("/index.html", "")).toBe("home");
    expect(pageFor("/rover", "")).toBe("rover");
    expect(pageFor("/rover/", "")).toBe("rover");
    expect(pageFor("/map/", "")).toBe("map");
    expect(pageFor("/map", "")).toBe("map");
    expect(pageFor("/nope/", "")).toBe("notfound");
  });

  it("works under a deployment sub-path", () => {
    expect(pageFor("/mars/map/", "/mars")).toBe("map");
    expect(pageFor("/mars/", "/mars")).toBe("home");
    expect(hrefFor("map", "/mars")).toBe("/mars/map/");
    expect(hrefFor("home", "")).toBe("/");
  });
});
