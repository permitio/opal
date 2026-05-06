package audit.enforcement.user.deny.policy_0599

# Auto-generated policy 599 (Rego v1 syntax)
# Package: audit.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0599",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0599_allowed = false
policy_0599_allowed if {
    input.user.role == "admin"
}
policy_0599_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
