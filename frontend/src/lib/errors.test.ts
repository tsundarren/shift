import { describe, expect, it } from "vitest";
import { describeError, describeThrown } from "./errors";

describe("error messages", () => {
  it("passes plain strings through", () => {
    expect(describeError("Alex isn't trained on Intake")).toBe("Alex isn't trained on Intake");
  });

  it("flattens FastAPI validation errors and hides the 'body' prefix", () => {
    const detail = [
      { loc: ["body", "blocks", 0, "headcount"], msg: "Input should be greater than or equal to 1" },
      { loc: ["body", "name"], msg: "Field required" },
    ];
    expect(describeError(detail)).toBe("blocks.0.headcount: Input should be greater than or equal to 1; name: Field required");
  });

  it("never throws on odd input", () => {
    expect(describeError(undefined)).toBe("Something went wrong");
    expect(describeError([{ weird: true }])).toBe("[object Object]");
    expect(describeThrown(new Error("boom"))).toBe("boom");
    expect(describeThrown("text")).toBe("text");
  });
});
