from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


# Capability matrix. Services MUST consult this; routes MUST enforce it.
CAPABILITIES: dict[str, set[Role]] = {
    "bot:create": {Role.ADMIN},
    "bot:edit": {Role.ADMIN},
    "bot:start": {Role.ADMIN, Role.OPERATOR},
    "bot:stop": {Role.ADMIN, Role.OPERATOR},
    "bot:archive": {Role.ADMIN},
    "bot:read": {Role.ADMIN, Role.OPERATOR, Role.REVIEWER, Role.VIEWER},

    "config:draft": {Role.ADMIN},
    "config:validate": {Role.ADMIN, Role.REVIEWER},
    "config:approve": {Role.REVIEWER},
    "config:apply": {Role.ADMIN},
    "config:rollback": {Role.ADMIN, Role.REVIEWER},
    "config:read": {Role.ADMIN, Role.OPERATOR, Role.REVIEWER, Role.VIEWER},

    "audit:read": {Role.ADMIN, Role.REVIEWER, Role.VIEWER},
    "alert:ack": {Role.ADMIN, Role.OPERATOR},
}


def can(role: Role, capability: str) -> bool:
    allowed = CAPABILITIES.get(capability)
    if allowed is None:
        return False
    return role in allowed
