package compliance.validation.action.deny.policy_0517

# Auto-generated policy 517 (Rego v1 syntax)
# Package: compliance.validation.action.deny

# Metadata
metadata := {
    "policy_id": "0517",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0517_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0517_allowed = false
policy_0517_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
