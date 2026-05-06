package audit.enforcement.resource.check.policy_0543

# Auto-generated policy 543 (Rego v1 syntax)
# Package: audit.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0543",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0543_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0543_allowed if {
    input.user.active
    input.resource.public
}
default policy_0543_allowed = false
policy_0543_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
