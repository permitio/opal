package audit.validation.policy.deny.data.policy_0830

# Auto-generated policy 830 (Rego v1 syntax)
# Package: audit.validation.policy.deny.data

# Metadata
metadata := {
    "policy_id": "0830",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0830_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0830_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0830_allowed if {
    input.user.role == "admin"
}
default policy_0830_allowed = false
