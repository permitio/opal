package audit.enforcement.action.deny.policy_0212

# Auto-generated policy 212 (Rego v1 syntax)
# Package: audit.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0212",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0212_allowed if {
    input.user.role == "admin"
}
policy_0212_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0212_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
