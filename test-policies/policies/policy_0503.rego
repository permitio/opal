package risk.enforcement.action.deny.utils.policy_0503

# Auto-generated policy 503 (Rego v1 syntax)
# Package: risk.enforcement.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0503",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0503_allowed = false
policy_0503_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0503_allowed if {
    input.user.active
    input.resource.public
}
policy_0503_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
