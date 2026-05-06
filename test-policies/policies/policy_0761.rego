package audit.authorization.resource.deny.policy_0761

# Auto-generated policy 761 (Rego v1 syntax)
# Package: audit.authorization.resource.deny

# Metadata
metadata := {
    "policy_id": "0761",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0761_allowed if {
    input.user.role == "admin"
}
policy_0761_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0761_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0761_allowed = false
