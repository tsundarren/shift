/** FastAPI sends either a string (our own errors) or a list of {loc, msg} objects (request validation). */
export function describeError(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const { loc, msg } = item as { loc?: unknown[]; msg: string };
          const where = (loc ?? []).filter((part) => !["body", "query", "path"].includes(String(part))).join(".");
          return where ? `${where}: ${msg}` : msg;
        }
        return String(item);
      })
      .join("; ");
  }
  return "Something went wrong";
}

export function describeThrown(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
