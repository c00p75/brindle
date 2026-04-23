import type { Role } from "./types";

const MATRIX: Record<string, Role[]> = {
  "bot:create": ["admin"],
  "bot:edit": ["admin"],
  "bot:start": ["admin", "operator"],
  "bot:stop": ["admin", "operator"],
  "bot:archive": ["admin"],
  "bot:read": ["admin", "operator", "reviewer", "viewer"],
  "config:draft": ["admin"],
  "config:validate": ["admin", "reviewer"],
  "config:approve": ["reviewer"],
  "config:apply": ["admin"],
  "config:rollback": ["admin", "reviewer"],
  "config:read": ["admin", "operator", "reviewer", "viewer"],
  "audit:read": ["admin", "reviewer", "viewer"],
  "alert:ack": ["admin", "operator"],
};

export function can(role: Role | undefined, capability: string): boolean {
  if (!role) return false;
  return MATRIX[capability]?.includes(role) ?? false;
}
