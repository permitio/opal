package risk.validation.action.allow.policy_0457

# Auto-generated policy 457 (Rego v1 syntax)
# Package: risk.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0457",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0457_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0457_allowed = false
policy_0457_allowed if {
    input.user.role == "admin"
}
